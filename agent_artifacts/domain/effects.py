"""The canonical Effect algebra with explicit risk and reconciliation capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import ClassVar, TypeAlias


class RiskClass(IntEnum):
    READ_ONLY = 0
    LOCAL_MUTATION = 10
    CONFIGURATION_MUTATION = 20
    CREDENTIAL_MUTATION = 30
    EXECUTABLE_INSTALL = 40
    NETWORK_MUTATION = 50
    HIGH_RISK_EXECUTION = 60


class DeliveryKind(str, Enum):
    """What is put where a harness reads it: a directory, or one file."""

    TREE = "tree"
    FILE = "file"


@dataclass(frozen=True, slots=True)
class EffectCapabilities:
    inspectable: bool
    idempotent: bool
    reversible: bool
    independently_repairable: bool

    def __post_init__(self) -> None:
        values = (
            self.inspectable,
            self.idempotent,
            self.reversible,
            self.independently_repairable,
        )
        if any(not isinstance(value, bool) for value in values):
            raise ValueError("effect capabilities must be booleans")
        if self.independently_repairable and not self.inspectable:
            raise ValueError("independent repair requires inspectability")


#: How an installer must read a descriptor. A locked project is not the same job as a loose one.
DESCRIPTOR_KINDS = ("requirements", "pyproject", "locked-project")

_OWNED = EffectCapabilities(True, True, True, True)
_RECREATABLE = EffectCapabilities(True, True, False, True)
_CREDENTIAL = EffectCapabilities(True, False, False, True)
_HARNESS = EffectCapabilities(True, True, True, True)
_REMOVAL = EffectCapabilities(True, True, False, True)


def _delivery_kind(value: object) -> DeliveryKind:
    try:
        return DeliveryKind(value)
    except ValueError:
        raise ValueError(f"{value!r} is not a shape an artifact can be delivered as") from None


def _line(value: str, label: str) -> None:
    if not isinstance(value, str) or not value or any(character in value for character in "\r\n"):
        raise ValueError(f"{label} must be one non-empty line")


@dataclass(frozen=True, slots=True)
class CopyTree:
    source: str
    destination: str
    risk: ClassVar[RiskClass] = RiskClass.LOCAL_MUTATION
    capabilities: ClassVar[EffectCapabilities] = _OWNED

    def __post_init__(self) -> None:
        _line(self.source, "copy source")
        _line(self.destination, "copy destination")


@dataclass(frozen=True, slots=True)
class WriteFile:
    destination: str
    content_digest: str
    executable: bool = False
    risk: ClassVar[RiskClass] = RiskClass.LOCAL_MUTATION
    capabilities: ClassVar[EffectCapabilities] = _OWNED

    def __post_init__(self) -> None:
        _line(self.destination, "write destination")
        _line(self.content_digest, "content digest")
        if not isinstance(self.executable, bool):
            raise ValueError("executable must be boolean")


@dataclass(frozen=True, slots=True)
class RemoveOwnedPath:
    """Remove a path owned by one installed artifact.

    The effect deliberately says whether a directory tree may be removed. The interpreter still
    proves ownership before acting; a recursive flag is not authority to cross an artifact root.
    """

    destination: str
    recursive: bool = False
    risk: ClassVar[RiskClass] = RiskClass.LOCAL_MUTATION
    capabilities: ClassVar[EffectCapabilities] = _REMOVAL

    def __post_init__(self) -> None:
        _line(self.destination, "removal destination")
        if not isinstance(self.recursive, bool):
            raise ValueError("recursive removal flag must be boolean")


@dataclass(frozen=True, slots=True)
class CreatePythonEnvironment:
    """Build an artifact-owned environment from a named base interpreter.

    The base interpreter is part of the effect because "whichever Python happens to be active" is
    not something a reviewer can approve or a reconciler can re-check (INV-046).
    """

    artifact: str
    destination: str
    base_interpreter: str
    risk: ClassVar[RiskClass] = RiskClass.EXECUTABLE_INSTALL
    capabilities: ClassVar[EffectCapabilities] = _RECREATABLE

    def __post_init__(self) -> None:
        _line(self.artifact, "artifact")
        _line(self.destination, "environment destination")
        _line(self.base_interpreter, "base interpreter")


@dataclass(frozen=True, slots=True)
class InstallPythonDependencies:
    """Install a declared descriptor with a selected backend.

    The installer is data, not a separate effect: approving an install with uv is not approving
    the same install with pip, so the choice has to reach the review digest (INV-042).
    """

    environment: str
    descriptor: str
    descriptor_kind: str
    installer: str
    risk: ClassVar[RiskClass] = RiskClass.EXECUTABLE_INSTALL
    capabilities: ClassVar[EffectCapabilities] = _RECREATABLE

    def __post_init__(self) -> None:
        _line(self.environment, "Python environment")
        _line(self.descriptor, "dependency descriptor")
        _line(self.installer, "dependency installer")
        if self.descriptor_kind not in DESCRIPTOR_KINDS:
            raise ValueError("dependency descriptor kind is unsupported")


@dataclass(frozen=True, slots=True)
class StoreCredential:
    reference: str
    provider: str
    risk: ClassVar[RiskClass] = RiskClass.CREDENTIAL_MUTATION
    capabilities: ClassVar[EffectCapabilities] = _CREDENTIAL

    def __post_init__(self) -> None:
        _line(self.reference, "credential reference")
        _line(self.provider, "credential provider")


@dataclass(frozen=True, slots=True)
class ReplaceCredential:
    reference: str
    provider: str
    risk: ClassVar[RiskClass] = RiskClass.CREDENTIAL_MUTATION
    capabilities: ClassVar[EffectCapabilities] = _CREDENTIAL

    def __post_init__(self) -> None:
        _line(self.reference, "credential reference")
        _line(self.provider, "credential provider")


@dataclass(frozen=True, slots=True)
class DeleteCredential:
    reference: str
    provider: str
    risk: ClassVar[RiskClass] = RiskClass.CREDENTIAL_MUTATION
    capabilities: ClassVar[EffectCapabilities] = _CREDENTIAL

    def __post_init__(self) -> None:
        _line(self.reference, "credential reference")
        _line(self.provider, "credential provider")


@dataclass(frozen=True, slots=True)
class VerifyCredential:
    """Ask the provider whether the reference resolves. It never returns the value."""

    reference: str
    provider: str
    risk: ClassVar[RiskClass] = RiskClass.READ_ONLY
    capabilities: ClassVar[EffectCapabilities] = EffectCapabilities(True, True, False, True)

    def __post_init__(self) -> None:
        _line(self.reference, "credential reference")
        _line(self.provider, "credential provider")


@dataclass(frozen=True, slots=True)
class ConfigureHarness:
    harness: str
    artifact: str
    destination: str
    risk: ClassVar[RiskClass] = RiskClass.CONFIGURATION_MUTATION
    capabilities: ClassVar[EffectCapabilities] = _HARNESS

    def __post_init__(self) -> None:
        _line(self.harness, "harness")
        _line(self.artifact, "artifact")
        _line(self.destination, "harness destination")


@dataclass(frozen=True, slots=True)
class UnconfigureHarness:
    """Remove only the named owned entry from a harness settings file."""

    harness: str
    server: str
    destination: str
    risk: ClassVar[RiskClass] = RiskClass.CONFIGURATION_MUTATION
    capabilities: ClassVar[EffectCapabilities] = _HARNESS

    def __post_init__(self) -> None:
        _line(self.harness, "harness")
        _line(self.server, "harness server")
        _line(self.destination, "harness destination")


@dataclass(frozen=True, slots=True)
class DeliverArtifact:
    """Place an installed artifact where one harness reads it.

    This is a configuration mutation rather than a local one. The destination belongs to the
    harness, not to AART, and a policy ceiling that refuses to register an MCP server has to refuse
    writing a Skill straight into the directory that same harness reads. A `CopyTree` would have
    carried LOCAL_MUTATION and slipped underneath that ceiling.

    The source is inside the artifact's own tree, so a withdrawal can be undone while the payload
    stands -- which is why this is reversible in the same way an entry in a settings file is.
    """

    harness: str
    artifact: str
    source: str
    destination: str
    delivery: DeliveryKind
    risk: ClassVar[RiskClass] = RiskClass.CONFIGURATION_MUTATION
    capabilities: ClassVar[EffectCapabilities] = _HARNESS

    def __post_init__(self) -> None:
        _line(self.harness, "harness")
        _line(self.artifact, "artifact")
        _line(self.source, "delivery source")
        _line(self.destination, "delivery destination")
        object.__setattr__(self, "delivery", _delivery_kind(self.delivery))


@dataclass(frozen=True, slots=True)
class WithdrawArtifact:
    """Remove only the delivery this artifact owns from where a harness reads it."""

    harness: str
    artifact: str
    destination: str
    delivery: DeliveryKind
    risk: ClassVar[RiskClass] = RiskClass.CONFIGURATION_MUTATION
    capabilities: ClassVar[EffectCapabilities] = _HARNESS

    def __post_init__(self) -> None:
        _line(self.harness, "harness")
        _line(self.artifact, "artifact")
        _line(self.destination, "delivery destination")
        object.__setattr__(self, "delivery", _delivery_kind(self.delivery))


@dataclass(frozen=True, slots=True)
class VerifyRequirement:
    requirement: str
    risk: ClassVar[RiskClass] = RiskClass.READ_ONLY
    capabilities: ClassVar[EffectCapabilities] = EffectCapabilities(True, True, False, True)

    def __post_init__(self) -> None:
        _line(self.requirement, "verified requirement")


Effect: TypeAlias = (
    CopyTree
    | WriteFile
    | RemoveOwnedPath
    | CreatePythonEnvironment
    | InstallPythonDependencies
    | StoreCredential
    | ReplaceCredential
    | DeleteCredential
    | VerifyCredential
    | ConfigureHarness
    | UnconfigureHarness
    | DeliverArtifact
    | WithdrawArtifact
    | VerifyRequirement
)


def effect_to_data(effect: Effect) -> dict[str, object]:
    data: dict[str, object] = {
        "capabilities": {
            "idempotent": effect.capabilities.idempotent,
            "independently_repairable": effect.capabilities.independently_repairable,
            "inspectable": effect.capabilities.inspectable,
            "reversible": effect.capabilities.reversible,
        },
        "risk": effect.risk.name.lower().replace("_", "-"),
    }
    if isinstance(effect, CopyTree):
        data.update(kind="copy-tree", source=effect.source, destination=effect.destination)
    elif isinstance(effect, WriteFile):
        data.update(
            kind="write-file",
            destination=effect.destination,
            content_digest=effect.content_digest,
            executable=effect.executable,
        )
    elif isinstance(effect, RemoveOwnedPath):
        data.update(
            kind="remove-owned-path",
            destination=effect.destination,
            recursive=effect.recursive,
        )
    elif isinstance(effect, CreatePythonEnvironment):
        data.update(
            kind="create-python-environment",
            artifact=effect.artifact,
            base_interpreter=effect.base_interpreter,
            destination=effect.destination,
        )
    elif isinstance(effect, InstallPythonDependencies):
        data.update(
            kind="install-python-dependencies",
            environment=effect.environment,
            descriptor=effect.descriptor,
            descriptor_kind=effect.descriptor_kind,
            installer=effect.installer,
        )
    elif isinstance(effect, StoreCredential):
        data.update(kind="store-credential", reference=effect.reference, provider=effect.provider)
    elif isinstance(effect, ReplaceCredential):
        data.update(kind="replace-credential", reference=effect.reference, provider=effect.provider)
    elif isinstance(effect, DeleteCredential):
        data.update(kind="delete-credential", reference=effect.reference, provider=effect.provider)
    elif isinstance(effect, VerifyCredential):
        data.update(kind="verify-credential", reference=effect.reference, provider=effect.provider)
    elif isinstance(effect, ConfigureHarness):
        data.update(
            kind="configure-harness",
            harness=effect.harness,
            artifact=effect.artifact,
            destination=effect.destination,
        )
    elif isinstance(effect, UnconfigureHarness):
        data.update(
            kind="unconfigure-harness",
            harness=effect.harness,
            server=effect.server,
            destination=effect.destination,
        )
    elif isinstance(effect, DeliverArtifact):
        data.update(
            kind="deliver-artifact",
            harness=effect.harness,
            artifact=effect.artifact,
            source=effect.source,
            destination=effect.destination,
            delivery=effect.delivery.value,
        )
    elif isinstance(effect, WithdrawArtifact):
        data.update(
            kind="withdraw-artifact",
            harness=effect.harness,
            artifact=effect.artifact,
            destination=effect.destination,
            delivery=effect.delivery.value,
        )
    else:
        data.update(kind="verify-requirement", requirement=effect.requirement)
    return data
