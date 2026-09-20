"""Compose the safe, per-installation input form that precedes an installation offer.

Planning requires every required runtime input to have a value source.  The TUI therefore needs a
state before planning: declarations are known, persisted config and provider references may be
known, but unanswered fields are still visible.  This module owns that state without introducing a
secret-value channel.  Secret fields can become configured only through ``SecretProviderReference``.

The unit is the installation, not the declared input (§169.4-6, D-353).  What this replaces keyed a
field by ``InputId`` across artifacts -- "one semantic form field and every artifact whose launch
contract depends on it" -- which is the sharing D-333 removed: one artifact installed on four
harnesses asked once and wrote the same answer into all four.  A field is now one owner's own use
of one declared input, so four installations ask four times and hold four answers.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from aart_cli.domain.credentials import CredentialObservation, CredentialReference
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.identifiers import InputId
from aart_cli.domain.inputs import (
    BoundInputs,
    InputValueSource,
    RuntimeInput,
)
from aart_cli.domain.installation_owner import InstallationOwner
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.result import Err, Ok, Result

from .consumer_views import InputView, project_required_inputs
from .input_binding import bind_runtime_inputs

__all__ = [
    "INPUT_COMPOSITION_INVALID",
    "InstallationInputComposition",
    "InstallationInputField",
    "InstallationInputUse",
    "OwnedInputSource",
    "compose_installation_inputs",
]

INPUT_COMPOSITION_INVALID = DiagnosticCode("installation-input-composition-invalid")


def _error(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message),))


@dataclass(frozen=True, slots=True)
class InstallationInputUse:
    """One installation's use of a declared runtime input."""

    owner: InstallationOwner
    input: RuntimeInput

    def __post_init__(self) -> None:
        if not isinstance(self.owner, InstallationOwner) or not isinstance(
            self.input, RuntimeInput
        ):
            raise ValueError("an installation input use is invalid")


@dataclass(frozen=True, slots=True)
class OwnedInputSource:
    """One value source, and the installation that answered it.

    The owner travels with the source because the same declared input is asked of several
    installations and each answer is that installation's alone.  A bare source could only be
    matched back by id, which is the grouping this module exists to stop.
    """

    owner: InstallationOwner
    source: InputValueSource

    def __post_init__(self) -> None:
        if not isinstance(self.owner, InstallationOwner) or not isinstance(
            self.source, InputValueSource
        ):
            raise ValueError("an owned input source is invalid")


@dataclass(frozen=True, slots=True)
class InstallationInputField:
    """One form field: one installation's own use of one declared input.

    There is deliberately no list of dependants.  A field has exactly one owner, so "who else needs
    this" is not a question it can answer, and the answer it used to give is what made four
    installations share one value.
    """

    owner: InstallationOwner
    input: RuntimeInput

    def __post_init__(self) -> None:
        if not isinstance(self.owner, InstallationOwner) or not isinstance(
            self.input, RuntimeInput
        ):
            raise ValueError("an installation input field is invalid")

    @property
    def key(self) -> tuple[InstallationOwner, InputId]:
        return (self.owner, self.input.id)


def _field_sort_key(field: InstallationInputField) -> tuple[InstallationOwner, str]:
    return (field.owner, field.input.id.value)


@dataclass(frozen=True, slots=True)
class InstallationInputComposition:
    """The current screen-07 form state; safe to keep in application/TUI state."""

    uses: tuple[InstallationInputUse, ...]
    fields: tuple[InstallationInputField, ...]
    bound: tuple[tuple[InstallationOwner, BoundInputs], ...]

    def __post_init__(self) -> None:
        if (
            any(not isinstance(item, InstallationInputUse) for item in self.uses)
            or any(not isinstance(item, InstallationInputField) for item in self.fields)
            or any(
                not isinstance(owner, InstallationOwner) or not isinstance(value, BoundInputs)
                for owner, value in self.bound
            )
        ):
            raise ValueError("an installation input composition is invalid")
        keys = tuple(item.key for item in self.fields)
        if len(set(keys)) != len(keys):
            raise ValueError("an installation input composition has duplicate fields")
        owners = tuple(owner for owner, _ in self.bound)
        if len(set(owners)) != len(owners):
            raise ValueError("an installation input composition binds an owner twice")
        declared = set(keys)
        for owner, value in self.bound:
            if not {(owner, item.input.id) for item in value.inputs} <= declared:
                raise ValueError("bound installation inputs must name composed fields")

    @property
    def sources(self) -> tuple[OwnedInputSource, ...]:
        """Every answer with the installation that gave it, in composed field order."""

        return tuple(
            OwnedInputSource(owner, item.source)
            for owner, value in self.bound
            for item in value.inputs
        )

    @property
    def credential_references(self) -> tuple[CredentialReference, ...]:
        """Every credential any of these installations would read, each named once.

        Two installations of one artifact address two items, so this is a set over owners rather
        than over declared inputs -- which is exactly what makes inspecting them separate.
        """

        seen: list[CredentialReference] = []
        for _, value in self.bound:
            for reference in value.credential_references:
                if reference not in seen:
                    seen.append(reference)
        return tuple(seen)

    @property
    def unanswered(self) -> tuple[InstallationInputField, ...]:
        answered = {(owner, item.input.id) for owner, value in self.bound for item in value.inputs}
        return tuple(
            item for item in self.fields if item.input.required and item.key not in answered
        )

    @property
    def ready(self) -> bool:
        return not self.unanswered

    def bound_for(self, owner: InstallationOwner) -> BoundInputs:
        """What this one installation has bound, which is what its planner is given."""

        for candidate, value in self.bound:
            if candidate == owner:
                return value
        return BoundInputs()

    def sources_for(self, owner: InstallationOwner) -> tuple[InputValueSource, ...]:
        """Return only the sources this one installation answered, in canonical input order."""

        return tuple(item.source for item in self.bound_for(owner).inputs)

    def views(
        self,
        credential_observations: tuple[CredentialObservation, ...] = (),
    ) -> tuple[InputView, ...]:
        """One row per field, keyed by `InputView.row` because two rows may share an id."""

        projected: list[InputView] = []
        for owner in sorted({item.owner for item in self.fields}):
            declared = tuple(item.input for item in self.fields if item.owner == owner)
            projected.extend(
                project_required_inputs(
                    declared,
                    bound_inputs=self.bound_for(owner),
                    credential_observations=credential_observations,
                    declared_by=tuple((str(owner), item) for item in declared),
                    owner=str(owner),
                )
            )
        return tuple(projected)


def _ordered_uses(
    uses: Iterable[InstallationInputUse],
) -> tuple[InstallationInputUse, ...]:
    return tuple(sorted(set(uses), key=lambda item: (item.owner, item.input.id.value)))


def compose_installation_inputs(
    uses: tuple[InstallationInputUse, ...],
    sources: tuple[OwnedInputSource, ...],
    policy: EffectivePolicy,
) -> Result[InstallationInputComposition]:
    """Aggregate declarations and validate the currently supplied safe value sources.

    A declared default remains on ``ConfigInput`` for screen prefill.  It becomes a source only
    after a caller submits it as ``PromptedConfigValue``; merely drawing a default is not consent to
    install with it.

    Each owner binds separately, so ``BoundInputs``' "each input binds exactly once" now holds
    within one installation, which is where it was always true.
    """

    if (
        any(not isinstance(item, InstallationInputUse) for item in uses)
        or any(not isinstance(item, OwnedInputSource) for item in sources)
        or not isinstance(policy, EffectivePolicy)
    ):
        return _error(
            INPUT_COMPOSITION_INVALID,
            "installation input composition needs declared uses, owned sources and a policy",
        )
    ordered = _ordered_uses(uses)
    declarations: dict[InstallationOwner, dict[InputId, RuntimeInput]] = {}
    for use in ordered:
        # The same owner declaring one id twice with different semantics is one artifact
        # contradicting itself, which `InstallDescription` already refuses; two owners doing it are
        # simply two fields, which is why there is no conflict diagnostic here any more.
        declarations.setdefault(use.owner, {})[use.input.id] = use.input

    # An answer addressed to an installation this composition does not have is dropped rather than
    # refused. Narrowing the chosen harnesses re-composes the same selection with fewer owners, and
    # the answers already given for the ones left out are still correct -- they simply have nothing
    # to attach to. `ready` is what notices an installation that has not been answered.
    answered: dict[InstallationOwner, list[InputValueSource]] = {}
    for owned in sources:
        if owned.source.input in declarations.get(owned.owner, {}):
            answered.setdefault(owned.owner, []).append(owned.source)

    bound: list[tuple[InstallationOwner, BoundInputs]] = []
    for owner in sorted(declarations):
        supplied = tuple(answered.get(owner, ()))
        identifiers = {item.input for item in supplied}
        selected = tuple(
            declarations[owner][identifier]
            for identifier in sorted(
                identifiers & set(declarations[owner]), key=lambda item: item.value
            )
        )
        result = bind_runtime_inputs(selected, supplied, policy)
        if isinstance(result, Err):
            return result
        bound.append((owner, result.value))

    try:
        fields = tuple(
            sorted(
                (
                    InstallationInputField(owner, declared)
                    for owner, declared_inputs in declarations.items()
                    for declared in declared_inputs.values()
                ),
                key=_field_sort_key,
            )
        )
        return Ok(InstallationInputComposition(ordered, fields, tuple(bound)))
    except ValueError as error:
        return _error(INPUT_COMPOSITION_INVALID, f"installation inputs are invalid: {error}")
