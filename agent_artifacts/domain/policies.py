"""The canonical restrictive Policy algebra."""

from __future__ import annotations

from dataclasses import dataclass

from .effects import Effect, RiskClass


def _valid_set(values: frozenset[str] | None, label: str) -> None:
    if values is not None and any(
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character in value for character in "\r\n")
        for value in values
    ):
        raise ValueError(f"{label} contains an invalid value")


@dataclass(frozen=True, slots=True)
class EffectivePolicy:
    allowed_registries: frozenset[str] | None = None
    allowed_runtimes: frozenset[str] | None = None
    allowed_transports: frozenset[str] | None = None
    allowed_credential_providers: frozenset[str] | None = None
    forbidden_effects: frozenset[str] = frozenset()
    required_checks: frozenset[str] = frozenset()
    risk_ceiling: RiskClass = RiskClass.HIGH_RISK_EXECUTION

    def __post_init__(self) -> None:
        _valid_set(self.allowed_registries, "allowed registries")
        _valid_set(self.allowed_runtimes, "allowed runtimes")
        _valid_set(self.allowed_transports, "allowed transports")
        _valid_set(self.allowed_credential_providers, "allowed credential providers")
        _valid_set(self.forbidden_effects, "forbidden effects")
        _valid_set(self.required_checks, "required checks")
        if not isinstance(self.risk_ceiling, RiskClass):
            raise ValueError("risk ceiling is invalid")

    def permits_effect(self, effect: Effect) -> bool:
        kind = str(effect_to_policy_key(effect))
        return kind not in self.forbidden_effects and effect.risk <= self.risk_ceiling


@dataclass(frozen=True, slots=True)
class PolicyOverlay:
    allowed_registries: frozenset[str] | None = None
    allowed_runtimes: frozenset[str] | None = None
    allowed_transports: frozenset[str] | None = None
    allowed_credential_providers: frozenset[str] | None = None
    forbidden_effects: frozenset[str] = frozenset()
    required_checks: frozenset[str] = frozenset()
    risk_ceiling: RiskClass | None = None

    def __post_init__(self) -> None:
        _valid_set(self.allowed_registries, "allowed registries")
        _valid_set(self.allowed_runtimes, "allowed runtimes")
        _valid_set(self.allowed_transports, "allowed transports")
        _valid_set(self.allowed_credential_providers, "allowed credential providers")
        _valid_set(self.forbidden_effects, "forbidden effects")
        _valid_set(self.required_checks, "required checks")
        if self.risk_ceiling is not None and not isinstance(self.risk_ceiling, RiskClass):
            raise ValueError("risk ceiling is invalid")


def _narrow(parent: frozenset[str] | None, child: frozenset[str] | None) -> frozenset[str] | None:
    if parent is None:
        return child
    if child is None:
        return parent
    return parent & child


def compose_policy(parent: EffectivePolicy, overlay: PolicyOverlay) -> EffectivePolicy:
    ceiling = (
        parent.risk_ceiling
        if overlay.risk_ceiling is None
        else min(parent.risk_ceiling, overlay.risk_ceiling)
    )
    return EffectivePolicy(
        allowed_registries=_narrow(parent.allowed_registries, overlay.allowed_registries),
        allowed_runtimes=_narrow(parent.allowed_runtimes, overlay.allowed_runtimes),
        allowed_transports=_narrow(parent.allowed_transports, overlay.allowed_transports),
        allowed_credential_providers=_narrow(
            parent.allowed_credential_providers, overlay.allowed_credential_providers
        ),
        forbidden_effects=parent.forbidden_effects | overlay.forbidden_effects,
        required_checks=parent.required_checks | overlay.required_checks,
        risk_ceiling=ceiling,
    )


def effect_to_policy_key(effect: Effect) -> str:
    name = type(effect).__name__
    return "".join(
        ("-" + character.lower()) if character.isupper() else character for character in name
    ).lstrip("-")
