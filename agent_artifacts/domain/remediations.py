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

    def __post_init__(self) -> None:
        if not isinstance(self.requirement, RequirementId):
            raise ValueError("network remediation requires a requirement id")
        if (
            not isinstance(self.host, str)
            or not self.host
            or any(character in self.host for character in "\r\n")
        ):
            raise ValueError("network remediation host is invalid")


@dataclass(frozen=True, slots=True)
class ConfigureHarness:
    requirement: RequirementId
    harness: str

    def __post_init__(self) -> None:
        if not isinstance(self.requirement, RequirementId):
            raise ValueError("harness remediation requires a requirement id")
        _token(self.harness, "harness")


@dataclass(frozen=True, slots=True)
class InstallPythonPackages:
    """Install a declared dependency descriptor with one named backend.

    The installer is part of the remediation because "install the dependencies" and "install them
    with uv" are different things to offer and different things to approve.
    """

    requirement: RequirementId
    installer: str

    def __post_init__(self) -> None:
        if not isinstance(self.requirement, RequirementId):
            raise ValueError("Python package remediation requires a requirement id")
        _token(self.installer, "Python installer")


@dataclass(frozen=True, slots=True)
class SelectAlternativeProvider:
    requirement: RequirementId
    provider: str

    def __post_init__(self) -> None:
        if not isinstance(self.requirement, RequirementId):
            raise ValueError("provider remediation requires a requirement id")
        _token(self.provider, "credential provider")


Remediation: TypeAlias = (
    ConfigureCredential
    | InstallRuntime
    | InstallExecutable
    | InstallPythonPackages
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
    if isinstance(remediation, InstallPythonPackages):
        return {
            "installer": remediation.installer,
            "kind": "install-python-packages",
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
