#!/usr/bin/env python3
"""Generic id-keyed CRUD store for local-jobs instance config (jobs/v1).

One implementation for every type's ``config/jobs/<type>.yml`` — load/save/
find/add/set/remove with dup-id rejection, id sanitization, dry-run, and
load-time forward migration (single re-merge-at-load policy via
:mod:`migrate`). Handlers shape their own entry JSON and hand it here; the store
stays type-agnostic. Consolidates the former ``command_store.py`` and the
id-keyed half of the igf backend ``config.py``.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, TypeVar

import yaml

import contract
import migrate
import schedule as schedule_mod

T = TypeVar("T")


class Store:
    def __init__(
        self,
        path: Path,
        schema_version: int = 1,
        field_defaults: dict[str, Any] | None = None,
        required: list[str] | None = None,
    ) -> None:
        self.path = Path(path).expanduser()
        self.schema_version = schema_version
        self.field_defaults = field_defaults or {}
        self.required = required or []

    def _skeleton(self) -> dict[str, Any]:
        return {"schema": "jobs/v1", "version": 1, "schema_version": self.schema_version, "instances": []}

    def _lock_path(self) -> Path:
        return self.path.parent / (self.path.name + ".lock")

    def _with_lock(self, fn: Callable[[], T]) -> T:
        lock = self._lock_path()
        lock.parent.mkdir(parents=True, exist_ok=True)
        with lock.open("w") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                return fn()
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read_raw(self) -> dict[str, Any]:
        if not self.path.is_file():
            return self._skeleton()
        with self.path.open() as handle:
            data = yaml.safe_load(handle) or {}
        if data.get("version") not in (None, 1):
            raise SystemExit(f"unsupported store file version: {data.get('version')!r}")
        data.setdefault("schema", "jobs/v1")
        data.setdefault("instances", [])
        return data

    def load(self) -> dict[str, Any]:
        """Read + forward-migrate in memory (re-merge defaults, stamp version)."""

        def _do() -> dict[str, Any]:
            data = self._read_raw()
            migrate.forward_migrate(data, self.schema_version, self.field_defaults)
            return data

        return self._with_lock(_do)

    def save(self, data: dict[str, Any]) -> Path:
        def _do() -> Path:
            migrate.forward_migrate(data, self.schema_version, self.field_defaults)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            with tmp.open("w") as handle:
                yaml.safe_dump(data, handle, default_flow_style=False, sort_keys=False)
            tmp.replace(self.path)
            return self.path

        return self._with_lock(_do)

    def list(self) -> list[dict[str, Any]]:
        return self.load().get("instances") or []

    def find(self, iid: str) -> dict[str, Any] | None:
        for entry in self.list():
            if isinstance(entry, dict) and entry.get("id") == iid:
                return entry
        return None

    def get(self, iid: str) -> dict[str, Any]:
        entry = self.find(iid)
        if entry is None:
            raise SystemExit(f"instance not found: {iid}")
        return entry

    def _required_fields(self, entry: dict[str, Any]) -> list[str]:
        """Field names required for THIS entry.

        Each ``required`` spec is either a plain field name (always required) or
        an object ``{"field": <name>, "unless": {"field": <k>, "equals": <v>}}``
        whose requirement is waived when the referenced field equals the given
        value (e.g. ``schedule`` is not required for ``execution_mode:
        on_demand``). Plain-string lists keep their exact prior behavior.
        """
        out: list[str] = []
        for spec in self.required:
            if isinstance(spec, str):
                out.append(spec)
                continue
            if isinstance(spec, dict) and spec.get("field"):
                cond = spec.get("unless")
                if isinstance(cond, dict) and entry.get(cond.get("field")) == cond.get("equals"):
                    continue
                out.append(str(spec["field"]))
        return out

    @staticmethod
    def _schedule_errors(entry: dict[str, Any]) -> list[str]:
        value = entry.get("schedule")
        if value in (None, ""):
            return []
        try:
            sched = schedule_mod.Schedule.parse(value)
        except (KeyError, TypeError, ValueError) as exc:
            return [str(exc)]
        return sched.validate()

    def add(self, entry: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
        iid = entry.get("id")
        contract.sanitize_id(iid or "")
        for field in self._required_fields(entry):
            if field not in entry or entry[field] in (None, ""):
                raise SystemExit(f"missing required field: {field}")
        schedule_errors = self._schedule_errors(entry)
        if schedule_errors:
            raise SystemExit(f"{iid}: invalid schedule: {'; '.join(schedule_errors)}")

        def _do() -> dict[str, Any]:
            data = self._read_raw()
            migrate.forward_migrate(data, self.schema_version, self.field_defaults)
            if any(e.get("id") == iid for e in data["instances"]):
                raise SystemExit(f"instance already exists: {iid}")
            if dry_run:
                return {"dry_run": True, "would_add": entry}
            data["instances"].append(entry)
            migrate.forward_migrate(data, self.schema_version, self.field_defaults)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            with tmp.open("w") as handle:
                yaml.safe_dump(data, handle, default_flow_style=False, sort_keys=False)
            tmp.replace(self.path)
            return {"added": iid}

        return self._with_lock(_do)

    def set(self, iid: str, patch: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
        def _do() -> dict[str, Any]:
            data = self._read_raw()
            migrate.forward_migrate(data, self.schema_version, self.field_defaults)
            for entry in data["instances"]:
                if entry.get("id") == iid:
                    candidate = {**entry, **patch}
                    # Re-check required fields on the merged candidate, mirroring
                    # add(): an update that flips a conditional (e.g. execution_mode
                    # on_demand -> scheduled) must still satisfy the now-required
                    # field (schedule), or the write would produce a scheduled
                    # instance with no trigger.
                    for field in self._required_fields(candidate):
                        if field not in candidate or candidate[field] in (None, ""):
                            raise SystemExit(f"missing required field: {field}")
                    schedule_errors = self._schedule_errors(candidate)
                    if schedule_errors:
                        raise SystemExit(
                            f"{iid}: invalid schedule: {'; '.join(schedule_errors)}"
                        )
                    if dry_run:
                        return {"dry_run": True, "id": iid, "patch": patch}
                    entry.update(patch)
                    migrate.forward_migrate(data, self.schema_version, self.field_defaults)
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    tmp = self.path.with_suffix(self.path.suffix + ".tmp")
                    with tmp.open("w") as handle:
                        yaml.safe_dump(data, handle, default_flow_style=False, sort_keys=False)
                    tmp.replace(self.path)
                    return {"updated": iid}
            raise SystemExit(f"instance not found: {iid}")

        return self._with_lock(_do)

    def remove(self, iid: str, dry_run: bool = False) -> dict[str, Any]:
        def _do() -> dict[str, Any]:
            data = self._read_raw()
            migrate.forward_migrate(data, self.schema_version, self.field_defaults)
            if not any(e.get("id") == iid for e in data["instances"]):
                raise SystemExit(f"instance not found: {iid}")
            if dry_run:
                return {"dry_run": True, "would_remove": iid}
            data["instances"] = [e for e in data["instances"] if e.get("id") != iid]
            migrate.forward_migrate(data, self.schema_version, self.field_defaults)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            with tmp.open("w") as handle:
                yaml.safe_dump(data, handle, default_flow_style=False, sort_keys=False)
            tmp.replace(self.path)
            return {"removed": iid}

        return self._with_lock(_do)

    def validate(self) -> list[str]:
        data = self.load()
        errs: list[str] = []
        seen: set[str] = set()
        for entry in data["instances"]:
            iid = entry.get("id")
            if not iid:
                errs.append("instance missing id")
                continue
            try:
                contract.sanitize_id(iid)
            except ValueError as exc:
                errs.append(str(exc))
            if iid in seen:
                errs.append(f"duplicate id: {iid}")
            seen.add(iid)
            for field in self._required_fields(entry):
                if field not in entry or entry[field] in (None, ""):
                    errs.append(f"{iid}: missing required field {field}")
            for schedule_error in self._schedule_errors(entry):
                errs.append(f"{iid}: invalid schedule: {schedule_error}")
        return errs

    def migrate(self) -> dict[str, Any]:
        data = self._read_raw()
        _, changed = migrate.forward_migrate(data, self.schema_version, self.field_defaults)
        if changed:
            self.save(data)
        return {"migrated": changed, "schema_version": self.schema_version, "count": len(data.get("instances") or [])}


def _store_from_args(args: argparse.Namespace) -> Store:
    defaults = json.loads(args.defaults) if args.defaults else {}
    required = json.loads(args.required) if args.required else []
    return Store(Path(args.file), schema_version=args.schema_version, field_defaults=defaults, required=required)


def main() -> int:
    ap = argparse.ArgumentParser(prog="store.py")
    ap.add_argument("--file", required=True)
    ap.add_argument("--schema-version", type=int, default=1)
    ap.add_argument("--defaults", default=None, help="JSON object of optional-field defaults")
    ap.add_argument("--required", default=None, help="JSON array of required field names")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    g = sub.add_parser("get"); g.add_argument("--id", required=True)
    a = sub.add_parser("add"); a.add_argument("--entry", required=True); a.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("set"); s.add_argument("--id", required=True); s.add_argument("--patch", required=True); s.add_argument("--dry-run", action="store_true")
    r = sub.add_parser("remove"); r.add_argument("--id", required=True); r.add_argument("--dry-run", action="store_true")
    sub.add_parser("validate")
    sub.add_parser("migrate")

    args = ap.parse_args()
    store = _store_from_args(args)

    if args.cmd == "list":
        print(json.dumps(store.list(), indent=2))
        return 0
    if args.cmd == "get":
        print(json.dumps(store.get(args.id), indent=2))
        return 0
    if args.cmd == "add":
        print(json.dumps(store.add(json.loads(args.entry), args.dry_run), indent=2))
        return 0
    if args.cmd == "set":
        print(json.dumps(store.set(args.id, json.loads(args.patch), args.dry_run), indent=2))
        return 0
    if args.cmd == "remove":
        print(json.dumps(store.remove(args.id, args.dry_run), indent=2))
        return 0
    if args.cmd == "validate":
        errs = store.validate()
        if errs:
            print("\n".join(errs), file=sys.stderr)
            return 2
        print("ok")
        return 0
    if args.cmd == "migrate":
        print(json.dumps(store.migrate(), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
