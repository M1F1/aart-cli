"""The Python dependency-specification algebra and the artifact-owned environment layout.

Two separations carry this module. An artifact declares what its dependencies *are*
(`RequirementsFile`, `PyProjectSpec`); nothing here names pip or uv, because which backend installs
them is the platform's and the policy's decision, not the artifact's (INV-042). And an installed
artifact owns its environment (INV-044): the paths below are derived from the artifact root rather
than accepted from a caller, so no code path can point a generated launcher at a global
interpreter (INV-045, INV-046).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TypeAlias

#: Lock formats a V1 installer can read. Poetry is deliberately absent; see B-005.
LOCK_FORMATS = ("uv",)

_ENVIRONMENT_SUBPATH = "runtime/.venv"
_PAYLOAD_SUBPATH = "payload"
_INTERPRETER_SUBPATH = "bin/python"


class PythonInstaller(str, Enum):
    """A backend that can install dependencies. Selected by the platform, never by the artifact."""

    PIP = "pip"
    UV = "uv"


def _line(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character in value for character in "\r\n\x00")
    ):
        raise ValueError(f"{label} must be one safe non-empty line")
    return value


def _payload_relative(value: object, label: str) -> str:
    """A path inside the artifact payload, which cannot be absolute and cannot climb out of it."""

    path = _line(value, label)
    segments = path.split("/")
    if path.startswith("/") or "\\" in path or any(part in ("", ".", "..") for part in segments):
        raise ValueError(f"{label} must be a relative path inside the artifact payload")
    return path


def _root(value: object, label: str) -> str:
    path = _line(value, label)
    if "\\" in path or any(part == ".." for part in path.split("/")) or path.endswith("/"):
        raise ValueError(f"{label} must be a plain path with no parent segments")
    return path


@dataclass(frozen=True, slots=True)
class RequirementsFile:
    """A `requirements.txt`-style descriptor, readable by pip and by uv alike."""

    path: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _payload_relative(self.path, "requirements path"))


@dataclass(frozen=True, slots=True)
class PyProjectSpec:
    """A `pyproject.toml` descriptor, optionally with the lock a resolver already produced."""

    pyproject: str
    lock: str | None = None
    lock_format: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "pyproject", _payload_relative(self.pyproject, "pyproject path"))
        if (self.lock is None) != (self.lock_format is None):
            raise ValueError("a lock and its format are declared together or not at all")
        if self.lock is not None:
            object.__setattr__(self, "lock", _payload_relative(self.lock, "lock path"))
            if self.lock_format not in LOCK_FORMATS:
                raise ValueError("lock format is unsupported")


PythonDependencySpec: TypeAlias = RequirementsFile | PyProjectSpec


def spec_kind(spec: PythonDependencySpec) -> str:
    return "requirements" if isinstance(spec, RequirementsFile) else "pyproject"


def spec_descriptor_path(spec: PythonDependencySpec) -> str:
    """The descriptor an installer reads, relative to the payload."""

    return spec.path if isinstance(spec, RequirementsFile) else spec.pyproject


def installers_for_lock(lock_format: str | None) -> frozenset[PythonInstaller]:
    """Which backends can read a dependency contract locked in this format.

    A lock is only meaningful to the resolver that wrote it, so a locked contract narrows to that
    one backend. An unlocked one is readable by both V1 backends.
    """

    if lock_format is None:
        return frozenset(PythonInstaller)
    return frozenset({PythonInstaller(lock_format)})


def compatible_installers(spec: PythonDependencySpec) -> frozenset[PythonInstaller]:
    """Which backends can install this specification, as a property of the specification alone."""

    return installers_for_lock(spec.lock_format if isinstance(spec, PyProjectSpec) else None)


@dataclass(frozen=True, slots=True)
class ArtifactEnvironment:
    """The isolated environment one installed artifact owns.

    Every path is derived. A caller supplies the artifact and its root and gets the rest, so an
    interpreter outside the root is not something this type can be talked into producing.
    """

    artifact: str
    root: str
    payload: str = field(init=False)
    environment: str = field(init=False)
    interpreter: str = field(init=False)

    def __post_init__(self) -> None:
        _line(self.artifact, "artifact name")
        root = _root(self.root, "artifact root")
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "payload", f"{root}/{_PAYLOAD_SUBPATH}")
        environment = f"{root}/{_ENVIRONMENT_SUBPATH}"
        object.__setattr__(self, "environment", environment)
        object.__setattr__(self, "interpreter", f"{environment}/{_INTERPRETER_SUBPATH}")

    def owns(self, path: str) -> bool:
        """Whether `path` lies inside this artifact's root. A climbing path is never owned."""

        if not isinstance(path, str) or not path:
            return False
        if any(part == ".." for part in path.split("/")):
            return False
        return path == self.root or path.startswith(f"{self.root}/")

    def payload_path(self, relative: str) -> str:
        return f"{self.payload}/{_payload_relative(relative, 'payload path')}"


def dependency_spec_to_data(spec: PythonDependencySpec) -> dict[str, object]:
    if isinstance(spec, RequirementsFile):
        return {"kind": "requirements", "path": spec.path}
    return {
        "kind": "pyproject",
        "lock": spec.lock,
        "lock_format": spec.lock_format,
        "pyproject": spec.pyproject,
    }


def artifact_environment_to_data(environment: ArtifactEnvironment) -> dict[str, object]:
    return {
        "artifact": environment.artifact,
        "environment": environment.environment,
        "interpreter": environment.interpreter,
        "payload": environment.payload,
        "root": environment.root,
    }
