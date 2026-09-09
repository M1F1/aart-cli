"""Pure generation of the runtime projection: the launcher an installed artifact is started by.

The projection is derived, never authored. It comes from the artifact's own environment, its launch
contract and its bound inputs, and it exists so that nothing else has to be present at run time --
not AART, not a package installer, not a network. A harness records one path and executes it.

Two rules decide the shape of the file. A secret is never written: the script holds the command
that asks the provider for it, and the value exists only inside the launched process. Everything
else is a value that has already been reviewed, so it is quoted, once, by the domain's quoter, and
never concatenated into a command line by hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agent_artifacts.domain.credentials import CredentialReference
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import ObjectDigest
from agent_artifacts.domain.inputs import (
    BoundInput,
    BoundInputs,
    CliArgumentBinding,
    EnvironmentBinding,
    FileBinding,
    SecretProviderReference,
    StdinBinding,
)
from agent_artifacts.domain.launch import LaunchContract, launcher_path, shell_quote
from agent_artifacts.domain.python_runtime import ArtifactEnvironment
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.protocol.hashing import sha256_bytes

LAUNCHER_BINDING_UNSUPPORTED = DiagnosticCode("launcher-binding-unsupported")
LAUNCHER_INVALID = DiagnosticCode("launcher-invalid")
LAUNCHER_PROVIDER_UNRESOLVABLE = DiagnosticCode("launcher-provider-unresolvable")
LAUNCHER_TRANSPORT_CONFLICT = DiagnosticCode("launcher-transport-conflict")

# Distinct enough to tell apart in a harness log: the environment is missing versus the provider
# would not answer. Both are ordinary repair cases, and neither is the artifact failing.
MISSING_ENVIRONMENT_STATUS = 78
UNRESOLVED_CREDENTIAL_STATUS = 77

_SECRET_VARIABLE_PREFIX = "AART_SECRET_"


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


def _error(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message),))


def _secret_variable(bound: BoundInput) -> str:
    return _SECRET_VARIABLE_PREFIX + bound.input.id.value.upper().replace("-", "_")


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
) -> Result[RuntimeProjection]:
    """Derive the launcher for one installed artifact. Pure: nothing here touches a filesystem."""

    if (
        not isinstance(environment, ArtifactEnvironment)
        or not isinstance(contract, LaunchContract)
        or not isinstance(bound, BoundInputs)
    ):
        return _error(LAUNCHER_INVALID, "launcher generation needs an environment and a contract")

    declared = {
        item.binding.variable
        for item in bound.inputs
        if isinstance(item.binding, EnvironmentBinding)
    }
    exports: list[str] = []
    assignments: list[str] = []
    arguments: list[str] = [shell_quote(argument) for argument in contract.arguments]

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
            command = " ".join(shell_quote(part) for part in argv)
            assignments.append(
                f'if ! {variable}="$({command})"; then\n'
                f"  printf '%s\\n' "
                f"{shell_quote(f'aart: could not read {item.source.reference} from its provider')}"
                " >&2\n"
                f"  exit {UNRESOLVED_CREDENTIAL_STATUS}\n"
                "fi"
            )
            if isinstance(binding, EnvironmentBinding):
                exports.append(f"export {variable}")
            else:
                arguments.extend([shell_quote(binding.argument), f'"${variable}"'])
            continue

        value = shell_quote(item.source.value)
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

    content = _render(environment, contract, assignments, exports, arguments)
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
        "# It holds no secret value; each one is read from its provider when this script runs.",
        "set -eu",
        "",
        f"AART_INTERPRETER={interpreter}",
        f"AART_ENTRYPOINT={entrypoint}",
        "",
        'if [ ! -x "$AART_INTERPRETER" ]; then',
        f"  printf '%s\\n' {missing} >&2",
        f"  exit {MISSING_ENVIRONMENT_STATUS}",
        "fi",
    ]
    if assignments:
        lines.extend(["", *assignments])
    if exports:
        lines.extend(["", *exports])
    invocation = ['exec "$AART_INTERPRETER" "$AART_ENTRYPOINT"', *arguments]
    lines.extend(["", " ".join(invocation), ""])
    return "\n".join(lines)
