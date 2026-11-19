#!/usr/bin/env python3
"""Inspect a managed local-jobs instance and write a layperson explain cache."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import explain  # noqa: E402
import explain_agent_queue  # noqa: E402
import explain_cache  # noqa: E402
import explain_synthesize  # noqa: E402
import registry  # noqa: E402


def inspect_job(job_id: str, *, queue_agent: bool = True) -> dict[str, Any]:
    reg = registry.load_registry()
    inst = next((i for i in registry.collect_instances(reg) if i.get("id") == job_id), None)
    if inst is None:
        raise SystemExit(f"unknown job id: {job_id}")
    if inst.get("role") == "error":
        raise SystemExit(f"job {job_id} is quarantined")

    existing = explain_cache.load_for_instance(inst)
    if existing and existing.get("source") == "agent":
        return existing

    type_by_slug = {t["slug"]: t for t in registry.build_list_types(reg)}
    facts = explain_synthesize.facts_from_instance(inst, type_by_slug)
    narrative = explain_synthesize.synthesize_narrative(facts)

    ops = explain.build_explain(job_id, str(inst.get("type") or "?"), {"instances": [inst]})
    suggested = list(ops.get("suggested_commands") or [])

    fp = explain_cache.fingerprint(inst)
    body = {
        "job_id": job_id,
        "type": inst.get("type"),
        "fingerprint": fp,
        "source": "synthesize",
        "narrative": narrative,
        "suggested_commands": suggested,
    }

    if queue_agent:
        explain_agent_queue.write_task(
            job_id,
            {
                "fingerprint": fp,
                "prompt": explain_agent_queue.agent_prompt(job_id, facts.__dict__),
            },
        )

    return body


def cmd_write(job_id: str) -> int:
    body = inspect_job(job_id)
    if body.get("source") == "agent" and "narrative" in body:
        print(explain_cache.cache_path(job_id))
        return 0
    path = explain_cache.write(job_id, body)
    print(path)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="explain_inspect.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_write = sub.add_parser("write")
    p_write.add_argument("--id", required=True)
    args = ap.parse_args()
    if args.cmd == "write":
        return cmd_write(args.id)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
