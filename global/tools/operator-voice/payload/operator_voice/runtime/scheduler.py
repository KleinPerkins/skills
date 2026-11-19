"""local-jobs on-demand curation planner (daily maintenance policy, ADR 0007).

This module is a PURE PLANNER: it renders the exact ``local-jobs.sh`` argv for the single
``command``-type instance that invokes ``operator-voice curate`` on demand, plus the matching
remove / run-now argv. It NEVER shells out, installs a launchd agent, writes a plist, or starts a
second scheduler — OVT builds no bespoke scheduler/cron/launchd path of its own (§13 M3 invariant).
The operator (or an agent, or the M3 disposable-home integration test) runs the printed command
through the local-jobs skill, which is the sole config-writer and launchd owner.

Key design point (why config travels via ``--env``, not ``--arg``): local-jobs' generic ``add-job``
passthrough drops the VALUE after ``--arg`` when that value itself begins with ``--`` (it treats a
``--``-prefixed token as the next flag). So the scheduled tick's configuration (trigger, bounded
per-source limit) is passed as ``--env OVT_CURATE_*=...`` — values with no leading dashes — and
:meth:`OperatorVoiceService.curate` reads those env vars as its defaults. Program args are limited
to non-``--`` tokens (``-m``, a module path, ``curate``), which pass through ``--arg`` safely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from operator_voice.runtime.paths import default_paths

SCHEDULER_VERSION = "scheduler/v2"

# One stable instance id → exactly one local-jobs command instance (single com.<label_root>.command
# .operator-voice-curate; the operator's ~/.local-jobs/config.yml owns label_root, e.g.
# com.kleinperkins). Reusing this id with ``add-job`` is rejected once registered — enrollment uses
# ``update-job`` to refresh program/env in place.
SCHEDULE_JOB_ID = "operator-voice-curate"
DEFAULT_INTERVAL_SECONDS = 86400  # compatibility argument only; the host owns the daily timer
MIN_INTERVAL_SECONDS = 60  # local-jobs fails closed below this
DISPLAY_NAME = "Operator Voice — curate on demand"
DESCRIPTION = (
    "Local curation on demand. The daily connected-host cycle owns recurring refresh. "
    "No independent timer; encrypted publication uses the existing opted-in backend."
)


def resolve_runtime_pythonpath() -> str:
    """Stable ``runtime/current`` path for launchd — matches ``install.sh`` wrapper ``PYTHONPATH``.

    OVT installs the package as an immutable runtime slot, not into the venv, so a scheduled tick
    must carry this explicitly; launchd jobs do not inherit the ``operator-voice`` wrapper."""
    return str(default_paths().data_dir / "runtime" / "current")


def resolve_curation_python() -> str:
    """Stable launchd interpreter — always the installed OVT venv, never ``sys.executable``.

    ``setup()``, ``repair``, and ``install.sh`` may run from an AWA worktree or dev checkout whose
    ``sys.executable`` is ephemeral; baking that into local-jobs breaks when the worktree is removed.
    Matches ``install.sh``'s ``$VENV/bin/python`` and the ``operator-voice`` wrapper."""
    return str(default_paths().data_dir / "venv" / "bin" / "python")


def build_program_and_args() -> tuple[str, list[str]]:
    """The absolute interpreter + argv for one scheduled tick.

    Uses :func:`resolve_curation_python` with ``-m operator_voice.interfaces.cli curate`` (never a
    bare ``operator-voice`` on ``$PATH``) because a launchd job runs with a minimal environment.
    Every token is dash-free or single-dash, so it survives the local-jobs ``--arg`` passthrough."""
    return resolve_curation_python(), ["-m", "operator_voice.interfaces.cli", "curate"]


def build_schedule_env(*, per_source_limit: Optional[int] = None) -> dict[str, str]:
    """Env vars the single local-jobs instance must pass — trigger, optional limit, and runtime path."""
    env = {
        "OVT_CURATE_TRIGGER": "manual",
        "PYTHONPATH": resolve_runtime_pythonpath(),
    }
    if per_source_limit is not None:
        env["OVT_CURATE_PER_SOURCE_LIMIT"] = str(int(per_source_limit))
    return env


@dataclass(frozen=True, slots=True)
class SchedulePlan:
    job_id: str
    interval_seconds: int
    program: str
    program_args: list[str]
    env: dict[str, str]
    add_argv: list[str]
    update_argv: list[str]
    remove_argv: list[str]
    run_now_argv: list[str]
    warnings: list[str] = field(default_factory=list)


def build_add_job_argv(
    *,
    program: str,
    program_args: list[str],
    env: dict[str, str],
    job_id: str = SCHEDULE_JOB_ID,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    enabled: bool = True,
    dry_run: bool = False,
) -> list[str]:
    if interval_seconds < MIN_INTERVAL_SECONDS:
        raise ValueError(f"interval_seconds must be >= {MIN_INTERVAL_SECONDS} (local-jobs fails closed below this)")
    argv = [
        "add-job", "--type", "command",
        "--id", job_id,
        "--program", program,
        "--execution-mode", "on_demand",
    ]
    for arg in program_args:
        argv += ["--arg", arg]
    for key, value in env.items():
        argv += ["--env", f"{key}={value}"]
    argv += [
        "--display-name", DISPLAY_NAME,
        "--description", DESCRIPTION,
        "--enabled", "true" if enabled else "false",
    ]
    if dry_run:
        argv.append("--dry-run")
    return argv


def build_repair_job_argv(
    *,
    program: str,
    program_args: list[str],
    env: dict[str, str],
    job_id: str = SCHEDULE_JOB_ID,
    dry_run: bool = False,
) -> list[str]:
    """Minimal ``update-job`` argv for install/repair/setup refresh.

    Patches ``program``, ``args``, ``env`` and execution mode, retiring the old timer.
    Operator choices such as ``enabled`` and ``OVT_CURATE_PER_SOURCE_LIMIT`` are preserved."""
    argv = [
        "update-job", "--type", "command",
        "--id", job_id,
        "--program", program,
        "--execution-mode", "on_demand",
    ]
    for arg in program_args:
        argv += ["--arg", arg]
    for key, value in env.items():
        argv += ["--env", f"{key}={value}"]
    if dry_run:
        argv.append("--dry-run")
    return argv


def merge_repair_env(
    existing: Optional[dict[str, str]],
    *,
    required: dict[str, str],
    per_source_limit: Optional[int] = None,
) -> dict[str, str]:
    """Merge required launchd env keys into an existing job env without dropping operator keys."""
    merged = dict(existing or {})
    for key in ("PYTHONPATH", "OVT_CURATE_TRIGGER"):
        if key in required:
            merged[key] = required[key]
    if per_source_limit is not None:
        merged["OVT_CURATE_PER_SOURCE_LIMIT"] = str(int(per_source_limit))
    return merged


def build_update_job_argv(
    *,
    program: str,
    program_args: list[str],
    env: dict[str, str],
    job_id: str = SCHEDULE_JOB_ID,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    enabled: bool = True,
    dry_run: bool = False,
) -> list[str]:
    if interval_seconds < MIN_INTERVAL_SECONDS:
        raise ValueError(f"interval_seconds must be >= {MIN_INTERVAL_SECONDS} (local-jobs fails closed below this)")
    argv = [
        "update-job", "--type", "command",
        "--id", job_id,
        "--program", program,
        "--execution-mode", "on_demand",
    ]
    for arg in program_args:
        argv += ["--arg", arg]
    for key, value in env.items():
        argv += ["--env", f"{key}={value}"]
    argv += [
        "--display-name", DISPLAY_NAME,
        "--description", DESCRIPTION,
        "--enabled", "true" if enabled else "false",
    ]
    if dry_run:
        argv.append("--dry-run")
    return argv


def build_delete_job_argv(*, job_id: str = SCHEDULE_JOB_ID) -> list[str]:
    return ["delete-job", "--id", job_id, "--confirm"]


def build_run_now_argv(*, job_id: str = SCHEDULE_JOB_ID, dry_run: bool = True) -> list[str]:
    argv = ["run-job", "--id", job_id]
    if dry_run:
        argv.append("--dry-run")
    return argv


def plan_schedule(
    *, interval_seconds: int = DEFAULT_INTERVAL_SECONDS, per_source_limit: Optional[int] = None,
    job_id: str = SCHEDULE_JOB_ID,
) -> SchedulePlan:
    """Produce the full, deterministic local-jobs registration plan for the single curation
    instance. Pure — no shell, no filesystem, no launchd."""
    program, program_args = build_program_and_args()
    env = build_schedule_env(per_source_limit=per_source_limit)
    warnings: list[str] = ["The passive timer is retired; interval_seconds is ignored. The host owns the daily cycle."]
    effective_interval = interval_seconds
    if interval_seconds < MIN_INTERVAL_SECONDS:
        effective_interval = MIN_INTERVAL_SECONDS
        warnings.append(
            f"requested interval_seconds {interval_seconds} is below the local-jobs minimum "
            f"{MIN_INTERVAL_SECONDS}; the printed command uses {MIN_INTERVAL_SECONDS}"
        )
    return SchedulePlan(
        job_id=job_id,
        interval_seconds=0,
        program=program,
        program_args=program_args,
        env=env,
        add_argv=build_add_job_argv(
            program=program, program_args=program_args, env=env, job_id=job_id, interval_seconds=effective_interval,
        ),
        update_argv=build_update_job_argv(
            program=program, program_args=program_args, env=env, job_id=job_id, interval_seconds=effective_interval,
        ),
        remove_argv=build_delete_job_argv(job_id=job_id),
        run_now_argv=build_run_now_argv(job_id=job_id),
        warnings=warnings,
    )


def _shell_quote(token: str) -> str:
    if token and all(c.isalnum() or c in "-_=/.:" for c in token):
        return token
    return "'" + token.replace("'", "'\\''") + "'"


def render_command(argv: list[str], *, local_jobs_sh: str = "local-jobs.sh") -> str:
    """Render a copy-pasteable command line. ``local_jobs_sh`` is the operator's resolved
    ``scripts/local-jobs.sh`` path (the skill runtime); left as the bare name when unknown."""
    return " ".join([_shell_quote(local_jobs_sh)] + [_shell_quote(a) for a in argv])


__all__ = [
    "SCHEDULER_VERSION",
    "SCHEDULE_JOB_ID",
    "DEFAULT_INTERVAL_SECONDS",
    "MIN_INTERVAL_SECONDS",
    "SchedulePlan",
    "build_program_and_args",
    "build_schedule_env",
    "resolve_curation_python",
    "resolve_runtime_pythonpath",
    "build_add_job_argv",
    "build_repair_job_argv",
    "merge_repair_env",
    "build_update_job_argv",
    "build_delete_job_argv",
    "build_run_now_argv",
    "plan_schedule",
    "render_command",
]
