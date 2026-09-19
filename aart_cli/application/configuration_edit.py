"""Pure planning for changing ordinary per-harness configuration files.

The caller supplies the bytes it read.  This module validates the reviewed baseline, replaces one
declared input in exactly the chosen files, and returns the receipt/component projection needed by
the shared lifecycle planner.  It performs no filesystem I/O and never returns a diagnostic that
echoes the proposed value.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from aart_cli.domain.configuration_files import (
    ConfigurationFileRecord,
    configuration_value_problem,
    parse_configuration_file,
    render_configuration_file,
)
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.effects import WriteFile
from aart_cli.domain.identifiers import InputId
from aart_cli.domain.inputs import InputValidation, validate_config_value
from aart_cli.domain.receipts import InstallationReceipt
from aart_cli.domain.reconciliation import Component, ComponentId, DesiredComponent
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.protocol.hashing import sha256_bytes

__all__ = [
    "CONFIGURATION_EDIT_INVALID",
    "ConfigurationEdit",
    "EditedConfigurationFile",
    "plan_configuration_edit",
]

CONFIGURATION_EDIT_INVALID = DiagnosticCode("configuration-edit-invalid")


def _error(message: str) -> Err:
    return Err((Diagnostic(CONFIGURATION_EDIT_INVALID, Severity.ERROR, message),))


@dataclass(frozen=True, slots=True)
class EditedConfigurationFile:
    """One old record and the new bytes/record that replace it."""

    previous: ConfigurationFileRecord
    updated: ConfigurationFileRecord
    content: bytes

    def __post_init__(self) -> None:
        if (
            not isinstance(self.previous, ConfigurationFileRecord)
            or not isinstance(self.updated, ConfigurationFileRecord)
            or self.previous.harness != self.updated.harness
            or self.previous.path != self.updated.path
            or not isinstance(self.content, bytes)
            or sha256_bytes(self.content) != self.updated.digest
        ):
            raise ValueError("an edited configuration file is invalid")

    @property
    def harness(self) -> str:
        return self.updated.harness


@dataclass(frozen=True, slots=True)
class ConfigurationEdit:
    """The updated receipt and CONFIGURATION-only replacements for one reviewed edit."""

    receipt: InstallationReceipt
    replacements: tuple[DesiredComponent, ...]
    files: tuple[EditedConfigurationFile, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.receipt, InstallationReceipt)
            or not self.files
            or any(not isinstance(item, EditedConfigurationFile) for item in self.files)
            or len({item.harness for item in self.files}) != len(self.files)
            or len(self.replacements) != len(self.files)
            or any(
                item.id.component is not Component.CONFIGURATION
                or len(item.effects) != 1
                or not isinstance(item.effects[0], WriteFile)
                for item in self.replacements
            )
        ):
            raise ValueError("a configuration edit is invalid")


def plan_configuration_edit(
    receipt: InstallationReceipt,
    *,
    input_id: InputId,
    harnesses: tuple[str, ...],
    value: str,
    current_files: tuple[tuple[str, bytes], ...],
    validation: InputValidation | None = None,
) -> Result[ConfigurationEdit]:
    """Replace ``input_id`` in exactly ``harnesses`` from an unchanged reviewed baseline."""

    if not isinstance(receipt, InstallationReceipt) or not isinstance(input_id, InputId):
        return _error("editing configuration needs an installed runtime artifact and input")
    if not harnesses:
        return _error("choose at least one installed harness")
    if len(set(harnesses)) != len(harnesses):
        return _error("a configuration edit names the same harness more than once")
    if any(not isinstance(item, str) or not item for item in harnesses):
        return _error("a configuration edit contains an invalid harness")
    problem = configuration_value_problem(value)
    if problem is not None:
        return _error(f"the new configuration value is invalid: {problem}")
    validation_problem = validate_config_value(validation, value)
    if validation_problem is not None:
        assert validation is not None
        # An author-provided message is reviewed metadata and cannot contain the candidate value.
        # The domain's default URL message can include the candidate host, so keep the fallback
        # structural: rejected input values never become diagnostics, Activity or durable state.
        reason = (
            validation.message
            if validation.message
            else f"it does not satisfy the declared {validation.kind} rule"
        )
        return _error(f"the new configuration value is invalid: {reason}")
    if (
        not isinstance(current_files, tuple)
        or len({item[0] for item in current_files if isinstance(item, tuple) and len(item) == 2})
        != len(current_files)
        or any(
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not isinstance(item[1], bytes)
            for item in current_files
        )
    ):
        return _error("the current configuration-file reading is invalid")

    records = {item.harness: item for item in receipt.configuration_files}
    stale = sorted(set(harnesses) - set(records))
    if stale:
        return _error(
            "the chosen harnesses are not installed for this artifact: " + ", ".join(stale)
        )
    content_by_harness = dict(current_files)
    missing_readings = sorted(set(harnesses) - set(content_by_harness))
    if missing_readings:
        return _error(
            "the chosen configuration files could not be read: " + ", ".join(missing_readings)
        )

    edited: list[EditedConfigurationFile] = []
    replacements: list[DesiredComponent] = []
    updated_records = dict(records)
    for harness in harnesses:
        previous = records[harness]
        content = content_by_harness[harness]
        if sha256_bytes(content) != previous.digest:
            return _error(
                f"{harness}'s configuration changed outside AART; inspect it before editing"
            )
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            return _error(f"{harness}'s configuration is not valid UTF-8 text")
        parsed = parse_configuration_file(text)
        if isinstance(parsed, Err):
            return _error(f"{harness}'s configuration is not in AART's supported format")
        values = dict(parsed.value)
        if input_id not in values:
            return _error(f"{harness}'s configuration does not declare {input_id}")
        values[input_id] = value
        rendered = render_configuration_file(
            receipt.artifact,
            harness,
            tuple(values.items()),
        ).encode("utf-8")
        digest = sha256_bytes(rendered)
        if digest == previous.digest:
            return _error(f"{harness} already has that configuration value")
        updated = ConfigurationFileRecord(harness, previous.path, digest)
        file = EditedConfigurationFile(previous, updated, rendered)
        edited.append(file)
        updated_records[harness] = updated
        replacements.append(
            DesiredComponent(
                ComponentId(Component.CONFIGURATION, harness),
                (WriteFile(updated.path, str(updated.digest), False),),
            )
        )

    try:
        return Ok(
            ConfigurationEdit(
                replace(receipt, configuration_files=tuple(updated_records.values())),
                tuple(replacements),
                tuple(edited),
            )
        )
    except ValueError as error:
        return _error(f"the configuration edit cannot be planned: {error}")
