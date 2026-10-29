"""Whether a connected Registry runs a newer aart-cli, and how this one is upgraded to it (§211).

A Registry pins the aart-cli its CI runs in `.aart-cli-version`. It may also commit
`.aart-cli-source`, which says where its organisation gets aart-cli from in the names of the CI's
own variables, so the commands offered here are the route that deployment already uses rather than
one that does not work everywhere. Everything here is pure: the pins, the file and how this aart-cli
was installed are read elsewhere and handed in.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.protocol.semver import SemVer, parse_semver

__all__ = [
    "AART_CLI_SOURCE_INVALID",
    "INSTALLER_MARKS",
    "SOURCE_NAMES",
    "AartCliUpdate",
    "Installer",
    "RegistryPin",
    "RunningAartCli",
    "UpdateStep",
    "aart_cli_update",
    "detect_installer",
    "governing_pin",
    "parse_aart_cli_source",
    "upgrade_guidance",
    "upgrade_headline",
    "upgrade_steps",
]

AART_CLI_SOURCE_INVALID = DiagnosticCode("aart-cli-source-invalid")

#: The Registry CI's own variables, in the order its "Provide AART" step tries them (§211).
SOURCE_NAMES = (
    "AART_CLI_PIP_INDEX_URL",
    "AART_CLI_PACKAGE",
    "AART_CLI_WHEEL_URL",
    "AART_CLI_TOOL_PATH",
    "AART_CLI_TOOL_URL",
    "AART_CLI_REPOSITORY",
)
#: What the CI step installs a package from when no index is named.
DEFAULT_INDEX = "https://pypi.org/simple"
_NAME = re.compile(r"[A-Z][A-Z0-9_]*")
# A user name or password before `@` in any address a value carries, where it starts or inside a
# requirement such as `aart-cli @ https://...`.
_USERINFO = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*)://([^/\s?#]*)@")
_SCP = re.compile(r"(?P<user>[^@/\s:]+)@(?P<host>[^/\s:]+):(?P<path>.+)")
#: A Registry origin as a URL: its scheme and the authority the repository is placed beside.
_ORIGIN = re.compile(r"(?P<scheme>https?|ssh)://(?P<netloc>[^/?#\s]+)(?:[/?#]\S*)?", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class RegistryPin:
    """What one connected Registry's current snapshot says about aart-cli."""

    alias: str
    #: `.aart-cli-version` as committed; empty when the snapshot has none.
    pin: str
    #: Where the Registry was connected from, which names the host `AART_CLI_REPOSITORY` is on.
    origin: str
    #: `.aart-cli-source` as committed, or `None` when the Registry has none.
    source: bytes | None = None


class Installer(str, Enum):
    PIP = "pip"
    PIPX = "pipx"
    UV = "uv"
    EDITABLE = "editable"


@dataclass(frozen=True, slots=True)
class RunningAartCli:
    version: SemVer
    #: The interpreter running aart-cli, which a pip install has to use.
    python: str
    installer: Installer
    #: The Git checkout an editable install runs from; empty for any other.
    checkout: str = ""


@dataclass(frozen=True, slots=True)
class UpdateStep:
    """One thing to do: what it is in prose, then the commands for it, bare and copyable."""

    says: str
    commands: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AartCliUpdate:
    current: str
    available: str
    registry: str
    installer: Installer
    steps: tuple[UpdateStep, ...]


#: What pipx and uv each leave at the root of the environment they install a tool into.
INSTALLER_MARKS = {"pipx_metadata.json": Installer.PIPX, "uv-receipt.toml": Installer.UV}


def detect_installer(prefix: str, checkout: str, marks: frozenset[str] = frozenset()) -> Installer:
    """How this aart-cli was installed, from where its environment and its code live.

    A checkout wins: the code runs from it whatever environment it was installed into, and moving
    the checkout is what upgrades it. Then the file pipx or uv left in the environment (`marks`),
    since `PIPX_HOME` and `UV_TOOL_DIR` put it anywhere; then their default paths.
    """

    if checkout:
        return Installer.EDITABLE
    for mark, installer in INSTALLER_MARKS.items():
        if mark in marks:
            return installer
    where = prefix.replace("\\", "/").rstrip("/") + "/"
    if "/pipx/venvs/aart-cli/" in where:
        return Installer.PIPX
    if "/uv/tools/aart-cli/" in where:
        return Installer.UV
    return Installer.PIP


def _read_pin(raw: str) -> SemVer | None:
    # The CI reads the file with `tr -d ' \t\r\n'`, so whitespace anywhere is not part of it.
    parsed = parse_semver(re.sub(r"[ \t\r\n]", "", raw))
    return parsed.value if isinstance(parsed, Ok) else None


def governing_pin(
    pins: tuple[RegistryPin, ...], running: SemVer, *, default_alias: str
) -> tuple[RegistryPin, SemVer] | None:
    """The pin that says which aart-cli this person should run, if it is newer than this one.

    The default Registry's pin governs when it is connected and readable; otherwise the highest,
    and the first alias among equal pins (INV-316).
    """

    readable = sorted(
        ((pin, version) for pin in pins if (version := _read_pin(pin.pin)) is not None),
        key=lambda item: item[0].alias,
    )
    default = [item for item in readable if default_alias and item[0].alias == default_alias]
    if default:
        chosen = default[0]
    elif readable:
        chosen = max(readable, key=lambda item: item[1])
    else:
        return None
    return chosen if chosen[1] > running else None


def _refused(message: str) -> Err:
    return Err((Diagnostic(AART_CLI_SOURCE_INVALID, Severity.ERROR, message),))


def parse_aart_cli_source(raw: bytes) -> Result[dict[str, str]]:
    """Read `.aart-cli-source`, or say why the whole file is refused (INV-317).

    Nothing a refused file says is used: a half-read route could send a person to an address the
    maintainers did not mean. A reason never repeats a value, since the value may be what was
    wrong with it.
    """

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return _refused(".aart-cli-source is not UTF-8 text")
    values: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name, equals, value = stripped.partition("=")
        name, value = name.strip(), value.strip()
        if not equals or _NAME.fullmatch(name) is None:
            return _refused(f".aart-cli-source line {number} is not NAME=value")
        if name not in SOURCE_NAMES:
            return _refused(f".aart-cli-source line {number} names {name}, which it cannot set")
        if name in values:
            return _refused(f".aart-cli-source sets {name} twice")
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            return _refused(f".aart-cli-source {name} holds a control character")
        if '"' in value or "'" in value:
            return _refused(f".aart-cli-source {name} is quoted; write the value without quotes")
        for scheme, userinfo in _USERINFO.findall(value):
            if ":" in userinfo or scheme.lower().removeprefix("git+") in {"http", "https"}:
                return _refused(
                    f".aart-cli-source {name} carries a credential in its address; a sign-in "
                    "belongs to the person's package manager or Git, never to the Registry"
                )
        values[name] = value
    return Ok(values)


def _pip_git(url: str, tag: str) -> str:
    """A Git address as pip, pipx and uv read it, at the tag."""

    if url.startswith("git+"):
        return f"{url}@{tag}"
    scp = _SCP.fullmatch(url)
    if scp is not None and "://" not in url:
        return f"git+ssh://{scp['user']}@{scp['host']}/{scp['path']}@{tag}"
    return f"git+{url}@{tag}"


def _repository_url(origin: str, repository: str) -> str | None:
    """`owner/name` on the Registry's own host, as the CI's `github.server_url` places it."""

    scp = _SCP.fullmatch(origin)
    if scp is not None and "://" not in origin:
        return f"{scp['user']}@{scp['host']}:{repository}.git"
    found = _ORIGIN.fullmatch(origin)
    if found is None:
        return None
    netloc = found["netloc"]
    host = netloc.rpartition("@")[2].split(":", 1)[0]
    if not host:
        return None
    return f"{found['scheme'].lower()}://{netloc}/{repository}.git"


def _install(running: RunningAartCli, *words: str) -> str:
    if running.installer is Installer.PIPX:
        return shlex.join(("pipx", "install", "--force", *words))
    if running.installer is Installer.UV:
        return shlex.join(("uv", "tool", "install", "--force", *words))
    return shlex.join((running.python, "-m", "pip", "install", "--upgrade", "--no-deps", *words))


def _index_words(running: RunningAartCli, index: str) -> tuple[str, ...]:
    # uv names the option differently; its `--index-url` is kept only as a deprecated alias.
    return ("--default-index" if running.installer is Installer.UV else "--index-url", index)


def _route(
    values: Mapping[str, str], pin: RegistryPin, version: str, running: RunningAartCli
) -> tuple[UpdateStep, ...]:
    def expand(name: str) -> str:
        return values.get(name, "").replace("{version}", version)

    if expand("AART_CLI_PACKAGE"):
        index = expand("AART_CLI_PIP_INDEX_URL") or DEFAULT_INDEX
        return (
            UpdateStep(
                f"Install it from the package index {pin.alias} uses:",
                (_install(running, *_index_words(running, index), expand("AART_CLI_PACKAGE")),),
            ),
        )
    if expand("AART_CLI_WHEEL_URL"):
        return (
            UpdateStep(
                f"Install the wheel {pin.alias} uses:",
                (_install(running, expand("AART_CLI_WHEEL_URL")),),
            ),
            UpdateStep(
                "If that address needs a sign-in, download the wheel in a browser, then:",
                ("aart-cli upgrade --wheel FILE",),
            ),
        )
    if expand("AART_CLI_TOOL_PATH"):
        return (
            UpdateStep(
                f"{pin.alias}'s CI takes aart-cli from a directory on its runner, so it names no "
                "place to install it from here. Its maintainers know where that copy comes from."
            ),
        )
    url = expand("AART_CLI_TOOL_URL")
    if not url and expand("AART_CLI_REPOSITORY"):
        url = _repository_url(pin.origin, expand("AART_CLI_REPOSITORY")) or ""
        if not url:
            return (
                UpdateStep(
                    f"{pin.alias} names AART_CLI_REPOSITORY, a repository on its own host, and "
                    "was connected from a local directory, which names no host. Its maintainers "
                    "can set AART_CLI_TOOL_URL in .aart-cli-source instead."
                ),
            )
    if url:
        return (
            UpdateStep(
                f"Install it from the Git repository {pin.alias} uses:",
                (_install(running, _pip_git(url, f"v{version}")),),
            ),
        )
    return _no_route(pin)


def _no_route(pin: RegistryPin) -> tuple[UpdateStep, ...]:
    return (
        UpdateStep(
            f"{pin.alias} does not say where aart-cli comes from. Its maintainers can commit a "
            ".aart-cli-source naming the package index, wheel or Git repository its CI uses."
        ),
    )


def aart_cli_update(
    pins: tuple[RegistryPin, ...], running: RunningAartCli, *, default_alias: str
) -> AartCliUpdate | None:
    """The newer aart-cli to announce and how to install it, or `None` when none is newer."""

    governing = governing_pin(pins, running.version, default_alias=default_alias)
    if governing is None:
        return None
    pin, version = governing
    available = str(version)
    steps: tuple[UpdateStep, ...]
    if running.installer is Installer.EDITABLE:
        # The checkout is what runs, so it is moved; the Registry's route installs another copy.
        steps = (
            UpdateStep(
                "Move the checkout this aart-cli runs from to the release:",
                (
                    shlex.join(("git", "-C", running.checkout, "fetch", "--tags")),
                    shlex.join(("git", "-C", running.checkout, "checkout", f"v{available}")),
                ),
            ),
        )
    elif pin.source is None:
        steps = _no_route(pin)
    else:
        parsed = parse_aart_cli_source(pin.source)
        if isinstance(parsed, Err):
            steps = (
                UpdateStep(
                    f"{pin.alias}'s .aart-cli-source is not used: {parsed.diagnostics[0].message}."
                ),
            )
        else:
            steps = _route(parsed.value, pin, available, running)
    return AartCliUpdate(str(running.version), available, pin.alias, running.installer, steps)


_INSTALLED_WITH = {
    Installer.PIP: "Installed with pip.",
    Installer.PIPX: "Installed with pipx.",
    Installer.UV: "Installed with uv.",
    Installer.EDITABLE: "Running from a Git checkout.",
}


def upgrade_headline(update: AartCliUpdate) -> tuple[str, ...]:
    """Which aart-cli is available, from which Registry, and how this one was installed."""

    return (
        f"aart-cli {update.available} is available: Registry {update.registry} runs it, "
        f"and this is {update.current}.",
        _INSTALLED_WITH[update.installer],
    )


def upgrade_steps(update: AartCliUpdate) -> tuple[str, ...]:
    """Each step in prose with its commands under it, indented and bare, a blank line between."""

    lines: list[str] = []
    for step in update.steps:
        lines += [
            *([""] if lines else []),
            step.says,
            *(f"  {command}" for command in step.commands),
        ]
    return tuple(lines)


def upgrade_guidance(update: AartCliUpdate) -> tuple[str, ...]:
    """What `aart-cli upgrade --how` prints: the headline, then the steps."""

    return (*upgrade_headline(update), "", *upgrade_steps(update))
