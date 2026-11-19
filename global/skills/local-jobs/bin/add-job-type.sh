#!/usr/bin/env bash
# Add a new ABI-conformant job type, atomically and safely:
#   scaffold a chassis-based handler (born conformant on lib/handler_lib.sh)
#   -> register it in config/registry.yml (atomic, backed up)
#   -> VERIFY it (describe + instances validate, doctor PASS)
#   -> cross-type REGRESSION (every other type still conforms)
#   -> on ANY failure, ROLL BACK (restore registry + remove scaffold) so the
#      tree is left exactly as it was.
#
# Usage: add-job-type.sh --type <type> [--cardinality singleton|multi]
#                        [--description "..."] [--force]
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
. "$SCRIPT_DIR/../lib/common.sh"

type=""; cardinality="multi"; description=""; force=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --type) shift; type="${1:-}" ;;
    --cardinality) shift; cardinality="${1:-multi}" ;;
    --description) shift; description="${1:-}" ;;
    --force) force=1 ;;
    *) die "unknown option: $1" ;;
  esac
  shift
done
[[ -n "$type" ]] || die "add-job-type requires --type"
[[ "$type" =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "type must be lowercase alnum/dash: $type"
[[ "$cardinality" == "singleton" || "$cardinality" == "multi" ]] || die "cardinality must be singleton|multi"

handler="${LOCAL_JOBS_HANDLER_DIR:-$LOCAL_JOBS_STATE/handlers}/${type}.sh"
store_file="$LOCAL_JOBS_STATE/jobs/${type}.yml"
token="${type//[^a-z0-9]/-}"
# Uppercased env-var token (LOCAL_JOBS_<TOKEN>_CONFIG); avoid bash4 ${x^^}.
token_uc="$(printf '%s' "$token" | tr 'a-z-' 'A-Z_')"
mkdir -p "$(dirname "$handler")" "$LOCAL_JOBS_STATE/jobs"
[[ -e "$handler" && "$force" -eq 0 ]] && die "handler already exists: $handler (use --force to overwrite)"

authoring() { "$LOCAL_JOBS_PYTHON" "$LOCAL_JOBS_HOME/lib/authoring.py" "$@"; }

# --- scaffold a born-conformant, chassis-based handler ----------------------
singleton_id_line=""
add_schema='[
  {"flag":"--id","field":"id","kind":"id","required":true,"help":"stable instance id"},
  {"flag":"--schedule","field":"schedule","kind":"scalar","required":true,"help":"HH:MM"},
  {"flag":"--enabled","field":"enabled","kind":"bool","default":true,"help":"true | false"}
]'
required_fields='["schedule"]'
if [[ "$cardinality" == "singleton" ]]; then
  singleton_id_line="HANDLER_SINGLETON_ID=\"$token\""
  add_schema='[
  {"flag":"--schedule","field":"schedule","kind":"scalar","required":false,"help":"HH:MM"},
  {"flag":"--enabled","field":"enabled","kind":"bool","help":"true | false"}
]'
  required_fields='[]'
fi

cat >"$handler" <<HANDLER
#!/usr/bin/env bash
# Handler plugin: ${type} (${cardinality}, ABI v1). Born conformant on the shared
# chassis (lib/handler_lib.sh): it declares its schema + how to run; every other
# verb is inherited. Fill in handler_do_run with the real work.
set -euo pipefail
SCRIPT_DIR="\$(cd -- "\$(dirname -- "\${BASH_SOURCE[0]}")" && pwd)"
LOCAL_JOBS_HOME="\${LOCAL_JOBS_HOME:-\$(cd -- "\$SCRIPT_DIR/.." && pwd)}"
LOCAL_JOBS_PYTHON="\${LOCAL_JOBS_PYTHON:-python3}"
. "\$LOCAL_JOBS_HOME/lib/handler_lib.sh"

HANDLER_TYPE="${type}"
HANDLER_CARDINALITY="${cardinality}"
HANDLER_LABEL_TOKEN="${token}"
HANDLER_SCHEMA_VERSION=1
${singleton_id_line}
HANDLER_STORE_FILE="\${LOCAL_JOBS_${token_uc}_CONFIG:-\$LOCAL_JOBS_STATE/jobs/${type}.yml}"
HANDLER_FIELD_DEFAULTS='{"enabled":true}'
HANDLER_REQUIRED_FIELDS='${required_fields}'
HANDLER_ADD_SCHEMA='${add_schema}'

handler_describe() {
  HANDLER_TYPE="\$HANDLER_TYPE" HANDLER_CARDINALITY="\$HANDLER_CARDINALITY" \\
  HANDLER_LABEL_TOKEN="\$HANDLER_LABEL_TOKEN" HANDLER_SCHEMA_VERSION="\$HANDLER_SCHEMA_VERSION" \\
  HANDLER_STORE_FILE="\$HANDLER_STORE_FILE" HANDLER_ADD_SCHEMA="\$HANDLER_ADD_SCHEMA" \\
  HANDLER_LABEL_TEMPLATE="\$(_hl_label_template)" \\
    "\$LOCAL_JOBS_PYTHON" -c 'import json, os
card = os.environ["HANDLER_CARDINALITY"]
token = os.environ["HANDLER_LABEL_TOKEN"]
print(json.dumps({
    "type": os.environ["HANDLER_TYPE"],
    "cardinality": card,
    "label_token": token,
    "label_template": os.environ["HANDLER_LABEL_TEMPLATE"],
    "schema_version": int(os.environ["HANDLER_SCHEMA_VERSION"]),
    "config_file": os.environ["HANDLER_STORE_FILE"],
    "add_schema": json.loads(os.environ["HANDLER_ADD_SCHEMA"]),
}, indent=2))'
}

handler_do_run() {
  local id="" dry=0
  while [[ \$# -gt 0 ]]; do case "\$1" in --id) shift; id="\${1:-}" ;; --dry-run) dry=1 ;; *) hl_die "unknown run option: \$1" ;; esac; shift; done
  # TODO: implement the real work for '${type}'. Emit exactly one @@RUNLOG@@ line.
  if (( dry == 1 )); then
    printf '@@RUNLOG@@ {"status":"dry-run","fields":{"note":"scaffold"}}\\n'
  else
    printf '@@RUNLOG@@ {"status":"success","fields":{"note":"scaffold did nothing yet"}}\\n'
  fi
}

handler_main "\$@"
HANDLER
chmod +x "$handler"
log "scaffolded chassis handler: $handler"

# Seed a singleton store so the one instance is managed from first read.
if [[ "$cardinality" == "singleton" ]]; then
  cat >"$store_file" <<EOF
schema: jobs/v1
version: 1
schema_version: 1
instances:
- id: ${token}
  enabled: false
  schedule: "18:00"
EOF
  log "seeded singleton store (disabled): $store_file"
fi

# --- atomic register + verify + regression + rollback -----------------------
created_handler=1
rollback() {
  log_err "verification failed — rolling back"
  [[ -n "${BACKUP:-}" ]] && authoring restore-registry --backup "$BACKUP" >/dev/null 2>&1 || true
  (( created_handler == 1 )) && rm -f "$handler"
  [[ "$cardinality" == "singleton" ]] && rm -f "$store_file"
  die "add-job-type: $type rolled back (tree unchanged)"
}

BACKUP="$(authoring register --type "$type" --handler "$handler" --description "${description:-$type}" | "$LOCAL_JOBS_PYTHON" -c 'import json,sys; print(json.load(sys.stdin)["backup"])')" \
  || die "registry register failed"
log "registered $type in registry.yml (backup: $BACKUP)"

log "verifying new type conforms..."
if ! authoring verify --type "$type"; then rollback; fi
log "cross-type regression (all other types still conform)..."
if ! authoring regression --exclude "$type" >/dev/null; then rollback; fi

# Success: drop the backup.
rm -f "$BACKUP" 2>/dev/null || true
log "add-job-type: $type registered + verified + regression-clean"
log "Next: implement handler_do_run in $handler (it currently no-ops)."
