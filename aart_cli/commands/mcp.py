"""CLI-only smoke verification for already installed MCP artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from aart_cli import command_outcome as _common
from aart_cli.application.mcp_smoke import (
    McpCallResult,
    McpTool,
    SmokeDeclaration,
    SmokeOutcome,
    SmokeStage,
    SmokeStageResult,
    aggregate_success,
    declaration_from_intent,
    evaluate_tool_call,
    select_installed_mcps,
)
from aart_cli.configuration.policy import redact_text
from aart_cli.domain.configuration_files import parse_configuration_file
from aart_cli.domain.credentials import CredentialState, ProviderState
from aart_cli.domain.harness import Scope
from aart_cli.domain.installation_owner import installation_key
from aart_cli.domain.receipts import InstallationReceipt, InstalledRecord
from aart_cli.domain.result import Err
from aart_cli.io.credentials import MacOsKeychainProvider
from aart_cli.io.harness_smoke import run_harness_smoke
from aart_cli.io.mcp_smoke import execute_stdio_smoke
from aart_cli.io.object_store import read_object
from aart_cli.io.receipt_store import LocalReceiptStore
from aart_cli.model import Request
from aart_cli.protocol.authoring import AUTHORING_EXTENSION
from aart_cli.protocol.json import JsonArray, JsonObject, JsonValue
from aart_cli.protocol.native_schema import parse_artifact_manifest
from aart_cli.protocol.native_tree import SnapshotEntryKind
from aart_cli.receipt_service import resolved_paths
from aart_cli.store.model import ObjectReadRequest, object_store_paths

from ._configured_runtime import load_runtime_configuration

_OPERATION = "mcp.test"
_HARNESSES = frozenset({"opencode", "tabnine", "claude"})
_MAX_RESPONSE_BYTES = 64 * 1024


def _stage_data(stage: SmokeStageResult) -> dict[str, str]:
    return {"stage": stage.stage.value, "outcome": stage.outcome.value, "reason": stage.reason}


def _plain(value: JsonValue) -> object:
    if isinstance(value, JsonObject):
        return {key: _plain(item) for key, item in value.entries}
    if isinstance(value, JsonArray):
        return [_plain(item) for item in value.items]
    return value


def _response_preview(result: McpCallResult, *, sensitive: tuple[str, ...]) -> dict[str, object]:
    document: dict[str, object] = {}
    if result.content is not None:
        document["content"] = _plain(result.content)
    if result.structured_content is not None:
        document["structuredContent"] = _plain(result.structured_content)
    if result.is_error is not None:
        document["isError"] = result.is_error
    encoded = json.dumps(document, ensure_ascii=True, separators=(",", ":"))
    for value in sorted((item for item in sensitive if item), key=len, reverse=True):
        encoded = encoded.replace(value, "<redacted>")
    truncated = len(encoded.encode("utf-8")) > _MAX_RESPONSE_BYTES
    if truncated:
        encoded = encoded[:_MAX_RESPONSE_BYTES]
    return {
        "format": "mcp-result-json",
        "truncated": truncated,
        "content": encoded,
        "warning": (
            "The response may contain confidential service data; redirected output is retained "
            "by the caller."
        ),
    }


def _failure(request: Request, message: str) -> int:
    safe = redact_text(message)
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": False,
                    "operation": _OPERATION,
                    "diagnostics": [{"code": "mcp-smoke-invalid", "message": safe}],
                },
                indent=2,
            )
        )
    else:
        print(f"error: {safe}")
    return _common.ERROR


def _configuration_values(receipt: InstallationReceipt) -> tuple[dict[str, str], str | None]:
    owner = receipt.owner
    if owner is None:
        return {}, "the installation record has no owner"
    if not os.path.isfile(receipt.launcher) or not os.access(receipt.launcher, os.X_OK):
        return {}, "the installed launcher is absent or not executable"
    try:
        launcher_bytes = Path(receipt.launcher).read_bytes()
    except OSError:
        return {}, "the installed launcher cannot be read"
    if hashlib.sha256(launcher_bytes).hexdigest() != receipt.launcher_digest.value:
        return {}, "the installed launcher differs from its receipt"

    values: dict[str, str] = {}
    for record in receipt.configuration_files:
        if record.harness != owner.harness:
            continue
        try:
            content = Path(record.path).read_bytes()
        except OSError:
            return {}, "the installation configuration file is unavailable"
        if hashlib.sha256(content).hexdigest() != record.digest.value:
            return {}, "the installation configuration differs from its receipt"
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError:
            return {}, "the installation configuration is not UTF-8"
        parsed = parse_configuration_file(decoded)
        if isinstance(parsed, Err):
            return {}, "the installation configuration is malformed"
        values.update((identifier.value, value) for identifier, value in parsed.value)

    provider = MacOsKeychainProvider()
    for reference in receipt.credentials:
        if reference.provider.provider != provider.provider:
            return {}, "the installation credential provider is unsupported on this host"
        observed = provider.inspect(reference)
        if isinstance(observed, Err):
            return {}, "the installation credential could not be inspected"
        if (
            observed.value.provider_state is not ProviderState.AVAILABLE
            or observed.value.state is not CredentialState.PRESENT
        ):
            return {}, "an installation credential is missing or its provider is unavailable"
    return values, None


def _resolve_arguments(value: JsonValue, config: dict[str, str]) -> JsonValue:
    if isinstance(value, JsonArray):
        return JsonArray(tuple(_resolve_arguments(item, config) for item in value.items))
    if not isinstance(value, JsonObject):
        return value
    fields = dict(value.entries)
    if fields.keys() == {"configuration"} and isinstance(fields["configuration"], str):
        name = fields["configuration"]
        if name not in config:
            raise KeyError(name)
        return config[name]
    return JsonObject(tuple((key, _resolve_arguments(item, config)) for key, item in value.entries))


def _declaration(
    record: InstalledRecord, data_root: str
) -> tuple[SmokeDeclaration | None, str | None]:
    receipt = record.receipt
    assert isinstance(receipt, InstallationReceipt)
    if receipt.object_digest is None:
        return None, "the installation record does not identify its immutable content"
    loaded = read_object(ObjectReadRequest(object_store_paths(data_root), receipt.object_digest))
    if isinstance(loaded, Err) or loaded.value is None:
        return None, "the installed canonical content is unavailable"
    entry = next(
        (
            item
            for item in loaded.value.candidate.entries
            if str(item.path) == "artifact.json" and item.kind is SnapshotEntryKind.FILE
        ),
        None,
    )
    if entry is None:
        return None, "the installed canonical content has no artifact manifest"
    parsed = parse_artifact_manifest(entry.content, path="artifact.json")
    if isinstance(parsed, Err):
        return None, "the installed canonical artifact manifest is invalid"
    intent = dict(parsed.value.extensions).get(AUTHORING_EXTENSION)
    smoke = intent.get("smoke_test") if isinstance(intent, JsonObject) else None
    declaration = declaration_from_intent(smoke)
    if declaration is None:
        return None, "the installed content has no valid declared read-only smoke operation"
    return declaration, None


def _harness_stages(
    receipt: InstallationReceipt,
    declaration_and_tools: tuple[SmokeDeclaration, tuple[McpTool, ...]] | None,
) -> tuple[SmokeStageResult, SmokeStageResult, SmokeStageResult, str | None, str]:
    assert receipt.owner is not None
    harness = receipt.owner.harness
    if harness == "tabnine":
        reason = "Tabnine has no verified pre-invocation allowed-tools boundary"
        excluded = SmokeStageResult(SmokeStage.MODEL_PROVIDER, SmokeOutcome.NOT_RUN, reason)
        return (
            excluded,
            SmokeStageResult(SmokeStage.HARNESS, SmokeOutcome.NOT_RUN, reason),
            SmokeStageResult(SmokeStage.MODEL_ASSESSMENT, SmokeOutcome.NOT_RUN, reason),
            None,
            "direct",
        )
    executable = shutil.which(harness)
    if executable is None:
        blocked = SmokeStageResult(
            SmokeStage.MODEL_PROVIDER,
            SmokeOutcome.BLOCKED,
            f"{harness} CLI is not installed",
        )
        return (
            blocked,
            SmokeStageResult(
                SmokeStage.HARNESS,
                SmokeOutcome.NOT_RUN,
                f"depends on {SmokeStage.MODEL_PROVIDER.value}",
            ),
            SmokeStageResult(
                SmokeStage.MODEL_ASSESSMENT,
                SmokeOutcome.NOT_RUN,
                f"depends on {SmokeStage.MODEL_PROVIDER.value}",
            ),
            None,
            "direct-and-harness",
        )
    if declaration_and_tools is None:
        return (
            SmokeStageResult(
                SmokeStage.MODEL_PROVIDER,
                SmokeOutcome.NOT_RUN,
                "the installed content has no executable smoke operation",
            ),
            SmokeStageResult(
                SmokeStage.HARNESS,
                SmokeOutcome.NOT_RUN,
                "the installed content has no executable smoke operation",
            ),
            SmokeStageResult(
                SmokeStage.MODEL_ASSESSMENT,
                SmokeOutcome.NOT_RUN,
                "the installed content has no executable smoke operation",
            ),
            None,
            "direct-and-harness",
        )
    declaration, tools = declaration_and_tools
    registration = next(
        (item for item in receipt.registrations if item.target.harness == harness), None
    )
    if registration is None:
        return (
            SmokeStageResult(
                SmokeStage.MODEL_PROVIDER,
                SmokeOutcome.NOT_RUN,
                "the selected harness registration is absent",
            ),
            SmokeStageResult(
                SmokeStage.HARNESS,
                SmokeOutcome.NOT_CONFIGURED,
                "the selected harness registration is absent",
            ),
            SmokeStageResult(
                SmokeStage.MODEL_ASSESSMENT,
                SmokeOutcome.NOT_RUN,
                "the selected harness registration is absent",
            ),
            None,
            "direct-and-harness",
        )
    run = run_harness_smoke(
        harness,
        executable,
        registration.server,
        declaration,
        cwd=receipt.owner.root,
    )
    try:
        outcome = SmokeOutcome(run.outcome)
    except ValueError:
        outcome = SmokeOutcome.FAIL
    if run.result is None or outcome is not SmokeOutcome.PASS:
        model_outcome = SmokeOutcome.BLOCKED if outcome is SmokeOutcome.BLOCKED else outcome
        return (
            SmokeStageResult(SmokeStage.MODEL_PROVIDER, model_outcome, run.reason),
            SmokeStageResult(
                SmokeStage.HARNESS,
                SmokeOutcome.NOT_RUN if outcome is SmokeOutcome.BLOCKED else outcome,
                run.reason,
            ),
            SmokeStageResult(
                SmokeStage.MODEL_ASSESSMENT,
                SmokeOutcome(run.assessment.outcome),
                run.assessment.reason,
            ),
            run.version,
            run.coverage,
        )
    evaluated = evaluate_tool_call(declaration, tools, run.result)
    route_outcome: SmokeOutcome
    if evaluated.protocol.outcome is not SmokeOutcome.PASS:
        route_outcome = evaluated.protocol.outcome
        reason = evaluated.protocol.reason
    elif evaluated.expectation.outcome is SmokeOutcome.FAIL:
        route_outcome = SmokeOutcome.FAIL
        reason = evaluated.expectation.reason
    elif evaluated.service.outcome is SmokeOutcome.NOT_VERIFIED:
        route_outcome = SmokeOutcome.NOT_VERIFIED
        reason = (
            "the harness call completed, but external-service access is not independently proven"
        )
    else:
        route_outcome = SmokeOutcome.PASS
        reason = run.reason
    return (
        SmokeStageResult(
            SmokeStage.MODEL_PROVIDER,
            SmokeOutcome.PASS,
            "the harness obtained a current model response and completed the allowed tool call",
        ),
        SmokeStageResult(SmokeStage.HARNESS, route_outcome, reason),
        SmokeStageResult(
            SmokeStage.MODEL_ASSESSMENT,
            SmokeOutcome(run.assessment.outcome),
            run.assessment.reason,
        ),
        run.version,
        run.coverage,
    )


def _target(
    record: InstalledRecord, data_root: str, *, show_response: bool = False
) -> dict[str, object]:
    receipt = record.receipt
    assert isinstance(receipt, InstallationReceipt) and receipt.owner is not None
    owner = receipt.owner
    stages: list[SmokeStageResult] = []
    harness_context: tuple[SmokeDeclaration, tuple[McpTool, ...]] | None = None
    direct_result = None
    expectation_configured = False
    service_configured = False
    config, config_failure = _configuration_values(receipt)
    if config_failure is not None:
        stages.append(
            SmokeStageResult(SmokeStage.INSTALLATION, SmokeOutcome.BLOCKED, config_failure)
        )
        stages.extend(
            (
                SmokeStageResult(
                    SmokeStage.PROTOCOL,
                    SmokeOutcome.NOT_RUN,
                    f"depends on {SmokeStage.INSTALLATION.value}",
                ),
                SmokeStageResult(
                    SmokeStage.EXPECTATION,
                    SmokeOutcome.NOT_RUN,
                    f"depends on {SmokeStage.PROTOCOL.value}",
                ),
                SmokeStageResult(
                    SmokeStage.SERVICE,
                    SmokeOutcome.NOT_RUN,
                    f"depends on {SmokeStage.PROTOCOL.value}",
                ),
            )
        )
    else:
        stages.append(
            SmokeStageResult(
                SmokeStage.INSTALLATION,
                SmokeOutcome.PASS,
                "receipt, launcher, configuration and credential references are usable",
            )
        )
        declaration, declaration_failure = _declaration(record, data_root)
        if declaration_failure is not None or declaration is None:
            stages.extend(
                (
                    SmokeStageResult(
                        SmokeStage.PROTOCOL,
                        SmokeOutcome.NOT_CONFIGURED,
                        declaration_failure or "smoke operation is not configured",
                    ),
                    SmokeStageResult(
                        SmokeStage.EXPECTATION,
                        SmokeOutcome.NOT_RUN,
                        f"depends on {SmokeStage.PROTOCOL.value}",
                    ),
                    SmokeStageResult(
                        SmokeStage.SERVICE,
                        SmokeOutcome.NOT_RUN,
                        f"depends on {SmokeStage.PROTOCOL.value}",
                    ),
                )
            )
        else:
            try:
                arguments = _resolve_arguments(declaration.arguments, config)
            except KeyError:
                stages.extend(
                    (
                        SmokeStageResult(
                            SmokeStage.PROTOCOL,
                            SmokeOutcome.NOT_CONFIGURED,
                            "a declared installation configuration argument is unavailable",
                        ),
                        SmokeStageResult(
                            SmokeStage.EXPECTATION,
                            SmokeOutcome.NOT_RUN,
                            f"depends on {SmokeStage.PROTOCOL.value}",
                        ),
                        SmokeStageResult(
                            SmokeStage.SERVICE,
                            SmokeOutcome.NOT_RUN,
                            f"depends on {SmokeStage.PROTOCOL.value}",
                        ),
                    )
                )
            else:
                assert isinstance(arguments, JsonObject)
                resolved = SmokeDeclaration(
                    declaration.tool,
                    arguments,
                    declaration.timeout_seconds,
                    declaration.expect,
                    declaration.reaches_service,
                )
                expectation_configured = resolved.expect is not None
                service_configured = resolved.reaches_service
                run = execute_stdio_smoke(receipt.launcher, resolved, cwd=receipt.root)
                if isinstance(run, Err):
                    stages.extend(
                        (
                            SmokeStageResult(
                                SmokeStage.PROTOCOL,
                                SmokeOutcome.FAIL,
                                run.diagnostics[0].message,
                            ),
                            SmokeStageResult(
                                SmokeStage.EXPECTATION,
                                SmokeOutcome.NOT_RUN,
                                f"depends on {SmokeStage.PROTOCOL.value}",
                            ),
                            SmokeStageResult(
                                SmokeStage.SERVICE,
                                SmokeOutcome.NOT_RUN,
                                f"depends on {SmokeStage.PROTOCOL.value}",
                            ),
                        )
                    )
                else:
                    evaluated = evaluate_tool_call(resolved, run.value.tools, run.value.result)
                    stages.extend((evaluated.protocol, evaluated.expectation, evaluated.service))
                    harness_context = (resolved, run.value.tools)
                    direct_result = run.value.result
    model, harness, assessment, harness_version, coverage = _harness_stages(
        receipt, harness_context
    )
    stages.extend((model, harness, assessment))
    required = [
        stage
        for stage in stages
        if not (
            (stage.stage is SmokeStage.EXPECTATION and not expectation_configured)
            # An undeclared service read is outside the required set for the same reason an
            # absent expectation is (§170.5): nothing was requested, so nothing is owed.
            or (stage.stage is SmokeStage.SERVICE and not service_configured)
            or (
                coverage == "direct"
                and stage.stage
                in {SmokeStage.MODEL_PROVIDER, SmokeStage.HARNESS, SmokeStage.MODEL_ASSESSMENT}
            )
        )
    ]
    target: dict[str, object] = {
        "installation": installation_key(record.coordinate, owner),
        "coordinate": str(record.coordinate),
        "owner": str(owner),
        "content_digest": None if receipt.object_digest is None else str(receipt.object_digest),
        "harness": owner.harness,
        "harness_version": harness_version,
        "coverage": coverage,
        "ok": aggregate_success(required),
        "stages": [_stage_data(stage) for stage in stages],
    }
    if show_response and direct_result is not None:
        target["response"] = _response_preview(direct_result, sensitive=tuple(config.values()))
    return target


def run(request: Request) -> int:
    if request.mcp_action != "test":
        return _failure(request, "unsupported MCP command action")
    harnesses = frozenset(request.profiles)
    unknown = sorted(harnesses - _HARNESSES)
    if unknown:
        return _failure(request, f"unsupported MCP smoke harness {unknown[0]!r}")
    runtime = load_runtime_configuration(request, content_required=False)
    if isinstance(runtime, Err):
        return _failure(request, runtime.diagnostics[0].message)
    project_root, user_home = resolved_paths(
        data_root=runtime.value.paths.data_root,
        project=request.project,
        user_home=request.user_home,
    )
    root = project_root if request.scope == "project" else user_home
    records = LocalReceiptStore(
        os.path.join(runtime.value.paths.data_root, "state")
    ).installations()
    if isinstance(records, Err):
        return _failure(request, records.diagnostics[0].message)
    selection = select_installed_mcps(
        records.value,
        scope=Scope(request.scope),
        root=root,
        harnesses=harnesses,
        selectors=request.names,
        all_installed=request.all_installed,
    )
    if selection.failure is not None:
        return _failure(request, selection.failure)
    targets = tuple(
        _target(
            record,
            runtime.value.paths.data_root,
            show_response=request.show_response,
        )
        for record in selection.targets
    )
    ok = bool(targets) and all(bool(target["ok"]) for target in targets)
    payload = {
        "schema_version": 1,
        "ok": ok,
        "operation": _OPERATION,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "scope": request.scope,
        "targets": targets,
    }
    if request.json:
        print(json.dumps(payload, indent=2))
    else:
        for target in targets:
            print(f"{target['installation']}")
            stage_rows = target["stages"]
            assert isinstance(stage_rows, list)
            for stage in stage_rows:
                assert isinstance(stage, dict)
                print(f"  {stage['outcome']:<14} {stage['stage']}: {stage['reason']}")
            response = target.get("response")
            if isinstance(response, dict):
                suffix = " (truncated)" if response.get("truncated") else ""
                print(f"  response{suffix}: {response.get('content', '')}")
    return _common.OK if ok else _common.ERROR


__all__ = ["run"]
