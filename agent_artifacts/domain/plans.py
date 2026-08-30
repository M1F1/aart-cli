"""Canonical immutable planning values shared by human and machine projections."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import cast

from .effects import Effect, RiskClass, effect_to_data
from .identifiers import ArtifactCoordinate, ObjectDigest
from .remediations import Remediation, remediation_to_data
from .requirements import Requirement, RequirementState, requirement_to_data
from .selection import ResolvedSelection, artifact_coordinate_sort_key
from .serialization import CanonicalValue, canonical_json_bytes


def _canonical(value: object) -> bytes:
    return canonical_json_bytes(cast(CanonicalValue, value))


def _requirement_key(requirement: Requirement) -> bytes:
    return _canonical(requirement_to_data(requirement))


def _remediation_key(remediation: Remediation) -> bytes:
    return _canonical(remediation_to_data(remediation))


def _effect_key(effect: Effect) -> bytes:
    return _canonical(effect_to_data(effect))


def _owners(
    values: tuple[ArtifactCoordinate, ...],
    label: str,
) -> tuple[ArtifactCoordinate, ...]:
    if not values or any(not isinstance(item, ArtifactCoordinate) for item in values):
        raise ValueError(f"{label} requires artifact owners")
    return tuple(sorted(set(values), key=artifact_coordinate_sort_key))


@dataclass(frozen=True, slots=True)
class OwnedRequirement:
    requirement: Requirement
    owners: tuple[ArtifactCoordinate, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "owners", _owners(self.owners, "owned requirement"))

    @property
    def sort_key(self) -> bytes:
        return _requirement_key(self.requirement)


@dataclass(frozen=True, slots=True)
class OwnedAssessment:
    requirement: OwnedRequirement
    state: RequirementState
    detail: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.requirement, OwnedRequirement)
            or not isinstance(self.state, RequirementState)
            or not isinstance(self.detail, str)
            or any(character in self.detail for character in "\r\n")
        ):
            raise ValueError("owned requirement assessment is invalid")

    @property
    def sort_key(self) -> bytes:
        return self.requirement.sort_key


@dataclass(frozen=True, slots=True)
class PlannedRemediation:
    remediation: Remediation
    owners: tuple[ArtifactCoordinate, ...]
    risk: RiskClass

    def __post_init__(self) -> None:
        object.__setattr__(self, "owners", _owners(self.owners, "planned remediation"))
        if not isinstance(self.risk, RiskClass):
            raise ValueError("planned remediation risk is invalid")

    @property
    def sort_key(self) -> bytes:
        return _remediation_key(self.remediation)


@dataclass(frozen=True, slots=True)
class PlannedEffect:
    effect: Effect
    owners: tuple[ArtifactCoordinate, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "owners", _owners(self.owners, "planned effect"))

    @property
    def sort_key(self) -> bytes:
        return _effect_key(self.effect)


@dataclass(frozen=True, slots=True)
class MutationPlan:
    effects: tuple[PlannedEffect, ...]
    risks: tuple[RiskClass, ...]

    def __post_init__(self) -> None:
        if any(not isinstance(item, PlannedEffect) for item in self.effects) or any(
            not isinstance(item, RiskClass) for item in self.risks
        ):
            raise ValueError("mutation plan is invalid")
        effects = tuple(sorted(self.effects, key=lambda item: item.sort_key))
        risks = tuple(sorted(set(self.risks)))
        if any(effect.effect.risk not in risks for effect in effects):
            raise ValueError("mutation plan risk summary is incomplete")
        object.__setattr__(self, "effects", effects)
        object.__setattr__(self, "risks", risks)


@dataclass(frozen=True, slots=True)
class InstallPlan:
    selection: ResolvedSelection
    platform: str
    requirements: tuple[OwnedAssessment, ...]
    remediations: tuple[PlannedRemediation, ...]
    mutation: MutationPlan
    policy_digest: ObjectDigest
    review_digest: ObjectDigest = field(init=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.selection, ResolvedSelection)
            or not isinstance(self.platform, str)
            or not self.platform
            or self.platform != self.platform.strip()
            or any(character in self.platform for character in "\r\n")
            or any(not isinstance(item, OwnedAssessment) for item in self.requirements)
            or any(not isinstance(item, PlannedRemediation) for item in self.remediations)
            or not isinstance(self.mutation, MutationPlan)
            or not isinstance(self.policy_digest, ObjectDigest)
        ):
            raise ValueError("canonical install plan is invalid")
        requirements = tuple(sorted(self.requirements, key=lambda item: item.sort_key))
        remediations = tuple(sorted(self.remediations, key=lambda item: item.sort_key))
        object.__setattr__(self, "requirements", requirements)
        object.__setattr__(self, "remediations", remediations)
        digest = hashlib.sha256(_canonical(install_plan_to_data(self, review=False)))
        object.__setattr__(self, "review_digest", ObjectDigest("sha256", digest.hexdigest()))


def _coordinate_data(coordinate: ArtifactCoordinate) -> dict[str, object]:
    return {
        "artifact": {
            "kind": coordinate.artifact.kind,
            "name": coordinate.artifact.name,
        },
        "source": coordinate.source.value,
        "version": coordinate.version,
    }


def _selection_data(selection: ResolvedSelection) -> dict[str, object]:
    return {
        "artifacts": [
            {
                "coordinate": _coordinate_data(item.version.coordinate),
                "canonical_digest": str(item.version.canonical_digest),
                "dependencies": [_coordinate_data(dependency) for dependency in item.dependencies],
                "lifecycle": item.version.lifecycle.value,
                "mode": item.version.mode.value,
                "ownership": [
                    {"kind": reason.kind.value, "owner": reason.owner} for reason in item.ownership
                ],
                "payload_digest": str(item.version.payload_digest),
                "publication": item.version.publication.value,
                "registry_snapshot": str(item.version.registry_snapshot),
            }
            for item in selection.artifacts
        ],
        "intent": {
            "artifacts": [str(item) for item in selection.selection.artifacts],
            "collections": [str(item) for item in selection.selection.collections],
            "derived_from": [str(item) for item in selection.selection.derived_from],
        },
    }


def _owned_requirement_data(requirement: OwnedRequirement) -> dict[str, object]:
    return {
        "owners": [_coordinate_data(owner) for owner in requirement.owners],
        "requirement": requirement_to_data(requirement.requirement),
    }


def install_plan_to_data(plan: InstallPlan, *, review: bool = True) -> dict[str, object]:
    data: dict[str, object] = {
        "mutation": {
            "effects": [
                {
                    "effect": effect_to_data(item.effect),
                    "owners": [_coordinate_data(owner) for owner in item.owners],
                }
                for item in plan.mutation.effects
            ],
            "risks": [risk.name.lower().replace("_", "-") for risk in plan.mutation.risks],
        },
        "platform": plan.platform,
        "policy_digest": str(plan.policy_digest),
        "remediations": [
            {
                "owners": [_coordinate_data(owner) for owner in item.owners],
                "remediation": remediation_to_data(item.remediation),
                "risk": item.risk.name.lower().replace("_", "-"),
            }
            for item in plan.remediations
        ],
        "requirements": [
            {
                **_owned_requirement_data(item.requirement),
                "detail": item.detail,
                "state": item.state.value,
            }
            for item in plan.requirements
        ],
        "selection": _selection_data(plan.selection),
    }
    if review:
        data["review_digest"] = str(plan.review_digest)
    return data
