"""Agent-facing MCP server — build plan v3 §6: "Agent-facing MCP registration is read-only by
default. Mutation tools are hidden unless explicitly enabled." Built on the low-level
``mcp.server.lowlevel.Server`` (stdio transport) so tool schemas are generated directly from
:data:`operator_voice.domain.operations.OPERATIONS` rather than hand-writing one decorated
function per operation — adding an operation to the registry, and nothing else, makes it appear
here (§6.1).

Mutations are enabled ONLY via the ``OPERATOR_VOICE_MCP_ENABLE_MUTATIONS=1`` environment variable
(never a request-time parameter an agent could set itself) — the read-only default is a runtime
property of how this process was launched, not something a tool call can escalate.

The tool-listing and dispatch logic (:func:`list_available_tools`, :func:`dispatch_tool_call`) are
plain async functions, independent of any live ``Server`` instance, so tests can call them
directly instead of reaching into the SDK's internal request-handler registry.
"""

from __future__ import annotations

import json
import os
from typing import Any

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from operator_voice.application.service import ConfirmationRequired, ServiceError
from operator_voice.application.transactions import OperationRefused
from operator_voice.docs.prompts import PROMPTS, render_prompt_messages
from operator_voice.docs.resources import ACTIVE_RESOURCE_URIS, ALL_RESOURCES, read_resource
from operator_voice.domain.operations import ArgType, Operation, mcp_operations
from operator_voice.interfaces.render import render_json
from operator_voice.runtime.bootstrap import open_runtime

MCP_VERSION = "mcp/v1"
MUTATIONS_ENV_VAR = "OPERATOR_VOICE_MCP_ENABLE_MUTATIONS"

_ARG_TYPE_TO_JSON_SCHEMA = {
    ArgType.STR: {"type": "string"},
    ArgType.INT: {"type": "integer"},
    ArgType.FLOAT: {"type": "number"},
    ArgType.BOOL: {"type": "boolean"},
    ArgType.JSON: {},
}


def mutations_enabled() -> bool:
    return os.environ.get(MUTATIONS_ENV_VAR, "").strip() in ("1", "true", "yes")


def exposed_operations() -> dict[str, Operation]:
    return {op.mcp_name: op for op in mcp_operations(mutations_enabled())}


def _input_schema(op: Operation) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for arg in op.args:
        schema = dict(_ARG_TYPE_TO_JSON_SCHEMA[arg.type])
        if arg.help:
            schema["description"] = arg.help
        if arg.choices:
            schema["enum"] = list(arg.choices)
        properties[arg.name] = schema
        if arg.required and arg.default is None:
            required.append(arg.name)
    return {"type": "object", "properties": properties, "required": required}


async def list_available_tools() -> list[types.Tool]:
    return [
        types.Tool(name=op.mcp_name, description=op.summary, inputSchema=_input_schema(op))
        for op in exposed_operations().values()
    ]


async def list_available_resources() -> list[types.Resource]:
    return [
        types.Resource(uri=r.uri, name=r.title, description=r.description, mimeType="application/json" if r.dynamic else "text/plain")
        for r in ALL_RESOURCES
        if r.uri in ACTIVE_RESOURCE_URIS
    ]


async def list_available_prompts() -> list[types.Prompt]:
    return [
        types.Prompt(
            name=p.name,
            description=p.description,
            arguments=[
                types.PromptArgument(name=a.name, description=a.description, required=a.required)
                for a in p.arguments
            ],
        )
        for p in PROMPTS
    ]


async def dispatch_get_prompt(name: str, arguments: dict[str, Any] | None) -> types.GetPromptResult:
    messages = render_prompt_messages(name, {k: str(v) for k, v in (arguments or {}).items()})
    return types.GetPromptResult(
        messages=[
            types.PromptMessage(role=m["role"], content=types.TextContent(type="text", text=m["content"]))
            for m in messages
        ]
    )


async def dispatch_read_resource(uri: str) -> str:
    from operator_voice.docs.resources import RESOURCES_BY_URI

    spec = RESOURCES_BY_URI.get(uri)
    if spec is not None and not spec.dynamic:
        return read_resource(uri, service=None)  # static text never touches the runtime/Keychain
    runtime = open_runtime()
    try:
        return read_resource(uri, runtime.service)
    finally:
        runtime.close()


async def dispatch_tool_call(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    matching = exposed_operations().get(name)
    if matching is None:
        payload = {"status": "error", "detail": f"unknown or disabled tool: {name!r}"}
        return [types.TextContent(type="text", text=json.dumps(payload))]

    runtime = open_runtime()
    try:
        handler = getattr(runtime.service, matching.handler_name)
        try:
            result = handler(**(arguments or {}))
        except ConfirmationRequired as cr:
            result = cr.to_dict()
        except (OperationRefused, ServiceError) as exc:
            result = {"status": "error", "detail": str(exc)}
        return [types.TextContent(type="text", text=render_json(matching.name, result))]
    finally:
        runtime.close()


def build_server() -> Server:
    server = Server("operator-voice")

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return await list_available_tools()

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        return await dispatch_tool_call(name, arguments)

    @server.list_resources()
    async def _list_resources() -> list[types.Resource]:
        return await list_available_resources()

    @server.read_resource()
    async def _read_resource(uri) -> str:
        return await dispatch_read_resource(str(uri))

    @server.list_prompts()
    async def _list_prompts() -> list[types.Prompt]:
        return await list_available_prompts()

    @server.get_prompt()
    async def _get_prompt(name: str, arguments: dict[str, Any] | None) -> types.GetPromptResult:
        return await dispatch_get_prompt(name, arguments)

    return server


async def run_stdio() -> None:
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    import asyncio

    asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
