#!/usr/bin/env python3
"""Govern the local Cursor marketplace continual-learning plugin.

v3 (continual-learning decoupling): the governor now RETARGETS the plugin's write target from the
tracked ``AGENTS.md`` to the machine-local, git-ignored ``agent-learnings.md`` via a finite
BLESSED / CONTAINABLE / INCOMPATIBLE compatibility state machine with fail-closed stop-hook
neutralization, in addition to projecting the 50/1440 cadence. It also OWNS the global git exclude
(``agent-learnings.md`` + ``.cursor/hooks/state/``). It does not vendor the plugin payload.

Safety-bearing signal is the behavior fingerprint (``meta.provenance_ref``); plugin version and cache
revision are advisory provenance. See ``plugin.json`` ``compatibilityMatrix`` for the change fan-out.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any


CAP_DIR = Path(__file__).resolve().parents[1]
DESCRIPTOR = CAP_DIR / "plugin.json"
META = CAP_DIR / "meta.yml"

STATE_BLESSED = "blessed"
STATE_CONTAINABLE = "containable"
STATE_INCOMPATIBLE = "incompatible"
_SEVERITY = {STATE_BLESSED: 0, STATE_CONTAINABLE: 1, STATE_INCOMPATIBLE: 2}


# ----------------------------------------------------------------------------- basics

def load_json(path: Path) -> Any:
    with path.open() as fh:
        return json.load(fh)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def descriptor_hash(path: Path = DESCRIPTOR) -> str:
    data = load_json(path)
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return sha256_text(canonical)


def meta_field(key: str, path: Path = META) -> str:
    if not path.exists():
        return ""
    prefix = f"{key}:"
    for line in path.read_text().splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip().strip("\"'")
    return ""


def cursor_home() -> Path:
    return Path(os.environ.get("CURSOR_HOME", Path.home() / ".cursor")).expanduser()


def hooks_json_path() -> Path:
    return Path(
        os.environ.get("CONTINUAL_LEARNING_CURSOR_HOOKS_JSON", cursor_home() / "hooks.json")
    ).expanduser()


def governor_state_dir() -> Path:
    return cursor_home() / "continual-learning-governor"


def cache_bases(desc: dict[str, Any]) -> list[Path]:
    override = os.environ.get("CONTINUAL_LEARNING_PLUGIN_CACHE_BASE")
    raw = override or desc["marketplace"]["cacheBase"]
    return [Path(part).expanduser() for part in raw.split(os.pathsep) if part]


# ----------------------------------------------------------------------------- discovery

def read_plugin_metadata(root: Path, desc: dict[str, Any]) -> dict[str, Any] | None:
    metadata_path = root / desc["cacheDiscovery"]["pluginJson"]
    if not metadata_path.exists():
        return None
    try:
        metadata = load_json(metadata_path)
    except Exception:
        return None
    if metadata.get("name") != desc["cacheDiscovery"]["pluginName"]:
        return None
    if metadata.get("hooks") != desc["cacheDiscovery"]["hooksField"]:
        return None
    return metadata


def discover_cache_roots(desc: dict[str, Any]) -> list[Path]:
    """Re-walk cacheBase every invocation so a freshly installed hash dir is found immediately
    (no cached sentinel). This is what makes a new cache revision project on the very next run."""
    roots: list[Path] = []
    for base in cache_bases(desc):
        if not base.exists():
            continue
        for current, dirs, _files in os.walk(base):
            cur = Path(current)
            if read_plugin_metadata(cur, desc) is not None:
                roots.append(cur)
                dirs[:] = []
    return sorted(set(roots))


def hooks_path(cache_root: Path, desc: dict[str, Any]) -> Path:
    return cache_root / desc["cacheDiscovery"]["hooksField"].lstrip("./")


# ----------------------------------------------------------------------------- cadence (env-prefix)

ENV_TOKEN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")


def split_env_prefix(command: str) -> tuple[list[str], str]:
    parts = command.split()
    idx = 0
    while idx < len(parts) and ENV_TOKEN_RE.match(parts[idx]):
        idx += 1
    return parts[:idx], " ".join(parts[idx:])


def command_env(command: str) -> dict[str, str]:
    env_tokens, _suffix = split_env_prefix(command)
    out: dict[str, str] = {}
    for token in env_tokens:
        key, value = token.split("=", 1)
        out[key] = value
    return out


def projected_command(command: str, target: dict[str, Any]) -> str:
    _env_tokens, suffix = split_env_prefix(command)
    prefix = " ".join(f"{k}={v}" for k, v in target["envPrefix"].items())
    return f"{prefix} {suffix}".strip()


def matching_entries(data: dict[str, Any], target: dict[str, Any]) -> list[dict[str, Any]]:
    entries = data.get("hooks", {}).get(target["hook"], [])
    return [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and isinstance(entry.get("command"), str)
        and target["commandContains"] in entry["command"]
    ]


def cadence_ok(cache_root: Path, desc: dict[str, Any]) -> tuple[bool, str]:
    path = hooks_path(cache_root, desc)
    try:
        data = load_json(path)
    except Exception as exc:
        return False, f"could not parse {path}: {exc}"
    for target in desc["patchTargets"]:
        matches = matching_entries(data, target)
        if len(matches) != 1:
            return False, f"{path}: expected one {target['hook']} command match, found {len(matches)}"
        env = command_env(matches[0]["command"])
        for key, value in target["envPrefix"].items():
            if env.get(key) != value:
                return False, f"{path}: {key}={env.get(key, '<missing>')} expected {value}"
    return True, "ok"


# ----------------------------------------------------------------------------- atomic IO + backups

def atomic_json_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def content_backup(path: Path, original: bytes, suffix: str = "kp-cl") -> Path:
    """Content-addressed, never-overwritten backup so a good original is never clobbered by a
    partial re-run (kill-interrupt recovery)."""
    digest = sha256_bytes(original)[:12]
    bak = path.parent / f".{path.name}.{digest}.{suffix}.bak"
    if not bak.exists():
        _write_bytes_atomic(bak, original)
    return bak


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


# ----------------------------------------------------------------------------- fingerprint

def _canonical_cadence_command(command: str, target: dict[str, Any]) -> str | None:
    """Return the projected form only for a command shape the governor owns.

    A fresh upstream cache has the exact bare ``bun run`` command. Older caches and the
    governor projection carry exactly the two numeric cadence assignments in descriptor order.
    Anything else stays byte-distinct so it cannot inherit the approved fingerprint.
    """
    command_contains = target.get("commandContains")
    env_prefix = target.get("envPrefix")
    if not isinstance(command_contains, str) or not isinstance(env_prefix, dict):
        return None

    bare_command = f"bun run ${{CURSOR_PLUGIN_ROOT}}/{command_contains.lstrip('/')}"
    env_tokens, suffix = split_env_prefix(command)
    if suffix != bare_command:
        return None
    if not env_tokens:
        if command != bare_command:
            return None
        return projected_command(command, target)

    # Reject extra, missing, reordered, non-numeric, or oddly spaced assignments. The
    # projection itself emits this exact shape, while malformed variants remain unblessed.
    if command != " ".join([*env_tokens, suffix]):
        return None
    expected_keys = list(env_prefix)
    if len(env_tokens) != len(expected_keys):
        return None
    for token, expected_key in zip(env_tokens, expected_keys):
        actual_key, value = token.split("=", 1)
        if actual_key != expected_key or not value.isdigit():
            return None
    return projected_command(command, target)


def _canonicalize_cadence_manifest(text: str, desc: dict[str, Any]) -> str:
    """Project recognized hook commands in memory without reformatting the manifest."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text
    if not isinstance(data, dict):
        return text
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return text

    for target in desc.get("patchTargets", []):
        command_contains = target.get("commandContains")
        if not isinstance(command_contains, str):
            continue
        entries = hooks.get(target.get("hook"))
        if not isinstance(entries, list):
            continue
        matches = [
            entry
            for entry in entries
            if isinstance(entry, dict)
            and isinstance(entry.get("command"), str)
            and command_contains in entry["command"]
        ]
        if len(matches) != 1:
            continue
        command = matches[0]["command"]
        canonical = _canonical_cadence_command(command, target)
        if canonical is None or canonical == command:
            continue
        encoded_command = json.dumps(command)
        if text.count(encoded_command) != 1:
            continue
        text = text.replace(encoded_command, json.dumps(canonical), 1)
        matches[0]["command"] = canonical
    return text


def normalize_behavior(path: Path, desc: dict[str, Any]) -> bytes:
    text = path.read_text()
    hooks_parts = Path(desc["cacheDiscovery"]["hooksField"].lstrip("./")).parts
    if hooks_parts and tuple(path.parts[-len(hooks_parts):]) == hooks_parts:
        text = _canonicalize_cadence_manifest(text, desc)
    for key in desc["behaviorContract"]["normalizeEnvKeys"]:
        text = re.sub(rf"{re.escape(key)}=[0-9]+", f"{key}=<governed>", text)
    # Normalize BOTH target-filename tokens so the fingerprint is invariant to whether the
    # retarget projection has run (projection never self-drifts provenance).
    for tok in desc["behaviorContract"].get("normalizeTargetTokens", []):
        text = text.replace(tok, "<governed-target>")
    return text.encode("utf-8")


def behavior_hash(cache_root: Path, desc: dict[str, Any]) -> str:
    h = hashlib.sha256()
    for rel in desc["behaviorContract"]["files"]:
        path = cache_root / rel
        if not path.exists():
            raise FileNotFoundError(f"behaviorContract file missing: {rel}")
        h.update(rel.encode("utf-8") + b"\0")
        h.update(normalize_behavior(path, desc) + b"\0")
    return h.hexdigest()


# ----------------------------------------------------------------------------- retarget (writers)

def _retarget_file_state(cache_root: Path, target: dict[str, Any]) -> tuple[str, int, int] | None:
    path = cache_root / target["file"]
    if not path.exists():
        return None
    text = path.read_text()
    return text, text.count(target["from"]), text.count(target["to"])


def validate_retarget(cache_root: Path, desc: dict[str, Any]) -> tuple[bool, str]:
    """Validate ALL retarget targets before writing ANY. Exact-count guard: the sum of
    (from + to) tokens in each file must equal expectedCount; otherwise the write target cannot be
    trusted and the root is INCOMPATIBLE."""
    for t in desc["retargetTargets"]:
        st = _retarget_file_state(cache_root, t)
        if st is None:
            return False, f"{t['file']}: missing"
        _text, n_from, n_to = st
        if n_from + n_to != t["expectedCount"]:
            return False, f"{t['file']}: from={n_from} to={n_to} (expected {t['expectedCount']})"
    return True, "ok"


def apply_retarget_all(cache_root: Path, desc: dict[str, Any]) -> tuple[bool, str]:
    """validate-all-before-write; content-addressed backups; write order
    updater -> skill -> stop.ts -> cadence; verify-set; restore-on-fail."""
    ok, detail = validate_retarget(cache_root, desc)
    if not ok:
        raise RuntimeError(f"retarget validation failed: {detail}")

    written: list[tuple[Path, bytes]] = []  # (path, original_bytes) for restore
    changed_any = False
    try:
        for t in desc["retargetTargets"]:
            path = cache_root / t["file"]
            original = path.read_bytes()
            text = original.decode("utf-8")
            n_from = text.count(t["from"])
            if n_from == 0:  # already retargeted for this file
                continue
            content_backup(path, original)
            written.append((path, original))
            atomic_write_text(path, text.replace(t["from"], t["to"]))
            changed_any = True
        # cadence last (its own fixed .kp-governance.bak)
        cadence_changed = project_cadence(cache_root, desc)
        changed_any = changed_any or cadence_changed

        # verify-set: every retarget target now all-`to`, zero-`from`; cadence correct
        for t in desc["retargetTargets"]:
            st = _retarget_file_state(cache_root, t)
            if st is None:
                raise RuntimeError(f"{t['file']} vanished during retarget")
            _text, n_from, n_to = st
            if n_from != 0 or n_to != t["expectedCount"]:
                raise RuntimeError(f"{t['file']} verify failed: from={n_from} to={n_to}")
        cad_ok, cad_msg = cadence_ok(cache_root, desc)
        if not cad_ok:
            raise RuntimeError(f"cadence verify failed: {cad_msg}")
    except Exception:
        # restore-on-fail: put the writers back exactly
        for path, original in written:
            try:
                _write_bytes_atomic(path, original)
            except OSError:
                pass
        raise
    return changed_any, ("projected" if changed_any else "already projected")


def project_cadence(cache_root: Path, desc: dict[str, Any]) -> bool:
    path = hooks_path(cache_root, desc)
    data = load_json(path)
    changed = False
    for target in desc["patchTargets"]:
        matches = matching_entries(data, target)
        if len(matches) != 1:
            raise RuntimeError(f"{path}: expected one {target['hook']} command match, found {len(matches)}")
        entry = matches[0]
        new_command = projected_command(entry["command"], target)
        if entry["command"] != new_command:
            entry["command"] = new_command
            changed = True
    if not changed:
        return False
    backup = path.with_suffix(path.suffix + ".kp-governance.bak")
    if not backup.exists():
        shutil.copy2(path, backup)
    else:
        shutil.copy2(path, path.with_suffix(path.suffix + ".kp-governance.prev.bak"))
    atomic_json_write(path, data)
    load_json(path)
    return True


# ----------------------------------------------------------------------------- neutralization (fail-closed)

def neutralize(cache_root: Path, desc: dict[str, Any]) -> str:
    """Fail-closed containment for an INCOMPATIBLE cache: the plugin must not be able to write
    AGENTS.md. Rewrite the stop-hook command to a contained no-op; if the command is unlocatable,
    write an empty ``stop: []``; if hooks.json is unparseable, write a minimal contained hooks file."""
    nt = desc["neutralize"]
    path = hooks_path(cache_root, desc)
    if not path.exists():
        _write_bytes_atomic(path, json.dumps({"version": 1, "hooks": {"stop": []}}, indent=2).encode() + b"\n")
        return "hooks.json absent; wrote contained empty stop[]"
    original = path.read_bytes()
    content_backup(path, original, suffix="kp-cl-neutralize")
    try:
        data = json.loads(original.decode("utf-8"))
    except Exception:
        _write_bytes_atomic(path, json.dumps({"version": 1, "hooks": {"stop": []}}, indent=2).encode() + b"\n")
        return "hooks.json unparseable; wrote contained empty stop[]"

    entries = data.setdefault("hooks", {}).setdefault(nt["hook"], [])
    matches = [
        e for e in entries
        if isinstance(e, dict) and nt["commandContains"] in str(e.get("command", ""))
    ]
    if matches:
        for e in matches:
            e["command"] = nt["noopCommand"]
        detail = f"rewrote {len(matches)} stop hook command(s) to contained no-op"
    else:
        data["hooks"][nt["hook"]] = []
        detail = "stop hook command unlocatable; wrote empty stop[]"
    atomic_json_write(path, data)
    # verify: no live command referencing the stop-hook script remains under the stop hook
    after = load_json(path)
    after_entries = after.get("hooks", {}).get(nt["hook"], [])
    live = [
        e for e in after_entries
        if isinstance(e, dict) and nt["commandContains"] in str(e.get("command", ""))
    ]
    if live:
        data["hooks"][nt["hook"]] = []
        atomic_json_write(path, data)
        detail += " (residual live command found; forced empty stop[])"
    return detail


# ----------------------------------------------------------------------------- state machine

def classify_root(cache_root: Path, desc: dict[str, Any]) -> tuple[str, str]:
    counts_ok, cdetail = validate_retarget(cache_root, desc)
    if not counts_ok:
        return STATE_INCOMPATIBLE, f"retarget target unidentifiable: {cdetail}"
    # cadence stop entry must be locatable and unambiguous
    hp = hooks_path(cache_root, desc)
    try:
        data = load_json(hp)
    except Exception as exc:
        return STATE_INCOMPATIBLE, f"hooks.json unparseable: {exc}"
    for target in desc["patchTargets"]:
        n = len(matching_entries(data, target))
        if n != 1:
            return STATE_INCOMPATIBLE, f"cadence '{target['hook']}' entries={n} (expected 1)"
    try:
        fp = behavior_hash(cache_root, desc)
    except Exception as exc:
        return STATE_INCOMPATIBLE, f"fingerprint failed: {exc}"
    prov = meta_field("provenance_ref")
    if prov and fp == prov:
        return STATE_BLESSED, f"fingerprint matches provenance_ref ({fp[:12]})"
    return STATE_CONTAINABLE, f"fingerprint {fp[:12]} != provenance_ref {(prov[:12] if prov else '<empty>')}"


# ----------------------------------------------------------------------------- session-start hook

def ensure_session_start(desc: dict[str, Any], apply: bool) -> tuple[bool, str]:
    path = hooks_json_path()
    data: dict[str, Any] = {"version": 1, "hooks": {}}
    if path.exists():
        data = load_json(path)
    hooks = data.setdefault("hooks", {})
    session = hooks.setdefault("sessionStart", [])
    marker = desc["sessionStart"]["marker"]
    command = f"bash {CAP_DIR / 'install.sh'} --repair --cache-only"
    desired = {
        "command": command,
        "timeout": desc["sessionStart"]["timeout"],
        "failClosed": desc["sessionStart"]["failClosed"],
        "description": marker,
    }
    for entry in session:
        if isinstance(entry, dict) and entry.get("description") == marker:
            if entry == desired:
                return False, "sessionStart reapply hook already present"
            if apply:
                entry.clear()
                entry.update(desired)
                atomic_json_write(path, data)
            return True, "updated sessionStart reapply hook"
    if apply:
        session.append(desired)
        atomic_json_write(path, data)
    return True, "added sessionStart reapply hook" if apply else "would add sessionStart reapply hook"


# ----------------------------------------------------------------------------- global excludes ownership

def _expand_git_path(raw: str) -> Path:
    raw = raw.strip()
    if raw.startswith("~/"):
        raw = str(Path.home()) + raw[1:]
    return Path(raw).expanduser()


def excludes_file_target() -> tuple[Path, bool]:
    """Return (path, needs_git_config_set)."""
    proc = subprocess.run(
        ["git", "config", "--global", "core.excludesFile"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return _expand_git_path(proc.stdout.strip()), False
    return Path.home() / ".gitignore_global", True


def ensure_global_excludes(desc: dict[str, Any], apply: bool) -> tuple[bool, str]:
    path, need_set = excludes_file_target()
    needed = desc.get("globalExcludes", [])
    text = path.read_text() if path.exists() else ""
    present = set(text.splitlines())
    missing = [ln for ln in needed if ln not in present]
    if not apply:
        return (need_set or bool(missing)), f"would ensure {missing or 'nothing'} in {path}"
    if need_set:
        subprocess.run(["git", "config", "--global", "core.excludesFile", str(path)], check=False)
    if missing:
        new_text = text
        if new_text and not new_text.endswith("\n"):
            new_text += "\n"
        new_text += "".join(ln + "\n" for ln in missing)
        atomic_write_text(path, new_text)
    return bool(missing or need_set), f"excludes ensured at {path} (added {len(missing)})"


def check_global_excludes(desc: dict[str, Any]) -> tuple[bool, str]:
    path, need_set = excludes_file_target()
    if need_set or not path.exists():
        return False, f"core.excludesFile unset or missing on disk ({path})"
    present = set(path.read_text(errors="ignore").splitlines())
    missing = [ln for ln in desc.get("globalExcludes", []) if ln not in present]
    if missing:
        return False, f"{path} lacks {missing}"
    return True, f"{path} covers {desc.get('globalExcludes', [])}"


# ----------------------------------------------------------------------------- hook-state .gitignore

_HOOKSTATE_GITIGNORE_CONTENT = "*\n"


def hookstate_dir(workspace_root: Path | None = None) -> Path:
    """Return the workspace-local .cursor/hooks/state directory.

    Priority: explicit ``workspace_root`` argument > env var
    ``CONTINUAL_LEARNING_HOOKSTATE_DIR`` (test override) > ``Path.cwd()``.
    """
    if workspace_root is not None:
        return workspace_root / ".cursor" / "hooks" / "state"
    override = os.environ.get("CONTINUAL_LEARNING_HOOKSTATE_DIR")
    if override:
        return Path(override).expanduser()
    return Path.cwd() / ".cursor" / "hooks" / "state"


def ensure_hookstate_gitignore(workspace_root: Path | None = None) -> tuple[bool, str]:
    """Idempotently write ``*`` to ``.cursor/hooks/state/.gitignore``.

    Creates the state directory if absent.  Only (re)writes the file when it is
    missing or its content is not already ``*\\n``, so a second call is a
    guaranteed no-op.  Returns (changed, message).
    """
    state_dir = hookstate_dir(workspace_root)
    gitignore = state_dir / ".gitignore"
    if gitignore.exists():
        try:
            if gitignore.read_text() == _HOOKSTATE_GITIGNORE_CONTENT:
                return False, f"hookstate .gitignore already correct at {gitignore}"
        except OSError:
            pass  # fall through to (re)write
    state_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(gitignore, _HOOKSTATE_GITIGNORE_CONTENT)
    return True, f"wrote hookstate .gitignore at {gitignore}"


# ----------------------------------------------------------------------------- state marker

def write_state_marker(root_states: list[tuple[Path, str, str]], descriptor_ok: bool, excludes_ok: bool) -> None:
    worst = STATE_BLESSED
    for _root, state, _detail in root_states:
        if _SEVERITY[state] > _SEVERITY[worst]:
            worst = state
    if not root_states:
        worst = STATE_INCOMPATIBLE
    marker = {
        "updated_utc": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "descriptor_ref_ok": descriptor_ok,
        "global_excludes_ok": excludes_ok,
        "worst": worst,
        "roots": [{"root": str(r), "state": s, "detail": d} for r, s, d in root_states],
    }
    d = governor_state_dir()
    d.mkdir(parents=True, exist_ok=True)
    atomic_json_write(d / "state.json", marker)


# ----------------------------------------------------------------------------- bounded lock

@contextmanager
def apply_lock(timeout: float = 5.0):
    d = governor_state_dir()
    d.mkdir(parents=True, exist_ok=True)
    lock_path = d / "apply.lock"
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    got = False
    start = time.time()
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                got = True
                break
            except OSError:
                if time.time() - start > timeout:
                    break
                time.sleep(0.2)
        yield got
    finally:
        if got:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(fd)


# ----------------------------------------------------------------------------- apply / doctor

def run_apply(cache_only: bool = False) -> int:
    desc = load_json(DESCRIPTOR)
    rc = 0
    with apply_lock() as got:
        if not got:
            print("ok   another governor apply holds the lock; skipping (idempotent)")
            return 0

        _exc_changed, exc_msg = ensure_global_excludes(desc, apply=True)
        print(f"ok   {exc_msg}")
        excludes_ok, _ = check_global_excludes(desc)

        _gi_changed, gi_msg = ensure_hookstate_gitignore()
        print(f"ok   {gi_msg}")

        roots = discover_cache_roots(desc)
        root_states: list[tuple[Path, str, str]] = []
        for root in roots:
            state, detail = classify_root(root, desc)
            if state == STATE_INCOMPATIBLE:
                try:
                    d2 = neutralize(root, desc)
                    detail = f"{detail}; neutralized: {d2}"
                except Exception as exc:
                    detail = f"{detail}; NEUTRALIZE ERROR: {exc}"
                print(f"VIOLATION {root}: INCOMPATIBLE — {detail}. Fix: review the new cache, update "
                      f"retargetTargets/counts + meta.provenance_ref in a KleinPerkins/skills PR, or disable the plugin in Cursor.")
                rc = 1
            else:
                try:
                    changed, msg = apply_retarget_all(root, desc)
                    if state == STATE_CONTAINABLE:
                        print(f"WARN {root}: CONTAINABLE — retarget applied ({msg}); REQUIRED re-bless: "
                              f"run `behavior-hash` and update meta.provenance_ref in a PR. {detail}")
                    else:
                        print(f"ok   {root}: BLESSED — {msg}; {detail}")
                except Exception as exc:
                    try:
                        d2 = neutralize(root, desc)
                    except Exception as exc2:
                        d2 = f"NEUTRALIZE ERROR: {exc2}"
                    state = STATE_INCOMPATIBLE
                    detail = f"retarget failed ({exc}); restored writers + neutralized: {d2}"
                    print(f"VIOLATION {root}: {detail}")
                    rc = 1
            root_states.append((root, state, detail))

        if not roots:
            print("FAIL no continual-learning marketplace cache roots found")
            rc = 1

        descriptor_ok = descriptor_hash(DESCRIPTOR) == meta_field("descriptor_ref")
        write_state_marker(root_states, descriptor_ok, excludes_ok)

        if not cache_only:
            _changed, msg = ensure_session_start(desc, apply=True)
            print(f"ok   {msg}")
    return rc


def run_doctor() -> int:
    desc = load_json(DESCRIPTOR)
    rc = 0
    print("== continual-learning plugin doctor ==")

    actual_descriptor = descriptor_hash(DESCRIPTOR)
    expected_descriptor = meta_field("descriptor_ref")
    descriptor_ok = actual_descriptor == expected_descriptor
    if descriptor_ok:
        print("ok   descriptor_ref matches")
    else:
        print(f"FAIL descriptor_ref mismatch actual={actual_descriptor} meta={expected_descriptor or '<empty>'} "
              f"(fix: run `descriptor-hash` and pin meta.descriptor_ref in the same PR)")
        rc = 1

    excludes_ok, exc_msg = check_global_excludes(desc)
    print(("ok   " if excludes_ok else "FAIL ") + exc_msg)
    rc = rc if excludes_ok else 1

    roots = discover_cache_roots(desc)
    if roots:
        print(f"ok   cache roots: {len(roots)}")
    else:
        print("FAIL no cache roots discovered from plugin metadata")
        rc = 1

    root_states: list[tuple[Path, str, str]] = []
    for root in roots:
        state, detail = classify_root(root, desc)
        cad_ok, cad_msg = cadence_ok(root, desc)
        root_states.append((root, state, detail))
        if state == STATE_BLESSED:
            # confirm the writers are actually retargeted (all-`to`, zero-`from`) and cadence set
            fully = True
            for t in desc["retargetTargets"]:
                st = _retarget_file_state(root, t)
                if st is None or st[1] != 0 or st[2] != t["expectedCount"]:
                    fully = False
            if fully and cad_ok:
                print(f"ok   {root}: BLESSED, retarget applied, cadence {cad_msg}")
            else:
                print(f"WARN {root}: BLESSED but projection not yet applied (retarget/cadence pending; run --repair)")
        elif state == STATE_CONTAINABLE:
            print(f"FAIL {root}: CONTAINABLE — behavior fingerprint changed; REQUIRED re-bless: review the new cache, "
                  f"run `behavior-hash`, update meta.provenance_ref in a KleinPerkins/skills PR. {detail}")
            rc = 1
        else:
            print(f"FAIL {root}: INCOMPATIBLE (mining paused via neutralized stop hook) — {detail}. "
                  f"Fix: update retargetTargets/counts + meta.provenance_ref, or disable the plugin in Cursor.")
            rc = 1

    write_state_marker(root_states, descriptor_ok, excludes_ok)
    return rc


# ----------------------------------------------------------------------------- CLI

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    dh = sub.add_parser("descriptor-hash")
    dh.add_argument("--descriptor", type=Path, default=DESCRIPTOR)
    bh = sub.add_parser("behavior-hash")
    bh.add_argument("--cache-root", type=Path)
    sub.add_parser("doctor")
    apply_p = sub.add_parser("apply")
    apply_p.add_argument("--cache-only", action="store_true")
    repair_p = sub.add_parser("repair")
    repair_p.add_argument("--cache-only", action="store_true")
    args = parser.parse_args(argv)

    if args.cmd == "descriptor-hash":
        print(descriptor_hash(args.descriptor))
        return 0
    if args.cmd == "behavior-hash":
        desc = load_json(DESCRIPTOR)
        roots = discover_cache_roots(desc)
        root = args.cache_root or (roots[0] if roots else None)
        if root is None:
            print("no cache root found", file=sys.stderr)
            return 1
        print(behavior_hash(root, desc))
        return 0
    if args.cmd == "doctor":
        return run_doctor()
    if args.cmd == "apply":
        return run_apply(cache_only=args.cache_only)
    if args.cmd == "repair":
        return run_apply(cache_only=args.cache_only)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
