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

from agent_artifacts.domain.hooks import hook_entry_fingerprint
from agent_artifacts.domain.identifiers import ObjectDigest
from agent_artifacts.domain.receipts import InstallationReceipt
from agent_artifacts.protocol.hashing import sha256_bytes

__all__ = [
    "DeliveryObservation",
    "InstallationObservation",
    "MergeObservation",
    "PlacementObservation",
    "SettingsObservation",
    "VerificationFinding",
    "installation_verified",
    "settings_entry_digest",
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
class MergeObservation:
    """What one region of a shared file says now. Facts only.

    Distinct from a delivery observation because absent means something narrower: the file may be
    full of the user's own writing and simply not contain this artifact's region. `present` is about
    the region, never about the file.
    """

    harness: str
    present: bool = False
    digest: ObjectDigest | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.harness, str) or not self.harness.strip():
            raise ValueError("an observed merge names the harness that reads it")
        if not isinstance(self.present, bool):
            raise ValueError("observed merge presence is invalid")
        if self.digest is not None and not isinstance(self.digest, ObjectDigest):
            raise ValueError("observed merge digest is invalid")
        if self.digest is not None and not self.present:
            raise ValueError("a region that is not there cannot have been measured")


def settings_entry_digest(entry: object) -> ObjectDigest:
    """How a settings entry is compared, whether it came off a disk or out of a receipt.

    One construction for both sides on purpose. Two would be free to disagree about whitespace or
    key order, and a hook that reads as drift every time it is looked at is a repair that never
    converges.
    """

    return sha256_bytes(hook_entry_fingerprint(entry).encode("utf-8"))


@dataclass(frozen=True, slots=True)
class SettingsObservation:
    """Whether this artifact's entry is in the harness's settings, and how it is spelled now.

    Absent means narrower again than a merge's: the list may be full of other hooks and simply not
    contain this one. `present` is about the entry, never about the file or the list.
    """

    harness: str
    present: bool = False
    digest: ObjectDigest | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.harness, str) or not self.harness.strip():
            raise ValueError("an observed settings entry names the harness that reads it")
        if not isinstance(self.present, bool):
            raise ValueError("observed settings entry presence is invalid")
        if self.digest is not None and not isinstance(self.digest, ObjectDigest):
            raise ValueError("observed settings entry digest is invalid")
        if self.digest is not None and not self.present:
            raise ValueError("an entry that is not there cannot have been measured")


@dataclass(frozen=True, slots=True)
class PlacementObservation:
    """What an inspector found for an artifact a harness reads. Facts only."""

    payload_present: bool = False
    #: What the payload tree hashes to now, or `None` when nobody could measure it. Absent for a
    #: payload that is not there at all, which `payload_present` already says.
    payload_digest: ObjectDigest | None = None
    deliveries: tuple[DeliveryObservation, ...] = ()
    merges: tuple[MergeObservation, ...] = ()
    settings: tuple[SettingsObservation, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.payload_present, bool):
            raise ValueError("observed placement payload presence is invalid")
        if self.payload_digest is not None and not isinstance(self.payload_digest, ObjectDigest):
            raise ValueError("observed placement payload digest is invalid")
        if self.payload_digest is not None and not self.payload_present:
            raise ValueError("a payload that is not there cannot have been measured")
        if not isinstance(self.deliveries, tuple) or any(
            not isinstance(item, DeliveryObservation) for item in self.deliveries
        ):
            raise ValueError("observed deliveries are invalid")
        if not isinstance(self.merges, tuple) or any(
            not isinstance(item, MergeObservation) for item in self.merges
        ):
            raise ValueError("observed merges are invalid")
        if not isinstance(self.settings, tuple) or any(
            not isinstance(item, SettingsObservation) for item in self.settings
        ):
            raise ValueError("observed settings entries are invalid")
        for items, label in (
            (self.deliveries, "delivery"),
            (self.merges, "merge"),
            (self.settings, "settings entry"),
        ):
            harnesses = [item.harness for item in items]
            if len(set(harnesses)) != len(harnesses):
                raise ValueError(f"one harness reads one {label} of an artifact")


@dataclass(frozen=True, slots=True)
class InstallationObservation:
    """What an interpreter found. Facts only -- no comparison has happened yet."""

    #: Tri-state on purpose. `False` is "the tree is gone", `None` is "nobody looked" -- D-029,
    #: and the reason this is not a plain bool: a caller assembling a partial observation would
    #: otherwise report every payload it did not measure as deleted.
    payload_present: bool | None = None
    launcher_present: bool = False
    launcher_executable: bool = False
    launcher_digest: ObjectDigest | None = None
    interpreter_present: bool = False
    registered_commands: tuple[tuple[str, str, str | None], ...] = ()

    def __post_init__(self) -> None:
        if self.payload_present is not None and not isinstance(self.payload_present, bool):
            raise ValueError("observed installed payload presence is invalid")
        for value, label in (
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
