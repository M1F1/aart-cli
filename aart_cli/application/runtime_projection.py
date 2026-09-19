"""Pure generation of the runtime projection: the launcher an installed artifact is started by.

The projection is derived, never authored. It comes from the artifact's own environment, its launch
contract and its bound inputs, and it exists so that nothing else has to be present at run time --
not AART, not a package installer, not a network. A harness records one path and executes it.

Three rules decide the shape of the file. A secret is never written: the script holds the command
that asks the provider for it, and the value exists only inside the launched process. A
configuration value is not written either: it lives in the configuration file of the harness that
started the launcher, beside the artifact (D-264), and is read line by line with `read -r`, so it is
text in a variable and never a word the shell interprets. Everything the script does hold -- paths,
argument names -- is quoted, once, by the domain's quoter, and never concatenated by hand.

Configuration is per harness, and the launcher is shared, so a launcher that reads configuration is
started with one argument: the harness that started it. Each harness registration passes its own
name. A launcher for an artifact with no configuration takes no argument and reads no file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from aart_cli.domain.configuration_files import (
    CONFIGURATION_DIRECTORY,
    CONFIGURATION_FILE_INVALID,
    CONFIGURATION_SUFFIX,
    ConfigurationFileRecord,
    configuration_file_path,
    render_configuration_file,
)
from aart_cli.domain.credentials import CredentialReference
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.identifiers import InputId, ObjectDigest
from aart_cli.domain.inputs import (
    BoundInput,
    BoundInputs,
    CliArgumentBinding,
    EnvironmentBinding,
    FileBinding,
    SecretProviderReference,
    StdinBinding,
)
from aart_cli.domain.launch import LaunchContract, launcher_path, shell_quote
from aart_cli.domain.python_runtime import ArtifactEnvironment
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.protocol.hashing import sha256_bytes

LAUNCHER_BINDING_UNSUPPORTED = DiagnosticCode("launcher-binding-unsupported")
LAUNCHER_INVALID = DiagnosticCode("launcher-invalid")
LAUNCHER_PROVIDER_UNRESOLVABLE = DiagnosticCode("launcher-provider-unresolvable")
LAUNCHER_TRANSPORT_CONFLICT = DiagnosticCode("launcher-transport-conflict")
#: The provider's resolution command does not name the service anywhere, so this launcher cannot
#: parameterise it by harness. Refused: one fixed address for every harness is the defect (D-354).
LAUNCHER_PROVIDER_UNPARAMETERISED = DiagnosticCode("launcher-provider-unparameterised")

# Distinct enough to tell apart in a harness log: the environment is missing versus the provider
# would not answer. Both are ordinary repair cases, and neither is the artifact failing.
MISSING_ENVIRONMENT_STATUS = 78
UNRESOLVED_CREDENTIAL_STATUS = 77
MISSING_CONFIGURATION_STATUS = 76

_SECRET_VARIABLE_PREFIX = "AART_CLI_SECRET_"
_CONFIG_VARIABLE_PREFIX = "AART_CLI_CONFIG_"

#: The token a caller leaves in a credential service template where the harness goes. It is split
#: on, never evaluated: each side is quoted as a literal and only the validated harness variable is
#: expanded between them, so nothing in the address can be read by the shell.
HARNESS_PLACEHOLDER = "AART-CLI-HARNESS-SLOT"

#: The variable the launcher validates as a canonical slug before it composes anything from it.
_HARNESS_VARIABLE = "AART_CLI_HARNESS"
_SERVICE_VARIABLE = "AART_CLI_SERVICE"


class CredentialResolutionPort(Protocol):
    """A provider that can say how a reference is read, without reading it here."""

    provider: str

    def resolution_argv(self, reference: CredentialReference) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class RuntimeProjection:
    """One generated file and the command a harness records to start the artifact."""

    path: str
    content: str
    digest: ObjectDigest
    executable: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path.startswith("/"):
            raise ValueError("a runtime projection is written to an absolute path")
        if not isinstance(self.content, str) or not self.content:
            raise ValueError("a runtime projection has content")

    @property
    def command(self) -> str:
        return self.path


@dataclass(frozen=True, slots=True)
class ConfigurationProjection:
    """One harness's configuration file for one installed artifact, with the digest it must have."""

    harness: str
    path: str
    content: str
    digest: ObjectDigest

    def __post_init__(self) -> None:
        # The record's own checks: a harness slug, and the path of that harness's file.
        ConfigurationFileRecord(self.harness, self.path, self.digest)
        if not isinstance(self.content, str) or not self.content:
            raise ValueError("a configuration projection has content")

    @property
    def record(self) -> ConfigurationFileRecord:
        return ConfigurationFileRecord(self.harness, self.path, self.digest)


def configuration_projection(
    environment: ArtifactEnvironment, harness: str, values: tuple[tuple[InputId, str], ...]
) -> Result[ConfigurationProjection]:
    """The file `harness` reads `values` from. Pure; a value unfit for the file is refused here."""

    try:
        content = render_configuration_file(environment.artifact, harness, values)
        return Ok(
            ConfigurationProjection(
                harness,
                configuration_file_path(environment.root, harness),
                content,
                sha256_bytes(content.encode("utf-8")),
            )
        )
    except ValueError as error:
        return _error(CONFIGURATION_FILE_INVALID, f"{environment.artifact}: {error}")


def _error(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message),))


def _secret_variable(bound: BoundInput) -> str:
    return _SECRET_VARIABLE_PREFIX + bound.input.id.value.upper().replace("-", "_")


def _config_variable(bound: BoundInput) -> str:
    return _CONFIG_VARIABLE_PREFIX + bound.input.id.value.upper().replace("-", "_")


def _harness_preamble(environment: ArtifactEnvironment) -> list[str]:
    """Take the harness this launcher was started with, and refuse anything that is not one.

    Everything composed from it afterwards -- the configuration file it reads and the credential
    item it asks the provider for -- is composed from a value already held to a canonical slug, so
    neither a path nor a shell expression can reach either.
    """

    artifact = shell_quote(environment.artifact)
    return [
        f'{_HARNESS_VARIABLE}="${{1-}}"',
        f'case "${_HARNESS_VARIABLE}" in',
        "  ''|*[!a-z0-9-]*)",
        "    printf 'aart: %s was started without the harness it belongs to; "
        f"repair the installation\\n' {artifact} >&2",
        f"    exit {MISSING_CONFIGURATION_STATUS}",
        "    ;;",
        "esac",
    ]


def _service_composition(template: str) -> list[str]:
    """Compose this harness's credential service from the address with its harness slot open.

    The template is split on the placeholder and each side is emitted single-quoted, so no part of
    the address is ever read by the shell. Only the harness variable is expanded, and the preamble
    has already held it to a slug.
    """

    prefix, _, suffix = template.partition(HARNESS_PLACEHOLDER)  # exactly one slot; see the guard
    return [f'{_SERVICE_VARIABLE}={shell_quote(prefix)}"${_HARNESS_VARIABLE}"{shell_quote(suffix)}']


def _with_service_variable(part: str, service: str) -> str:
    """One argv word with every mention of the service replaced by the composed variable.

    A provider may name the service as its own argument (`-s <service>`) or fold it into a single
    reference string; both are one word once quoted, so the substitution happens inside the word
    rather than over the list. Each surrounding fragment stays single-quoted and the fragments are
    written adjacent, so only the variable is expanded and the result is still one word.
    """

    pieces = part.split(service)
    quoted = [shell_quote(piece) for piece in pieces]
    if len(quoted) > 1:
        # An empty fragment at either end would quote to '', which is a word this does not need.
        if not pieces[0]:
            quoted[0] = ""
        if not pieces[-1]:
            quoted[-1] = ""
    return f'"${_SERVICE_VARIABLE}"'.join(quoted)


def _configuration_reader(environment: ArtifactEnvironment, items: list[BoundInput]) -> list[str]:
    """Read each configured value from the starting harness's file, or stop saying which is missing.

    Nothing read is evaluated: `IFS= read -r` keeps the line exactly, a `case` pattern matches the
    literal input id, and the value is taken with a prefix removal into a variable that is only ever
    expanded inside double quotes.
    """

    artifact = shell_quote(environment.artifact)
    directory = shell_quote(f"{environment.root}/{CONFIGURATION_DIRECTORY}/")
    status = MISSING_CONFIGURATION_STATUS
    lines = [
        f'AART_CLI_CONFIGURATION={directory}"${_HARNESS_VARIABLE}"'
        f"{shell_quote(CONFIGURATION_SUFFIX)}",
        'if [ ! -r "$AART_CLI_CONFIGURATION" ]; then',
        "  printf 'aart: %s has no configuration for %s; set it in AART under User variables "
        f'and credentials\\n\' {artifact} "${_HARNESS_VARIABLE}" >&2',
        f"  exit {status}",
        "fi",
    ]
    for item in items:
        variable = _config_variable(item)
        lines.append(f"{variable}=")
    lines.append('while IFS= read -r aart_line || [ -n "$aart_line" ]; do')
    lines.append('  case "$aart_line" in')
    for item in items:
        identifier = item.input.id.value
        variable = _config_variable(item)
        lines.extend(
            [
                f"    {shell_quote(identifier + '=')}*)",
                f'      if [ -n "${variable}" ]; then',
                f"        printf 'aart: %s sets %s twice in %s\\n' {artifact} "
                f'{shell_quote(identifier)} "$AART_CLI_CONFIGURATION" >&2',
                f"        exit {status}",
                "      fi",
                f'      {variable}="${{aart_line#{identifier}=}}"',
                "      ;;",
            ]
        )
    lines.extend(["  esac", 'done < "$AART_CLI_CONFIGURATION"'])
    for item in items:
        variable = _config_variable(item)
        lines.extend(
            [
                f'if [ -z "${variable}" ]; then',
                f"  printf 'aart: %s has no value for %s in %s\\n' {artifact} "
                f'{shell_quote(item.input.id.value)} "$AART_CLI_CONFIGURATION" >&2',
                f"  exit {status}",
                "fi",
            ]
        )
    return lines


def _resolution_argv(
    source: SecretProviderReference,
    resolvers: tuple[CredentialResolutionPort, ...],
) -> tuple[str, ...] | None:
    for resolver in resolvers:
        if resolver.provider == source.provider.provider:
            return tuple(resolver.resolution_argv(source.reference))
    return None


def generate_launcher(
    environment: ArtifactEnvironment,
    contract: LaunchContract,
    bound: BoundInputs,
    *,
    resolvers: tuple[CredentialResolutionPort, ...] = (),
    credential_service_template: str | None = None,
) -> Result[RuntimeProjection]:
    """Derive the launcher for one installed artifact. Pure: nothing here touches a filesystem.

    Given `credential_service_template` -- the installation's credential address with its harness
    left as `HARNESS_PLACEHOLDER` -- the launcher composes the item to read from the harness it is
    started with, so one generated launcher serves every target of one installation without any of
    them reaching another's secret.
    """

    if (
        not isinstance(environment, ArtifactEnvironment)
        or not isinstance(contract, LaunchContract)
        or not isinstance(bound, BoundInputs)
    ):
        return _error(LAUNCHER_INVALID, "launcher generation needs an environment and a contract")
    if credential_service_template is not None and (
        not isinstance(credential_service_template, str)
        or credential_service_template.count(HARNESS_PLACEHOLDER) != 1
    ):
        return _error(
            LAUNCHER_INVALID,
            "a credential service template must leave exactly one harness slot open as "
            f"{HARNESS_PLACEHOLDER}; anything else has no single address to compose",
        )

    declared = {
        item.binding.variable
        for item in bound.inputs
        if isinstance(item.binding, EnvironmentBinding)
    }
    exports: list[str] = []
    assignments: list[str] = []
    arguments: list[str] = [shell_quote(argument) for argument in contract.arguments]
    parameterised = False
    configured = [
        item for item in bound.inputs if not isinstance(item.source, SecretProviderReference)
    ]
    for item in configured:
        if _config_variable(item) in declared:
            return _error(
                LAUNCHER_INVALID,
                f"input {item.input.id} needs the shell variable {_config_variable(item)}, which "
                "another input already binds to the environment",
            )

    for item in bound.inputs:
        binding = item.binding
        if isinstance(binding, StdinBinding):
            return _error(
                LAUNCHER_TRANSPORT_CONFLICT,
                f"input {item.input.id} binds to stdin, which the "
                f"{contract.transport.value} transport already uses",
            )
        if isinstance(binding, FileBinding):
            return _error(
                LAUNCHER_BINDING_UNSUPPORTED,
                f"input {item.input.id} binds to a file, which a generated launcher does not "
                "write; bind it to the environment or an argument instead",
            )

        if isinstance(item.source, SecretProviderReference):
            argv = _resolution_argv(item.source, resolvers)
            if argv is None:
                return _error(
                    LAUNCHER_PROVIDER_UNRESOLVABLE,
                    f"no interpreter can resolve {item.source.provider.provider} at launch, so "
                    f"input {item.input.id} would have no value",
                )
            if not isinstance(binding, (EnvironmentBinding, CliArgumentBinding)):
                return _error(
                    LAUNCHER_BINDING_UNSUPPORTED,
                    f"input {item.input.id} uses a binding this launcher cannot render",
                )
            variable = (
                binding.variable
                if isinstance(binding, EnvironmentBinding)
                else _secret_variable(item)
            )
            if not isinstance(binding, EnvironmentBinding) and variable in declared:
                return _error(
                    LAUNCHER_INVALID,
                    f"input {item.input.id} needs the shell variable {variable}, which another "
                    "input already binds to the environment",
                )
            unreadable = f"aart: could not read {item.source.reference} from its provider"
            said = f"'%s\\n' {shell_quote(unreadable)}"
            if credential_service_template is None:
                command = " ".join(shell_quote(part) for part in argv)
            else:
                service = item.source.reference.provider.service
                if not any(service in part for part in argv):
                    return _error(
                        LAUNCHER_PROVIDER_UNPARAMETERISED,
                        f"resolving {item.input.id} from "
                        f"{item.source.provider.provider} does not name the credential service, so "
                        "this launcher could only read one harness's item for every harness",
                    )
                command = " ".join(_with_service_variable(part, service) for part in argv)
                # The composed item, passed as an argument rather than substituted into the
                # sentence: what the launcher says it could not read is then the item it actually
                # asked for, and no prose is searched for something that looks like an address.
                sentence = f"aart: could not read %s from {item.source.provider.provider}" + "\\n"
                said = f'{shell_quote(sentence)} "${_SERVICE_VARIABLE}"'
                parameterised = True
            assignments.append(
                f'if ! {variable}="$({command})"; then\n'
                f"  printf {said} >&2\n"
                f"  exit {UNRESOLVED_CREDENTIAL_STATUS}\n"
                "fi"
            )
            if isinstance(binding, EnvironmentBinding):
                exports.append(f"export {variable}")
            else:
                arguments.extend([shell_quote(binding.argument), f'"${variable}"'])
            continue

        value = f'"${_config_variable(item)}"'
        if isinstance(binding, EnvironmentBinding):
            assignments.append(f"{binding.variable}={value}")
            exports.append(f"export {binding.variable}")
        elif isinstance(binding, CliArgumentBinding):
            arguments.extend([shell_quote(binding.argument), value])
        else:
            return _error(
                LAUNCHER_BINDING_UNSUPPORTED,
                f"input {item.input.id} uses a binding this launcher cannot render",
            )

    preamble = _harness_preamble(environment) if configured or parameterised else []
    if parameterised and credential_service_template is not None:
        preamble += _service_composition(credential_service_template)
    reader = _configuration_reader(environment, configured) if configured else []
    content = _render(environment, contract, preamble + reader + assignments, exports, arguments)
    try:
        return Ok(
            RuntimeProjection(
                launcher_path(environment), content, sha256_bytes(content.encode("utf-8"))
            )
        )
    except ValueError as error:
        return _error(LAUNCHER_INVALID, f"generated launcher is invalid: {error}")


def _render(
    environment: ArtifactEnvironment,
    contract: LaunchContract,
    assignments: list[str],
    exports: list[str],
    arguments: list[str],
) -> str:
    interpreter = shell_quote(environment.interpreter)
    entrypoint = shell_quote(environment.payload_path(contract.entrypoint))
    missing = shell_quote(
        f"aart: {environment.artifact} has no runtime environment; repair the installation"
    )
    lines = [
        "#!/bin/sh",
        f"# Generated by AART for {environment.artifact}. Do not edit: repairing or updating this",
        "# artifact rewrites this file. It is a projection of the installation, not its source.",
        "# It holds no secret and no configuration value: secrets are read from their provider and",
        "# configuration from the starting harness's file under config/ when this script runs.",
        "set -eu",
        "",
        f"AART_CLI_INTERPRETER={interpreter}",
        f"AART_CLI_ENTRYPOINT={entrypoint}",
        "",
        'if [ ! -x "$AART_CLI_INTERPRETER" ]; then',
        f"  printf '%s\\n' {missing} >&2",
        f"  exit {MISSING_ENVIRONMENT_STATUS}",
        "fi",
    ]
    if assignments:
        lines.extend(["", *assignments])
    if exports:
        lines.extend(["", *exports])
    invocation = ['exec "$AART_CLI_INTERPRETER" "$AART_CLI_ENTRYPOINT"', *arguments]
    lines.extend(["", " ".join(invocation), ""])
    return "\n".join(lines)
