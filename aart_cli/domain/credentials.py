"""Credential identity and lifecycle state, with no channel for a credential value.

`CredentialReference` is stable metadata and `CredentialObservation` is what inspection can say
about it. Neither carries the material itself: the value exists only transiently inside a provider
interpreter, never in a domain value that a plan, receipt, log or snapshot could serialize.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256

from .identifiers import InputId

_SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


def _line(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character in value for character in "\r\n")
    ):
        raise ValueError(f"{label} must be one safe non-empty line")
    return value


def _slug(value: object, label: str) -> str:
    if not isinstance(value, str) or _SLUG_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be a canonical slug")
    return value


@dataclass(frozen=True, slots=True, order=True)
class CredentialProviderRef:
    """Where a credential lives, named without saying what it is."""

    provider: str
    service: str
    account: str

    def __post_init__(self) -> None:
        _slug(self.provider, "credential provider")
        _line(self.service, "credential service")
        _line(self.account, "credential account")

    def __str__(self) -> str:
        return f"{self.provider}:{self.service}/{self.account}"


@dataclass(frozen=True, slots=True, order=True)
class CredentialReference:
    input: InputId
    provider: CredentialProviderRef

    def __post_init__(self) -> None:
        if not isinstance(self.input, InputId) or not isinstance(
            self.provider, CredentialProviderRef
        ):
            raise ValueError("credential reference is invalid")

    def __str__(self) -> str:
        return f"{self.input}@{self.provider}"


def credential_component_names(
    references: tuple[CredentialReference, ...],
) -> tuple[str, ...]:
    """One component name per reference, in the order given.

    The declared input was a name while one artifact held one item for it. Each installation of an
    artifact holding its own (§169.4-6) means that id can appear several times in one desired
    state, where naming the same component twice is refused. So an id that still names exactly one
    item is left exactly as it was, and one that does not is suffixed with a short digest of the
    whole address: stable across runs, unique between installations, and derived from a reference
    rather than from any value.
    """

    if any(not isinstance(item, CredentialReference) for item in references):
        raise ValueError("credential component names are taken from credential references")
    shared = Counter(item.input.value for item in references)
    return tuple(
        item.input.value
        if shared[item.input.value] == 1
        else f"{item.input.value}.{sha256(str(item).encode('utf-8')).hexdigest()[:8]}"
        for item in references
    )


class ProviderState(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class CredentialState(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    INVALID = "invalid"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CredentialObservation:
    """What a provider can say about a reference. Deliberately has no value field."""

    reference: CredentialReference
    provider_state: ProviderState
    state: CredentialState
    detail: str = ""

    def __post_init__(self) -> None:
        if (
            not isinstance(self.reference, CredentialReference)
            or not isinstance(self.provider_state, ProviderState)
            or not isinstance(self.state, CredentialState)
            or not isinstance(self.detail, str)
            or any(character in self.detail for character in "\r\n")
        ):
            raise ValueError("credential observation is invalid")
        if self.provider_state is not ProviderState.AVAILABLE and self.state not in {
            CredentialState.UNKNOWN,
            CredentialState.ABSENT,
        }:
            raise ValueError("an unavailable provider cannot report credential presence")


class CredentialIntent(str, Enum):
    INSPECT = "inspect"
    STORE = "store"
    VERIFY = "verify"
    REPLACE = "replace"
    DELETE = "delete"


def credential_provider_to_data(provider: CredentialProviderRef) -> dict[str, object]:
    return {
        "account": provider.account,
        "provider": provider.provider,
        "service": provider.service,
    }


def credential_reference_to_data(reference: CredentialReference) -> dict[str, object]:
    return {
        "input": reference.input.value,
        "provider": credential_provider_to_data(reference.provider),
    }


def credential_observation_to_data(observation: CredentialObservation) -> dict[str, object]:
    return {
        "detail": observation.detail,
        "provider_state": observation.provider_state.value,
        "reference": credential_reference_to_data(observation.reference),
        "state": observation.state.value,
    }
