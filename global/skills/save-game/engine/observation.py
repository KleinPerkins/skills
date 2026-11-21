"""Read-only resume evidence. The regular Reconcile route still owns recovery."""

from __future__ import annotations

from . import canonical, identity as identity_mod, index, lifecycle, schemas, transaction
from .lock import LockTimeoutError, observe_workstream_lock
from .schemas_validate import SchemaValidationError


def validate_observation(value: dict) -> None:
    """Validate the closed shape and the observation's status/pointer invariant.

    The shared stdlib validator checks the engine's structural schema subset.
    Enforce this schema's additional draft-07 conditional here as well.
    """
    schemas.validate_as(value, "reconcile-observation.v1")
    if (value["status"] == "MATCH") != ("checkpoint" in value):
        raise SchemaValidationError(["checkpoint is required exactly for MATCH"])


def observe_reconcile(repo_key: str, clone_key: str, workstream_key: str, *,
                      task_id: str, identity: identity_mod.RootIdentity) -> dict:
    def result(status: str, *, checkpoint: dict | None = None) -> dict:
        value = {
            "schema": "save-game-reconcile-observation/v1",
            "status": status,
            "repo_key": repo_key,
            "clone_key": clone_key,
            "workstream_key": workstream_key,
        }
        if checkpoint is not None:
            value["checkpoint"] = {
                "id": checkpoint["checkpoint_id"],
                "digest": "sha256:" + canonical.sha256_hex(canonical.canonical_bytes(checkpoint)),
                "generation": checkpoint["active_state_generation"],
            }
        validate_observation(value)
        return value

    try:
        registration = lifecycle.read_registration(repo_key, clone_key)
        if registration is None:
            return result("UNADOPTED")
        if (registration["repo_key"], registration["clone_key"]) != (repo_key, clone_key):
            return result("IDENTITY_MISMATCH")
        if not registration["enabled"]:
            return result("ADOPTION_DISABLED")
        if identity.ref_kind not in {"branch", "detached"} or not identity.observed_head:
            return result("WORKSTREAM_UNAVAILABLE")
        if identity.operation_marker != "none":
            return result("GIT_CONFLICT")

        with observe_workstream_lock(workstream_key):
            try:
                checkpoint, ambiguous = index.resolve_checkpoint(
                    repo_key, clone_key, workstream_key, adopted_since=registration["updated_at"],
                )
            except FileNotFoundError:
                return result("INVALID_EVIDENCE")
            if ambiguous:
                return result("CHECKPOINT_AMBIGUOUS")
            current = transaction.read_current(repo_key, clone_key, workstream_key)
            if current is None or checkpoint is None:
                return result("WORKSTREAM_UNAVAILABLE")
            if (current["task_id"], current["workstream_key"]) != (task_id, workstream_key):
                return result("IDENTITY_MISMATCH")
            if current["current_digest"] != canonical.digest_active_state(current):
                return result("INVALID_EVIDENCE")

            fresh_identity = identity_mod.resolve_root_identity(identity.physical_root)
            conflicts = identity_mod._run_git(identity.physical_root, "--no-optional-locks", "ls-files", "--unmerged")
            if fresh_identity.operation_marker != "none" or conflicts:
                return result("GIT_CONFLICT")
            if conflicts is None:
                return result("WORKSTREAM_UNAVAILABLE")
            if (fresh_identity != identity or current["root"] != identity_mod.root_snapshot_dict(fresh_identity)
                    or lifecycle.read_registration(repo_key, clone_key) != registration
                    or identity_mod.resolve_root_identity(identity.physical_root) != fresh_identity):
                return result("LIVE_STATE_CHANGED")
            if (current["generation"] != checkpoint["active_state_generation"]
                    or current["current_digest"] != checkpoint["active_state_digest"]):
                return result("CHECKPOINT_STALE")
            return result("MATCH", checkpoint=checkpoint)
    except LockTimeoutError:
        return result("LOCK_BUSY")
    except index.IncompleteJournalError:
        return result("INCOMPLETE_TRANSACTION")
    except index.UnadoptedCheckpointError:
        return result("CHECKPOINT_UNADOPTED")
    except FileNotFoundError:
        return result("WORKSTREAM_UNAVAILABLE")
    except (OSError, ValueError, SchemaValidationError, transaction.CurrentStateCorruptError):
        return result("INVALID_EVIDENCE")
