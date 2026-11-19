"""CLI — one ``argparse`` subcommand per :data:`operator_voice.domain.operations.OPERATIONS`
entry, including ``Group.LIFECYCLE`` (CLI-only per §6/D13). Deliberately stdlib-only (no third-
party CLI framework) to match this codebase's "stdlib-first" posture (§7) and keep the runtime
dependency footprint auditable. Every subcommand's flags are generated from that operation's
``ArgSpec`` tuple — adding an operation to the registry is the only edit needed for it to appear
here (§6.1).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from operator_voice.application.service import ConfirmationRequired, ServiceError
from operator_voice.application.transactions import OperationRefused
from operator_voice.domain.operations import ArgType, OPERATIONS, Operation
from operator_voice.interfaces.render import render_json
from operator_voice.runtime.bootstrap import open_runtime

CLI_VERSION = "cli/v1"


def _add_arguments(parser: argparse.ArgumentParser, op: Operation) -> None:
    for arg in op.args:
        flag = f"--{arg.name.replace('_', '-')}"
        kwargs: dict[str, Any] = {"help": arg.help, "required": arg.required}
        if arg.default is not None or not arg.required:
            kwargs["required"] = False
            kwargs["default"] = arg.default
        if arg.type == ArgType.INT:
            kwargs["type"] = int
        elif arg.type == ArgType.FLOAT:
            kwargs["type"] = float
        elif arg.type == ArgType.BOOL:
            kwargs["action"] = "store_true"
            kwargs.pop("required", None)
        elif arg.type == ArgType.JSON:
            kwargs["type"] = json.loads
        else:
            kwargs["type"] = str
        if arg.choices:
            kwargs["choices"] = list(arg.choices)
        parser.add_argument(flag, **kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="operator-voice", description="Operator Voice Toolkit (OVT)")
    subparsers = parser.add_subparsers(dest="operation", required=True)
    for op in OPERATIONS:
        sub = subparsers.add_parser(op.cli_name, help=op.summary)
        _add_arguments(sub, op)
        if op.name in ("status", "slack.status", "drive.status", "gmail.status", "google.status"):
            # CLI-only presentation flag (§ OVT Slack/Drive/Gmail Adapter status) — deliberately NOT a
            # registry ArgSpec, so it never leaks into the MCP tool schema; every caller (MCP
            # included) already gets the same `brief` field as part of the normal JSON result.
            sub.add_argument(
                "--brief", action="store_true",
                help="Print just the one-line plain-text summary (for a session-start hook), not full JSON",
            )
        sub.set_defaults(_op=op)
    return parser


def _kwargs_from_namespace(op: Operation, ns: argparse.Namespace) -> dict[str, Any]:
    return {arg.name: getattr(ns, arg.name) for arg in op.args if getattr(ns, arg.name, None) is not None}


# Per-import-operation stdin envelope shape: the identity field the caller may omit from the CLI
# flags (filled from the envelope) + the payload field the envelope carries. Both the Slack and
# Drive adapters accept "JSON file or stdin from agent" (§ OVT Slack/Drive Adapter import).
_STDIN_IMPORT_OPS: dict[str, tuple[str, str]] = {
    "slack.import": ("author_id", "messages"),
    "drive.import": ("owner_id", "files"),
    "gmail.import": ("author_email", "messages"),
}


def _maybe_read_import_stdin(op: Operation, kwargs: dict[str, Any]) -> None:
    """CLI-only stdin fallback for the channel ``*.import`` operations — only triggers when neither
    ``--file`` nor the operation's inline payload flag was given, and reads the exact same envelope
    shape ``--file`` accepts. Mutates ``kwargs`` in place; leaves it untouched (and lets the service
    raise its own clear error) if stdin isn't valid JSON."""
    fields = _STDIN_IMPORT_OPS.get(op.name)
    if fields is None:
        return
    identity_field, payload_field = fields
    if kwargs.get("file") or kwargs.get(payload_field):
        return
    try:
        envelope = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError, ValueError, AttributeError):
        # No usable stdin (closed, pytest's captured-stdin guard, absent entirely, etc.) — leave
        # kwargs alone and let the service raise its own clear error instead.
        return
    if isinstance(envelope, dict):
        kwargs.setdefault(identity_field, envelope.get(identity_field))
        kwargs[payload_field] = envelope.get(payload_field)
        if "sync_cursor" in envelope and envelope.get("sync_cursor") is not None:
            kwargs.setdefault("sync_cursor", envelope.get("sync_cursor"))


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    op: Operation = ns._op
    kwargs = _kwargs_from_namespace(op, ns)
    _maybe_read_import_stdin(op, kwargs)
    brief = bool(getattr(ns, "brief", False))

    runtime = open_runtime()
    try:
        handler = getattr(runtime.service, op.handler_name)
        try:
            result = handler(**kwargs)
        except ConfirmationRequired as cr:
            result = cr.to_dict()
        except OperationRefused as exc:
            print(json.dumps({"status": "refused", "detail": str(exc)}, indent=2))
            return 1
        except ServiceError as exc:
            print(json.dumps({"status": "error", "detail": str(exc)}, indent=2))
            return 1
        if brief and isinstance(result, dict) and "brief" in result:
            print(result["brief"])
        else:
            print(render_json(op.name, result))
        return 0
    finally:
        runtime.close()


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
