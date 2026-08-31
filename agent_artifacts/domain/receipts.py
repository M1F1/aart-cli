"""What one installation left behind, recorded so a later run can tell it is still true.

A receipt is evidence, not a log. It records identity and digests: where the launcher is and what
it contains, which interpreter it runs, which credential references it will resolve, and which
harnesses were told about it. From that a reconciler can decide what drifted without re-reading
anything it should not.

Config values are recorded by digest rather than in full. They are not secret -- the launcher holds
them in the open -- but a policy may forbid persisting a particular one, and a digest detects drift
just as well as a copy does while leaving that policy nothing to be violated by.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .credentials import CredentialProviderRef, CredentialReference
from .diagnostics import Diagnostic, DiagnosticCode, Severity
from .harness import McpRegistration, registration_from_data, registration_to_data
from .identifiers import ArtifactCoordinate, InputId, ObjectDigest
from .launch import Transport
from .result import Err, Ok, Result
from .selection import OwnershipKind, OwnershipReason

__all__ = [
    "RECEIPT_INVALID",
    "ConfigFingerprint",
    "InstallationReceipt",
    "InstalledRecord",
    "config_fingerprint",
    "installation_receipt_from_data",
    "installation_receipt_to_data",
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


@dataclass(frozen=True, slots=True)
class InstalledRecord:
    """One installed artifact: what it left behind, and why it is there.

    Ownership is kept beside the receipt rather than inside it because the two answer different
    questions and are established at different times. A receipt records the effects that ran; the
    reasons an artifact is installed come from the Selection that asked for it, and they change
    when another Collection starts or stops needing it without any effect running at all.
    """

    coordinate: ArtifactCoordinate
    receipt: InstallationReceipt
    ownership: tuple[OwnershipReason, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.coordinate, ArtifactCoordinate)
            or not isinstance(self.receipt, InstallationReceipt)
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


def _error(message: str) -> Err:
    return Err((Diagnostic(RECEIPT_INVALID, Severity.ERROR, message),))


def _digest(value: object, label: str) -> ObjectDigest:
    if not isinstance(value, str) or value.count(":") != 1:
        raise ValueError(f"{label} must be written as algorithm:value")
    algorithm, digest = value.split(":")
    if not algorithm or not digest:
        raise ValueError(f"{label} must be written as algorithm:value")
    return ObjectDigest(algorithm, digest)


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
