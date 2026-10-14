"""Run the two-stage smoke over installed MCP owners (§170.2, D-378).

This is the effect boundary both surfaces share: `aart-cli mcp test` and the optional test the TUI
offers after an installation (§170.4) run exactly this, so the two cannot disagree about what a
stage means. It reads the receipt, launcher, configuration file and credential presence, starts
the installed launcher once, and returns typed results. It never writes anything.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from aart_cli.application.mcp_smoke import (
    McpCallResult,
    SmokeDeclaration,
    SmokeOutcome,
    SmokeStage,
    SmokeStageResult,
    aggregate_success,
    declaration_from_intent,
    evaluate_tool_call,
    select_installed_mcps,
)
from aart_cli.domain.configuration_files import parse_configuration_file
from aart_cli.domain.credentials import CredentialState, ProviderState
from aart_cli.domain.harness import Scope
from aart_cli.domain.installation_owner import installation_key
from aart_cli.domain.receipts import InstallationReceipt, InstalledRecord
from aart_cli.domain.result import Err
from aart_cli.io.credentials import MacOsKeychainProvider
from aart_cli.io.mcp_smoke import execute_stdio_smoke
from aart_cli.io.object_store import read_object
from aart_cli.io.receipt_store import LocalReceiptStore
from aart_cli.protocol.authoring import AUTHORING_EXTENSION
from aart_cli.protocol.json import JsonArray, JsonObject, JsonValue
from aart_cli.protocol.native_schema import parse_artifact_manifest
from aart_cli.protocol.native_tree import SnapshotEntryKind
from aart_cli.store.model import ObjectReadRequest, object_store_paths

_MAX_RESPONSE_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class SmokeTargetResult:
    """One installation's two stages, and the bounded response when it was asked for."""

    installation: str
    coordinate: str
    owner: str
    content_digest: str | None
    harness: str
    stages: tuple[SmokeStageResult, ...]
    response: dict[str, object] | None = None

    @property
    def ok(self) -> bool:
        return aggregate_success(self.stages)


@dataclass(frozen=True, slots=True)
class SmokePlanEntry:
    """What a test of one installation would call, stated before anything runs (§170.4).

    `tool` is empty where the installed content declares no smoke operation; such an installation
    is `NOT CONFIGURED` rather than a problem with the install.
    """

    installation: str
    tool: str
    arguments: str


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


def _depends_on_installation() -> SmokeStageResult:
    return SmokeStageResult(
        SmokeStage.PROTOCOL,
        SmokeOutcome.NOT_RUN,
        f"depends on {SmokeStage.INSTALLATION.value}",
    )


def smoke_installation(
    record: InstalledRecord, data_root: str, *, show_response: bool = False
) -> SmokeTargetResult:
    """Both stages for one installed MCP owner. The second runs only after the first passes."""

    receipt = record.receipt
    assert isinstance(receipt, InstallationReceipt) and receipt.owner is not None
    owner = receipt.owner
    response: dict[str, object] | None = None
    config, config_failure = _configuration_values(receipt)
    if config_failure is not None:
        stages = (
            SmokeStageResult(SmokeStage.INSTALLATION, SmokeOutcome.BLOCKED, config_failure),
            _depends_on_installation(),
        )
    else:
        installation = SmokeStageResult(
            SmokeStage.INSTALLATION,
            SmokeOutcome.PASS,
            "receipt, launcher, configuration and credential references are usable",
        )
        protocol = _protocol(record, data_root, receipt, config)
        if isinstance(protocol, tuple):
            protocol, result = protocol
            if show_response and result is not None:
                response = _response_preview(result, sensitive=tuple(config.values()))
        stages = (installation, protocol)
    return SmokeTargetResult(
        installation_key(record.coordinate, owner),
        str(record.coordinate),
        str(owner),
        None if receipt.object_digest is None else str(receipt.object_digest),
        owner.harness,
        stages,
        response,
    )


def _protocol(
    record: InstalledRecord,
    data_root: str,
    receipt: InstallationReceipt,
    config: dict[str, str],
) -> SmokeStageResult | tuple[SmokeStageResult, McpCallResult | None]:
    assert receipt.owner is not None
    declaration, failure = _declaration(record, data_root)
    if declaration is None:
        return SmokeStageResult(
            SmokeStage.PROTOCOL,
            SmokeOutcome.NOT_CONFIGURED,
            failure or "smoke operation is not configured",
        )
    try:
        arguments = _resolve_arguments(declaration.arguments, config)
    except KeyError:
        return SmokeStageResult(
            SmokeStage.PROTOCOL,
            SmokeOutcome.NOT_CONFIGURED,
            "a declared installation configuration argument is unavailable",
        )
    assert isinstance(arguments, JsonObject)
    resolved = SmokeDeclaration(declaration.tool, arguments, declaration.timeout_seconds)
    run = execute_stdio_smoke(
        receipt.launcher, resolved, cwd=receipt.root, harness=receipt.owner.harness
    )
    if isinstance(run, Err):
        return SmokeStageResult(SmokeStage.PROTOCOL, SmokeOutcome.FAIL, run.diagnostics[0].message)
    return evaluate_tool_call(resolved, run.value.tools, run.value.result), run.value.result


def smoke_plan(records: tuple[InstalledRecord, ...], data_root: str) -> tuple[SmokePlanEntry, ...]:
    """What testing these installations would call, read from their installed content only.

    Arguments are shown as declared: a reference to a configuration input stays a reference, so
    the offer names what will be sent without reading an installation's values to say so.
    """

    entries = []
    for record in records:
        receipt = record.receipt
        assert isinstance(receipt, InstallationReceipt) and receipt.owner is not None
        declaration, _ = _declaration(record, data_root)
        entries.append(
            SmokePlanEntry(
                installation_key(record.coordinate, receipt.owner),
                "" if declaration is None else declaration.tool,
                ""
                if declaration is None
                else json.dumps(_plain(declaration.arguments), sort_keys=True),
            )
        )
    return tuple(entries)


@dataclass(frozen=True, slots=True)
class LocalMcpTest:
    """The post-installation test (§170.4) over this machine's own state, for the TUI to call."""

    data_root: str

    def installations(
        self,
        *,
        scope: Scope,
        root: str,
        harnesses: frozenset[str],
        coordinates: frozenset[str],
    ) -> tuple[InstalledRecord, ...]:
        """The recorded MCP installations of these coordinates in this target, and no others."""

        if not harnesses or not coordinates:
            return ()
        records = LocalReceiptStore(os.path.join(self.data_root, "state")).installations()
        if isinstance(records, Err):
            return ()
        selection = select_installed_mcps(
            records.value,
            scope=scope,
            root=root,
            harnesses=harnesses,
            selectors=(),
            all_installed=True,
        )
        return tuple(item for item in selection.targets if str(item.coordinate) in coordinates)

    def plan(self, records: tuple[InstalledRecord, ...]) -> tuple[SmokePlanEntry, ...]:
        return smoke_plan(records, self.data_root)

    def run(self, records: tuple[InstalledRecord, ...]) -> tuple[SmokeTargetResult, ...]:
        return tuple(smoke_installation(record, self.data_root) for record in records)


__all__ = [
    "LocalMcpTest",
    "SmokePlanEntry",
    "SmokeTargetResult",
    "smoke_installation",
    "smoke_plan",
]
