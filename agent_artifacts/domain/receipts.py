"""What one installation left behind, recorded so a later run can tell it is still true.

A receipt is evidence, not a log. It records identity and digests: where the launcher is and what
it contains, which interpreter it runs, which credential references it will resolve, and which
harnesses were told about it. From that a reconciler can decide what drifted without re-reading
anything it should not.

Config values are recorded by digest rather than in full. They are not secret -- the launcher holds
them in the open -- but a policy may forbid persisting a particular one, and a digest detects drift
just as well as a copy does while leaving that policy nothing to be violated by.

There are two records here because there are two kinds of installation, and INV-010 keeps semantic
kind separate from runtime protocol. `InstallationReceipt` describes an artifact a harness starts:
it has a launcher, an interpreter and a transport. `PlacedArtifactReceipt` describes one a harness
reads -- a Skill, a guideline, a hook, a memory -- which has none of those and is installed by being
delivered where the harness looks. They are separate types rather than one type with optional
halves, so an MCP receipt cannot lose its launcher without something noticing, and a Skill has no
launcher field to leave empty.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TypeAlias

from .credentials import CredentialProviderRef, CredentialReference
from .diagnostics import Diagnostic, DiagnosticCode, Severity
from .effects import DeliveryKind
from .harness import McpRegistration, registration_from_data, registration_to_data
from .hooks import HookEntry, HookEntryShape
from .identifiers import ArtifactCoordinate, InputId, ObjectDigest
from .launch import Transport
from .managed_blocks import is_block_name
from .result import Err, Ok, Result
from .selection import OwnershipKind, OwnershipReason

__all__ = [
    "RECEIPT_INVALID",
    "ArtifactDelivery",
    "ArtifactMerge",
    "ArtifactReceipt",
    "ArtifactSettingsEntry",
    "ConfigFingerprint",
    "DeliveryKind",
    "InstallationReceipt",
    "InstalledRecord",
    "PlacedArtifactReceipt",
    "config_fingerprint",
    "installation_receipt_from_data",
    "installation_receipt_to_data",
    "placed_artifact_receipt_from_data",
    "placed_artifact_receipt_to_data",
]

RECEIPT_INVALID = DiagnosticCode("receipt-invalid")


def config_fingerprint(input_id: InputId, value: str) -> "ConfigFingerprint":
    """Fingerprint one bound config value. The input id is folded in, so the same value under two
    names does not produce one digest that either could claim."""

    if not isinstance(input_id, InputId) or not isinstance(value, str):
        raise ValueError("a config fingerprint needs an input id and a value")
    digest = hashlib.sha256()
    digest.update(input_id.value.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(value.encode("utf-8"))
    return ConfigFingerprint(input_id, ObjectDigest("sha256", digest.hexdigest()))


@dataclass(frozen=True, slots=True)
class ConfigFingerprint:
    input: InputId
    digest: ObjectDigest

    def __post_init__(self) -> None:
        if not isinstance(self.input, InputId) or not isinstance(self.digest, ObjectDigest):
            raise ValueError("config fingerprint is invalid")


@dataclass(frozen=True, slots=True)
class InstallationReceipt:
    """One installed artifact, as it stood when the effects finished."""

    artifact: str
    root: str
    launcher: str
    launcher_digest: ObjectDigest
    interpreter: str
    transport: Transport = Transport.STDIO
    registrations: tuple[McpRegistration, ...] = ()
    credentials: tuple[CredentialReference, ...] = ()
    config: tuple[ConfigFingerprint, ...] = ()
    base_interpreter: str | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.artifact, "artifact"),
            (self.root, "root"),
            (self.launcher, "launcher"),
            (self.interpreter, "interpreter"),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"installation receipt {label} is invalid")
        for path, label in ((self.root, "root"), (self.launcher, "launcher")):
            if not path.startswith("/"):
                raise ValueError(f"installation receipt {label} must be absolute")
        if self.base_interpreter is not None and (
            not isinstance(self.base_interpreter, str)
            or not self.base_interpreter.startswith("/")
            or any(character in self.base_interpreter for character in "\r\n")
        ):
            raise ValueError("installation receipt base interpreter must be an absolute path")
        if not self.launcher.startswith(f"{self.root}/"):
            raise ValueError("a receipt's launcher belongs to the root it records")
        if not isinstance(self.launcher_digest, ObjectDigest) or not isinstance(
            self.transport, Transport
        ):
            raise ValueError("installation receipt digest or transport is invalid")
        for items, kind, label in (
            (self.registrations, McpRegistration, "registrations"),
            (self.credentials, CredentialReference, "credentials"),
            (self.config, ConfigFingerprint, "config"),
        ):
            if not isinstance(items, tuple) or any(not isinstance(item, kind) for item in items):
                raise ValueError(f"installation receipt {label} are invalid")
        object.__setattr__(
            self,
            "registrations",
            tuple(sorted(self.registrations, key=lambda item: (item.target.harness, item.server))),
        )
        object.__setattr__(self, "credentials", tuple(sorted(set(self.credentials))))
        object.__setattr__(
            self, "config", tuple(sorted(self.config, key=lambda item: item.input.value))
        )


def installation_receipt_to_data(receipt: InstallationReceipt) -> dict[str, object]:
    return {
        "artifact": receipt.artifact,
        "base_interpreter": receipt.base_interpreter,
        "config": [
            {"digest": str(item.digest), "input": item.input.value} for item in receipt.config
        ],
        # Structural, not the joined string alone: a service or account may itself contain the
        # separators, so a document that only carried `str(reference)` could not be read back.
        "credentials": [
            {
                "account": reference.provider.account,
                "input": reference.input.value,
                "provider": reference.provider.provider,
                "reference": str(reference),
                "service": reference.provider.service,
            }
            for reference in receipt.credentials
        ],
        "interpreter": receipt.interpreter,
        "launcher": receipt.launcher,
        "launcher_digest": str(receipt.launcher_digest),
        "registrations": [registration_to_data(item) for item in receipt.registrations],
        "root": receipt.root,
        "transport": receipt.transport.value,
    }


@dataclass(frozen=True, slots=True)
class ArtifactDelivery:
    """Where one harness reads one installed artifact from, and what was put there.

    This is the counterpart of an MCP registration for a kind that starts nothing.  A registration
    tells a harness a command to run; a delivery is the harness reading a path.  Both are the same
    statement -- this harness now knows about this artifact -- and both carry a digest, so a later
    reconciler can tell "still there and unchanged" from "still there".
    """

    harness: str
    source: str
    destination: str
    kind: DeliveryKind
    digest: ObjectDigest

    def __post_init__(self) -> None:
        if not isinstance(self.harness, str) or not self.harness.strip():
            raise ValueError("a delivery names the harness that reads it")
        for value, label in ((self.source, "source"), (self.destination, "destination")):
            if (
                not isinstance(value, str)
                or not value.startswith("/")
                or any(character in value for character in "\r\n")
            ):
                # Absolute, because the harness resolves the destination from a working directory
                # nobody here controls -- the same rule a registration's command follows -- and
                # because a relative source would be resolved against whatever happened to be the
                # working directory of the run that repaired it.
                raise ValueError(f"a delivery {label} must be one absolute path")
        if not isinstance(self.kind, DeliveryKind) or not isinstance(self.digest, ObjectDigest):
            raise ValueError("delivery kind or digest is invalid")


@dataclass(frozen=True, slots=True)
class ArtifactMerge:
    """One region of a file somebody else owns that this artifact writes into, and what it says.

    A delivery and a merge are both a harness reading an artifact, but they are not the same
    statement about the destination. A delivery owns its path outright; a merge owns a delimited
    region of a file the user writes in, which is why it records the region by name and digests the
    block rather than the file. Digesting the file would report every edit the user made to their
    own notes as drift in the artifact.
    """

    harness: str
    source: str
    destination: str
    region: str
    digest: ObjectDigest

    def __post_init__(self) -> None:
        if not isinstance(self.harness, str) or not self.harness.strip():
            raise ValueError("a merge names the harness that reads it")
        for value, label in ((self.source, "source"), (self.destination, "destination")):
            if (
                not isinstance(value, str)
                or not value.startswith("/")
                or any(character in value for character in "\r\n")
            ):
                raise ValueError(f"a merge {label} must be one absolute path")
        if not is_block_name(self.region):
            raise ValueError("a merge names the region of the file it owns")
        if not isinstance(self.digest, ObjectDigest):
            raise ValueError("merge digest is invalid")


@dataclass(frozen=True, slots=True)
class ArtifactSettingsEntry:
    """One entry this artifact owns inside a list in a settings file the harness reads.

    The half of a hook a delivery cannot record. There is no digest here because there is nothing
    to digest against: the entry itself is what was written, so drift is the file disagreeing with
    this record rather than with a hash of it. `path` is where the harness reads the list from,
    which differs between builds for the same event and so is recorded rather than recomputed.
    """

    harness: str
    destination: str
    path: str
    entry: HookEntry

    def __post_init__(self) -> None:
        if not isinstance(self.harness, str) or not self.harness.strip():
            raise ValueError("a settings entry names the harness that reads it")
        if (
            not isinstance(self.destination, str)
            or not self.destination.startswith("/")
            or any(character in self.destination for character in "\r\n")
        ):
            raise ValueError("a settings entry destination must be one absolute path")
        if (
            not isinstance(self.path, str)
            or not self.path
            or any(not part or part.strip() != part for part in self.path.split("."))
        ):
            raise ValueError("a settings entry path is dotted, non-empty and untrimmed")
        if not isinstance(self.entry, HookEntry):
            raise ValueError("a settings entry records the hook it wrote")


@dataclass(frozen=True, slots=True)
class PlacedArtifactReceipt:
    """One installed artifact that a harness reads rather than starts.

    INV-010 keeps semantic kind separate from runtime protocol, and this is where that separation
    becomes structural: there is no launcher field to leave empty, no interpreter to invent and no
    transport to default.  A Skill has none of those, and a receipt that carried them anyway would
    have a later reconciler looking for a process nobody installed and reporting its absence as
    drift.
    """

    artifact: str
    root: str
    payload_digest: ObjectDigest
    deliveries: tuple[ArtifactDelivery, ...] = ()
    config: tuple[ConfigFingerprint, ...] = ()
    merges: tuple[ArtifactMerge, ...] = ()
    settings: tuple[ArtifactSettingsEntry, ...] = ()

    def __post_init__(self) -> None:
        for value, label in ((self.artifact, "artifact"), (self.root, "root")):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"placed artifact receipt {label} is invalid")
        if not self.root.startswith("/"):
            raise ValueError("placed artifact receipt root must be absolute")
        if not isinstance(self.payload_digest, ObjectDigest):
            raise ValueError("placed artifact receipt payload digest is invalid")
        for items, kind, label in (
            (self.deliveries, ArtifactDelivery, "deliveries"),
            (self.config, ConfigFingerprint, "config"),
            (self.merges, ArtifactMerge, "merges"),
            (self.settings, ArtifactSettingsEntry, "settings"),
        ):
            if not isinstance(items, tuple) or any(not isinstance(item, kind) for item in items):
                raise ValueError(f"placed artifact receipt {label} are invalid")
        if not self.deliveries and not self.merges and not self.settings:
            # Placed in its own tree and read by nobody is a download, not an installation, and
            # recording it as one would let `status` report an artifact nothing can reach.
            raise ValueError("a placed artifact is read by at least one harness")
        destinations = [item.destination for item in self.deliveries]
        if len(set(destinations)) != len(destinations):
            raise ValueError("two deliveries cannot write the same destination")
        regions = [(item.destination, item.region) for item in self.merges]
        if len(set(regions)) != len(regions):
            raise ValueError("two merges cannot own the same region of the same file")
        shared: tuple[ArtifactMerge | ArtifactSettingsEntry, ...] = (*self.merges, *self.settings)
        if set(destinations) & {item.destination for item in shared}:
            # One of them replaces the destination and the others preserve it. Whichever ran
            # second would undo the first.
            raise ValueError("a destination is either delivered or merged into, not both")
        entries = [(item.destination, item.path, item.entry) for item in self.settings]
        if len(set(entries)) != len(entries):
            raise ValueError("two settings entries cannot own the same entry of the same list")
        sources: tuple[ArtifactDelivery | ArtifactMerge, ...] = (*self.deliveries, *self.merges)
        for item in sources:
            if not _within(self.root, item.source):
                # Re-delivery copies from the artifact's own tree. A source outside it would let
                # a repair place content this installation never owned.
                raise ValueError("a delivery source lies inside the artifact root")
        for items, label in (
            (self.deliveries, "delivery"),
            (self.merges, "merge"),
            (self.settings, "settings entry"),
        ):
            harnesses = [item.harness for item in items]
            if len(set(harnesses)) != len(harnesses):
                # One per harness, so the reconciler can name the component by the harness that
                # reads it. Two would collide into one component and the second would be silently
                # dropped from the state everything else compares against.
                raise ValueError(f"one harness reads one {label} of an artifact")


def _within(root: str, path: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


#: What one installed artifact left behind. An MCP server leaves a launcher, an interpreter and a
#: transport; a Skill, a guideline, a hook or a memory leaves what was delivered and where. They are
#: two types rather than one with optional halves, so neither can be missing what it must have.
ArtifactReceipt: TypeAlias = InstallationReceipt | PlacedArtifactReceipt


@dataclass(frozen=True, slots=True)
class InstalledRecord:
    """One installed artifact: what it left behind, and why it is there.

    Ownership is kept beside the receipt rather than inside it because the two answer different
    questions and are established at different times. A receipt records the effects that ran; the
    reasons an artifact is installed come from the Selection that asked for it, and they change
    when another Collection starts or stops needing it without any effect running at all.
    """

    coordinate: ArtifactCoordinate
    receipt: ArtifactReceipt
    ownership: tuple[OwnershipReason, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.coordinate, ArtifactCoordinate)
            or not isinstance(self.receipt, (InstallationReceipt, PlacedArtifactReceipt))
            or any(not isinstance(item, OwnershipReason) for item in self.ownership)
        ):
            raise ValueError("an installed record is invalid")
        object.__setattr__(
            self, "ownership", tuple(sorted(set(self.ownership), key=lambda item: item.sort_key))
        )

    @property
    def collections(self) -> tuple[str, ...]:
        """The Collections that want this artifact, in the order they are named."""

        return tuple(item.owner for item in self.ownership if item.kind is OwnershipKind.COLLECTION)

    @property
    def credential_references(self) -> tuple[CredentialReference, ...]:
        """The credentials this installation resolves when it runs.

        An artifact a harness reads starts no process, so it resolves none. That is the answer
        rather than a missing field: asking a placement for its credentials is a fair question with
        an empty answer, and every caller that inspects credentials has to be able to ask it.
        """

        if isinstance(self.receipt, PlacedArtifactReceipt):
            return ()
        return self.receipt.credentials


def placed_artifact_receipt_to_data(receipt: PlacedArtifactReceipt) -> dict[str, object]:
    return {
        "artifact": receipt.artifact,
        "config": [
            {"digest": str(item.digest), "input": item.input.value} for item in receipt.config
        ],
        "deliveries": [
            {
                "destination": item.destination,
                "digest": str(item.digest),
                "harness": item.harness,
                "kind": item.kind.value,
                "source": item.source,
            }
            for item in receipt.deliveries
        ],
        "merges": [
            {
                "destination": item.destination,
                "digest": str(item.digest),
                "harness": item.harness,
                "region": item.region,
                "source": item.source,
            }
            for item in receipt.merges
        ],
        "payload_digest": str(receipt.payload_digest),
        "root": receipt.root,
        "settings": [
            {
                "command": item.entry.command,
                "destination": item.destination,
                "harness": item.harness,
                "matcher": item.entry.matcher,
                "path": item.path,
                "shape": item.entry.shape.value,
            }
            for item in receipt.settings
        ],
    }


def _error(message: str) -> Err:
    return Err((Diagnostic(RECEIPT_INVALID, Severity.ERROR, message),))


def _digest(value: object, label: str) -> ObjectDigest:
    if not isinstance(value, str) or value.count(":") != 1:
        raise ValueError(f"{label} must be written as algorithm:value")
    algorithm, digest = value.split(":")
    if not algorithm or not digest:
        raise ValueError(f"{label} must be written as algorithm:value")
    return ObjectDigest(algorithm, digest)


def _delivery(value: object) -> ArtifactDelivery:
    if not isinstance(value, dict):
        raise ValueError("a delivery must be a mapping")
    for key in ("harness", "source", "destination", "kind", "digest"):
        if key not in value:
            raise ValueError(f"a delivery is missing {key}")
    raw = str(value["kind"])
    try:
        kind = DeliveryKind(raw)
    except ValueError:
        raise ValueError(f"unknown delivery kind {raw!r}") from None
    return ArtifactDelivery(
        str(value["harness"]),
        str(value["source"]),
        str(value["destination"]),
        kind,
        _digest(value["digest"], "delivery digest"),
    )


def _merge(value: object) -> ArtifactMerge:
    if not isinstance(value, dict):
        raise ValueError("a merge must be a mapping")
    for key in ("harness", "source", "destination", "region", "digest"):
        if key not in value:
            raise ValueError(f"a merge is missing {key}")
    return ArtifactMerge(
        str(value["harness"]),
        str(value["source"]),
        str(value["destination"]),
        str(value["region"]),
        _digest(value["digest"], "merge digest"),
    )


def _settings_entry(value: object) -> ArtifactSettingsEntry:
    if not isinstance(value, dict):
        raise ValueError("a settings entry must be a mapping")
    for key in ("harness", "destination", "path", "shape", "matcher", "command"):
        if key not in value:
            raise ValueError(f"a settings entry is missing {key}")
    raw = str(value["shape"])
    try:
        shape = HookEntryShape(raw)
    except ValueError:
        raise ValueError(f"unknown settings entry shape {raw!r}") from None
    return ArtifactSettingsEntry(
        str(value["harness"]),
        str(value["destination"]),
        str(value["path"]),
        HookEntry(shape, str(value["matcher"]), str(value["command"])),
    )


def _reference(data: object) -> CredentialReference:
    if not isinstance(data, dict):
        raise ValueError("a credential document must be a mapping")
    try:
        return CredentialReference(
            InputId(str(data["input"])),
            CredentialProviderRef(
                str(data["provider"]), str(data["service"]), str(data["account"])
            ),
        )
    except KeyError as error:
        raise ValueError(f"credential document is missing {error.args[0]}") from None


def _fingerprint(data: object) -> ConfigFingerprint:
    if not isinstance(data, dict):
        raise ValueError("a config document must be a mapping")
    try:
        return ConfigFingerprint(
            InputId(str(data["input"])), _digest(data["digest"], "config digest")
        )
    except KeyError as error:
        raise ValueError(f"config document is missing {error.args[0]}") from None


def placed_artifact_receipt_from_data(data: object) -> Result[PlacedArtifactReceipt]:
    """The exact inverse of :func:`placed_artifact_receipt_to_data`.

    Like the installation receipt, this refuses what it cannot rebuild rather than defaulting a
    missing field: a record whose deliveries are absent would come back as an artifact delivered
    nowhere, which reads as an install that never reached a harness rather than as a record this
    process could not understand.
    """

    if not isinstance(data, dict):
        return _error("a placed artifact receipt must be a mapping")
    try:
        for key in ("artifact", "root", "payload_digest", "deliveries"):
            if key not in data:
                raise ValueError(f"placed artifact receipt is missing {key}")
        for key in ("deliveries", "config", "merges", "settings"):
            if not isinstance(data.get(key, []), list):
                raise ValueError(f"placed artifact receipt {key} must be a list")
        return Ok(
            PlacedArtifactReceipt(
                str(data["artifact"]),
                str(data["root"]),
                _digest(data["payload_digest"], "payload digest"),
                tuple(_delivery(item) for item in data["deliveries"]),
                tuple(_fingerprint(item) for item in data.get("config", [])),
                # Absent rather than required: a receipt written before merges existed records an
                # artifact that merged into nothing, which is exactly what it did.
                tuple(_merge(item) for item in data.get("merges", [])),
                tuple(_settings_entry(item) for item in data.get("settings", [])),
            )
        )
    except ValueError as error:
        return _error(str(error))


def installation_receipt_from_data(data: object) -> Result[InstallationReceipt]:
    """The exact inverse of :func:`installation_receipt_to_data`.

    A receipt read back off a disk is evidence somebody else's process wrote, so this refuses
    anything it cannot rebuild faithfully rather than filling a gap with a default.  Every
    constructor invariant still applies: a launcher outside its own root is rejected here for the
    same reason it is rejected when the installation is first recorded.
    """

    if not isinstance(data, dict):
        return _error("an installation receipt must be a mapping")
    try:
        for key in ("artifact", "root", "launcher", "launcher_digest", "interpreter"):
            if key not in data:
                raise ValueError(f"installation receipt is missing {key}")
        for key in ("registrations", "credentials", "config"):
            if not isinstance(data.get(key, []), list):
                raise ValueError(f"installation receipt {key} must be a list")
        return Ok(
            InstallationReceipt(
                str(data["artifact"]),
                str(data["root"]),
                str(data["launcher"]),
                _digest(data["launcher_digest"], "launcher digest"),
                str(data["interpreter"]),
                Transport(str(data.get("transport", Transport.STDIO.value))),
                tuple(registration_from_data(item) for item in data.get("registrations", [])),
                tuple(_reference(item) for item in data.get("credentials", [])),
                tuple(_fingerprint(item) for item in data.get("config", [])),
                None if data.get("base_interpreter") is None else str(data["base_interpreter"]),
            )
        )
    except ValueError as error:
        return _error(str(error))
