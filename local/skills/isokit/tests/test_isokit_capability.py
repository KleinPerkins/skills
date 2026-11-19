#!/usr/bin/env python3
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


CAPABILITY = Path(__file__).resolve().parents[1]
REPO = CAPABILITY.parents[2]
PIN = "e25dfc82681628dfb5240cddc9f07081042fe348"
PLAYWRIGHT_VERSION = "1.64.1"
PLAYWRIGHT_INTEGRITY = (
    "sha512-BC4s8y6SEVA6Q1rSxZTto8hI1KUI3xXlHGZgvGqP4IqPdI/"
    "a6FX9H29IDNz7vKo9l21b6LfYosScPL6M3xxyDQ=="
)
UPSTREAM_DESCRIPTION = (
    "Draw an interactive isometric figure in React with react-isokit — a line-art "
    "object on a numbered plate whose parts you can press, that produce real output "
    "(text on a screen, a count, a state change) with optional synthesized sound. "
    'Use when someone asks for an isometric illustration, an "iso figure", a 2.5D '
    "product drawing, an interactive hero object, a pressable diagram, a playable "
    "desk object (computer, keypad, timer, synth), or runs /isokit with an idea."
)
LOCAL_DESCRIPTION = (
    "Draws pressable React isometric objects whose controls produce state, output, "
    "or optional sound. Use for interactive 2.5D figures, product heroes, diagrams, "
    "keypads, timers, synths, or /isokit requests."
)
UPSTREAM_LAUNCH = (
    'const launch = async () => { for (const channel of ["chrome", "chromium", '
    "undefined]) { try { return await chromium.launch({ channel, headless: true }) "
    '} catch {} } console.error("No Chrome or Chromium found: npx playwright '
    'install chromium"); process.exit(2) }'
)
SHOOT_BEGIN = (
    "// LOCAL-ADAPTATION-BEGIN: preserve launch diagnostics and approval boundary.\n"
)
SHOOT_END = "// LOCAL-ADAPTATION-END\n"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def simple_yaml(path: Path) -> dict[str, str]:
    values = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.lstrip().startswith("#") or ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        values[key] = value.strip().strip("\"'")
    return values


def upstream_manifest() -> dict[str, str]:
    rows = {}
    raw_paths = []
    for raw in (CAPABILITY / "UPSTREAM-FILES.sha256").read_text(
        encoding="utf-8"
    ).splitlines():
        digest, source_path = raw.split("  ", 1)
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise AssertionError(f"invalid digest for {source_path}")
        if source_path in rows:
            raise AssertionError(f"duplicate source path {source_path}")
        rows[source_path] = digest
        raw_paths.append(source_path)
    if raw_paths != sorted(raw_paths):
        raise AssertionError("upstream manifest is not path-sorted")
    return rows


def local_path(source_path: str) -> Path:
    prefix = "skills/isokit/"
    if source_path.startswith(prefix):
        return CAPABILITY / source_path.removeprefix(prefix)
    return CAPABILITY / source_path


def skill_bytes_as_upstream() -> bytes:
    lines = (CAPABILITY / "SKILL.md").read_text(encoding="utf-8").splitlines(
        keepends=True
    )
    matches = [index for index, line in enumerate(lines) if line.startswith("description:")]
    if len(matches) != 1:
        raise AssertionError("SKILL.md must contain exactly one description")
    index = matches[0]
    newline = "\n" if lines[index].endswith("\n") else ""
    lines[index] = f"description: {UPSTREAM_DESCRIPTION}{newline}"
    return "".join(lines).encode("utf-8")


def shoot_bytes_as_upstream() -> bytes:
    text = (CAPABILITY / "scripts/shoot.mjs").read_text(encoding="utf-8")
    if text.count(SHOOT_BEGIN) != 1 or text.count(SHOOT_END) != 1:
        raise AssertionError("shoot.mjs must contain one bounded local adaptation")
    before, adapted = text.split(SHOOT_BEGIN, 1)
    _, after = adapted.split(SHOOT_END, 1)
    return f"{before}{UPSTREAM_LAUNCH}\n{after}".encode()


class TestPinnedSnapshot(unittest.TestCase):
    def test_complete_source_set_and_byte_parity(self):
        rows = upstream_manifest()
        self.assertEqual(len(rows), 115)
        self.assertIn("LICENSE", rows)
        self.assertIn("NOTICE.md", rows)
        self.assertIn("skills/isokit/SKILL.md", rows)
        self.assertIn("skills/isokit/scripts/shoot.mjs", rows)

        for source_path, expected in rows.items():
            with self.subTest(source_path=source_path):
                target = local_path(source_path)
                self.assertTrue(target.is_file(), f"missing {target}")
                if source_path == "skills/isokit/SKILL.md":
                    actual = sha256_bytes(skill_bytes_as_upstream())
                elif source_path == "skills/isokit/scripts/shoot.mjs":
                    actual = sha256_bytes(shoot_bytes_as_upstream())
                else:
                    actual = sha256(target)
                self.assertEqual(actual, expected)

        expected_figures = {
            source_path
            for source_path in rows
            if source_path.startswith("examples/demo/src/figures/")
        }
        actual_figures = {
            path.relative_to(CAPABILITY).as_posix()
            for path in (CAPABILITY / "examples/demo/src/figures").rglob("*")
            if path.is_file()
        }
        self.assertEqual(len(expected_figures), 106)
        self.assertEqual(actual_figures, expected_figures)

        expected_skill_files = {
            source_path.removeprefix("skills/isokit/")
            for source_path in rows
            if source_path.startswith("skills/isokit/")
        }
        actual_skill_files = {
            path.relative_to(CAPABILITY).as_posix()
            for subtree in ("references", "scripts")
            for path in (CAPABILITY / subtree).rglob("*")
            if path.is_file()
        }
        actual_skill_files.add("SKILL.md")
        self.assertEqual(actual_skill_files, expected_skill_files)

    def test_metadata_description_dependency_and_diagnostics(self):
        meta = simple_yaml(CAPABILITY / "meta.yml")
        self.assertEqual(meta["id"], "isokit")
        self.assertEqual(meta["kind"], "skill")
        self.assertEqual(meta["flavor"], "2")
        self.assertEqual(meta["scope"], "local")
        self.assertEqual(meta["expose"], "cursor claude codex")
        self.assertEqual(meta["runtime_contract"], "installer-doctor/v1")
        self.assertEqual(meta["provenance_source"], "github.com/aadilghani1/isokit")
        self.assertEqual(meta["provenance_ref"], PIN)
        self.assertEqual(meta["provenance_trust"], "community")

        skill = simple_yaml(CAPABILITY / "SKILL.md")
        self.assertEqual(skill["description"], LOCAL_DESCRIPTION)
        normalized = " ".join(skill["description"].split())
        self.assertEqual(len(normalized), 202)
        self.assertLessEqual(len(normalized), 300)
        for term in ("pressable", "isometric", "React", "state", "output", "sound"):
            self.assertIn(term, normalized)

        package = json.loads((CAPABILITY / "package.json").read_text(encoding="utf-8"))
        lock = json.loads((CAPABILITY / "package-lock.json").read_text(encoding="utf-8"))
        self.assertTrue(package["private"])
        self.assertNotIn("scripts", package)
        self.assertEqual(package["dependencies"], {"playwright-core": PLAYWRIGHT_VERSION})
        self.assertEqual(lock["lockfileVersion"], 3)
        self.assertEqual(
            lock["packages"][""]["dependencies"],
            {"playwright-core": PLAYWRIGHT_VERSION},
        )
        resolved = lock["packages"]["node_modules/playwright-core"]
        self.assertEqual(resolved["version"], PLAYWRIGHT_VERSION)
        self.assertEqual(resolved["integrity"], PLAYWRIGHT_INTEGRITY)

        shoot = (CAPABILITY / "scripts/shoot.mjs").read_text(encoding="utf-8")
        self.assertIn("failures.push", shoot)
        self.assertIn("error.message", shoot)
        self.assertIn("must not be downloaded without explicit operator approval", shoot)
        self.assertNotIn("npx playwright install chromium", shoot)
        adaptations = (CAPABILITY / "LOCAL-ADAPTATIONS.md").read_text(encoding="utf-8")
        provenance = (CAPABILITY / "PROVENANCE.md").read_text(encoding="utf-8")
        self.assertIn("scripts/shoot.mjs", adaptations)
        self.assertIn("scripts/shoot.mjs", provenance)


class TestInstaller(unittest.TestCase):
    # The governed stdlib-shell image has no Node. Test the shell boundary with
    # an explicit runtime double there; TestNodeIntegration repeats these checks
    # against actual module imports on developer hosts with Node installed.
    use_real_node = False

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.capability = self.root / "isokit"
        shutil.copytree(
            CAPABILITY,
            self.capability,
            ignore=shutil.ignore_patterns("node_modules", "__pycache__"),
        )
        self.home = self.root / "home"
        self.home.mkdir()
        self.fake_bin = self.root / "bin"
        self.fake_bin.mkdir()
        self.npm_log = self.root / "npm.log"
        npm = self.fake_bin / "npm"
        npm.write_text(
            f"""#!/usr/bin/env bash
set -euo pipefail
printf 'ignore_scripts=%s skip_browser=%s args=%s\\n' \\
  "${{npm_config_ignore_scripts:-}}" "${{PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD:-}}" "$*" \\
  >> "$ISOKIT_TEST_NPM_LOG"
if [ "${{PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD:-}}" != 1 ]; then
  mkdir -p "$HOME/.cache/ms-playwright"
fi
if [ "${{npm_config_ignore_scripts:-}}" != true ] ||
  [[ " $* " != *" --ignore-scripts "* ]]; then
  : > "$ISOKIT_TEST_LIFECYCLE_MARKER"
fi
[ "${{ISOKIT_TEST_NPM_MODE:-success}}" != fail ] || exit 42
rm -rf node_modules/playwright-core
mkdir -p node_modules/playwright-core
cat > node_modules/playwright-core/package.json <<'JSON'
{{"name":"playwright-core","version":"{PLAYWRIGHT_VERSION}","type":"module","exports":"./index.js"}}
JSON
cat > node_modules/playwright-core/index.js <<'JS'
export const chromium = {{ launch: async () => ({{ close: async () => {{}} }}) }};
JS
: > node_modules/playwright-core/test-runtime-ready
""",
            encoding="utf-8",
        )
        npm.chmod(0o755)
        if not self.use_real_node:
            node = self.fake_bin / "node"
            node.write_text(
                "#!/bin/sh\n"
                'test -f node_modules/playwright-core/test-runtime-ready\n',
                encoding="utf-8",
            )
            node.chmod(0o755)
        self.lifecycle_marker = self.root / "lifecycle-ran"
        self.env = {
            **os.environ,
            "BASH_ENV": "/dev/null",
            "HOME": str(self.home),
            "ISOKIT_TEST_LIFECYCLE_MARKER": str(self.lifecycle_marker),
            "ISOKIT_TEST_NPM_LOG": str(self.npm_log),
            "ISOKIT_TEST_NPM_MODE": "success",
            "PATH": f"{self.fake_bin}{os.pathsep}{os.environ['PATH']}",
        }

    def tearDown(self):
        self.temp.cleanup()

    def run_installer(
        self, *args: str, npm_mode: str = "success"
    ) -> subprocess.CompletedProcess:
        env = {**self.env, "ISOKIT_TEST_NPM_MODE": npm_mode}
        return subprocess.run(
            ["bash", str(self.capability / "install.sh"), *args],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def link(self, tool: str) -> Path:
        return self.home / f".{tool}" / "skills" / "isokit"

    def create_links(self):
        for tool in ("cursor", "claude", "codex"):
            link = self.link(tool)
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(self.capability)

    def assert_links(self):
        for tool in ("cursor", "claude", "codex"):
            link = self.link(tool)
            self.assertTrue(link.is_symlink())
            self.assertEqual(Path(os.readlink(link)).resolve(), self.capability.resolve())

    def assert_no_links(self, *except_tools: str):
        for tool in ("cursor", "claude", "codex"):
            if tool in except_tools:
                continue
            link = self.link(tool)
            self.assertFalse(link.exists() or link.is_symlink(), str(link))

    def assert_no_browser_or_lifecycle_side_effects(self):
        self.assertFalse(self.lifecycle_marker.exists())
        self.assertFalse((self.home / ".cache/ms-playwright").exists())
        self.assertFalse((self.home / "Library/Caches/ms-playwright").exists())
        self.assertFalse(
            (self.capability / "node_modules/playwright-core/.local-browsers").exists()
        )

    def write_runtime_module(self, source: str):
        runtime = self.capability / "node_modules/playwright-core"
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "package.json").write_text(
            json.dumps(
                {
                    "name": "playwright-core",
                    "version": PLAYWRIGHT_VERSION,
                    "type": "module",
                    "exports": "./index.js",
                }
            ),
            encoding="utf-8",
        )
        (runtime / "index.js").write_text(source, encoding="utf-8")

    def make_partial_runtime(self):
        runtime = self.capability / "node_modules/playwright-core"
        runtime.mkdir(parents=True)
        (runtime / "package.json").write_text(
            json.dumps({"name": "playwright-core", "version": PLAYWRIGHT_VERSION}),
            encoding="utf-8",
        )
        (runtime / "cli.js").touch()

    def make_bootstrap_projection(self) -> tuple[Path, Path]:
        projection = self.root / "repo"
        (projection / "global").mkdir(parents=True)
        (projection / "local/skills").mkdir(parents=True)
        (projection / "scripts").mkdir(parents=True)
        shutil.copy2(REPO / "bootstrap.sh", projection / "bootstrap.sh")
        shutil.copy2(
            REPO / "scripts/capability_meta.py",
            projection / "scripts/capability_meta.py",
        )
        projected_capability = projection / "local/skills/isokit"
        shutil.copytree(
            self.capability,
            projected_capability,
            ignore=shutil.ignore_patterns("node_modules", "__pycache__"),
        )
        subprocess.run(
            ["git", "init", "-q", str(projection)],
            check=True,
            capture_output=True,
            text=True,
        )
        return projection, projected_capability

    def test_install_is_idempotent_and_disables_unsafe_npm_behavior(self):
        first = self.run_installer()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assert_links()
        self.assertEqual(
            self.npm_log.read_text(encoding="utf-8"),
            "ignore_scripts=true skip_browser=1 "
            "args=ci --ignore-scripts --no-audit --no-fund\n",
        )
        self.assert_no_browser_or_lifecycle_side_effects()

        second = self.run_installer()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assert_links()
        self.assertEqual(len(self.npm_log.read_text().splitlines()), 1)

        doctor = self.run_installer("--doctor")
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        self.link("codex").unlink()
        failed_doctor = self.run_installer("--doctor")
        self.assertNotEqual(failed_doctor.returncode, 0)

    def test_partial_metadata_and_cli_stub_fails_doctor_and_is_repaired(self):
        self.make_partial_runtime()
        self.create_links()

        doctor = self.run_installer("--doctor")
        self.assertNotEqual(doctor.returncode, 0)
        self.assertIn("cannot import with chromium.launch", doctor.stdout)
        self.assertFalse(self.npm_log.exists())

        repaired = self.run_installer()
        self.assertEqual(repaired.returncode, 0, repaired.stdout + repaired.stderr)
        self.assertEqual(len(self.npm_log.read_text().splitlines()), 1)
        healthy = self.run_installer("--doctor")
        self.assertEqual(healthy.returncode, 0, healthy.stdout + healthy.stderr)
        self.assert_no_browser_or_lifecycle_side_effects()

    def test_forced_npm_failure_propagates_without_browser_download(self):
        failed = self.run_installer(npm_mode="fail")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn(
            "ignore_scripts=true skip_browser=1 "
            "args=ci --ignore-scripts --no-audit --no-fund",
            self.npm_log.read_text(encoding="utf-8"),
        )
        for tool in ("cursor", "claude", "codex"):
            self.assertFalse(self.link(tool).exists())
        self.assert_no_browser_or_lifecycle_side_effects()

    def test_bootstrap_reconcile_and_doctor_reject_failed_runtime(self):
        projection, _ = self.make_bootstrap_projection()
        env = {**self.env, "ISOKIT_TEST_NPM_MODE": "fail"}

        reconcile = subprocess.run(
            ["bash", str(projection / "bootstrap.sh"), "--reconcile"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertNotEqual(reconcile.returncode, 0)
        self.assertIn("activation-critical runtime isokit", reconcile.stdout)
        self.assert_no_links()
        self.assert_no_browser_or_lifecycle_side_effects()

        repair = subprocess.run(
            ["bash", str(projection / "bootstrap.sh"), "--repair"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertNotEqual(repair.returncode, 0)
        self.assertIn("activation-critical runtime isokit", repair.stdout)
        self.assert_no_links()

        doctor = subprocess.run(
            ["bash", str(projection / "bootstrap.sh"), "--doctor"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertNotEqual(doctor.returncode, 0)
        self.assertIn("activation-critical runtime doctor failed", doctor.stdout)
        self.assert_no_links()
        self.assert_no_browser_or_lifecycle_side_effects()

    def test_bootstrap_owns_single_publication_after_runtime_provisioning(self):
        projection, projected_capability = self.make_bootstrap_projection()
        link_log = self.root / "link.log"
        fake_ln = self.fake_bin / "ln"
        fake_ln.write_text(
            """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$ISOKIT_TEST_LINK_LOG"
exec /bin/ln "$@"
""",
            encoding="utf-8",
        )
        fake_ln.chmod(0o755)
        result = subprocess.run(
            ["bash", str(projection / "bootstrap.sh"), "--reconcile"],
            check=False,
            capture_output=True,
            text=True,
            env={**self.env, "ISOKIT_TEST_LINK_LOG": str(link_log)},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(link_log.read_text(encoding="utf-8").splitlines()), 3)
        for tool in ("cursor", "claude", "codex"):
            link = self.link(tool)
            self.assertTrue(link.is_symlink())
            self.assertEqual(
                Path(os.readlink(link)).resolve(), projected_capability.resolve()
            )
        self.assertEqual(len(self.npm_log.read_text().splitlines()), 1)
        self.assert_no_browser_or_lifecycle_side_effects()

    def test_failed_bootstrap_preserves_only_preexisting_correct_link(self):
        projection, projected_capability = self.make_bootstrap_projection()
        cursor_link = self.link("cursor")
        cursor_link.parent.mkdir(parents=True)
        cursor_link.symlink_to(projected_capability)
        env = {**self.env, "ISOKIT_TEST_NPM_MODE": "fail"}

        reconcile = subprocess.run(
            ["bash", str(projection / "bootstrap.sh"), "--reconcile"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertNotEqual(reconcile.returncode, 0)
        self.assertTrue(cursor_link.is_symlink())
        self.assertEqual(
            Path(os.readlink(cursor_link)).resolve(),
            projected_capability.resolve(),
        )
        self.assert_no_links("cursor")
        self.assert_no_browser_or_lifecycle_side_effects()

    def test_bootstrap_collision_blocks_reconcile_and_repair_before_npm(self):
        projection, _ = self.make_bootstrap_projection()
        collision = self.link("cursor")
        collision.mkdir(parents=True)
        marker = collision / "keep"
        marker.write_text("operator-owned", encoding="utf-8")

        for mode in ("--reconcile", "--repair"):
            with self.subTest(mode=mode):
                result = subprocess.run(
                    ["bash", str(projection / "bootstrap.sh"), mode],
                    check=False,
                    capture_output=True,
                    text=True,
                    env=self.env,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("activation preflight", result.stdout)
                self.assertEqual(marker.read_text(encoding="utf-8"), "operator-owned")
                self.assert_no_links("cursor")
                self.assertFalse(self.npm_log.exists())

    def test_browser_launch_failures_emit_each_channel_and_approval_boundary(self):
        if not self.use_real_node:
            self.skipTest("JavaScript launch diagnostics run in TestNodeIntegration")
        attempts = self.root / "launch-attempts.log"
        self.write_runtime_module(
            """
import { appendFileSync } from "node:fs";
export const chromium = {
  launch: async ({ channel }) => {
    const label = channel === undefined ? "bundled" : channel;
    appendFileSync(process.env.ISOKIT_TEST_LAUNCH_LOG, `${label}\\n`);
    throw new Error(`synthetic-${label}-failure`);
  },
};
""".strip()
            + "\n"
        )
        result = subprocess.run(
            [
                "node",
                str(self.capability / "scripts/shoot.mjs"),
                "http://fixture.invalid",
                "--out",
                str(self.root / "shots"),
            ],
            check=False,
            capture_output=True,
            text=True,
            cwd=self.root,
            env={**self.env, "ISOKIT_TEST_LAUNCH_LOG": str(attempts)},
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            attempts.read_text(encoding="utf-8").splitlines(),
            ["chrome", "chromium", "bundled"],
        )
        self.assertIn("chrome: synthetic-chrome-failure", result.stderr)
        self.assertIn("chromium: synthetic-chromium-failure", result.stderr)
        self.assertIn("bundled chromium: synthetic-bundled-failure", result.stderr)
        self.assertIn(
            "must not be downloaded without explicit operator approval",
            result.stderr,
        )
        self.assert_no_browser_or_lifecycle_side_effects()

    def test_real_path_collision_is_not_clobbered(self):
        collision = self.link("cursor")
        collision.mkdir(parents=True)
        marker = collision / "keep"
        marker.write_text("operator-owned", encoding="utf-8")

        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(marker.read_text(encoding="utf-8"), "operator-owned")
        self.assertIn("refusing activation", result.stdout)
        self.assertFalse(self.npm_log.exists())
        self.assert_no_links("cursor")

    def test_missing_node_fails_before_npm_or_exposure(self):
        # Use a closed PATH so this also proves the missing-Node behavior on
        # developer machines that normally have Node installed.
        closed_bin = self.root / "closed-bin"
        closed_bin.mkdir()
        for name in ("dirname", "basename", "awk", "tr"):
            executable = shutil.which(name)
            self.assertIsNotNone(executable)
            (closed_bin / name).symlink_to(executable)
        (closed_bin / "npm").symlink_to(self.fake_bin / "npm")
        result = subprocess.run(
            ["/bin/bash", str(self.capability / "install.sh")],
            capture_output=True,
            text=True,
            env={**self.env, "PATH": str(closed_bin)},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("node is required", result.stdout)
        self.assertFalse(self.npm_log.exists())
        self.assert_no_links()


@unittest.skipUnless(shutil.which("node"), "Node.js integration requires a Node-equipped host")
class TestNodeIntegration(TestInstaller):
    use_real_node = True


if __name__ == "__main__":
    unittest.main()
