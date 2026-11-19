#!/usr/bin/env bash
# .github/scripts/verify-skills.sh — self-contained CI backstop for KleinPerkins/skills (reorg-v2 WS-9).
# No dependency on ~/dev: validates the kp-capability/v1 contract for BOTH global/ and local/
# artifacts + asserts INV-zero-link (artifacts must NOT reveal cpp). Mirrors the home verifiers
# but standalone for Actions.
#
# Scope paradigm: artifacts under global/ MUST declare scope: global; artifacts under local/ MUST
# declare scope: local — the manifest is enforced to match the containing dir (Decision A scope
# paradigm). Adding local/ coverage means the three demoted skills (session-close, update-skills,
# frontend-design) get the same remote enforcement as global/.
set -uo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)" || exit 1
fail=0
note() { printf '%s\n' "$*"; }
SHELVES="skills rules sub-agents tools plugins"
MODEL_CHECKER="global/rules/subagent-orchestration/verify_model_tiers.py"
MODEL_TESTS="global/rules/subagent-orchestration/tests"
META_VALIDATOR="scripts/capability_meta.py"

# The shared tier catalog is the only tier -> slug source. Its checker validates
# structure only; live-list drift surfaces as reported fallbacks, not here.
if [ -f "$MODEL_CHECKER" ] && python3 "$MODEL_CHECKER"; then
  :
else
  note "FAIL  shared model-tier catalog validity"
  fail=1
fi
if [ -d "$MODEL_TESTS" ] && python3 -m unittest discover -s "$MODEL_TESTS" -p 'test_*.py'; then
  note "PASS  shared model-tier catalog refusal tests"
else
  note "FAIL  shared model-tier catalog refusal tests"
  fail=1
fi

if [ -f scripts/tests/test_capability_meta.py ] &&
  PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
    -s scripts/tests -p 'test_capability_meta.py'; then
  note "PASS  strict capability metadata parser tests"
else
  note "FAIL  strict capability metadata parser tests"
  fail=1
fi

if [ -d global/skills/plan-refine/tests ] && python3 -m unittest discover -s global/skills/plan-refine/tests -p 'test_*.py'; then
  note "PASS  plan-refine doctrine contract tests"
else
  note "FAIL  plan-refine doctrine contract tests"
  fail=1
fi

if [ -f local/tools/google-kit-doc-styles/test_install.py ] &&
  PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover \
    -s local/tools/google-kit-doc-styles -p 'test_install.py' -v; then
  note "PASS  google-kit generic style seeds and local installer preservation"
else
  note "FAIL  google-kit generic style seeds and local installer preservation"
  fail=1
fi

if [ -d local/plugins/continual-learning/tests ] && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s local/plugins/continual-learning/tests -p 'test_*.py'; then
  note "PASS  continual-learning governor contract tests"
else
  note "FAIL  continual-learning governor contract tests"
  fail=1
fi

# The shared index owns retrieval/runtime tests; the thin consumers own source-backed
# package checks. Native entry scenarios remain a separate review/canary boundary.
if [ -d global/tools/ecosystem-index/tests ] &&
  PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover \
    -s global/tools/ecosystem-index/tests -p 'test_*.py'; then
  note "PASS  ecosystem-index runtime contract"
else
  note "FAIL  ecosystem-index runtime contract"
  fail=1
fi
if [ -f scripts/tests/test_ecosystem_consumers.py ] &&
  PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover \
    -s scripts/tests -p 'test_ecosystem_consumers.py'; then
  note "PASS  ecosystem source-backed consumer packages"
else
  note "FAIL  ecosystem source-backed consumer packages"
  fail=1
fi

# 1) manifest contract: every {global,local}/*/meta.yml is kp-capability/v1 with the required keys,
#    AND scope matches the containing dir.
shopt -s nullglob
kind_shelf() {
  case "$1" in
    skill) printf 'skills\n' ;;
    rule) printf 'rules\n' ;;
    sub-agent) printf 'sub-agents\n' ;;
    tool) printf 'tools\n' ;;
    plugin) printf 'plugins\n' ;;
    *) printf '' ;;
  esac
}
seen_keys=""
seen_ids=""
found_meta=0
expose_tokens() {
  awk -F'expose:[[:space:]]*' '/^expose:/{print $2; exit}' "$1" | tr -d '[]' | tr ',' ' '
}
if [ -f "$META_VALIDATOR" ] &&
  PYTHONDONTWRITEBYTECODE=1 python3 "$META_VALIDATOR" action-plan . >/dev/null; then
  note "PASS  strict flat capability metadata grammar + action plan"
else
  note "FAIL  strict flat capability metadata grammar + action plan"
  fail=1
fi
for scope_dir in global local; do
  [ -d "$scope_dir" ] || continue
  for shelf_dir in $SHELVES; do
    for m in "$scope_dir/$shelf_dir"/*/meta.yml; do
    found_meta=1
    grep -qE "^schema:[[:space:]]*kp-capability/v1" "$m" || { note "FAIL  $m: schema != kp-capability/v1"; fail=1; }
    grep -qE "^scope:[[:space:]]*${scope_dir}"      "$m" || { note "FAIL  $m: scope != ${scope_dir} (under ${scope_dir}/)"; fail=1; }
    # kind-value check (P0-1): the shared parser asserts the required `kind:` key is present.
    # Assert its VALUE is in the kp enrollment enum (8 kinds), matching _ops/eco/manifest.sh:39 and
    # kp-mcp verify-capabilities.sh. This is the kp enrollment table — intentionally broader than
    # cpp's 6-kind vendorable enum (asset|doc enroll fine but are non-vendorable, sync_policy:none).
    kindv="$(awk -F': *' '/^kind:/{print $2; exit}' "$m" | tr -d '"' | tr -d "'" | tr -d '[:space:]')"
    case "$kindv" in
      skill|mcp|rule|tool|workflow|sub-agent|asset|doc|plugin) ;;
      *) note "FAIL  $m: kind '$kindv' not in kp enrollment enum (skill|mcp|rule|tool|workflow|sub-agent|asset|doc|plugin)"; fail=1 ;;
    esac
    expected_shelf="$(kind_shelf "$kindv")"
    if [ -n "$expected_shelf" ]; then
      [ "$shelf_dir" = "$expected_shelf" ] || { note "FAIL  $m: kind '$kindv' belongs on shelf '$expected_shelf' (got '$shelf_dir')"; fail=1; }
    else
      note "FAIL  $m: kind '$kindv' is not supported in skills kind shelves"; fail=1
    fi
    idv="$(awk -F': *' '/^id:/{print $2; exit}' "$m" | tr -d '"' | tr -d "'" | tr -d '[:space:]')"
    dir_id="$(basename "$(dirname "$m")")"
    [ "$idv" = "$dir_id" ] || { note "FAIL  $m: id '$idv' does not match directory '$dir_id'"; fail=1; }
    key="${scope_dir}:${kindv}:${idv}"
    case " $seen_keys " in *" $key "*) note "FAIL  duplicate capability key ($key)"; fail=1 ;; *) seen_keys="$seen_keys $key" ;; esac
    case " $seen_ids " in *" $idv "*) note "FAIL  duplicate capability id '$idv' (ids are globally unique until tuple-key registry support lands)"; fail=1 ;; *) seen_ids="$seen_ids $idv" ;; esac
    # expose-value check (P0-2a): `expose:` is OPTIONAL (absent => all three tools per Decision D4);
    # when present, every token must be a known tool. Format is a space- or comma-separated subset.
    # `none` (ADR 0007) = kept in the repo, never installed locally; it must stand alone.
    exposev="$(expose_tokens "$m")"
    if [ -n "$exposev" ]; then
      case " $exposev " in
        *" none "*) [ "$(printf '%s' "$exposev" | tr -d '[:space:]')" = none ] || { note "FAIL  $m: expose 'none' cannot be combined with tools"; fail=1; } ;;
        *) for t in $exposev; do
             case "$t" in cursor|claude|codex) ;; *) note "FAIL  $m: expose has invalid tool '$t' (allowed: cursor|claude|codex|none)"; fail=1 ;; esac
           done ;;
      esac
    fi
    dir="$(dirname "$m")"
    inst="$(awk -F': *' '/^install:/{print $2; exit}' "$m" | tr -d '"' | tr -d "'" | tr -d '[:space:]')"
    case "$inst" in
      "")        note "FAIL  $m: install contract missing"; fail=1 ;;
      *..*|*/*)  note "FAIL  $m: install must be a bare filename (got '$inst')"; fail=1 ;;
      *) if [ ! -f "$dir/$inst" ]; then note "FAIL  $dir/$inst missing"; fail=1
         elif [ ! -x "$dir/$inst" ]; then note "FAIL  $dir/$inst not executable"; fail=1; fi ;;
    esac
    case "$kindv" in
      skill)
        sk="$dir/SKILL.md"
        if [ ! -f "$sk" ]; then
          note "FAIL  $sk missing"
          fail=1
        else
          # Supplementary, non-authoritative name/path guard. The strict Python gate below owns
          # YAML validity, parsed description values, normalization, duplicates, and inventory.
          # This narrow shell check remains only to preserve the existing name<->id diagnostic.
          sk_first="$(awk 'NR==1{print; exit}' "$sk")"
          sk_close="$(awk 'NR>1 && $0=="---"{print NR; exit}' "$sk")"
          if [ "$sk_first" != "---" ] || [ -z "$sk_close" ]; then
            note "FAIL  $sk: expected closed YAML frontmatter at file start"
            fail=1
          else
            sk_fm="$(awk 'NR==1{next} $0=="---"{exit} {print}' "$sk")"
            for sk_key in name description; do
              sk_count="$(printf '%s\n' "$sk_fm" | awk -F: -v k="$sk_key" '$1==k{n++} END{print n+0}')"
              [ "$sk_count" = "1" ] || { note "FAIL  $sk: frontmatter key '$sk_key' must appear exactly once"; fail=1; }
            done
            sk_name="$(printf '%s\n' "$sk_fm" | awk -F'name:[[:space:]]*' '/^name:/{print $2; exit}' | tr -d '"' | tr -d "'")"
            [ "$sk_name" = "$idv" ] || { note "FAIL  $sk: frontmatter name '$sk_name' != '$idv'"; fail=1; }
            sk_nlen=${#sk_name}
            { [ "$sk_nlen" -ge 1 ] && [ "$sk_nlen" -le 64 ]; } || { note "FAIL  $sk: frontmatter name length $sk_nlen out of range 1..64"; fail=1; }
          fi
        fi
        ;;
      rule) [ -f "$dir/$idv.mdc" ] || { note "FAIL  $dir/$idv.mdc missing"; fail=1; } ;;
      sub-agent)
        agent="$dir/$idv.md"
        if [ ! -f "$agent" ]; then
          note "FAIL  $agent missing"
          fail=1
        else
          first="$(awk 'NR==1{print; exit}' "$agent")"
          close_line="$(awk 'NR>1 && $0=="---"{print NR; exit}' "$agent")"
          if [ "$first" != "---" ] || [ -z "$close_line" ]; then
            note "FAIL  $agent: expected closed YAML frontmatter at file start"
            fail=1
          else
            fm="$(awk 'NR==1{next} $0=="---"{exit} {print}' "$agent")"
            for agent_key in name description tools; do
              key_count="$(printf '%s\n' "$fm" | awk -F: -v k="$agent_key" '$1==k{n++} END{print n+0}')"
              [ "$key_count" = "1" ] || { note "FAIL  $agent: frontmatter key '$agent_key' must appear exactly once"; fail=1; }
            done
            while IFS= read -r agent_key; do
              [ -n "$agent_key" ] || continue
              case "$agent_key" in
                name|description|tools) ;;
                *) note "FAIL  $agent: unknown frontmatter key '$agent_key'"; fail=1 ;;
              esac
            done < <(printf '%s\n' "$fm" | awk -F: '/^[A-Za-z0-9_-]+:/{print $1}')
            agent_name="$(printf '%s\n' "$fm" | awk -F': *' '/^name:/{print $2; exit}' | tr -d '"' | tr -d "'")"
            agent_desc="$(printf '%s\n' "$fm" | awk -F'description:[[:space:]]*' '/^description:/{print $2; exit}' | tr -d '"' | tr -d "'")"
            agent_tools="$(printf '%s\n' "$fm" | awk -F'tools:[[:space:]]*' '/^tools:/{print $2; exit}' | tr -d '[]' | tr ',' ' ')"
            [ "$agent_name" = "$idv" ] || { note "FAIL  $agent: frontmatter name '$agent_name' != '$idv'"; fail=1; }
            [ -n "$agent_desc" ] || { note "FAIL  $agent: frontmatter description is required"; fail=1; }
            if [ -z "$(printf '%s' "$agent_tools" | tr -d '[:space:]')" ]; then
              note "FAIL  $agent: tools must declare a read-only subset of Read, Glob, Grep"
              fail=1
            else
              has_read=0
              for agent_tool in $agent_tools; do
                case "$agent_tool" in
                  Read) has_read=1 ;;
                  Glob|Grep) ;;
                  *) note "FAIL  $agent: tool '$agent_tool' is not read-only (allowed: Read, Glob, Grep)"; fail=1 ;;
                esac
              done
              [ "$has_read" = 1 ] || { note "FAIL  $agent: tools must include Read"; fail=1; }
            fi
          fi
        fi
        ;;
      tool)
        [ -f "$dir/tool.yml" ] || { note "FAIL  $dir/tool.yml missing"; fail=1; }
        shapev="$(awk -F': *' '/^shape:/{print $2; exit}' "$m" | tr -d '"' | tr -d "'" | tr -d '[:space:]')"
        case "$shapev" in snapshot|release-descriptor|descriptor-only) ;; *) note "FAIL  $m: tool shape must be snapshot|release-descriptor|descriptor-only (got '$shapev')"; fail=1 ;; esac
        if [ "$shapev" != "snapshot" ]; then
          [ ! -d "$dir/bin" ] || { note "FAIL  $dir: record-only tool shape '$shapev' must not carry bin/"; fail=1; }
          if grep -REnI '(curl|wget|PATH=|/usr/local/bin|~/\.local/bin|chmod[[:space:]]+\+x|exec[[:space:]])' "$dir/install.sh" "$dir/tool.yml" 2>/dev/null; then
            note "FAIL  $dir: record-only tool shape '$shapev' must not fetch, PATH-install, chmod executable, or exec"
            fail=1
          fi
        fi
        ;;
      plugin)
        [ -f "$dir/SKILL.md" ] || { note "FAIL  $dir/SKILL.md missing"; fail=1; }
        [ -f "$dir/plugin.json" ] || { note "FAIL  $dir/plugin.json missing"; fail=1; }
        grep -qE '^descriptor_ref:' "$m" || { note "FAIL  $m: missing descriptor_ref"; fail=1; }
        if [ -f "$dir/plugin.json" ]; then
          expected="$(awk -F': *' '/^descriptor_ref:/{print $2; exit}' "$m" | tr -d '"' | tr -d "'" | tr -d '[:space:]')"
          actual="$(python3 - "$dir/plugin.json" 2>/dev/null <<'PY' || true
import hashlib
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    descriptor = json.load(fh)
canonical = json.dumps(descriptor, sort_keys=True, separators=(",", ":"))
print(hashlib.sha256(canonical.encode("utf-8")).hexdigest())
PY
)"
          if [ -z "$actual" ]; then
            note "FAIL  $dir: could not compute plugin descriptor hash"; fail=1
          elif [ "$actual" != "$expected" ]; then
            note "FAIL  $m: descriptor_ref mismatch (expected $actual)"
            fail=1
          fi
        fi
        ;;
    esac
    # kp-capability/v1 optional `assets:` (ADR 0002): every declared runtime sibling must exist in
    # source, for any kind. Bare-filename only (mirrors the install: contract guard above).
    for asset in $(awk -F'assets:[[:space:]]*' '/^assets:/{print $2; exit}' "$m" | tr -d '[]' | tr -d '"' | tr -d "'" | tr ',' ' '); do
      [ -n "$asset" ] || continue
      case "$asset" in
        *..*|*/*) note "FAIL  $m: asset must be a bare filename (got '$asset')"; fail=1 ;;
        *) [ -f "$dir/$asset" ] || { note "FAIL  $dir declares asset '$asset' but $dir/$asset missing in source"; fail=1; } ;;
      esac
    done
    done
  done
done
[ "$found_meta" = 1 ] || { note "FAIL  no kind-shelf meta.yml files found under global|local/{skills,rules,sub-agents,tools,plugins}/"; fail=1; }

if PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s scripts/tests -p 'test_skill_description_inventory.py' -v; then
  note "PASS  strict skill-description conformance"
else
  note "FAIL  strict skill-description conformance"
  fail=1
fi
# The strict repository inventory also owns the D-02 description budgets. Discard only
# successful JSON stdout; preserve diagnostics on stderr and let any nonzero result fail.
if PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/skill-description-inventory.py --repo . >/dev/null; then
  note "PASS  strict repository description inventory + D-02 budgets"
else
  note "FAIL  strict repository description inventory + D-02 budgets"
  fail=1
fi

# 2) zero-link: nothing under global/ OR local/ may reveal cpp (the 'other side').
# Exclusion set mirrors ~/dev/_ops/eco/verify-zero-link.sh (machine-local routing/discovery
# state, caches, VCS, node_modules) so local + CI runs agree on the same scan boundary.
# Also excluded by FILE: *.generated.* machine-generated, git-ignored artifacts (e.g. local-jobs
# dashboards) that legitimately embed real machine paths + local-job ids like `cpp-archive`; and
# AGENTS.md continual-learning agent memory (cross-repo facts, never a vendored capability payload).
re='card-platform-product|cpp-stuff|affirm/(src|vendor)|(^|[^A-Za-z.])cpp([^A-Za-z]|$)'
for scope_dir in global local; do
  [ -d "$scope_dir" ] || continue
  hits="$(grep -REnI \
    --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=.venv --exclude-dir=.pytest_cache \
    --exclude-dir=node_modules --exclude-dir=.state --exclude-dir=home --exclude-dir=discoveries \
    --exclude='*.generated.*' --exclude=AGENTS.md \
    "$re" "$scope_dir" 2>/dev/null || true)"
  if [ -n "$hits" ]; then note "FAIL  zero-link (cpp tokens under ${scope_dir}/):"; printf '%s\n' "$hits" | sed 's/^/      /'; fail=1; fi
done

# 3) lockfile parity (WF1/B2, Decision D1=keep): .eco-registry.lock must match the current metas.
# This is the local/CI fast-feedback gate of record. The pre-commit registration-guard regenerates the
# lock, but --no-verify / web edits bypass it — so CI is the backstop. Branch protection can require
# the check only where the GitHub plan exposes it. eco-lock.sh is the single normalization algorithm.
if [ -x .github/scripts/eco-lock.sh ]; then
  if ! bash .github/scripts/eco-lock.sh check; then note "FAIL  .eco-registry.lock parity"; fail=1; fi
else
  note "FAIL  .github/scripts/eco-lock.sh missing (cannot verify lock parity)"; fail=1
fi

if [ -x scripts/tests/test_eco_lock_digest.sh ]; then
  if bash scripts/tests/test_eco_lock_digest.sh; then
    note "PASS  eco-lock digest regression"
  else
    note "FAIL  eco-lock digest regression"
    fail=1
  fi
else
  note "FAIL  scripts/tests/test_eco_lock_digest.sh missing"
  fail=1
fi

if [ -x scripts/tests/test_sibling_assets.sh ]; then
  if bash scripts/tests/test_sibling_assets.sh; then
    note "PASS  capability sibling-assets regression"
  else
    note "FAIL  capability sibling-assets regression"
    fail=1
  fi
else
  note "FAIL  scripts/tests/test_sibling_assets.sh missing"
  fail=1
fi

# 4) machine-local capability opt-out helper + bootstrap gate
if [ -f scripts/capability-local.py ] && python3 -m unittest discover -s scripts/tests -p 'test_capability_local.py'; then
  note "PASS  capability-local helper tests"
else
  note "FAIL  capability-local helper tests"
  fail=1
fi
if [ -x scripts/tests/test_bootstrap_opt_out.sh ]; then
  if bash scripts/tests/test_bootstrap_opt_out.sh; then
    note "PASS  bootstrap plugin opt-out gate"
  else
    note "FAIL  bootstrap plugin opt-out gate"
    fail=1
  fi
else
  note "FAIL  scripts/tests/test_bootstrap_opt_out.sh missing"
  fail=1
fi
if [ -x scripts/tests/test_bootstrap_expose_none.sh ] && bash scripts/tests/test_bootstrap_expose_none.sh; then
  note "PASS  bootstrap expose: none local-install gate"
else
  note "FAIL  bootstrap expose: none local-install gate"
  fail=1
fi
# Lexical/adversarial metadata combinations live in the millisecond parser unit
# suite above. This bounded end-to-end suite keeps one full action matrix plus
# transaction failures at each publication step, avoiding O(cases × bootstrap).
if [ -x scripts/tests/test_bootstrap_runtime_contract.sh ] && bash scripts/tests/test_bootstrap_runtime_contract.sh; then
  note "PASS  bootstrap activation-critical runtime contract"
else
  note "FAIL  bootstrap activation-critical runtime contract"
  fail=1
fi
if [ -f local/skills/isokit/tests/test_isokit_capability.py ] &&
  PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
    -s local/skills/isokit/tests -p 'test_*.py' -v; then
  note "PASS  isokit provenance and runtime contract"
else
  note "FAIL  isokit provenance and runtime contract"
  fail=1
fi

if [ -x global/skills/swarm/tests/test_bootstrap.sh ]; then
  if SKILLS_BOOTSTRAP_SMOKE=1 bash global/skills/swarm/tests/test_bootstrap.sh; then
    note "PASS  durable bootstrap source smoke"
  else
    note "FAIL  durable bootstrap source smoke"
    fail=1
  fi
else
  note "FAIL  global/skills/swarm/tests/test_bootstrap.sh missing"
  fail=1
fi

if [ -x global/tools/dev-main-sync/scripts/v3-preflight-acceptance.sh ]; then
  case "$(uname -s)" in
    Darwin)
      dev_main_sync_mode=""
      dev_main_sync_label="macOS runtime"
      ;;
    Linux)
      dev_main_sync_mode="--portable-source-contract"
      dev_main_sync_label="portable source contract"
      ;;
    *)
      note "FAIL  dev-main-sync v3 preflight unsupported platform"
      fail=1
      dev_main_sync_mode=""
      dev_main_sync_label=""
      ;;
  esac
  if [ -n "$dev_main_sync_label" ]; then
    if { [ -z "$dev_main_sync_mode" ] \
        && bash global/tools/dev-main-sync/scripts/v3-preflight-acceptance.sh; } \
      || { [ -n "$dev_main_sync_mode" ] \
        && bash global/tools/dev-main-sync/scripts/v3-preflight-acceptance.sh \
          "$dev_main_sync_mode"; }; then
      note "PASS  dev-main-sync v3 $dev_main_sync_label acceptance"
    else
      note "FAIL  dev-main-sync v3 $dev_main_sync_label acceptance"
      fail=1
    fi
  fi
else
  note "FAIL  dev-main-sync v3 preflight acceptance missing"
  fail=1
fi

if [ "$fail" = 0 ]; then note "verify-skills: OK (global + local + lock + capability-local)"; else note "verify-skills: FAILED"; exit 1; fi
