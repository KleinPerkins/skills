#!/bin/bash
set -euo pipefail
umask 077
unset BASH_ENV ENV CDPATH
export PATH="/usr/bin:/bin:/usr/sbin:/sbin"

CAPABILITY="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
cd "$CAPABILITY"
. "$CAPABILITY/scripts/owned-cleanup.sh"
SCRATCH="$(mktemp -d /private/tmp/dev-main-sync-v4-preflight.XXXXXX)"
export SWIFTPM_MODULECACHE_OVERRIDE="$SCRATCH/swift-module-cache"
export CLANG_MODULE_CACHE_PATH="$SCRATCH/clang-module-cache"

cleanup() {
  local status="$1"
  trap - EXIT INT TERM
  dms_reap_owned_root_helpers "$SCRATCH" v4-preflight-acceptance || status=1
  dms_remove_owned_root "$SCRATCH" v4-preflight-acceptance || status=1
  exit "$status"
}
trap 'cleanup "$?"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

"$CAPABILITY/scripts/generate-icon.sh" --check

python3 - "$CAPABILITY" <<'PY'
from pathlib import Path
import re
import sys

root = Path(sys.argv[1])
old = re.compile(r"Dev Main Sync|DevMainSync|DEV_MAIN_SYNC")
metadata = re.compile(
    r"DevMainSync(Architecture|BuildMode|MetadataContractSHA256|"
    r"ReleaseSchema|SourceInputSHA256|SourceRevision)"
)
allowed_predecessor_files = {
    "Sources/ShadowSyncCore/InstallationLifecycle.swift",
    "Sources/ShadowSyncCore/DM4PreflightSelfTests.swift",
    "Sources/ShadowSyncApp/M6Harness.swift",
    "install.sh",
    "scripts/source-doctor.sh",
}
classified = []
for path in sorted(root.rglob("*")):
    if not path.is_file() or ".build" in path.parts:
        continue
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        continue
    relative = str(path.relative_to(root))
    for number, line in enumerate(lines, 1):
        if not old.search(line):
            continue
        reason = None
        if metadata.search(line):
            reason = "stable-release-metadata-key"
        elif "DEV_MAIN_SYNC_BODY1_TEST" in line:
            reason = "stable-retained-test-fixture-environment"
        elif relative == "scripts/v4-preflight-acceptance.sh":
            reason = "closed-naming-audit-rule"
        elif relative in allowed_predecessor_files and (
            "Dev Main Sync" in line or "DevMainSync" in line
        ):
            reason = "explicit-predecessor-generation"
        if reason is None:
            raise SystemExit(
                f"unclassified old application identity: {relative}:{number}:{line}"
            )
        classified.append((relative, number, reason))
if not classified:
    raise SystemExit("old-name compatibility manifest is unexpectedly empty")
for relative, number, reason in classified:
    print(f"CLASSIFIED {reason} {relative}:{number}")
PY

swift package \
  --package-path "$CAPABILITY" \
  --scratch-path "$SCRATCH/package" \
  dump-package >"$SCRATCH/package.json"
python3 - "$SCRATCH/package.json" <<'PY'
import json
import sys

package = json.load(open(sys.argv[1], encoding="utf-8"))
assert package["name"] == "ShadowSync", package["name"]
products = {product["name"] for product in package["products"]}
targets = {target["name"] for target in package["targets"]}
assert products == {"ShadowSync", "ShadowSyncCatalog"}, products
assert targets == {
    "ShadowSyncCatalog", "ShadowSyncCore", "ShadowSyncApp",
    "ShadowSyncSelfTest", "ShadowSyncCompileTests",
}, targets
PY

TEST_OUTPUT="$SCRATCH/testing-output"
"$CAPABILITY/scripts/build-app.sh" \
  --scratch-path "$SCRATCH/testing-swift" \
  --output-dir "$TEST_OUTPUT" \
  --testing
TEST_APP="$TEST_OUTPUT/ShadowSync.app"
TEST_EXECUTABLE="$TEST_APP/Contents/MacOS/ShadowSync"

swift build \
  --package-path "$CAPABILITY" \
  --scratch-path "$SCRATCH/testing-swift" \
  --configuration release \
  --product ShadowSyncSelfTest \
  --disable-index-store \
  -Xswiftc -DSHADOW_SYNC_TESTING >/dev/null
BIN_DIR="$(swift build \
  --package-path "$CAPABILITY" \
  --scratch-path "$SCRATCH/testing-swift" \
  --configuration release \
  --product ShadowSyncSelfTest \
  --disable-index-store \
  -Xswiftc -DSHADOW_SYNC_TESTING \
  --show-bin-path)"
SELF_TEST="$BIN_DIR/ShadowSyncSelfTest"

for index in $(jot -w '%02d' 12 1); do
  "$SELF_TEST" \
    --app-executable "$TEST_EXECUTABLE" \
    "--dm4-t${index}-only"
done

make_source() {
  local name="$1" revision="$2" digest="$3" app="$SCRATCH/$1.app"
  cp -R "$TEST_APP" "$app"
  plutil -replace DevMainSyncBuildMode -string production \
    "$app/Contents/Info.plist"
  plutil -replace DevMainSyncSourceRevision -string "$revision" \
    "$app/Contents/Info.plist"
  plutil -replace DevMainSyncSourceInputSHA256 -string "$digest" \
    "$app/Contents/Info.plist"
  plutil -replace DevMainSyncMetadataContractSHA256 \
    -string 5555555555555555555555555555555555555555555555555555555555555555 \
    "$app/Contents/Info.plist"
  codesign --force --sign - --timestamp=none \
    --identifier com.kleinperkins.dev-main-sync "$app" >/dev/null
  xattr -cr "$app"
  codesign --verify --strict --verbose=2 "$app" >/dev/null
  printf '%s\n' "$app"
}
SOURCE_N="$(make_source n \
  1111111111111111111111111111111111111111 \
  2222222222222222222222222222222222222222222222222222222222222222)"
SOURCE_N1="$(make_source n1 \
  3333333333333333333333333333333333333333 \
  4444444444444444444444444444444444444444444444444444444444444444)"

mkdir -m 700 "$SCRATCH/home"
python3 - "$TEST_EXECUTABLE" "$SCRATCH" "$SOURCE_N" "$SOURCE_N1" <<'PY'
import json
import socket
import subprocess
import sys

executable, root, source_n, source_n1 = sys.argv[1:]
parent, child = socket.socketpair()
process = subprocess.Popen(
    [executable, "--_dms-m6-lifecycle-channel", str(child.fileno())],
    pass_fds=(child.fileno(),),
    stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
child.close()
request = {
    "schema": "dev-main-sync-m6-lifecycle/v1",
    "testRoot": root,
    "sourceN": source_n,
    "sourceEquivalent": source_n,
    "sourceN1": source_n1,
    "operation": "v4-migration",
}
parent.sendall(json.dumps(request, separators=(",", ":")).encode() + b"\n")
parent.shutdown(socket.SHUT_WR)
payload = b""
while not payload.endswith(b"\n"):
    block = parent.recv(65536)
    if not block:
        break
    payload += block
parent.close()
stdout, stderr = process.communicate(timeout=60)
if process.returncode != 0:
    raise SystemExit(
        "v4 migration harness failed: "
        + stderr.decode(errors="replace")
        + stdout.decode(errors="replace")
    )
result = json.loads(payload)
expected = {
    "v4-predecessor-forward-migration",
    "v4-old-new-no-overlap",
    "v4-stopped-predecessor-dead-coordination-repair",
    "v4-predecessor-readiness-rollback",
    "v4-migration-fault-cuts-12",
    "v4-dual-generation-uninstall",
}
if not expected.issubset(result["passed"]):
    raise SystemExit(f"missing v4 migration evidence: {result}")
for item in sorted(expected):
    print("PASS " + item)
PY

if strings "$TEST_EXECUTABLE" | grep -F 'DEV_MAIN_SYNC_TESTING' >/dev/null; then
  printf 'v4-preflight-acceptance: old testing compile identity remains\n' >&2
  exit 1
fi

printf 'PASS DM4-T01..DM4-T12\n'
printf 'v4-preflight-acceptance: PASS\n'
