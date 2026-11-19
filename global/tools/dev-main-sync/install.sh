#!/bin/bash
set -euo pipefail
umask 077
unset BASH_ENV ENV CDPATH GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY
unset GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_CEILING_DIRECTORIES
unset SDKROOT SWIFT_EXEC CC CXX CFLAGS CPPFLAGS LDFLAGS DYLD_LIBRARY_PATH DYLD_INSERT_LIBRARIES
export PATH="/usr/bin:/bin:/usr/sbin:/sbin"
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_ATTR_NOSYSTEM=1

SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
NAME="dev-main-sync"

log() { printf '[install:%s] %s\n' "$NAME" "$*"; }
fail() { printf '[install:%s] FAIL: %s\n' "$NAME" "$*" >&2; return 1; }

field() {
  awk -v key="$2" '
    /^[[:space:]]*#/ { next }
    $0 ~ ("^" key ":[[:space:]]*") {
      line=$0
      sub(/^[^:]+:[[:space:]]*/, "", line)
      gsub(/^"|"$/, "", line)
      print line
      exit
    }
  ' "$1"
}

expect_field() {
  local file="$1" key="$2" expected="$3" actual
  actual="$(field "$file" "$key")"
  [ "$actual" = "$expected" ] || fail "$file: $key must be '$expected' (got '$actual')"
}

do_check() {
  local rc=0 required
  log "static source and package check (no writes, no network)"
  for required in \
    meta.yml tool.yml README.md install.sh Package.swift \
    Resources/Info.plist Resources/com.kleinperkins.dev-main-sync.plist.template \
    Sources/ShadowSyncCatalog Sources/ShadowSyncCore Sources/ShadowSyncApp \
    Tests scripts/build-app.sh \
    scripts/installer-scratch-cleanup-tests.sh \
    scripts/m1-core-tests.sh scripts/m1-native-e2e.sh scripts/verify-m1.sh \
    scripts/v2-body1-acceptance.sh scripts/v2-body2-acceptance.sh \
    scripts/v2-body4-acceptance.sh scripts/v3-preflight-acceptance.sh \
    scripts/verify-m5.sh scripts/verify-m6.sh scripts/source-doctor.sh \
    scripts/owned-cleanup.sh scripts/beta-v0.1-native-smoke.sh \
    scripts/beta-v0.2-native-smoke.sh \
    scripts/verify-beta-v0.2.sh scripts/verify-beta-v0.5.sh \
    scripts/verify-beta-v0.6.sh scripts/verify-beta-v0.7.sh; do
    [ -e "$SRC/$required" ] || { printf '  FAIL  missing %s\n' "$required"; rc=1; }
  done

  expect_field "$SRC/meta.yml" schema kp-capability/v1 || rc=1
  expect_field "$SRC/meta.yml" id dev-main-sync || rc=1
  expect_field "$SRC/meta.yml" kind tool || rc=1
  expect_field "$SRC/meta.yml" flavor 1 || rc=1
  expect_field "$SRC/meta.yml" scope global || rc=1
  expect_field "$SRC/meta.yml" owner KleinPerkins || rc=1
  expect_field "$SRC/meta.yml" install install.sh || rc=1
  expect_field "$SRC/meta.yml" post_mgmt launchd || rc=1
  expect_field "$SRC/meta.yml" shape snapshot || rc=1
  expect_field "$SRC/meta.yml" sync_policy none || rc=1
  expect_field "$SRC/meta.yml" expose "cursor claude codex" || rc=1
  expect_field "$SRC/meta.yml" provenance_source "" || rc=1
  expect_field "$SRC/meta.yml" provenance_ref "" || rc=1
  expect_field "$SRC/meta.yml" provenance_trust "" || rc=1
  expect_field "$SRC/tool.yml" schema kp-tool/v1 || rc=1
  expect_field "$SRC/tool.yml" id dev-main-sync || rc=1
  expect_field "$SRC/tool.yml" entrypoint install.sh || rc=1

  [ -x "$SRC/install.sh" ] || { printf '  FAIL  install.sh is not executable\n'; rc=1; }
  [ -x "$SRC/scripts/build-app.sh" ] || { printf '  FAIL  build-app.sh is not executable\n'; rc=1; }
  [ -x "$SRC/scripts/installer-scratch-cleanup-tests.sh" ] \
    || { printf '  FAIL  installer-scratch-cleanup-tests.sh is not executable\n'; rc=1; }
  [ -x "$SRC/scripts/m1-core-tests.sh" ] || { printf '  FAIL  m1-core-tests.sh is not executable\n'; rc=1; }
  [ -x "$SRC/scripts/m1-native-e2e.sh" ] || { printf '  FAIL  m1-native-e2e.sh is not executable\n'; rc=1; }
  [ -x "$SRC/scripts/verify-m1.sh" ] || { printf '  FAIL  verify-m1.sh is not executable\n'; rc=1; }
  [ -x "$SRC/scripts/v2-body1-acceptance.sh" ] \
    || { printf '  FAIL  v2-body1-acceptance.sh is not executable\n'; rc=1; }
  [ -x "$SRC/scripts/v2-body2-acceptance.sh" ] \
    || { printf '  FAIL  v2-body2-acceptance.sh is not executable\n'; rc=1; }
  [ -x "$SRC/scripts/v2-body4-acceptance.sh" ] \
    || { printf '  FAIL  v2-body4-acceptance.sh is not executable\n'; rc=1; }
  [ -x "$SRC/scripts/v3-preflight-acceptance.sh" ] \
    || { printf '  FAIL  v3-preflight-acceptance.sh is not executable\n'; rc=1; }
  [ -x "$SRC/scripts/verify-m5.sh" ] || { printf '  FAIL  verify-m5.sh is not executable\n'; rc=1; }
  [ -x "$SRC/scripts/verify-m6.sh" ] || { printf '  FAIL  verify-m6.sh is not executable\n'; rc=1; }
  [ -x "$SRC/scripts/source-doctor.sh" ] || { printf '  FAIL  source-doctor.sh is not executable\n'; rc=1; }
  [ -x "$SRC/scripts/beta-v0.1-native-smoke.sh" ] \
    || { printf '  FAIL  beta-v0.1-native-smoke.sh is not executable\n'; rc=1; }
  [ -x "$SRC/scripts/beta-v0.2-native-smoke.sh" ] \
    || { printf '  FAIL  beta-v0.2-native-smoke.sh is not executable\n'; rc=1; }
  [ -x "$SRC/scripts/verify-beta-v0.2.sh" ] \
    || { printf '  FAIL  verify-beta-v0.2.sh is not executable\n'; rc=1; }
  [ -x "$SRC/scripts/verify-beta-v0.5.sh" ] \
    || { printf '  FAIL  verify-beta-v0.5.sh is not executable\n'; rc=1; }
  [ -x "$SRC/scripts/verify-beta-v0.6.sh" ] \
    || { printf '  FAIL  verify-beta-v0.6.sh is not executable\n'; rc=1; }
  [ -x "$SRC/scripts/verify-beta-v0.7.sh" ] \
    || { printf '  FAIL  verify-beta-v0.7.sh is not executable\n'; rc=1; }
  plutil -lint "$SRC/Resources/Info.plist" >/dev/null || rc=1
  plutil -lint "$SRC/Resources/com.kleinperkins.dev-main-sync.plist.template" >/dev/null || rc=1
  [ "$(plutil -extract ProgramArguments.1 raw \
    "$SRC/Resources/com.kleinperkins.dev-main-sync.plist.template")" = "--managed-host" ] \
    || { printf '  FAIL  LaunchAgent template is missing its managed-host role\n'; rc=1; }
  if plutil -extract ProgramArguments.2 raw \
    "$SRC/Resources/com.kleinperkins.dev-main-sync.plist.template" >/dev/null 2>&1; then
    printf '  FAIL  LaunchAgent template has unexpected program arguments\n'
    rc=1
  fi
  [ "$(plutil -extract RunAtLoad raw \
    "$SRC/Resources/com.kleinperkins.dev-main-sync.plist.template")" = "false" ] \
    || { printf '  FAIL  LaunchAgent must be manual-by-default\n'; rc=1; }

  if grep -R -n -E '/Users/[[:alnum:]_.-]+/' "$SRC" --exclude-dir=.build --exclude-dir=.swiftpm; then
    printf '  FAIL  source contains an absolute user-home path\n'
    rc=1
  fi
  if grep -R -n -E '(^|[^A-Za-z])import[[:space:]]+AppKit([^A-Za-z]|$)' "$SRC/Sources/ShadowSyncCore"; then
    printf '  FAIL  core target imports AppKit\n'
    rc=1
  fi
  if grep -q '\.package[[:space:]]*(' "$SRC/Package.swift"; then
    printf '  FAIL  third-party Swift package dependency declared\n'
    rc=1
  fi
  grep -q '^// swift-tools-version: 6\.2$' "$SRC/Package.swift" || {
    printf '  FAIL  Package.swift must use Swift tools 6.2\n'; rc=1;
  }
  grep -q '\.macOS("26\.0")' "$SRC/Package.swift" || {
    printf '  FAIL  Package.swift must require macOS 26\n'; rc=1;
  }
  grep -q 'swiftLanguageModes: \[\.v6\]' "$SRC/Package.swift" || {
    printf '  FAIL  Package.swift must use Swift 6 language mode\n'; rc=1;
  }
  [ "$(grep -c '\.executable(name:' "$SRC/Package.swift")" -eq 1 ] || {
    printf '  FAIL  Package.swift must expose only ShadowSync\n'; rc=1;
  }
  [ ! -d "$SRC/payload" ] || {
    printf '  FAIL  Flavor-1 source must not contain payload/\n'; rc=1;
  }
  if [ -d "$SRC/.build" ] || [ -d "$SRC/.swiftpm" ]; then
    printf '  FAIL  in-tree SwiftPM residue exists\n'
    rc=1
  fi
  command -v swift >/dev/null 2>&1 || { printf '  FAIL  swift is unavailable\n'; rc=1; }
  command -v codesign >/dev/null 2>&1 || { printf '  FAIL  codesign is unavailable\n'; rc=1; }
  command -v git >/dev/null 2>&1 || { printf '  FAIL  git is unavailable\n'; rc=1; }

  if [ "$rc" -eq 0 ]; then
    log "check OK"
  else
    fail "check failed"
  fi
}

SOURCE_REPOSITORY=""
SOURCE_REVISION=""
SOURCE_INPUT_SHA256=""
METADATA_CONTRACT_SHA256=""

capture_source_identity() {
  local repository source_relative head remote_head git_dir branch dirty lock_row committed_row
  local origin computed_contract unsafe_tree
  repository="$(git -C "$SRC" rev-parse --show-toplevel 2>/dev/null)" || fail "source is not inside a Git repository"
  repository="$(cd -P "$repository" && pwd)"
  [ "$SRC" = "$repository/global/tools/dev-main-sync" ] || fail "source is not the canonical capability path"
  origin="$(git -C "$repository" remote get-url origin)"
  case "$origin" in
    git@github.com:KleinPerkins/skills.git|https://github.com/KleinPerkins/skills.git) ;;
    *) fail "source origin is not canonical KleinPerkins/skills" ;;
  esac
  git_dir="$(git -C "$repository" rev-parse --absolute-git-dir)"
  [ "$git_dir" = "$repository/.git" ] || fail "live lifecycle requires the durable primary checkout"
  [ ! -e "$git_dir/shallow" ] \
    && [ ! -e "$git_dir/info/grafts" ] \
    && [ ! -e "$git_dir/objects/info/alternates" ] \
    && [ -z "$(git -C "$repository" for-each-ref refs/replace/)" ] \
    || fail "source repository uses non-ordinary object semantics"
  branch="$(git -C "$repository" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  [ "$branch" = "main" ] || fail "live lifecycle requires the primary main branch"
  head="$(git -C "$repository" rev-parse HEAD)"
  remote_head="$(git -C "$repository" rev-parse refs/remotes/origin/main)"
  [ "$head" = "$remote_head" ] || fail "source HEAD must exactly match local origin/main"
  source_relative="global/tools/dev-main-sync"
  dirty="$(git -C "$repository" status --porcelain=v1 --untracked-files=all -- \
    "$source_relative" .eco-registry.lock .github/scripts/eco-lock.sh)"
  [ -z "$dirty" ] || fail "capability source or metadata lock is modified/untracked"
  lock_row="$(awk '$1 == "dev-main-sync" { print; found=1 } END { if (!found) exit 1 }' "$repository/.eco-registry.lock")" \
    || fail "metadata lock has no dev-main-sync row"
  committed_row="$(git -C "$repository" show "$head:.eco-registry.lock" \
    | awk '$1 == "dev-main-sync" { print; found=1 } END { if (!found) exit 1 }')" \
    || fail "committed metadata lock has no dev-main-sync row"
  [ "$lock_row" = "$committed_row" ] || fail "working metadata-lock row differs from the captured commit"
  METADATA_CONTRACT_SHA256="$(printf '%s\n' "$lock_row" | awk '{print $2}')"
  case "$METADATA_CONTRACT_SHA256" in
    *[!0-9a-f]*|"") fail "metadata-contract digest is invalid" ;;
  esac
  [ "${#METADATA_CONTRACT_SHA256}" -eq 64 ] || fail "metadata-contract digest has the wrong length"
  computed_contract="$(
    cd "$repository"
    /bin/bash .github/scripts/eco-lock.sh digest global/tools/dev-main-sync/meta.yml
  )"
  [ "$computed_contract" = "$METADATA_CONTRACT_SHA256" ] \
    || fail "committed metadata-lock row is stale"
  unsafe_tree="$(git -C "$repository" ls-tree -r "$head" -- "$source_relative" \
    | awk '$1 == "120000" || $1 == "160000" {print; exit}')"
  [ -z "$unsafe_tree" ] || fail "capability tree contains a symlink or submodule"
  SOURCE_INPUT_SHA256="$(
    {
      printf 'dev-main-sync-source/v1\0'
      git -C "$repository" ls-tree -r -z "$head" -- "$source_relative"
      printf '\0%s\0' "$lock_row"
    } | shasum -a 256 | awk '{print $1}'
  )"
  SOURCE_REPOSITORY="$repository"
  SOURCE_REVISION="$head"
}

assert_source_unchanged() {
  local expected_repository="$SOURCE_REPOSITORY"
  local expected_revision="$SOURCE_REVISION"
  local expected_input="$SOURCE_INPUT_SHA256"
  local expected_contract="$METADATA_CONTRACT_SHA256"
  capture_source_identity
  [ "$SOURCE_REPOSITORY" = "$expected_repository" ] \
    && [ "$SOURCE_REVISION" = "$expected_revision" ] \
    && [ "$SOURCE_INPUT_SHA256" = "$expected_input" ] \
    && [ "$METADATA_CONTRACT_SHA256" = "$expected_contract" ] \
    || fail "source/head/tree/metadata lock changed before lifecycle promotion"
}

verify_captured_tree() {
  local capture="$1" record header relative expected_oid actual_oid expected_mode actual_mode count=0
  while IFS= read -r -d '' record; do
    header="${record%%$'\t'*}"
    relative="${record#*$'\t'}"
    expected_mode="${header%% *}"
    header="${header#* }"; header="${header#* }"
    expected_oid="$header"
    [ -f "$capture/$relative" ] && [ ! -L "$capture/$relative" ] \
      || fail "captured tree contains a missing or non-regular path: $relative"
    actual_oid="$(git hash-object --no-filters "$capture/$relative")"
    [ "$actual_oid" = "$expected_oid" ] || fail "captured blob differs from Git object: $relative"
    actual_mode="$(stat -f '%Lp' "$capture/$relative")"
    case "$expected_mode" in
      100755) [ $((8#$actual_mode & 0111)) -ne 0 ] || fail "captured executable mode changed: $relative" ;;
      100644) [ $((8#$actual_mode & 0111)) -eq 0 ] || fail "captured regular mode changed: $relative" ;;
      *) fail "captured tree has unsupported mode $expected_mode: $relative" ;;
    esac
    count=$((count + 1))
  done < <(git -C "$SOURCE_REPOSITORY" ls-tree -r -z "$SOURCE_REVISION" -- global/tools/dev-main-sync)
  [ "$count" -gt 0 ] || fail "captured tree inventory is empty"
  [ "$(find "$capture/global/tools/dev-main-sync" -type f | wc -l | tr -d ' ')" -eq "$count" ] \
    || fail "captured archive contains unexpected files"
}

captured_release_root_has_expected_path() {
  local root="$1" suffix
  case "$root" in
    /private/tmp/dev-main-sync-m6-live.*) ;;
    *) return 1 ;;
  esac
  suffix="${root#/private/tmp/dev-main-sync-m6-live.}"
  [ "${#suffix}" -eq 6 ] || return 1
  case "$suffix" in *[!A-Za-z0-9]*) return 1 ;; esac
  [ "$(dirname "$root")" = "/private/tmp" ] \
    && [ -d /private/tmp ] && [ ! -L /private/tmp ] \
    && [ "$(cd -P /private/tmp && pwd)" = "/private/tmp" ]
}

remove_empty_captured_release_root() {
  local root="$1" expected_uid="$2" expected_device="$3" expected_inode="$4"
  local expected_mode="$5" expected_parent_device="$6" expected_parent_inode="$7"
  local identity actual_uid actual_device actual_inode actual_mode
  local parent_identity actual_parent_device actual_parent_inode
  local first_entry final_identity final_parent_identity
  captured_release_root_has_expected_path "$root" \
    && [ -d "$root" ] && [ ! -L "$root" ] \
    && [ "$(cd -P "$root" 2>/dev/null && pwd)" = "$root" ] || {
      fail "refusing pre-identity cleanup of an unexpected captured-release root: $root"
      return 1
    }
  identity="$(stat -f '%u %d %i %Lp' "$root" 2>/dev/null)" || {
    fail "could not inspect pre-identity captured-release root: $root"
    return 1
  }
  read -r actual_uid actual_device actual_inode actual_mode <<<"$identity"
  parent_identity="$(stat -f '%d %i' /private/tmp 2>/dev/null)" || {
    fail "could not inspect pre-identity captured-release parent"
    return 1
  }
  read -r actual_parent_device actual_parent_inode <<<"$parent_identity"
  [ "$actual_uid" = "$(id -u)" ] && [ "$actual_mode" = 700 ] \
    && [ "$actual_device" = "$actual_parent_device" ] || {
      fail "refusing unsafe pre-identity captured-release cleanup: $root"
      return 1
    }
  if ! { { [ -z "$expected_uid" ] || [ "$actual_uid" = "$expected_uid" ]; } \
      && { [ -z "$expected_device" ] || [ "$actual_device" = "$expected_device" ]; } \
      && { [ -z "$expected_inode" ] || [ "$actual_inode" = "$expected_inode" ]; } \
      && { [ -z "$expected_mode" ] || [ "$actual_mode" = "$expected_mode" ]; } \
      && { [ -z "$expected_parent_device" ] \
        || [ "$actual_parent_device" = "$expected_parent_device" ]; } \
      && { [ -z "$expected_parent_inode" ] \
        || [ "$actual_parent_inode" = "$expected_parent_inode" ]; }; }; then
      fail "refusing pre-identity cleanup after captured-release root changed: $root"
      return 1
  fi
  first_entry="$(/usr/bin/find "$root" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" || {
    fail "could not inspect pre-identity captured-release root contents: $root"
    return 1
  }
  [ -z "$first_entry" ] || {
    fail "refusing non-empty pre-identity captured-release cleanup: $root"
    return 1
  }
  final_identity="$(stat -f '%u %d %i %Lp' "$root" 2>/dev/null)" \
    && final_parent_identity="$(stat -f '%d %i' /private/tmp 2>/dev/null)" \
    && [ "$final_identity" = "$identity" ] \
    && [ "$final_parent_identity" = "$parent_identity" ] || {
      fail "refusing pre-identity cleanup after final identity check changed: $root"
      return 1
    }
  /bin/rmdir "$root"
  [ ! -e "$root" ] && [ ! -L "$root" ] \
    || fail "empty captured-release root removal failed: $root"
}

remove_captured_release_root() {
  local root="$1" identity_complete="$2" expected_uid="$3" expected_device="$4"
  local expected_inode="$5" expected_mode="$6" expected_parent_device="$7"
  local expected_parent_inode="$8"
  local identity actual_uid actual_device actual_inode actual_mode
  local parent_identity actual_parent_device actual_parent_inode
  [ -n "$root" ] || return 0
  if [ ! -e "$root" ] && [ ! -L "$root" ]; then
    return 0
  fi
  if [ "$identity_complete" = 0 ]; then
    remove_empty_captured_release_root \
      "$root" "$expected_uid" "$expected_device" "$expected_inode" "$expected_mode" \
      "$expected_parent_device" "$expected_parent_inode"
    return
  fi
  [ "$identity_complete" = 1 ] || {
    fail "refusing captured-release cleanup with invalid identity state: $root"
    return 1
  }
  captured_release_root_has_expected_path "$root" \
    && [ -d "$root" ] && [ ! -L "$root" ] \
    && [ "$(cd -P "$root" 2>/dev/null && pwd)" = "$root" ] || {
      fail "refusing cleanup of an unexpected captured-release root: $root"
      return 1
    }
  identity="$(stat -f '%u %d %i %Lp' "$root" 2>/dev/null)" || {
    fail "could not verify captured-release root identity: $root"
    return 1
  }
  read -r actual_uid actual_device actual_inode actual_mode <<<"$identity"
  parent_identity="$(stat -f '%d %i' /private/tmp 2>/dev/null)" || {
    fail "could not verify captured-release parent identity"
    return 1
  }
  read -r actual_parent_device actual_parent_inode <<<"$parent_identity"
  [ -n "$expected_uid" ] && [ "$actual_uid" = "$expected_uid" ] \
    && [ "$actual_uid" = "$(id -u)" ] \
    && [ -n "$expected_device" ] && [ "$actual_device" = "$expected_device" ] \
    && [ -n "$expected_inode" ] && [ "$actual_inode" = "$expected_inode" ] \
    && [ -n "$expected_mode" ] && [ "$actual_mode" = "$expected_mode" ] \
    && [ "$actual_mode" = 700 ] \
    && [ -n "$expected_parent_device" ] \
    && [ "$actual_parent_device" = "$expected_parent_device" ] \
    && [ -n "$expected_parent_inode" ] \
    && [ "$actual_parent_inode" = "$expected_parent_inode" ] \
    && [ "$actual_device" = "$actual_parent_device" ] || {
      fail "refusing cleanup after captured-release root identity changed: $root"
      return 1
    }
  /bin/rm -rf -- "$root"
  [ ! -e "$root" ] && [ ! -L "$root" ] || fail "captured-release root removal failed: $root"
}

build_captured_release() (
  local action="$1" root="" capture captured_source built
  local identity_complete=0
  local root_identity root_uid="" root_device="" root_inode="" root_mode=""
  local parent_identity parent_device="" parent_inode=""
  # shellcheck disable=SC2329 # Invoked indirectly by the EXIT trap below.
  cleanup_live_release() {
    local status=$?
    trap - EXIT INT TERM
    if ! remove_captured_release_root \
      "$root" "$identity_complete" "$root_uid" "$root_device" "$root_inode" "$root_mode" \
      "$parent_device" "$parent_inode"; then
      status=1
    fi
    exit "$status"
  }
  # The subshell keeps these traps and the recorded root identity bound to this invocation.
  trap cleanup_live_release EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  capture_source_identity
  log "captured source revision $SOURCE_REVISION"
  root="$(mktemp -d /private/tmp/dev-main-sync-m6-live.XXXXXX)"
  # The successful assignment registers the exact path with the already-active EXIT trap.
  chmod 700 "$root"
  root_identity="$(stat -f '%u %d %i %Lp' "$root")"
  read -r root_uid root_device root_inode root_mode <<<"$root_identity"
  parent_identity="$(stat -f '%d %i' /private/tmp)"
  read -r parent_device parent_inode <<<"$parent_identity"
  captured_release_root_has_expected_path "$root" \
    && [ "$root_uid" = "$(id -u)" ] && [ "$root_mode" = 700 ] \
    && [ "$root_device" = "$parent_device" ] || {
      fail "created captured-release root failed safety validation: $root"
      return 1
  }
  identity_complete=1
  capture="$root/capture"
  mkdir -m 700 "$capture"
  git -C "$SOURCE_REPOSITORY" archive "$SOURCE_REVISION" global/tools/dev-main-sync \
    | tar -x -C "$capture"
  verify_captured_tree "$capture"
  captured_source="$capture/global/tools/dev-main-sync"
  [ -x "$captured_source/scripts/build-app.sh" ] || fail "captured build script is missing"
  built="$(
    "$captured_source/scripts/build-app.sh" \
      --scratch-path "$root/swift" \
      --output-dir "$root/output" \
      --source-revision "$SOURCE_REVISION" \
      --source-input-sha256 "$SOURCE_INPUT_SHA256" \
      --metadata-contract-sha256 "$METADATA_CONTRACT_SHA256"
  )"
  assert_source_unchanged
  if [ "$action" = "--check-only" ]; then
    "$built/Contents/MacOS/ShadowSync" --check
  elif [ "$action" = "--lifecycle-reconcile" ] \
      || [ "$action" = "--lifecycle-repair" ] \
      || [ "$action" = "--lifecycle-remove" ]; then
    "$built/Contents/MacOS/ShadowSync" "$action" \
      --source-installer "$SRC/install.sh" \
      --source-revision "$SOURCE_REVISION" \
      --source-input-sha256 "$SOURCE_INPUT_SHA256" \
      --metadata-contract-sha256 "$METADATA_CONTRACT_SHA256"
  else
    "$built/Contents/MacOS/ShadowSync" "$action"
  fi
)

effective_home() {
  local username home
  username="$(id -un)"
  home="$(dscl . -read "/Users/$username" NFSHomeDirectory 2>/dev/null | awk '{print $2}')"
  case "$home" in /*) printf '%s\n' "$home" ;; *) fail "could not resolve the effective account home" ;; esac
}

live_doctor() {
  local home app executable info predecessor_app predecessor_executable predecessor=0
  capture_source_identity
  home="$(effective_home)"
  app="$home/Applications/ShadowSync.app"
  executable="$app/Contents/MacOS/ShadowSync"
  predecessor_app="$home/Applications/Dev Main Sync.app"
  predecessor_executable="$predecessor_app/Contents/MacOS/DevMainSync"
  if { [ -e "$app" ] || [ -L "$app" ]; } \
    && { [ -e "$predecessor_app" ] || [ -L "$predecessor_app" ]; }; then
    fail "both ShadowSync and predecessor app bundles are present; run repair"
  fi
  if [ ! -e "$app" ] && [ ! -L "$app" ] \
    && { [ -e "$predecessor_app" ] || [ -L "$predecessor_app" ]; }; then
    app="$predecessor_app"
    executable="$predecessor_executable"
    predecessor=1
  fi
  info="$app/Contents/Info.plist"
  if [ ! -e "$app" ] && [ ! -L "$app" ]; then
    "$SRC/scripts/source-doctor.sh" --home "$home" --launchctl /bin/launchctl
    return
  fi
  [ -d "$app" ] && [ ! -L "$app" ] || fail "installed app is not a physical directory"
  [ -f "$executable" ] && [ ! -L "$executable" ] && [ -x "$executable" ] \
    || fail "installed executable is missing, aliased, or not executable"
  [ -f "$info" ] && [ ! -L "$info" ] || fail "installed release metadata is missing or aliased"
  codesign --verify --strict --verbose=2 "$app"
  [ "$(plutil -extract DevMainSyncBuildMode raw "$info")" = production ] \
    || fail "installed app is not a production build"
  if [ "$predecessor" -eq 1 ]; then
    "$executable" --lifecycle-doctor
    log "verified predecessor is installed; reconcile or repair will migrate it to ShadowSync"
    return
  fi
  [ "$(plutil -extract DevMainSyncSourceRevision raw "$info")" = "$SOURCE_REVISION" ] \
    || fail "installed app source revision differs from canonical source"
  [ "$(plutil -extract DevMainSyncSourceInputSHA256 raw "$info")" = "$SOURCE_INPUT_SHA256" ] \
    || fail "installed app source identity differs from canonical source"
  [ "$(plutil -extract DevMainSyncMetadataContractSHA256 raw "$info")" = "$METADATA_CONTRACT_SHA256" ] \
    || fail "installed app metadata contract differs from canonical source"
  "$executable" --lifecycle-doctor
}

reconcile_live() {
  local home executable report
  capture_source_identity
  home="$(effective_home)"
  executable="$home/Applications/ShadowSync.app/Contents/MacOS/ShadowSync"
  if [ -x "$executable" ] && [ ! -L "$executable" ]; then
    report="$("$executable" --lifecycle-doctor 2>/dev/null || true)"
    if printf '%s\n' "$report" \
        | grep -F "source-sha256=$SOURCE_INPUT_SHA256" >/dev/null \
      && printf '%s\n' "$report" \
        | grep -F "metadata-contract-sha256=$METADATA_CONTRACT_SHA256" >/dev/null; then
      log "healthy identical source is already installed; no build or process change"
      return 0
    fi
  fi
  build_captured_release --lifecycle-reconcile
}

canonical_test_root() {
  local root="$1"
  local canonical mode
  case "$root" in /*) ;; *) fail "test root must be absolute"; return 1 ;; esac
  [ "$root" != "/" ] || { fail "refusing filesystem root as a test root"; return 1; }
  [ -d "$root" ] && [ ! -L "$root" ] || {
    fail "test root must be an existing physical directory"
    return 1
  }
  canonical="$(cd -P "$root" && pwd)"
  case "$canonical" in
    /private/tmp/*) ;;
    *) fail "explicit M1 test root must resolve inside /private/tmp"; return 1 ;;
  esac
  [ "$(stat -f '%u' "$canonical")" = "$(id -u)" ] || {
    fail "test root must be owned by the effective user"
    return 1
  }
  mode="$(stat -f '%Lp' "$canonical")"
  [ $((8#$mode & 077)) -eq 0 ] || {
    fail "test root must not grant group or other access"
    return 1
  }
  printf '%s\n' "$canonical"
}

stage_m1() {
  local test_root scratch="$2"
  test_root="$(canonical_test_root "$1")"
  case "$scratch" in /*) ;; *) fail "scratch path must be absolute" ;; esac
  case "$scratch/" in "$test_root"/*) ;; *) fail "scratch path must stay inside the test root" ;; esac
  case "/$scratch/" in */../*|*/./*) fail "scratch path must not contain dot components" ;; esac
  [ ! -e "$scratch" ] && [ ! -L "$scratch" ] || fail "scratch path must be fresh"

  local home output built app_parent app_target plist_parent plist_target executable
  home="$test_root/home"
  output="$test_root/build-output"
  app_parent="$home/Applications"
  app_target="$app_parent/ShadowSync.app"
  plist_parent="$home/Library/LaunchAgents"
  plist_target="$plist_parent/com.kleinperkins.dev-main-sync.plist"
  [ ! -e "$output" ] && [ ! -L "$output" ] || fail "build output path must be fresh"
  local descendant parent
  for descendant in "$home" "$app_parent" "$home/Library" "$plist_parent"; do
    [ ! -e "$descendant" ] && [ ! -L "$descendant" ] || {
      fail "refusing pre-existing staging descendant: $descendant"
      return 1
    }
    parent="$(dirname "$descendant")"
    [ -d "$parent" ] && [ ! -L "$parent" ] || {
      fail "staging parent is not physical: $parent"
      return 1
    }
    [ "$(cd -P "$parent" && pwd)/$(basename "$descendant")" = "$descendant" ] || {
      fail "staging parent path is not physical: $parent"
      return 1
    }
    mkdir -m 700 "$descendant"
    [ -d "$descendant" ] && [ ! -L "$descendant" ] \
      && [ "$(stat -f '%u' "$descendant")" = "$(id -u)" ] \
      && [ "$(stat -f '%Lp' "$descendant")" = 700 ] || {
        fail "could not create private staging descendant: $descendant"
        return 1
      }
  done

  built="$("$SRC/scripts/build-app.sh" --scratch-path "$scratch" --output-dir "$output" --testing)"
  [ -d "$built" ] || fail "test bundle was not built"
  [ ! -e "$app_target" ] || fail "test app target already exists"
  mv "$built" "$app_target"

  executable="$app_target/Contents/MacOS/ShadowSync"
  install -m 0600 "$SRC/Resources/com.kleinperkins.dev-main-sync.plist.template" "$plist_target"
  plutil -remove ProgramArguments.0 "$plist_target"
  plutil -insert ProgramArguments.0 -string "$executable" "$plist_target"
  plutil -lint "$plist_target" >/dev/null
  log "staged M1 test app without loading launchd: $app_target"
  log "staged M1 test LaunchAgent without bootstrapping it: $plist_target"
}

doctor_test_root() {
  local test_root home app plist executable launchctl_stub rc=0
  test_root="$(canonical_test_root "$1")"
  home="$test_root/home"
  app="$home/Applications/ShadowSync.app"
  plist="$home/Library/LaunchAgents/com.kleinperkins.dev-main-sync.plist"
  executable="$app/Contents/MacOS/ShadowSync"
  launchctl_stub="$test_root/launchctl-stub"

  if [ ! -e "$app" ] && [ ! -L "$app" ]; then
    [ -f "$launchctl_stub" ] && [ ! -L "$launchctl_stub" ] \
      && [ -x "$launchctl_stub" ] \
      && [ "$(stat -f '%u' "$launchctl_stub")" = "$(id -u)" ] \
      && [ "$(stat -f '%Lp' "$launchctl_stub")" = 700 ] \
      && [ "$(stat -f '%l' "$launchctl_stub")" = 1 ] \
      || fail "test-root launchctl stub is unsafe"
    "$SRC/scripts/source-doctor.sh" --home "$home" --launchctl "$launchctl_stub"
    return
  fi

  local directory
  for directory in \
    "$home" "$home/Applications" "$home/Library" "$home/Library/LaunchAgents"; do
    [ -d "$directory" ] && [ ! -L "$directory" ] \
      && [ "$(stat -f '%u' "$directory")" = "$(id -u)" ] \
      && [ "$(stat -f '%Lp' "$directory")" = 700 ] || {
        printf '  FAIL  unsafe staging directory: %s\n' "$directory"
        rc=1
      }
  done
  [ -d "$app" ] && [ ! -L "$app" ] || { printf '  FAIL  staged app missing or aliased\n'; rc=1; }
  [ -x "$executable" ] || { printf '  FAIL  staged executable missing\n'; rc=1; }
  [ -f "$plist" ] && [ ! -L "$plist" ] || { printf '  FAIL  staged LaunchAgent missing or aliased\n'; rc=1; }
  if [ "$rc" -eq 0 ]; then
    codesign --verify --strict --verbose=2 "$app" || rc=1
    plutil -lint "$app/Contents/Info.plist" >/dev/null || rc=1
    plutil -lint "$plist" >/dev/null || rc=1
    [ "$(plutil -extract DevMainSyncBuildMode raw "$app/Contents/Info.plist")" = "testing" ] || rc=1
    [ "$(plutil -extract ProgramArguments.0 raw "$plist")" = "$executable" ] || rc=1
    [ "$(plutil -extract ProgramArguments.1 raw "$plist")" = "--managed-host" ] || rc=1
    ! plutil -extract ProgramArguments.2 raw "$plist" >/dev/null 2>&1 || rc=1
    [ "$(plutil -extract RunAtLoad raw "$plist")" = "false" ] || rc=1
    [ "$(plutil -extract KeepAlive raw "$plist")" = "false" ] || rc=1
    [ "$(plutil -extract ProcessType raw "$plist")" = "Interactive" ] || rc=1
  fi
  if [ "$rc" -eq 0 ]; then
    log "test-root doctor OK"
  else
    fail "test-root doctor failed"
  fi
}

case "${1:-}" in
  "")
    reconcile_live
    ;;
  --apply)
    [ "$#" -eq 1 ] || { fail "$1 accepts no additional arguments"; exit 2; }
    reconcile_live
    ;;
  --repair)
    [ "$#" -eq 1 ] || { fail "$1 accepts no additional arguments"; exit 2; }
    build_captured_release --lifecycle-repair
    ;;
  --uninstall)
    [ "$#" -eq 1 ] || { fail "--uninstall accepts no additional arguments"; exit 2; }
    build_captured_release --lifecycle-remove
    ;;
  --check)
    [ "$#" -eq 1 ] || { fail "--check accepts no additional arguments"; exit 2; }
    do_check
    ;;
  --source-identity)
    [ "$#" -eq 1 ] || { fail "--source-identity accepts no additional arguments"; exit 2; }
    capture_source_identity
    printf 'source-revision=%s\nsource-input-sha256=%s\nmetadata-contract-sha256=%s\n' \
      "$SOURCE_REVISION" "$SOURCE_INPUT_SHA256" "$METADATA_CONTRACT_SHA256"
    ;;
  --build-release-check)
    [ "$#" -eq 1 ] || { fail "--build-release-check accepts no additional arguments"; exit 2; }
    build_captured_release --check-only
    ;;
  --doctor)
    if [ "$#" -eq 1 ]; then
      live_doctor
    elif [ "$#" -eq 3 ] && [ "$2" = "--test-root" ]; then
      doctor_test_root "$3"
    else
      fail "usage: install.sh --doctor [--test-root ABSOLUTE_TEMP_PATH]"
      exit 2
    fi
    ;;
  --m1-stage)
    [ "$#" -eq 5 ] && [ "$2" = "--test-root" ] && [ "$4" = "--scratch-path" ] || {
      fail "usage: install.sh --m1-stage --test-root ABSOLUTE_TEMP_PATH --scratch-path ABSOLUTE_PATH"
      exit 2
    }
    stage_m1 "$3" "$5"
    ;;
  -h|--help)
    printf '%s\n' \
      'usage: install.sh' \
      '       install.sh --apply|--repair|--uninstall' \
      '       install.sh --check' \
      '       install.sh --source-identity' \
      '       install.sh --build-release-check' \
      '       install.sh --doctor [--test-root ABSOLUTE_TEMP_PATH]' \
      '       install.sh --m1-stage --test-root ABSOLUTE_TEMP_PATH --scratch-path ABSOLUTE_PATH'
    ;;
  *)
    fail "unsupported command '$1'"
    exit 2
    ;;
esac
