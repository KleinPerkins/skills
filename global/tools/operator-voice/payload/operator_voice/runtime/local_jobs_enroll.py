"""Best-effort registration/migration of the on-demand local curation instance.

The pure planner in ``scheduler.py`` still renders argv only; this module is the optional
enrollment step ``setup()`` uses when the operator's local-jobs skill is installed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from operator_voice.runtime import scheduler
from operator_voice.runtime.paths import default_paths

_DISABLE_ENV = "OVT_DISABLE_PASSIVE_CURATION_ENROLL"


def _python_has_yaml(python: str) -> bool:
    try:
        proc = subprocess.run(
            [python, "-c", "import yaml"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _repo_venv_python_candidates(start: Path) -> list[Path]:
    """Mirror ``local-jobs.sh``'s ``_find_repo_venv_python`` search order."""
    candidates: list[Path] = []
    try:
        proc = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            candidates.append(Path(proc.stdout.strip()) / "_ops" / ".venv" / "bin" / "python3")
    except (OSError, subprocess.TimeoutExpired):
        pass

    parts = start.parts
    if "quiver" in parts:
        root = Path(*parts[: parts.index("quiver")])
        candidates.append(root / "_ops" / ".venv" / "bin" / "python3")

    current = start
    while True:
        candidates.append(current / "_ops" / ".venv" / "bin" / "python3")
        if current == current.parent:
            break
        current = current.parent
    return candidates


_PATH_PYTHON_PREFIXES = (
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
    Path("/usr/bin"),
)


def _path_python_candidates() -> list[str]:
    """Interpreters discoverable on PATH and common install prefixes."""
    names = ["python3", "python"]
    for minor in range(14, 8, -1):
        names.append(f"python3.{minor}")
    found: list[str] = []
    seen: set[str] = set()

    def _add(candidate: Optional[str | Path]) -> None:
        if candidate is None:
            return
        resolved = str(Path(candidate))
        if resolved not in seen:
            seen.add(resolved)
            found.append(resolved)

    for name in names:
        _add(shutil.which(name))
        for prefix in _PATH_PYTHON_PREFIXES:
            try:
                candidate = prefix / name
                if candidate.is_file():
                    _add(candidate)
            except OSError:
                continue
    return found


def _resolve_uv_python_with_yaml() -> Optional[str]:
    """Install PyYAML into the durable OVT runtime venv when uv is available."""
    venv_python = default_paths().data_dir / "venv" / "bin" / "python"
    try:
        if not venv_python.is_file():
            return None
    except OSError:
        return None

    resolved = str(venv_python)
    if _python_has_yaml(resolved):
        return resolved
    if not shutil.which("uv"):
        return None
    try:
        proc = subprocess.run(
            ["uv", "pip", "install", "--python", resolved, "pyyaml"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return resolved if _python_has_yaml(resolved) else None


def resolve_local_jobs_python(*, local_jobs_sh: Optional[str] = None) -> Optional[str]:
    """Return an interpreter ``local-jobs.sh`` can use (must import PyYAML).

    Honors ``LOCAL_JOBS_PYTHON`` when valid, then common repo/home venv fallbacks, then PATH
    and well-known system prefixes (e.g. Homebrew ``python3``), then ``uv pip install pyyaml``
    into the OVT runtime venv when ``uv`` is on PATH.
    """
    seen: set[str] = set()
    candidates: list[str] = []

    def _add(candidate: Optional[str | Path]) -> None:
        if candidate is None:
            return
        path = str(Path(candidate))
        if path not in seen:
            seen.add(path)
            candidates.append(path)

    _add(os.environ.get("LOCAL_JOBS_PYTHON"))
    _add(sys.executable)

    if local_jobs_sh:
        try:
            wrapper = Path(local_jobs_sh).resolve()
            skill_dir = wrapper.parent.parent if wrapper.parent.name == "scripts" else wrapper.parent
            for venv_py in _repo_venv_python_candidates(skill_dir):
                _add(venv_py)
        except OSError:
            pass

    _add(Path.home() / "dev" / "_ops" / ".venv" / "bin" / "python3")
    _add(default_paths().data_dir / "venv" / "bin" / "python")
    for path_python in _path_python_candidates():
        _add(path_python)

    for candidate in candidates:
        try:
            if Path(candidate).is_file() and _python_has_yaml(candidate):
                return candidate
        except OSError:
            continue

    return _resolve_uv_python_with_yaml()


def _local_jobs_subprocess_env(*, local_jobs_sh: str) -> tuple[Optional[dict[str, str]], Optional[str]]:
    python = resolve_local_jobs_python(local_jobs_sh=local_jobs_sh)
    if python is None:
        return None, (
            "PyYAML is required for local-jobs; install PyYAML for python3, set LOCAL_JOBS_PYTHON "
            "to an interpreter that has it, or install uv so setup can resolve one automatically"
        )
    env = os.environ.copy()
    env["LOCAL_JOBS_PYTHON"] = python
    return env, None


def _run_local_jobs(local_jobs_sh: str, argv: list[str], *, timeout: int) -> subprocess.CompletedProcess[str] | dict[str, Any]:
    env, err = _local_jobs_subprocess_env(local_jobs_sh=local_jobs_sh)
    if env is None:
        return {"status": "failed", "local_jobs_sh": local_jobs_sh, "detail": err}
    try:
        return subprocess.run(
            [local_jobs_sh, *argv],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "failed", "local_jobs_sh": local_jobs_sh, "detail": str(exc)}


def resolve_local_jobs_sh() -> Optional[str]:
    """Return the operator's ``local-jobs.sh`` path when the skill is installed."""
    candidates = [
        Path.home() / ".claude/skills/local-jobs/scripts/local-jobs.sh",
        Path.home() / ".cursor/skills/local-jobs/scripts/local-jobs.sh",
        Path.home() / ".codex/skills/local-jobs/scripts/local-jobs.sh",
    ]
    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue
    return None


def _view_jobs_payload(*, local_jobs_sh: str) -> Optional[dict[str, Any]]:
    proc = _run_local_jobs(local_jobs_sh, ["view-jobs", "--json"], timeout=30)
    if isinstance(proc, dict):
        return None
    if proc.returncode != 0:
        return None
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _load_job_entry(*, local_jobs_sh: str, job_id: str) -> Optional[dict[str, Any]]:
    payload = _view_jobs_payload(local_jobs_sh=local_jobs_sh)
    if payload is None:
        return None
    for entry in payload.get("instances") or []:
        if isinstance(entry, dict) and entry.get("id") == job_id:
            return entry
    return None


def _job_registered(*, local_jobs_sh: str, job_id: str) -> bool:
    return _load_job_entry(local_jobs_sh=local_jobs_sh, job_id=job_id) is not None


def _curation_runtime_ready(*, program: str, runtime_pythonpath: str) -> tuple[bool, str]:
    """Mirror ``install.sh``'s ``refresh_curation_schedule`` guard — never write a launchd program
    path that does not exist yet."""
    try:
        if not Path(program).is_file():
            return False, "ovt_venv_not_installed"
    except OSError:
        return False, "ovt_venv_not_installed"
    try:
        if not Path(runtime_pythonpath).is_dir():
            return False, "ovt_runtime_not_installed"
    except OSError:
        return False, "ovt_runtime_not_installed"
    return True, ""


def ensure_curation_schedule(
    *,
    interval_seconds: int = scheduler.DEFAULT_INTERVAL_SECONDS,
    per_source_limit: Optional[int] = None,
    local_jobs_sh: Optional[str] = None,
) -> dict[str, Any]:
    """Register the single on-demand curation local-jobs instance when possible.

    Returns a small status dict suitable for ``setup()`` output. Never raises — enrollment is
    best-effort and must not block first-run setup.
    """
    if os.environ.get(_DISABLE_ENV) == "1":
        return {
            "status": "skipped",
            "reason": "disabled_by_env",
            "env": _DISABLE_ENV,
        }

    ljs = local_jobs_sh or resolve_local_jobs_sh()
    if ljs is None:
        return {
            "status": "skipped",
            "reason": "local_jobs_not_installed",
            "note": "Run operator-voice schedule-plan and register the printed add_command when ready.",
        }

    plan = scheduler.plan_schedule(interval_seconds=interval_seconds, per_source_limit=per_source_limit)
    ready, skip_reason = _curation_runtime_ready(
        program=plan.program,
        runtime_pythonpath=plan.env["PYTHONPATH"],
    )
    if not ready:
        return {
            "status": "skipped",
            "reason": skip_reason,
            "job_id": plan.job_id,
            "note": "Run install.sh (or finish setup after install) before enrolling on-demand curation.",
        }
    existing_entry = _load_job_entry(local_jobs_sh=ljs, job_id=plan.job_id)
    if existing_entry is None:
        enroll_argv = plan.add_argv
        result_status = "registered"
    else:
        repair_env = scheduler.merge_repair_env(
            existing_entry.get("env"),
            required=plan.env,
            per_source_limit=per_source_limit,
        )
        enroll_argv = scheduler.build_repair_job_argv(
            program=plan.program,
            program_args=plan.program_args,
            env=repair_env,
            job_id=plan.job_id,
        )
        result_status = "repaired"

    proc = _run_local_jobs(ljs, enroll_argv, timeout=60)
    if isinstance(proc, dict):
        return {**proc, "job_id": plan.job_id}

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        return {
            "status": "failed",
            "job_id": plan.job_id,
            "local_jobs_sh": ljs,
            "detail": detail,
        }

    return {
        "status": result_status,
        "job_id": plan.job_id,
        "interval_seconds": plan.interval_seconds,
        "execution_mode": "on_demand",
        "local_jobs_sh": ljs,
        "warnings": plan.warnings,
    }


__all__ = ["ensure_curation_schedule", "resolve_local_jobs_python", "resolve_local_jobs_sh"]
