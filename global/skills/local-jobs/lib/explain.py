#!/usr/bin/env python3
"""Operator narrative layer for local-jobs.

The single source of truth for the plain-English surfaces built on top of a
``dashboard/v1`` payload: ``next_actions[]``, the one-line ``health_verdict``,
per-job ``explain-job`` narratives, and the ``--brief`` printer. Extracted from
``dashboard.py`` so the data-join (``build_dashboard``) and the narrative it
feeds live in separate modules with no copy-paste duplication.

These are pure functions over an already-built payload dict — this module has no
dependency on ``dashboard`` or ``registry``, so it is a leaf in the import graph
(``dashboard`` imports *this*, never the reverse). Behavior is identical to the
prior in-dashboard implementation.
"""

from __future__ import annotations

from typing import Any

import schedule as schedule_mod

STALE_HOURS_DEFAULT = 36


def _schedule_lay(value: Any, fallback: str = "its schedule") -> str:
    if value is None:
        return fallback
    try:
        return schedule_mod.Schedule.parse(value).summary()
    except (ValueError, TypeError, KeyError):
        s = str(value).strip()
        return s if s else fallback


def _action(priority: int, job_id: str, jtype: str, issue: str, verb: str, command: str) -> dict[str, Any]:
    return {
        "priority": priority,
        "job_id": job_id,
        "type": jtype,
        "issue": issue,
        "verb": verb,
        "command": command,
    }


def build_next_actions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for inst in payload.get("instances", []):
        iid = inst.get("id") or inst.get("type") or "?"
        jtype = inst.get("type") or "?"
        if inst.get("role") == "error":
            actions.append(_action(1, iid, jtype, "quarantined type", "doctor",
                                     f"scripts/local-jobs.sh doctor"))
            continue
        rs = inst.get("run_stats") or {}
        if inst.get("drift"):
            actions.append(_action(1, iid, jtype, "launchd drift", "repair",
                                     f"scripts/local-jobs.sh repair-job --id {iid}"))
        if rs.get("consecutive_failures", 0) > 0:
            actions.append(_action(2, iid, jtype, f"{rs['consecutive_failures']} consecutive failure(s)", "logs",
                                     f"scripts/local-jobs.sh logs-job --id {iid} --tail 50"))
            actions.append(_action(2, iid, jtype, "retry run", "run",
                                     f"scripts/local-jobs.sh run-job --id {iid}"))
        if inst.get("stale"):
            actions.append(_action(3, iid, jtype, "stale — no recent success", "run",
                                     f"scripts/local-jobs.sh run-job --id {iid}"))
    for item in payload.get("discovered_unmanaged") or []:
        label = item.get("label") or "?"
        actions.append(_action(4, label, "unmanaged", "unmanaged launch agent", "adopt",
                                 f"scripts/local-jobs.sh adopt-job --label {label}"))
    actions.sort(key=lambda a: (a["priority"], a.get("job_id") or ""))
    return actions


def build_health_verdict(payload: dict[str, Any]) -> str:
    s = payload.get("summary") or {}
    parts: list[str] = []
    total = s.get("total", 0)
    if s.get("quarantined", 0):
        parts.append(f"{s['quarantined']} quarantined type(s)")
    if s.get("failing", 0):
        parts.append(f"{s['failing']} failing")
    issues = sum(
        1 for i in payload.get("instances", [])
        if ((i.get("run_stats") or {}).get("last_run") or {}).get("status") == "completed_with_failures"
    )
    if issues:
        parts.append(f"{issues} completed with issues")
    if s.get("drifted", 0):
        parts.append(f"{s['drifted']} drifted")
    stale = sum(1 for i in payload.get("instances", []) if i.get("stale"))
    if stale:
        parts.append(f"{stale} stale")
    if s.get("unmanaged", 0):
        parts.append(f"{s['unmanaged']} unmanaged agent(s)")
    running = s.get("running", 0)
    if not parts:
        if total == 0:
            return "No local jobs configured on this machine."
        running_note = f" ({running} running now)" if running else ""
        return f"All {total} managed job(s) healthy{running_note}."
    return f"{total} job(s): " + ", ".join(parts) + "."


def build_job_overview(inst: dict[str, Any], type_by_slug: dict[str, dict[str, Any]]) -> str:
    """Purpose-first plain English for in-canvas job click-to-explain."""
    iid = inst.get("id") or "?"
    jtype = inst.get("type") or "?"
    tdesc = (type_by_slug.get(jtype) or {}).get("description") or ""

    if inst.get("role") == "error":
        err = inst.get("error") or {}
        reason = err.get("reason") or "handler error"
        return tdesc or f"{jtype} is quarantined ({reason}) until repaired."

    # A user-set description is the operator's own words: it wins over any
    # derived overview (display precedence: description > overview > type desc).
    desc = inst.get("description")
    if isinstance(desc, str) and desc.strip():
        return desc.strip()

    if inst.get("role") == "global_scheduler" or iid == "__global__":
        sched = _schedule_lay(inst.get("schedule_summary") or inst.get("schedule"), "its evening window")
        return (
            "The git-fetch sweep is the global scheduler for incremental-git-fetch. "
            f"Once per window ({sched}), it runs filtered git fetches for every repo whose schedule is inherit."
        )

    if jtype == "incremental-git-fetch":
        path = inst.get("path") or "the configured repo"
        branch = inst.get("branch") or "its branch"
        sched = inst.get("schedule")
        if sched == "inherit":
            return f"Keeps {path} ({branch}) current via a filtered git fetch during the global git-fetch sweep."
        sched_s = _schedule_lay(inst.get("schedule_summary") or sched)
        return f"Keeps {path} ({branch}) current via filtered git fetch on schedule {sched_s}."

    if jtype == "command":
        prog = inst.get("program") or "a shell command"
        on_demand = inst.get("execution_mode") == "on_demand"
        args = inst.get("args") or []
        script = str(args[-1]) if args else str(prog)
        comment = None
        try:
            from explain_synthesize import _script_comment_summary  # noqa: WPS433

            comment = _script_comment_summary(script)
        except Exception:
            comment = None
        if on_demand:
            when = "runs on demand (no timer)"
            base = f"Runs {prog} on demand (no scheduling agent)."
        else:
            sched_s = _schedule_lay(inst.get("schedule_summary") or inst.get("schedule"))
            when = f"scheduled {sched_s}"
            base = f"Runs {prog} on schedule {sched_s}."
        if comment:
            lead = comment.rstrip(".")
            return f"{lead} — {when}."
        return f"{base} {tdesc}".strip() if tdesc else base

    if tdesc:
        return tdesc

    return f"{iid} is a managed {jtype} job on this machine."


def build_explain(job_id: str, job_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    inst = next((i for i in payload.get("instances", []) if i.get("id") == job_id), None)
    if inst is None:
        return {
            "job_id": job_id,
            "type": job_type,
            "found": False,
            "narrative": [f"No managed instance '{job_id}' found."],
            "suggested_commands": [f"scripts/local-jobs.sh resolve-instance --query {job_id}"],
        }
    lines: list[str] = []
    cmds: list[str] = []
    enabled = inst.get("enabled", True)
    loaded = inst.get("launchd_loaded")
    if inst.get("execution_mode") == "on_demand":
        lines.append(f"{job_id} ({job_type}) runs on demand (no scheduling agent); trigger it with Run now.")
    else:
        lines.append(f"{job_id} ({job_type}) is {'enabled' if enabled else 'disabled'}; launchd loaded={loaded}.")
    rs = inst.get("run_stats") or {}
    last = rs.get("last_run")
    if last:
        lines.append(f"Last run: {last.get('status')} at {last.get('ts')} — {last.get('summary') or '(no summary)'}.")
        if last.get("status") == "completed_with_failures":
            # Mixed sweep: informational only — the genuinely-failed repo(s) carry
            # their own failing streak and retry actions, not this parent.
            lines.append("Last sweep completed with issues — some repos failed while others succeeded; open the failing repo(s) individually to retry.")
    else:
        lines.append("Never run (no run-log records).")
    if inst.get("drift"):
        lines.append("DRIFT: enabled state disagrees with launchd — repair recommended.")
        cmds.append(f"scripts/local-jobs.sh repair-job --id {job_id}")
    if rs.get("consecutive_failures", 0) > 0:
        lines.append(f"Failing streak: {rs['consecutive_failures']} consecutive failure(s).")
        cmds.append(f"scripts/local-jobs.sh logs-job --id {job_id} --tail 50")
        cmds.append(f"scripts/local-jobs.sh run-job --id {job_id}")
    if inst.get("stale"):
        lines.append(f"Stale: no success in >{STALE_HOURS_DEFAULT}h (daily schedule).")
        cmds.append(f"scripts/local-jobs.sh run-job --id {job_id}")
    nr = inst.get("next_run") or {}
    if nr.get("window_start"):
        lines.append(f"Next window: {nr['window_start']}..{nr.get('window_end')} ({nr.get('basis')}).")
    if inst.get("role") == "error":
        err = inst.get("error") or {}
        lines.append(f"QUARANTINED: {err.get('reason')}")
        cmds.append("scripts/local-jobs.sh doctor")
    # dedupe commands preserving order
    seen: set[str] = set()
    deduped = [c for c in cmds if not (c in seen or seen.add(c))]
    return {
        "job_id": job_id,
        "type": job_type,
        "found": True,
        "narrative": lines,
        "suggested_commands": deduped or [f"scripts/local-jobs.sh dashboard --json"],
    }


def print_brief(payload: dict[str, Any]) -> None:
    print(build_health_verdict(payload))
    s = payload.get("summary") or {}
    print(f"  {s.get('total', 0)} managed · {s.get('failing', 0)} failing · "
          f"{s.get('drifted', 0)} drifted · {s.get('quarantined', 0)} quarantined · "
          f"{s.get('unmanaged', 0)} unmanaged")
    actions = payload.get("next_actions") or []
    if actions:
        print("Next actions:")
        for a in actions[:3]:
            print(f"  • {a['issue']} ({a['job_id']}): {a['command']}")
    stale_n = sum(1 for i in payload.get("instances", []) if i.get("stale"))
    if stale_n:
        print(f"  {stale_n} job(s) stale (no success in >{STALE_HOURS_DEFAULT}h).")
    gen = payload.get("generated_at")
    if gen:
        print(f"  Snapshot: {gen}")


def print_explain(explain: dict[str, Any]) -> None:
    print(f"=== {explain.get('job_id')} ({explain.get('type')}) ===")
    for line in explain.get("narrative") or []:
        print(line)
    cmds = explain.get("suggested_commands") or []
    if cmds:
        print("\nSuggested:")
        for c in cmds:
            print(f"  {c}")
