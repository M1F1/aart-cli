"""Compose the safe, aggregate input form that precedes an installation offer.

Planning requires every required runtime input to have a value source.  The TUI therefore needs a
state before planning: declarations are known, persisted config and provider references may be
known, but unanswered fields are still visible.  This module owns that state without introducing a
secret-value channel.  Secret fields can become configured only through ``SecretProviderReference``.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_artifacts.domain.credentials import CredentialObservation
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import ArtifactCoordinate, InputId
from agent_artifacts.domain.inputs import (
    BoundInputs,
    InputValueSource,
    RuntimeInput,
)
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import artifact_coordinate_sort_key

from .consumer_views import InputView, project_required_inputs
from .input_binding import bind_runtime_inputs

__all__ = [
    "INPUT_COMPOSITION_INVALID",
    "INPUT_DECLARATION_CONFLICT",
    "InstallationInputComposition",
    "InstallationInputField",
    "InstallationInputUse",
    "compose_installation_inputs",
]

INPUT_COMPOSITION_INVALID = DiagnosticCode("installation-input-composition-invalid")
INPUT_DECLARATION_CONFLICT = DiagnosticCode("installation-input-declaration-conflict")


def _error(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message),))


@dataclass(frozen=True, slots=True)
class InstallationInputUse:
    """One artifact's use of a declared runtime input."""

    owner: ArtifactCoordinate
    input: RuntimeInput

    def __post_init__(self) -> None:
        if not isinstance(self.owner, ArtifactCoordinate) or not isinstance(
            self.input, RuntimeInput
        ):
            raise ValueError("an installation input use is invalid")


@dataclass(frozen=True, slots=True)
class InstallationInputField:
    """One semantic form field and every artifact whose launch contract depends on it."""

    input: RuntimeInput
    dependants: tuple[ArtifactCoordinate, ...]

    def __post_init__(self) -> None:
        ordered = tuple(sorted(set(self.dependants), key=artifact_coordinate_sort_key))
        if not isinstance(self.input, RuntimeInput) or not ordered:
            raise ValueError("an installation input field is invalid")
        object.__setattr__(self, "dependants", ordered)


@dataclass(frozen=True, slots=True)
class InstallationInputComposition:
    """The current screen-07 form state; safe to keep in application/TUI state."""

    uses: tuple[InstallationInputUse, ...]
    fields: tuple[InstallationInputField, ...]
    bound: BoundInputs

    def __post_init__(self) -> None:
        if (
            any(not isinstance(item, InstallationInputUse) for item in self.uses)
            or any(not isinstance(item, InstallationInputField) for item in self.fields)
            or not isinstance(self.bound, BoundInputs)
        ):
            raise ValueError("an installation input composition is invalid")
        field_ids = tuple(item.input.id for item in self.fields)
        if len(set(field_ids)) != len(field_ids):
            raise ValueError("an installation input composition has duplicate fields")
        if not {item.input.id for item in self.bound.inputs} <= set(field_ids):
            raise ValueError("bound installation inputs must name composed fields")

    @property
    def sources(self) -> tuple[InputValueSource, ...]:
        return tuple(item.source for item in self.bound.inputs)

    @property
    def unanswered(self) -> tuple[InstallationInputField, ...]:
        answered = {item.input.id for item in self.bound.inputs}
        return tuple(
            item for item in self.fields if item.input.required and item.input.id not in answered
        )

    @property
    def ready(self) -> bool:
        return not self.unanswered

    def sources_for(self, owner: ArtifactCoordinate) -> tuple[InputValueSource, ...]:
        """Return only the sources declared by one placement, in canonical input order."""

        identifiers = {field.input.id for field in self.fields if owner in field.dependants}
        return tuple(source for source in self.sources if source.input in identifiers)

    def views(
        self,
        credential_observations: tuple[CredentialObservation, ...] = (),
    ) -> tuple[InputView, ...]:
        return project_required_inputs(
            tuple(item.input for item in self.fields),
            bound_inputs=self.bound,
            credential_observations=credential_observations,
        )


def _ordered_uses(
    uses: tuple[InstallationInputUse, ...],
) -> tuple[InstallationInputUse, ...]:
    return tuple(
        sorted(
            set(uses),
            key=lambda item: (item.input.id.value, *artifact_coordinate_sort_key(item.owner)),
        )
    )


def compose_installation_inputs(
    uses: tuple[InstallationInputUse, ...],
    sources: tuple[InputValueSource, ...],
    policy: EffectivePolicy,
) -> Result[InstallationInputComposition]:
    """Aggregate declarations and validate the currently supplied safe value sources.

    A declared default remains on ``ConfigInput`` for screen prefill.  It becomes a source only
    after a caller submits it as ``PromptedConfigValue``; merely drawing a default is not consent to
    install with it.
    """

    if any(not isinstance(item, InstallationInputUse) for item in uses) or not isinstance(
        policy, EffectivePolicy
    ):
        return _error(
            INPUT_COMPOSITION_INVALID,
            "installation input composition needs declared uses and effective policy",
        )
    ordered = _ordered_uses(uses)
    declarations: dict[InputId, RuntimeInput] = {}
    dependants: dict[InputId, list[ArtifactCoordinate]] = {}
    for use in ordered:
        existing = declarations.get(use.input.id)
        if existing is not None and existing != use.input:
            owners = tuple(
                sorted(
                    {*dependants[use.input.id], use.owner},
                    key=artifact_coordinate_sort_key,
                )
            )
            return _error(
                INPUT_DECLARATION_CONFLICT,
                f"input {use.input.id} has conflicting declarations for "
                + ", ".join(str(item) for item in owners),
            )
        declarations[use.input.id] = use.input
        dependants.setdefault(use.input.id, []).append(use.owner)

    source_ids = {item.input for item in sources}
    selected_declarations = tuple(
        declarations[identifier]
        for identifier in sorted(source_ids & set(declarations), key=lambda item: item.value)
    )
    bound = bind_runtime_inputs(selected_declarations, sources, policy)
    if isinstance(bound, Err):
        return bound
    try:
        fields = tuple(
            InstallationInputField(declarations[identifier], tuple(dependants[identifier]))
            for identifier in sorted(declarations, key=lambda item: item.value)
        )
        return Ok(InstallationInputComposition(ordered, fields, bound.value))
    except ValueError as error:
        return _error(INPUT_COMPOSITION_INVALID, f"installation inputs are invalid: {error}")
