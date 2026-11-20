"""Validate private active-source bindings without Git or network access."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import re
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA = "memory-source-classification/v1"
MAX_POLICY_BYTES = 1024 * 1024


class PolicyError(ValueError):
    pass


def canonical_path(value: object) -> str:
    if not isinstance(value, str) or not value or not Path(value).is_absolute():
        raise PolicyError("local alias must be an absolute path")
    try:
        canonical = str(Path(value).resolve(strict=False))
    except (OSError, RuntimeError, ValueError) as exc:
        raise PolicyError("cannot resolve local alias") from exc
    if canonical != value:
        raise PolicyError("local alias must be canonical (no symlink, dot or trailing slash)")
    return canonical


def normalize_origin(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PolicyError("origin alias must be nonempty text")
    value = value.strip().rstrip("/")
    try:
        if "://" in value:
            parsed = urlsplit(value)
            if parsed.scheme not in {"ssh", "https", "http", "git"} or not parsed.hostname:
                raise PolicyError("unsupported origin locator")
            if (parsed.query or parsed.fragment or parsed.password
                    or (parsed.username is not None and parsed.scheme != "ssh")):
                raise PolicyError("origin must not contain credentials, query or fragment")
            host = parsed.hostname
            if ":" in host:
                host = f"[{host}]"
            port = parsed.port  # Validates numeric range and malformed ports.
            if port is not None:
                if port == 0:
                    raise PolicyError("invalid origin port")
                defaults = {"ssh": 22, "https": 443, "http": 80, "git": 9418}
                if port != defaults[parsed.scheme]:
                    host += f":{port}"
            path = parsed.path.strip("/")
        elif len(value.split("/")) == 2 and not re.search(r"[:@\s]", value):
            # agent-route's installed map protocol uses GitHub owner/repo.
            # This normalizes a locator; it never assigns classification.
            host, path = "github.com", value
        elif len(value.split("/")) == 3 and "@" not in value.split("/")[0]:
            # Canonical host[:port]/owner/repository keeps an explicit port.
            # It may represent a non-default port for a different protocol.
            authority, owner, repository = value.split("/")
            parsed = urlsplit("//" + authority)
            if not parsed.hostname or parsed.username or parsed.password:
                raise PolicyError("invalid origin authority")
            port = parsed.port
            if port == 0:
                raise PolicyError("invalid origin port")
            host = parsed.hostname
            if ":" in host:
                host = f"[{host}]"
            if port is not None:
                host += f":{port}"
            path = owner + "/" + repository
        else:
            match = re.fullmatch(r"(?:[^/@:]+@)?([^/:]+):(.+)", value)
            if not match:
                raise PolicyError("origin alias requires a host and repository path")
            host, path = match.groups()
    except ValueError as exc:
        raise PolicyError("invalid origin locator or port") from exc
    path = path.rstrip("/").lower()
    if path.endswith(".git"):
        path = path[:-4]
    if not host or re.search(r"\s", host) or not re.fullmatch(r"[^\s/]+/[^\s/]+", path):
        raise PolicyError("origin alias requires owner/repository")
    return f"{host.lower()}/{path}"


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise PolicyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


class Policy:
    def __init__(self, payload: object, digest: str) -> None:
        if not isinstance(payload, dict) or set(payload) != {"schema", "repositories", "excluded_paths"}:
            raise PolicyError("policy requires schema, repositories and excluded_paths only")
        if payload["schema"] != SCHEMA:
            raise PolicyError("unsupported classification schema")
        if not isinstance(payload["repositories"], list) or not isinstance(payload["excluded_paths"], list):
            raise PolicyError("repositories and excluded_paths must be arrays")
        self.digest = digest
        self.excluded = tuple(Path(canonical_path(path)) for path in payload["excluded_paths"])
        self.bindings: dict[tuple[str, str], tuple[str, str, frozenset[str]]] = {}
        self.ids: set[str] = set()
        local_owners: dict[str, str] = {}
        origin_owners: dict[str, str] = {}
        for row in payload["repositories"]:
            if not isinstance(row, dict) or set(row) != {"repository_id", "classification", "active_bindings", "origin_aliases"}:
                raise PolicyError("invalid repository record")
            identity, kind = row["repository_id"], row["classification"]
            if not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", identity) or identity in self.ids:
                raise PolicyError("repository_id must be unique stable text")
            self.ids.add(identity)
            if kind not in {"personal", "work", "unknown"}:
                raise PolicyError("invalid repository classification")
            if not isinstance(row["active_bindings"], list) or not isinstance(row["origin_aliases"], list):
                raise PolicyError("bindings and origins must be arrays")
            origins = frozenset(normalize_origin(origin) for origin in row["origin_aliases"])
            for origin in origins:
                if origin in origin_owners and origin_owners[origin] != identity:
                    raise PolicyError("origin alias assigned to different repository IDs")
                origin_owners[origin] = identity
            for binding in row["active_bindings"]:
                if not isinstance(binding, dict) or set(binding) != {"primary_path", "git_common_dir"}:
                    raise PolicyError("active binding requires paired primary_path and git_common_dir")
                primary = canonical_path(binding["primary_path"])
                common = canonical_path(binding["git_common_dir"])
                if self.is_excluded(Path(primary)) or self.is_excluded(Path(common)):
                    raise PolicyError("active binding overlaps excluded storage")
                for alias in (primary, common):
                    if alias in local_owners and local_owners[alias] != identity:
                        raise PolicyError("local alias assigned to different repository IDs")
                    local_owners[alias] = identity
                key = (primary, common)
                if key in self.bindings:
                    raise PolicyError("duplicate active binding")
                self.bindings[key] = (identity, kind, origins)

    def is_excluded(self, path: Path) -> bool:
        return any(path == prefix or prefix in path.parents for prefix in self.excluded)

    def resolve(self, root: dict, path: Path) -> tuple[str, str] | None:
        # Historical identity never grants admission. Exclude storage before
        # matching metadata and before the caller opens a memory file.
        if self.is_excluded(path):
            return None
        primary, common = root.get("primary_abs_path"), root.get("git_common_dir")
        if not isinstance(primary, str) or not isinstance(common, str):
            return None
        try:
            primary, common = canonical_path(primary), canonical_path(common)
        except PolicyError:
            return None
        if self.is_excluded(Path(primary)) or self.is_excluded(Path(common)):
            return None
        record = self.bindings.get((primary, common))
        if record is None:
            return None
        identity, kind, origins = record
        if kind == "unknown":
            return None
        # Observed disagreement invalidates this binding. Origin never creates
        # an assignment or another independent corroborating repository.
        observed_origins: set[str] = set()
        for field in ("origin", "live_origin"):
            observed = root.get(field)
            if observed:
                try:
                    normalized = normalize_origin(observed)
                except PolicyError:
                    return None
                if origins and normalized not in origins:
                    return None
                observed_origins.add(normalized)
        if len(observed_origins) > 1:
            return None
        return identity, kind


def open_directory(path: Path, *, directory_fd: int | None = None) -> int:
    if directory_fd is None:
        if not path.is_absolute():
            raise PolicyError("directory must be absolute")
        descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        components = path.parts[1:]
    else:
        if path.is_absolute() or ".." in path.parts:
            raise PolicyError("anchored directory must stay relative")
        descriptor = os.dup(directory_fd)
        components = path.parts
    try:
        for component in components:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def open_install_lock(path: Path):
    """Open the cooperating installer/reader lock without following a link."""
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise PolicyError("installation lock must be a current-user regular file")
        os.fchmod(descriptor, 0o600)
        return os.fdopen(descriptor, "r+")
    except Exception:
        os.close(descriptor)
        raise


def read_regular_file(path: Path, *, private: bool = False,
                      directory_fd: int | None = None) -> tuple[bytes, int]:
    parent_fd = None
    try:
        if directory_fd is not None:
            parent_fd = open_directory(path.parent, directory_fd=directory_fd)
        descriptor = os.open(path.name if parent_fd is not None else path,
                             os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=parent_fd)
    finally:
        if parent_fd is not None:
            os.close(parent_fd)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        mode = stat.S_IMODE(info.st_mode)
        if not stat.S_ISREG(info.st_mode):
            raise PolicyError("input must be a regular file")
        if private and (info.st_uid != os.getuid() or mode != 0o600):
            raise PolicyError("classification policy must be current-user owned with mode 0600")
        if info.st_size > MAX_POLICY_BYTES:
            raise PolicyError("input exceeds 1 MiB limit")
        data = handle.read(MAX_POLICY_BYTES + 1)
        if len(data) > MAX_POLICY_BYTES:
            raise PolicyError("input exceeds 1 MiB limit")
        return data, mode


def read_policy_file(path: Path, *, private: bool = False) -> tuple[bytes, int]:
    return read_regular_file(path, private=private)


def load_policy(path: Path) -> Policy:
    try:
        data, _ = read_policy_file(path, private=True)
        payload = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
        return Policy(payload, hashlib.sha256(data).hexdigest())
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise PolicyError(f"invalid classification policy: {exc}") from exc
