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

from .credentials import CredentialReference
from .harness import McpRegistration, registration_to_data
from .identifiers import InputId, ObjectDigest
from .launch import Transport

__all__ = [
    "ConfigFingerprint",
    "InstallationReceipt",
    "config_fingerprint",
    "installation_receipt_to_data",
]


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
        "config": [
            {"digest": str(item.digest), "input": item.input.value} for item in receipt.config
        ],
        "credentials": [str(reference) for reference in receipt.credentials],
        "interpreter": receipt.interpreter,
        "launcher": receipt.launcher,
        "launcher_digest": str(receipt.launcher_digest),
        "registrations": [registration_to_data(item) for item in receipt.registrations],
        "root": receipt.root,
        "transport": receipt.transport.value,
    }
