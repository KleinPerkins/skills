#!/usr/bin/env python3
"""Turn inspected job facts into layperson dashboard explanations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import schedule as schedule_mod


@dataclass
class GatherFacts:
    job_id: str
    job_type: str
    role: str
    enabled: bool
    schedule_summary: str
    execution_mode: str = "scheduled"
    description: str | None = None
    program: str | None = None
    script_path: str | None = None
    script_comment: str | None = None
    repo_path: str | None = None
    repo_name: str | None = None
    branch: str | None = None
    remote: str | None = None
    type_description: str | None = None
    last_run_status: str | None = None
    consecutive_failures: int = 0
    drift: bool = False
    stale: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def _basename_repo(path: str | None) -> str | None:
    if not path:
        return None
    p = path.rstrip("/")
    return p.split("/")[-1] if p else None


def _script_comment_summary(path: str | None, max_lines: int = 20) -> str | None:
    if not path:
        return None
    p = Path(path).expanduser()
    if not p.is_file():
        return None
    try:
        lines = p.read_text(errors="replace").splitlines()
    except OSError:
        return None
    comments: list[str] = []
    for line in lines[:max_lines]:
        stripped = line.strip()
        if stripped.startswith("#"):
            text = stripped.lstrip("#").strip()
            if text and not text.startswith("!"):
                comments.append(text)
        elif stripped and not stripped.startswith("#"):
            break
    if not comments:
        return None
    joined = " ".join(comments)
    joined = re.sub(r"\s+", " ", joined).strip()
    return joined or None


def _schedule_when(summary: str) -> str:
    s = summary.strip().lower()
    if s == "inherit (follows global window)":
        return "during the shared evening git-fetch window (roughly 6–10pm local)"
    if s.startswith("daily "):
        time_part = summary[6:].replace(" local", "")
        return f"once each day at {time_part} local time"
    if s.startswith("every "):
        return s.replace("every", "about every", 1)
    return summary or "on its configured schedule"


def _command_what(facts: GatherFacts) -> str:
    cid = facts.job_id
    comment = facts.script_comment or ""
    script = facts.script_path or facts.program or ""

    if "orchestrator" in script or "session-hook" in script or cid == "orchestrator":
        return (
            "This keeps the ecosystem orchestrator's session hook healthy. It runs the "
            "periodic maintenance path so capability sync and session bookkeeping stay current."
        )
    if comment:
        cleaned = comment
        cleaned = re.sub(r"^scripts?/hooks?/\S+\s*[—–-]\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"^daily:\s*", "Each run ", cleaned, flags=re.I)
        if cleaned and not cleaned[0].isupper():
            cleaned = cleaned[0].upper() + cleaned[1:]
        return f"This job runs a script on your Mac. {cleaned}."
    if script:
        name = Path(script).name
        return f"This job runs the {name} program on your Mac."
    return "This job runs a command on your Mac."


def _igf_what(facts: GatherFacts) -> str:
    repo = facts.repo_name or facts.repo_path or "the configured repository"
    branch = facts.branch or "its default branch"
    when = _schedule_when(facts.schedule_summary)
    if facts.role == "global_scheduler":
        return (
            "This is the evening git-fetch sweep. Once per window it runs filtered fetches "
            "for every vendor repo whose schedule is set to inherit — so those repos do not "
            "need their own separate timers."
        )
    if facts.schedule_summary.startswith("inherit"):
        return (
            f"This keeps your local clone of {repo} aligned with GitHub. During the shared "
            f"evening fetch window it downloads the latest {branch} commits using a bandwidth‑"
            f"friendly filtered fetch. It does not rewrite your working tree on its own."
        )
    return (
        f"This keeps your local clone of {repo} aligned with GitHub by fetching the latest "
        f"{branch} {when}. It uses a filtered fetch to avoid downloading unnecessary history."
    )


def _repo_snapshot_what(facts: GatherFacts) -> str:
    return (
        "This archives a snapshot of a governed team repo from your machine "
        "to your personal remote backup. It is a continuity job, not something "
        "that changes the source repository."
    )


def synthesize_narrative(facts: GatherFacts) -> list[str]:
    when = _schedule_when(facts.schedule_summary)
    paragraphs: list[str] = []

    # Display precedence: a user-set description is the operator's own words and
    # leads the narrative over any derived "what this does" paragraph.
    if facts.description:
        paragraphs.append(facts.description)
    elif facts.job_type == "command":
        paragraphs.append(_command_what(facts))
    elif facts.job_type == "incremental-git-fetch":
        paragraphs.append(_igf_what(facts))
    elif facts.job_type.endswith("-archive"):
        paragraphs.append(_repo_snapshot_what(facts))
    elif facts.type_description:
        paragraphs.append(facts.type_description)
    else:
        paragraphs.append(f"The {facts.job_id} job is a managed {facts.job_type} task on this Mac.")

    if facts.role != "global_scheduler":
        if facts.execution_mode == "on_demand":
            paragraphs.append(
                "It runs on demand only — there is no timer and no scheduling agent installed. "
                "Trigger it yourself with Run now (or run-job) when you need it."
            )
        else:
            state = "enabled" if facts.enabled else "paused"
            paragraphs.append(
                f"It is {state} and scheduled to run {when}. macOS launchd starts it automatically; "
                f"you do not need to run it by hand unless you are testing."
            )

    if facts.consecutive_failures > 0:
        paragraphs.append(
            f"Heads-up: the last {facts.consecutive_failures} run(s) failed. Check logs or use "
            f"the suggested commands below if you want to dig in."
        )
    elif facts.drift:
        paragraphs.append(
            "Launchd state looks out of sync with the job config (drift). A repair pass is "
            "recommended so the timer matches what local-jobs thinks is enabled."
        )
    elif facts.stale:
        paragraphs.append(
            "This job has not recorded a recent success. That may be normal for a new job, or "
            "it may be worth a manual run to confirm it still works."
        )
    elif facts.last_run_status == "completed_with_failures":
        paragraphs.append(
            "The last sweep completed with issues — some repos updated fine while others failed. "
            "The failing repos are listed individually with their own status, so only those need a look."
        )
    elif facts.last_run_status == "success":
        paragraphs.append("Recent runs have been completing successfully.")

    return paragraphs


def facts_from_instance(inst: dict[str, Any], type_by_slug: dict[str, dict[str, Any]]) -> GatherFacts:
    jtype = str(inst.get("type") or "?")
    iid = str(inst.get("id") or "?")
    sched_raw = inst.get("schedule_summary") or inst.get("schedule")
    try:
        sched_summary = schedule_mod.Schedule.parse(sched_raw).summary()
    except (ValueError, TypeError, KeyError):
        sched_summary = str(sched_raw) if sched_raw is not None else "unknown"

    script_path = None
    if jtype == "command":
        args = inst.get("args") or []
        if args:
            script_path = str(args[-1])
        elif inst.get("program"):
            script_path = str(inst["program"])

    rs = inst.get("run_stats") or {}
    last = rs.get("last_run") or {}

    return GatherFacts(
        job_id=iid,
        job_type=jtype,
        role=str(inst.get("role") or "instance"),
        enabled=bool(inst.get("enabled", True)),
        schedule_summary=sched_summary,
        execution_mode=str(inst.get("execution_mode") or "scheduled"),
        description=(str(inst.get("description")).strip() or None) if inst.get("description") else None,
        program=str(inst.get("program")) if inst.get("program") else None,
        script_path=script_path,
        script_comment=_script_comment_summary(script_path),
        repo_path=str(inst.get("path")) if inst.get("path") else None,
        repo_name=_basename_repo(str(inst.get("path")) if inst.get("path") else None),
        branch=str(inst.get("branch")) if inst.get("branch") else None,
        remote=str(inst.get("remote")) if inst.get("remote") else None,
        type_description=(type_by_slug.get(jtype) or {}).get("description"),
        last_run_status=str(last.get("status")) if last.get("status") else None,
        consecutive_failures=int(rs.get("consecutive_failures") or 0),
        drift=bool(inst.get("drift")),
        stale=bool(inst.get("stale")),
    )
