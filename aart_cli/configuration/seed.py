"""The one default Registry a build may carry, read back and validated (CP-27, D-373)."""

from __future__ import annotations

from dataclasses import dataclass

from aart_cli import _default_registry
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Err, Ok, Result

from .model import git_location_parts, parse_source_alias

SEED_INVALID = DiagnosticCode("default-registry-invalid")


@dataclass(frozen=True, slots=True)
class SeededRegistry:
    """One Registry a release stamped into the wheel, to connect when nothing is configured."""

    alias: SourceAlias
    url: str

    def __post_init__(self) -> None:
        if not self.alias.value or not self.url:
            raise ValueError("a seeded registry has both an alias and a URL")


def _error(message: str) -> Err:
    return Err((Diagnostic(SEED_INVALID, Severity.ERROR, message),))


def baked_default_registry(
    alias: str = _default_registry.ALIAS,
    url: str = _default_registry.URL,
) -> Result[SeededRegistry | None]:
    """Return the Registry this build baked, ``None`` if it baked none, or why it is unusable.

    Both empty is the ordinary answer for a build whose release variable was unset, so it is an
    ``Ok(None)`` rather than a diagnostic: a public wheel carrying no default is correct, not
    broken. Everything else is refused rather than repaired. Half a pair cannot be completed --
    an alias is stamped into the path of everything installed from this Registry (D-359, INV-253),
    so inventing one would commit a person to a name nobody chose. A location Git cannot clone, or
    one carrying credentials, is refused for the same reason the alias is: the first run prints
    what it connected, and a release variable is not a secret store.

    The caller decides what an error means. At build time it fails the release; at runtime it
    leaves the first run asking for a Registry the way it does today, which is the whole point of
    the value being a default and not an authority.
    """

    if not alias and not url:
        return Ok(None)
    if not url:
        return _error("baked default registry alias has no URL")
    if not alias:
        return _error("baked default registry URL has no alias")
    parsed = parse_source_alias(alias)
    if parsed is None:
        return _error("baked default registry alias is invalid")
    if git_location_parts(url) is None:
        return _error("baked default registry URL is invalid")
    return Ok(SeededRegistry(parsed, url))
