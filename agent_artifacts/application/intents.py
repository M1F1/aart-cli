"""Installed lifecycle intents expressed as desired states over one reconciler.

An intent changes what should be true; it does not select a procedure. Install, update, configure,
repair, credential rotation, harness reconfiguration, downgrade and uninstall all lower through
``plan_repair``. Component-specific builders restrict which desired components may change so a
token rotation cannot quietly become a launcher/runtime reinstall.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agent_artifacts.domain.identifiers import ObjectDigest
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.reconciliation import (
    Component,
    CurrentState,
    DesiredComponent,
    DesiredState,
    DriftKind,
    compare_states,
)
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import OwnershipReason
from agent_artifacts.protocol.semver import SemVer, parse_semver

from .reconciliation import RepairPlan, plan_repair

__all__ = [
    "CollectionHealth",
    "InstalledHealth",
    "LifecycleIntent",
    "LifecycleIntentKind",
    "LifecyclePlan",
    "MemberHealth",
    "collection_health",
    "configure_intent",
    "credential_rotation_intent",
    "downgrade_intent",
    "harness_reconfiguration_intent",
    "install_intent",
    "installation_health",
    "plan_lifecycle_intent",
    "repair_intent",
    "uninstall_intent",
    "update_intent",
]


class LifecycleIntentKind(str, Enum):
    INSTALL = "install"
    UPDATE = "update"
    CONFIGURE = "configure"
    REPAIR = "repair"
    CREDENTIAL_ROTATION = "credential-rotation"
    HARNESS_RECONFIGURATION = "harness-reconfiguration"
    DOWNGRADE = "downgrade"
    UNINSTALL = "uninstall"


class InstalledHealth(str, Enum):
    """What is known about one installation, including that nothing is.

    ``UNKNOWN`` is not a fifth degree of badness. It is the absence of a measurement, and it exists
    because the alternative -- reporting an unmeasured installation as ready, or omitting it -- is
    the one answer that is never safe. Nothing derives it from drift; it is asserted only where the
    evidence to measure health does not exist at all.
    """

    READY = "ready"
    UPDATE = "update"
    UNKNOWN = "unknown"
    ATTENTION = "attention"
    BROKEN = "broken"


@dataclass(frozen=True, slots=True)
class LifecycleIntent:
    kind: LifecycleIntentKind
    desired: DesiredState
    previous: DesiredState | None = None
    ownership: tuple[OwnershipReason, ...] = ()
    retained_ownership: tuple[OwnershipReason, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, LifecycleIntentKind) or not isinstance(
            self.desired, DesiredState
        ):
            raise ValueError("lifecycle intent is invalid")
        if self.previous is not None and not isinstance(self.previous, DesiredState):
            raise ValueError("lifecycle previous desired state is invalid")
        if self.previous is not None and (
            self.previous.artifact.source != self.desired.artifact.source
            or self.previous.artifact.artifact != self.desired.artifact.artifact
        ):
            raise ValueError("lifecycle intent cannot change artifact identity or source")
        for values, label in (
            (self.ownership, "ownership"),
            (self.retained_ownership, "retained ownership"),
        ):
            if any(not isinstance(item, OwnershipReason) for item in values):
                raise ValueError(f"lifecycle {label} is invalid")
            ordered = tuple(sorted(set(values), key=lambda item: item.sort_key))
            object.__setattr__(self, label.replace(" ", "_"), ordered)
        if not set(self.retained_ownership).issubset(self.ownership):
            raise ValueError("retained ownership must have existed before the intent")

    @property
    def retained(self) -> bool:
        return self.kind is LifecycleIntentKind.UNINSTALL and bool(self.retained_ownership)

    @property
    def establishes_ownership(self) -> bool:
        """Whether this action decides who wants the artifact, or only what state it is in.

        A repair, a reconfiguration and a credential rotation are about the machine. They carry no
        ownership because they have no opinion about it, and reading that silence as "nobody wants
        this" would let fixing a launcher release a Collection's claim on the artifact.
        """

        return self.kind in _OWNERSHIP_INTENTS

    @property
    def resulting_ownership(self) -> tuple[OwnershipReason, ...]:
        """Who owns the artifact once this action has run."""

        if self.kind is LifecycleIntentKind.UNINSTALL:
            return self.retained_ownership
        return self.ownership


@dataclass(frozen=True, slots=True)
class LifecyclePlan:
    intent: LifecycleIntent
    repair: RepairPlan

    def __post_init__(self) -> None:
        if not isinstance(self.intent, LifecycleIntent) or not isinstance(self.repair, RepairPlan):
            raise ValueError("lifecycle plan is invalid")
        if self.intent.desired.artifact != self.repair.artifact:
            raise ValueError("lifecycle plan and intent name different artifacts")

    @property
    def review_digest(self) -> ObjectDigest:
        return self.repair.review_digest


@dataclass(frozen=True, slots=True)
class MemberHealth:
    artifact: str
    health: InstalledHealth

    def __post_init__(self) -> None:
        if (
            not isinstance(self.artifact, str)
            or not self.artifact
            or any(character in self.artifact for character in "\r\n")
            or not isinstance(self.health, InstalledHealth)
        ):
            raise ValueError("member health is invalid")


@dataclass(frozen=True, slots=True)
class CollectionHealth:
    status: InstalledHealth
    members: tuple[MemberHealth, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.status, InstalledHealth)
            or not self.members
            or any(not isinstance(item, MemberHealth) for item in self.members)
            or len({item.artifact for item in self.members}) != len(self.members)
        ):
            raise ValueError("collection health is invalid")

    @property
    def members_requiring_attention(self) -> tuple[MemberHealth, ...]:
        return tuple(
            member
            for member in self.members
            if member.health in (InstalledHealth.ATTENTION, InstalledHealth.BROKEN)
        )


#: The intents that speak to who wants an artifact. The rest change only what is true of it.
_OWNERSHIP_INTENTS = frozenset(
    {
        LifecycleIntentKind.INSTALL,
        LifecycleIntentKind.UPDATE,
        LifecycleIntentKind.DOWNGRADE,
        LifecycleIntentKind.UNINSTALL,
    }
)


def _same_identity(previous: DesiredState, desired: DesiredState) -> None:
    before, after = previous.artifact, desired.artifact
    if before.source != after.source or before.artifact != after.artifact:
        raise ValueError("a lifecycle transition cannot change artifact identity or source")


def _versions(previous: DesiredState, desired: DesiredState) -> tuple[SemVer, SemVer]:
    _same_identity(previous, desired)
    if previous.artifact.version is None or desired.artifact.version is None:
        raise ValueError("version transitions need exact versions")
    before = parse_semver(previous.artifact.version)
    after = parse_semver(desired.artifact.version)
    if isinstance(before, Err) or isinstance(after, Err):
        raise ValueError("version transitions need valid semantic versions")
    return before.value, after.value


def _replace_components(
    previous: DesiredState,
    replacements: tuple[DesiredComponent, ...],
    *,
    allowed: frozenset[Component],
) -> DesiredState:
    if not replacements:
        raise ValueError("a component-specific intent needs at least one replacement")
    if any(item.id.component not in allowed for item in replacements):
        raise ValueError("intent replacement contains an unrelated component")
    by_id = {item.id: item for item in previous.components}
    for replacement in replacements:
        by_id[replacement.id] = replacement
    return DesiredState(previous.artifact, tuple(by_id.values()))


def install_intent(
    desired: DesiredState, *, ownership: tuple[OwnershipReason, ...] = ()
) -> LifecycleIntent:
    return LifecycleIntent(LifecycleIntentKind.INSTALL, desired, None, ownership)


def repair_intent(desired: DesiredState) -> LifecycleIntent:
    return LifecycleIntent(LifecycleIntentKind.REPAIR, desired, desired)


def configure_intent(
    previous: DesiredState, replacements: tuple[DesiredComponent, ...]
) -> LifecycleIntent:
    desired = _replace_components(
        previous,
        replacements,
        allowed=frozenset({Component.CONFIGURATION, Component.LAUNCHER}),
    )
    return LifecycleIntent(LifecycleIntentKind.CONFIGURE, desired, previous)


def credential_rotation_intent(
    previous: DesiredState, replacements: tuple[DesiredComponent, ...]
) -> LifecycleIntent:
    desired = _replace_components(previous, replacements, allowed=frozenset({Component.CREDENTIAL}))
    return LifecycleIntent(LifecycleIntentKind.CREDENTIAL_ROTATION, desired, previous)


def harness_reconfiguration_intent(
    previous: DesiredState, replacements: tuple[DesiredComponent, ...]
) -> LifecycleIntent:
    desired = _replace_components(previous, replacements, allowed=frozenset({Component.HARNESS}))
    return LifecycleIntent(LifecycleIntentKind.HARNESS_RECONFIGURATION, desired, previous)


def update_intent(
    previous: DesiredState,
    desired: DesiredState,
    *,
    ownership: tuple[OwnershipReason, ...] = (),
) -> LifecycleIntent:
    before, after = _versions(previous, desired)
    if not before < after:
        raise ValueError("an update must select a newer version")
    return LifecycleIntent(LifecycleIntentKind.UPDATE, desired, previous, ownership)


def downgrade_intent(
    previous: DesiredState,
    desired: DesiredState,
    *,
    ownership: tuple[OwnershipReason, ...] = (),
) -> LifecycleIntent:
    before, after = _versions(previous, desired)
    if not after < before:
        raise ValueError("a downgrade must select an older version")
    return LifecycleIntent(LifecycleIntentKind.DOWNGRADE, desired, previous, ownership)


def uninstall_intent(
    previous: DesiredState,
    removal: DesiredState,
    *,
    ownership: tuple[OwnershipReason, ...] = (),
    release: tuple[OwnershipReason, ...] = (),
) -> LifecycleIntent:
    _same_identity(previous, removal)
    owned = tuple(sorted(set(ownership), key=lambda item: item.sort_key))
    released = set(release or owned)
    if not released.issubset(owned):
        raise ValueError("cannot release ownership the installation does not have")
    retained = tuple(item for item in owned if item not in released)
    desired = previous if retained else removal
    return LifecycleIntent(
        LifecycleIntentKind.UNINSTALL,
        desired,
        previous,
        owned,
        retained,
    )


def plan_lifecycle_intent(
    intent: LifecycleIntent,
    current: CurrentState,
    *,
    policy: EffectivePolicy,
) -> Result[LifecyclePlan]:
    if not isinstance(intent, LifecycleIntent):
        raise ValueError("lifecycle planning needs an intent")
    planned = plan_repair(intent.desired, current, policy=policy)
    if isinstance(planned, Err):
        return planned
    return Ok(LifecyclePlan(intent, planned.value))


def installation_health(
    desired: DesiredState,
    current: CurrentState,
    *,
    update_available: bool = False,
) -> InstalledHealth:
    drift = compare_states(desired, current)
    if not drift:
        return InstalledHealth.UPDATE if update_available else InstalledHealth.READY
    critical = {
        Component.PAYLOAD,
        Component.RUNTIME_ENVIRONMENT,
        Component.RUNTIME_DEPENDENCIES,
        Component.LAUNCHER,
    }
    if any(
        (
            item.component.component in critical
            and item.kind not in (DriftKind.UNOBSERVED, DriftKind.UNVERIFIABLE)
        )
        or not item.repairable
        for item in drift
    ):
        return InstalledHealth.BROKEN
    return InstalledHealth.ATTENTION


def collection_health(members: tuple[MemberHealth, ...]) -> CollectionHealth:
    if not members or len({item.artifact for item in members}) != len(members):
        raise ValueError("collection health needs unique members")
    ordered = tuple(sorted(members, key=lambda item: item.artifact))
    # An unmeasured member outranks a healthy one -- the Collection cannot be called ready when
    # part of it was never looked at -- but a measured problem outranks it in turn, because that
    # is the one somebody can act on.
    rank = {
        InstalledHealth.READY: 0,
        InstalledHealth.UPDATE: 1,
        InstalledHealth.UNKNOWN: 2,
        InstalledHealth.ATTENTION: 3,
        InstalledHealth.BROKEN: 4,
    }
    status = max((item.health for item in ordered), key=rank.__getitem__)
    return CollectionHealth(status, ordered)
