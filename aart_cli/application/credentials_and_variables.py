"""Credentials and variables: what one installation's inputs hold, for every front end (§198).

The TUI's Credentials and variables screens and the CLI's `consume inputs` read and change the same
things, so what they say about them is decided once, here: which installation a command names, what
each ordinary value and credential is now, what is still `AART_NOT_SET`, and whether setting a
credential stores it or replaces it. Nothing here reads a file, asks a provider or holds a value
of a credential; the views it takes are the ones the machine was already measured into.
"""

from __future__ import annotations

from dataclasses import dataclass

from aart_cli.domain.inputs import SKIPPED_INPUT

from .consumer_ui import ConsumerActionKind
from .consumer_views import PLACEHOLDER_STATE, ConfigurationFileView, CredentialRecordView


def installation_parts(key: str) -> tuple[str, str, str, str]:
    """An installation key's coordinate, harness label, scope and root (§169.3, D-479).

    A key without an owner is a bare coordinate, which is what such a record is.
    """

    coordinate, separator, rest = key.partition("#")
    if not separator:
        return key, "", "", ""
    label, _, rest = rest.partition("#")
    scope, _, root = rest.partition("#")
    return coordinate, label, scope, root


@dataclass(frozen=True, slots=True)
class InstallationSelector:
    """Which installations a request names: an artifact, and optionally harness and scope.

    `coordinate` is `ALIAS/KIND/NAME`, with or without `@VERSION`; empty names every artifact.
    An empty harness or scope names any.
    """

    coordinate: str
    harness: str = ""
    scope: str = ""


def select_installations(keys: tuple[str, ...], selector: InstallationSelector) -> tuple[str, ...]:
    """The installations among `keys` the selector names, in the order they were given.

    An artifact is named whole: `alias/mcp/git` never names `alias/mcp/github`.
    """

    chosen: list[str] = []
    for key in keys:
        coordinate, label, scope, _ = installation_parts(key)
        if selector.coordinate not in ("", coordinate, coordinate.partition("@")[0]):
            continue
        if selector.harness not in ("", label) or selector.scope not in ("", scope):
            continue
        chosen.append(key)
    return tuple(chosen)


def configuration_identifiers(configurations: tuple[ConfigurationFileView, ...]) -> list[str]:
    """Every ordinary input these files declare or hold, once each and in order."""

    return sorted(
        {
            identifier
            for file in configurations
            for identifier in (*file.inputs, *(item[0] for item in file.values))
        }
    )


@dataclass(frozen=True, slots=True)
class ConfigurationValue:
    """One ordinary input of one installation, as its configuration file holds it."""

    input: str
    #: None where the file does not hold the input at all.
    value: str | None
    path: str
    state: str
    harness: str

    @property
    def placeholder(self) -> bool:
        return self.value == SKIPPED_INPUT


@dataclass(frozen=True, slots=True)
class InstallationInputs:
    """One installation's ordinary values and credentials, and its artifact's documentation."""

    key: str
    configuration: tuple[ConfigurationValue, ...]
    credentials: tuple[CredentialRecordView, ...]
    documentation: str = ""

    @property
    def coordinate(self) -> str:
        return installation_parts(self.key)[0]

    @property
    def harness(self) -> str:
        return installation_parts(self.key)[1]

    @property
    def scope(self) -> str:
        return installation_parts(self.key)[2]

    @property
    def root(self) -> str:
        return installation_parts(self.key)[3]

    @property
    def placeholders(self) -> tuple[str, ...]:
        """Every input, ordinary or credential, still `AART_NOT_SET`, once each and in order."""

        return tuple(
            sorted(
                {
                    *(item.input for item in self.configuration if item.placeholder),
                    *(item.input for item in self.credentials if item.placeholder),
                }
            )
        )

    def declares_configuration(self, input_id: str) -> bool:
        return any(item.input == input_id for item in self.configuration)

    def credential(self, input_id: str) -> CredentialRecordView | None:
        return next((item for item in self.credentials if item.input == input_id), None)


def installation_inputs(
    key: str,
    configurations: tuple[ConfigurationFileView, ...],
    credentials: tuple[CredentialRecordView, ...],
    documentation: str = "",
) -> InstallationInputs:
    """Project one installation's measured configuration files and credentials (§161.8)."""

    values = tuple(
        ConfigurationValue(
            identifier, dict(file.values).get(identifier), file.path, file.state, file.harness
        )
        for identifier in configuration_identifiers(configurations)
        for file in configurations
        if identifier in file.inputs or identifier in dict(file.values)
    )
    return InstallationInputs(key, values, credentials, documentation)


def credential_state(view: CredentialRecordView) -> str:
    """A credential's state in words, never its value; aart-cli never has the value."""

    if view.placeholder:
        return PLACEHOLDER_STATE
    if view.health == "present":
        return "Configured securely"
    return view.health.title()


#: What setting a credential is, by the actions its state offers: a new item is stored, and one
#: already there -- the placeholder too -- is replaced (§161.8).
_SETTING: tuple[tuple[str, ConsumerActionKind], ...] = (
    ("set", ConsumerActionKind.CREDENTIAL_SET),
    ("replace", ConsumerActionKind.CREDENTIAL_REPLACE),
)


def credential_setting(view: CredentialRecordView) -> tuple[str, ConsumerActionKind] | None:
    """Whether setting this credential stores or replaces it, or None while its state is unknown."""

    return next(((word, action) for word, action in _SETTING if word in view.actions), None)


__all__ = [
    "PLACEHOLDER_STATE",
    "ConfigurationValue",
    "InstallationInputs",
    "InstallationSelector",
    "configuration_identifiers",
    "credential_setting",
    "credential_state",
    "installation_inputs",
    "installation_parts",
    "select_installations",
]
