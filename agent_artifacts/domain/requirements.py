"""The canonical Requirement algebra and effect-free assessment values."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

from .python_runtime import LOCK_FORMATS

_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


def _single_line(value: str, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\n" in value
        or "\r" in value
    ):
        raise ValueError(f"{label} must be one non-empty line")
    return value


@dataclass(frozen=True, slots=True, order=True)
class RequirementId:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or _ID_RE.fullmatch(self.value) is None:
            raise ValueError("requirement id must be a canonical slug")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class CredentialRequirement:
    id: RequirementId
    provider: str | None = None
    required: bool = True

    def __post_init__(self) -> None:
        if (
            not isinstance(self.id, RequirementId)
            or (self.provider is not None and _ID_RE.fullmatch(self.provider) is None)
            or not isinstance(self.required, bool)
        ):
            raise ValueError("credential requirement is invalid")


@dataclass(frozen=True, slots=True)
class RuntimeRequirement:
    id: RequirementId
    runtime: str
    constraint: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, RequirementId) or _ID_RE.fullmatch(self.runtime) is None:
            raise ValueError("runtime requirement is invalid")
        _single_line(self.constraint, "runtime constraint")


@dataclass(frozen=True, slots=True)
class ExecutableRequirement:
    id: RequirementId
    executable: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, RequirementId) or _ID_RE.fullmatch(self.executable) is None:
            raise ValueError("executable requirement is invalid")


@dataclass(frozen=True, slots=True)
class NetworkRequirement:
    id: RequirementId
    host: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, RequirementId):
            raise ValueError("network requirement is invalid")
        _single_line(self.host, "network host")


@dataclass(frozen=True, slots=True)
class FilesystemRequirement:
    id: RequirementId
    path: str
    access: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, RequirementId) or self.access not in {
            "read",
            "write",
            "execute",
        }:
            raise ValueError("filesystem requirement is invalid")
        _single_line(self.path, "filesystem path")


@dataclass(frozen=True, slots=True)
class HarnessRequirement:
    id: RequirementId
    harness: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, RequirementId) or _ID_RE.fullmatch(self.harness) is None:
            raise ValueError("harness requirement is invalid")


@dataclass(frozen=True, slots=True)
class PythonPackageRequirement:
    """The dependency contract an artifact declares, never the backend that installs it."""

    id: RequirementId
    descriptor: str
    path: str
    lock_format: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, RequirementId) or self.descriptor not in {
            "requirements",
            "pyproject",
        }:
            raise ValueError("Python package requirement is invalid")
        _single_line(self.path, "dependency descriptor path")
        if self.lock_format is not None and self.lock_format not in LOCK_FORMATS:
            raise ValueError("Python package lock format is unsupported")


Requirement: TypeAlias = (
    CredentialRequirement
    | RuntimeRequirement
    | ExecutableRequirement
    | NetworkRequirement
    | FilesystemRequirement
    | HarnessRequirement
    | PythonPackageRequirement
)


class RequirementState(str, Enum):
    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class RequirementAssessment:
    requirement: Requirement
    state: RequirementState
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.state, RequirementState) or not isinstance(self.detail, str):
            raise ValueError("requirement assessment is invalid")
        if "\n" in self.detail or "\r" in self.detail:
            raise ValueError("requirement assessment detail must be one line")


def requirement_to_data(requirement: Requirement) -> dict[str, object]:
    if isinstance(requirement, CredentialRequirement):
        return {
            "id": requirement.id.value,
            "kind": "credential",
            "provider": requirement.provider,
            "required": requirement.required,
        }
    if isinstance(requirement, RuntimeRequirement):
        return {
            "constraint": requirement.constraint,
            "id": requirement.id.value,
            "kind": "runtime",
            "runtime": requirement.runtime,
        }
    if isinstance(requirement, ExecutableRequirement):
        return {
            "executable": requirement.executable,
            "id": requirement.id.value,
            "kind": "executable",
        }
    if isinstance(requirement, NetworkRequirement):
        return {"host": requirement.host, "id": requirement.id.value, "kind": "network"}
    if isinstance(requirement, FilesystemRequirement):
        return {
            "access": requirement.access,
            "id": requirement.id.value,
            "kind": "filesystem",
            "path": requirement.path,
        }
    if isinstance(requirement, HarnessRequirement):
        return {"harness": requirement.harness, "id": requirement.id.value, "kind": "harness"}
    return {
        "descriptor": requirement.descriptor,
        "id": requirement.id.value,
        "kind": "python-package",
        "lock_format": requirement.lock_format,
        "path": requirement.path,
    }
