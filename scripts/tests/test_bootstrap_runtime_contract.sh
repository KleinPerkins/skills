#!/usr/bin/env bash
# Regression coverage for the opt-in activation-critical runtime contract.
set -uo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO="$(cd "$SELF/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail=0
pass() { printf '  PASS %s\n' "$1"; }
fail_case() { printf '  FAIL %s\n' "$1"; fail=1; }

make_primary() {
  local root="$1" id="$2" contract="${3:-}"
  mkdir -p "$root/.git" "$root/scripts"
  cp "$REPO/bootstrap.sh" "$root/bootstrap.sh"
  cp "$REPO/scripts/capability_meta.py" "$root/scripts/capability_meta.py"
  make_capability "$root" "$id" "$contract"
  chmod +x "$root/bootstrap.sh"
}

make_capability() {
  local root="$1" id="$2" contract="${3:-}" cap
  cap="$root/global/skills/$id"
  mkdir -p "$cap"
  cat > "$cap/meta.yml" <<EOF
schema: kp-capability/v1
id: $id
kind: skill
flavor: 2
scope: global
owner: test
install: install.sh
post_mgmt: none
expose: cursor claude codex
EOF
  [ -z "$contract" ] || printf 'runtime_contract: %s\n' "$contract" >> "$cap/meta.yml"
  cat > "$cap/SKILL.md" <<EOF
---
name: $id
description: Test fixture for runtime activation behavior.
---
EOF
  cat > "$cap/install.sh" <<'EOF'
#!/usr/bin/env bash
set -u
SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
case "${1:-}" in
  --doctor)
    printf 'doctor\n' >> "$PROBE_LOG"
    [ "${PROBE_DOCTOR_OK:-0}" = 1 ]
    ;;
  "")
    printf 'install\n' >> "$PROBE_LOG"
    if [ "${KP_BOOTSTRAP_MANAGES_EXPOSURE:-0}" != 1 ]; then
      printf 'unmanaged-exposure\n' >> "$PROBE_LOG"
    fi
    if [ "${PROBE_CREATE_LINK_BEFORE_FAIL:-0}" = 1 ]; then
      for tool in cursor claude codex; do
        mkdir -p "$HOME/.$tool/skills"
        ln -sfn "$SRC" "$HOME/.$tool/skills/$(basename "$SRC")"
      done
    fi
    if [ "${PROBE_MUTATE_META_AFTER_PLAN:-0}" = 1 ]; then
      printf 'runtime_contract: unsupported-after-plan/v9\n' >> "$SRC/meta.yml"
    fi
    [ "${PROBE_INSTALL_OK:-0}" = 1 ]
    ;;
  *) exit 2 ;;
esac
EOF
  chmod +x "$cap/install.sh"
}

run_bootstrap() {
  local root="$1" home="$2" log="$3"
  shift 3
  env HOME="$home" PROBE_LOG="$log" "$@"
}

tool_link() {
  local home="$1" tool="$2" id="$3"
  printf '%s/.%s/skills/%s\n' "$home" "$tool" "$id"
}

no_links_for() {
  local home="$1" id="$2" tool link
  for tool in cursor claude codex; do
    link="$(tool_link "$home" "$tool" "$id")"
    { [ -e "$link" ] || [ -L "$link" ]; } && return 1
  done
  return 0
}

correct_link() {
  local home="$1" tool="$2" id="$3" target="$4" link
  link="$(tool_link "$home" "$tool" "$id")"
  [ -L "$link" ] && [ "$link" -ef "$target" ]
}

exact_link() {
  local home="$1" tool="$2" id="$3" target="$4" link
  link="$(tool_link "$home" "$tool" "$id")"
  [ -L "$link" ] && [ "$(readlink "$link")" = "$target" ]
}

create_correct_links() {
  local home="$1" id="$2" target="$3" tool link
  for tool in cursor claude codex; do
    link="$(tool_link "$home" "$tool" "$id")"
    mkdir -p "$(dirname "$link")"
    ln -s "$target" "$link"
  done
}

STRICT="$TMP/strict"
STRICT_HOME="$TMP/strict-home"
STRICT_LOG="$TMP/strict.log"
mkdir -p "$STRICT_HOME"
make_primary "$STRICT" runtime-probe installer-doctor/v1

strict_install_out="$(
  run_bootstrap "$STRICT" "$STRICT_HOME" "$STRICT_LOG" \
    PROBE_INSTALL_OK=0 bash "$STRICT/bootstrap.sh" --reconcile 2>&1
)"
strict_install_rc=$?
if [ "$strict_install_rc" -ne 0 ] &&
  printf '%s\n' "$strict_install_out" | grep -q 'activation-critical runtime runtime-probe' &&
  no_links_for "$STRICT_HOME" runtime-probe; then
  pass "opted-in reconcile failure propagates without new links"
else
  fail_case "opted-in reconcile failure propagates without new links (rc=$strict_install_rc)"
  printf '%s\n' "$strict_install_out"
fi

strict_repair_out="$(
  run_bootstrap "$STRICT" "$STRICT_HOME" "$STRICT_LOG" \
    PROBE_INSTALL_OK=0 bash "$STRICT/bootstrap.sh" --repair 2>&1
)"
strict_repair_rc=$?
if [ "$strict_repair_rc" -ne 0 ] && no_links_for "$STRICT_HOME" runtime-probe; then
  pass "opted-in repair failure propagates without new links"
else
  fail_case "opted-in repair failure propagates without new links (rc=$strict_repair_rc)"
  printf '%s\n' "$strict_repair_out"
fi

: > "$STRICT_LOG"
strict_reconcile_out="$(
  run_bootstrap "$STRICT" "$STRICT_HOME" "$STRICT_LOG" \
    PROBE_INSTALL_OK=1 bash "$STRICT/bootstrap.sh" --reconcile 2>&1
)"
strict_reconcile_rc=$?
if [ "$strict_reconcile_rc" -eq 0 ] &&
  correct_link "$STRICT_HOME" cursor runtime-probe "$STRICT/global/skills/runtime-probe" &&
  correct_link "$STRICT_HOME" claude runtime-probe "$STRICT/global/skills/runtime-probe" &&
  correct_link "$STRICT_HOME" codex runtime-probe "$STRICT/global/skills/runtime-probe"; then
  pass "opted-in installer success reconciles"
else
  fail_case "opted-in installer success reconciles (rc=$strict_reconcile_rc)"
  printf '%s\n' "$strict_reconcile_out"
fi

: > "$STRICT_LOG"
strict_doctor_out="$(
  run_bootstrap "$STRICT" "$STRICT_HOME" "$STRICT_LOG" \
    PROBE_DOCTOR_OK=0 bash "$STRICT/bootstrap.sh" --doctor 2>&1
)"
strict_doctor_rc=$?
if [ "$strict_doctor_rc" -ne 0 ] &&
  grep -qx 'doctor' "$STRICT_LOG" &&
  printf '%s\n' "$strict_doctor_out" | grep -q 'activation-critical runtime doctor failed'; then
  pass "opted-in doctor invokes installer and propagates failure"
else
  fail_case "opted-in doctor invokes installer and propagates failure (rc=$strict_doctor_rc)"
  printf '%s\n' "$strict_doctor_out"
fi

ROLLBACK="$TMP/rollback"
ROLLBACK_HOME="$TMP/rollback-home"
ROLLBACK_LOG="$TMP/rollback.log"
mkdir -p "$ROLLBACK_HOME"
make_primary "$ROLLBACK" rollback-probe installer-doctor/v1
rollback_out="$(
  run_bootstrap "$ROLLBACK" "$ROLLBACK_HOME" "$ROLLBACK_LOG" \
    PROBE_CREATE_LINK_BEFORE_FAIL=1 PROBE_INSTALL_OK=0 \
    bash "$ROLLBACK/bootstrap.sh" --reconcile 2>&1
)"
rollback_rc=$?
if [ "$rollback_rc" -ne 0 ] &&
  no_links_for "$ROLLBACK_HOME" rollback-probe &&
  printf '%s\n' "$rollback_out" | grep -q 'ROLLBACK.*new activation link'; then
  pass "failed installer rolls back links it created"
else
  fail_case "failed installer rolls back links it created (rc=$rollback_rc)"
  printf '%s\n' "$rollback_out"
fi

PREEXISTING="$TMP/preexisting"
PREEXISTING_HOME="$TMP/preexisting-home"
PREEXISTING_LOG="$TMP/preexisting.log"
PREEXISTING_CAP="$PREEXISTING/global/skills/preexisting-probe"
mkdir -p "$PREEXISTING_HOME/.cursor/skills"
make_primary "$PREEXISTING" preexisting-probe installer-doctor/v1
ln -s "$PREEXISTING_CAP" "$PREEXISTING_HOME/.cursor/skills/preexisting-probe"
preexisting_out="$(
  run_bootstrap "$PREEXISTING" "$PREEXISTING_HOME" "$PREEXISTING_LOG" \
    PROBE_INSTALL_OK=0 bash "$PREEXISTING/bootstrap.sh" --reconcile 2>&1
)"
preexisting_rc=$?
if [ "$preexisting_rc" -ne 0 ] &&
  correct_link "$PREEXISTING_HOME" cursor preexisting-probe "$PREEXISTING_CAP" &&
  [ ! -e "$(tool_link "$PREEXISTING_HOME" claude preexisting-probe)" ] &&
  [ ! -e "$(tool_link "$PREEXISTING_HOME" codex preexisting-probe)" ]; then
  pass "failed activation preserves a pre-existing correct link only"
else
  fail_case "failed activation preserves a pre-existing correct link only (rc=$preexisting_rc)"
  printf '%s\n' "$preexisting_out"
fi

COLLISION="$TMP/collision"
COLLISION_HOME="$TMP/collision-home"
COLLISION_LOG="$TMP/collision.log"
COLLISION_PATH="$COLLISION_HOME/.cursor/skills/collision-probe"
mkdir -p "$COLLISION_PATH"
printf 'operator-owned\n' > "$COLLISION_PATH/keep"
make_primary "$COLLISION" collision-probe installer-doctor/v1
for action in reconcile repair; do
  : > "$COLLISION_LOG"
  collision_out="$(
    run_bootstrap "$COLLISION" "$COLLISION_HOME" "$COLLISION_LOG" \
      PROBE_INSTALL_OK=1 bash "$COLLISION/bootstrap.sh" "--$action" 2>&1
  )"
  collision_rc=$?
  if [ "$collision_rc" -ne 0 ] &&
    [ -f "$COLLISION_PATH/keep" ] &&
    [ ! -s "$COLLISION_LOG" ] &&
    [ ! -e "$(tool_link "$COLLISION_HOME" claude collision-probe)" ] &&
    [ ! -e "$(tool_link "$COLLISION_HOME" codex collision-probe)" ] &&
    printf '%s\n' "$collision_out" | grep -q 'activation preflight'; then
    pass "opted-in $action rejects real-path collision without partial exposure"
  else
    fail_case "opted-in $action rejects real-path collision without partial exposure (rc=$collision_rc)"
    printf '%s\n' "$collision_out"
  fi
done

LEGACY="$TMP/legacy"
LEGACY_HOME="$TMP/legacy-home"
LEGACY_LOG="$TMP/legacy.log"
mkdir -p "$LEGACY_HOME"
make_primary "$LEGACY" legacy-runtime

legacy_out="$(
  run_bootstrap "$LEGACY" "$LEGACY_HOME" "$LEGACY_LOG" \
    PROBE_INSTALL_OK=0 bash "$LEGACY/bootstrap.sh" --reconcile 2>&1
)"
legacy_rc=$?
if [ "$legacy_rc" -eq 0 ] &&
  printf '%s\n' "$legacy_out" | grep -q 'install.sh non-zero for legacy-runtime (continuing)' &&
  correct_link "$LEGACY_HOME" cursor legacy-runtime "$LEGACY/global/skills/legacy-runtime" &&
  correct_link "$LEGACY_HOME" claude legacy-runtime "$LEGACY/global/skills/legacy-runtime" &&
  correct_link "$LEGACY_HOME" codex legacy-runtime "$LEGACY/global/skills/legacy-runtime"; then
  pass "omitted optional runtime contract preserves legacy advisory installation"
else
  fail_case "omitted optional runtime contract preserves legacy advisory installation (rc=$legacy_rc)"
  printf '%s\n' "$legacy_out"
fi

: > "$LEGACY_LOG"
legacy_doctor_out="$(
  run_bootstrap "$LEGACY" "$LEGACY_HOME" "$LEGACY_LOG" \
    PROBE_DOCTOR_OK=0 bash "$LEGACY/bootstrap.sh" --doctor 2>&1
)"
legacy_doctor_rc=$?
if [ "$legacy_doctor_rc" -eq 0 ] && [ ! -s "$LEGACY_LOG" ]; then
  pass "omitted optional runtime contract preserves legacy doctor behavior"
else
  fail_case "omitted optional runtime contract preserves legacy doctor behavior (rc=$legacy_doctor_rc)"
  printf '%s\n' "$legacy_doctor_out"
fi

if grep -q 'scripts/capability_meta.py' "$REPO/bootstrap.sh" &&
  grep -q 'scripts/capability_meta.py' "$REPO/.github/scripts/verify-skills.sh"; then
  pass "bootstrap and repository verifier invoke the shared metadata parser"
else
  fail_case "bootstrap and repository verifier invoke the shared metadata parser"
fi

exercise_invalid_contract() {
  local name="$1" metadata="$2" root home log cap valid_id
  local stale_source stale_link
  local registry registry_expected action out rc
  local -a action_args
  root="$TMP/invalid-$name"
  home="$TMP/invalid-$name-home"
  log="$TMP/invalid-$name.log"
  cap="$root/global/skills/invalid-$name"
  stale_source="$root/global/skills/unrelated-stale-source"
  stale_link="$home/.cursor/skills/unrelated-stale-$name"
  registry="$home/capability-local.yml"
  registry_expected="$TMP/invalid-$name-registry-expected.yml"
  mkdir -p "$home" "$stale_source"
  make_primary "$root" "invalid-$name"
  valid_id="aaa-valid-$name"
  make_capability "$root" "$valid_id"
  mkdir -p "$root/scripts"
  cp "$REPO/scripts/capability-local.py" "$root/scripts/capability-local.py"
  printf '%b\n' "$metadata" >> "$cap/meta.yml"
  create_correct_links "$home" "invalid-$name" "$cap"
  ln -s "$stale_source" "$stale_link"
  printf 'schema: kp-capability-local/v1\nopt_out:\n  - preserve-me\n' > "$registry"
  cp "$registry" "$registry_expected"

  for action in install reconcile repair doctor reconcile-dry-run; do
    case "$action" in
      install) action_args=(--install) ;;
      reconcile) action_args=(--reconcile) ;;
      repair) action_args=(--repair) ;;
      doctor) action_args=(--doctor) ;;
      reconcile-dry-run) action_args=(--reconcile --dry-run) ;;
    esac
    : > "$log"
    out="$(
      run_bootstrap "$root" "$home" "$log" \
        CAPABILITY_LOCAL_REGISTRY="$registry" \
        PROBE_INSTALL_OK=1 PROBE_DOCTOR_OK=1 \
        bash "$root/bootstrap.sh" "${action_args[@]}" --reset-local-config 2>&1
    )"
    rc=$?
    if [ "$rc" -ne 0 ] &&
      [ ! -s "$log" ] &&
      cmp -s "$registry" "$registry_expected" &&
      exact_link "$home" cursor "invalid-$name" "$cap" &&
      exact_link "$home" claude "invalid-$name" "$cap" &&
      exact_link "$home" codex "invalid-$name" "$cap" &&
      no_links_for "$home" "$valid_id" &&
      [ -L "$stale_link" ] &&
      [ "$(readlink "$stale_link")" = "$stale_source" ] &&
      ! printf '%s\n' "$out" | grep -q 'reset  machine-local' &&
      printf '%s\n' "$out" | grep -q 'action-plan preflight made no changes'; then
      pass "$name multi-manifest $action fails before every mutation"
    else
      fail_case "$name multi-manifest $action fails before every mutation (rc=$rc)"
      printf '%s\n' "$out"
    fi
  done
}

exercise_invalid_contract colon-key 'runtime:contract: installer-doctor/v1'

exercise_ancestor_collision() {
  local action="$1" root="$TMP/ancestor-$1" home="$TMP/ancestor-$1-home"
  local log="$TMP/ancestor-$1.log" id="ancestor-$1" cap cursor stale stale_source
  local prior_target out rc
  mkdir -p "$home/.cursor/skills"
  make_primary "$root" "$id" installer-doctor/v1
  cap="$root/global/skills/$id"
  cursor="$(tool_link "$home" cursor "$id")"
  if [ "$action" = reconcile ]; then
    prior_target="$TMP/old absolute target $action"
    mkdir -p "$prior_target"
  else
    prior_target="../../old relative target $action"
  fi
  ln -s "$prior_target" "$cursor"
  printf 'operator-owned-ancestor\n' > "$home/.claude"
  stale_source="$root/global/skills/unrelated-stale"
  stale="$home/.cursor/skills/unrelated-stale"
  mkdir -p "$stale_source"
  ln -s "$stale_source" "$stale"

  out="$(
    run_bootstrap "$root" "$home" "$log" \
      PROBE_INSTALL_OK=1 bash "$root/bootstrap.sh" "--$action" 2>&1
  )"
  rc=$?
  if [ "$rc" -ne 0 ] &&
    exact_link "$home" cursor "$id" "$prior_target" &&
    [ "$(cat "$home/.claude")" = operator-owned-ancestor ] &&
    [ ! -e "$(tool_link "$home" codex "$id")" ] &&
    [ -L "$stale" ] &&
    [ ! -s "$log" ] &&
    printf '%s\n' "$out" | grep -q 'NOT a directory (activation preflight)'; then
    pass "$action rejects ancestor-file collision before every mutation"
  else
    fail_case "$action ancestor-file collision is atomic (rc=$rc)"
    printf '%s\n' "$out"
  fi
}

for action in install reconcile repair; do
  exercise_ancestor_collision "$action"
done

exercise_publication_failure() {
  local action="$1" fail_at="$2"
  local root="$TMP/publish-$action-$fail_at"
  local home="$TMP/publish-$action-$fail_at-home"
  local log="$TMP/publish-$action-$fail_at.log"
  local fake_bin="$TMP/publish-$action-$fail_at-bin"
  local id="publish-$action-$fail_at" cursor_target claude_target
  local stale stale_source out rc
  mkdir -p "$home/.cursor/skills" "$home/.claude/skills" "$fake_bin"
  make_primary "$root" "$id" installer-doctor/v1
  cursor_target="../../old relative target $action $fail_at"
  claude_target="$TMP/old absolute target $action $fail_at"
  mkdir -p "$claude_target"
  ln -s "$cursor_target" "$(tool_link "$home" cursor "$id")"
  ln -s "$claude_target" "$(tool_link "$home" claude "$id")"
  stale_source="$root/global/skills/unrelated-stale"
  stale="$home/.cursor/skills/unrelated-stale"
  mkdir -p "$stale_source"
  ln -s "$stale_source" "$stale"
  cat > "$fake_bin/ln" <<'EOF'
#!/usr/bin/env bash
set -u
count=0
[ ! -f "$LINK_FAIL_COUNT" ] || count="$(cat "$LINK_FAIL_COUNT")"
count=$((count + 1))
printf '%s\n' "$count" > "$LINK_FAIL_COUNT"
if [ "$count" -eq "$LINK_FAIL_AT" ] && [ ! -f "$LINK_FAIL_ONCE" ]; then
  : > "$LINK_FAIL_ONCE"
  exit 75
fi
exec /bin/ln "$@"
EOF
  chmod +x "$fake_bin/ln"

  out="$(
    run_bootstrap "$root" "$home" "$log" \
      PATH="$fake_bin:$PATH" LINK_FAIL_AT="$fail_at" \
      LINK_FAIL_COUNT="$TMP/publish-$action-$fail_at.count" \
      LINK_FAIL_ONCE="$TMP/publish-$action-$fail_at.once" \
      PROBE_INSTALL_OK=1 bash "$root/bootstrap.sh" "--$action" 2>&1
  )"
  rc=$?
  if [ "$rc" -ne 0 ] &&
    exact_link "$home" cursor "$id" "$cursor_target" &&
    exact_link "$home" claude "$id" "$claude_target" &&
    [ ! -e "$(tool_link "$home" codex "$id")" ] &&
    [ -L "$stale" ] &&
    grep -qx install "$log" &&
    ! grep -q unmanaged-exposure "$log" &&
    printf '%s\n' "$out" | grep -q 'ROLLBACK'; then
    pass "$action link-step $fail_at restores exact prior publication state"
  else
    fail_case "$action link-step $fail_at rollback is exact (rc=$rc)"
    printf '%s\n' "$out"
  fi
}

for fail_at in 1 2 3; do
  exercise_publication_failure reconcile "$fail_at"
done

PLAN_ONCE="$TMP/plan once"
PLAN_ONCE_HOME="$TMP/plan once home"
PLAN_ONCE_LOG="$TMP/plan-once.log"
PLAN_ONCE_COUNT="$TMP/plan-once.count"
mkdir -p "$PLAN_ONCE_HOME"
make_primary "$PLAN_ONCE" runtime-plan installer-doctor/v1
make_capability "$PLAN_ONCE" aaa-legacy-plan
mv "$PLAN_ONCE/scripts/capability_meta.py" \
  "$PLAN_ONCE/scripts/capability_meta.real.py"
cat > "$PLAN_ONCE/scripts/capability_meta.py" <<'PY'
#!/usr/bin/env python3
import os
import pathlib
import sys

counter = pathlib.Path(os.environ["PLAN_PARSER_COUNT"])
count = int(counter.read_text() or "0") if counter.exists() else 0
count += 1
counter.write_text(str(count))
if count > 1:
    raise SystemExit(91)
real = pathlib.Path(__file__).with_name("capability_meta.real.py")
os.execv(sys.executable, [sys.executable, str(real), *sys.argv[1:]])
PY
plan_once_out="$(
  run_bootstrap "$PLAN_ONCE" "$PLAN_ONCE_HOME" "$PLAN_ONCE_LOG" \
    PLAN_PARSER_COUNT="$PLAN_ONCE_COUNT" PROBE_INSTALL_OK=1 \
    PROBE_MUTATE_META_AFTER_PLAN=1 \
    bash "$PLAN_ONCE/bootstrap.sh" --reconcile 2>&1
)"
plan_once_rc=$?
if [ "$plan_once_rc" -eq 0 ] &&
  [ "$(cat "$PLAN_ONCE_COUNT")" = 1 ] &&
  correct_link "$PLAN_ONCE_HOME" cursor runtime-plan \
    "$PLAN_ONCE/global/skills/runtime-plan" &&
  correct_link "$PLAN_ONCE_HOME" cursor aaa-legacy-plan \
    "$PLAN_ONCE/global/skills/aaa-legacy-plan"; then
  pass "one parser call and immutable plan survive post-plan metadata corruption"
else
  fail_case "parser is invoked only during preflight (rc=$plan_once_rc)"
  printf '%s\n' "$plan_once_out"
fi

exercise_bad_plan() {
  local mode="$1" root="$TMP/bad-plan-$1" home="$TMP/bad-plan-$1-home"
  local log="$TMP/bad-plan-$1.log" id="bad-plan-$1" prior out rc
  local registry="$TMP/bad-plan-$1-registry.yml"
  local expected="$TMP/bad-plan-$1-registry-expected.yml"
  local stale_source="$root/global/skills/unrelated-stale"
  local stale="$home/.cursor/skills/unrelated-stale"
  mkdir -p "$home/.cursor/skills"
  make_primary "$root" "$id" installer-doctor/v1
  cp "$REPO/scripts/capability-local.py" "$root/scripts/capability-local.py"
  prior="../../prior target $mode"
  ln -s "$prior" "$(tool_link "$home" cursor "$id")"
  mkdir -p "$stale_source"
  ln -s "$stale_source" "$stale"
  printf 'schema: kp-capability-local/v1\nopt_out:\n  - preserve-me\n' > "$registry"
  cp "$registry" "$expected"
  cat > "$root/scripts/capability_meta.py" <<PY
#!/usr/bin/env python3
import sys
sys.stdout.buffer.write(b"kp-capability-plan/v1\\0" + b"1\\0" + b"truncated")
raise SystemExit(${mode})
PY
  out="$(
    run_bootstrap "$root" "$home" "$log" \
      CAPABILITY_LOCAL_REGISTRY="$registry" PROBE_INSTALL_OK=1 \
      bash "$root/bootstrap.sh" --reconcile --reset-local-config 2>&1
  )"
  rc=$?
  if [ "$rc" -ne 0 ] &&
    exact_link "$home" cursor "$id" "$prior" &&
    cmp -s "$registry" "$expected" &&
    [ -L "$stale" ] &&
    [ ! -s "$log" ] &&
    [ ! -e "$(tool_link "$home" claude "$id")" ] &&
    [ ! -e "$(tool_link "$home" codex "$id")" ] &&
    printf '%s\n' "$out" | grep -q 'action-plan'; then
    pass "helper exit $mode leaves publication untouched"
  else
    fail_case "helper exit $mode is fail-before-mutation (rc=$rc)"
    printf '%s\n' "$out"
  fi
}

exercise_bad_plan 0
exercise_bad_plan 73

RULE="$TMP/rule"
RULE_HOME="$TMP/rule-home"
RULE_CAP="$RULE/global/rules/runtime-rule"
mkdir -p "$RULE_CAP" "$RULE_HOME" "$RULE/scripts" "$RULE/.git"
cp "$REPO/bootstrap.sh" "$RULE/bootstrap.sh"
cp "$REPO/scripts/capability_meta.py" "$RULE/scripts/capability_meta.py"
cat > "$RULE_CAP/meta.yml" <<'EOF'
schema: kp-capability/v1
id: runtime-rule
kind: rule
flavor: 1
scope: global
owner: test
install: install.sh
post_mgmt: none
runtime_contract: installer-doctor/v1
expose: cursor
EOF
printf '# runtime rule fixture\n' > "$RULE_CAP/runtime-rule.mdc"
cat > "$RULE_CAP/install.sh" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
  "") exit 0 ;;
  --doctor)
    printf 'RULE_RUNTIME_DIAGNOSTIC: fixture is unhealthy\n'
    exit 41
    ;;
  *) exit 2 ;;
esac
EOF
chmod +x "$RULE/bootstrap.sh" "$RULE_CAP/install.sh"
rule_reconcile_out="$(HOME="$RULE_HOME" bash "$RULE/bootstrap.sh" --reconcile 2>&1)"
rule_reconcile_rc=$?
if [ "$rule_reconcile_rc" -eq 0 ] &&
  [ -L "$RULE_HOME/.cursor/rules/runtime-rule.mdc" ]; then
  pass "opted-in rule reconciles before doctor fixture"
else
  fail_case "opted-in rule reconciles before doctor fixture (rc=$rule_reconcile_rc)"
  printf '%s\n' "$rule_reconcile_out"
fi
rule_doctor_out="$(HOME="$RULE_HOME" bash "$RULE/bootstrap.sh" --doctor 2>&1)"
rule_doctor_rc=$?
if [ "$rule_doctor_rc" -ne 0 ] &&
  printf '%s\n' "$rule_doctor_out" | grep -q 'RULE_RUNTIME_DIAGNOSTIC' &&
  printf '%s\n' "$rule_doctor_out" | grep -q 'activation-critical runtime doctor failed'; then
  pass "opted-in rule doctor preserves actionable diagnostics"
else
  fail_case "opted-in rule doctor preserves actionable diagnostics (rc=$rule_doctor_rc)"
  printf '%s\n' "$rule_doctor_out"
fi


# INT-005/006: exercise the shipped snapshots and both entrypoints in disposable
# homes. No native client, user configuration, or upstream fetch participates.
if PYTHONDONTWRITEBYTECODE=1 python3 - "$REPO" "$TMP" <<'PY_SKILLS'
import os
from pathlib import Path
import shutil
import subprocess
import sys

repo, temporary = (Path(value).resolve() for value in sys.argv[1:])
root = temporary / "required skills source"
root.mkdir()
(root / ".git").mkdir()
(root / "scripts").mkdir()
for relative in ("bootstrap.sh", "scripts/capability_meta.py", "scripts/capability-local.py"):
    shutil.copy2(repo / relative, root / relative)
skills = ("prompt-architect", "verification-before-completion")
for name in skills:
    shutil.copytree(repo / "global/skills" / name, root / "global/skills" / name)


def snapshot(home):
    result = {}
    for path in home.rglob("*"):
        if path.is_symlink():
            st = path.lstat()
            result[str(path.relative_to(home))] = ("link", os.readlink(path), st.st_ino, st.st_mtime_ns)
        elif path.is_file():
            result[str(path.relative_to(home))] = ("file", path.read_bytes())
        elif path.is_dir():
            result[str(path.relative_to(home))] = ("directory",)
    return result


def prepare_home(label):
    home = temporary / label
    home.mkdir()
    (home / ".codex").mkdir()
    # A native opt-out and unknown settings are opaque user-owned bytes here.
    (home / ".codex/config.toml").write_text(
        'unmanaged_setting = "preserve"\n[[skills.config]]\n'
        + "".join(f'path = "{name}"\nenabled = false\n' +
                  ('[[skills.config]]\n' if index == 0 else '')
                  for index, name in enumerate(skills))
    )
    (home / ".agents/skills").mkdir(parents=True)
    (home / ".agents/skills/imported").symlink_to(temporary / "unknown import")
    (home / ".codex/plugins/cache").mkdir(parents=True)
    (home / ".codex/plugins/cache/keep").write_text("externally owned\n")
    return home


def run(home, entry, *args):
    environment = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
                       CAPABILITY_LOCAL_REGISTRY=str(home / "capability-local.yml"))
    command = ["bash", str(root / entry), *args]
    result = subprocess.run(command, env=environment, text=True, capture_output=True)
    assert result.returncode == 0, (command, result.stdout, result.stderr)
    return result.stdout


def entries(mode):
    return ["bootstrap.sh"] if mode == "bootstrap" else [f"global/skills/{name}/install.sh" for name in skills]


def apply(home, mode, preview=False):
    output = []
    for entry in entries(mode):
        args = ["--reconcile"] if mode == "bootstrap" else []
        if preview:
            args.append("--dry-run")
        output.append(run(home, entry, *args))
    return "\n".join(output)


for mode in ("bootstrap", "standalone"):
    home = prepare_home(mode + " clean home")
    preserved = snapshot(home)
    assert not (home / ".cursor").exists()
    apply(home, mode, preview=True)
    assert snapshot(home) == preserved, f"{mode} preview changed home"
    apply(home, mode)
    for name in skills:
        for tool in ("cursor", "codex"):
            link = home / f".{tool}/skills" / name
            assert link.is_symlink() and os.readlink(link) == str(root / "global/skills" / name), (mode, link)
        assert not os.path.lexists(home / ".claude/skills" / name), (mode, name, "unexpected Claude exposure")
    assert all(snapshot(home).get(k) == v for k, v in preserved.items()), mode
    first = snapshot(home)
    apply(home, mode)
    assert snapshot(home) == first, f"{mode} second application rewrote an existing link"
    # Crossing entrypoints must also be an exact no-op.
    apply(home, "standalone" if mode == "bootstrap" else "bootstrap")
    assert snapshot(home) == first, f"{mode} entrypoints disagree"
    print(f"  PASS required skills {mode}: preview, clean install, parity, exact no-op, unmanaged state")

    for collision in ("directory", "foreign-link", "dangling-link", "alias-to-source"):
        home = prepare_home(mode + " " + collision)
        for name in skills:
            link = home / ".codex/skills" / name
            link.parent.mkdir(exist_ok=True)
            if collision == "directory":
                link.mkdir()
                (link / "keep").write_text("operator-owned\n")
            else:
                target = temporary / (collision + " " + name)
                if collision == "foreign-link":
                    target.mkdir(exist_ok=True)
                elif collision == "alias-to-source" and not target.is_symlink():
                    target.symlink_to(root / "global/skills" / name)
                link.symlink_to(target)
        before = snapshot(home)
        preview = apply(home, mode, preview=True)
        for name in skills:
            conflict_path = str(home / ".codex/skills" / name)
            assert any(conflict_path in line and "skip" in line.lower()
                       for line in preview.splitlines()), (mode, collision, "conflict not reported", preview)
        assert snapshot(home) == before, (mode, collision, "preview changed conflict")
        apply(home, mode)
        assert all(snapshot(home).get(k) == v for k, v in before.items()), (mode, collision)
        print(f"  PASS required skills {mode}: preserves {collision}")

# Existing metadata grammar must mean the same thing to standalone installers.
for exposure in ("cursor,codex", "[cursor, codex]", "none"):
    for name in skills:
        metadata = root / "global/skills" / name / "meta.yml"
        metadata.write_text("\n".join(
            "expose: " + exposure if line.startswith("expose:") else line
            for line in metadata.read_text().splitlines()
        ) + "\n")
    home = prepare_home("grammar " + exposure)
    apply(home, "standalone")
    for name in skills:
        for tool in ("cursor", "codex"):
            assert os.path.lexists(home / f".{tool}/skills" / name) == (exposure != "none")
    print(f"  PASS required skills standalone metadata grammar: {exposure}")
PY_SKILLS
then
  pass "required skill exposure contract"
else
  fail_case "required skill exposure contract"
fi

exit "$fail"
