"""Where this machine keeps everything `aart-cli` owns: one directory, resolved once.

There used to be three roots and a platform branch -- `Library/Application Support` beside
`Library/Caches` on macOS, `XDG_CONFIG_HOME` beside `XDG_DATA_HOME` beside `XDG_CACHE_HOME` on
Linux -- which meant the same installation had a different shape depending on the machine it ran
on, and a CI job that wanted its own state had three variables to set and could get two of them
right. §169.2 replaces all of it with one answer: `AART_CLI_HOME` if it is set, otherwise
`<user-home>/.aart-cli`, identical on macOS and Linux.

Machine policy is the one thing that does not move. An administrator writes it, and the point of
it is that the person running the command cannot overrule it -- so it cannot live under a
directory that person chooses with an environment variable. It stays where the platform puts
administrator-owned configuration, and `AART_CLI_HOME` does not reach it.

Pure: this module never reads the process environment or the filesystem. The caller resolves the
variable at the process boundary and passes the value in, which is what keeps two machines from
disagreeing about where one installation lives.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from enum import Enum

#: The environment variable that names an explicit application home.
APPLICATION_HOME_VARIABLE = "AART_CLI_HOME"

#: The directory under the user's home used when that variable is not set.
APPLICATION_HOME_DIRECTORY = ".aart-cli"

#: Every entry `aart-cli` writes inside its home, in the order §169.2 lists them. Nothing else in
#: the home belongs to the tool, which is what lets a reset name what it removes instead of
#: removing the directory (D-345).
MANAGED_HOME_ENTRIES: tuple[str, ...] = (
    "config.json",
    "objects",
    "sources",
    "state",
    "cache",
    "locks",
    "tmp",
)


class Platform(str, Enum):
    DARWIN = "darwin"
    LINUX = "linux"


@dataclass(frozen=True, slots=True)
class ConfigPaths:
    application_home: str
    user_config_file: str
    data_root: str
    cache_root: str
    policy_file: str

    def __post_init__(self) -> None:
        for path in (
            self.application_home,
            self.user_config_file,
            self.data_root,
            self.cache_root,
            self.policy_file,
        ):
            if not posixpath.isabs(path) or posixpath.normpath(path) != path:
                raise ValueError("configuration paths must be normalized absolute paths")


def _absolute(path: str, label: str) -> str:
    if not posixpath.isabs(path) or posixpath.normpath(path) != path:
        raise ValueError(f"{label} must be a normalized absolute path")
    return path


def config_lock_directory(paths: ConfigPaths) -> str:
    """The lock guarding compare-and-swap writes of the user configuration (CFG02).

    It sits beside the configuration file so the lock and the file it protects always share a
    directory, and therefore a filesystem.
    """

    return paths.user_config_file + ".lock"


def _policy_file(platform: Platform) -> str:
    if platform is Platform.DARWIN:
        return "/Library/Application Support/aart-cli/policy.json"
    return "/etc/aart-cli/policy.json"


def resolve_config_paths(
    platform: Platform,
    *,
    home: str,
    application_home: str | None = None,
    policy_file: str | None = None,
) -> ConfigPaths:
    """Resolve paths from supplied values; this function never reads the process environment.

    `application_home` is whatever `AART_CLI_HOME` held, already trimmed of nothing: an empty or
    relative value is a mistake the caller should hear about rather than a silent fall back to the
    default, because falling back would write a CI job's state into the developer's own home.
    """

    if not isinstance(platform, Platform):
        raise ValueError("unsupported configuration platform")
    home = _absolute(home, "home")
    if application_home is None:
        root = posixpath.join(home, APPLICATION_HOME_DIRECTORY)
    else:
        root = _absolute(application_home, APPLICATION_HOME_VARIABLE)
    return ConfigPaths(
        root,
        posixpath.join(root, "config.json"),
        root,
        posixpath.join(root, "cache"),
        _absolute(policy_file, "policy override") if policy_file else _policy_file(platform),
    )
