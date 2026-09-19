"""Who one installation is, and the credential item that therefore belongs to it alone.

§169.4-6 and D-333 settle a question the product had been answering by accident. Configuration and
credentials belong to an *installation*, and an installation is not an artifact: it is a Registry
alias, an artifact kind and name, a scope, the concrete root it was installed into, and the harness
with its profile. Installing the same package into a second harness is a second installation, with
its own entered values and its own credential item, even when the bytes are identical.

The address this module derives is what makes that true where it matters most. What it replaces
named the machine and the declared input and nothing else -- a service of `aart.<hash of the user
home>` with the input id as the account -- so one artifact in two harnesses, two scopes or from two
Registry aliases reached for one item. Anyone who then rotated or deleted a credential for one
installation silently did it for the others.

Three things it must not do. It must not carry the version: a compatible update reconciles the
installation that is there, and an address that moved with the version would ask for every secret
again (D-313's owner fields, minus the sharing exception D-333 removed). It must not carry the root
as a path: an item's attributes are readable by anything that can list the keychain, and a project
directory is often the name of a client. And it must not truncate, because a truncated address is
how two owners quietly become one item -- an oversized name is refused instead.

Pure identity: nothing here consults a filesystem, an environment or a provider.
"""

from __future__ import annotations

import hashlib
import posixpath
import re
from dataclasses import dataclass

from .credentials import CredentialProviderRef
from .harness import Scope
from .identifiers import ArtifactCoordinate, ArtifactIdentity, InputId, SourceAlias

__all__ = [
    "CREDENTIAL_SERVICE_PREFIX",
    "MAX_CREDENTIAL_SERVICE_LENGTH",
    "InstallationOwner",
    "credential_address",
    "installation_owner",
]

#: The product's own namespace in somebody else's credential store, so an operator reading a
#: keychain can tell at a glance which items are not their own.
CREDENTIAL_SERVICE_PREFIX = "aart-cli"

#: What a provider will hold without complaint. macOS accepts more, but an address is written by
#: this product and read by a person, and one that needs scrolling is one nobody checks. Exceeding
#: it is refused rather than shortened.
MAX_CREDENTIAL_SERVICE_LENGTH = 255

#: The default provider: the platform store, named the way the credential context already names it.
_DEFAULT_PROVIDER = "keychain"

#: The slug every composed label is held to -- the same one the configuration and protocol schemas
#: validate aliases, kinds and names against. Repeated rather than assumed, because a separator
#: reaching this far from an alias somebody typed would make one owner's address readable as
#: another's.
_SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")

#: Separates the labels. It cannot appear inside a slug, so the address parses back to exactly one
#: owner rather than to whichever split happens to fit.
_SEPARATOR = "."

#: Stands in for a harness with no profile. It is not a usable slug, so a profile can never be read
#: as an absent one, and `claude` at user scope stays distinct from profile `user` at project scope.
_NO_PROFILE = "-"

#: How much of the root's digest identifies it. Sixty-four bits: enough that two roots colliding is
#: not a thing that happens, short enough to stay readable beside the labels.
_ROOT_DISCRIMINATOR_LENGTH = 16


def _slug(value: object, label: str) -> str:
    if not isinstance(value, str) or _SLUG_RE.fullmatch(value) is None:
        raise ValueError(f"{label} is not a canonical slug: {value!r}")
    return value


def _root(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or not posixpath.isabs(value)
        or posixpath.normpath(value) != value
        or any(character in value for character in "\r\n")
    ):
        raise ValueError("an installation root must be a normalized absolute path")
    return value


@dataclass(frozen=True, slots=True, order=True)
class InstallationOwner:
    """The complete identity of one installation, with no version in it.

    `profile` is empty for a harness that has only one. It is a field rather than part of `harness`
    because two profiles of one harness are two installations that share an adapter, and the
    adapter is what `harness` names.
    """

    source: SourceAlias
    artifact: ArtifactIdentity
    scope: Scope
    root: str
    harness: str
    profile: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.source, SourceAlias):
            raise ValueError("an installation owner needs a Registry alias")
        if not isinstance(self.artifact, ArtifactIdentity):
            raise ValueError("an installation owner needs an artifact identity")
        if not isinstance(self.scope, Scope):
            raise ValueError("an installation owner needs a harness scope")
        _slug(self.source.value, "registry alias")
        _slug(self.artifact.kind, "artifact kind")
        _slug(self.artifact.name, "artifact name")
        _slug(self.harness, "harness")
        _root(self.root)
        if self.profile:
            _slug(self.profile, "harness profile")

    def __str__(self) -> str:
        profile = f"+{self.profile}" if self.profile else ""
        return f"{self.harness}{profile}/{self.scope.value}:{self.source}/{self.artifact}"


def installation_owner(
    coordinate: ArtifactCoordinate,
    *,
    scope: Scope,
    root: str,
    harness: str,
    profile: str = "",
) -> InstallationOwner:
    """The owner this coordinate installs as, with the version deliberately dropped.

    The version is dropped here rather than at each call site so no caller can decide to keep it:
    an owner that moved with the version would make every compatible update a fresh installation
    with no configuration and no credentials.
    """

    if not isinstance(coordinate, ArtifactCoordinate):
        raise ValueError("an installation owner needs an artifact coordinate")
    return InstallationOwner(coordinate.source, coordinate.artifact, scope, root, harness, profile)


def credential_address(
    owner: InstallationOwner,
    input_id: InputId,
    *,
    provider: str = _DEFAULT_PROVIDER,
) -> CredentialProviderRef:
    """Where this owner's value for `input_id` lives, named without saying what it is.

    The service carries the owner in labels a person can read back, with the root reduced to an
    opaque discriminator; the account is the declared input. Nothing in either is derived from a
    value, so the address can be computed before the value exists and again on every retry.
    """

    if not isinstance(owner, InstallationOwner):
        raise ValueError("a credential address needs an installation owner")
    if not isinstance(input_id, InputId):
        raise ValueError("a credential address needs a declared input id")
    service = _SEPARATOR.join(
        (
            CREDENTIAL_SERVICE_PREFIX,
            owner.harness,
            owner.profile or _NO_PROFILE,
            owner.scope.value,
            owner.source.value,
            owner.artifact.kind,
            owner.artifact.name,
            _root_discriminator(owner.root),
        )
    )
    if len(service) > MAX_CREDENTIAL_SERVICE_LENGTH:
        raise ValueError(
            f"credential service exceeds {MAX_CREDENTIAL_SERVICE_LENGTH} characters: {len(service)}"
        )
    return CredentialProviderRef(provider, service, input_id.value)


def _root_discriminator(root: str) -> str:
    """The root as an identifier rather than as a path, because the path is often a client's name."""

    return hashlib.sha256(root.encode("utf-8")).hexdigest()[:_ROOT_DISCRIMINATOR_LENGTH]
