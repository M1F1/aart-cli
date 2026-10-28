"""Bounded MCP stdio execution for one already installed launcher."""

from __future__ import annotations

import json
import math
import os
import select
import subprocess
import tempfile
import time
from dataclasses import dataclass
from fractions import Fraction
from typing import IO, cast

from aart_cli.application.mcp_smoke import (
    McpCallResult,
    McpNumber,
    McpTool,
    SmokeDeclaration,
    SmokeOutcome,
    evaluate_tool_call,
)
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.protocol.json import (
    MAX_PROTOCOL_INTEGER,
    MIN_PROTOCOL_INTEGER,
    JsonArray,
    JsonObject,
    JsonValue,
)

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


#: The bounds `parse_json` keeps on aart-cli's own documents, kept on what a server says too.
_MAX_DEPTH = 64
_MAX_STRING_LENGTH = 1_000_000


class _NotJson(ValueError):
    pass


def _number(value: float | int) -> JsonValue:
    """A server's number: an integer when it is whole and fits, else exactly what was written.

    FastMCP writes a `float` parameter's bounds as `0.0` and `1.0` and its answers carry ratios,
    so refusing every fraction refused the whole `tools/list` (§205). `repr` is the shortest text
    that reads back as the same float, which is the decimal the server wrote.
    """

    if isinstance(value, float):
        if not math.isfinite(value):
            raise _NotJson("MCP returned a number that is not finite")
        exact = Fraction(repr(value))
    else:
        exact = Fraction(value)
    if exact.denominator == 1 and MIN_PROTOCOL_INTEGER <= exact <= MAX_PROTOCOL_INTEGER:
        return int(exact)
    # Only the smoke's validator and preview read these trees; see `McpNumber`.
    return cast(JsonValue, McpNumber(exact))


def _frozen(value: object, depth: int) -> JsonValue:
    if depth > _MAX_DEPTH:
        raise _NotJson("MCP returned JSON nested beyond the supported depth")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return _number(value)
    if isinstance(value, str):
        if len(value) > _MAX_STRING_LENGTH:
            raise _NotJson("MCP returned a string beyond the supported length")
        return value
    if isinstance(value, list):
        return JsonArray(tuple(_frozen(item, depth + 1) for item in value))
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return JsonObject(tuple((key, _frozen(item, depth + 1)) for key, item in value.items()))
    raise _NotJson("MCP returned a value that is not JSON")


def _freeze(value: object) -> Result[JsonValue]:
    try:
        return Ok(_frozen(value, 0))
    except _NotJson as error:
        return _error(str(error))
    except RecursionError:
        return _error("MCP returned JSON nested beyond the supported depth")


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


#: A launcher that died says why on stderr, and that sentence is the whole diagnosis. Bounded
#: because it reaches a diagnostic a person reads, and a server that logs freely would otherwise
#: put a megabyte there.
_MAX_STDERR_BYTES = 2048
_REFUSED = "declared MCP call was refused before invocation"


def _annotate(failure: Err, errors: IO[bytes]) -> Err:
    """Put what the launcher said on stderr into the diagnostic that says it stopped.

    Without this the one sentence naming the cause is written to a file nobody reads and the
    operator is told only that the exchange did not complete -- which is the symptom, never the
    reason.
    """

    try:
        errors.seek(0)
        raw = errors.read(_MAX_STDERR_BYTES)
    except (OSError, ValueError):
        return failure
    said = " ".join(raw.decode("utf-8", "replace").split())
    if not said:
        return failure
    first = failure.diagnostics[0]
    return Err(
        (
            Diagnostic(first.code, first.severity, f"{first.message}: {said}"),
            *failure.diagnostics[1:],
        )
    )


def execute_stdio_smoke(
    launcher: str,
    declaration: SmokeDeclaration,
    *,
    cwd: str,
    harness: str,
) -> Result[DirectSmokeRun]:
    """Start one exact installed launcher and invoke only its declared operation.

    `harness` is passed to the launcher as its one argument, because that is how a launcher learns
    which harness started it and therefore which configuration file under `config/` to read. A
    harness registration passes it; this route is a second caller of the same contract and has to
    pass it too. Omitting it made every launcher carrying configuration refuse to start, and the
    refusal it printed went to a discarded stderr, so the smoke reported only that the process had
    closed (B-173).
    """

    with tempfile.TemporaryFile() as errors:
        outcome = _execute(launcher, declaration, cwd=cwd, harness=harness, errors=errors)
        if isinstance(outcome, Ok) or outcome.diagnostics[0].message.startswith(_REFUSED):
            # A refusal is the schema's verdict, not the process's: what the server logged while
            # starting (FastMCP prints a banner) would bury the one line that names the keyword.
            return outcome
        return _annotate(outcome, errors)


def _execute(
    launcher: str,
    declaration: SmokeDeclaration,
    *,
    cwd: str,
    harness: str,
    errors: IO[bytes],
) -> Result[DirectSmokeRun]:
    """The bounded exchange itself, with stderr going somewhere `execute_stdio_smoke` can read."""

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
            [launcher, harness],
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=errors,
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
        preflight = evaluate_tool_call(declaration, tools.value, None)
        if preflight.outcome is not SmokeOutcome.NOT_RUN:
            return _error(f"{_REFUSED}: {preflight.reason}")
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
    except BrokenPipeError:
        # A launcher that refuses exits at once, often before the first message is written, so
        # whether this or an empty read reports it is a race. Both mean the same thing.
        return _error("installed MCP closed before the protocol exchange completed")
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
