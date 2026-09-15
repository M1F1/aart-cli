"""Immutable, secret-free environment observations used by pure planning."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .requirements import RequirementId


def _line(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character in value for character in "\r\n")
    ):
        raise ValueError(f"{label} must be one safe non-empty line")
    return value


class FactState(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True, order=True)
class EnvironmentFact:
    requirement: RequirementId
    state: FactState
    observed_version: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.requirement, RequirementId) or not isinstance(self.state, FactState):
            raise ValueError("environment fact is invalid")
        if self.observed_version is not None:
            _line(self.observed_version, "observed version")
        if self.state is not FactState.AVAILABLE and self.observed_version is not None:
            raise ValueError("only an available fact can carry an observed version")


class RemediationCapabilityKind(str, Enum):
    CREDENTIAL_PROVIDER = "credential-provider"
    EXECUTABLE_INSTALLER = "executable-installer"
    HARNESS_CONFIGURATION = "harness-configuration"
    NETWORK_CONFIGURATION = "network-configuration"
    PYTHON_INSTALLER = "python-installer"
    RUNTIME_INSTALLER = "runtime-installer"


@dataclass(frozen=True, slots=True, order=True)
class RemediationCapability:
    kind: RemediationCapabilityKind
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, RemediationCapabilityKind):
            raise ValueError("remediation capability kind is invalid")
        _line(self.name, "remediation capability name")


@dataclass(frozen=True, slots=True)
class EnvironmentFacts:
    platform: str
    facts: tuple[EnvironmentFact, ...] = ()
    remediation_capabilities: tuple[RemediationCapability, ...] = ()

    def __post_init__(self) -> None:
        _line(self.platform, "environment platform")
        if any(not isinstance(item, EnvironmentFact) for item in self.facts) or any(
            not isinstance(item, RemediationCapability) for item in self.remediation_capabilities
        ):
            raise ValueError("environment facts contain invalid values")
        facts = tuple(sorted(self.facts, key=lambda item: item.requirement.value))
        if len({item.requirement for item in facts}) != len(facts):
            raise ValueError("environment facts require one observation per requirement")
        object.__setattr__(self, "facts", facts)
        object.__setattr__(
            self,
            "remediation_capabilities",
            tuple(sorted(set(self.remediation_capabilities))),
        )


def environment_facts_to_data(facts: EnvironmentFacts) -> dict[str, object]:
    return {
        "facts": [
            {
                "requirement": item.requirement.value,
                "state": item.state.value,
                "observed_version": item.observed_version,
            }
            for item in facts.facts
        ],
        "platform": facts.platform,
        "remediation_capabilities": [
            {"kind": item.kind.value, "name": item.name} for item in facts.remediation_capabilities
        ],
    }
