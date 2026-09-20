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
from collections.abc import Iterable
from dataclasses import dataclass

from .credentials import CredentialProviderRef
from .diagnostics import Diagnostic, DiagnosticCode, Severity
from .harness import Scope
from .identifiers import ArtifactCoordinate, ArtifactIdentity, InputId, SourceAlias
from .result import Err, Ok, Result

__all__ = [
    "CREDENTIAL_SERVICE_PREFIX",
    "INSTALLED_NAME_COLLISION",
    "INSTALLED_NAME_INVALID",
    "MAX_CREDENTIAL_SERVICE_LENGTH",
    "MAX_INSTALLED_NAME_LENGTH",
    "InstallationOwner",
    "credential_address",
    "installation_key",
    "installation_owner",
    "installation_owner_from_data",
    "installation_owner_to_data",
    "installed_name",
    "installed_names",
]

#: The composed name could not be a name the harness would discover. Refused rather than shortened.
INSTALLED_NAME_INVALID = DiagnosticCode("installed-name-invalid")
#: Two owners in one operation spell the same installed name. Refused before anything is written.
INSTALLED_NAME_COLLISION = DiagnosticCode("installed-name-collision")

#: The published skill contract: lowercase alphanumeric with single hyphens, 1-64 characters, and
#: a directory whose name matches. OpenCode and the Agent Skills specification both say so, and
#: Tabnine CLI discovers the same shape, so one bound holds for every adapter rather than each
#: carrying its own.
MAX_INSTALLED_NAME_LENGTH = 64

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
#: A harness-visible name carries no version, so composing one from a coordinate needs a stand-in
#: for the field the join never reads.
_ANY_VERSION = "0.0.0"

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

    @property
    def label(self) -> str:
        """The harness this installation is, as one token: `harness`, or `harness+profile`.

        Composed here rather than at each reader, because a key spelled one way where it is
        written and another where it is looked up addresses nothing.
        """

        return f"{self.harness}+{self.profile}" if self.profile else self.harness

    def __str__(self) -> str:
        return f"{self.label}/{self.scope.value}:{self.source}/{self.artifact}"


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


def installation_key(coordinate: object, owner: InstallationOwner | None) -> str:
    """The key that addresses one installation rather than one artifact (§169.3).

    The coordinate stopped identifying one thing on this machine when each harness became its own
    installation: the same artifact in claude and in tabnine is two trees, two configuration files
    and two records. Everything that selects something to act on -- a row, a focus, a lookup --
    has to use this, because an action addressed to the coordinate alone would reach whichever of
    them a dictionary happened to keep.

    `#` separates the two halves, and both are composed of slugs, so the key stays greppable and
    cannot collide with a coordinate: no alias, kind, name or version may contain one. A record
    that names no owner falls back to the coordinate, which is what it is.
    """

    if owner is None:
        return str(coordinate)
    if not isinstance(owner, InstallationOwner):
        raise ValueError("an installation key needs an installation owner")
    return f"{coordinate}#{owner.label}"


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
    service = _SEPARATOR.join(_service_labels(owner, owner.harness))
    if len(service) > MAX_CREDENTIAL_SERVICE_LENGTH:
        raise ValueError(
            f"credential service exceeds {MAX_CREDENTIAL_SERVICE_LENGTH} characters: {len(service)}"
        )
    return CredentialProviderRef(provider, service, input_id.value)


def _service_labels(owner: InstallationOwner, harness: str) -> tuple[str, ...]:
    """The address's labels in order, with `harness` already decided by the caller.

    One function composes them, so the labels an address is built from cannot drift apart from
    the labels anything else reads it back by.
    """

    return (
        CREDENTIAL_SERVICE_PREFIX,
        harness,
        owner.profile or _NO_PROFILE,
        owner.scope.value,
        owner.source.value,
        owner.artifact.kind,
        owner.artifact.name,
        _root_discriminator(owner.root),
    )


def _refuse(code: DiagnosticCode, message: str, *remediation: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message, remediation=remediation),))


def installed_name_for(coordinate: ArtifactCoordinate, scope: Scope) -> Result[str]:
    """The same name, asked for before any owner exists to ask it of.

    Placement composes the directory a harness discovers before it knows which harnesses will read
    it, and the join carries no harness and no root, so a coordinate and a scope are the whole of
    it. Both spellings come from here so a directory cannot be delivered under one name and
    recorded under another.
    """

    if not isinstance(coordinate, ArtifactCoordinate) or not isinstance(scope, Scope):
        raise ValueError("an installed name needs an artifact coordinate and a scope")
    name = "-".join((coordinate.artifact.name, coordinate.source.value, scope.value))
    if len(name) > MAX_INSTALLED_NAME_LENGTH or _SLUG_RE.fullmatch(name) is None:
        return _refuse(
            INSTALLED_NAME_INVALID,
            f"{coordinate} cannot be installed as {name!r}: a harness name is lowercase "
            f"alphanumeric with single hyphens and at most {MAX_INSTALLED_NAME_LENGTH} characters",
            "Shorten the artifact name or connect the Registry under a shorter alias.",
        )
    return Ok(name)


def installed_name(owner: InstallationOwner) -> Result[str]:
    """What the harness shows for this installation: artifact, alias and scope, joined once.

    The version is absent on purpose. A harness-visible name is what a person reads in their own
    directory listing, and one that moved with every update would rename a directory the harness
    had already discovered. The version stays in AART's own views and in the receipt.

    The harness is not in it either, because the name lives *inside* that harness's own root, and
    the root is not in it because a name is not an identity -- §169.4's owner remains the authority
    and `credential_address` is what carries it.
    """

    if not isinstance(owner, InstallationOwner):
        raise ValueError("an installed name needs an installation owner")
    composed = installed_name_for(
        ArtifactCoordinate(owner.source, owner.artifact, _ANY_VERSION), owner.scope
    )
    if isinstance(composed, Err):
        # The coordinate this was asked of is a stand-in; the owner is what the person can act on.
        return _refuse(
            INSTALLED_NAME_INVALID,
            f"{owner} cannot be installed under a harness-visible name: a harness name is "
            f"lowercase alphanumeric with single hyphens and at most "
            f"{MAX_INSTALLED_NAME_LENGTH} characters",
            "Shorten the artifact name or connect the Registry under a shorter alias.",
        )
    return composed


def installed_names(
    owners: Iterable[InstallationOwner],
) -> Result[tuple[tuple[InstallationOwner, str], ...]]:
    """Name every owner in one operation, refusing the set if two of them spell the same thing.

    The join is ambiguous by construction: the separator between the labels is also a character
    allowed inside them, so the split can move. `github` from `company-user` and `github-company`
    from `user` both spell `github-company-user` at project scope. Nothing about either name is
    wrong, and neither can be silently disambiguated -- a counter would depend on which was
    encountered first, and truncation is worse. So the whole operation is refused by name, before
    a directory exists to overwrite.
    """

    by_slot: dict[tuple[str, str, str, str, str], InstallationOwner] = {}
    named: list[tuple[InstallationOwner, str]] = []
    for owner in owners:
        composed = installed_name(owner)
        if isinstance(composed, Err):
            return composed
        name = composed.value
        # A visible name occupies one namespace owned by one concrete harness/profile/root and
        # artifact kind. The same spelling in Claude and Tabnine, or in a Skill directory and an
        # MCP registration table, cannot overwrite itself because those adapters never meet.
        slot = (owner.root, owner.harness, owner.profile, owner.artifact.kind, name)
        claimed = by_slot.get(slot)
        if claimed is not None and claimed != owner:
            return _refuse(
                INSTALLED_NAME_COLLISION,
                f"{claimed} and {owner} would both be installed as {name!r}",
                "Connect one of them under a different Registry alias, "
                "or install them into different scopes.",
            )
        if claimed is None:
            by_slot[slot] = owner
            named.append((owner, name))
    return Ok(tuple(named))


def _root_discriminator(root: str) -> str:
    """The root as an identifier rather than as a path, because the path is often a client's name."""

    return hashlib.sha256(root.encode("utf-8")).hexdigest()[:_ROOT_DISCRIMINATOR_LENGTH]


def installation_owner_to_data(owner: InstallationOwner) -> dict[str, object]:
    """One owner as the record that names it, with every field written out.

    The root is written as the path it is. This is the product's own managed record, not an
    address in somebody else's store: `credential_address` hides the root because a keychain item's
    attributes are readable by anything that can list the keychain, and this record is not.
    """

    if not isinstance(owner, InstallationOwner):
        raise ValueError("an installation owner record needs an installation owner")
    return {
        "artifact": {"kind": owner.artifact.kind, "name": owner.artifact.name},
        "harness": owner.harness,
        "profile": owner.profile,
        "root": owner.root,
        "scope": owner.scope.value,
        "source": owner.source.value,
    }


def installation_owner_from_data(data: object) -> InstallationOwner:
    """Rebuild one owner from its own record, refusing anything that is not one.

    Every field is required. An owner missing one of them would be a different installation from
    the one that was recorded, and reading it as the recorded one is how two installations become
    one record.
    """

    if not isinstance(data, dict):
        raise ValueError("an installation owner record must be a mapping")
    artifact = data.get("artifact")
    if not isinstance(artifact, dict):
        raise ValueError("an installation owner record names one artifact")
    try:
        kind = artifact["kind"]
        name = artifact["name"]
        harness = data["harness"]
        profile = data["profile"]
        root = data["root"]
        scope = data["scope"]
        source = data["source"]
    except KeyError as error:
        raise ValueError(f"installation owner record is missing {error.args[0]}") from None
    if not all(isinstance(value, str) for value in (kind, name, harness, profile, root, source)):
        raise ValueError("installation owner record has an invalid field")
    try:
        return InstallationOwner(
            SourceAlias(source), ArtifactIdentity(kind, name), Scope(scope), root, harness, profile
        )
    except ValueError as error:
        raise ValueError(f"installation owner record is not an owner: {error}") from None
