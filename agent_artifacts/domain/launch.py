"""How an installed artifact is started: the declared contract, and POSIX quoting.

The contract is declarative. It names an entrypoint inside the payload and a transport, and it
holds no values -- what the process is given comes from the bound inputs, and where the process
lives comes from the artifact's environment. Keeping those three apart is what lets one plan be
reviewed before anything is written.

`shell_quote` is small and load-bearing. A generated launcher is a shell script, so every value it
carries crosses a parser that will happily execute what it reads. Single quotes are the only POSIX
construct that suspends every expansion, so every value goes inside them and the one character they
cannot contain is spliced rather than escaped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

__all__ = [
    "LAUNCHER_FILENAME",
    "LaunchContract",
    "Transport",
    "launch_contract_to_data",
    "launcher_path",
    "shell_quote",
]

LAUNCHER_FILENAME = "launch.sh"
_ENTRYPOINT_RE = re.compile(r"^[A-Za-z0-9_.][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_.][A-Za-z0-9_.-]*)*$")


class Transport(str, Enum):
    """How a harness talks to the started process."""

    STDIO = "stdio"


def shell_quote(value: str) -> str:
    """`value` as a single POSIX shell word that expands back to exactly `value`.

    NUL is refused rather than dropped. No argument vector can carry it, so a quoter that silently
    truncated there would hand the process a different value than the one that was reviewed.
    """

    if not isinstance(value, str):
        raise ValueError("only a string can be quoted for a shell")
    if "\x00" in value:
        raise ValueError("a shell word cannot contain a null byte")
    return "'" + value.replace("'", "'\\''") + "'"


@dataclass(frozen=True, slots=True)
class LaunchContract:
    """What starts the artifact, said without saying where it is installed.

    `entrypoint` is payload-relative so the same contract survives being installed at a different
    scope, and `arguments` are literal: anything that varies per installation is an input, which
    is reviewed, validated and bound, rather than a string spliced into a command line.
    """

    entrypoint: str
    transport: Transport = Transport.STDIO
    arguments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.entrypoint, str)
            or _ENTRYPOINT_RE.fullmatch(self.entrypoint) is None
        ):
            raise ValueError("launch entrypoint must be a relative path inside the payload")
        if any(part == ".." for part in self.entrypoint.split("/")):
            raise ValueError("launch entrypoint must not climb out of the payload")
        if not isinstance(self.transport, Transport):
            raise ValueError("launch transport is invalid")
        if not isinstance(self.arguments, tuple) or any(
            not isinstance(argument, str) or not argument or "\x00" in argument
            for argument in self.arguments
        ):
            raise ValueError("launch arguments are invalid")


def launcher_path(environment: object) -> str:
    """Where the generated launcher for `environment` belongs."""

    root = getattr(environment, "root", None)
    if not isinstance(root, str) or not root:
        raise ValueError("launcher path needs an artifact environment")
    return f"{root}/{LAUNCHER_FILENAME}"


def launch_contract_to_data(contract: LaunchContract) -> dict[str, object]:
    return {
        "arguments": list(contract.arguments),
        "entrypoint": contract.entrypoint,
        "transport": contract.transport.value,
    }
