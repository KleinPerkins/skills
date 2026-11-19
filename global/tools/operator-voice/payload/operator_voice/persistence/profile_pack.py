"""Profile-pack publisher + exact-parent Git delivery — build plan v3/v4 §4 "Profile-pack
publisher", §5.1 storage tiers, §8 "profile_publish validates/encrypts and delivers a generation
by exact-parent CAS", and decision D20 ("no mandatory profile PR ceremony ... CAS, no force-push,
encryption, allowlist/plaintext scans, and key recovery provide the safety").

Wire format (matches the `operator-voice-profile` repo's own README, which is the operator-facing
description of this exact contract):

    profile/objects/<sha256[:2]>/<sha256>.enc   -- AEAD ciphertext, content-addressed by the
                                                    SHA-256 of the REDACTED PLAINTEXT payload
    profile/manifest.json                       -- current ``ProfilePackManifest`` (redacted;
                                                    §5.1: "no fact values, aliases, paths, or raw
                                                    titles")
    profile/generations/<generation_id>.json    -- one append-only pointer record per generation

Exact-parent compare-and-swap is implemented by delegating to Git's own fast-forward check: this
module NEVER passes ``--force`` or ``--force-with-lease`` to ``git push``. A plain push only
succeeds when the remote ref has not moved past the commit this publish was based on; any
divergence is refused by Git itself and surfaced as ``SyncStatus.CONFLICT`` — never merged with
last-write-wins (README "Recovery"/"How it is written", build plan §5.1/§8).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Any, Optional

from operator_voice.domain.models import (
    FactState,
    FeedbackEvent,
    ProfileFact,
    ProfileGeneration,
    ProfilePackManifest,
    ProfilePackObjectRef,
    RETRIEVAL_ELIGIBLE_STATES,
    SyncStatus,
)
from operator_voice.persistence.crypto import CryptoContext, aead_decrypt, deterministic_aead_encrypt

PROFILE_PACK_VERSION = "profile-pack/v1"
PROFILE_PACK_PUBLISHER_VERSION = "operator-voice-publisher/v1"

# §5.1: only these fact states are stable/curated enough to leave the machine at all. OBSERVED
# and MODEL_HYPOTHESIS never publish (they are not yet evidence the operator has confirmed or the
# kernel has calibrated as stable), and DEPRECATED is excluded from retrieval entirely already.
PUBLISHABLE_FACT_STATES = RETRIEVAL_ELIGIBLE_STATES


class ProfilePackError(RuntimeError):
    pass


def canonical_json(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True, slots=True)
class PortableObject:
    object_type: str
    digest: str  # sha256 hex of the redacted plaintext payload (content-addressing key)
    plaintext: bytes


def _digest(plaintext: bytes) -> str:
    return hashlib.sha256(plaintext).hexdigest()


def fact_to_portable(fact: ProfileFact) -> PortableObject:
    payload = {
        "object_type": "profile_fact",
        "facet": fact.facet,
        "value": fact.value,
        "scope": fact.scope.as_dict(),
        "state": fact.state.value,
        "confidence": fact.confidence,
        "confidence_interval": list(fact.confidence_interval) if fact.confidence_interval else None,
        "document_count": fact.document_count,
        "source_count": fact.source_count,
        "synthesis_version": fact.synthesis_version,
        "valid_from": fact.valid_from,
    }
    plaintext = canonical_json(payload)
    return PortableObject("profile_fact", _digest(plaintext), plaintext)


def feedback_to_portable(event: FeedbackEvent) -> PortableObject:
    payload = {
        "object_type": "feedback_event",
        "action": event.action.value,
        "reason": event.reason,
        "target_facet": event.target_facet,
        "prior_value": event.prior_value,
        "new_value": event.new_value,
        "utterance_digest": event.utterance_digest,
        "created_at": event.created_at,
    }
    plaintext = canonical_json(payload)
    return PortableObject("feedback_event", _digest(plaintext), plaintext)


def calibration_manifest_to_portable(generation: ProfileGeneration) -> PortableObject:
    payload = {"object_type": "calibration_manifest", **generation.version_bundle()}
    plaintext = canonical_json(payload)
    return PortableObject("calibration_manifest", _digest(plaintext), plaintext)


def select_publishable_facts(facts: list[ProfileFact]) -> list[ProfileFact]:
    return [f for f in facts if f.state in PUBLISHABLE_FACT_STATES]


def build_portable_objects(
    *, facts: list[ProfileFact], feedback_events: list[FeedbackEvent], generation: ProfileGeneration
) -> list[PortableObject]:
    objects = [fact_to_portable(f) for f in select_publishable_facts(facts)]
    objects += [feedback_to_portable(e) for e in feedback_events]
    objects.append(calibration_manifest_to_portable(generation))
    return objects


def build_manifest(
    *,
    generation: ProfileGeneration,
    objects: list[PortableObject],
    key_generation_id: str,
    git_parent_sha: Optional[str] = None,
) -> ProfilePackManifest:
    counts: dict[str, int] = {}
    for obj in objects:
        counts[obj.object_type] = counts.get(obj.object_type, 0) + 1
    return ProfilePackManifest(
        generation_id=generation.generation_id,
        parent_generation_id=generation.parent_generation_id,
        object_refs=[ProfilePackObjectRef(digest=o.digest, object_type=o.object_type) for o in objects],
        redacted_counts=counts,
        key_generation_id=key_generation_id,
        publisher_version=PROFILE_PACK_PUBLISHER_VERSION,
        git_parent_sha=git_parent_sha,
    )


def manifest_to_dict(manifest: ProfilePackManifest) -> dict[str, Any]:
    return {
        "schema": manifest.schema,
        "generation_id": manifest.generation_id,
        "parent_generation_id": manifest.parent_generation_id,
        "object_refs": [{"digest": r.digest, "object_type": r.object_type} for r in manifest.object_refs],
        "redacted_counts": manifest.redacted_counts,
        "key_generation_id": manifest.key_generation_id,
        "publisher_version": manifest.publisher_version,
        "git_parent_sha": manifest.git_parent_sha,
        "created_at": manifest.created_at,
    }


def encrypt_objects(crypto: CryptoContext, dek: bytes, objects: list[PortableObject]) -> dict[str, bytes]:
    """Returns {digest: ciphertext_blob}. Uses the deterministic AEAD variant so republishing
    unchanged content yields byte-identical ciphertext (real CAS dedup, §4.4/§5.1)."""
    return {
        obj.digest: deterministic_aead_encrypt(dek, obj.plaintext, aad=obj.object_type.encode())
        for obj in objects
    }


def decrypt_object(dek: bytes, ciphertext: bytes, object_type: str) -> dict[str, Any]:
    plaintext = aead_decrypt(dek, ciphertext, aad=object_type.encode())
    return json.loads(plaintext)


# --------------------------------------------------------------------------------------
# Git delivery (exact-parent CAS, no force push — build plan §5.1/§8, decision D20)
# --------------------------------------------------------------------------------------


def _run_git(repo_path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo_path), *args], capture_output=True, text=True
    )


def ensure_clone(repo_path: Path, remote_url: str) -> None:
    if (repo_path / ".git").exists():
        fetch = _run_git(repo_path, "fetch", "origin")
        if fetch.returncode != 0:
            raise ProfilePackError(f"profile repo fetch failed: {fetch.stderr.strip()}")
        return
    repo_path.parent.mkdir(parents=True, exist_ok=True)
    clone = subprocess.run(
        ["git", "clone", remote_url, str(repo_path)], capture_output=True, text=True
    )
    if clone.returncode != 0:
        raise ProfilePackError(f"profile repo clone failed: {clone.stderr.strip()}")


def current_remote_head(repo_path: Path, branch: str = "main") -> Optional[str]:
    result = _run_git(repo_path, "rev-parse", f"origin/{branch}")
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def read_manifest(repo_path: Path) -> Optional[dict[str, Any]]:
    manifest_path = repo_path / "profile" / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        payload = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as exc:
        raise ProfilePackError(f"profile manifest is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict) or not payload.get("generation_id"):
        raise ProfilePackError("profile manifest missing generation_id")
    return payload


def local_advances_remote(
    *,
    local_generation_id: str,
    remote_generation_id: str,
    parent_of: Callable[[str], Optional[str]],
) -> bool:
    """Return True when ``local_generation_id`` may replace the remote manifest generation.

    Idempotent republish (same id) and any local generation whose parent chain reaches the remote
    generation are allowed. A stale or divergent local generation is refused so ``sync_clone_to_remote``
    cannot turn a previously non-fast-forward Git refusal into a last-write-wins profile regression."""
    if local_generation_id == remote_generation_id:
        return True
    cursor = local_generation_id
    seen: set[str] = set()
    while cursor and cursor not in seen:
        parent = parent_of(cursor)
        if parent is None:
            return False
        if parent == remote_generation_id:
            return True
        seen.add(cursor)
        cursor = parent
    return False


def sync_clone_to_remote(repo_path: Path, *, branch: str = "main") -> None:
    """Align the local clone with ``origin/{branch}`` after fetch.

    The profile-pack clone is a disposable staging checkout — canonical profile state lives in the
    local encrypted store, not in unpushed clone commits. When governance or other non-profile
    commits land on the remote default branch, a stale or diverged local ``main`` would otherwise
    produce a non-fast-forward push refusal even though ``expected_parent_sha`` still matches
    ``origin/{branch}``. Resetting discards only restaged, unpushed publish attempts; exact-parent
    CAS at push time is unchanged."""
    remote_head = current_remote_head(repo_path, branch)
    if remote_head is None:
        return
    local_head = _run_git(repo_path, "rev-parse", "HEAD")
    if local_head.returncode != 0:
        raise ProfilePackError(f"profile repo HEAD unreadable: {local_head.stderr.strip()}")
    if local_head.stdout.strip() == remote_head:
        return
    checkout = _run_git(repo_path, "checkout", branch)
    if checkout.returncode != 0:
        raise ProfilePackError(f"profile repo checkout {branch} failed: {checkout.stderr.strip()}")
    reset = _run_git(repo_path, "reset", "--hard", f"origin/{branch}")
    if reset.returncode != 0:
        raise ProfilePackError(f"profile repo reset to origin/{branch} failed: {reset.stderr.strip()}")


def write_pack(
    *,
    repo_path: Path,
    encrypted_objects: dict[str, bytes],
    manifest: ProfilePackManifest,
    object_types: dict[str, str],
) -> list[str]:
    """Writes objects/manifest/generation-pointer into the working tree. Never overwrites an
    existing object (immutable by content-address); returns the list of NEWLY written digests."""
    objects_dir = repo_path / "profile" / "objects"
    generations_dir = repo_path / "profile" / "generations"
    objects_dir.mkdir(parents=True, exist_ok=True)
    generations_dir.mkdir(parents=True, exist_ok=True)

    newly_written: list[str] = []
    for digest, ciphertext in encrypted_objects.items():
        shard = objects_dir / digest[:2]
        shard.mkdir(exist_ok=True)
        dest = shard / f"{digest}.enc"
        if dest.exists():
            continue  # same digest = no-op (idempotent CAS write)
        dest.write_bytes(ciphertext)
        newly_written.append(digest)

    (repo_path / "profile" / "manifest.json").write_text(
        json.dumps(manifest_to_dict(manifest), indent=2, sort_keys=True) + "\n"
    )
    (generations_dir / f"{manifest.generation_id}.json").write_text(
        json.dumps(
            {
                "generation_id": manifest.generation_id,
                "parent_generation_id": manifest.parent_generation_id,
                "publisher_version": manifest.publisher_version,
                "created_at": manifest.created_at,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return newly_written


@dataclass(frozen=True, slots=True)
class PublishOutcome:
    status: SyncStatus
    pushed_sha: Optional[str]
    detail: str
    pr_url: Optional[str] = None
    pr_number: Optional[int] = None


_NON_FAST_FORWARD_MARKERS = ("[rejected]", "non-fast-forward", "fetch first", "stale info")
_PR_RULE_MARKERS = ("gh013", "pull request", "repository rule violations")
_DEFAULT_PR_WAIT_SECONDS = 600
_PR_POLL_INTERVAL_SECONDS = 15


def _push_requires_pull_request(combined_output: str) -> bool:
    lowered = combined_output.lower()
    return any(marker in lowered for marker in _PR_RULE_MARKERS)


def _origin_remote_url(repo_path: Path) -> str:
    result = _run_git(repo_path, "remote", "get-url", "origin")
    if result.returncode != 0:
        raise ProfilePackError(f"profile repo origin URL unreadable: {result.stderr.strip()}")
    return result.stdout.strip()


def _github_repo_slug(remote_url: str) -> str:
    scp = re.match(r"^git@github\.com:(?P<slug>[^/]+/[^/.]+)(?:\.git)?$", remote_url)
    if scp:
        return scp.group("slug")
    https = re.match(r"^https://github\.com/(?P<slug>[^/]+/[^/.]+)(?:\.git)?/?$", remote_url)
    if https:
        return https.group("slug")
    raise ProfilePackError(f"profile remote is not a GitHub repository URL: {remote_url}")


def _run_gh(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def _pr_wait_seconds(override: Optional[int]) -> int:
    if override is not None:
        return max(0, override)
    raw = os.environ.get("OVT_PROFILE_PR_WAIT_SECONDS", str(_DEFAULT_PR_WAIT_SECONDS))
    try:
        return max(0, int(raw))
    except ValueError:
        return _DEFAULT_PR_WAIT_SECONDS


def _wait_for_pr_merge(
    repo_slug: str,
    pr_number: int,
    *,
    timeout_seconds: int,
    cancel_check: Optional[Callable[[], None]] = None,
) -> bool:
    if timeout_seconds <= 0:
        return False
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if cancel_check is not None:
            cancel_check()
        view = _run_gh(
            "pr", "view", str(pr_number), "--repo", repo_slug, "--json", "state,mergedAt",
        )
        if view.returncode != 0:
            raise ProfilePackError(f"gh pr view failed: {view.stderr.strip()}")
        payload = json.loads(view.stdout)
        state = payload.get("state")
        if state == "MERGED":
            return True
        if state == "CLOSED":
            raise ProfilePackError(f"profile publish PR #{pr_number} closed without merge")
        time.sleep(_PR_POLL_INTERVAL_SECONDS)
    return False


def _published_outcome_if_remote_has_generation(
    repo_path: Path,
    *,
    generation_id: str,
    branch: str = "main",
    detail: str,
    pr_url: Optional[str] = None,
    pr_number: Optional[int] = None,
) -> Optional[PublishOutcome]:
    sync_clone_to_remote(repo_path, branch=branch)
    merged_manifest = read_manifest(repo_path)
    if merged_manifest is None or merged_manifest.get("generation_id") != generation_id:
        return None
    merged_sha = current_remote_head(repo_path, branch)
    if merged_sha is None:
        raise ProfilePackError("profile repo remote head unreadable after PR merge")
    return PublishOutcome(
        status=SyncStatus.PUBLISHED,
        pushed_sha=merged_sha,
        detail=detail,
        pr_url=pr_url,
        pr_number=pr_number,
    )


def try_finalize_pending_publication(
    repo_path: Path,
    *,
    generation_id: str,
    branch: str = "main",
    pr_wait_seconds: Optional[int] = None,
    cancel_check: Optional[Callable[[], None]] = None,
) -> Optional[PublishOutcome]:
    """When a prior publish opened a PR but timed out, resume by polling that PR (or recognizing
    an already-merged remote head) without creating a new commit."""
    fetch = _run_git(repo_path, "fetch", "origin")
    if fetch.returncode != 0:
        raise ProfilePackError(f"profile repo fetch failed: {fetch.stderr.strip()}")
    sync_clone_to_remote(repo_path, branch=branch)

    try:
        remote_manifest = read_manifest(repo_path)
    except ProfilePackError:
        remote_manifest = None
    if remote_manifest is not None and remote_manifest.get("generation_id") == generation_id:
        return _published_outcome_if_remote_has_generation(
            repo_path,
            generation_id=generation_id,
            branch=branch,
            detail="remote already carries requested generation",
        )

    publish_branch = f"publish/{generation_id}"
    branch_ref = _run_git(repo_path, "ls-remote", "--heads", "origin", publish_branch)
    if branch_ref.returncode != 0 or not branch_ref.stdout.strip():
        return None

    remote_url = _origin_remote_url(repo_path)
    repo_slug = _github_repo_slug(remote_url)

    existing = _run_gh(
        "pr", "list", "--repo", repo_slug, "--head", publish_branch, "--json", "number,url,state", "--state", "all",
    )
    if existing.returncode != 0:
        raise ProfilePackError(f"gh pr list failed: {existing.stderr.strip()}")
    prs = json.loads(existing.stdout or "[]")
    open_prs = [p for p in prs if p.get("state") == "OPEN"]
    merged_prs = [p for p in prs if p.get("state") == "MERGED"]

    if merged_prs and not open_prs:
        pr = merged_prs[-1]
        published = _published_outcome_if_remote_has_generation(
            repo_path,
            generation_id=generation_id,
            branch=branch,
            detail=f"published via PR #{pr['number']} (already merged)",
            pr_url=pr.get("url"),
            pr_number=int(pr["number"]),
        )
        if published is not None:
            return published
        return None

    if not open_prs:
        return None

    pr_number = int(open_prs[0]["number"])
    pr_url = open_prs[0]["url"]
    timeout = _pr_wait_seconds(pr_wait_seconds)
    if not _wait_for_pr_merge(
        repo_slug, pr_number, timeout_seconds=timeout, cancel_check=cancel_check,
    ):
        return PublishOutcome(
            status=SyncStatus.PENDING_PUBLICATION,
            pushed_sha=None,
            detail=f"PR #{pr_number} still open; merge not complete within {timeout}s",
            pr_url=pr_url,
            pr_number=pr_number,
        )

    fetch = _run_git(repo_path, "fetch", "origin")
    if fetch.returncode != 0:
        raise ProfilePackError(f"profile repo fetch after PR merge failed: {fetch.stderr.strip()}")
    published = _published_outcome_if_remote_has_generation(
        repo_path,
        generation_id=generation_id,
        branch=branch,
        detail=f"published via PR #{pr_number}",
        pr_url=pr_url,
        pr_number=pr_number,
    )
    if published is None:
        raise ProfilePackError(
            f"PR #{pr_number} merged but remote manifest does not carry generation {generation_id}"
        )
    return published


def deliver_via_pull_request(
    repo_path: Path,
    *,
    generation_id: str,
    branch: str = "main",
    commit_message: str,
    pr_wait_seconds: Optional[int] = None,
    cancel_check: Optional[Callable[[], None]] = None,
) -> PublishOutcome:
    """When the profile remote requires PRs (fleet merge-safety ruleset), push a publish branch,
    open a PR, wait for the governed reviewer App to squash-merge, then realign the clone to
    ``origin/{branch}``. Never calls ``gh pr merge`` — merge is exclusively the reviewer App's job."""
    remote_url = _origin_remote_url(repo_path)
    repo_slug = _github_repo_slug(remote_url)
    publish_branch = f"publish/{generation_id}"
    commit_sha = _run_git(repo_path, "rev-parse", "HEAD").stdout.strip()

    checkout = _run_git(repo_path, "checkout", "-B", publish_branch, commit_sha)
    if checkout.returncode != 0:
        raise ProfilePackError(f"publish branch checkout failed: {checkout.stderr.strip()}")

    push = _run_git(repo_path, "push", "-u", "origin", publish_branch)
    if push.returncode != 0:
        combined = push.stdout + push.stderr
        if any(marker in combined.lower() for marker in _NON_FAST_FORWARD_MARKERS):
            # The publish branch is disposable staging — updating it after a timed-out PR attempt
            # must not block a later republish, and must never force-write ``main``.
            push = _run_git(repo_path, "push", "--force-with-lease", "-u", "origin", publish_branch)
        if push.returncode != 0:
            raise ProfilePackError(f"publish branch push failed: {push.stderr.strip()}")

    existing = _run_gh(
        "pr", "list", "--repo", repo_slug, "--head", publish_branch, "--json", "number,url", "--state", "open",
    )
    if existing.returncode != 0:
        raise ProfilePackError(f"gh pr list failed: {existing.stderr.strip()}")
    open_prs = json.loads(existing.stdout or "[]")
    if open_prs:
        pr_number = int(open_prs[0]["number"])
        pr_url = open_prs[0]["url"]
    else:
        create = _run_gh(
            "pr", "create",
            "--repo", repo_slug,
            "--head", publish_branch,
            "--base", branch,
            "--title", commit_message,
            "--body", (
                "## Summary\n"
                f"- Publish operator voice profile generation `{generation_id}`.\n"
                "- Exact-parent CAS preserved; encrypted profile objects only.\n\n"
                "## Test plan\n"
                "- [ ] `pr-automation / verify` passes\n"
                "- [ ] Reviewer App arms squash auto-merge\n"
                "- [ ] After merge: `operator-voice profile-sync_status` reports `PUBLISHED`\n"
            ),
        )
        if create.returncode != 0:
            raise ProfilePackError(f"gh pr create failed: {create.stderr.strip()}")
        pr_url = create.stdout.strip()
        pr_number = int(pr_url.rstrip("/").split("/")[-1])

    timeout = _pr_wait_seconds(pr_wait_seconds)
    if not _wait_for_pr_merge(
        repo_slug, pr_number, timeout_seconds=timeout, cancel_check=cancel_check,
    ):
        _run_git(repo_path, "checkout", branch)
        return PublishOutcome(
            status=SyncStatus.PENDING_PUBLICATION,
            pushed_sha=None,
            detail=f"PR #{pr_number} opened; merge not complete within {timeout}s",
            pr_url=pr_url,
            pr_number=pr_number,
        )

    fetch = _run_git(repo_path, "fetch", "origin")
    if fetch.returncode != 0:
        raise ProfilePackError(f"profile repo fetch after PR merge failed: {fetch.stderr.strip()}")
    published = _published_outcome_if_remote_has_generation(
        repo_path,
        generation_id=generation_id,
        branch=branch,
        detail=f"published via PR #{pr_number}",
        pr_url=pr_url,
        pr_number=pr_number,
    )
    if published is None:
        raise ProfilePackError(
            f"PR #{pr_number} merged but remote manifest does not carry generation {generation_id}"
        )
    return published


def commit_and_push(
    repo_path: Path,
    *,
    branch: str = "main",
    commit_message: str,
    expected_parent_sha: Optional[str],
    generation_id: Optional[str] = None,
    pr_wait_seconds: Optional[int] = None,
    cancel_check: Optional[Callable[[], None]] = None,
) -> PublishOutcome:
    """Commits the working tree and pushes with a PLAIN push (no --force / --force-with-lease).
    A non-fast-forward rejection means the remote moved since ``expected_parent_sha`` was read —
    exactly the "exact-parent compare-and-swap" the profile repo README/build plan require. This
    function never retries with a merge or rebase; a conflict is reported, not resolved, per
    D18/§8 ("divergent writers refuse safely")."""
    current_head = _run_git(repo_path, "rev-parse", f"origin/{branch}")
    live_parent = current_head.stdout.strip() if current_head.returncode == 0 else None
    if expected_parent_sha is not None and live_parent is not None and live_parent != expected_parent_sha:
        return PublishOutcome(
            status=SyncStatus.CONFLICT,
            pushed_sha=None,
            detail=(
                f"remote {branch} moved from expected parent {expected_parent_sha[:12]} to "
                f"{live_parent[:12]} before publish; refusing to publish over a divergent head"
            ),
        )

    add = _run_git(repo_path, "add", "-A", "profile")
    if add.returncode != 0:
        raise ProfilePackError(f"git add failed: {add.stderr.strip()}")

    diff_check = _run_git(repo_path, "diff", "--cached", "--quiet")
    if diff_check.returncode == 0:
        head_sha = _run_git(repo_path, "rev-parse", "HEAD").stdout.strip()
        return PublishOutcome(status=SyncStatus.PUBLISHED, pushed_sha=head_sha, detail="no content changes; nothing to publish")

    commit = _run_git(repo_path, "commit", "-m", commit_message)
    if commit.returncode != 0:
        raise ProfilePackError(f"git commit failed: {commit.stderr.strip()}")

    push = _run_git(repo_path, "push", "origin", f"HEAD:{branch}")
    if push.returncode != 0:
        combined = push.stdout + push.stderr
        if _push_requires_pull_request(combined):
            if generation_id is None:
                raise ProfilePackError(
                    "profile remote requires a pull request; generation_id is required for PR delivery"
                )
            return deliver_via_pull_request(
                repo_path,
                generation_id=generation_id,
                branch=branch,
                commit_message=commit_message,
                pr_wait_seconds=pr_wait_seconds,
                cancel_check=cancel_check,
            )
        lowered = combined.lower()
        if any(marker in lowered for marker in _NON_FAST_FORWARD_MARKERS):
            return PublishOutcome(
                status=SyncStatus.CONFLICT,
                pushed_sha=None,
                detail=f"push refused (non-fast-forward): {push.stderr.strip()}",
            )
        raise ProfilePackError(f"git push failed: {push.stderr.strip()}")

    pushed_sha = _run_git(repo_path, "rev-parse", "HEAD").stdout.strip()
    return PublishOutcome(status=SyncStatus.PUBLISHED, pushed_sha=pushed_sha, detail="published")
