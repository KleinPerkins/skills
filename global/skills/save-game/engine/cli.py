"""Generic, client-agnostic CLI surface (plan: "Cross-client discovery and
invocation") — dispatches `save-game`'s full verb set: the Phase-2 four core
contracts (flush|index|compact-check|reconcile), Phase-3c lifecycle/curation
verbs (adopt|retention-status|gc|archive|remove|uninstall|promotion-candidates),
and a status/doctor path surfacing Phase-3a behavior outputs (next-actions,
stopping) plus Phase-3b's engine doctor.

Per-client adapters (Cursor/Claude/Codex discovery paths, hook wiring, printing
the exact manual compaction command, deriving a real task_id from session
context) are Phase 3b's domain. This CLI is the generic engine surface every
adapter calls into, and is also directly usable for manual/smoke-test
invocation via `scripts/save-game.sh`. Every subcommand only calls existing
engine functions (`flush`/`index`/`compact_decision`/`reconcile`/`lifecycle`/
`curation`/`behavior`/`doctor`) — this module is integration wiring, never a
second place engine rules get decided.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from . import behavior
from . import compact_decision as cd
from . import curation
from . import doctor as doctor_mod
from . import flush as flush_mod
from . import identity as identity_mod
from . import index as index_mod
from . import lifecycle
from . import observation
from . import reconcile as reconcile_mod
from . import transaction

# No adapter/session layer exists yet to supply a real per-session task_id
# (Phase 3b's domain) — "default" is a stable, documented placeholder so bare
# CLI invocations against the same root/branch converge on one workstream
# instead of inventing a fresh random one every call.
_DEFAULT_TASK_ID = "default"

_CLIENT_ID_CHOICES = ["cursor", "claude", "codex", "unknown"]


def _resolve_keys(task_id: str, root: str):
    identity = identity_mod.resolve_root_identity(root)
    repo_key = identity_mod.repo_key_for(identity)
    clone_key = identity_mod.clone_key_for(identity)
    workstream_key = identity_mod.workstream_key_for(repo_key, clone_key, task_id, identity)
    return identity, repo_key, clone_key, workstream_key


def _resolve_clone_keys(root: str):
    """Repo/clone-scoped identity only, for the verbs that operate below the
    workstream level (`adopt`, `uninstall`) — see plan "Adoption" and
    "Retention, archive, GC, rollback, and removal" (uninstall is "unlinks
    only owned client links" at the clone level, never one workstream)."""
    identity = identity_mod.resolve_root_identity(root)
    repo_key = identity_mod.repo_key_for(identity)
    clone_key = identity_mod.clone_key_for(identity)
    return identity, repo_key, clone_key


def _print(doc: dict) -> None:
    # `default=str` is a CLI-boundary concern, not an engine-contract change:
    # `lifecycle.retention_status`'s temp-file/snapshot report items carry real
    # `Path` objects (a deliberate choice for its direct Python callers, e.g.
    # `test_lifecycle.py`'s own `Path` equality assertions) that `json.dumps`
    # cannot serialize natively. Converting at the print boundary here, rather
    # than changing `lifecycle.py`'s return contract, is exactly the smallest
    # fix that closes this integration gap without touching already-tested
    # engine behavior — found by wiring lifecycle into a JSON-emitting CLI for
    # the first time (see EVIDENCE.md's Phase 4 note).
    print(json.dumps(doc, indent=2, sort_keys=True, default=str))


def _confirm_digest_required(verb: str) -> dict:
    return {
        "status": "CONFIRM_DIGEST_REQUIRED",
        "hint": f"run `save-game {verb}` without --execute first, then pass its preview_digest back via --confirm-digest",
    }


# Fields `begin_transaction` (and the privacy gate it calls) computes/fills in
# itself — a candidate builder must never pass these through, per the
# `build_candidate_fn` contract ("SEMANTIC fields only"). Stripping them here
# defends against exactly the bug a naive `dict(current_doc)` copy would
# otherwise reintroduce: stale volatile metadata leaking back in as if it were
# new semantic content (e.g. corrupting NO_DURABLE_DELTA detection).
_VOLATILE_FIELDS = ("generation", "current_digest", "previous_digest", "created_at", "updated_at", "privacy")

_STATUS_CHOICES = ("active", "terminal", "archived")


def _default_candidate_builder(
    task_id: str,
    workstream_key: str,
    identity: identity_mod.RootIdentity,
    objective: Optional[str],
    next_action: Optional[str],
    status: Optional[str] = None,
):
    """Minimal candidate builder for bare CLI use. A real client adapter
    (Phase 3b) inspects live state itself per the Flush algorithm's steps 1-4
    (classify durable/ephemeral/derivable, apply scope/marginal-scope rules);
    this default just carries the caller's literal `--objective`/`--next-action`/
    `--status` strings through, preserving whatever else was already saved.
    `--status` is the only CLI-reachable path to `terminal` (a precondition
    `lifecycle.archive_workstream` requires) — without it, `archive` would be
    unreachable through the CLI alone."""

    def build(current_doc: Optional[dict]) -> dict:
        if current_doc is not None:
            doc = {k: v for k, v in current_doc.items() if k not in _VOLATILE_FIELDS}
        else:
            doc = {
                "schema": "save-game-current/v1",
                "task_id": task_id,
                "workstream_key": workstream_key,
                "root": identity_mod.root_snapshot_dict(identity),
                "scope": {"in_scope": [], "non_scope": [], "deferred": []},
                "hygiene": {
                    "transactions_finalized": True,
                    "temp_artifacts_clear": True,
                    "repo_status_observed": True,
                    "required_checks_run": True,
                    "unclassified_delta": False,
                },
                "blockers": [],
                "marginal_scope_budget": {"consumed_minutes": 0, "estimate_source": "agent_estimated"},
                "status": "active",
            }
        doc["root"] = identity_mod.root_snapshot_dict(identity)
        if objective:
            doc["objective"] = objective[:200]
        elif "objective" not in doc:
            doc["objective"] = "(no objective recorded yet)"
        if next_action:
            doc["next_actions"] = [{"description": next_action[:150]}]
        elif "next_actions" not in doc:
            doc["next_actions"] = []
        if status:
            doc["status"] = status
        return doc

    return build


def cmd_flush(args: argparse.Namespace) -> int:
    task_id = args.task_id or _DEFAULT_TASK_ID
    identity, repo_key, clone_key, workstream_key = _resolve_keys(task_id, args.root)
    build_fn = _default_candidate_builder(task_id, workstream_key, identity, args.objective, args.next_action, args.status)

    compact_inputs = None
    if args.pressure_percent is not None:
        compact_inputs = cd.CompactDecisionInputs(
            pressure_source="client_metric", pressure_percent=args.pressure_percent,
            continuation_count=args.continuation_count, client_id=args.client_id,
        )

    receipt = flush_mod.run_flush(
        repo_key, clone_key, workstream_key,
        identity=identity, build_candidate_fn=build_fn, client_id=args.client_id,
        expected_current_digest=args.expected_digest, compact_inputs=compact_inputs,
        authority_conflict=args.authority_conflict,
    )
    _print(receipt)
    return 0 if receipt["status"] in ("SAVED", "SAVED_PRIVATE_UNADOPTED", "NO_DURABLE_DELTA") else 1


def cmd_index(args: argparse.Namespace) -> int:
    """Read-only resolution of "which checkpoint is current" — actual
    checkpoint CREATION only ever happens inside a Flush transaction (plan
    step 7 runs Index under the same workstream lock); there is no standalone
    "create a checkpoint right now" CLI action."""
    task_id = args.task_id or _DEFAULT_TASK_ID
    _identity, repo_key, clone_key, workstream_key = _resolve_keys(task_id, args.root)
    checkpoint, ambiguous = index_mod.resolve_checkpoint(repo_key, clone_key, workstream_key)
    if ambiguous:
        _print({"status": "CHECKPOINT_AMBIGUOUS", "example": checkpoint})
        return 1
    if checkpoint is None:
        _print({"status": "NO_CHECKPOINT"})
        return 1
    _print(checkpoint)
    return 0


def cmd_compact_check(args: argparse.Namespace) -> int:
    inputs = cd.CompactDecisionInputs(
        operator_request=args.operator_request,
        pressure_source=args.pressure_source,
        pressure_percent=args.pressure_percent,
        continuation_count=args.continuation_count,
        task_completed_or_topic_change=args.task_completed,
        explicit_cross_session_continuation=args.cross_session_continuation,
        client_id=args.client_id,
    )
    result = cd.evaluate(inputs)
    _print({
        "status": result.status,
        "pressure_source": result.pressure_source,
        "pressure_percent": result.pressure_percent,
        "reason": result.reason,
        "client_id": result.client_id,
        "manual_compaction_command": result.manual_compaction_command,
        "pre_compaction_capability": result.pre_compaction_capability,
        "client_capability_known": result.client_capability_known,
    })
    return 0


def cmd_reconcile(args: argparse.Namespace) -> int:
    task_id = args.task_id or _DEFAULT_TASK_ID
    identity, repo_key, clone_key, workstream_key = _resolve_keys(task_id, args.root)
    if args.observe:
        result = observation.observe_reconcile(repo_key, clone_key, workstream_key, task_id=task_id, identity=identity)
        _print(result)
        return 0 if result["status"] == "MATCH" else 1
    triggers = args.trigger or ["resume"]
    receipt = reconcile_mod.run_reconcile(repo_key, clone_key, workstream_key, identity=identity, triggers=triggers)
    _print(receipt)
    return 0


# ---------------------------------------------------------------------------
# Lifecycle verbs (plan: "Adoption"; "Retention, archive, GC, rollback, and
# removal"). Every command below reuses an existing `lifecycle.py` function —
# this is wiring, not new engine logic.
# ---------------------------------------------------------------------------


def cmd_adopt(args: argparse.Namespace) -> int:
    _identity, repo_key, clone_key = _resolve_clone_keys(args.root)
    if args.preview:
        _print(lifecycle.adoption_status(repo_key, clone_key))
        return 0
    doc = lifecycle.adopt(repo_key, clone_key, notes=args.note, enabled=not args.disable)
    _print(doc)
    return 0


def cmd_retention_status(args: argparse.Namespace) -> int:
    task_id = args.task_id or _DEFAULT_TASK_ID
    _identity, repo_key, clone_key, workstream_key = _resolve_keys(task_id, args.root)
    _print(lifecycle.retention_status(repo_key, clone_key, workstream_key))
    return 0


def cmd_gc(args: argparse.Namespace) -> int:
    task_id = args.task_id or _DEFAULT_TASK_ID
    _identity, repo_key, clone_key, workstream_key = _resolve_keys(task_id, args.root)
    _print(lifecycle.gc_run(repo_key, clone_key, workstream_key))
    return 0


def cmd_archive(args: argparse.Namespace) -> int:
    task_id = args.task_id or _DEFAULT_TASK_ID
    _identity, repo_key, clone_key, workstream_key = _resolve_keys(task_id, args.root)
    result = lifecycle.archive_workstream(repo_key, clone_key, workstream_key)
    _print(result)
    return 0 if result["status"] == "ARCHIVED" else 1


def cmd_remove(args: argparse.Namespace) -> int:
    task_id = args.task_id or _DEFAULT_TASK_ID
    _identity, repo_key, clone_key, workstream_key = _resolve_keys(task_id, args.root)
    if not args.execute:
        _print(lifecycle.remove_preview(repo_key, clone_key, workstream_key))
        return 0
    if not args.confirm_digest:
        _print(_confirm_digest_required("remove"))
        return 2
    result = lifecycle.remove_execute(repo_key, clone_key, workstream_key, confirm_preview_digest=args.confirm_digest)
    _print(result)
    return 0 if result["status"] == "REMOVED" else 1


def cmd_uninstall(args: argparse.Namespace) -> int:
    _identity, repo_key, clone_key = _resolve_clone_keys(args.root)
    workstream_keys = args.workstream_key or None
    if not args.execute:
        _print(lifecycle.uninstall_preview(repo_key, clone_key, workstream_keys=workstream_keys))
        return 0
    if not args.confirm_digest:
        _print(_confirm_digest_required("uninstall"))
        return 2
    result = lifecycle.uninstall_execute(
        repo_key, clone_key, confirm_preview_digest=args.confirm_digest, workstream_keys=workstream_keys,
    )
    _print(result)
    return 0 if result["status"] == "UNINSTALLED" else 1


def cmd_promotion_candidates(args: argparse.Namespace) -> int:
    task_id = args.task_id or _DEFAULT_TASK_ID
    _identity, repo_key, clone_key, workstream_key = _resolve_keys(task_id, args.root)
    _print(curation.curate(repo_key, clone_key, workstream_key))
    return 0


# ---------------------------------------------------------------------------
# Status (plan: "Autonomy, blockers, hygiene, and stopping" — Phase 3a's
# next-action/stopping outputs, read-only against already-persisted state).
# ---------------------------------------------------------------------------


def cmd_status(args: argparse.Namespace) -> int:
    """Read-only projection of Phase 3a's behavior outputs against the
    persisted active-state document — never mutates anything, never runs
    Flush. Blockers/hygiene are reconstructed via behavior.py's dedicated
    persisted-document helpers (`blocker_classification_from_persisted`,
    `hygiene_report_from_persisted`); `acceptance_complete` is read directly
    from `current.v1`'s own `status` field (`"terminal"`), the same signal
    `lifecycle.archive_workstream` gates on."""
    task_id = args.task_id or _DEFAULT_TASK_ID
    _identity, repo_key, clone_key, workstream_key = _resolve_keys(task_id, args.root)
    current_doc = transaction.read_current(repo_key, clone_key, workstream_key)
    if current_doc is None:
        _print({"status": "NO_ACTIVE_STATE", "workstream_key": workstream_key})
        return 1

    hygiene_report = behavior.hygiene_report_from_persisted(current_doc.get("hygiene", {}))
    blockers = [behavior.blocker_classification_from_persisted(b) for b in current_doc.get("blockers", [])]
    next_actions = current_doc.get("next_actions", [])
    acceptance_complete = current_doc.get("status") == "terminal"

    stopping = behavior.determine_stopping(
        operator_requested_stop=args.operator_stop,
        blockers=blockers,
        acceptance_complete=acceptance_complete,
        hygiene=hygiene_report,
        next_actions=next_actions,
    )

    _print({
        "workstream_key": workstream_key,
        "task_status": current_doc.get("status"),
        "objective": current_doc.get("objective"),
        "hygiene": {"all_clear": hygiene_report.all_clear, "plain_language": hygiene_report.plain_language()},
        "blockers": [{"kind": b.kind, "plain_language": b.plain_language()} for b in blockers],
        "next_actions": next_actions,
        "stopping": {"outcome": stopping.outcome, "reason": stopping.reason},
    })
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    report = doctor_mod.run_doctor(include_runtime=not args.skip_runtime)
    if args.json:
        _print(report)
    else:
        print(doctor_mod.render_report(report))
    status_value = report["disk_prerequisite_status"]
    if status_value == doctor_mod.FAIL:
        return 1
    if status_value == doctor_mod.UNKNOWN:
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="save-game")
    parser.add_argument("--root", default=identity_mod.default_start_path(), help="Anchor root to resolve identity from (default: cwd).")
    sub = parser.add_subparsers(dest="command", required=True)

    p_flush = sub.add_parser("flush", help="Save the current active state.")
    p_flush.add_argument("--task-id", default=None, help=f"Defaults to {_DEFAULT_TASK_ID!r} (placeholder pending Phase 3b session adapters).")
    p_flush.add_argument("--client-id", default="unknown", choices=_CLIENT_ID_CHOICES)
    p_flush.add_argument("--objective", default=None)
    p_flush.add_argument("--next-action", default=None)
    p_flush.add_argument("--status", default=None, choices=_STATUS_CHOICES, help="Set the workstream's lifecycle status (e.g. 'terminal' before archive).")
    p_flush.add_argument("--expected-digest", default=None, help="CAS: fail with RECOVERY_REQUIRED if current digest has moved past this.")
    p_flush.add_argument("--pressure-percent", type=int, default=None)
    p_flush.add_argument("--continuation-count", type=int, default=0)
    p_flush.add_argument("--authority-conflict", action="store_true")
    p_flush.set_defaults(func=cmd_flush)

    p_index = sub.add_parser("index", help="Resolve and print the current checkpoint (read-only).")
    p_index.add_argument("--task-id", default=None)
    p_index.set_defaults(func=cmd_index)

    p_compact = sub.add_parser("compact-check", help="Evaluate the Compact Decision ordered rule set.")
    p_compact.add_argument("--operator-request", default="unspecified", choices=["compact", "no_compact", "unspecified"])
    p_compact.add_argument("--pressure-source", default="unknown", choices=["client_metric", "operator_report", "unknown"])
    p_compact.add_argument("--pressure-percent", type=int, default=None)
    p_compact.add_argument("--continuation-count", type=int, default=0)
    p_compact.add_argument("--task-completed", action="store_true")
    p_compact.add_argument("--cross-session-continuation", action="store_true")
    p_compact.add_argument("--client-id", default="unknown", choices=_CLIENT_ID_CHOICES, help="Resolves the exact manual command + hook capability from adapters.py.")
    p_compact.set_defaults(func=cmd_compact_check)

    p_reconcile = sub.add_parser("reconcile", help="Reconcile current state, with explicit read-only observation available.")
    p_reconcile.add_argument("--task-id", default=None)
    mode = p_reconcile.add_mutually_exclusive_group()
    mode.add_argument("--trigger", action="append", default=None, help="Repeatable. Defaults to ['resume'].")
    mode.add_argument("--observe", action="store_true", help="Read-only pointer evidence. Refuse incomplete transactions.")
    p_reconcile.set_defaults(func=cmd_reconcile)

    p_adopt = sub.add_parser("adopt", help="Preview or write the private clone-level registration (plan: 'Adoption').")
    p_adopt.add_argument("--preview", action="store_true", help="Read-only: show current adoption_status instead of writing.")
    p_adopt.add_argument("--note", default=None, help="Free-text note (<=200 chars), stored in the registration.")
    p_adopt.add_argument("--disable", action="store_true", help="Write the registration with enabled=false instead of true.")
    p_adopt.set_defaults(func=cmd_adopt)

    p_retention = sub.add_parser("retention-status", help="Read-only eligible/pinned/ambiguous retention report ('gc status').")
    p_retention.add_argument("--task-id", default=None)
    p_retention.set_defaults(func=cmd_retention_status)

    p_gc = sub.add_parser("gc", help="Run automatic GC: deletes only abandoned temp files + unreferenced aborted snapshots >= 7 days old.")
    p_gc.add_argument("--task-id", default=None)
    p_gc.set_defaults(func=cmd_gc)

    p_archive = sub.add_parser("archive", help="Archive a terminal, hygiene-clear workstream (writes a hash manifest; never deletes).")
    p_archive.add_argument("--task-id", default=None)
    p_archive.set_defaults(func=cmd_archive)

    p_remove = sub.add_parser("remove", help="Preview-first, confirmation-bound permanent deletion of one workstream's private state.")
    p_remove.add_argument("--task-id", default=None)
    p_remove.add_argument("--execute", action="store_true", help="Actually delete. Requires --confirm-digest from a fresh preview.")
    p_remove.add_argument("--confirm-digest", default=None, help="The preview_digest from a prior 'remove' (without --execute) call.")
    p_remove.set_defaults(func=cmd_remove)

    p_uninstall = sub.add_parser("uninstall", help="Preview-first, confirmation-bound full private-state retirement for this repo/clone.")
    p_uninstall.add_argument("--execute", action="store_true", help="Actually delete. Requires --confirm-digest from a fresh preview.")
    p_uninstall.add_argument("--confirm-digest", default=None, help="The preview_digest from a prior 'uninstall' (without --execute) call.")
    p_uninstall.add_argument("--workstream-key", action="append", default=None, help="Advanced: repeatable raw workstream_key override. Defaults to auto-discovery of every workstream under this clone.")
    p_uninstall.set_defaults(func=cmd_uninstall)

    p_promo = sub.add_parser("promotion-candidates", help="Read-only report of candidates proposed for promotion (plan: 'Independent curation and promotion').")
    p_promo.add_argument("--task-id", default=None)
    p_promo.set_defaults(func=cmd_promotion_candidates)

    p_status = sub.add_parser("status", help="Read-only next-actions/stopping projection against persisted active state.")
    p_status.add_argument("--task-id", default=None)
    p_status.add_argument("--operator-stop", action="store_true", help="Signal an explicit operator stop into the stopping determination.")
    p_status.set_defaults(func=cmd_status)

    p_doctor = sub.add_parser("doctor", help="Run the engine doctor (schema/import prerequisites + optional runtime smoke checks).")
    p_doctor.add_argument("--json", action="store_true")
    p_doctor.add_argument("--skip-runtime", action="store_true", help="Skip throwaway flush/index/compact-check/reconcile smoke runs.")
    p_doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
