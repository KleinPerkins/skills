"""Engine and disk-discovery doctor for the save-game capability.

Unlike ``install.sh --doctor``, this module verifies engine prerequisites and
runtime smoke paths as well as the installed client links. It cannot prove that
a separately running client has discovered or invoked the skill.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from . import adapters


PASS = "pass"
FAIL = "fail"
UNKNOWN = "unknown"

EXPECTED_SCHEMA_FILES = (
    "archive-manifest.v1.schema.json",
    "checkpoint.v1.schema.json",
    "current.v1.schema.json",
    "flush-receipt.v1.schema.json",
    "journal-aborted.v1.schema.json",
    "journal-finalized.v1.schema.json",
    "journal-prepared.v1.schema.json",
    "promotion-candidate.v1.schema.json",
    "reconcile-receipt.v1.schema.json",
    "reconcile-observation.v1.schema.json",
    "registration.v1.schema.json",
    "tombstone.v1.schema.json",
)

LIVE_ACCEPTANCE_STATEMENT = (
    "True cross-client acceptance is not proved by this doctor. An operator must "
    "invoke save-game inside a running Cursor, Claude, or Codex session and confirm "
    "that the client discovered it; this report proves only disk-level prerequisites."
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


def _default_skill_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _python_env(skill_dir: Path, base: Optional[dict] = None) -> dict:
    env = dict(os.environ if base is None else base)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(skill_dir)
        if not existing
        else str(skill_dir) + os.pathsep + existing
    )
    return env


def _brief_failure(completed: subprocess.CompletedProcess) -> str:
    text = (completed.stderr or completed.stdout or "").strip()
    if not text:
        return f"exit code {completed.returncode}"
    return f"exit code {completed.returncode}: {text[:300]}"


def check_schema_files(skill_dir: Optional[Path] = None) -> List[CheckResult]:
    """Check the closed twelve-schema inventory, JSON parsing, and base shape."""

    root = _default_skill_dir() if skill_dir is None else Path(skill_dir)
    schema_dir = root / "engine" / "schemas"
    results: List[CheckResult] = []
    for filename in EXPECTED_SCHEMA_FILES:
        path = schema_dir / filename
        name = f"schema:{filename}"
        if not path.is_file():
            results.append(CheckResult(name, FAIL, f"missing {path}"))
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            results.append(CheckResult(name, FAIL, f"invalid JSON: {exc}"))
            continue
        if not isinstance(document, dict):
            results.append(CheckResult(name, FAIL, "schema JSON is not an object"))
            continue
        if (
            document.get("type") != "object"
            or document.get("additionalProperties") is not False
            or not isinstance(document.get("properties"), dict)
        ):
            results.append(
                CheckResult(
                    name,
                    FAIL,
                    "not a closed object schema (type/properties/additionalProperties)",
                )
            )
            continue
        results.append(CheckResult(name, PASS, "valid JSON; closed object schema"))
    return results


def check_module_imports(
    skill_dir: Optional[Path] = None,
    python_executable: Optional[str] = None,
) -> List[CheckResult]:
    """Import every top-level engine Python module in a fresh interpreter."""

    root = _default_skill_dir() if skill_dir is None else Path(skill_dir)
    engine_dir = root / "engine"
    python = python_executable or sys.executable
    module_paths = sorted(engine_dir.glob("*.py"))
    if not module_paths:
        return [CheckResult("engine-imports", FAIL, f"no modules found in {engine_dir}")]

    env = _python_env(root)
    results: List[CheckResult] = []
    for path in module_paths:
        module_name = "engine" if path.stem == "__init__" else f"engine.{path.stem}"
        try:
            completed = subprocess.run(
                [
                    python,
                    "-c",
                    (
                        "import importlib; "
                        f"importlib.import_module({module_name!r})"
                    ),
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            results.append(
                CheckResult(f"import:{module_name}", FAIL, f"could not import: {exc}")
            )
            continue
        if completed.returncode == 0:
            results.append(CheckResult(f"import:{module_name}", PASS, "imported cleanly"))
        else:
            results.append(
                CheckResult(
                    f"import:{module_name}", FAIL, _brief_failure(completed)
                )
            )
    return results


def check_client_link(
    capability: adapters.ClientCapability,
    *,
    skill_dir: Optional[Path] = None,
    home: Optional[Path] = None,
) -> CheckResult:
    """Verify one discovery path is an owned symlink to this skill directory."""

    root = _default_skill_dir() if skill_dir is None else Path(skill_dir)
    link = capability.resolved_discovery_path(home)
    name = f"client-link:{capability.client_id}"
    try:
        root_real = root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        return CheckResult(name, UNKNOWN, f"skill directory cannot be resolved: {exc}")

    try:
        link_stat = link.lstat()
    except FileNotFoundError:
        return CheckResult(name, FAIL, f"missing discovery link {link}")
    except (OSError, RuntimeError) as exc:
        return CheckResult(name, UNKNOWN, f"cannot inspect {link}: {exc}")

    if not stat.S_ISLNK(link_stat.st_mode):
        return CheckResult(name, FAIL, f"{link} exists but is not a symlink")

    if hasattr(os, "getuid") and link_stat.st_uid != os.getuid():
        return CheckResult(
            name,
            FAIL,
            f"{link} is owned by uid {link_stat.st_uid}, expected {os.getuid()}",
        )

    try:
        target_real = link.resolve(strict=True)
    except FileNotFoundError:
        return CheckResult(name, FAIL, f"{link} is a broken symlink")
    except (OSError, RuntimeError) as exc:
        return CheckResult(name, UNKNOWN, f"cannot resolve {link}: {exc}")

    if target_real != root_real:
        return CheckResult(
            name,
            FAIL,
            f"{link} resolves to {target_real}, expected {root_real}",
        )
    return CheckResult(name, PASS, f"{link} is an owned symlink to {root_real}")


def check_client_links(
    *,
    skill_dir: Optional[Path] = None,
    home: Optional[Path] = None,
    capabilities: Optional[Iterable[adapters.ClientCapability]] = None,
) -> List[CheckResult]:
    selected = adapters.list_clients() if capabilities is None else tuple(capabilities)
    return [
        check_client_link(capability, skill_dir=skill_dir, home=home)
        for capability in selected
    ]


def _runtime_argvs(root: Path, task_id: str) -> Sequence[tuple[str, List[str]]]:
    return (
        (
            "flush",
            [
                "--root",
                str(root),
                "flush",
                "--task-id",
                task_id,
                "--objective",
                "Verify the engine doctor smoke path.",
            ],
        ),
        ("index", ["--root", str(root), "index", "--task-id", task_id]),
        ("compact-check", ["--root", str(root), "compact-check"]),
        (
            "reconcile",
            ["--root", str(root), "reconcile", "--task-id", task_id],
        ),
    )


def check_runtime_commands(
    skill_dir: Optional[Path] = None,
    python_executable: Optional[str] = None,
) -> List[CheckResult]:
    """Run both public entrypoints through all four commands in temporary state."""

    root = _default_skill_dir() if skill_dir is None else Path(skill_dir)
    python = python_executable or sys.executable
    script = root / "scripts" / "save-game.sh"
    entrypoints = (
        ("script", [str(script)]),
        ("module", [python, "-m", "engine.cli"]),
    )
    results: List[CheckResult] = []

    with tempfile.TemporaryDirectory(prefix="save-game-doctor-") as temp:
        temp_root = Path(temp)
        target_root = temp_root / "root"
        target_root.mkdir()
        for entrypoint_name, prefix in entrypoints:
            state = temp_root / f"state-{entrypoint_name}"
            config = temp_root / f"config-{entrypoint_name}"
            state.mkdir()
            config.mkdir()
            env = _python_env(root)
            env["XDG_STATE_HOME"] = str(state)
            env["XDG_CONFIG_HOME"] = str(config)
            task_id = f"doctor-{entrypoint_name}"
            for command_name, argv in _runtime_argvs(target_root, task_id):
                check_name = f"runtime:{entrypoint_name}:{command_name}"
                try:
                    completed = subprocess.run(
                        [*prefix, *argv],
                        cwd=root,
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=30,
                        check=False,
                    )
                except (OSError, subprocess.TimeoutExpired) as exc:
                    results.append(
                        CheckResult(check_name, FAIL, f"could not run: {exc}")
                    )
                    continue
                if completed.returncode != 0:
                    results.append(
                        CheckResult(check_name, FAIL, _brief_failure(completed))
                    )
                    continue
                try:
                    output = json.loads(completed.stdout)
                except json.JSONDecodeError as exc:
                    results.append(
                        CheckResult(check_name, FAIL, f"non-JSON output: {exc}")
                    )
                    continue
                if not isinstance(output, dict):
                    results.append(
                        CheckResult(check_name, FAIL, "output JSON is not an object")
                    )
                    continue
                results.append(CheckResult(check_name, PASS, "completed without crashing"))
    return results


def _acceptance_checks() -> List[CheckResult]:
    results = []
    for capability in adapters.list_clients():
        detail = (
            adapters.codex_acceptance_status()
            if capability.client_id == "codex"
            else capability.acceptance_status
        )
        results.append(
            CheckResult(f"live-acceptance:{capability.client_id}", UNKNOWN, detail)
        )
    return results


def run_doctor(
    *,
    skill_dir: Optional[Path] = None,
    home: Optional[Path] = None,
    python_executable: Optional[str] = None,
    include_runtime: bool = True,
) -> dict:
    """Run the doctor and return a stable, JSON-serializable report."""

    root = _default_skill_dir() if skill_dir is None else Path(skill_dir)
    checks: List[CheckResult] = []
    checks.extend(check_schema_files(root))
    checks.extend(check_module_imports(root, python_executable))
    if include_runtime:
        checks.extend(check_runtime_commands(root, python_executable))
    else:
        checks.append(
            CheckResult(
                "runtime-smoke",
                UNKNOWN,
                "runtime smoke checks skipped by explicit request",
            )
        )
    checks.extend(check_client_links(skill_dir=root, home=home))
    checks.extend(_acceptance_checks())

    prerequisite_checks = [
        result
        for result in checks
        if not result.name.startswith("live-acceptance:")
    ]
    if any(result.status == FAIL for result in prerequisite_checks):
        prerequisite_status = FAIL
    elif any(result.status == UNKNOWN for result in prerequisite_checks):
        prerequisite_status = UNKNOWN
    else:
        prerequisite_status = PASS

    return {
        "disk_prerequisite_status": prerequisite_status,
        "checks": [result.to_dict() for result in checks],
        "live_cross_client_acceptance": {
            "status": UNKNOWN,
            "statement": LIVE_ACCEPTANCE_STATEMENT,
        },
    }


def render_report(report: dict) -> str:
    lines = [
        "save-game engine doctor",
        f"disk prerequisites: {report['disk_prerequisite_status'].upper()}",
    ]
    for check in report["checks"]:
        lines.append(
            f"[{check['status'].upper():7}] {check['name']}: {check['detail']}"
        )
    acceptance = report["live_cross_client_acceptance"]
    lines.extend(
        [
            f"live cross-client acceptance: {acceptance['status'].upper()}",
            acceptance["statement"],
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m engine.doctor",
        description="Check save-game engine and disk-level client prerequisites.",
    )
    parser.add_argument("--skill-dir", type=Path, default=_default_skill_dir())
    parser.add_argument("--home", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--skip-runtime",
        action="store_true",
        help="Skip throwaway flush/index/compact-check/reconcile smoke runs.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_doctor(
        skill_dir=args.skill_dir,
        home=args.home,
        include_runtime=not args.skip_runtime,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_report(report))

    status_value = report["disk_prerequisite_status"]
    if status_value == FAIL:
        return 1
    if status_value == UNKNOWN:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
