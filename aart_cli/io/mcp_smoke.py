"""Bounded MCP stdio execution for one already installed launcher."""

from __future__ import annotations

import json
import os
import select
import subprocess
import time
from dataclasses import dataclass

from aart_cli.application.mcp_smoke import (
    McpCallResult,
    McpTool,
    SmokeDeclaration,
    SmokeOutcome,
    evaluate_tool_call,
)
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.protocol.json import JsonArray, JsonObject, JsonValue, parse_json

MCP_SMOKE_EXECUTION_FAILED = DiagnosticCode("mcp-smoke-execution-failed")
_MAX_OUTPUT_BYTES = 1024 * 1024
_PROTOCOL_VERSION = "2025-11-25"


@dataclass(frozen=True, slots=True)
class DirectSmokeRun:
    protocol_version: str
    tools: tuple[McpTool, ...]
    result: McpCallResult


def _error(message: str) -> Err:
    return Err((Diagnostic(MCP_SMOKE_EXECUTION_FAILED, Severity.ERROR, message),))


def _thaw(value: JsonValue) -> object:
    if isinstance(value, JsonObject):
        return {key: _thaw(item) for key, item in value.entries}
    if isinstance(value, JsonArray):
        return [_thaw(item) for item in value.items]
    return value


def _freeze(value: object) -> Result[JsonValue]:
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError):
        return _error("MCP returned a value that is not JSON")
    parsed = parse_json(encoded)
    if isinstance(parsed, Err):
        return _error("MCP returned JSON outside the supported bounded protocol")
    return parsed


def _messages(values: tuple[dict[str, object], ...]) -> bytes:
    return b"".join(
        json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
        for value in values
    )


def _start_messages() -> bytes:
    return _messages(
        (
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": _PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "aart-cli", "version": "1"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
    )


def _call_message(declaration: SmokeDeclaration) -> bytes:
    return _messages(
        (
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": declaration.tool,
                    "arguments": _thaw(declaration.arguments),
                },
            },
        )
    )


def _read_responses(
    process: subprocess.Popen[bytes],
    identifiers: frozenset[int],
    *,
    deadline: float,
) -> Result[list[dict[str, object]]]:
    assert process.stdout is not None
    rows: list[dict[str, object]] = []
    size = 0
    found: set[int] = set()
    while not identifiers <= found:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return _error("installed MCP smoke call exceeded its declared timeout")
        ready, _, _ = select.select((process.stdout,), (), (), remaining)
        if not ready:
            return _error("installed MCP smoke call exceeded its declared timeout")
        line = process.stdout.readline()
        if not line:
            return _error("installed MCP closed before the protocol exchange completed")
        size += len(line)
        if size > _MAX_OUTPUT_BYTES:
            return _error("installed MCP returned more than the bounded output limit")
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _error("installed MCP emitted malformed JSON-RPC")
        if not isinstance(value, dict):
            return _error("installed MCP emitted a non-object protocol message")
        rows.append(value)
        identifier = value.get("id")
        if isinstance(identifier, int) and not isinstance(identifier, bool):
            found.add(identifier)
    return Ok(rows)


def _response(lines: list[dict[str, object]], identifier: int) -> dict[str, object] | None:
    return next((line for line in lines if line.get("id") == identifier), None)


def _tools(response: dict[str, object] | None) -> Result[tuple[McpTool, ...]]:
    if response is None or "error" in response:
        return _error("MCP tools/list did not complete successfully")
    result = response.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("tools"), list):
        return _error("MCP tools/list returned a malformed result")
    tools: list[McpTool] = []
    for raw in result["tools"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
            return _error("MCP tools/list returned a malformed tool")
        input_schema = _freeze(raw.get("inputSchema", {}))
        output_schema = None if "outputSchema" not in raw else _freeze(raw.get("outputSchema"))
        if isinstance(input_schema, Err) or isinstance(output_schema, Err):
            return _error("MCP tool schema is not supported JSON")
        output_value = None if output_schema is None else output_schema.value
        if not isinstance(input_schema.value, JsonObject) or not (
            output_value is None or isinstance(output_value, JsonObject)
        ):
            return _error("MCP tool schema must be an object")
        tools.append(
            McpTool(
                raw["name"],
                input_schema.value,
                output_value,
            )
        )
    return Ok(tuple(tools))


def _call(response: dict[str, object] | None) -> Result[McpCallResult]:
    if response is None:
        return _error("MCP tools/call did not return a current response")
    if "error" in response:
        return Ok(McpCallResult(jsonrpc_error="present"))
    raw = response.get("result")
    if not isinstance(raw, dict):
        return _error("MCP tools/call returned a malformed result")
    content = None
    if "content" in raw:
        frozen_content = _freeze(raw["content"])
        if isinstance(frozen_content, Err) or not isinstance(frozen_content.value, JsonArray):
            return _error("MCP tools/call content is malformed")
        content = frozen_content.value
    structured = None
    if "structuredContent" in raw:
        frozen_structured = _freeze(raw["structuredContent"])
        if isinstance(frozen_structured, Err):
            return frozen_structured
        structured = frozen_structured.value
    return Ok(
        McpCallResult(
            content=content,
            structured_content=structured,
            # Preserve malformed values so the pure evaluator, not this adapter, owns the verdict.
            is_error=raw.get("isError"),
        )
    )


def execute_stdio_smoke(
    launcher: str,
    declaration: SmokeDeclaration,
    *,
    cwd: str,
) -> Result[DirectSmokeRun]:
    """Start one exact installed launcher and invoke only its declared operation."""

    if (
        not os.path.isabs(launcher)
        or not os.path.isfile(launcher)
        or not os.path.isabs(cwd)
        or not os.path.isdir(cwd)
    ):
        return _error("installed MCP launcher or root is unavailable")
    process: subprocess.Popen[bytes] | None = None
    deadline = time.monotonic() + declaration.timeout_seconds
    try:
        process = subprocess.Popen(
            [launcher],
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
            start_new_session=True,
        )
        assert process.stdin is not None
        process.stdin.write(_start_messages())
        process.stdin.flush()
        started = _read_responses(process, frozenset({1, 2}), deadline=deadline)
        if isinstance(started, Err):
            return started
        initialize = _response(started.value, 1)
        if initialize is None or "error" in initialize:
            return _error("installed MCP did not initialize successfully")
        params = initialize.get("result")
        if not isinstance(params, dict) or not isinstance(params.get("protocolVersion"), str):
            return _error("installed MCP initialize result is malformed")
        tools = _tools(_response(started.value, 2))
        if isinstance(tools, Err):
            return tools
        preflight = evaluate_tool_call(declaration, tools.value, None).protocol
        if preflight.outcome is not SmokeOutcome.NOT_RUN:
            return _error(f"declared MCP call was refused before invocation: {preflight.reason}")
        process.stdin.write(_call_message(declaration))
        process.stdin.flush()
        called = _read_responses(process, frozenset({3}), deadline=deadline)
        if isinstance(called, Err):
            return called
        call = _call(_response(called.value, 3))
        if isinstance(call, Err):
            return call
        process.stdin.close()
        remaining = max(0.0, deadline - time.monotonic())
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            return _error("installed MCP did not stop after the bounded smoke call")
        if returncode != 0:
            return _error("installed MCP process exited unsuccessfully")
        return Ok(DirectSmokeRun(params["protocolVersion"], tools.value, call.value))
    except OSError:
        return _error("installed MCP launcher could not be started")
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        if process is not None:
            for stream in (process.stdin, process.stdout):
                if stream is not None and not stream.closed:
                    stream.close()


__all__ = ["DirectSmokeRun", "MCP_SMOKE_EXECUTION_FAILED", "execute_stdio_smoke"]
