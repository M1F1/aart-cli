"""Comparing a receipt against what is actually on disk, without deciding what to do about it.

Verification answers one question -- is what was installed still what is there -- and answers it in
findings a later slice can turn into repairs. It is pure: an observation is gathered by an
interpreter and handed in, so the same comparison runs against a real machine, a fixture, or a
hypothetical state nobody has built yet.

Findings are named, not phrased. "The launcher changed" and "the harness points somewhere else" are
different repairs, and a reconciler that only received prose would have to parse it back.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agent_artifacts.domain.identifiers import ObjectDigest
from agent_artifacts.domain.receipts import InstallationReceipt

__all__ = [
    "DeliveryObservation",
    "InstallationObservation",
    "PlacementObservation",
    "VerificationFinding",
    "installation_verified",
    "verify_installation",
]


class VerificationFinding(str, Enum):
    """One way an installation stopped matching its receipt."""

    LAUNCHER_MISSING = "launcher-missing"
    LAUNCHER_NOT_EXECUTABLE = "launcher-not-executable"
    LAUNCHER_CHANGED = "launcher-changed"
    INTERPRETER_MISSING = "interpreter-missing"
    HARNESS_NOT_REGISTERED = "harness-not-registered"
    HARNESS_POINTS_ELSEWHERE = "harness-points-elsewhere"


@dataclass(frozen=True, slots=True)
class DeliveryObservation:
    """What was found where one harness reads this artifact. Facts only.

    `present` without a `digest` is the case worth naming: something is there and nobody could
    measure it. That is not the same fact as nothing being there, and collapsing the two would
    plan a delivery over a file somebody may have been editing.
    """

    harness: str
    present: bool = False
    digest: ObjectDigest | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.harness, str) or not self.harness.strip():
            raise ValueError("an observed delivery names the harness that reads it")
        if not isinstance(self.present, bool):
            raise ValueError("observed delivery presence is invalid")
        if self.digest is not None and not isinstance(self.digest, ObjectDigest):
            raise ValueError("observed delivery digest is invalid")
        if self.digest is not None and not self.present:
            raise ValueError("a delivery that is not there cannot have been measured")


@dataclass(frozen=True, slots=True)
class PlacementObservation:
    """What an inspector found for an artifact a harness reads. Facts only."""

    payload_present: bool = False
    deliveries: tuple[DeliveryObservation, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.payload_present, bool):
            raise ValueError("observed placement payload presence is invalid")
        if not isinstance(self.deliveries, tuple) or any(
            not isinstance(item, DeliveryObservation) for item in self.deliveries
        ):
            raise ValueError("observed deliveries are invalid")
        harnesses = [item.harness for item in self.deliveries]
        if len(set(harnesses)) != len(harnesses):
            raise ValueError("one harness reads one delivery of an artifact")


@dataclass(frozen=True, slots=True)
class InstallationObservation:
    """What an interpreter found. Facts only -- no comparison has happened yet."""

    payload_present: bool = False
    launcher_present: bool = False
    launcher_executable: bool = False
    launcher_digest: ObjectDigest | None = None
    interpreter_present: bool = False
    registered_commands: tuple[tuple[str, str, str | None], ...] = ()

    def __post_init__(self) -> None:
        for value, label in (
            (self.payload_present, "installed payload presence"),
            (self.launcher_present, "launcher presence"),
            (self.launcher_executable, "launcher executability"),
            (self.interpreter_present, "interpreter presence"),
        ):
            if not isinstance(value, bool):
                raise ValueError(f"observed {label} is invalid")
        if self.launcher_digest is not None and not isinstance(self.launcher_digest, ObjectDigest):
            raise ValueError("observed launcher digest is invalid")
        if not isinstance(self.registered_commands, tuple) or any(
            not isinstance(item, tuple)
            or len(item) != 3
            or not isinstance(item[0], str)
            or not isinstance(item[1], str)
            or not (item[2] is None or isinstance(item[2], str))
            for item in self.registered_commands
        ):
            raise ValueError("observed harness registrations are invalid")

    def command_for(self, harness: str, server: str) -> str | None:
        for observed_harness, observed_server, command in self.registered_commands:
            if observed_harness == harness and observed_server == server:
                return command
        return None


def verify_installation(
    receipt: InstallationReceipt,
    observation: InstallationObservation,
) -> tuple[VerificationFinding, ...]:
    """Every way `observation` differs from `receipt`, in a stable order."""

    if not isinstance(receipt, InstallationReceipt) or not isinstance(
        observation, InstallationObservation
    ):
        raise ValueError("verification needs a receipt and an observation")

    findings: list[VerificationFinding] = []
    if not observation.launcher_present:
        findings.append(VerificationFinding.LAUNCHER_MISSING)
    else:
        if not observation.launcher_executable:
            findings.append(VerificationFinding.LAUNCHER_NOT_EXECUTABLE)
        # A missing digest is not a match. Verification that passes when nothing could be
        # measured is a report that the measurement did not happen.
        if observation.launcher_digest is None or str(observation.launcher_digest) != str(
            receipt.launcher_digest
        ):
            findings.append(VerificationFinding.LAUNCHER_CHANGED)
    if not observation.interpreter_present:
        findings.append(VerificationFinding.INTERPRETER_MISSING)

    for registration in receipt.registrations:
        command = observation.command_for(registration.target.harness, registration.server)
        if command is None:
            findings.append(VerificationFinding.HARNESS_NOT_REGISTERED)
        elif command != registration.command:
            findings.append(VerificationFinding.HARNESS_POINTS_ELSEWHERE)

    ordered = sorted(set(findings), key=lambda finding: tuple(VerificationFinding).index(finding))
    return tuple(ordered)


def installation_verified(
    receipt: InstallationReceipt,
    observation: InstallationObservation,
) -> bool:
    return not verify_installation(receipt, observation)
