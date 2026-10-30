"""The one default Registry a build may carry, read back and validated (CP-27, D-373)."""

from __future__ import annotations

from dataclasses import dataclass

from aart_cli import _default_registry, _default_telemetry, _default_usage
from aart_cli.domain.artifact_usage import parse_usage_harnesses
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.domain.telemetry import parse_telemetry_endpoint

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


def baked_usage_harnesses(raw: str | None = None) -> tuple[str, ...]:
    """The harnesses this build records artifact usage in until a person chooses (§212, D-502).

    Read when asked rather than when imported, so the stamped module is what counts. A value the
    release would have refused records nowhere: recording without asking is never the fallback.
    """

    parsed = parse_usage_harnesses(_default_usage.HARNESSES if raw is None else raw)
    return parsed.value if isinstance(parsed, Ok) else ()


def baked_telemetry_endpoint(raw: str | None = None) -> str | None:
    """The telemetry server this build names, or `None` (§213, D-503, D-505).

    Read when asked rather than when imported, so the stamped module is what counts. A value the
    release would have refused names nothing: sending without a valid address is never the
    fallback. A named server is where telemetry goes from the first start where nobody decided.
    """

    value = (_default_telemetry.ENDPOINT if raw is None else raw).strip()
    if not value:
        return None
    parsed = parse_telemetry_endpoint(value)
    return parsed.value if isinstance(parsed, Ok) else None
