#!/usr/bin/env python3
"""Queue optional agent-authored explain upgrades for local-jobs dashboard jobs."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def queue_dir() -> Path:
    return Path(os.environ.get("LOCAL_JOBS_STATE", str(Path.home() / ".local-jobs"))) / "explain" / "agent-queue"


def write_task(job_id: str, payload: dict[str, Any]) -> Path:
    queue_dir().mkdir(parents=True, exist_ok=True)
    path = queue_dir() / f"{job_id.replace('/', '_')}.json"
    body = {
        "schema": "job-explain-agent-queue/v1",
        "job_id": job_id,
        "queued_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        **payload,
    }
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)
    return path


def agent_prompt(job_id: str, facts: dict[str, Any]) -> str:
    return f"""local-jobs dashboard: write a layperson explanation for job "{job_id}".

Read the job on this machine (handler config, program/script, recent logs if useful). Do NOT paste code or log dumps into the answer.

Write JSON to ~/.local-jobs/explain/{job_id}.json:
- schema: job-explain/v1
- source: agent
- fingerprint: (match current job config — see context)
- narrative: 2–4 short plain-English paragraphs (what it does for the operator, when it runs, what to watch for)
- suggested_commands: only if genuinely helpful for troubleshooting

Context (machine-gathered, may be incomplete):
{json.dumps(facts, indent=2)}

When done, run: local-jobs view
Work silently; do not ask questions."""
