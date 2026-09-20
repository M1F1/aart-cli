"""Published executable protocol contract shared by runtime composition roots."""

from __future__ import annotations

from aart_cli import __version__
from aart_cli.domain.result import Ok
from aart_cli.protocol.capabilities import Capability
from aart_cli.protocol.semver import SemVer, parse_semver


def _executable_version() -> SemVer:
    """The published version, read rather than written a second time.

    A second literal here would have to be kept in step with `aart_cli.__version__`, which
    INV-085 forbids.  There is one literal, the release engine writes it, and this is derived from
    it, so the two cannot disagree at all rather than being checked afterwards.

    A malformed version is raised at import.  This is the executable's published identity; a
    tool that cannot say which version it is has nothing sensible to do next.
    """

    parsed = parse_semver(__version__)
    if not isinstance(parsed, Ok):
        raise ValueError(f"aart_cli.__version__ is not a SemVer: {__version__!r}")
    return parsed.value


EXECUTABLE_VERSION = _executable_version()
EXECUTABLE_CAPABILITIES = tuple(
    Capability(value)
    for value in (
        "artifact-manifest-v1",
        "keychain-secret",
        "lockfile-v1",
        "managed-file",
        "open-browser",
        "registry-entry-v1",
    )
)

__all__ = ["EXECUTABLE_CAPABILITIES", "EXECUTABLE_VERSION"]
