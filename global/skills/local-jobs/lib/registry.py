#!/usr/bin/env python3
"""Type-agnostic registry, discovery, and launchd scanning for local-jobs.

The core never hardcodes job types. It loads ``config/registry.yml``
(``registry/v1``) and drives every handler purely through the ABI verbs
``describe`` / ``list-instances`` (see ABI.md). Adding a new type requires only
a handler + a registry entry — no edits here.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract  # noqa: E402
import launchd  # noqa: E402
import schedule as schedule_mod  # noqa: E402
import settings  # noqa: E402

HANDLER_TIMEOUT = float(os.environ.get("LOCAL_JOBS_HANDLER_TIMEOUT", "30"))


def jobs_home() -> Path:
    env = os.environ.get("LOCAL_JOBS_HOME", "")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parent.parent


def registry_path() -> Path:
    env = os.environ.get("LOCAL_JOBS_REGISTRY", "")
    if env:
        return Path(env).expanduser()
    return jobs_home() / "config" / "registry.yml"


def _read_registry_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"registry not found: {path}")
    with path.open() as handle:
        data = yaml.safe_load(handle) or {}
    schema = data.get("schema")
    version = data.get("version", 1)
    if schema not in (None, "registry/v1"):
        raise SystemExit(f"unsupported registry schema: {schema!r}")
    if version not in (None, 1):
        raise SystemExit(f"unsupported registry version: {version!r}")
    return data


def overlay_dir() -> Path:
    env = os.environ.get("LOCAL_JOBS_OVERLAY_DIR", "")
    if env:
        return Path(env).expanduser()
    return settings.state_dir() / "registry.d"


def _overlay_entry(path: Path) -> tuple[str | None, dict[str, Any] | None, str | None]:
    try:
        with path.open() as handle:
            data = yaml.safe_load(handle) or {}
    except Exception as exc:
        return path.stem, None, f"overlay parse failed: {exc}"
    if not isinstance(data, dict):
        return path.stem, None, "overlay must be a mapping"
    if "job_types" in data:
        return None, {"job_types": data.get("job_types") or {}}, None
    job_id = data.get("id") or data.get("type") or path.stem
    handler = data.get("handler")
    entry = {k: v for k, v in data.items() if k not in {"id", "type", "override"}}
    entry["handler"] = handler
    entry["_overlay"] = True
    entry["override"] = bool(data.get("override", False))
    return str(job_id), entry, None


def _merge_overlay(data: dict[str, Any]) -> dict[str, Any]:
    odir = overlay_dir()
    if not odir.is_dir():
        return data
    types = data.setdefault("job_types", {})
    for frag in sorted(odir.glob("*.yml"), key=lambda p: p.name):
        job_id, entry, error = _overlay_entry(frag)
        entries: list[tuple[str, dict[str, Any], str | None]] = []
        if entry and "job_types" in entry:
            for jid, raw in sorted((entry.get("job_types") or {}).items()):
                item = dict(raw or {})
                item["_overlay"] = True
                item.setdefault("override", False)
                entries.append((str(jid), item, None))
        else:
            entries.append((str(job_id or frag.stem), entry or {}, error))
        for jid, item, item_error in entries:
            if jid in types and not item.get("override", False):
                data.setdefault("overlay_errors", {})[jid] = f"overlay duplicate type without override: {frag}"
                continue
            handler = item.get("handler")
            if item_error:
                item["_overlay_error"] = item_error
            elif not handler:
                item["_overlay_error"] = f"overlay type {jid} has no handler"
            else:
                hpath = Path(str(handler)).expanduser()
                if not hpath.is_absolute():
                    item["_overlay_error"] = f"overlay handler must be absolute: {handler}"
                elif not hpath.is_file() or not os.access(hpath, os.X_OK):
                    item["_overlay_error"] = f"overlay handler is not executable: {hpath}"
                item["handler"] = str(hpath)
            item.pop("override", None)
            types[jid] = item
    return data


def load_registry() -> dict[str, Any]:
    data = _read_registry_file(registry_path())
    data.setdefault("discovery", {}).setdefault("label_root", settings.DEFAULT_LABEL_ROOT)
    return _merge_overlay(data)


def job_types(reg: dict[str, Any]) -> dict[str, Any]:
    return reg.get("job_types") or {}


def handler_path(job_type: str, reg: dict[str, Any] | None = None) -> Path:
    reg = reg or load_registry()
    types = job_types(reg)
    if job_type not in types:
        raise SystemExit(f"unknown job type: {job_type}")
    meta = types[job_type] or {}
    if meta.get("_overlay_error"):
        raise SystemExit(meta["_overlay_error"])
    rel = meta.get("handler")
    if not rel:
        raise SystemExit(f"job type {job_type} has no handler")
    path = Path(str(rel)).expanduser()
    if not path.is_absolute():
        path = jobs_home() / path
    if not path.is_file():
        raise SystemExit(f"handler missing: {path}")
    return path


def _run_handler(
    job_type: str, args: list[str], reg: dict[str, Any], timeout: float = HANDLER_TIMEOUT
) -> subprocess.CompletedProcess[str]:
    handler = handler_path(job_type, reg)
    return subprocess.run(
        [str(handler), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _tail(text: str, n: int = 500) -> str:
    return (text or "").strip()[-n:]


def collect_for_type(job_type: str, reg: dict[str, Any]) -> list[dict[str, Any]]:
    """Instances for one type, fully isolated: any failure (non-zero rc, bad
    JSON, contract-invalid, timeout, missing handler) yields exactly ONE
    quarantine row instead of crashing the whole view or silently vanishing.
    """
    try:
        dproc = _run_handler(job_type, ["describe"], reg)
        if dproc.returncode != 0:
            return [contract.quarantine_row(job_type, "describe failed", _tail(dproc.stderr), "describe", dproc.returncode)]
        try:
            desc = json.loads(dproc.stdout or "null")
        except json.JSONDecodeError as exc:
            return [contract.quarantine_row(job_type, f"describe emitted non-JSON: {exc}", _tail(dproc.stdout), "describe")]
        derrs = contract.validate_describe(desc)
        if derrs:
            return [contract.quarantine_row(job_type, "invalid describe: " + "; ".join(derrs), _tail(dproc.stdout), "describe")]

        lproc = _run_handler(job_type, ["list-instances"], reg)
        if lproc.returncode != 0:
            return [contract.quarantine_row(job_type, "list-instances failed", _tail(lproc.stderr), "list-instances", lproc.returncode)]
        try:
            data = json.loads(lproc.stdout or "[]")
        except json.JSONDecodeError as exc:
            return [contract.quarantine_row(job_type, f"list-instances emitted non-JSON: {exc}", _tail(lproc.stdout), "list-instances")]
        if not isinstance(data, list):
            return [contract.quarantine_row(job_type, "list-instances did not return a JSON array", _tail(lproc.stdout), "list-instances")]

        out: list[dict[str, Any]] = []
        for inst in data:
            ierrs = contract.validate_instance(inst)
            if ierrs:
                # Partial invalid instances are skipped — they must not quarantine
                # the whole type or block handler doctor when others are valid.
                continue
            inst.setdefault("type", job_type)
            out.append(inst)
        return out
    except subprocess.TimeoutExpired:
        return [contract.quarantine_row(job_type, f"handler timed out after {HANDLER_TIMEOUT:g}s", "", "list-instances")]
    except SystemExit as exc:  # handler_path: missing handler/type
        return [contract.quarantine_row(job_type, str(exc), "", "discover")]
    except Exception as exc:  # never let one type break discovery
        return [contract.quarantine_row(job_type, f"unexpected error: {exc}", "", "discover")]


def handler_describe(job_type: str, reg: dict[str, Any]) -> dict[str, Any]:
    try:
        proc = _run_handler(job_type, ["describe"], reg)
    except SystemExit:
        return {}
    if proc.returncode != 0 or not proc.stdout.strip():
        return {}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def handler_list_instances(job_type: str, reg: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        proc = _run_handler(job_type, ["list-instances"], reg)
    except SystemExit:
        return []
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def collect_instances(reg: dict[str, Any]) -> list[dict[str, Any]]:
    """All instances across all types, with per-type failure isolation.

    A broken type contributes a single ``role:"error"`` quarantine row rather
    than crashing discovery or disappearing silently.
    """
    instances: list[dict[str, Any]] = []
    for jtype in job_types(reg):
        instances.extend(collect_for_type(jtype, reg))
    return instances


def resolve_instance(query: str, reg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Delegate to :mod:`resolver`, the single source of truth for discovery.

    The scoring logic moved to ``lib/resolver.py``; this thin re-export keeps
    ``registry.resolve_instance`` working for existing importers (imported lazily
    to avoid any load-time cycle between the two modules).
    """
    import resolver

    return resolver.resolve_instance(query, reg)


def instance_type(instance_id: str, reg: dict[str, Any] | None = None) -> str:
    """Resolve the single job type that owns ``instance_id``.

    Fail-closed on cross-type collisions: instance ids are a global namespace,
    so an id claimed by two types is an error, not a silent first-match. Callers
    that already know the type pass ``--type`` and never reach here.
    """
    reg = reg or load_registry()
    matches: list[str] = []
    for jtype in job_types(reg):
        for inst in collect_for_type(jtype, reg):
            if isinstance(inst, dict) and inst.get("role") != "error" and inst.get("id") == instance_id:
                matches.append(jtype)
                break  # this type owns the id; stop scanning its instances
    if not matches:
        msg = f"unknown instance: {instance_id}"
        if ID_LIKE.match(instance_id):
            suggestions = resolve_instance(instance_id, reg)[:3]
            if suggestions:
                hints = ", ".join(f"{s['id']} ({s['type']})" for s in suggestions)
                msg += f"; did you mean: {hints}?"
        raise SystemExit(msg)
    if len(matches) > 1:
        joined = ", ".join(sorted(matches))
        raise SystemExit(
            f"ambiguous id '{instance_id}' in types: {joined}; "
            f"re-run with --type <type> to disambiguate"
        )
    return matches[0]


ID_LIKE = re.compile(r"^[A-Za-z0-9._-]+$")


def canvas_bridge_adopted() -> bool:
    """True when the operator adopted the canvas Run-now bridge sidecar."""
    return (settings.state_dir() / "canvas-bridge" / "adopted.yml").is_file()


def managed_labels(reg: dict[str, Any], instances: list[dict[str, Any]] | None = None) -> set[str]:
    if instances is None:
        instances = collect_instances(reg)
    labels: set[str] = set()
    for inst in instances:
        label = inst.get("launchd_label")
        if label:
            labels.add(label)
    if canvas_bridge_adopted():
        labels.add(settings.label_for("canvas-bridge", cardinality="singleton", registry=reg))
    return labels


def launchctl_loaded(label: str) -> bool:
    # Delegate to the single launchd module so discovery honors
    # LOCAL_JOBS_LAUNCHD_DISABLE and degrades gracefully without launchctl.
    return launchd.is_loaded(label)


def parse_plist_schedule(plist_path: Path) -> dict[str, Any]:
    if not plist_path.is_file():
        return {}
    with plist_path.open("rb") as handle:
        data = plistlib.load(handle)
    schedule: dict[str, Any] = {}
    interval = data.get("StartInterval")
    if interval is not None:
        schedule["kind"] = "interval"
        schedule["seconds"] = interval
    cal = data.get("StartCalendarInterval")
    if isinstance(cal, dict):
        schedule["kind"] = "calendar"
        if "Hour" in cal:
            schedule["hour"] = cal["Hour"]
        if "Minute" in cal:
            schedule["minute"] = cal["Minute"]
    if data.get("RunAtLoad"):
        schedule["run_at_load"] = True
    return schedule


def discover_launchd(prefix: str) -> list[dict[str, Any]]:
    # Reuse launchd.agents_dir() so the sandbox (LOCAL_JOBS_LAUNCHAGENTS_DIR)
    # is honored and discovery is hermetic.
    agents_dir = launchd.agents_dir()
    found: list[dict[str, Any]] = []
    if not agents_dir.is_dir():
        return found
    for plist in sorted(agents_dir.glob(f"{prefix}*.plist")):
        label = plist.stem
        found.append(
            {
                "label": label,
                "plist": str(plist),
                "loaded": launchctl_loaded(label),
                "schedule": parse_plist_schedule(plist),
            }
        )
    return found


def _schedule_str(sched: dict[str, Any]) -> str:
    try:
        return schedule_mod.Schedule.parse(sched).summary()
    except (ValueError, TypeError, KeyError):
        return "?"


def build_view(reg: dict[str, Any]) -> dict[str, Any]:
    instances = collect_instances(reg)
    managed = managed_labels(reg, instances)
    discovered = []
    seen = set()
    for prefix in settings.discovery_prefixes(reg):
        for item in discover_launchd(prefix):
            if item["label"] not in seen:
                discovered.append(item)
                seen.add(item["label"])
    unmanaged = [d for d in discovered if d["label"] not in managed]
    payload: dict[str, Any] = {
        "registry": str(registry_path()),
        "label_root": settings.label_root(reg),
        "instances": instances,
        "discovered_unmanaged": unmanaged,
    }
    overlay_errors = reg.get("overlay_errors")
    if overlay_errors:
        payload["overlay_errors"] = overlay_errors
    return payload


def view_jobs(as_json: bool) -> int:
    reg = load_registry()
    payload = build_view(reg)
    if as_json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"registry: {payload['registry']}")
    print("\n== Managed instances ==")
    for inst in payload["instances"]:
        if inst.get("role") == "error":
            err = inst.get("error") or {}
            print(f"  [QUARANTINED] {inst.get('type')} — {err.get('reason')} (verb={err.get('verb')})")
            continue
        if inst.get("role") == "global_scheduler":
            print(
                f"  [global] {inst.get('launchd_label')} "
                f"loaded={inst.get('launchd_loaded')} schedule={inst.get('schedule')}"
            )
            continue
        enabled = "enabled" if inst.get("enabled", True) else "disabled"
        print(
            f"  {inst.get('id')} ({inst.get('type')}) {enabled} "
            f"label={inst.get('launchd_label')} loaded={inst.get('launchd_loaded')} "
            f"schedule={inst.get('schedule', '-')}"
        )
        if inst.get("path"):
            print(
                f"    path={inst.get('path')} branch={inst.get('branch')} "
                f"fetch_tags={inst.get('fetch_tags', False)} head={inst.get('head', '-')}"
            )
        if inst.get("program"):
            print(f"    program={inst.get('program')}")

    unmanaged = payload["discovered_unmanaged"]
    overlay_errors = payload.get("overlay_errors") or {}
    if overlay_errors:
        print("\n== Overlay errors ==")
        for jid, msg in sorted(overlay_errors.items()):
            print(f"  {jid}: {msg}")

    label_root = payload.get("label_root") or settings.label_root(reg)
    if unmanaged:
        print(f"\n== Discovered (unmanaged) {label_root}.* agents ==")
        for item in unmanaged:
            print(f"  {item['label']} loaded={item['loaded']} schedule={_schedule_str(item.get('schedule') or {})}")
    else:
        print("\n== Discovered (unmanaged) ==\n  (none)")
    return 0


def add_schema(job_type: str) -> int:
    reg = load_registry()
    desc = handler_describe(job_type, reg)
    print(json.dumps(desc.get("add_schema") or [], indent=2))
    return 0


def _update_field_matrix(add_schema: list[Any]) -> list[dict[str, Any]]:
    """Which ``add_schema`` flags ``update-job`` can mutate.

    The instance ``id`` is the key (never updatable); every other declared field
    is patchable. Mirrors ``handler_lib.sh`` ``_hl_cmd_update``, which builds the
    update patch from the same ``add_schema`` with ``--id`` stripped out.
    """
    fields: list[dict[str, Any]] = []
    for f in add_schema:
        if not isinstance(f, dict):
            continue
        flag = f.get("flag")
        if not flag:
            continue
        name = f.get("field") or flag.lstrip("-").replace("-", "_")
        updatable = f.get("kind") != "id" and name != "id" and flag != "--id"
        fields.append({
            "flag": flag,
            "field": name,
            "kind": f.get("kind", "scalar"),
            "required": bool(f.get("required")),
            "required_one_of": f.get("required_one_of"),
            "updatable": updatable,
            "help": f.get("help") or f.get("description") or "",
        })
    return fields


def build_describe_types(reg: dict[str, Any]) -> list[dict[str, Any]]:
    """Full per-type schema surface — the machine-readable superset of
    ``list-types --json`` that grounds agent-guided job creation (the
    dashboard-to-chat "Add job" flow) and other tooling.

    Adds ``schema_version`` and the ``update_fields`` matrix on top of the
    human-facing list-types fields. Pure read (drives handlers via ``describe``).
    """
    out: list[dict[str, Any]] = []
    for slug, meta in job_types(reg).items():
        desc = handler_describe(slug, reg)
        add_schema = desc.get("add_schema") or []
        singleton_id = None
        if desc.get("cardinality") == "singleton":
            singleton_id = desc.get("label_token") or slug
        out.append({
            "slug": slug,
            "description": (meta or {}).get("description") or desc.get("type") or slug,
            "cardinality": desc.get("cardinality"),
            "singleton_id": singleton_id,
            "label_template": desc.get("label_template"),
            "schema_version": desc.get("schema_version", 1),
            "add_schema": add_schema,
            "update_fields": _update_field_matrix(add_schema),
        })
    return out


# list-types --json is the human/simple surface: a strict projection of the
# describe-types superset (same fields, unchanged shape) so there is one
# aggregation and no copy-paste drift between the two verbs.
_LIST_TYPE_KEYS = ("slug", "description", "cardinality", "singleton_id", "label_template", "add_schema")


def build_list_types(reg: dict[str, Any]) -> list[dict[str, Any]]:
    """Aggregate handler describe + registry metadata for list-types --json."""
    return [{k: t[k] for k in _LIST_TYPE_KEYS} for t in build_describe_types(reg)]


def print_list_types_plain(types: list[dict[str, Any]]) -> None:
    for t in types:
        card = t.get("cardinality") or "?"
        print(f"{t['slug']} ({card}) — {t.get('description') or ''}")
        if t.get("singleton_id"):
            print(f"  singleton id: {t['singleton_id']}")
        req = [f"{f['flag']}: {f.get('help') or f.get('description') or ''}"
               for f in (t.get("add_schema") or []) if isinstance(f, dict) and f.get("required")]
        groups: dict[str, list[str]] = {}
        for field in t.get("add_schema") or []:
            if isinstance(field, dict) and field.get("required_one_of") and field.get("flag"):
                groups.setdefault(str(field["required_one_of"]), []).append(str(field["flag"]))
        for flags in groups.values():
            req.append(f"one of {', '.join(flags)}")
        if req:
            print(f"  required: {'; '.join(req)}")
        examples = {
            "command": "scheduled shell script or binary",
            "incremental-git-fetch": "keep a reference repo up to date",
        }
        if t["slug"] in examples:
            print(f"  example: {examples[t['slug']]}")


def cmd_resolve_instance(query: str, as_json: bool) -> int:
    reg = load_registry()
    matches = resolve_instance(query, reg)
    if len(matches) == 1:
        m = matches[0]
        if as_json:
            print(json.dumps(m, indent=2))
        else:
            print(f"{m['id']}\t{m['type']}")
        return 0
    if len(matches) == 0:
        if as_json:
            print(json.dumps({"matches": [], "suggestions": []}, indent=2))
        else:
            print("no matches", file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps({"matches": matches, "ambiguous": True}, indent=2))
    else:
        print("ambiguous matches:", file=sys.stderr)
        for m in matches[:10]:
            print(f"  {m['id']} ({m['type']}) — matched {m.get('matched')}", file=sys.stderr)
        print("hint: re-run with --type <type>", file=sys.stderr)
    return 2


def dashboard(as_json: bool, brief: bool = False) -> int:
    # Delegates to lib/dashboard.py for the richer payload; the narrative
    # printers live in lib/explain.py (single source of truth).
    from importlib import import_module

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    dash = import_module("dashboard")
    payload = dash.build_dashboard(load_registry())
    if brief:
        import_module("explain").print_brief(payload)
        return 0
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        dash.print_dashboard(payload)
    return 0


def cmd_explain_job(job_id: str, job_type: str | None, as_json: bool) -> int:
    from importlib import import_module

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    dash = import_module("dashboard")
    explain_mod = import_module("explain")
    reg = load_registry()
    if not job_type:
        job_type = instance_type(job_id, reg)
    payload = dash.build_dashboard(reg)
    explain = explain_mod.build_explain(job_id, job_type, payload)
    if as_json:
        print(json.dumps(explain, indent=2))
    else:
        explain_mod.print_explain(explain)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="local-jobs registry helpers")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_handler = sub.add_parser("handler-path")
    p_handler.add_argument("--type", required=True)

    p_inst = sub.add_parser("instance-type")
    p_inst.add_argument("--id", required=True)

    p_view = sub.add_parser("view")
    p_view.add_argument("--json", action="store_true")

    p_schema = sub.add_parser("add-schema")
    p_schema.add_argument("--type", required=True)

    p_types = sub.add_parser("job-types")

    sub.add_parser("label-root")

    p_list_types = sub.add_parser("list-types")
    p_list_types.add_argument("--plain", action="store_true")
    p_list_types.add_argument("--json", action="store_true")

    p_desc_types = sub.add_parser("describe-types")
    p_desc_types.add_argument("--json", action="store_true")  # always JSON; accepted for symmetry

    p_resolve = sub.add_parser("resolve-instance")
    p_resolve.add_argument("--query", required=True)
    p_resolve.add_argument("--json", action="store_true")

    p_explain = sub.add_parser("explain-job")
    p_explain.add_argument("--id", required=True)
    p_explain.add_argument("--type", default=None)
    p_explain.add_argument("--json", action="store_true")

    p_dash = sub.add_parser("dashboard")
    p_dash.add_argument("--json", action="store_true")
    p_dash.add_argument("--brief", action="store_true")

    args = parser.parse_args()
    if args.cmd == "handler-path":
        print(handler_path(args.type))
        return 0
    if args.cmd == "instance-type":
        print(instance_type(args.id))
        return 0
    if args.cmd == "view":
        return view_jobs(args.json)
    if args.cmd == "add-schema":
        return add_schema(args.type)
    if args.cmd == "job-types":
        for jtype in job_types(load_registry()):
            print(jtype)
        return 0
    if args.cmd == "label-root":
        print(settings.label_root(load_registry()))
        return 0
    if args.cmd == "list-types":
        reg = load_registry()
        types = build_list_types(reg)
        if args.json:
            print(json.dumps(types, indent=2))
        else:
            print_list_types_plain(types)
        return 0
    if args.cmd == "describe-types":
        print(json.dumps(build_describe_types(load_registry()), indent=2))
        return 0
    if args.cmd == "resolve-instance":
        return cmd_resolve_instance(args.query, args.json)
    if args.cmd == "explain-job":
        return cmd_explain_job(args.id, args.type, args.json)
    if args.cmd == "dashboard":
        return dashboard(args.json, args.brief)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
