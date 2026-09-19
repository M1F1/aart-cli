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
    "credential_service_template",
    "installation_owner",
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

#: Stands in for a harness with no profile. It is not a usable slug, so a profile can never be read
#: as an absent one, and `claude` at user scope stays distinct from profile `user` at project scope.
_NO_PROFILE = "-"

#: What a harness placeholder may be. Not a shell expression: the launcher splits the template on
#: this token and quotes each side, so nothing in it is ever read by a shell.
_PLACEHOLDER_RE = re.compile(r"^[A-Za-z0-9_-]+$")

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
    service = _SEPARATOR.join(_service_labels(owner, owner.harness))
    if len(service) > MAX_CREDENTIAL_SERVICE_LENGTH:
        raise ValueError(
            f"credential service exceeds {MAX_CREDENTIAL_SERVICE_LENGTH} characters: {len(service)}"
        )
    return CredentialProviderRef(provider, service, input_id.value)


def _service_labels(owner: InstallationOwner, harness: str) -> tuple[str, ...]:
    """The address's labels in order, with `harness` already decided by the caller.

    One function composes them so `credential_address` and `credential_service_template` cannot
    drift apart: a launcher that composed a different address from the one this product stored at
    would read an item that is not there, and the failure would look like a missing credential.
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


def credential_service_template(owner: InstallationOwner, placeholder: str) -> str:
    """This owner's credential service on every harness, with the harness slot left to fill.

    A launcher is generated once for an artifact and told at start which harness started it -- the
    same argument it already uses to find that harness's configuration file. Giving it the address
    with one slot open lets it compose its own rather than carry one harness's, which is what keeps
    one artifact on four harnesses reading four items instead of one.

    Substituting any canonical harness slug yields exactly the service `credential_address` returns
    for that harness, and that equivalence is a property test rather than a comment.

    The placeholder is a token to split on, never an expression. It is held to letters, digits,
    underscore and hyphen: a separator in it would make the address parse as a different owner, and
    anything a shell reads -- a dollar, a quote, a backtick -- would be a way to make a generated
    launcher run something at start. The caller substitutes; nothing here is evaluated anywhere.
    """

    if not isinstance(owner, InstallationOwner):
        raise ValueError("a credential service template needs an installation owner")
    if not isinstance(placeholder, str) or _PLACEHOLDER_RE.fullmatch(placeholder) is None:
        raise ValueError(
            f"a harness placeholder must be letters, digits, underscore or hyphen: {placeholder!r}"
        )
    return _SEPARATOR.join(_service_labels(owner, placeholder))


def _refuse(code: DiagnosticCode, message: str, *remediation: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message, remediation=remediation),))


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
    name = "-".join((owner.artifact.name, owner.source.value, owner.scope.value))
    if len(name) > MAX_INSTALLED_NAME_LENGTH or _SLUG_RE.fullmatch(name) is None:
        return _refuse(
            INSTALLED_NAME_INVALID,
            f"{owner} cannot be installed as {name!r}: a harness name is lowercase alphanumeric "
            f"with single hyphens and at most {MAX_INSTALLED_NAME_LENGTH} characters",
            "Shorten the artifact name or connect the Registry under a shorter alias.",
        )
    return Ok(name)


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

    by_name: dict[str, InstallationOwner] = {}
    named: list[tuple[InstallationOwner, str]] = []
    for owner in owners:
        composed = installed_name(owner)
        if isinstance(composed, Err):
            return composed
        name = composed.value
        claimed = by_name.get(name)
        if claimed is not None and claimed != owner:
            return _refuse(
                INSTALLED_NAME_COLLISION,
                f"{claimed} and {owner} would both be installed as {name!r}",
                "Connect one of them under a different Registry alias, "
                "or install them into different scopes.",
            )
        if claimed is None:
            by_name[name] = owner
            named.append((owner, name))
    return Ok(tuple(named))


def _root_discriminator(root: str) -> str:
    """The root as an identifier rather than as a path, because the path is often a client's name."""

    return hashlib.sha256(root.encode("utf-8")).hexdigest()[:_ROOT_DISCRIMINATOR_LENGTH]
