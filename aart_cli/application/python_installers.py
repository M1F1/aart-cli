"""What aart-cli's own pip and uv runs see, so a failed dependency install can be explained (§216).

aart-cli runs pip and uv with a reduced environment, so a person's working `pip install` proves
nothing about aart-cli's. This module is the pure half of the check that closes that gap: which of
the person's variables would change pip or uv and are not passed to them, which line of an
installer's output names the cause rather than its consequence, and what to do about each cause.

Only names are ever compared. A variable's value -- an index URL with a token in it, a proxy with a
password -- is never read here and never reaches a report.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from aart_cli.redaction import redact_text

#: Prefixes of the variables pip and uv read their own options from.
_INSTALLER_PREFIXES = ("PIP_", "UV_")
#: The variables outside those prefixes that decide where pip and uv connect and what they trust.
_NETWORK_SETTINGS = frozenset(
    {
        "ALL_PROXY",
        "CURL_CA_BUNDLE",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "NO_PROXY",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
    }
)


def is_installer_setting(name: str) -> bool:
    """Whether a variable of this name changes what pip or uv does. Proxies are matched in either
    case, because both spellings are honoured."""

    upper = name.upper()
    return upper.startswith(_INSTALLER_PREFIXES) or upper in _NETWORK_SETTINGS


def ignored_installer_settings(present: Iterable[str], passed: Iterable[str]) -> tuple[str, ...]:
    """The installer settings the person has set that aart-cli's pip and uv runs never see."""

    given = frozenset(passed)
    return tuple(sorted({name for name in present if is_installer_setting(name)} - given))


class InstallerFailureKind(str, Enum):
    """What an installer's output says went wrong, as far as one line of it can say."""

    CERTIFICATE = "certificate"
    PROXY = "proxy"
    NETWORK = "network"
    ACCESS = "access"
    NOT_FOUND = "not-found"
    OTHER = "other"


# Ordered: the first kind whose marker a line carries is that line's kind. pip prints the cause in
# its retry warnings and the consequence ("No matching distribution") last, and uv prints the cause
# under "Caused by:", so the cause is looked for before the consequence wherever it appears.
def _code(status: str) -> str:
    """A status code as a whole token: neither a digit, a letter nor a dot on either side, so the
    `403` in version `1.403.0` is not a refusal."""

    return rf"(?<![\w.]){status}(?![\w.])"


_MARKER_TEXT: tuple[tuple[InstallerFailureKind, tuple[str, ...]], ...] = (
    (
        InstallerFailureKind.CERTIFICATE,
        (
            "certificate_verify_failed",
            "certificate verify failed",
            "invalid peer certificate",
            "unknownissuer",
            "self signed certificate",
            "self-signed certificate",
            "sslerror",
            "ssl:",
        ),
    ),
    (
        InstallerFailureKind.PROXY,
        ("proxyerror", "proxy error", "tunnel connection failed", _code("407")),
    ),
    (
        InstallerFailureKind.NETWORK,
        (
            "newconnectionerror",
            "connectionerror",
            "connection refused",
            "name or service not known",
            "nodename nor servname",
            "temporary failure in name resolution",
            "failed to resolve",
            "dns error",
            "network is unreachable",
            "timed out",
        ),
    ),
    (
        InstallerFailureKind.ACCESS,
        (_code("401"), _code("403"), "unauthorized", "forbidden", "authentication"),
    ),
    (
        InstallerFailureKind.NOT_FOUND,
        (
            "no matching distribution",
            "could not find a version that satisfies",
            "no solution found",
            "not found in the package registry",
        ),
    ),
)


#: Each marker is a regular expression over the lowered line: literal text, or a status code from
#: `_code`.
_MARKERS = tuple(
    (
        kind,
        tuple(
            re.compile(marker if marker.startswith("(?") else re.escape(marker))
            for marker in markers
        ),
    )
    for kind, markers in _MARKER_TEXT
)


@dataclass(frozen=True, slots=True)
class InstallerFailure:
    """One line of an installer's output that says why it failed, with credentials redacted."""

    kind: InstallerFailureKind
    line: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, InstallerFailureKind) or not isinstance(self.line, str):
            raise ValueError("an installer failure needs a kind and a line")
        if not self.line or "\n" in self.line:
            raise ValueError("an installer failure is one non-empty line")


def _kind(line: str) -> InstallerFailureKind | None:
    lowered = line.lower()
    for kind, markers in _MARKERS:
        if any(marker.search(lowered) for marker in markers):
            return kind
    return None


def installer_failure(output: str) -> InstallerFailure:
    """The line of `output` that best says why pip or uv failed.

    The first line naming a cause (certificate, proxy, network, access) wins over a line naming the
    consequence (nothing matched), which wins over the last line that calls itself an error, which
    wins over the last line at all. Every candidate is a line of `output` itself, never a
    paraphrase, so the report cannot claim a cause the installer did not give.
    """

    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return InstallerFailure(InstallerFailureKind.OTHER, "(no output)")
    ranked = [(kind, line) for line in lines if (kind := _kind(line)) is not None]
    for wanted in (
        InstallerFailureKind.CERTIFICATE,
        InstallerFailureKind.PROXY,
        InstallerFailureKind.NETWORK,
        InstallerFailureKind.ACCESS,
    ):
        for kind, line in ranked:
            if kind is wanted:
                return InstallerFailure(kind, redact_text(line))
    for kind, line in ranked:
        if kind is InstallerFailureKind.NOT_FOUND:
            return InstallerFailure(kind, redact_text(line))
    errors = [line for line in lines if line.lower().startswith("error")]
    return InstallerFailure(InstallerFailureKind.OTHER, redact_text((errors or lines)[-1]))


_ADVICE = {
    InstallerFailureKind.CERTIFICATE: (
        "The package index's certificate is not trusted. Name your organization's CA bundle in "
        "pip.conf (`cert = <path>`); for uv, set `native-tls = true` in uv.toml."
    ),
    InstallerFailureKind.PROXY: (
        "The proxy refused the connection. Name it in pip.conf (`proxy = <url>`)."
    ),
    InstallerFailureKind.NETWORK: (
        "The package index could not be reached. Check that pip.conf or uv.toml names the index "
        "this machine should use (`index-url = <url>`), and behind a proxy name it in pip.conf "
        "(`proxy = <url>`)."
    ),
    InstallerFailureKind.ACCESS: (
        "The package index refused access. Check the index and its credentials in pip.conf or "
        "uv.toml, or in your keyring."
    ),
    InstallerFailureKind.NOT_FOUND: (
        "The index did not have a matching package. If you use an internal mirror, check that "
        "pip.conf or uv.toml names it and that it carries the package."
    ),
    InstallerFailureKind.OTHER: "",
}


def installer_failure_advice(kind: InstallerFailureKind) -> str:
    """What to try for one kind of failure, or nothing when the kind says nothing actionable."""

    return _ADVICE[kind]


@dataclass(frozen=True, slots=True)
class IndexCheck:
    """Whether one installer, run as aart-cli runs it, reached its package index."""

    reachable: bool
    failure: InstallerFailure | None = None

    def __post_init__(self) -> None:
        if (self.failure is None) is not self.reachable:
            raise ValueError("an index check fails exactly when it carries a failure")


@dataclass(frozen=True, slots=True)
class PythonInstallersReadiness:
    """What aart-cli's own pip and uv runs see on this machine.

    `environment_pip` is the pip version a new artifact environment starts with -- the one bundled
    with the interpreter, not whatever pip that interpreter has since been upgraded to -- and
    `None` when new environments get no pip at all. Index checks are `None` when not asked for.
    """

    interpreter: str
    pip_selectable: bool
    environment_pip: str | None
    uv: str | None
    pip_configuration: tuple[str, ...] = ()
    ignored_settings: tuple[str, ...] = ()
    pip_index: IndexCheck | None = None
    uv_index: IndexCheck | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.interpreter, str) or not self.interpreter:
            raise ValueError("python installer readiness needs the interpreter it observed")
        if self.uv is None and self.uv_index is not None:
            raise ValueError("uv's index cannot be checked without uv")
        if any(not is_installer_setting(name) for name in self.ignored_settings):
            raise ValueError("only installer settings can be reported as ignored")
        object.__setattr__(self, "ignored_settings", tuple(sorted(set(self.ignored_settings))))

    @property
    def needs_attention(self) -> bool:
        """An index that was checked and failed, or new environments that get no pip."""

        return (
            (self.pip_selectable and self.environment_pip is None)
            or (self.pip_index is not None and not self.pip_index.reachable)
            or (self.uv_index is not None and not self.uv_index.reachable)
        )


def _index_data(check: IndexCheck | None) -> dict[str, object] | None:
    if check is None:
        return None
    return {
        "reachable": check.reachable,
        "failure": (
            None
            if check.failure is None
            else {"kind": check.failure.kind.value, "line": check.failure.line}
        ),
    }


def python_installers_to_data(readiness: PythonInstallersReadiness) -> dict[str, object]:
    return {
        "interpreter": readiness.interpreter,
        "needs_attention": readiness.needs_attention,
        "pip": {
            "selectable": readiness.pip_selectable,
            "environment_pip": readiness.environment_pip,
            "configuration": list(readiness.pip_configuration),
            "index": _index_data(readiness.pip_index),
        },
        "uv": {
            "version": readiness.uv,
            "index": _index_data(readiness.uv_index),
        },
        "ignored_settings": list(readiness.ignored_settings),
    }


def _index_lines(name: str, check: IndexCheck | None) -> list[str]:
    if check is None:
        return []
    if check.failure is None:
        return [f"  ✓ {name} reached its package index"]
    lines = [f"  ✗ {name} could not get a package from its index", f"    {check.failure.line}"]
    advice = installer_failure_advice(check.failure.kind)
    if advice:
        lines.append(f"    {advice}")
    return lines


def python_installer_lines(readiness: PythonInstallersReadiness) -> tuple[str, ...]:
    """Doctor's section on pip and uv, as aart-cli itself runs them."""

    lines = ["Python installers (as aart-cli runs them)", f"Interpreter: {readiness.interpreter}"]
    if not readiness.pip_selectable:
        lines.append("– pip is not available to this interpreter")
    elif readiness.environment_pip is None:
        lines.append(
            "✗ New environments get no pip: this interpreter cannot run ensurepip. Install a "
            "Python that includes venv and ensurepip, then install aart-cli with it."
        )
    else:
        lines.append(f"✓ pip {readiness.environment_pip} in new environments")
    if readiness.pip_selectable:
        if readiness.pip_configuration:
            lines.append("  pip configuration:")
            lines.extend(f"    {item}" for item in readiness.pip_configuration)
        else:
            lines.append("  pip configuration: none (pip uses https://pypi.org/simple)")
    lines.extend(_index_lines("pip", readiness.pip_index))
    lines.append(f"✓ uv {readiness.uv}" if readiness.uv else "– uv not found (pip is used)")
    lines.extend(_index_lines("uv", readiness.uv_index))
    if readiness.ignored_settings:
        lines.append(
            "⚠ Set in your shell but not passed to pip or uv: "
            + ", ".join(readiness.ignored_settings)
        )
        lines.append(
            "  aart-cli runs pip and uv without your shell's variables. Put the same settings in "
            "pip.conf or uv.toml."
        )
    if readiness.pip_index is None and readiness.uv_index is None:
        lines.append(
            "To try the package index the way an install does: aart-cli doctor --check-index"
        )
    return tuple(lines)


__all__ = [
    "IndexCheck",
    "InstallerFailure",
    "InstallerFailureKind",
    "PythonInstallersReadiness",
    "ignored_installer_settings",
    "installer_failure",
    "installer_failure_advice",
    "is_installer_setting",
    "python_installer_lines",
    "python_installers_to_data",
]
