"""Which adapters carry out one confirmed Selection, and what each of them is allowed to touch.

`execute_installation` takes one tuple of interpreters for the whole transaction and runs every
member's effects through it (D-064).  Deciding what belongs in that tuple was the last piece of the
install composition that existed only hand-wired in a test, so a public command and the shell's
action handler would each have had to build it -- and two copies of that wiring disagree the first
time one of them changes.

The assembly follows the rule the interpreters already enforce: every one of them is bound to what
it may act on, never merely to a kind of effect.  One file interpreter per artifact, already holding
the launcher bytes the effect names by digest; one runtime interpreter per artifact, bound to its
environment; one harness interpreter per artifact, holding that artifact's registrations and its
name; and one credential interpreter per provider, holding the references that name it.

Nothing here reads a secret value.  A credential reaches this module as a reference, and the
interpreter built from it can verify or delete the value through the provider but never receives it.
"""

from __future__ import annotations

from agent_artifacts.application.execution import EffectInterpreter
from agent_artifacts.application.installation_proposal import (
    PlannedInstallation,
    intended_receipt,
)
from agent_artifacts.domain.credentials import CredentialReference
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.result import Err, Ok, Result

from .credentials import CredentialProviderPort
from .execution import (
    CredentialEffectInterpreter,
    FileEffectInterpreter,
    HarnessEffectInterpreter,
    RuntimeEffectInterpreter,
)
from .harness import LocalHarnessRegistry
from .python_runtime import LocalPythonRuntime

__all__ = ["INTERPRETERS_UNAVAILABLE", "interpreters_for"]

#: A confirmed installation names a credential provider no adapter here can act on.
INTERPRETERS_UNAVAILABLE = DiagnosticCode("installation-interpreters-unavailable")


def _error(message: str) -> Err:
    return Err((Diagnostic(INTERPRETERS_UNAVAILABLE, Severity.ERROR, message),))


def interpreters_for(
    installations: tuple[PlannedInstallation, ...],
    *,
    registry: LocalHarnessRegistry,
    credential_providers: tuple[CredentialProviderPort, ...] = (),
    timeout_seconds: float = 900.0,
    offline: bool = False,
) -> Result[tuple[EffectInterpreter, ...]]:
    """Build the interpreters `installations` are executed through, or say what is missing.

    A reference whose provider nobody supplied is refused here rather than left to the executor.
    It is not a case that can come out well later: an uninspectable credential is observed unknown,
    unknown diverges from the desired state, and the repair that closes it is a credential effect
    no interpreter in the tuple would carry out -- reported half-way through a transaction that has
    already written files, as an effect nobody would take rather than as an adapter nobody supplied.
    Refusing before the mutation lock is even taken names the real fault and costs nothing, because
    there is no install where the missing adapter would have gone unused.
    """

    if any(not isinstance(item, PlannedInstallation) for item in installations):
        raise ValueError("assembling interpreters needs planned installations")
    if not isinstance(registry, LocalHarnessRegistry):
        raise ValueError("assembling interpreters needs a harness registry")
    providers = {item.provider: item for item in credential_providers}
    if len(providers) != len(credential_providers):
        raise ValueError("assembling interpreters needs one adapter per credential provider")

    interpreters: list[EffectInterpreter] = []
    references: dict[str, list[CredentialReference]] = {}
    for installation in installations:
        files = FileEffectInterpreter(installation.environment)
        files.offer(installation.launcher.content.encode("utf-8"))
        interpreters.append(files)
        interpreters.append(
            RuntimeEffectInterpreter(
                LocalPythonRuntime(
                    installation.environment,
                    timeout_seconds=timeout_seconds,
                    offline=offline,
                )
            )
        )
        interpreters.append(
            HarnessEffectInterpreter(
                registry,
                installation.registrations,
                artifact=installation.environment.artifact,
            )
        )
        for reference in intended_receipt(installation).credentials:
            held = references.setdefault(reference.provider.provider, [])
            if reference not in held:
                held.append(reference)

    missing = sorted(name for name in references if name not in providers)
    if missing:
        return _error(
            "nothing here can act on credentials held by "
            + ", ".join(missing)
            + "; no adapter for that provider was supplied"
        )
    interpreters.extend(
        CredentialEffectInterpreter(providers[name], tuple(references[name]))
        for name in sorted(references)
    )
    return Ok(tuple(interpreters))
