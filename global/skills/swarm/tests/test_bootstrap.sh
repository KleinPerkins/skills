#!/usr/bin/env bash
set -uo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILL="$(cd "$SELF/.." && pwd)"
REPO="$(cd "$SELF/../../../.." && pwd)"
if [ ! -f "$REPO/bootstrap.sh" ] || \
   [ ! -d "$REPO/global/sub-agents/swarm-probe" ] || \
   [ ! -d "$REPO/global/sub-agents/swarm-reviewer" ] || \
   [ ! -d "$REPO/global/sub-agents/swarm-verifier" ]; then
  printf '  SKIP source-repository bootstrap integration is unavailable in vendored payload\n'
  exit 0
fi
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# Intercept native/network entrypoints explicitly; temporary HOME alone is not isolation.
# Disable global Git hooks/config for the disposable repository commits below.
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
mkdir -p "$TMP/blocked-bin"
export BOOTSTRAP_NATIVE_CALLS="$TMP/native-calls"
for blocked_command in launchctl osascript defaults security open curl wget pip pip3; do
  cat > "$TMP/blocked-bin/$blocked_command" <<'EOF'
#!/bin/sh
printf '%s\n' "$0" >> "$BOOTSTRAP_NATIVE_CALLS"
exit 86
EOF
  chmod +x "$TMP/blocked-bin/$blocked_command"
done
export PATH="$TMP/blocked-bin:$PATH"
PROJECTION="$TMP/repo"
mkdir -p \
  "$PROJECTION/global/skills" \
  "$PROJECTION/global/rules" \
  "$PROJECTION/global/sub-agents" \
  "$PROJECTION/global/tools" \
  "$PROJECTION/scripts"
cp "$REPO/bootstrap.sh" "$PROJECTION/bootstrap.sh"
cp "$REPO/scripts/capability_meta.py" "$PROJECTION/scripts/capability_meta.py"
cp -R "$SKILL" "$PROJECTION/global/skills/swarm"
cp -R "$REPO/global/skills/agent-route" "$PROJECTION/global/skills/agent-route"
cp -R "$REPO/global/skills/ecosystem-search" "$PROJECTION/global/skills/ecosystem-search"
cp -R "$REPO/global/tools/ecosystem-index" "$PROJECTION/global/tools/ecosystem-index"
cp -R \
  "$REPO/global/rules/subagent-orchestration" \
  "$PROJECTION/global/rules/subagent-orchestration"
for agent in swarm-probe swarm-reviewer swarm-verifier; do
  cp -R "$REPO/global/sub-agents/$agent" "$PROJECTION/global/sub-agents/$agent"
done
: > "$PROJECTION/.git"
BOOTSTRAP_SKILL="$PROJECTION/global/skills/swarm"
BOOTSTRAP_AGENT_ROUTE="$PROJECTION/global/skills/agent-route"
BOOTSTRAP_SEARCH="$PROJECTION/global/skills/ecosystem-search"
RUNTIME_MODELS="$(python3 -c 'import json,sys; t=json.load(open(sys.argv[1]))["tiers"]; print(json.dumps(sorted({m for s in t.values() for m in s["candidates"]})))' "$REPO/global/rules/subagent-orchestration/model-tiers.json")"

fail=0
pass() { printf '  PASS %s\n' "$1"; }
fail_case() { printf '  FAIL %s\n' "$1"; fail=1; }

assert_link() {
  local link="$1" target="$2" name="$3"
  if [ -L "$link" ] && [ "$link" -ef "$target" ]; then
    pass "$name"
  else
    fail_case "$name (got $(readlink "$link" 2>/dev/null || printf missing))"
  fi
}

tree_bytes_digest() {
  python3 - "$1" <<'PY'
import hashlib
import os
import stat
import sys
from pathlib import Path

root = Path(sys.argv[1])
digest = hashlib.sha256()
for path in sorted(root.rglob("*"), key=lambda item: str(item.relative_to(root))):
    relative = path.relative_to(root)
    if ".git" in relative.parts:
        continue
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        kind = b"L"
        payload = os.readlink(path).encode("utf-8")
    elif stat.S_ISREG(info.st_mode):
        kind = b"F"
        payload = path.read_bytes()
    elif stat.S_ISDIR(info.st_mode):
        kind = b"D"
        payload = b""
    else:
        kind = b"O"
        payload = b""
    digest.update(str(relative).encode("utf-8") + b"\0")
    digest.update(kind + b"\0")
    digest.update(("%o" % stat.S_IMODE(info.st_mode)).encode("ascii") + b"\0")
    digest.update(payload + b"\0")
print(digest.hexdigest())
PY
}

projection_digest() {
  python3 - "$1" <<'PY'
import hashlib
import os
import stat
import sys
from pathlib import Path

home = Path(sys.argv[1])
roots = (
    ".cursor/skills",
    ".cursor/rules",
    ".cursor/agents",
    ".claude/skills",
    ".claude/agents",
    ".codex/skills",
    ".codex/agents",
    ".local/share/bootstrap-fixture",
)
paths = []
for relative in roots:
    base = home / relative
    if not base.exists() and not base.is_symlink():
        continue
    paths.append(base)
    if base.is_dir() and not base.is_symlink():
        paths.extend(base.rglob("*"))
digest = hashlib.sha256()
for path in sorted(set(paths), key=lambda item: str(item.relative_to(home))):
    relative = path.relative_to(home)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        kind = b"L"
        payload = os.readlink(path).encode("utf-8")
    elif stat.S_ISREG(info.st_mode):
        kind = b"F"
        payload = path.read_bytes()
    elif stat.S_ISDIR(info.st_mode):
        kind = b"D"
        payload = b""
    else:
        kind = b"O"
        payload = b""
    digest.update(str(relative).encode("utf-8") + b"\0")
    digest.update(kind + b"\0")
    digest.update(("%o" % stat.S_IMODE(info.st_mode)).encode("ascii") + b"\0")
    digest.update(payload + b"\0")
print(digest.hexdigest())
PY
}

ordered_link_map() {
  local home="$1" path
  for path in \
    "$home"/.cursor/skills/* \
    "$home"/.cursor/rules/* \
    "$home"/.cursor/agents/* \
    "$home"/.claude/skills/* \
    "$home"/.claude/agents/* \
    "$home"/.codex/skills/* \
    "$home"/.codex/agents/*; do
    [ -L "$path" ] || continue
    printf '%s\t%s\n' "${path#"$home"/}" "$(readlink "$path")"
  done | LC_ALL=C sort
}

init_skills_fixture() {
  local root="$1" tool
  tool="$root/global/tools/fixture-pointer"
  mkdir -p "$(dirname "$root")"
  cp -R "$PROJECTION" "$root" || return 1
  rm -f "$root/.git"
  mkdir -p "$tool"
  cat > "$tool/meta.yml" <<'EOF'
schema: kp-capability/v1
id: fixture-pointer
kind: tool
flavor: 2
scope: global
owner: Bootstrap Test
install: install.sh
post_mgmt: pointer
shape: descriptor-only
expose: cursor claude codex
EOF
  cat > "$tool/install.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd -P)"
POINTER="${XDG_DATA_HOME:-$HOME/.local/share}/bootstrap-fixture/source.txt"
BACKUP="${POINTER}.before-e01"
mkdir -p "$(dirname "$POINTER")"
STAGE="${POINTER}.tmp.$$"
trap 'rm -f "$STAGE"' EXIT
printf '%s\n' "$SRC" > "$STAGE"
if [ -f "$POINTER" ] && cmp -s "$POINTER" "$STAGE"; then
  exit 0
fi
if [ -e "$POINTER" ] && [ ! -e "$BACKUP" ]; then
  cp -p "$POINTER" "$BACKUP"
fi
mv "$STAGE" "$POINTER"
EOF
  chmod +x "$tool/install.sh"
  cat > "$tool/tool.yml" <<'EOF'
schema: kp-tool/v1
id: fixture-pointer
name: Bootstrap fixture pointer
scope: global
shape: descriptor-only
entrypoint: install.sh
EOF
  git init -q "$root" &&
    git -C "$root" config user.name "Bootstrap Test" &&
    git -C "$root" config user.email "bootstrap@example.invalid" &&
    git -C "$root" remote add origin git@github.com:KleinPerkins/skills.git &&
    git -C "$root" add bootstrap.sh global scripts &&
    git -C "$root" commit -qm "durable bootstrap fixture"
}

HOME_ONE="$TMP/home-one"
mkdir -p "$HOME_ONE"
HOME="$HOME_ONE" bash "$PROJECTION/bootstrap.sh" --install >/dev/null 2>&1 \
  || fail_case "isolated bootstrap succeeds"
HOME="$HOME_ONE" bash "$PROJECTION/bootstrap.sh" --install >/dev/null 2>&1 \
  && pass "isolated bootstrap is idempotent" \
  || fail_case "isolated bootstrap is idempotent"
PYTHONPATH='' HOME="$HOME_ONE" python3 \
  "$BOOTSTRAP_SKILL/scripts/swarm_cli.py" \
  route --role reviewer --score 70 --runtime-models "$RUNTIME_MODELS" \
  >/dev/null 2>&1 \
  && pass "vendored helper consumes shared catalog" \
  || fail_case "vendored helper consumes shared catalog"
PYTHONPATH='' HOME="$HOME_ONE" python3 -m py_compile \
  "$BOOTSTRAP_SKILL"/scripts/swarm_*.py \
  >/dev/null 2>&1 \
  && pass "vendored helper compiles" \
  || fail_case "vendored helper compiles"

QUIVER="$TMP/quiver-projection/quiver"
mkdir -p "$QUIVER/skills" "$QUIVER/rules"
cp -R "$SKILL" "$QUIVER/skills/swarm"
cp -R \
  "$REPO/global/rules/subagent-orchestration" \
  "$QUIVER/rules/subagent-orchestration"
PYTHONPATH='' python3 \
  "$QUIVER/skills/swarm/scripts/swarm_cli.py" \
  route --role reviewer --score 70 --runtime-models "$RUNTIME_MODELS" \
  >/dev/null 2>&1 \
  && pass "quiver projection resolves shared catalog" \
  || fail_case "quiver projection resolves shared catalog"

SKILL_ONLY="$TMP/skill-only/swarm"
RULE_SOURCE="$TMP/installed-rule-source"
SYMLINK_HOME="$TMP/symlink-home"
mkdir -p "$(dirname "$SKILL_ONLY")" "$RULE_SOURCE" "$SYMLINK_HOME/.cursor/rules"
cp -R "$SKILL" "$SKILL_ONLY"
cp \
  "$REPO/global/rules/subagent-orchestration/subagent-orchestration.mdc" \
  "$REPO/global/rules/subagent-orchestration/model-tiers.json" \
  "$RULE_SOURCE/"
ln -s \
  "$RULE_SOURCE/subagent-orchestration.mdc" \
  "$SYMLINK_HOME/.cursor/rules/subagent-orchestration.mdc"
PYTHONPATH='' HOME="$SYMLINK_HOME" python3 \
  "$SKILL_ONLY/scripts/swarm_cli.py" \
  route --role reviewer --score 70 --runtime-models "$RUNTIME_MODELS" \
  >/dev/null 2>&1 \
  && pass "skill-only projection resolves catalog through rule symlink" \
  || fail_case "skill-only projection resolves catalog through rule symlink"

rm "$QUIVER/rules/subagent-orchestration/model-tiers.json"
NO_CATALOG_HOME="$TMP/no-catalog-home"
mkdir -p "$NO_CATALOG_HOME"
PROBE_JSON="$(python3 - <<'PY'
import json
dims = {f"D{i:02d}": {"score": 5, "confidence": 80, "hotspot": False} for i in range(1, 17)}
print(json.dumps({
    "scores": dims,
    "surface": {"roots": 1, "files_changed": 1, "lines_changed": 10, "impacted_surfaces": []},
    "fix_character": "cosmetic",
}))
PY
)"
PYTHONPATH='' HOME="$NO_CATALOG_HOME" python3 \
  "$QUIVER/skills/swarm/scripts/swarm_cli.py" \
  risk --impact 4 --likelihood 4 --exposure 4 --irreversibility 4 \
  >/dev/null 2>&1 \
  && pass "missing catalog leaves risk available" \
  || fail_case "missing catalog leaves risk available"
PYTHONPATH='' HOME="$NO_CATALOG_HOME" python3 \
  "$QUIVER/skills/swarm/scripts/swarm_cli.py" \
  size "$PROBE_JSON" \
  >/dev/null 2>&1 \
  && pass "missing catalog leaves size available" \
  || fail_case "missing catalog leaves size available"
output="$(PYTHONPATH='' HOME="$NO_CATALOG_HOME" python3 \
  "$QUIVER/skills/swarm/scripts/swarm_cli.py" \
  route --role reviewer --score 70 --runtime-models "$RUNTIME_MODELS" 2>&1)"
rc=$?
case "$output" in
  *"shared model-tier catalog not found; tried "*"quiver/rules/subagent-orchestration/model-tiers.json"*\
"$NO_CATALOG_HOME/.cursor/rules/model-tiers.json"*)
    if [ "$rc" -ne 0 ]; then
      pass "missing catalog fails only routing with both attempted paths"
    else
      fail_case "missing catalog route diagnostic returned success"
    fi ;;
  *)
    fail_case "missing catalog route lacks actionable diagnostic ($output)" ;;
esac

for tool in cursor claude codex; do
  assert_link \
    "$HOME_ONE/.$tool/skills/swarm" \
    "$BOOTSTRAP_SKILL" \
    "$tool skill link"
  assert_link \
    "$HOME_ONE/.$tool/skills/ecosystem-search" \
    "$BOOTSTRAP_SEARCH" \
    "$tool ecosystem-search link"
  if [ "$tool" = codex ]; then
    assert_link \
      "$HOME_ONE/.$tool/skills/agent-route" \
      "$BOOTSTRAP_AGENT_ROUTE" \
      "codex agent-route link"
  elif [ ! -e "$HOME_ONE/.$tool/skills/agent-route" ] &&
       [ ! -L "$HOME_ONE/.$tool/skills/agent-route" ]; then
    pass "$tool agent-route remains unexposed"
  else
    fail_case "$tool agent-route should not be exposed"
  fi
done

assert_link \
  "$HOME_ONE/.cursor/rules/subagent-orchestration.mdc" \
  "$PROJECTION/global/rules/subagent-orchestration/subagent-orchestration.mdc" \
  "cursor shared orchestration rule link"

for agent in swarm-probe swarm-reviewer swarm-verifier; do
  payload="$PROJECTION/global/sub-agents/$agent/$agent.md"
  for tool in cursor claude; do
    assert_link \
      "$HOME_ONE/.$tool/agents/$agent.md" \
      "$payload" \
      "$tool $agent link"
  done
  if [ ! -e "$HOME_ONE/.codex/agents/$agent.md" ]; then
    pass "codex $agent uses skill fallback"
  else
    fail_case "codex $agent should not be directly exposed"
  fi
done

no_double_slash_targets() {
  local home="$1" label="$2" link target bad=0 seen=0
  for link in "$home"/.cursor/skills/* "$home"/.claude/skills/* "$home"/.codex/skills/* \
    "$home"/.cursor/rules/* "$home"/.cursor/agents/* "$home"/.claude/agents/* "$home"/.codex/agents/*; do
    [ -L "$link" ] || continue
    seen=1
    target="$(readlink "$link")"
    case "$target" in
      *//*|*/) fail_case "$label: $link -> $target"; bad=1 ;;
    esac
  done
  [ "$seen" = 1 ] || { fail_case "$label: no links found"; bad=1; }
  [ "$bad" -eq 0 ] && pass "$label"
}
no_double_slash_targets "$HOME_ONE" "bootstrap link targets carry no '//' or trailing '/'"

HOME_DOUBLE="$TMP/home-double-slash"
mkdir -p "$HOME_DOUBLE/.cursor/rules" "$HOME_DOUBLE/.claude/agents"
ln -s "$PROJECTION/global/rules/subagent-orchestration//subagent-orchestration.mdc" \
  "$HOME_DOUBLE/.cursor/rules/subagent-orchestration.mdc"
ln -s "$PROJECTION/global/rules/subagent-orchestration//model-tiers.json" \
  "$HOME_DOUBLE/.cursor/rules/model-tiers.json"
ln -s "$PROJECTION/global/sub-agents/swarm-probe//swarm-probe.md" \
  "$HOME_DOUBLE/.claude/agents/swarm-probe.md"
HOME="$HOME_DOUBLE" bash "$PROJECTION/bootstrap.sh" --reconcile >/dev/null 2>&1 \
  || fail_case "reconcile over earlier '//' links succeeds"
no_double_slash_targets "$HOME_DOUBLE" "reconcile rewrites earlier '//' links to clean targets"

HOME_TWO="$TMP/home-two"
mkdir -p "$HOME_TWO/.cursor/agents"
printf 'operator-owned\n' > "$HOME_TWO/.cursor/agents/swarm-probe.md"
HOME="$HOME_TWO" bash "$PROJECTION/bootstrap.sh" --install >/dev/null 2>&1 \
  || fail_case "non-clobber bootstrap succeeds"
preserved="$(< "$HOME_TWO/.cursor/agents/swarm-probe.md")"
if [ "$preserved" = "operator-owned" ]; then
  pass "bootstrap preserves real agent file"
else
  fail_case "bootstrap preserves real agent file"
fi

HOME_THREE="$TMP/home-three"
mkdir -p "$HOME_THREE"
HOME="$HOME_THREE" bash "$SKILL/install.sh" >/dev/null 2>&1 \
  || fail_case "skill installer succeeds"
assert_link "$HOME_THREE/.cursor/skills/swarm" "$SKILL" "skill installer link"
for agent in swarm-probe swarm-reviewer swarm-verifier; do
  HOME="$HOME_THREE" bash "$REPO/global/sub-agents/$agent/install.sh" >/dev/null 2>&1 \
    || fail_case "$agent installer succeeds"
  assert_link \
    "$HOME_THREE/.cursor/agents/$agent.md" \
    "$REPO/global/sub-agents/$agent/$agent.md" \
    "$agent installer link"
done
HOME="$HOME_THREE" bash "$SKILL/install.sh" --doctor >/dev/null 2>&1 \
  && pass "aggregate skill installer doctor" \
  || fail_case "aggregate skill installer doctor"

HOME="$HOME_ONE" bash "$PROJECTION/bootstrap.sh" --doctor >/dev/null 2>&1 \
  && pass "bootstrap doctor accepts swarm capabilities" \
  || fail_case "bootstrap doctor accepts swarm capabilities"

assert_no_native_calls() {
  if [ -e "$BOOTSTRAP_NATIVE_CALLS" ]; then
    fail_case "fixture attempted a native/network entrypoint"
  else
    pass "fixture made no intercepted native/network calls"
  fi
}

if [ "${SKILLS_BOOTSTRAP_SMOKE:-0}" = 1 ]; then
  assert_no_native_calls
  [ "$fail" -eq 0 ]
  exit $?
fi

test_linked_worktree_bootstrap() {
  local canonical="$TMP/canonical-repo"
  local linked="$TMP/linked-worktree"
  local canonical_home="$TMP/canonical-home"
  local linked_home="$TMP/linked-home"
  local diagnostic_home="$TMP/diagnostic-home"
  local output rc link target bad=0

  cp -R "$PROJECTION" "$canonical" || {
    fail_case "linked-worktree fixture copies canonical source"
    return
  }
  rm -f "$canonical/.git"
  if git init -q "$canonical" &&
    git -C "$canonical" config user.name "Bootstrap Test" &&
    git -C "$canonical" config user.email "bootstrap@example.invalid" &&
    git -C "$canonical" add bootstrap.sh global &&
    git -C "$canonical" commit -qm "bootstrap fixture" &&
    git -C "$canonical" worktree add -q -b bootstrap-linked-regression "$linked"; then
    :
  else
    fail_case "linked-worktree fixture initializes"
    return
  fi

  mkdir -p "$canonical_home"
  if HOME="$canonical_home" bash "$canonical/bootstrap.sh" --reconcile >/dev/null 2>&1; then
    pass "canonical-worktree reconciliation succeeds"
  else
    fail_case "canonical-worktree reconciliation succeeds"
  fi
  assert_link \
    "$canonical_home/.cursor/skills/swarm" \
    "$canonical/global/skills/swarm" \
    "canonical worktree remains the installed skill source"

  mkdir -p "$linked_home"
  output="$(HOME="$linked_home" bash "$linked/bootstrap.sh" --reconcile 2>&1)"
  rc=$?
  if [ "$rc" -eq 0 ]; then
    pass "linked-worktree reconciliation succeeds"
  else
    fail_case "linked-worktree reconciliation succeeds ($output)"
  fi
  assert_link \
    "$linked_home/.cursor/skills/swarm" \
    "$canonical/global/skills/swarm" \
    "linked worktree installs skill from canonical source"
  assert_link \
    "$linked_home/.cursor/rules/subagent-orchestration.mdc" \
    "$canonical/global/rules/subagent-orchestration/subagent-orchestration.mdc" \
    "linked worktree installs rule from canonical source"
  assert_link \
    "$linked_home/.claude/agents/swarm-probe.md" \
    "$canonical/global/sub-agents/swarm-probe/swarm-probe.md" \
    "linked worktree installs sub-agent from canonical source"

  for link in \
    "$linked_home"/.cursor/skills/* \
    "$linked_home"/.claude/skills/* \
    "$linked_home"/.codex/skills/* \
    "$linked_home"/.cursor/rules/* \
    "$linked_home"/.cursor/agents/* \
    "$linked_home"/.claude/agents/* \
    "$linked_home"/.codex/agents/*; do
    [ -L "$link" ] || continue
    target="$(readlink "$link")"
    case "$target" in
      "$linked"/*)
        fail_case "linked-worktree reconciliation targeted temporary root ($link -> $target)"
        bad=1 ;;
    esac
  done
  [ "$bad" -eq 0 ] && pass "no installed link targets the temporary worktree"

  mv "$canonical/global" "$canonical/global.unavailable" || {
    fail_case "missing-canonical diagnostic fixture initializes"
    return
  }
  output="$(HOME="$diagnostic_home" bash "$linked/bootstrap.sh" --reconcile --dry-run 2>&1)"
  rc=$?
  mv "$canonical/global.unavailable" "$canonical/global"
  case "$output" in
    *"durable primary worktree unavailable:"*"$canonical"*\
"missing global/"*"refusing to install from linked worktree"*)
      if [ "$rc" -ne 0 ]; then
        pass "missing canonical source fails with actionable diagnostic"
      else
        fail_case "missing canonical source diagnostic returned success"
      fi ;;
    *)
      fail_case "missing canonical source lacks actionable diagnostic ($output)" ;;
  esac
}

test_nested_standalone_bootstrap() {
  local candidate_home="$TMP/durable-source-home"
  local host_primary="$TMP/host-primary"
  local host_linked="$candidate_home/.cursor/worktrees/host-repo/slot"
  local nested="$host_linked/capabilities/skills"
  local nested_alias="$candidate_home/rejected-source-alias"
  local primary="$candidate_home/dev/capabilities/skills"
  local lookalike="$candidate_home/.cursor/worktrees-backup/host-repo/slot/capabilities/skills"
  local ordinary_parent="$candidate_home/.cursor/worktrees/ordinary-repo/slot"
  local ordinary_nested="$ordinary_parent/capabilities/skills"
  local pointer="$candidate_home/.local/share/bootstrap-fixture/source.txt"
  local backup="${pointer}.before-e01"
  local orphan_link="$candidate_home/.cursor/skills/retired-nested"
  local unexposed_link="$candidate_home/.claude/skills/cursor-only"
  local foreign_target="$TMP/foreign-capability"
  local foreign_link="$candidate_home/.cursor/skills/foreign-capability"
  local foreign_dir="$candidate_home/.claude/skills/operator-owned"
  local operator_home="$HOME"
  local nested_physical primary_physical host_linked_physical
  local output rc before after refusal_before refusal_after
  local nested_digest primary_digest bad link target
  local first_projection second_projection archive archive_count

  mkdir -p "$host_primary" "$(dirname "$host_linked")"
  if git init -q "$host_primary" &&
    git -C "$host_primary" config user.name "Bootstrap Test" &&
    git -C "$host_primary" config user.email "bootstrap@example.invalid" &&
    printf 'host\n' > "$host_primary/host.txt" &&
    git -C "$host_primary" add host.txt &&
    git -C "$host_primary" commit -qm "host fixture" &&
    git -C "$host_primary" worktree add -q -b e01-host-linked "$host_linked"; then
    pass "nested-standalone host worktree fixture initializes"
  else
    fail_case "nested-standalone host worktree fixture initializes"
    return
  fi

  if init_skills_fixture "$nested" && init_skills_fixture "$primary"; then
    pass "nested and established-primary Skills fixtures initialize"
  else
    fail_case "nested and established-primary Skills fixtures initialize"
    return
  fi
  nested_physical="$(cd "$nested" && pwd -P)"
  primary_physical="$(cd "$primary" && pwd -P)"
  host_linked_physical="$(cd "$host_linked" && pwd -P)"
  ln -s "$nested_physical" "$nested_alias"
  for root in "$nested" "$primary"; do
    mkdir -p "$root/global/skills/cursor-only"
    cat > "$root/global/skills/cursor-only/meta.yml" <<'EOF'
schema: kp-capability/v1
id: cursor-only
kind: skill
flavor: 1
scope: global
owner: Bootstrap Test
install: install.sh
post_mgmt: none
expose: cursor
EOF
    printf '# Cursor-only fixture\n' > "$root/global/skills/cursor-only/SKILL.md"
    cat > "$root/global/skills/cursor-only/install.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
EOF
    chmod +x "$root/global/skills/cursor-only/install.sh"
    git -C "$root" add global/skills/cursor-only
    git -C "$root" commit -qm "add cursor-only fixture"
  done
  mkdir -p "$foreign_target"
  printf 'foreign\n' > "$foreign_target/payload.txt"

  seed_upgrade_state() {
    rm -rf \
      "$candidate_home/.cursor/skills" \
      "$candidate_home/.cursor/rules" \
      "$candidate_home/.cursor/agents" \
      "$candidate_home/.claude" \
      "$candidate_home/.codex" \
      "$candidate_home/.local/share/bootstrap-fixture"
    mkdir -p \
      "$candidate_home/.cursor/skills" \
      "$candidate_home/.cursor/rules" \
      "$candidate_home/.cursor/agents" \
      "$candidate_home/.claude/skills" \
      "$candidate_home/.claude/agents" \
      "$candidate_home/.codex/skills/swarm" \
      "$foreign_dir" \
      "$(dirname "$pointer")"
    ln -s "$nested/global/skills/swarm" \
      "$candidate_home/.cursor/skills/swarm"
    ln -s "$nested_alias/global/skills/retired-nested" \
      "$orphan_link"
    ln -s "$nested_alias/global/skills/cursor-only" \
      "$unexposed_link"
    ln -s "$foreign_target" "$foreign_link"
    ln -s "$primary_physical/global/skills/swarm" \
      "$candidate_home/.claude/skills/swarm"
    ln -s "$nested/global/rules/subagent-orchestration/subagent-orchestration.mdc" \
      "$candidate_home/.cursor/rules/subagent-orchestration.mdc"
    ln -s "$nested/global/sub-agents/swarm-probe/swarm-probe.md" \
      "$candidate_home/.claude/agents/swarm-probe.md"
    printf 'operator-owned\n' \
      > "$candidate_home/.codex/skills/swarm/operator-owned.txt"
    printf 'operator-owned\n' > "$foreign_dir/payload.txt"
    printf '%s\n' "$nested_physical/global/tools/fixture-pointer" > "$pointer"
  }

  run_refusal_case() {
    local name="$1" reason="$2"
    output="$(HOME="$candidate_home" \
      XDG_DATA_HOME="$candidate_home/.local/share" \
      bash "$nested/bootstrap.sh" --reconcile 2>&1)"
    rc=$?
    if [ "$rc" -ne 0 ]; then
      pass "$name returns non-zero before mutation"
    else
      fail_case "$name returned success"
    fi
    case "$output" in
      *"rejected nested Skills source"*"$nested_physical"*"disposable Cursor worktree"*"$host_linked_physical"*"expected durable primary"*"$primary"*"failed check"*"$reason"*)
        pass "$name reports rejected source, ancestor, primary, and check" ;;
      *)
        fail_case "$name lacks complete actionable diagnostic ($output)" ;;
    esac
  }

  run_origin_acceptance_case() {
    local name="$1" origin_url="$2"
    git -C "$primary" remote set-url origin "$origin_url"
    output="$(HOME="$candidate_home" \
      XDG_DATA_HOME="$candidate_home/.local/share" \
      bash "$nested/bootstrap.sh" --help 2>&1)"
    rc=$?
    if [ "$rc" -eq 0 ]; then
      case "$output" in
        *"usage: bootstrap.sh"*)
          pass "$name established primary is accepted" ;;
        *)
          fail_case "$name accepted origin did not reach bootstrap CLI ($output)" ;;
      esac
    else
      fail_case "$name established primary was rejected ($output)"
    fi
  }

  run_origin_refusal_case() {
    local name="$1" origin_url="$2"
    git -C "$primary" remote set-url origin "$origin_url"
    output="$(HOME="$candidate_home" \
      XDG_DATA_HOME="$candidate_home/.local/share" \
      bash "$nested/bootstrap.sh" --help 2>&1)"
    rc=$?
    if [ "$rc" -ne 0 ]; then
      pass "$name returns non-zero before mutation"
    else
      fail_case "$name returned success"
    fi
    case "$output" in
      *"rejected nested Skills source"*"$nested_physical"*"disposable Cursor worktree"*"$host_linked_physical"*"expected durable primary"*"$primary"*"failed check"*"origin is not KleinPerkins/skills"*)
        pass "$name reports rejected source, ancestor, primary, and check" ;;
      *)
        fail_case "$name lacks complete actionable diagnostic ($output)" ;;
    esac
  }

  seed_upgrade_state
  refusal_before="$(projection_digest "$candidate_home")"
  if mv "$primary" "$primary.missing"; then
    run_refusal_case "missing established primary" "path is missing"
    mv "$primary.missing" "$primary"
  else
    fail_case "missing established primary fixture initializes"
  fi

  run_origin_acceptance_case \
    "scp origin without dot-git" \
    "git@github.com:KleinPerkins/skills"
  run_origin_acceptance_case \
    "https origin without dot-git" \
    "https://github.com/KleinPerkins/skills"
  run_origin_acceptance_case \
    "ssh origin without dot-git" \
    "ssh://git@github.com/KleinPerkins/skills"

  run_origin_refusal_case \
    "fork origin" \
    "git@github.com:OtherOwner/skills"
  run_origin_refusal_case \
    "other repository origin" \
    "git@github.com:KleinPerkins/other"
  run_origin_refusal_case \
    "arbitrary host origin" \
    "git@example.com:KleinPerkins/skills"
  run_origin_refusal_case \
    "malformed scp-like origin" \
    "github.com:KleinPerkins/skills"
  run_origin_refusal_case \
    "embedded-credential origin" \
    "https://token@github.com/KleinPerkins/skills"
  run_origin_refusal_case \
    "path-suffix origin" \
    "https://github.com/KleinPerkins/skills/extra"
  # Keep one accepted no-.git form live so the later dry-run, reconcile,
  # idempotence, and repair assertions exercise the full durable-source path.
  git -C "$primary" remote set-url origin git@github.com:KleinPerkins/skills

  seed_upgrade_state
  if mv "$primary/global" "$primary/global.unavailable"; then
    run_refusal_case "malformed established primary" "global/ is missing"
    mv "$primary/global.unavailable" "$primary/global"
  else
    fail_case "malformed established primary fixture initializes"
  fi

  if init_skills_fixture "$host_linked/unsafe-primary"; then
    seed_upgrade_state
    if mv "$primary" "$primary.safe" &&
      ln -s "$host_linked/unsafe-primary" "$primary"; then
      run_refusal_case \
        "disposable established primary" \
        "resolves below disposable Cursor worktree"
      rm -f "$primary"
      mv "$primary.safe" "$primary"
    else
      fail_case "disposable established primary fixture initializes"
    fi
  else
    fail_case "disposable established primary repository initializes"
  fi
  refusal_after="$(projection_digest "$candidate_home")"
  if [ "$refusal_before" = "$refusal_after" ]; then
    pass "primary refusal matrix leaves isolated candidate home unchanged"
  else
    fail_case "primary refusal matrix mutated isolated candidate home"
  fi

  if init_skills_fixture "$lookalike"; then
    seed_upgrade_state
    output="$(HOME="$candidate_home" \
      XDG_DATA_HOME="$candidate_home/.local/share" \
      bash "$lookalike/bootstrap.sh" --reconcile 2>&1)"
    rc=$?
    if [ "$rc" -eq 0 ]; then
      pass "worktrees lookalike ordinary checkout remains eligible"
    else
      fail_case "worktrees lookalike ordinary checkout remains eligible ($output)"
    fi
    assert_link \
      "$candidate_home/.cursor/skills/swarm" \
      "$lookalike/global/skills/swarm" \
      "worktrees lookalike sources itself without prefix overmatch"
  else
    fail_case "worktrees lookalike fixture initializes"
  fi

  mkdir -p "$ordinary_parent"
  if git init -q "$ordinary_parent" &&
    git -C "$ordinary_parent" config user.name "Bootstrap Test" &&
    git -C "$ordinary_parent" config user.email "bootstrap@example.invalid" &&
    printf 'ordinary\n' > "$ordinary_parent/ordinary.txt" &&
    git -C "$ordinary_parent" add ordinary.txt &&
    git -C "$ordinary_parent" commit -qm "ordinary parent fixture" &&
    init_skills_fixture "$ordinary_nested"; then
    seed_upgrade_state
    output="$(HOME="$candidate_home" \
      XDG_DATA_HOME="$candidate_home/.local/share" \
      bash "$ordinary_nested/bootstrap.sh" --reconcile 2>&1)"
    rc=$?
    if [ "$rc" -eq 0 ]; then
      pass "ordinary parent below worktrees path remains eligible"
    else
      fail_case "ordinary parent below worktrees path remains eligible ($output)"
    fi
    assert_link \
      "$candidate_home/.cursor/skills/swarm" \
      "$ordinary_nested/global/skills/swarm" \
      "unlinked parent path does not trigger disposable recovery"
  else
    fail_case "ordinary parent below worktrees fixture initializes"
  fi

  seed_upgrade_state
  nested_digest="$(tree_bytes_digest "$nested")"
  primary_digest="$(tree_bytes_digest "$primary")"
  before="$(projection_digest "$candidate_home")"
  cp "$pointer" "$TMP/pointer-before-dry-run"
  output="$(HOME="$candidate_home" \
    XDG_DATA_HOME="$candidate_home/.local/share" \
    bash "$nested/bootstrap.sh" --reconcile --dry-run 2>&1)"
  rc=$?
  after="$(projection_digest "$candidate_home")"
  if [ "$rc" -eq 0 ]; then
    pass "nested-standalone dry-run succeeds"
  else
    fail_case "nested-standalone dry-run succeeds ($output)"
  fi
  case "$output" in
    *"nested standalone checkout detected"*"$primary_physical"*"$candidate_home/.cursor/skills/swarm"*"$primary_physical/global/skills/swarm"*)
      pass "dry-run previews durable source and link targets" ;;
    *)
      fail_case "dry-run does not preview durable targets ($output)" ;;
  esac
  case "$output" in
    *"PRUNE  $orphan_link -> $nested_alias/global/skills/retired-nested"*)
      pass "dry-run previews canonicalized pruning of deleted nested target" ;;
    *)
      fail_case "dry-run leaves non-canonical deleted nested target unrecognized ($output)" ;;
  esac
  case "$output" in
    *"PRUNE  $unexposed_link -> $nested_alias/global/skills/cursor-only"*)
      pass "dry-run previews canonicalized pruning of unexposed nested target" ;;
    *)
      fail_case "dry-run leaves non-canonical unexposed nested target unrecognized ($output)" ;;
  esac
  if [ "$before" = "$after" ] &&
    cmp -s "$pointer" "$TMP/pointer-before-dry-run" &&
    [ ! -e "$backup" ]; then
    pass "dry-run preserves links, pointer bytes, and archive state"
  else
    fail_case "dry-run changed links, pointer bytes, or archive state"
  fi

  output="$(HOME="$candidate_home" \
    XDG_DATA_HOME="$candidate_home/.local/share" \
    bash "$nested/bootstrap.sh" --reconcile 2>&1)"
  rc=$?
  if [ "$rc" -eq 0 ]; then
    pass "nested-standalone reconciliation succeeds"
  else
    fail_case "nested-standalone reconciliation succeeds ($output)"
  fi
  assert_link \
    "$candidate_home/.cursor/skills/swarm" \
    "$primary/global/skills/swarm" \
    "nested source retargets Cursor skill to established primary"
  assert_link \
    "$candidate_home/.cursor/rules/subagent-orchestration.mdc" \
    "$primary/global/rules/subagent-orchestration/subagent-orchestration.mdc" \
    "nested source retargets Cursor rule to established primary"
  assert_link \
    "$candidate_home/.claude/agents/swarm-probe.md" \
    "$primary/global/sub-agents/swarm-probe/swarm-probe.md" \
    "nested source retargets Claude sub-agent to established primary"
  assert_link \
    "$candidate_home/.claude/skills/swarm" \
    "$primary/global/skills/swarm" \
    "primary-rooted active link remains on established primary"
  assert_link \
    "$candidate_home/.cursor/skills/cursor-only" \
    "$primary/global/skills/cursor-only" \
    "active primary link retargets despite stale alias fixtures"

  if [ ! -e "$orphan_link" ] && [ ! -L "$orphan_link" ]; then
    pass "reconciliation prunes deleted target through non-canonical source alias"
  else
    fail_case "reconciliation left deleted non-canonical nested target ($(readlink "$orphan_link" 2>/dev/null || printf missing))"
  fi
  if [ ! -e "$unexposed_link" ] && [ ! -L "$unexposed_link" ]; then
    pass "reconciliation prunes unexposed target through non-canonical source alias"
  else
    fail_case "reconciliation left unexposed non-canonical nested target ($(readlink "$unexposed_link" 2>/dev/null || printf missing))"
  fi
  if [ -L "$foreign_link" ] &&
    [ "$(readlink "$foreign_link")" = "$foreign_target" ] &&
    [ -e "$foreign_link" ]; then
    pass "reconciliation preserves unrelated foreign symlink"
  else
    fail_case "reconciliation changed unrelated foreign symlink"
  fi
  if [ -d "$foreign_dir" ] &&
    [ ! -L "$foreign_dir" ] &&
    [ "$(< "$foreign_dir/payload.txt")" = "operator-owned" ]; then
    pass "reconciliation preserves unrelated foreign directory"
  else
    fail_case "reconciliation changed unrelated foreign directory"
  fi

  if [ -d "$candidate_home/.codex/skills/swarm" ] &&
    [ ! -L "$candidate_home/.codex/skills/swarm" ] &&
    [ "$(< "$candidate_home/.codex/skills/swarm/operator-owned.txt")" = "operator-owned" ]; then
    pass "nested reconciliation preserves real-directory collision"
  else
    fail_case "nested reconciliation clobbered real-directory collision"
  fi
  case "$output" in
    *"SKIP"*"$candidate_home/.codex/skills/swarm"*"refusing to overwrite real path"*)
      pass "real-directory collision retains explicit refusal diagnostic" ;;
    *)
      fail_case "real-directory collision lacks refusal diagnostic ($output)" ;;
  esac

  if [ "$(< "$pointer")" = "$primary_physical/global/tools/fixture-pointer" ]; then
    pass "fixture pointer is refreshed from established primary"
  else
    fail_case "fixture pointer was not refreshed from established primary (got $(< "$pointer"))"
  fi
  if [ -f "$backup" ] &&
    [ "$(< "$backup")" = "$nested_physical/global/tools/fixture-pointer" ]; then
    pass "pointer installer backs up stale disposable source before write"
  else
    fail_case "pointer installer did not preserve stale source backup"
  fi

  bad=0
  for link in \
    "$candidate_home"/.cursor/skills/* \
    "$candidate_home"/.claude/skills/* \
    "$candidate_home"/.codex/skills/* \
    "$candidate_home"/.cursor/rules/* \
    "$candidate_home"/.cursor/agents/* \
    "$candidate_home"/.claude/agents/* \
    "$candidate_home"/.codex/agents/*; do
    [ -L "$link" ] || continue
    target="$(readlink "$link")"
    case "$target" in
      "$host_linked"/*|"$host_linked_physical"/*|"$nested_alias"/*)
        fail_case "nested reconciliation left disposable link ($link -> $target)"
        bad=1 ;;
    esac
  done
  [ "$bad" -eq 0 ] &&
    pass "no fixture-owned link targets the disposable ancestor"

  ordered_link_map "$candidate_home" > "$TMP/e01-link-map-first"
  cp "$pointer" "$TMP/e01-pointer-first"
  cp "$backup" "$TMP/e01-backup-first"
  first_projection="$(projection_digest "$candidate_home")"
  output="$(HOME="$candidate_home" \
    XDG_DATA_HOME="$candidate_home/.local/share" \
    bash "$nested/bootstrap.sh" --reconcile 2>&1)"
  rc=$?
  ordered_link_map "$candidate_home" > "$TMP/e01-link-map-second"
  second_projection="$(projection_digest "$candidate_home")"
  if [ "$rc" -eq 0 ] &&
    cmp -s "$TMP/e01-link-map-first" "$TMP/e01-link-map-second" &&
    cmp -s "$pointer" "$TMP/e01-pointer-first" &&
    cmp -s "$backup" "$TMP/e01-backup-first" &&
    [ "$first_projection" = "$second_projection" ]; then
    pass "second reconciliation is byte-identical and leaves no projection drift"
  else
    fail_case "second reconciliation changed links, pointer, backup, or projection bytes"
  fi
  archive_count=0
  for archive in "${pointer}.before-e01"*; do
    [ -e "$archive" ] || continue
    archive_count=$((archive_count + 1))
  done
  if [ "$archive_count" -eq 1 ]; then
    pass "second reconciliation creates no duplicate archive"
  else
    fail_case "second reconciliation archive count is $archive_count"
  fi

  ln -sfn "$nested/global/skills/swarm" \
    "$candidate_home/.cursor/skills/swarm"
  printf '%s\n' "$nested_physical/global/tools/fixture-pointer" > "$pointer"
  output="$(HOME="$candidate_home" \
    XDG_DATA_HOME="$candidate_home/.local/share" \
    bash "$nested/bootstrap.sh" --repair 2>&1)"
  rc=$?
  if [ "$rc" -eq 0 ]; then
    pass "nested-standalone repair succeeds"
  else
    fail_case "nested-standalone repair succeeds ($output)"
  fi
  assert_link \
    "$candidate_home/.cursor/skills/swarm" \
    "$primary/global/skills/swarm" \
    "repair retargets stale skill to established primary"
  if [ "$(< "$pointer")" = "$primary_physical/global/tools/fixture-pointer" ] &&
    cmp -s "$backup" "$TMP/e01-backup-first"; then
    pass "repair refreshes pointer without duplicating its backup"
  else
    fail_case "repair failed durable pointer or backup identity (got $(< "$pointer"))"
  fi

  if [ "$nested_digest" = "$(tree_bytes_digest "$nested")" ] &&
    [ "$primary_digest" = "$(tree_bytes_digest "$primary")" ] &&
    [ -z "$(git -C "$nested" status --porcelain=v1)" ] &&
    [ -z "$(git -C "$primary" status --porcelain=v1)" ]; then
    pass "bootstrap leaves both Skills repository byte sets unchanged"
  else
    fail_case "bootstrap mutated a Skills repository fixture"
  fi
  case "$candidate_home" in
    "$TMP"/*)
      if [ "$candidate_home" != "$operator_home" ]; then
        pass "all E-01 projection writes stay in isolated candidate HOME"
      else
        fail_case "E-01 candidate HOME unexpectedly equals operator HOME"
      fi ;;
    *)
      fail_case "E-01 candidate HOME is outside the temporary fixture" ;;
  esac
}

test_linked_worktree_bootstrap
test_nested_standalone_bootstrap
assert_no_native_calls

[ "$fail" -eq 0 ]
