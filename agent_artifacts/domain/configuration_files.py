"""Where an installed artifact's ordinary configuration lives, and the one format it is written in.

A `ConfigInput` value -- a user name, an organisation, an `https` site -- is not a credential and is
not AART's to keep. §96 allows it in AART-owned local state; the owner narrowed that to the
artifact's own installed location (D-264), so the value sits beside the artifact that uses it and
leaves with it, and AART's state records only which file holds it and what that file's digest was.

There is one file per harness the artifact is installed into, because a value is always set in the
context of a harness: the same server may be started by two harnesses with two different
organisations. The launcher is shared and is told which harness started it, so changing one
harness's value rewrites one small file and nothing else (INV-179).

The format is deliberately the plainest one a POSIX shell can read without evaluating anything:

```text
# comment
input-id=value
```

A value is everything after the first `=`, one safe line with no surrounding space. Nothing is
quoted, so nothing is unquoted, and the launcher reads each line with `read -r` into a variable --
a value such as `acme; rm -rf ~` is text, never a command. Parsing is strict in the other direction:
a file somebody edited into a shape this module did not write is reported, not guessed at.

Credentials never appear here. The type only accepts config values, and a value shaped like a
credential is refused, so a token pasted into a user-name field is not written to disk (INV-161).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from agent_artifacts.redaction import contains_credential_shape

from .diagnostics import Diagnostic, DiagnosticCode, Severity
from .identifiers import InputId, ObjectDigest
from .result import Err, Ok, Result

__all__ = [
    "CONFIGURATION_DIRECTORY",
    "CONFIGURATION_FILE_INVALID",
    "CONFIGURATION_SUFFIX",
    "ConfigurationFileRecord",
    "configuration_file_path",
    "configuration_value_problem",
    "parse_configuration_file",
    "render_configuration_file",
]

CONFIGURATION_FILE_INVALID = DiagnosticCode("configuration-file-invalid")
CONFIGURATION_DIRECTORY = "config"
CONFIGURATION_SUFFIX = ".conf"

_SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


def _error(message: str) -> Err:
    return Err((Diagnostic(CONFIGURATION_FILE_INVALID, Severity.ERROR, message),))


def _slug(value: object, label: str) -> str:
    if not isinstance(value, str) or _SLUG_RE.fullmatch(value) is None:
        raise ValueError(f"a configuration file {label} is invalid")
    return value


def configuration_file_path(root: str, harness: str) -> str:
    """The file one harness's values for the artifact installed at `root` are kept in."""

    if (
        not isinstance(root, str)
        or not root.startswith("/")
        or root != root.rstrip("/")
        or any(character in root for character in "\r\n\x00")
    ):
        raise ValueError("a configuration file belongs to an absolute artifact root")
    return f"{root}/{CONFIGURATION_DIRECTORY}/{_slug(harness, 'harness')}{CONFIGURATION_SUFFIX}"


def configuration_value_problem(value: object) -> str | None:
    """Why `value` cannot be written as one configuration value, or None when it can."""

    if not isinstance(value, str) or not value:
        return "a value is needed"
    if any(
        unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for character in value
    ):
        return "a value is one line of visible text"
    if value != value.strip():
        return "a value cannot start or end with a space"
    if contains_credential_shape(value):
        return "this looks like a credential; credentials are kept by the provider, not here"
    return None


def _values(values: object) -> tuple[tuple[InputId, str], ...]:
    if not isinstance(values, tuple):
        raise ValueError("configuration values are invalid")
    seen: set[str] = set()
    for item in values:
        if (
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], InputId)
            or _SLUG_RE.fullmatch(item[0].value) is None
        ):
            raise ValueError("configuration values are invalid")
        if item[0].value in seen:
            raise ValueError(f"configuration names {item[0]} twice")
        seen.add(item[0].value)
        problem = configuration_value_problem(item[1])
        if problem is not None:
            raise ValueError(f"configuration value for {item[0]} is invalid: {problem}")
    return tuple(sorted(values, key=lambda item: item[0].value))


def render_configuration_file(
    artifact: str, harness: str, values: tuple[tuple[InputId, str], ...]
) -> str:
    """The exact text written for one harness. Ordered by input id, so equal values give one file."""

    if (
        not isinstance(artifact, str)
        or not artifact
        or any(unicodedata.category(character)[0] in {"C", "Z"} for character in artifact)
    ):
        raise ValueError("a configuration file names the artifact it configures")
    lines = [
        f"# Configuration for {artifact} when {_slug(harness, 'harness')} starts it.",
        "# Ordinary settings only; credentials stay with their provider and are never written here.",
        "# Change these from AART (User variables and credentials) so the change is reviewed.",
        *(f"{identifier.value}={value}" for identifier, value in _values(values)),
    ]
    return "\n".join(lines) + "\n"


def parse_configuration_file(content: object) -> Result[tuple[tuple[InputId, str], ...]]:
    """Read back what `render_configuration_file` writes, refusing anything it would not write."""

    if not isinstance(content, str):
        return _error("a configuration file is text")
    if content and not content.endswith("\n"):
        return _error("a configuration file ends with a newline")
    found: list[tuple[InputId, str]] = []
    seen: set[str] = set()
    for number, line in enumerate(content.split("\n")[:-1], start=1):
        if not line or line.startswith("#"):
            continue
        identifier, separator, value = line.partition("=")
        if not separator or _SLUG_RE.fullmatch(identifier) is None:
            return _error(f"line {number} is not input-id=value")
        if identifier in seen:
            return _error(f"line {number} sets {identifier} a second time")
        problem = configuration_value_problem(value)
        if problem is not None:
            return _error(f"line {number} ({identifier}): {problem}")
        seen.add(identifier)
        found.append((InputId(identifier), value))
    return Ok(tuple(sorted(found, key=lambda item: item[0].value)))


@dataclass(frozen=True, slots=True)
class ConfigurationFileRecord:
    """What a receipt keeps about one harness's configuration file: where it is and its digest.

    Never the values. The digest is enough to tell "as AART wrote it" from "changed since", and a
    record without the values leaves nothing in AART's state for a policy to object to.
    """

    harness: str
    path: str
    digest: ObjectDigest

    def __post_init__(self) -> None:
        _slug(self.harness, "harness")
        if (
            not isinstance(self.path, str)
            or not self.path.startswith("/")
            or not self.path.endswith(
                f"/{CONFIGURATION_DIRECTORY}/{self.harness}{CONFIGURATION_SUFFIX}"
            )
        ):
            raise ValueError("a configuration file record names its harness's file")
        if not isinstance(self.digest, ObjectDigest):
            raise ValueError("a configuration file record digest is invalid")

    @property
    def root(self) -> str:
        suffix = f"/{CONFIGURATION_DIRECTORY}/{self.harness}{CONFIGURATION_SUFFIX}"
        return self.path[: -len(suffix)]
