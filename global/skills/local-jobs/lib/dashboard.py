#!/usr/bin/env python3
"""Rich dashboard payload for local-jobs (consumed by `dashboard --json` and the
Cursor Canvas recipe). Joins handler-discovered instances with the run log to
add last-run, failure streaks, duration aggregates, a next-run *window* (never a
point — jitter is runtime), drift detection, and parsed summaries.
"""

from __future__ import annotations

import statistics
import os
from datetime import datetime
from typing import Any

import events
import explain
import explain_cache
import launchd
import registry
import running
import settings
import run_log
import schedule as schedule_mod

# The staleness threshold and the narrative builders (next_actions, health
# verdict, explain, brief) live in lib/explain.py — the single source of truth.
# Re-exported here so the data-join code below reads unchanged.
STALE_HOURS_DEFAULT = explain.STALE_HOURS_DEFAULT


def _now() -> datetime:
    """Local, tz-aware clock. ``LOCAL_JOBS_NOW`` (ISO 8601) overrides it so the
    render — next-run windows, staleness, run recency — is deterministic in tests.
    """
    raw = os.environ.get("LOCAL_JOBS_NOW")
    if raw:
        try:
            dt = datetime.fromisoformat(raw)
            return dt if dt.tzinfo is not None else dt.astimezone()
        except ValueError:
            pass
    return datetime.now().astimezone()


def _next_run(inst: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Next-run window via the single scheduler (LOCAL time — fixes the UTC
    drift, P1-6). 'inherit' has no own window; it follows the global agent.
    """
    # on_demand jobs have no timer at all — they run only via Run now / run-job.
    if inst.get("execution_mode") == "on_demand":
        return {"window_start": None, "window_end": None, "basis": "on_demand"}
    if inst.get("enabled") is False:
        return {"window_start": None, "window_end": None, "basis": "disabled"}
    sched = inst.get("schedule")
    if sched in (None, "inherit"):
        return {"window_start": None, "window_end": None, "basis": "inherit"}
    try:
        return schedule_mod.Schedule.parse(sched).next_run(now)
    except (ValueError, KeyError, TypeError):
        return {"window_start": None, "window_end": None, "basis": "unknown"}


def _records_for(inst: dict[str, Any], all_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    job_id = "all" if inst.get("role") == "global_scheduler" else inst.get("id")
    return [r for r in all_records if r.get("job_id") == job_id]


def _recent_outcomes(records: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    """Per-job run history (oldest→newest): just enough to draw a status strip
    without dumping raw logs."""
    return [
        {
            "ts": r.get("ts"),
            "status": r.get("status"),
            "summary": r.get("summary"),
            "duration_s": r.get("duration_s"),
        }
        for r in records[-limit:]
    ]


def _run_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {
            "last_run": None, "last_success_ts": None, "consecutive_failures": 0,
            "durations": {"p50": None, "max": None, "avg": None, "last": None, "series": []},
            "recent": [],
        }
    last = records[-1]
    last_success = next((r["ts"] for r in reversed(records) if r.get("status") == "success"), None)
    cf = 0
    for r in reversed(records):
        if r.get("status") == "failure":
            cf += 1
        else:
            break
    durs = [int(r["duration_s"]) for r in records if isinstance(r.get("duration_s"), int)]
    series = durs[-10:]
    last_dur = int(last["duration_s"]) if isinstance(last.get("duration_s"), int) else None
    agg = {
        "p50": int(statistics.median(durs)) if durs else None,
        "max": max(durs) if durs else None,
        "avg": int(statistics.fmean(durs)) if durs else None,
        "last": last_dur,
        "series": series,
    }
    return {
        "last_run": {
            "ts": last.get("ts"),
            "status": last.get("status"),
            "summary": last.get("summary"),
            "rc": last.get("rc"),
            "duration_s": last_dur,
            "fields": last.get("fields") or {},  # full fidelity (P0-B): nothing dropped
        },
        "last_success_ts": last_success,
        "consecutive_failures": cf,
        "durations": agg,
        "recent": _recent_outcomes(records),
    }


def _hours_since(ts: str | None, now: datetime) -> float | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.astimezone()
        return (now - dt).total_seconds() / 3600.0
    except (ValueError, TypeError):
        return None


def _is_stale(last_success_ts: str | None, schedule: Any, now: datetime, threshold_h: float = STALE_HOURS_DEFAULT) -> bool:
    """True when a daily-scheduled job hasn't succeeded within threshold hours."""
    if schedule in (None, "inherit", "?"):
        return False
    hrs = _hours_since(last_success_ts, now)
    if hrs is None:
        return True
    return hrs > threshold_h


# Floor so short jobs with tiny, noisy histories don't trip the flag on startup.
RUNNING_LONG_FLOOR_SECONDS = 300
RUNNING_LONG_MULTIPLIER = 3


def _running_long(elapsed_s: float | None, durations: dict[str, Any]) -> bool:
    """Observability-only: a run still going well beyond its historical typical
    duration. Needs a duration history to have a basis (unknown history is never
    flagged), and NEVER triggers an auto-kill/timeout — it only annotates the
    dashboard so a stuck run is visible.
    """
    if elapsed_s is None:
        return False
    typical = durations.get("max") or durations.get("p50")
    if not typical:
        return False
    return elapsed_s > max(typical * RUNNING_LONG_MULTIPLIER, RUNNING_LONG_FLOOR_SECONDS)


def _recent_runs(limit: int = 15, keep_ids: set[str] | None = None) -> list[dict[str, Any]]:
    """Newest ``limit`` run events. When ``keep_ids`` is given, only runs for a
    currently-registered instance survive (retired jobs drop out of the active
    feed; their append-only audit events remain in ``recent_events``)."""
    runs = [e for e in events.recent(limit * 6) if e.get("kind") == "run"]
    if keep_ids is not None:
        runs = [e for e in runs if e.get("job_id") in keep_ids]
    return runs[-limit:]


def _needs_attention(i: dict[str, Any]) -> bool:
    """Quarantined, failing, drifted, stale, or a mixed (completed_with_failures)
    sweep. A mixed sweep is attention-worthy even though it is not a fully-failed
    job (it accrues no failure streak of its own). This is the SINGLE definition
    the row sort, the PM buckets here, and the canvas ``needsAttention()`` all use
    so the summary counts always reconcile with the visible rows.
    """
    rs = i.get("run_stats") or {}
    last = rs.get("last_run") or {}
    return bool(
        i.get("role") == "error"
        or rs.get("consecutive_failures", 0) > 0
        or i.get("drift")
        or i.get("stale")
        or last.get("status") == "completed_with_failures"
    )


def _pm_buckets(out_instances: list[dict[str, Any]]) -> dict[str, int]:
    """PM-facing, mutually-exclusive, exhaustive buckets over EVERY instance.

    Each job lands in exactly one of healthy / needs_attention / paused /
    on_demand, so the four counts sum to ``len(out_instances)`` and reconcile
    with the dashboard rows. Order mirrors the canvas: attention wins first, then
    the execution mode (on_demand before paused, since an on_demand job has no
    timer to pause), else healthy.
    """
    healthy = attention = paused = on_demand = 0
    for i in out_instances:
        if _needs_attention(i):
            attention += 1
        elif i.get("execution_mode") == "on_demand":
            on_demand += 1
        elif i.get("enabled") is False:
            paused += 1
        else:
            healthy += 1
    return {"healthy": healthy, "needs_attention": attention, "paused": paused, "on_demand": on_demand}


# The operator narrative — next_actions, health_verdict, explain, and the
# --brief / explain printers — lives in lib/explain.py (single source of truth).
# build_dashboard() below delegates to explain.build_* for the payload fields.


def build_dashboard(reg: dict[str, Any]) -> dict[str, Any]:
    now = _now()  # LOCAL, tz-aware (fixes UTC next-run drift; deterministic in tests)
    launchd_disabled = os.environ.get("LOCAL_JOBS_LAUNCHD_DISABLE", "0") == "1"
    running_map = running.active_map(now)
    running_now = set(running_map.keys())
    instances = registry.collect_instances(reg)
    records = run_log.read_records()
    managed = registry.managed_labels(reg, instances)
    discovered = []
    seen = set()
    for prefix in settings.discovery_prefixes(reg):
        for item in registry.discover_launchd(prefix):
            if item["label"] not in seen:
                discovered.append(item)
                seen.add(item["label"])
    unmanaged = [d for d in discovered if d["label"] not in managed]

    type_by_slug = {t["slug"]: t for t in registry.build_list_types(reg)}
    out_instances = []
    failing = 0
    quarantined = 0
    for inst in instances:
        # Quarantined (broken) types render as degraded — never crash the board,
        # never claim a schedule/last-run they don't have.
        if inst.get("role") == "error":
            quarantined += 1
            out_instances.append({
                **inst,
                "overview": explain.build_job_overview(inst, type_by_slug),
                "next_run": {"window_start": None, "window_end": None, "basis": "error"},
                "run_stats": _run_stats([]),
                "drift": False,
                "stale": False,
                "running": False,
                "running_since": None,
                "running_long": False,
                "hours_since_success": None,
            })
            continue
        stats = _run_stats(_records_for(inst, records))
        enabled = inst.get("enabled", True)
        loaded = inst.get("launchd_loaded")
        sched = inst.get("schedule")
        on_demand = inst.get("execution_mode") == "on_demand"
        # on_demand jobs never carry a launchd agent; "no loaded agent" is the
        # correct, honest state, so they can never drift or go stale.
        if on_demand:
            drift = False
        # Disabled inherit repos have no per-repo agent — skip loaded/drift checks.
        elif sched == "inherit" and not enabled:
            drift = False
        else:
            drift = False if launchd_disabled else bool((enabled and loaded is False) or (not enabled and loaded is True))
        stale = False if launchd_disabled or not enabled or on_demand else _is_stale(stats["last_success_ts"], inst.get("schedule"), now)
        hours_since = _hours_since(stats["last_success_ts"], now)
        if stats["consecutive_failures"] > 0:
            failing += 1
        effective_id = "all" if inst.get("role") == "global_scheduler" else inst.get("id")
        is_running = (inst.get("type"), effective_id) in running_now
        running_since = running_map.get((inst.get("type"), effective_id)) if is_running else None
        elapsed_s = None
        if running_since:
            elapsed_h = _hours_since(running_since, now)
            elapsed_s = elapsed_h * 3600.0 if elapsed_h is not None else None
        running_long = _running_long(elapsed_s, stats["durations"]) if is_running else False
        out_instances.append({
            **inst,
            "overview": explain.build_job_overview(inst, type_by_slug),
            "next_run": _next_run(inst, now),
            "run_stats": stats,
            "drift": drift,
            "stale": stale,
            "running": is_running,
            "running_since": running_since,
            "running_long": running_long,
            "hours_since_success": hours_since,
        })

    # Quarantined, failing, drifted, stale, and mixed (completed_with_failures)
    # sort to the top (see module-level _needs_attention — the single definition
    # shared by the sort, the PM buckets, and the canvas).
    out_instances.sort(key=lambda i: (0 if _needs_attention(i) else 1, i.get("id") or ""))

    for inst in out_instances:
        cached = explain_cache.load_for_instance(inst)
        if cached:
            inst["explain_deep"] = cached

    # Restrict the global run feed to currently-registered instances so retired
    # jobs disappear from the active view; their audit events remain untouched.
    registered_ids: set[str] = set()
    for inst in out_instances:
        if inst.get("role") == "error":
            continue
        iid = inst.get("id")
        if iid:
            registered_ids.add(iid)
        if inst.get("role") == "global_scheduler":
            registered_ids.add("all")  # the sweep aggregate is logged under "all"

    recent_runs = list(reversed(_recent_runs(15, registered_ids)))
    bridge_label = settings.label_for("canvas-bridge", cardinality="singleton", registry=reg)
    payload = {
        "schema": "dashboard/v1",
        "generated_at": now.isoformat(timespec="seconds"),
        "run_bridge_enabled": launchd.is_loaded(bridge_label),
        "summary": {
            "total": sum(1 for i in out_instances if i.get("role") != "error"),
            "failing": failing,
            "drifted": sum(1 for i in out_instances if i["drift"]),
            "quarantined": quarantined,
            "disabled": sum(1 for i in out_instances if i.get("role") != "error" and i.get("enabled") is False and i.get("execution_mode") != "on_demand"),
            "on_demand": sum(1 for i in out_instances if i.get("role") != "error" and i.get("execution_mode") == "on_demand"),
            "running": sum(1 for i in out_instances if i.get("running")),
            "unmanaged": len(unmanaged),
            # PM-facing buckets over EVERY instance (mutually exclusive, sum to
            # len(instances)); these are the reconciled terms the canvas shows.
            "buckets": _pm_buckets(out_instances),
        },
        "instances": out_instances,
        "discovered_unmanaged": unmanaged,
        "recent_events": list(reversed(events.recent(25))),  # newest first
        "recent_runs": recent_runs,
        "type_catalog": [
            {"slug": t["slug"], "description": t.get("description") or "", "cardinality": t.get("cardinality")}
            for t in registry.build_list_types(reg)
        ],
    }
    overlay_errors = reg.get("overlay_errors")
    if overlay_errors:
        payload["overlay_errors"] = overlay_errors
    payload["health_verdict"] = explain.build_health_verdict(payload)
    payload["next_actions"] = explain.build_next_actions(payload)
    return payload


def print_dashboard(payload: dict[str, Any]) -> None:
    s = payload["summary"]
    b = s.get("buckets") or {}
    print(f"local-jobs dashboard — generated {payload['generated_at']}")
    print(
        f"  {s['total']} jobs · {s['failing']} failing · {s['drifted']} drifted · "
        f"{s.get('quarantined', 0)} quarantined · {s['unmanaged']} unmanaged"
    )
    # PM-facing reconciled buckets (mutually exclusive) — the same terms the canvas shows.
    print(
        f"  {b.get('healthy', 0)} healthy · {b.get('needs_attention', 0)} need attention · "
        f"{b.get('paused', 0)} paused · {b.get('on_demand', 0)} on demand"
    )
    overlay_errors = payload.get("overlay_errors") or {}
    if overlay_errors:
        print("\n== Overlay errors ==")
        for jid, msg in sorted(overlay_errors.items()):
            print(f"  {jid}: {msg}")
    for inst in payload["instances"]:
        if inst.get("role") == "error":
            err = inst.get("error") or {}
            print(f"  - {inst.get('type')} [QUARANTINED]: {err.get('reason')} (verb={err.get('verb')})")
            continue
        rs = inst["run_stats"]
        last = rs["last_run"]
        last_s = f"{last['status']} — {last['summary']}" if last else "never run"
        flags = []
        if inst.get("running"):
            flags.append("RUNNING LONG" if inst.get("running_long") else "RUNNING")
        if inst.get("execution_mode") == "on_demand":
            flags.append("ON DEMAND")
        elif inst.get("enabled") is False:
            flags.append("DISABLED")
        if inst["drift"]:
            flags.append("DRIFT")
        if last and last.get("status") == "completed_with_failures":
            flags.append("ISSUES")
        if rs["consecutive_failures"] > 0:
            flags.append(f"{rs['consecutive_failures']}x FAIL")
        flag_s = (" [" + ",".join(flags) + "]") if flags else ""
        print(f"  - {inst.get('id')} ({inst.get('type')}){flag_s}: last={last_s}")
        nr = inst["next_run"]
        if nr.get("window_start"):
            print(f"      next: {nr['window_start']}..{nr['window_end']} ({nr['basis']})")
        elif nr.get("basis") == "on_demand":
            print("      next: on demand (no timer)")
