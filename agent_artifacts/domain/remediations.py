"""The canonical Remediation algebra: possible resolutions, never performed effects."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypeAlias

from .requirements import RequirementId

_TOKEN_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


def _token(value: str, label: str) -> None:
    if not isinstance(value, str) or _TOKEN_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be a canonical slug")


@dataclass(frozen=True, slots=True)
class ConfigureCredential:
    requirement: RequirementId
    provider: str

    def __post_init__(self) -> None:
        if not isinstance(self.requirement, RequirementId):
            raise ValueError("credential remediation requires a requirement id")
        _token(self.provider, "credential provider")


@dataclass(frozen=True, slots=True)
class InstallRuntime:
    requirement: RequirementId
    runtime: str
    constraint: str

    def __post_init__(self) -> None:
        if not isinstance(self.requirement, RequirementId):
            raise ValueError("runtime remediation requires a requirement id")
        _token(self.runtime, "runtime")
        if not self.constraint or any(character in self.constraint for character in "\r\n"):
            raise ValueError("runtime remediation constraint is invalid")


@dataclass(frozen=True, slots=True)
class InstallExecutable:
    requirement: RequirementId
    executable: str

    def __post_init__(self) -> None:
        if not isinstance(self.requirement, RequirementId):
            raise ValueError("executable remediation requires a requirement id")
        _token(self.executable, "executable")


@dataclass(frozen=True, slots=True)
class ConfigureNetwork:
    requirement: RequirementId
    host: str


@dataclass(frozen=True, slots=True)
class ConfigureHarness:
    requirement: RequirementId
    harness: str


@dataclass(frozen=True, slots=True)
class SelectAlternativeProvider:
    requirement: RequirementId
    provider: str


Remediation: TypeAlias = (
    ConfigureCredential
    | InstallRuntime
    | InstallExecutable
    | ConfigureNetwork
    | ConfigureHarness
    | SelectAlternativeProvider
)


def remediation_to_data(remediation: Remediation) -> dict[str, object]:
    if isinstance(remediation, ConfigureCredential):
        return {
            "kind": "configure-credential",
            "provider": remediation.provider,
            "requirement": str(remediation.requirement),
        }
    if isinstance(remediation, InstallRuntime):
        return {
            "constraint": remediation.constraint,
            "kind": "install-runtime",
            "requirement": str(remediation.requirement),
            "runtime": remediation.runtime,
        }
    if isinstance(remediation, InstallExecutable):
        return {
            "executable": remediation.executable,
            "kind": "install-executable",
            "requirement": str(remediation.requirement),
        }
    if isinstance(remediation, ConfigureNetwork):
        return {
            "host": remediation.host,
            "kind": "configure-network",
            "requirement": str(remediation.requirement),
        }
    if isinstance(remediation, ConfigureHarness):
        return {
            "harness": remediation.harness,
            "kind": "configure-harness",
            "requirement": str(remediation.requirement),
        }
    return {
        "kind": "select-alternative-provider",
        "provider": remediation.provider,
        "requirement": str(remediation.requirement),
    }
