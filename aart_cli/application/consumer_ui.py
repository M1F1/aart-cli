"""Pure interaction reducer for the persistent consumer application.

Terminal adapters hand this module key names and interpret the commands it returns.  The reducer
itself performs no I/O and knows nothing about curses.  Selection, search, help, profile and
navigation therefore remain headlessly testable, and toggling presentation detail cannot touch
semantic plan identity.

Key interpretation lives here too, in :func:`key_event`, because it depends on the mode: while the
search filter is open every printable key is a letter of the query, and a shell that decided that
for itself would eventually let `q` quit instead of typing a q.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum

from aart_cli.authoring.skeleton import GENERATED_KINDS
from aart_cli.domain.configuration_files import configuration_value_problem
from aart_cli.domain.inputs import SKIPPED_INPUT, InputValidation, validate_config_value
from aart_cli.domain.publication import RegistryCommitOrigin, suggested_publication_branch
from aart_cli.domain.registry import RegistryContentMode

from .author_views import AuthorDraft
from .consumer_views import (
    AUTHOR_SCREENS,
    INSTALL_PATH_CUSTOM,
    INSTALL_PATH_DEFAULT,
    SETTING_ROWS,
    SUCCESS_CHOICES,
    ApplicationScreen,
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
    DefaultPathMismatch,
    choose_pair_scope,
    default_harness_from_row,
    installer_from_row,
    is_screen_identifier,
    keeps_focus,
    matrix_columns,
    matrix_from_row,
    navigation_targets,
    pairs_harnesses,
    scope_matrix_columns,
    scope_matrix_from_row,
    target_from_row,
    toggle_matrix_cell,
    usage_harness_from_row,
)
from .maintainer_views import (
    REGISTRY_WORKSPACE_READY_ROW,
    REGISTRY_WORKSPACE_ROW,
    MaintainerCandidateFilter,
    MaintainerScreen,
    parse_candidate_filter_row,
    parse_validation_row,
)

__all__ = [
    "installation_is_mcp",
    "selects_rows",
    "ConsumerActionKind",
    "ConsumerUiCommand",
    "ConsumerUiCommandKind",
    "ConsumerUiEvent",
    "ConsumerUiEventKind",
    "ConsumerUiState",
    "CONFIG_CONTINUE_ROW",
    "CONFIG_SET_LATER_ROW",
    "InstallationConfigDraft",
    "InstallationConfigField",
    "KeyBinding",
    "RegistryDraft",
    "RegistryInitDraft",
    "CollectionDraft",
    "ADOPTION_NAME_ROW",
    "COLLECTION_SAVE_ROW",
    "RepositoryScanDraft",
    "SourceDraft",
    "WorkflowProgressStep",
    "WorkflowStepStatus",
    "key_event",
    "key_bindings",
    "opening_state",
    "reduce_consumer_ui",
    "typing_text",
    "workflow_progress",
]


class ConsumerActionKind(str, Enum):
    """Lifecycle intents the UI may request from the application shell."""

    INSTALL = "install"
    UPDATE = "update"
    VERIFY_REPAIR = "verify-repair"
    UNINSTALL = "uninstall"
    SOURCE_SYNC = "source-sync"
    CANDIDATE_PROMOTION = "candidate-promotion"
    BULK_PROMOTION = "bulk-promotion"
    #: Screen 52's answer: one Collection version defined in the Registry (D-430).
    COLLECTION_DEFINE = "collection-define"
    REGISTRY_ADD = "registry-add"
    REGISTRY_SYNC = "registry-sync"
    REGISTRY_REMOVE = "registry-remove"
    SOURCE_ADD = "source-add"
    SOURCE_REMOVE = "source-remove"
    REGISTRY_INIT = "registry-init"
    REGISTRY_REBUILD = "registry-rebuild"
    REGISTRY_PUSH = "registry-push"
    REPOSITORY_SCAN = "repository-scan"
    REPOSITORY_ADOPT = "repository-adopt"
    REPOSITORY_UPSTREAM_CHECK = "repository-upstream-check"
    REPOSITORY_ADOPT_UPDATE = "repository-adopt-update"
    CREDENTIAL_VERIFY = "credential-verify"
    CREDENTIAL_SET = "credential-set"
    CONFIGURE = "configure"
    CREDENTIAL_REPLACE = "credential-replace"
    CREDENTIAL_DELETE = "credential-delete"
    #: The optional test of a committed install's MCP installations (§170.4). It reads and starts
    #: what was installed and records nothing, so it is never part of the install it follows.
    MCP_TEST = "mcp-test"
    AUTHOR_WORKSPACE = "author-workspace"
    AUTHOR_CHECK = "author-check"
    AUTHOR_INIT = "author-init"


class ConsumerUiEventKind(str, Enum):
    #: PgUp/PgDn on a screen taller than the terminal: half a terminal up or down (§206).
    SCROLL = "scroll"
    NAVIGATE = "navigate"
    BACK = "back"
    MOVE = "move"
    #: Left/Right on screen 05's matrix: which harness column Space ticks (§172.2).
    MOVE_COLUMN = "move-column"
    SET_ROWS = "set-rows"
    SET_SELECTION = "set-selection"
    TOGGLE_PROFILE = "toggle-profile"
    TOGGLE_SELECTION = "toggle-selection"
    TOGGLE_SETTING = "toggle-setting"
    TOGGLE_CANDIDATE_FILTER = "toggle-candidate-filter"
    TOGGLE_PROMOTION_MODE = "toggle-promotion-mode"
    TOGGLE_DETAILS = "toggle-details"
    TOGGLE_EVERYWHERE = "toggle-everywhere"
    SEARCH = "search"
    SEARCH_OPEN = "search-open"
    SEARCH_CLOSE = "search-close"
    HELP = "help"
    QUIT = "quit"
    CONFIRM_QUIT = "confirm-quit"
    REQUEST_ACTION = "request-action"
    ACTION_PREPARED = "action-prepared"
    CONFIRM_ACTION = "confirm-action"
    ACTION_RECORDED = "action-recorded"
    ACTION_FAILED = "action-failed"
    EDIT_AUTHOR = "edit-author"
    EDIT_REGISTRY = "edit-registry"
    EDIT_SOURCE = "edit-source"
    EDIT_REGISTRY_INIT = "edit-registry-init"
    EDIT_COLLECTION = "edit-collection"
    EDIT_REPOSITORY_SCAN = "edit-repository-scan"
    #: 46d: the Registry name a scanned artifact is adopted under, keyed by its scanned coordinate.
    EDIT_ADOPTION_NAME = "edit-adoption-name"
    EDIT_PUBLICATION_BRANCH = "edit-publication-branch"
    EDIT_INSTALL_CONFIG = "edit-install-config"
    EDIT_CONFIGURATION = "edit-configuration"
    #: Enter on a 07b secret row, and the adapter's answer: whether the store now asks for it.
    REQUEST_SECRET = "request-secret"
    SECRET_ASKED = "secret-asked"


@dataclass(frozen=True, slots=True)
class KeyBinding:
    """One key the current screen accepts and the short meaning its footer displays."""

    key: str
    label: str

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str)
            or not value
            or any(character in value for character in "\r\n")
            for value in (self.key, self.label)
        ):
            raise ValueError("a key binding needs a safe key and label")


#: The two transports screen 21a offers, in the order Space cycles them (D-350).  Both reach an
#: approved Registry and neither changes what approval means; what differs is where the bytes are
#: read from.  Authoring Sources are screen 31a's and stay out of this set.
REGISTRY_SOURCE_KINDS: tuple[str, ...] = ("registry-git", "registry-local")


@dataclass(frozen=True, slots=True)
class RegistryDraft:
    """Credential-free input for one approved registry subscription, by either transport."""

    alias: str = ""
    location: str = ""
    ref: str = ""
    make_default: bool = True
    kind: str = REGISTRY_SOURCE_KINDS[0]

    def __post_init__(self) -> None:
        if (
            any(
                not isinstance(value, str) or any(char in value for char in "\r\n")
                for value in (
                    self.alias,
                    self.location,
                    self.ref,
                )
            )
            or not isinstance(self.make_default, bool)
            or self.kind not in REGISTRY_SOURCE_KINDS
        ):
            raise ValueError("registry draft is invalid")

    @property
    def is_local_checkout(self) -> bool:
        """Whether this draft connects a repository already on this machine (D-350)."""

        return self.kind == "registry-local"


#: The two authoring kinds screen 31a offers, in the order Space cycles them.  `registry-git` is
#: deliberately absent: an approved registry is screen 21a's, and 164.2 keeps the two apart.
AUTHORING_SOURCE_KINDS: tuple[str, ...] = ("source-git", "source-local")


@dataclass(frozen=True, slots=True)
class SourceDraft:
    """Credential-free input for one authoring Source subscription (`source-git`/`source-local`).

    It is a separate value from `RegistryDraft` rather than a widened one because the two forms
    collect different things and mean different trust: a registry draft carries `make_default`,
    which an authoring Source can never be, and a source draft carries the kind, which a registry
    never chooses.
    """

    alias: str = ""
    kind: str = AUTHORING_SOURCE_KINDS[0]
    location: str = ""
    ref: str = ""

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or any(char in value for char in "\r\n")
            for value in (self.alias, self.kind, self.location, self.ref)
        ):
            raise ValueError("source draft is invalid")


#: Screen 07's final control is not an input id. Angle brackets cannot occur in an InputId, so an
#: authored field can never collide with it while rows contain an owner and config input id.
CONFIG_CONTINUE_ROW = "<continue>"
#: Screen 07's first row (§172.3): leave every value without an answer as `AART_NOT_SET`, and go on.
CONFIG_SET_LATER_ROW = "<set-later>"


@dataclass(frozen=True, slots=True)
class InstallationConfigField:
    """One non-secret answer held only for the lifetime of the interactive form.

    An optional field left empty is no answer: the input stays unbound and the server applies its
    own default (§187).
    """

    id: str
    value: str = ""
    validation: InputValidation | None = None
    accepted: bool = False
    owner: str = ""
    required: bool = True

    def __post_init__(self) -> None:
        if (
            not isinstance(self.id, str)
            or not self.id
            or any(character in self.id for character in "\r\n")
            or not isinstance(self.value, str)
            or any(character in self.value for character in "\r\n")
            or not (self.validation is None or isinstance(self.validation, InputValidation))
            or not isinstance(self.accepted, bool)
            or not isinstance(self.owner, str)
            or any(character in self.owner for character in "\r\n\t")
            or not isinstance(self.required, bool)
        ):
            raise ValueError("installation config field is invalid")

    @property
    def row(self) -> str:
        """The owner-qualified screen row, retaining the old shape for ownerless fixtures."""

        return f"{self.owner}\t{self.id}" if self.owner else self.id

    @property
    def problem(self) -> str | None:
        return configuration_value_problem(self.value) or validate_config_value(
            self.validation, self.value
        )

    @property
    def unset(self) -> bool:
        """An optional field nobody filled in, which is complete and is not an answer."""

        return not self.required and not self.value


@dataclass(frozen=True, slots=True)
class InstallationConfigDraft:
    """Editable config values, including which defaults a person explicitly accepted."""

    fields: tuple[InstallationConfigField, ...] = ()

    def __post_init__(self) -> None:
        if any(not isinstance(item, InstallationConfigField) for item in self.fields) or len(
            {item.row for item in self.fields}
        ) != len(self.fields):
            raise ValueError("installation config draft is invalid")

    @property
    def ready(self) -> bool:
        return bool(self.fields) and all(
            item.unset or (item.accepted and item.problem is None) for item in self.fields
        )

    @property
    def answers(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (item.row, item.value) for item in self.fields if item.accepted and not item.unset
        )

    def value(self, identifier: str) -> str:
        field = next((item for item in self.fields if item.row == identifier), None)
        if field is None:
            raise ValueError(f"installation config has no field {identifier}")
        return field.value

    def problem(self, identifier: str) -> str | None:
        field = next((item for item in self.fields if item.row == identifier), None)
        if field is None:
            raise ValueError(f"installation config has no field {identifier}")
        return field.problem

    def edit(self, identifier: str, value: str) -> "InstallationConfigDraft":
        if all(item.row != identifier for item in self.fields):
            raise ValueError(f"installation config has no field {identifier}")
        return InstallationConfigDraft(
            tuple(
                replace(item, value=value, accepted=False) if item.row == identifier else item
                for item in self.fields
            )
        )

    def set_later(self) -> "InstallationConfigDraft":
        """Set later (§172.3): every required value without a valid answer becomes `AART_NOT_SET`.

        A value that is there and valid, a declared default included, is an answer and is kept
        (§172.4). An empty value or one with a problem is not an answer, so it is the one skipped.
        An optional one is emptied instead, so it stays unbound and never reaches the server as the
        placeholder's text (§187).
        """

        return InstallationConfigDraft(
            tuple(
                replace(item, accepted=True)
                if item.value and item.problem is None
                else replace(item, value=SKIPPED_INPUT if item.required else "", accepted=True)
                for item in self.fields
            )
        )

    def accept(self, identifier: str) -> "InstallationConfigDraft":
        if all(item.row != identifier for item in self.fields):
            raise ValueError(f"installation config has no field {identifier}")
        return InstallationConfigDraft(
            tuple(
                replace(item, accepted=item.problem is None) if item.row == identifier else item
                for item in self.fields
            )
        )


@dataclass(frozen=True, slots=True)
class RegistryInitDraft:
    """What creating a registry in this project needs, and the one choice it offers (B-090).

    `commit` is the only effect the operator opts into.  The five stages write managed files into
    the checkout either way; whether that becomes a Git commit is a decision about the repository's
    own history, and pushing or merging it is a further decision that is never AART's to make.
    """

    registry_id: str = ""
    display_name: str = ""
    commit: bool = False

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or any(char in value for char in "\r\n")
            for value in (self.registry_id, self.display_name)
        ) or not isinstance(self.commit, bool):
            raise ValueError("registry init draft is invalid")

    def settled(self) -> "RegistryInitDraft":
        """The two text answers with the spaces around them dropped (`QA-058`).

        Screen 46a's status bar offers `[Space] Toggle`, and on a text row a printable key is
        text, so the space it types lands in the answer. Neither text answer can carry one at
        either end, so surrounding whitespace is not part of what the operator named and
        the identity is judged without it.  Settling happens here, at the boundary that judges,
        rather than while typing, because `Manual Registry` has to stay typeable one key at a
        time.
        """

        return replace(
            self,
            registry_id=self.registry_id.strip(),
            display_name=self.display_name.strip(),
        )


@dataclass(frozen=True, slots=True)
class CollectionDraft:
    """Screen 52's text: a new Collection's name, and the summary any Collection carries.

    The members are the session's ticked rows, so Space is the same key it is on every other
    selectable screen. An existing Collection's name is the row it was opened from, not text.
    """

    name: str = ""
    summary: str = ""

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or any(char in value for char in "\r\n")
            for value in (self.name, self.summary)
        ):
            raise ValueError("collection draft is invalid")


@dataclass(frozen=True, slots=True)
class RepositoryScanDraft:
    """The credential-free remote identity read once for artifact-scoped adoption."""

    url: str = ""
    ref: str = ""

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or any(char in value for char in "\r\n")
            for value in (self.url, self.ref)
        ):
            raise ValueError("repository scan draft is invalid")


class ConsumerUiCommandKind(str, Enum):
    RUN_AUTHOR = "run-author"
    LOAD_SCREEN = "load-screen"
    CONFIRM_QUIT = "confirm-quit"
    EXIT = "exit"
    PREPARE_ACTION = "prepare-action"
    EXECUTE_ACTION = "execute-action"
    PERSIST_SETTINGS = "persist-settings"
    #: 07b: mark or unmark one secret row for the credential store to ask while installing
    #: (§172.6). Nothing is typed or read; the answer says only whether it is now marked.
    ASK_SECRET = "ask-secret"
    #: Leaving the install before Ready was confirmed: forget what 07b marked.
    DISCARD_SECRETS = "discard-secrets"


class WorkflowStepStatus(str, Enum):
    """Where one declared screen sits relative to the current workflow position."""

    COMPLETED = "completed"
    CURRENT = "current"
    UPCOMING = "upcoming"


@dataclass(frozen=True, slots=True)
class WorkflowProgressStep:
    screen: ApplicationScreen
    status: WorkflowStepStatus

    def __post_init__(self) -> None:
        if not isinstance(self.screen, (ConsumerScreen, MaintainerScreen)) or not isinstance(
            self.status, WorkflowStepStatus
        ):
            raise ValueError("workflow progress needs a screen and status")


@dataclass(frozen=True, slots=True)
class ConsumerUiEvent:
    kind: ConsumerUiEventKind
    screen: ApplicationScreen | None = None
    action: ConsumerActionKind | None = None
    key: str = ""
    text: str = ""
    accepted: bool | None = None
    rows: tuple[str, ...] = ()
    semantic_identity: str = ""
    selection_identity: str = ""
    review_digest: str = ""
    config_draft: InstallationConfigDraft | None = None
    registry_commit_subject: str = ""
    #: The artifact×harness pairs an install was prepared for, which 05 adopts while it has none.
    pairs: tuple[str, ...] = ()
    #: The scope each of those pairs was prepared for, which 07a then shows as chosen.
    pair_scopes: tuple[str, ...] = ()
    #: §176: the Settings values a Default install could not apply, which 05p then lists.
    default_path_mismatches: tuple[DefaultPathMismatch, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.kind, ConsumerUiEventKind)
            or not _mismatches_valid(self.default_path_mismatches)
            or not _rows_valid(self.pairs)
            or not _rows_valid(self.pair_scopes)
            or (
                self.screen is not None
                and not isinstance(self.screen, (ConsumerScreen, MaintainerScreen))
            )
            or (self.action is not None and not isinstance(self.action, ConsumerActionKind))
            or not isinstance(self.key, str)
            or any(character in self.key for character in "\r\n")
            or not isinstance(self.text, str)
            or any(character in self.text for character in "\r\n")
            or not (self.accepted is None or isinstance(self.accepted, bool))
            or not _rows_valid(self.rows)
            or not _safe_identity(self.semantic_identity)
            or not _safe_identity(self.selection_identity)
            or not _safe_identity(self.review_digest)
            or not _safe_identity(self.registry_commit_subject)
            or (
                self.config_draft is not None
                and not isinstance(self.config_draft, InstallationConfigDraft)
            )
        ):
            raise ValueError("consumer UI event is invalid")


@dataclass(frozen=True, slots=True)
class ConsumerUiCommand:
    kind: ConsumerUiCommandKind
    screen: ApplicationScreen | None = None
    action: ConsumerActionKind | None = None
    selection: tuple[str, ...] = ()
    focus: str = ""
    review_digest: str = ""
    content_mode: RegistryContentMode | None = None
    author_draft: AuthorDraft | None = None
    registry_draft: RegistryDraft | None = None
    source_draft: SourceDraft | None = None
    registry_init_draft: RegistryInitDraft | None = None
    repository_scan_draft: RepositoryScanDraft | None = None
    collection_draft: CollectionDraft | None = None
    #: Screen 46d's typed Registry names, as (scanned coordinate, new name), for the selected
    #: artifacts whose own name the Registry took from another upstream (INV-279).
    adoption_names: tuple[tuple[str, str], ...] = ()
    targets: tuple[str, ...] = ()
    #: The artifact×harness pairs ticked on screen 05's matrix (§172.2), as `pair_key` strings.
    #: `targets` stays the harnesses they go into, so a plan is still prepared for those hosts.
    pairs: tuple[str, ...] = ()
    #: The scope chosen for each pair on screen 07a (§172.5), as `pair_scope_key` strings.
    pair_scopes: tuple[str, ...] = ()
    config_answers: tuple[tuple[str, str], ...] = ()
    #: The scope this one installation chose, or empty to follow the stored preference. It travels
    #: on the command rather than being read from Settings at the boundary, so what was reviewed is
    #: what is executed even if the preference changes in between (issue #11a).
    install_scope: str = ""
    #: Which backend resolves Python dependencies for this one operation, empty meaning "follow the
    #: preference". Separate from `install_scope`: where files land and what resolves them are two
    #: questions, and answering one is not answering the other (issue #11b).
    python_installer: str = ""
    publication_branch: str = ""
    suggested_branch: str = ""
    #: The install takes the Default path (§173.7): its harnesses come from Settings, and nothing
    #: 05 or 07a would ask is asked.
    default_path: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.kind, ConsumerUiCommandKind)
            or (self.author_draft is not None and not isinstance(self.author_draft, AuthorDraft))
            or not isinstance(self.default_path, bool)
            or self.install_scope not in ("", "project", "user")
            or self.python_installer not in ("", "pip", "uv")
            or not _safe_identity(self.publication_branch)
            or not _safe_identity(self.suggested_branch)
            or (
                self.screen is not None
                and not isinstance(self.screen, (ConsumerScreen, MaintainerScreen))
            )
            or (self.action is not None and not isinstance(self.action, ConsumerActionKind))
            or not _rows_valid(self.selection)
            or not _rows_valid(self.targets)
            or not _rows_valid(self.pairs)
            or not _rows_valid(self.pair_scopes)
            or not _config_answers_valid(self.config_answers)
            or not _config_answers_valid(self.adoption_names)
            or not isinstance(self.focus, str)
            or any(character in self.focus for character in "\r\n")
            or not _safe_identity(self.review_digest)
            or (
                self.content_mode is not None
                and not isinstance(self.content_mode, RegistryContentMode)
            )
            or (
                self.registry_draft is not None
                and not isinstance(self.registry_draft, RegistryDraft)
            )
            or (self.source_draft is not None and not isinstance(self.source_draft, SourceDraft))
            or (
                self.registry_init_draft is not None
                and not isinstance(self.registry_init_draft, RegistryInitDraft)
            )
            or (
                self.repository_scan_draft is not None
                and not isinstance(self.repository_scan_draft, RepositoryScanDraft)
            )
            or (
                self.collection_draft is not None
                and not isinstance(self.collection_draft, CollectionDraft)
            )
        ):
            raise ValueError("consumer UI command is invalid")
        if (
            self.kind
            in (
                ConsumerUiCommandKind.PREPARE_ACTION,
                ConsumerUiCommandKind.EXECUTE_ACTION,
            )
            and self.action is None
        ):
            raise ValueError("an action command needs a typed action")
        if self.kind is ConsumerUiCommandKind.EXECUTE_ACTION and not self.review_digest:
            raise ValueError("executing an action needs the reviewed plan identity")


_INITIAL_SESSION = ConsumerSession(ConsumerScreen.DASHBOARD)
_DEFAULT_SETTINGS = ConsumerSettings()

#: Where a filter is meaningful, and where ticking rows is.  Both are properties of the screen,
#: not of the keyboard, so the same key does nothing where the screen has nothing to do with it.
_SEARCHABLE = frozenset(
    {
        ConsumerScreen.MARKETPLACE,
        ConsumerScreen.INSTALLED,
        ConsumerScreen.UPDATES,
        ConsumerScreen.CREDENTIALS,
        ConsumerScreen.ACTIVITY,
        MaintainerScreen.CANDIDATES,
        # Its artifact rows only: on the name and summary rows `/` is a character (§183).
        MaintainerScreen.COLLECTION_EDITOR,
    }
)
_SELECTABLE = frozenset(
    {
        ConsumerScreen.MARKETPLACE,
        ConsumerScreen.COLLECTION_PREVIEW,
        ConsumerScreen.COLLECTION_CUSTOMIZE,
        # Several installations ticked here are uninstalled together (D-393).
        ConsumerScreen.INSTALLED,
        ConsumerScreen.UPDATES,
        ConsumerScreen.REVIEW_SELECTION,
        # 07a's rows are pairs, each put on one scope rather than ticked into the selection.
        ConsumerScreen.INSTALL_SCOPE,
        ConsumerScreen.CONFIGURATION_TARGETS,
        # Screen 47 assembles one registry transaction, so selecting rows is what it is for.
        MaintainerScreen.BULK_PROMOTION,
        MaintainerScreen.SCAN_RESULT,
        # Screen 52's members are ticked the same way; its text rows are the form's own.
        MaintainerScreen.COLLECTION_EDITOR,
    }
)


def selects_rows(screen: ApplicationScreen) -> bool:
    """Whether the session's ticked rows are ticked on this screen, where a count of them is read.

    05 and 23a are selectable too, but what Space ticks there is a harness, held apart from the
    selection; a count of the artifacts ticked on Marketplace says nothing on either (D-401).
    """

    return screen in _SELECTABLE and screen not in (
        ConsumerScreen.REVIEW_SELECTION,
        ConsumerScreen.CONFIGURATION_TARGETS,
    )


def _mismatches_valid(found: tuple[DefaultPathMismatch, ...]) -> bool:
    return (
        isinstance(found, tuple)
        and len(set(found)) == len(found)
        and all(isinstance(item, DefaultPathMismatch) for item in found)
    )


def _rows_valid(rows: tuple[str, ...]) -> bool:
    return (
        isinstance(rows, tuple)
        and len(set(rows)) == len(rows)
        and all(
            isinstance(item, str) and item and not any(character in item for character in "\r\n")
            for item in rows
        )
    )


def _safe_identity(value: str) -> bool:
    return isinstance(value, str) and not any(character in value for character in "\r\n")


def _config_answers_valid(values: tuple[tuple[str, str], ...]) -> bool:
    return (
        isinstance(values, tuple)
        and len({item[0] for item in values if isinstance(item, tuple) and len(item) == 2})
        == len(values)
        and all(
            isinstance(item, tuple)
            and len(item) == 2
            and isinstance(item[0], str)
            and bool(item[0])
            and isinstance(item[1], str)
            and not any(character in item[0] + item[1] for character in "\r\n")
            for item in values
        )
    )


@dataclass(frozen=True, slots=True)
class ConsumerUiState:
    session: ConsumerSession = _INITIAL_SESSION
    settings: ConsumerSettings = _DEFAULT_SETTINGS
    selection: tuple[str, ...] = ()
    search: str = ""
    rows: tuple[str, ...] = ()
    cursor: int = 0
    #: Usable terminal columns, sampled by the shell; never persisted as a preference.
    viewport_columns: int = 100
    viewport_rows: int = 0
    #: The first body line drawn when the screen is taller than the terminal (§206). The shell
    #: stores back the viewport's clamp, so it never runs past the last page.
    scroll: int = 0
    #: Whether the page follows the cursor's row; PgUp/PgDn turn it off, moving turns it on.
    scroll_follows: bool = True
    #: Whether the last frame drawn was taller than the terminal, so PgUp/PgDn are offered.
    scrollable: bool = False
    #: Whether Marketplace draws its columns after Artifact and Type; for this session only (§196).
    marketplace_details: bool = False
    #: Whether Installed and Updates draw theirs after Artifact, Type, Harness and Health (§199).
    installed_details: bool = False
    #: Whether Installed and Updates list every project's installations, not only those an agent
    #: here reaches; for this session only (§210).
    installed_everywhere: bool = False
    focus: str = ""
    searching: bool = False
    help_visible: bool = False
    quit_pending: bool = False
    exited: bool = False
    action: ConsumerActionKind | None = None
    #: The action whose attempted run stopped on this screen. It is not `action`: that plan is
    #: gone, so there is nothing left to confirm, and a review still advertising a confirmation is
    #: offering a key whose only possible answer is that nothing was prepared (`QA-033`).
    failed_action: ConsumerActionKind | None = None
    #: What the Candidate list is narrowed to. Screen 53 edits it; screen 35 obeys it.
    #: The scope this installation chose for itself, or empty to follow `settings.default_scope`.
    #: A one-off choice never rewrites the preference (issue #11a).
    install_scope: str = ""
    #: Which backend resolves Python dependencies for this one operation, empty meaning "follow the
    #: preference". Separate from `install_scope`: where files land and what resolves them are two
    #: questions, and answering one is not answering the other (issue #11b).
    python_installer: str = ""
    candidate_filter: MaintainerCandidateFilter = MaintainerCandidateFilter()
    #: Which promotion the Maintainer is reviewing. Screen 42 chooses it; screens 41 and 43 obey
    #: it. Both modes are composed, so this selects a projection rather than causing one.
    content_mode: RegistryContentMode = RegistryContentMode.SELF_CONTAINED
    author_draft: AuthorDraft = AuthorDraft()
    registry_draft: RegistryDraft = RegistryDraft()
    source_draft: SourceDraft = SourceDraft()
    registry_init_draft: RegistryInitDraft = RegistryInitDraft()
    #: Screen 45 confirms one local commit and then keeps its receipt on screen. This flag lets key
    #: interpretation know whether Enter commits or leaves for the Registry: publication is manual
    #: Git and has no state here (D-255).
    registry_commit_applied: bool = False
    #: Screen 46j's editable new-branch target. It is used only when HEAD is detached or names a
    #: protected/default branch; an eligible current branch remains the only possible target.
    publication_branch: str = ""
    registry_commit_origin: RegistryCommitOrigin | None = None
    registry_commit_subject: str = ""
    repository_scan_draft: RepositoryScanDraft = RepositoryScanDraft()
    collection_draft: CollectionDraft = CollectionDraft()
    #: Screen 46d's typed Registry names, keyed by scanned coordinate (INV-279).
    adoption_names: tuple[tuple[str, str], ...] = ()
    #: The directory this session was launched from, already written for a reader. It is context
    #: for every screen -- an install and a Registry edit land relative to it -- so it is carried
    #: on the state rather than fetched where it is drawn, which keeps the frame off the
    #: filesystem (`QA-053`).
    workspace: str = ""
    #: Harnesses explicitly chosen on screen 05. These are separate from artifact rows because
    #: changing delivery intent must never change which artifacts the request contains (D-260).
    targets: tuple[str, ...] = ()
    #: The artifact×harness pairs ticked on the matrix, and which harness column the cursor is on
    #: (§172.2). `targets` follows the pairs: it is the harnesses some pair goes into.
    pairs: tuple[str, ...] = ()
    pair_scopes: tuple[str, ...] = ()
    #: The 07b rows the credential store asks for while installing (§172.6). Row keys only: no
    #: value of a credential is ever held, here or in the adapter.
    asked_secrets: tuple[str, ...] = ()
    harness_column: int = 0
    #: Non-secret text lives only in this session until it is reviewed and written beside the
    #: artifact. ``config_form_active`` distinguishes the pre-review form from screen 07's later
    #: summary of the immutable plan.
    config_draft: InstallationConfigDraft = InstallationConfigDraft()
    config_form_active: bool = False
    #: The form was submitted for the harnesses chosen on 05 (D-380). The install then goes
    #: forward from it and 05 no longer offers the harness, until a Back to 05 makes it a choice.
    inputs_submitted: bool = False
    #: Screen 05p chose the Default path (§173.7): the install goes past 05 and 07a, to 07, 07b or
    #: Ready, until a Back to 05 makes it Custom.
    install_default: bool = False
    #: §176: why Default does not fit Settings for this selection, drawn on 05p until Install
    #: starts again from where it was asked.
    default_path_mismatches: tuple[DefaultPathMismatch, ...] = ()
    #: The artifact whose two input sections screen 22a shows. Credential drill-down changes
    #: ``focus`` to a provider reference, so this parent identity is carried separately.
    user_inputs_artifact: str = ""
    #: The ordinary input and harness subset currently being edited from screen 22a. They are
    #: separate from installation targets/drafts so leaving one workflow cannot alter the other.
    configuration_input: str = ""
    configuration_targets: tuple[str, ...] = ()
    configuration_draft: InstallationConfigDraft = InstallationConfigDraft()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.session, ConsumerSession)
            or not isinstance(self.settings, ConsumerSettings)
            or self.install_scope not in ("", "project", "user")
            or self.python_installer not in ("", "pip", "uv")
            or not _safe_identity(self.publication_branch)
            or (
                self.registry_commit_origin is not None
                and not isinstance(self.registry_commit_origin, RegistryCommitOrigin)
            )
            or not _safe_identity(self.registry_commit_subject)
            or not _rows_valid(self.rows)
            or not isinstance(self.viewport_columns, int)
            or isinstance(self.viewport_columns, bool)
            or self.viewport_columns < 1
            or not isinstance(self.viewport_rows, int)
            or isinstance(self.viewport_rows, bool)
            or self.viewport_rows < 0
            or not isinstance(self.scroll, int)
            or isinstance(self.scroll, bool)
            or self.scroll < 0
            or not isinstance(self.scroll_follows, bool)
            or not isinstance(self.scrollable, bool)
            or not isinstance(self.marketplace_details, bool)
            or not isinstance(self.installed_details, bool)
            or not isinstance(self.installed_everywhere, bool)
            or not isinstance(self.cursor, int)
            or isinstance(self.cursor, bool)
            or not 0 <= self.cursor < max(len(self.rows), 1)
            or not isinstance(self.focus, str)
            or any(character in self.focus for character in "\r\n")
            or not isinstance(self.searching, bool)
            or not _rows_valid(self.selection)
            or not _rows_valid(self.targets)
            or not _rows_valid(self.pairs)
            or not _rows_valid(self.pair_scopes)
            or not _rows_valid(self.asked_secrets)
            or not isinstance(self.harness_column, int)
            or isinstance(self.harness_column, bool)
            or self.harness_column < 0
            or not isinstance(self.config_draft, InstallationConfigDraft)
            or not isinstance(self.config_form_active, bool)
            or not isinstance(self.inputs_submitted, bool)
            or not isinstance(self.install_default, bool)
            or not _mismatches_valid(self.default_path_mismatches)
            or not isinstance(self.user_inputs_artifact, str)
            or any(character in self.user_inputs_artifact for character in "\r\n")
            or not isinstance(self.configuration_input, str)
            or any(character in self.configuration_input for character in "\r\n")
            or not _rows_valid(self.configuration_targets)
            or not isinstance(self.configuration_draft, InstallationConfigDraft)
            or not isinstance(self.search, str)
            or any(character in self.search for character in "\r\n")
            or not isinstance(self.help_visible, bool)
            or not isinstance(self.quit_pending, bool)
            or not isinstance(self.exited, bool)
            or (self.action is not None and not isinstance(self.action, ConsumerActionKind))
            or (
                self.failed_action is not None
                and not isinstance(self.failed_action, ConsumerActionKind)
            )
            # A plan cannot be both awaiting confirmation and already finished with.
            or (self.action is not None and self.failed_action is not None)
            or not isinstance(self.candidate_filter, MaintainerCandidateFilter)
            or not isinstance(self.workspace, str)
            or any(character in self.workspace for character in "\r\n")
            or not isinstance(self.registry_draft, RegistryDraft)
            or not isinstance(self.source_draft, SourceDraft)
            or not isinstance(self.registry_init_draft, RegistryInitDraft)
            or not isinstance(self.registry_commit_applied, bool)
            or not isinstance(self.repository_scan_draft, RepositoryScanDraft)
            or not isinstance(self.collection_draft, CollectionDraft)
            or not _config_answers_valid(self.adoption_names)
        ):
            raise ValueError("consumer UI state is invalid")
        if self.session.profile is not self.settings.profile:
            object.__setattr__(self, "settings", self.settings.with_profile(self.session.profile))
        if not isinstance(self.author_draft, AuthorDraft):
            raise ValueError("author form is invalid")
        if not self.settings.author_mode and any(
            screen in AUTHOR_SCREENS for screen in (self.session.screen, *self.session.history)
        ):
            raise ValueError("an Author screen needs Author Mode enabled")
        if not self.settings.maintainer_mode and any(
            isinstance(screen, MaintainerScreen)
            for screen in (self.session.screen, *self.session.history)
        ):
            raise ValueError("a Maintainer screen needs Registry Maintainer Mode enabled")

    @property
    def current_row(self) -> str:
        """The row identity the cursor is on, or empty where the screen has no rows."""

        return self.rows[self.cursor] if self.rows else ""


#: Multi-screen jobs whose progress is useful to the operator. Every adjacent pair is an accepted
#: edge in ``navigation_targets``; optional detail/question screens are omitted rather than shown as
#: completed when a real run skipped them. The session history supplies what was actually visited.
_WORKFLOW_ROUTES: tuple[tuple[ApplicationScreen, ...], ...] = (
    (
        MaintainerScreen.CANDIDATES,
        MaintainerScreen.CANDIDATE_DETAILS,
        MaintainerScreen.CANDIDATE_DIFF,
        MaintainerScreen.VALIDATION,
        MaintainerScreen.POLICY_REVIEW,
        MaintainerScreen.PROMOTION_REVIEW,
        MaintainerScreen.PROMOTION_MODE,
        MaintainerScreen.REGISTRY_DIFF,
        MaintainerScreen.REGISTRY_VALIDATION,
        MaintainerScreen.REGISTRY_COMMIT,
    ),
    (
        MaintainerScreen.REGISTRY_DETAILS,
        MaintainerScreen.BULK_PROMOTION,
        MaintainerScreen.REGISTRY_VALIDATION,
        MaintainerScreen.REGISTRY_COMMIT,
    ),
    (
        MaintainerScreen.REGISTRY_DETAILS,
        MaintainerScreen.COLLECTIONS,
        MaintainerScreen.COLLECTION_EDITOR,
        MaintainerScreen.REGISTRY_VALIDATION,
        MaintainerScreen.REGISTRY_COMMIT,
    ),
    (
        MaintainerScreen.SOURCES,
        MaintainerScreen.SOURCE_ADD,
        MaintainerScreen.SOURCE_ADD_REVIEW,
    ),
    (
        MaintainerScreen.SOURCES,
        MaintainerScreen.SOURCE_SYNC,
        MaintainerScreen.SOURCE_SYNC_RESULT,
    ),
    (
        MaintainerScreen.REGISTRY,
        MaintainerScreen.REGISTRY_INIT,
        MaintainerScreen.REGISTRY_INIT_REVIEW,
    ),
    (
        MaintainerScreen.REGISTRY_DETAILS,
        MaintainerScreen.REGISTRY_REBUILD,
        MaintainerScreen.REGISTRY_REBUILD_REVIEW,
    ),
    (
        MaintainerScreen.REGISTRY_DETAILS,
        MaintainerScreen.REPOSITORY_SCAN,
        MaintainerScreen.SCAN_RESULT,
        MaintainerScreen.ADOPTION_REVIEW,
    ),
    (
        ConsumerScreen.REGISTRIES,
        ConsumerScreen.REGISTRY_ADD,
        ConsumerScreen.REGISTRY_REVIEW,
    ),
    (
        ConsumerScreen.MARKETPLACE,
        ConsumerScreen.INSTALL_PATH,
        ConsumerScreen.REVIEW_SELECTION,
        ConsumerScreen.AUTOMATIC_INSPECTION,
        ConsumerScreen.READY,
        ConsumerScreen.INSTALLING,
        ConsumerScreen.SUCCESS,
    ),
    (
        ConsumerScreen.UPDATES,
        ConsumerScreen.UPDATE_INPUTS,
        ConsumerScreen.UPDATING,
        ConsumerScreen.ACTIVITY_DETAILS,
    ),
    (
        ConsumerScreen.INSTALLED_ARTIFACT_DETAILS,
        ConsumerScreen.UNINSTALL_REVIEW,
        ConsumerScreen.UNINSTALLING,
        ConsumerScreen.ACTIVITY_DETAILS,
    ),
    (
        ConsumerScreen.INSTALLED_ARTIFACT_DETAILS,
        ConsumerScreen.VERIFY_REPAIR,
        ConsumerScreen.ACTIVITY_DETAILS,
    ),
    (
        ConsumerScreen.DOCTOR,
        ConsumerScreen.VERIFY_REPAIR,
        ConsumerScreen.ACTIVITY_DETAILS,
    ),
)


def _workflow_route(state: ConsumerUiState) -> tuple[ApplicationScreen, ...] | None:
    """Choose the declared route best supported by the journey actually in session history."""

    for route in _WORKFLOW_ROUTES:
        for current, target in zip(route[:-1], route[1:], strict=True):
            if target not in navigation_targets(current, maintainer_mode=True):
                raise ValueError("workflow progress route is outside the navigation graph")
    candidates = tuple(
        route
        for route in _WORKFLOW_ROUTES
        if state.session.screen in route[1:] and route[0] in state.session.history
    )
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda route: sum(screen in state.session.history for screen in route),
    )


def workflow_progress(state: ConsumerUiState) -> tuple[WorkflowProgressStep, ...]:
    """Project completed/current/upcoming screens from the reducer's real navigation state."""

    if not isinstance(state, ConsumerUiState):
        raise ValueError("workflow progress needs consumer UI state")
    route = _workflow_route(state)
    if route is None:
        return ()
    return tuple(
        WorkflowProgressStep(
            screen,
            (
                WorkflowStepStatus.CURRENT
                if screen is state.session.screen
                else (
                    WorkflowStepStatus.COMPLETED
                    if screen in state.session.history
                    else WorkflowStepStatus.UPCOMING
                )
            ),
        )
        for screen in route
    )


def _same_workflow(current: ApplicationScreen, target: ApplicationScreen) -> bool:
    return any(current in route and target in route for route in _WORKFLOW_ROUTES)


# These reverse-navigation relationships retain one Source or Candidate through optional detail
# screens without adding those screens to the progress chrome (`QA-073`, CP-23/01).
_SUBJECT_PRESERVING_BACK_EDGES = frozenset(
    {
        (MaintainerScreen.SOURCE_DETAILS, MaintainerScreen.SOURCES),
        (MaintainerScreen.SOURCE_SYNC, MaintainerScreen.SOURCE_DETAILS),
        (MaintainerScreen.CANDIDATE_LIFECYCLE, MaintainerScreen.CANDIDATE_DETAILS),
        (MaintainerScreen.PROVENANCE, MaintainerScreen.CANDIDATE_DETAILS),
        (MaintainerScreen.VERSION_CONFLICT, MaintainerScreen.CANDIDATE_DETAILS),
        (MaintainerScreen.PROVENANCE, MaintainerScreen.CANDIDATE_LIFECYCLE),
        (MaintainerScreen.VERSION_CONFLICT, MaintainerScreen.PROVENANCE),
        (MaintainerScreen.VALIDATION_DETAILS, MaintainerScreen.VALIDATION),
        (MaintainerScreen.POLICY_REVIEW, MaintainerScreen.VALIDATION_DETAILS),
        # CP-23 task 12: backing out of a credential action is still about that credential.
        (ConsumerScreen.CREDENTIAL_REVIEW, ConsumerScreen.CREDENTIAL_ACTION),
        # Leaving the MCP test returns to the Success it followed, still about that receipt.
        (ConsumerScreen.MCP_TEST, ConsumerScreen.SUCCESS),
        # ... and to the installation it was asked for from (D-395).
        (ConsumerScreen.MCP_TEST, ConsumerScreen.INSTALLED_ARTIFACT_DETAILS),
        (ConsumerScreen.CREDENTIAL_ACTION, ConsumerScreen.CREDENTIAL_DETAILS),
    }
)


_BARE_CANDIDATE_FOCUS_SCREENS = frozenset(
    {
        MaintainerScreen.CANDIDATE_DETAILS,
        MaintainerScreen.CANDIDATE_DIFF,
        MaintainerScreen.CANDIDATE_LIFECYCLE,
        MaintainerScreen.PROVENANCE,
        MaintainerScreen.VERSION_CONFLICT,
    }
)


def _back_focus(state: ConsumerUiState, target: ApplicationScreen) -> str:
    """Keep one workflow subject, reducing a validation-row pair to its Candidate when needed."""

    if not (
        _same_workflow(state.session.screen, target)
        or (state.session.screen, target) in _SUBJECT_PRESERVING_BACK_EDGES
    ):
        return ""
    focus = state.focus
    if target in _BARE_CANDIDATE_FOCUS_SCREENS:
        row = parse_validation_row(focus)
        if row is not None:
            return row.candidate_id
    return focus


def opening_state(settings: ConsumerSettings, *, workspace: str = "") -> ConsumerUiState:
    """The state a session opens in, at the preferences somebody last chose.

    The session's profile and the stored detail level have to be set together: state validation
    lets the session win, so seeding only the settings would open Fast for somebody who chose
    Verbose and then silently rewrite their preference back.
    """

    if not isinstance(settings, ConsumerSettings):
        raise ValueError("opening the consumer application needs consumer settings")
    return ConsumerUiState(
        session=replace(_INITIAL_SESSION, profile=settings.profile),
        settings=settings,
        workspace=workspace,
    )


#: The draft each form owns, and therefore what "a new one" means when that form is opened.
#: Opening a form and returning to a refused one look alike from the screen and are opposite
#: requirements: `QA-028` wants the first empty, `QA-018`/`D-184` wants the second untouched. This
#: is read only on forward navigation, which is the difference between them.
_FORM_DRAFTS: dict[ApplicationScreen, Callable[[ConsumerUiState], ConsumerUiState]] = {
    ConsumerScreen.AUTHOR_WORKSPACE: lambda state: replace(
        state, author_draft=AuthorDraft(workspace=state.settings.author_workspace)
    ),
    ConsumerScreen.AUTHOR_INIT: lambda state: replace(state, author_draft=AuthorDraft()),
    ConsumerScreen.REGISTRY_ADD: lambda state: replace(state, registry_draft=RegistryDraft()),
    MaintainerScreen.SOURCE_ADD: lambda state: replace(state, source_draft=SourceDraft()),
    MaintainerScreen.REGISTRY_INIT: lambda state: replace(
        state, registry_init_draft=RegistryInitDraft()
    ),
    MaintainerScreen.REPOSITORY_SCAN: lambda state: replace(
        state, repository_scan_draft=RepositoryScanDraft()
    ),
    # The members a Collection opens with are seeded as the editor is entered.
    MaintainerScreen.COLLECTION_EDITOR: lambda state: replace(
        state, collection_draft=CollectionDraft(), selection=()
    ),
}


def _navigate(
    state: ConsumerUiState, screen: ApplicationScreen | None
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    if screen is None or screen not in navigation_targets(
        state.session.screen,
        maintainer_mode=state.settings.maintainer_mode,
        author_mode=state.settings.author_mode,
    ):
        return state, ()
    # What the next screen is about: the row somebody was on, or -- where this screen has no rows
    # of its own -- whatever the screen before it was already about.  A detail opened from a
    # detail is still about the same thing.
    focus = (
        state.focus
        if keeps_focus(state.session.screen, screen)
        else state.current_row or state.focus
    )
    # A dashboard's rows are destinations, so the row somebody was on is where they are going and
    # not what they are looking at. Carrying one forward put `31-sources` into a refusal as if it
    # were a Source alias, and the message then named no Source at all (`QA-077`).
    if is_screen_identifier(focus):
        focus = ""
    configuration_input = state.configuration_input
    configuration_targets = state.configuration_targets
    configuration_draft = state.configuration_draft
    if screen is ConsumerScreen.CONFIGURATION_TARGETS:
        prefix = "configuration:"
        configuration_input = focus[len(prefix) :] if focus.startswith(prefix) else ""
        configuration_targets = ()
        configuration_draft = InstallationConfigDraft()
    elif screen is ConsumerScreen.CONFIGURATION_VALUE:
        configuration_draft = (
            InstallationConfigDraft((InstallationConfigField(configuration_input),))
            if configuration_input
            else InstallationConfigDraft()
        )
    updated = replace(
        state,
        session=state.session.navigate(screen),
        focus=focus,
        user_inputs_artifact=(
            focus
            if screen is ConsumerScreen.USER_INPUT_DETAILS
            and state.session.screen is ConsumerScreen.CREDENTIALS
            else state.user_inputs_artifact
        ),
        configuration_input=configuration_input,
        configuration_targets=configuration_targets,
        configuration_draft=configuration_draft,
        # 07a's columns are scopes, not 05's harnesses: it opens on the first (§209).
        harness_column=(0 if screen is ConsumerScreen.INSTALL_SCOPE else state.harness_column),
        # #50: 05 -> 07 before any plan exists is the way into the form, through 07a when a scope
        # is chosen first (§209); once a plan has been reviewed, 07 is its summary instead.
        config_form_active=(
            state.session.screen
            in (
                ConsumerScreen.REVIEW_SELECTION,
                ConsumerScreen.INSTALL_PATH,
                ConsumerScreen.INSTALL_SCOPE,
            )
            and screen is ConsumerScreen.REQUIRED_INPUTS
            and state.session.review_digest is None
            and bool(state.config_draft.fields)
        ),
        search="",
        help_visible=False,
        quit_pending=False,
        failed_action=None,
    )
    # Only the form being entered is emptied. Each form owns one draft, and entering one is not a
    # reason to discard what somebody typed into another (`QA-028`).
    empty = _FORM_DRAFTS.get(screen)
    if empty is not None:
        updated = empty(updated)
    return updated, (ConsumerUiCommand(ConsumerUiCommandKind.LOAD_SCREEN, screen),)


#: The dashboard each list answers to: the one that declares it as a forward route. A list is a
#: place the reader goes *to* from a dashboard, so leaving it goes back there however they arrived
#: -- Candidates is reachable sideways from the Registry screen, and Esc from it still means "done
#: looking at candidates" rather than "back into whatever finished a moment ago" (`QA-072`).
_OWNING_DASHBOARD: dict[ApplicationScreen, ApplicationScreen] = {
    ConsumerScreen.AUTHOR: ConsumerScreen.DASHBOARD,
    **{
        target: ConsumerScreen.DASHBOARD
        for target in navigation_targets(ConsumerScreen.DASHBOARD, maintainer_mode=False)
    },
    **{
        target: MaintainerScreen.DASHBOARD
        for target in navigation_targets(MaintainerScreen.DASHBOARD, maintainer_mode=True)
    },
}


def _back(state: ConsumerUiState) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    # CP-23 task 06: the install already ran, so the screens behind Success are a finished wizard
    # -- Installing, and Ready still asking to confirm. Leaving goes where Done does.
    if state.session.screen is ConsumerScreen.SUCCESS:
        return _navigate(state, ConsumerScreen.MARKETPLACE)
    owner = _OWNING_DASHBOARD.get(state.session.screen)
    if owner is not None and owner in state.session.history:
        session = state.session.navigate(owner)
    else:
        session = state.session.back()
    if session is state.session:
        return state, ()
    updated = replace(
        state,
        session=session,
        # A wizard-like journey remains about the same stable subject while walking backwards.
        # Browsing back to an unrelated list still clears stale detail focus as before.
        focus=_back_focus(state, session.screen),
        search="",
        help_visible=False,
        quit_pending=False,
        failed_action=None,
        # D-380: going back to 05 is asking to choose again, so the harness is a row there again.
        inputs_submitted=(state.inputs_submitted and session.screen is ConsumerScreen.READY),
    )
    return updated, (ConsumerUiCommand(ConsumerUiCommandKind.LOAD_SCREEN, session.screen),)


def _set_rows(
    state: ConsumerUiState, rows: tuple[str, ...]
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    """Take the rows a screen is currently showing, keeping the cursor on the same row if it is
    still there.  A filter hides rows; it never moves what somebody was looking at, and it never
    unticks anything."""

    standing = state.current_row
    if standing not in rows:
        standing = state.focus
    cursor = rows.index(standing) if standing in rows else 0
    if (
        standing not in rows
        and state.session.screen is MaintainerScreen.COLLECTION_EDITOR
        and state.search
    ):
        # A filter hid the artifact under the cursor: land on the first match, so Space ticks it
        # rather than typing a space into the name (§183).
        cursor = next(
            (
                index
                for index, row in enumerate(rows)
                if row not in ("name", "summary", COLLECTION_SAVE_ROW)
            ),
            cursor,
        )
    if standing not in rows and rows[:1] == (CONFIG_SET_LATER_ROW,) and len(rows) > 1:
        # 07 opens on its first field: Set later is offered first, never pressed by accident.
        cursor = 1
    return replace(state, rows=rows, cursor=cursor), ()


def _set_selection(
    state: ConsumerUiState, selected: tuple[str, ...]
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    """Replace what is ticked, for a screen that opens with an opinion about it.

    A Collection opens with every member ticked, because opening a Collection is asking for the
    Collection. Untick from there; this event is how a screen says so, and it is only ever sent as
    a screen is entered.
    """

    if state.session.screen not in _SELECTABLE:
        return state, ()
    if state.session.screen is ConsumerScreen.CONFIGURATION_TARGETS:
        return (
            replace(
                state,
                configuration_targets=tuple(dict.fromkeys(selected)),
                quit_pending=False,
            ),
            (),
        )
    return replace(state, selection=tuple(dict.fromkeys(selected)), quit_pending=False), ()


def _move(
    state: ConsumerUiState, direction: str
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    if not state.rows or direction not in ("up", "down"):
        return state, ()
    step = -1 if direction == "up" else 1
    return replace(state, cursor=(state.cursor + step) % len(state.rows)), ()


def _move_column(
    state: ConsumerUiState, direction: str
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    columns = matrix_columns(state.rows) or scope_matrix_columns(state.rows)
    if not columns or direction not in ("left", "right"):
        return state, ()
    step = -1 if direction == "left" else 1
    column = (min(state.harness_column, len(columns) - 1) + step) % len(columns)
    return replace(state, harness_column=column, quit_pending=False), ()


def _toggle_selection(
    state: ConsumerUiState, key: str
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    key = key or state.current_row
    if state.session.screen not in _SELECTABLE or not key:
        return state, ()
    if state.session.screen is ConsumerScreen.CONFIGURATION_TARGETS:
        harness = target_from_row(key)
        if harness is None:
            return state, ()
        targets = (
            tuple(item for item in state.configuration_targets if item != harness)
            if harness in state.configuration_targets
            else (*state.configuration_targets, harness)
        )
        return replace(state, configuration_targets=targets, quit_pending=False), ()
    if state.session.screen is ConsumerScreen.INSTALL_SCOPE:
        columns = scope_matrix_columns(state.rows)
        if scope_matrix_from_row(key) is None or not columns:
            return state, ()
        column = columns[min(state.harness_column, len(columns) - 1)]
        pair_scopes = choose_pair_scope(state.rows, state.pair_scopes, key, column)
        if pair_scopes == state.pair_scopes:
            return state, ()
        # A scope is where the files land, so choosing one re-prepares the reviewed plan (§172.5).
        chosen = replace(state, pair_scopes=pair_scopes, quit_pending=False)
        return chosen, (
            ConsumerUiCommand(
                ConsumerUiCommandKind.PREPARE_ACTION,
                action=ConsumerActionKind.INSTALL,
                selection=state.selection,
                targets=state.targets,
                pairs=state.pairs,
                pair_scopes=pair_scopes,
                focus=state.focus,
                config_answers=state.config_draft.answers,
                install_scope=state.install_scope,
                python_installer=state.python_installer,
            ),
        )
    if state.session.screen is ConsumerScreen.REVIEW_SELECTION:
        installer = installer_from_row(key)
        if installer is not None:
            # The plan records which backend will resolve the dependencies, so choosing another one
            # is a different plan to review, not the same plan relabelled (issue #11b). Settings
            # keep saying what they said.
            chosen_installer = replace(state, python_installer=installer, quit_pending=False)
            if state.action is not ConsumerActionKind.INSTALL:
                return chosen_installer, ()
            return chosen_installer, (
                ConsumerUiCommand(
                    ConsumerUiCommandKind.PREPARE_ACTION,
                    action=ConsumerActionKind.INSTALL,
                    selection=state.selection,
                    targets=state.targets,
                    pairs=state.pairs,
                    pair_scopes=state.pair_scopes,
                    focus=state.focus,
                    config_answers=state.config_draft.answers,
                    install_scope=state.install_scope,
                    python_installer=installer,
                ),
            )
        if matrix_from_row(key) is not None:
            columns = matrix_columns(state.rows)
            if not columns:
                return state, ()
            column = columns[min(state.harness_column, len(columns) - 1)]
            pairs = toggle_matrix_cell(state.rows, state.pairs, key, column)
            if pairs == state.pairs:
                return state, ()
            targets = tuple(item for item in columns if item in pairs_harnesses(pairs))
            updated = replace(state, pairs=pairs, targets=targets, quit_pending=False)
        else:
            harness = target_from_row(key)
            if harness is None:
                return state, ()
            targets = (
                tuple(item for item in state.targets if item != harness)
                if harness in state.targets
                else (*state.targets, harness)
            )
            updated = replace(state, targets=targets, quit_pending=False)
        if state.action is not ConsumerActionKind.INSTALL:
            return updated, ()
        request_focus = "" if _install_origin(state) is ConsumerScreen.MARKETPLACE else state.focus
        return updated, (
            ConsumerUiCommand(
                ConsumerUiCommandKind.PREPARE_ACTION,
                action=ConsumerActionKind.INSTALL,
                selection=state.selection,
                targets=targets,
                pairs=updated.pairs,
                pair_scopes=updated.pair_scopes,
                focus=request_focus,
                config_answers=state.config_draft.answers,
                install_scope=state.install_scope,
                python_installer=state.python_installer,
            ),
        )
    if key in state.selection:
        selected = tuple(item for item in state.selection if item != key)
    else:
        selected = (*state.selection, key)
    return replace(state, selection=selected, quit_pending=False), ()


#: The actions reviewed on screen 44 and committed on 45 as one local Registry transaction.
_REGISTRY_TRANSACTIONS = frozenset(
    {
        ConsumerActionKind.CANDIDATE_PROMOTION,
        ConsumerActionKind.BULK_PROMOTION,
        ConsumerActionKind.COLLECTION_DEFINE,
    }
)

_ACTION_REVIEW: dict[tuple[ConsumerActionKind, ApplicationScreen], ApplicationScreen] = {
    (ConsumerActionKind.REGISTRY_ADD, ConsumerScreen.REGISTRY_ADD): ConsumerScreen.REGISTRY_REVIEW,
    # A refresh is requested from the list, where the row being refreshed is the row under the
    # cursor; its review is a screen of its own so the fetch is stated before it happens (B-084).
    (ConsumerActionKind.REGISTRY_SYNC, ConsumerScreen.REGISTRIES): ConsumerScreen.REGISTRY_SYNC,
    (ConsumerActionKind.REGISTRY_REMOVE, ConsumerScreen.REGISTRIES): ConsumerScreen.REGISTRY_REMOVE,
    (ConsumerActionKind.SOURCE_REMOVE, MaintainerScreen.SOURCES): MaintainerScreen.SOURCE_REMOVE,
    (
        ConsumerActionKind.SOURCE_ADD,
        MaintainerScreen.SOURCE_ADD,
    ): MaintainerScreen.SOURCE_ADD_REVIEW,
    (
        ConsumerActionKind.REGISTRY_INIT,
        MaintainerScreen.REGISTRY_INIT,
    ): MaintainerScreen.REGISTRY_INIT_REVIEW,
    (
        ConsumerActionKind.REGISTRY_REBUILD,
        MaintainerScreen.REGISTRY_REBUILD,
    ): MaintainerScreen.REGISTRY_REBUILD_REVIEW,
    (
        ConsumerActionKind.REGISTRY_PUSH,
        MaintainerScreen.REGISTRY_DETAILS,
    ): MaintainerScreen.REGISTRY_PUSH,
    (
        ConsumerActionKind.REPOSITORY_SCAN,
        MaintainerScreen.REPOSITORY_SCAN,
    ): MaintainerScreen.SCAN_RESULT,
    (
        ConsumerActionKind.REPOSITORY_ADOPT,
        MaintainerScreen.SCAN_RESULT,
    ): MaintainerScreen.ADOPTION_REVIEW,
    (
        ConsumerActionKind.REPOSITORY_UPSTREAM_CHECK,
        MaintainerScreen.ADOPTED_ARTIFACTS,
    ): MaintainerScreen.UPSTREAM_CHECK,
    (
        ConsumerActionKind.REPOSITORY_ADOPT_UPDATE,
        MaintainerScreen.UPSTREAM_CHECK,
    ): MaintainerScreen.ADOPTION_REVIEW,
    # Install opens 05p, where the path is chosen (§173.7); Custom goes on to 05.
    (ConsumerActionKind.INSTALL, ConsumerScreen.MARKETPLACE): ConsumerScreen.INSTALL_PATH,
    (
        ConsumerActionKind.INSTALL,
        ConsumerScreen.COLLECTION_PREVIEW,
    ): ConsumerScreen.INSTALL_PATH,
    (
        ConsumerActionKind.INSTALL,
        ConsumerScreen.COLLECTION_CUSTOMIZE,
    ): ConsumerScreen.INSTALL_PATH,
    (ConsumerActionKind.INSTALL, ConsumerScreen.INSTALL_PATH): ConsumerScreen.REVIEW_SELECTION,
    (ConsumerActionKind.UPDATE, ConsumerScreen.UPDATES): ConsumerScreen.UPDATE_INPUTS,
    (
        ConsumerActionKind.VERIFY_REPAIR,
        ConsumerScreen.INSTALLED_ARTIFACT_DETAILS,
    ): ConsumerScreen.VERIFY_REPAIR,
    (ConsumerActionKind.VERIFY_REPAIR, ConsumerScreen.DOCTOR): ConsumerScreen.VERIFY_REPAIR,
    (ConsumerActionKind.UNINSTALL, ConsumerScreen.INSTALLED): ConsumerScreen.UNINSTALL_REVIEW,
    (
        ConsumerActionKind.UNINSTALL,
        ConsumerScreen.INSTALLED_ARTIFACT_DETAILS,
    ): ConsumerScreen.UNINSTALL_REVIEW,
    (
        ConsumerActionKind.UNINSTALL,
        ConsumerScreen.INSTALLED_COLLECTION_DETAILS,
    ): ConsumerScreen.UNINSTALL_REVIEW,
    (ConsumerActionKind.SOURCE_SYNC, MaintainerScreen.SOURCES): MaintainerScreen.SOURCE_SYNC,
    (
        ConsumerActionKind.SOURCE_SYNC,
        MaintainerScreen.SOURCE_DETAILS,
    ): MaintainerScreen.SOURCE_SYNC,
    (
        ConsumerActionKind.CANDIDATE_PROMOTION,
        MaintainerScreen.REGISTRY_DIFF,
    ): MaintainerScreen.REGISTRY_VALIDATION,
    # Screen 47 selects; the transaction it assembles is reviewed and committed on the same two
    # screens a single promotion uses, because it is the same kind of transaction.
    (
        ConsumerActionKind.BULK_PROMOTION,
        MaintainerScreen.BULK_PROMOTION,
    ): MaintainerScreen.REGISTRY_VALIDATION,
    # Screen 52's Collection version is the same kind of Registry transaction, reviewed alike.
    (
        ConsumerActionKind.COLLECTION_DEFINE,
        MaintainerScreen.COLLECTION_EDITOR,
    ): MaintainerScreen.REGISTRY_VALIDATION,
    # CP-23 task 12: screen 24's rows are the actions, and each opens 24a about the same reference.
    (
        ConsumerActionKind.CREDENTIAL_VERIFY,
        ConsumerScreen.CREDENTIAL_ACTION,
    ): ConsumerScreen.CREDENTIAL_REVIEW,
    (
        ConsumerActionKind.CREDENTIAL_SET,
        ConsumerScreen.CREDENTIAL_ACTION,
    ): ConsumerScreen.CREDENTIAL_REVIEW,
    (
        ConsumerActionKind.CREDENTIAL_REPLACE,
        ConsumerScreen.CREDENTIAL_ACTION,
    ): ConsumerScreen.CREDENTIAL_REVIEW,
    (
        ConsumerActionKind.CREDENTIAL_DELETE,
        ConsumerScreen.CREDENTIAL_ACTION,
    ): ConsumerScreen.CREDENTIAL_REVIEW,
    (
        ConsumerActionKind.CONFIGURE,
        ConsumerScreen.CONFIGURATION_VALUE,
    ): ConsumerScreen.CONFIGURATION_REVIEW,
    # §170.4: the offer is a review of its own, so what will be called is stated before it is.
    (ConsumerActionKind.MCP_TEST, ConsumerScreen.SUCCESS): ConsumerScreen.MCP_TEST,
    # The same test at any later time, over installations chosen on Installed (§170.4, D-395).
    (ConsumerActionKind.MCP_TEST, ConsumerScreen.INSTALLED): ConsumerScreen.MCP_TEST,
    (
        ConsumerActionKind.MCP_TEST,
        ConsumerScreen.INSTALLED_ARTIFACT_DETAILS,
    ): ConsumerScreen.MCP_TEST,
}

#: The screens an action can be asked from, which are also the screens a declined preparation
#: returns to (`QA-018`/`D-184`). Derived from `_ACTION_REVIEW` so that adding an action cannot
#: leave a refusal with nowhere to be drawn.
ACTION_REQUEST_SCREENS: frozenset[ApplicationScreen] = frozenset(
    origin for _action, origin in _ACTION_REVIEW
)


#: Actions whose subject is the row under the cursor right now, rather than the row that opened
#: the screen they are requested from. Screen 46h's rows are stages of one run, and the registry
#: alias focused back on screen 46 is not one of them: inheriting it would ask for a run nobody
#: chose, which is what a shell walk-through of the keys found it doing (`QA-025`).
_ROW_IS_THE_REQUEST = frozenset(
    {
        ConsumerActionKind.REGISTRY_REBUILD,
        # Doctor is entered from Dashboard with that screen identifier as navigation focus. Its
        # repair action is about the measured installed issue under the cursor, never "29-doctor".
        ConsumerActionKind.VERIFY_REPAIR,
        # Navigation focus can still name the screen that opened this list. A Registry refresh is
        # always about the visible row, never that stale workflow subject (`QA-043`).
        ConsumerActionKind.REGISTRY_SYNC,
        ConsumerActionKind.REGISTRY_REMOVE,
        ConsumerActionKind.SOURCE_REMOVE,
    }
)


def _request_action(
    state: ConsumerUiState, action: ConsumerActionKind | None
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    if action is None:
        return state, ()
    if (
        action is ConsumerActionKind.INSTALL
        and state.session.screen is ConsumerScreen.MARKETPLACE
        and not state.selection
        and state.current_row
    ):
        state = replace(state, selection=(state.current_row,))
    author_origins = {
        ConsumerActionKind.AUTHOR_WORKSPACE: (ConsumerScreen.AUTHOR_WORKSPACE,),
        ConsumerActionKind.AUTHOR_INIT: (ConsumerScreen.AUTHOR_INIT,),
        ConsumerActionKind.AUTHOR_CHECK: (
            ConsumerScreen.AUTHOR,
            ConsumerScreen.AUTHOR_CHECK,
            ConsumerScreen.AUTHOR_MANIFEST,
        ),
    }
    if action in author_origins:
        if not state.settings.author_mode or state.session.screen not in author_origins[action]:
            return state, ()
        return replace(state, action=action, failed_action=None, quit_pending=False), (
            ConsumerUiCommand(
                ConsumerUiCommandKind.RUN_AUTHOR, action=action, author_draft=state.author_draft
            ),
        )
    if (
        action is ConsumerActionKind.REGISTRY_PUSH
        and state.session.screen is MaintainerScreen.REGISTRY_PUSH
    ):
        if not state.publication_branch:
            return state, ()
        return replace(state, action=action, quit_pending=False), (
            ConsumerUiCommand(
                ConsumerUiCommandKind.PREPARE_ACTION,
                action=action,
                focus=state.focus,
                publication_branch=state.publication_branch,
                suggested_branch=suggested_publication_branch(
                    state.registry_commit_origin,
                    subject=state.registry_commit_subject,
                ).value,
            ),
        )
    if action is ConsumerActionKind.CONFIGURE and (
        not state.configuration_targets or not state.configuration_draft.ready
    ):
        return state, ()
    if (
        action is ConsumerActionKind.INSTALL
        and state.session.screen is ConsumerScreen.REQUIRED_INPUTS
        and state.config_form_active
    ):
        if not state.config_draft.ready:
            return state, ()
        # The form is entered from screen 05 once the harness is chosen (#50) and is not part of
        # its later summary route. Returning to 05 rewinds over the form, so Review -> Required
        # Inputs remains a forward step over the immutable plan rather than back into the form.
        # The Default path rewinds to 05p instead: it never stood on 05 (§173.7).
        session = replace(
            state.session.navigate(
                ConsumerScreen.INSTALL_PATH
                if state.install_default
                else ConsumerScreen.REVIEW_SELECTION
            ),
            semantic_identity=None,
            selection_identity=None,
            review_digest=None,
        )
        prepared = replace(
            state,
            session=session,
            action=action,
            config_form_active=False,
            inputs_submitted=True,
            quit_pending=False,
        )
        command = ConsumerUiCommand(
            ConsumerUiCommandKind.PREPARE_ACTION,
            action=action,
            selection=state.selection,
            targets=state.targets,
            pairs=state.pairs,
            pair_scopes=state.pair_scopes,
            focus=state.focus,
            config_answers=state.config_draft.answers,
            install_scope=(state.install_scope if action is ConsumerActionKind.INSTALL else ""),
            python_installer=(
                state.python_installer if action is ConsumerActionKind.INSTALL else ""
            ),
            default_path=state.install_default,
        )
        return prepared, (
            command,
            ConsumerUiCommand(ConsumerUiCommandKind.LOAD_SCREEN, session.screen),
        )
    if (
        action is ConsumerActionKind.INSTALL
        and state.session.screen is ConsumerScreen.INSTALL_PATH
        and state.current_row == INSTALL_PATH_DEFAULT
    ):
        return _install_by_default(state)
    target = _ACTION_REVIEW.get((action, state.session.screen))
    focus = (
        state.current_row or state.focus
        if action in _ROW_IS_THE_REQUEST
        or (
            action in (ConsumerActionKind.UNINSTALL, ConsumerActionKind.MCP_TEST)
            and state.session.screen is ConsumerScreen.INSTALLED
        )
        else state.focus or state.current_row
    )
    if target is None:
        return state, ()
    # A bulk promotion is defined by what was selected, so an empty selection is not a request.
    if action in (ConsumerActionKind.BULK_PROMOTION, ConsumerActionKind.REPOSITORY_ADOPT):
        if not state.selection:
            return state, ()
    elif action in (ConsumerActionKind.INSTALL, ConsumerActionKind.UPDATE):
        if not state.selection and not (
            action is ConsumerActionKind.INSTALL
            and state.session.screen is not ConsumerScreen.MARKETPLACE
            and _install_origin(state) is not ConsumerScreen.MARKETPLACE
            and focus
        ):
            return state, ()
        if target is ConsumerScreen.INSTALL_PATH:
            # 05p only asks which path; nothing is prepared until one is chosen (§173.7).
            moved, navigation = _navigate(state, target)
            return (
                replace(
                    moved, install_default=False, default_path_mismatches=(), quit_pending=False
                ),
                navigation,
            )
    elif (
        action
        not in (
            ConsumerActionKind.REGISTRY_ADD,
            ConsumerActionKind.SOURCE_ADD,
            ConsumerActionKind.REGISTRY_INIT,
            ConsumerActionKind.REPOSITORY_SCAN,
        )
        and not focus
    ):
        return state, ()

    moved, navigation = _navigate(state, target)
    if moved is state:
        return state, ()
    if ConsumerScreen.MARKETPLACE in (state.session.screen, _install_origin(state)):
        focus = ""
    if action is ConsumerActionKind.CONFIGURE:
        focus = state.user_inputs_artifact
    prepared = replace(
        moved,
        action=action,
        publication_branch=(
            "" if action is ConsumerActionKind.REGISTRY_PUSH else moved.publication_branch
        ),
        quit_pending=False,
        registry_commit_applied=(
            False if action in _REGISTRY_TRANSACTIONS else moved.registry_commit_applied
        ),
    )
    selection = state.selection
    if action in (
        ConsumerActionKind.UNINSTALL,
        ConsumerActionKind.VERIFY_REPAIR,
        ConsumerActionKind.MCP_TEST,
    ):
        # A lifecycle action is about installations: what is ticked on Installed, and there only.
        # Ticks carried from elsewhere -- Marketplace offers, or Installed rows behind an open
        # details screen -- would otherwise outrank the one artifact the screen is about (D-393).
        selection = (
            tuple(key for key in state.selection if key in state.rows)
            if state.session.screen is ConsumerScreen.INSTALLED
            else ()
        )
    command = ConsumerUiCommand(
        ConsumerUiCommandKind.PREPARE_ACTION,
        # The MCP test is about the transaction on Success, or about installations chosen on
        # Installed; the screen it was asked from is what tells the two apart (D-395).
        screen=state.session.screen if action is ConsumerActionKind.MCP_TEST else None,
        action=action,
        selection=selection,
        targets=(
            state.targets
            if action is ConsumerActionKind.INSTALL
            else state.configuration_targets
            if action is ConsumerActionKind.CONFIGURE
            else ()
        ),
        pairs=state.pairs if action is ConsumerActionKind.INSTALL else (),
        pair_scopes=state.pair_scopes if action is ConsumerActionKind.INSTALL else (),
        focus=focus,
        content_mode=(
            state.content_mode
            if action in (ConsumerActionKind.CANDIDATE_PROMOTION, ConsumerActionKind.BULK_PROMOTION)
            else None
        ),
        registry_draft=(
            state.registry_draft if action is ConsumerActionKind.REGISTRY_ADD else None
        ),
        source_draft=(state.source_draft if action is ConsumerActionKind.SOURCE_ADD else None),
        registry_init_draft=(
            state.registry_init_draft if action is ConsumerActionKind.REGISTRY_INIT else None
        ),
        repository_scan_draft=(
            state.repository_scan_draft if action is ConsumerActionKind.REPOSITORY_SCAN else None
        ),
        collection_draft=(
            state.collection_draft if action is ConsumerActionKind.COLLECTION_DEFINE else None
        ),
        adoption_names=(
            tuple(item for item in state.adoption_names if item[0] in selection)
            if action is ConsumerActionKind.REPOSITORY_ADOPT
            else ()
        ),
        install_scope=(state.install_scope if action is ConsumerActionKind.INSTALL else ""),
        python_installer=(state.python_installer if action is ConsumerActionKind.INSTALL else ""),
        config_answers=(
            state.config_draft.answers
            if action is ConsumerActionKind.INSTALL
            else (
                state.configuration_draft.answers if action is ConsumerActionKind.CONFIGURE else ()
            )
        ),
        publication_branch="",
        suggested_branch=(
            suggested_publication_branch(
                state.registry_commit_origin,
                subject=state.registry_commit_subject,
            ).value
            if action is ConsumerActionKind.REGISTRY_PUSH
            else ""
        ),
    )
    return prepared, (command, *navigation)


def _install_origin(state: ConsumerUiState) -> ApplicationScreen | None:
    """The screen Install was pressed on, looking past 05p and 05, which only answer it."""

    trail = (*state.session.history, state.session.screen)
    return next(
        (
            item
            for item in reversed(trail)
            if item not in (ConsumerScreen.INSTALL_PATH, ConsumerScreen.REVIEW_SELECTION)
        ),
        None,
    )


def _install_by_default(
    state: ConsumerUiState,
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    """05p's Default (§173.7): prepare from Settings, staying on 05p until the answer says where.

    Nothing chosen on an earlier Custom attempt is carried: the harnesses, scopes and installer are
    the Settings ones, so the request names none of them.
    """

    if not state.selection and not state.focus:
        return state, ()
    session = replace(
        state.session, semantic_identity=None, selection_identity=None, review_digest=None
    )
    prepared = replace(
        state,
        session=session,
        action=ConsumerActionKind.INSTALL,
        install_default=True,
        default_path_mismatches=(),
        targets=(),
        pairs=(),
        pair_scopes=(),
        asked_secrets=(),
        harness_column=0,
        config_draft=InstallationConfigDraft(),
        config_form_active=False,
        inputs_submitted=False,
        install_scope="",
        python_installer="",
        quit_pending=False,
    )
    focus = "" if _install_origin(state) is ConsumerScreen.MARKETPLACE else state.focus
    return prepared, (
        ConsumerUiCommand(
            ConsumerUiCommandKind.PREPARE_ACTION,
            action=ConsumerActionKind.INSTALL,
            selection=state.selection,
            focus=focus,
            default_path=True,
        ),
    )


def _default_path_unfit(
    state: ConsumerUiState, found: tuple[DefaultPathMismatch, ...]
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    """§176: Default does not fit Settings, so 05p stays, lists why, and offers Custom.

    Nothing is pending afterwards: no plan was made, so no identity is kept and no form is open.
    The cursor moves to Custom, the path that can choose what Settings could not.
    """

    session = replace(
        state.session, semantic_identity=None, selection_identity=None, review_digest=None
    )
    return (
        replace(
            state,
            session=session,
            action=None,
            install_default=False,
            default_path_mismatches=found,
            cursor=(
                state.rows.index(INSTALL_PATH_CUSTOM)
                if INSTALL_PATH_CUSTOM in state.rows
                else state.cursor
            ),
            config_draft=InstallationConfigDraft(),
            config_form_active=False,
            inputs_submitted=False,
            quit_pending=False,
        ),
        (),
    )


def _declined_preparation(
    state: ConsumerUiState,
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    """`QA-018`: a refusal leaves no screen that still asks to confirm something.

    The review screen is opened before the adapter is asked to prepare, because consent is given on
    it. When the preparation refuses, that screen is about a plan that does not exist -- it went on
    saying "press Enter to connect", and Enter reached the execution boundary with nothing pending.
    The session returns to the screen the review was opened from, which for a form is the form with
    everything the operator typed still in it, and the pending action is cleared so a later Enter
    cannot reach a confirmation at all. The refusal itself is already on that screen: the adapter
    sent it as a notice with this event.
    """

    cleared = replace(state, action=None, quit_pending=False, install_default=False)
    session = state.session.back()
    # 05p only chose the path, so a refused install returns past it, to where Install was asked.
    if session.screen is ConsumerScreen.INSTALL_PATH and state.session.screen is not session.screen:
        session = session.back()
    if session is state.session:
        return cleared, ()
    return (
        replace(cleared, session=session, help_visible=False, search=""),
        (ConsumerUiCommand(ConsumerUiCommandKind.LOAD_SCREEN, session.screen),),
    )


def _action_prepared(
    state: ConsumerUiState, event: ConsumerUiEvent
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    action = event.action
    if action is None or action is not state.action:
        return state, ()
    on_path = state.install_default and state.session.screen is ConsumerScreen.INSTALL_PATH
    if action is ConsumerActionKind.INSTALL and on_path and event.default_path_mismatches:
        return _default_path_unfit(state, event.default_path_mismatches)
    if (
        action is ConsumerActionKind.INSTALL
        and event.pairs
        and not state.pairs
        and (state.session.screen is ConsumerScreen.REVIEW_SELECTION or on_path)
    ):
        # §172.2: what the preparation ticked by default is ticked on screen too, so the plan
        # and the matrix agree and Continue can go on without a keypress that changes nothing.
        state = replace(state, pairs=event.pairs, targets=pairs_harnesses(event.pairs))
    if action is ConsumerActionKind.INSTALL:
        # A new plan names new provider items, so whatever 07b marked was for another one; the
        # adapter has already forgotten it.
        state = replace(state, asked_secrets=())
    if action is ConsumerActionKind.INSTALL and event.pair_scopes:
        # §172.5: the adapter merged what 07a chose with each pair's starting scope; that merge is
        # what the plan was prepared for, so it is what 07a shows.
        state = replace(state, pair_scopes=event.pair_scopes)
    if action is ConsumerActionKind.INSTALL and event.config_draft is not None and on_path:
        # §173.7: Default goes straight to 07 with the Settings harnesses. When they leave some
        # artifact without a harness, the choice is the person's after all, so 05 asks it.
        session = replace(
            state.session, semantic_identity=None, selection_identity=None, review_digest=None
        )
        answered = replace(
            state,
            session=session,
            config_draft=event.config_draft,
            config_form_active=False,
            inputs_submitted=False,
            install_default=bool(event.config_draft.fields),
            quit_pending=False,
        )
        return _navigate(
            answered,
            ConsumerScreen.REQUIRED_INPUTS
            if event.config_draft.fields
            else ConsumerScreen.REVIEW_SELECTION,
        )
    if (
        action is ConsumerActionKind.INSTALL
        and event.config_draft is not None
        and state.session.screen is ConsumerScreen.INSTALL_SCOPE
    ):
        # §209: a scope chosen before the form is prepared again and still needs the form. The
        # questions are the same, so what was already typed into them is kept.
        typed = {item.row: item for item in state.config_draft.fields}
        draft = InstallationConfigDraft(
            tuple(typed.get(item.row, item) for item in event.config_draft.fields)
        )
        return replace(state, config_draft=draft, quit_pending=False), ()
    if action is ConsumerActionKind.INSTALL and event.config_draft is not None:
        if state.session.screen is not ConsumerScreen.REVIEW_SELECTION:
            return state, ()
        # #50: the answer to a preparation that still needs inputs is not the form yet. It stays
        # on 05, where the harness is chosen; the draft holds only the fields of the harnesses
        # already chosen, and Continue opens it. Any earlier plan is gone with its identities.
        session = replace(
            state.session,
            semantic_identity=None,
            selection_identity=None,
            review_digest=None,
        )
        return (
            replace(
                state,
                session=session,
                config_draft=event.config_draft,
                config_form_active=False,
                inputs_submitted=False,
                quit_pending=False,
            ),
            (
                ConsumerUiCommand(
                    ConsumerUiCommandKind.LOAD_SCREEN,
                    ConsumerScreen.REVIEW_SELECTION,
                ),
            ),
        )
    if not event.review_digest:
        return _declined_preparation(state)
    # Scanning is the completed read-only action: the result is now on screen and there is no
    # mutation waiting for confirmation.  Adoption starts a separate reviewed action from it.
    # Verifying a credential is the same kind of answer: the provider was asked while preparing,
    # and nothing is left to confirm (D-262).
    if action in (
        ConsumerActionKind.REPOSITORY_SCAN,
        ConsumerActionKind.REPOSITORY_UPSTREAM_CHECK,
        ConsumerActionKind.CREDENTIAL_VERIFY,
    ):
        return replace(state, action=None, quit_pending=False), ()
    if action in (ConsumerActionKind.INSTALL, ConsumerActionKind.UPDATE) and (
        not event.semantic_identity or not event.selection_identity
    ):
        return state, ()
    session = replace(
        state.session,
        semantic_identity=event.semantic_identity or None,
        selection_identity=event.selection_identity or None,
        review_digest=event.review_digest,
    )
    if action is ConsumerActionKind.INSTALL and on_path and event.screen is not None:
        # §173.7: the Settings plan goes on to 07b or Ready; 05 only if it left a choice open.
        reviewed = replace(
            state,
            session=session,
            config_form_active=False,
            install_default=event.screen is not ConsumerScreen.REVIEW_SELECTION,
            quit_pending=False,
        )
        return _navigate(reviewed, event.screen)
    if (
        action is ConsumerActionKind.INSTALL
        and state.inputs_submitted
        and state.session.screen is ConsumerScreen.REVIEW_SELECTION
        and event.screen is not None
        and event.screen is not ConsumerScreen.REVIEW_SELECTION
    ):
        # D-380: the answers are in, so the plan goes on to whatever needs deciding next rather
        # than back through the harness choice and a second Required Inputs.
        reviewed = replace(state, session=session, config_form_active=False, quit_pending=False)
        return _navigate(reviewed, event.screen)
    return replace(
        state,
        session=session,
        config_form_active=False,
        publication_branch=(
            event.text
            if action is ConsumerActionKind.REGISTRY_PUSH and event.text
            else state.publication_branch
        ),
        quit_pending=False,
    ), ()


_ACTION_RUNNING: dict[tuple[ConsumerActionKind, ApplicationScreen], ApplicationScreen | None] = {
    (ConsumerActionKind.REGISTRY_ADD, ConsumerScreen.REGISTRY_REVIEW): None,
    (ConsumerActionKind.REGISTRY_SYNC, ConsumerScreen.REGISTRY_SYNC): None,
    (ConsumerActionKind.REGISTRY_REMOVE, ConsumerScreen.REGISTRY_REMOVE): None,
    (ConsumerActionKind.SOURCE_REMOVE, MaintainerScreen.SOURCE_REMOVE): None,
    (ConsumerActionKind.SOURCE_ADD, MaintainerScreen.SOURCE_ADD_REVIEW): None,
    (ConsumerActionKind.REGISTRY_INIT, MaintainerScreen.REGISTRY_INIT_REVIEW): None,
    (ConsumerActionKind.REGISTRY_REBUILD, MaintainerScreen.REGISTRY_REBUILD_REVIEW): None,
    (ConsumerActionKind.REPOSITORY_ADOPT, MaintainerScreen.ADOPTION_REVIEW): None,
    (ConsumerActionKind.REPOSITORY_ADOPT_UPDATE, MaintainerScreen.ADOPTION_REVIEW): None,
    (ConsumerActionKind.INSTALL, ConsumerScreen.READY): ConsumerScreen.INSTALLING,
    (ConsumerActionKind.UPDATE, ConsumerScreen.UPDATE_INPUTS): ConsumerScreen.UPDATING,
    (
        ConsumerActionKind.VERIFY_REPAIR,
        ConsumerScreen.VERIFY_REPAIR,
    ): None,
    (ConsumerActionKind.UNINSTALL, ConsumerScreen.UNINSTALL_REVIEW): ConsumerScreen.UNINSTALLING,
    (ConsumerActionKind.SOURCE_SYNC, MaintainerScreen.SOURCE_SYNC): None,
    (
        ConsumerActionKind.CANDIDATE_PROMOTION,
        MaintainerScreen.REGISTRY_COMMIT,
    ): None,
    (
        ConsumerActionKind.BULK_PROMOTION,
        MaintainerScreen.REGISTRY_COMMIT,
    ): None,
    (
        ConsumerActionKind.COLLECTION_DEFINE,
        MaintainerScreen.REGISTRY_COMMIT,
    ): None,
    (ConsumerActionKind.CREDENTIAL_REPLACE, ConsumerScreen.CREDENTIAL_REVIEW): None,
    (ConsumerActionKind.CREDENTIAL_SET, ConsumerScreen.CREDENTIAL_REVIEW): None,
    (ConsumerActionKind.CREDENTIAL_DELETE, ConsumerScreen.CREDENTIAL_REVIEW): None,
    (ConsumerActionKind.CONFIGURE, ConsumerScreen.CONFIGURATION_REVIEW): None,
    (ConsumerActionKind.REGISTRY_PUSH, MaintainerScreen.REGISTRY_PUSH): None,
    (ConsumerActionKind.MCP_TEST, ConsumerScreen.MCP_TEST): None,
}


def _confirm_action(
    state: ConsumerUiState,
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    action, review_digest = state.action, state.session.review_digest
    if action is None or review_digest is None:
        return state, ()
    key = (action, state.session.screen)
    if key not in _ACTION_RUNNING:
        return state, ()
    command = ConsumerUiCommand(
        ConsumerUiCommandKind.EXECUTE_ACTION,
        action=action,
        selection=state.selection,
        targets=(
            state.targets
            if action is ConsumerActionKind.INSTALL
            else state.configuration_targets
            if action is ConsumerActionKind.CONFIGURE
            else ()
        ),
        pairs=state.pairs if action is ConsumerActionKind.INSTALL else (),
        pair_scopes=state.pair_scopes if action is ConsumerActionKind.INSTALL else (),
        focus=state.focus,
        review_digest=review_digest,
        config_answers=(
            state.config_draft.answers
            if action is ConsumerActionKind.INSTALL
            else (
                state.configuration_draft.answers if action is ConsumerActionKind.CONFIGURE else ()
            )
        ),
    )
    target = _ACTION_RUNNING[key]
    if target is None:
        return replace(state, quit_pending=False), (command,)
    moved, navigation = _navigate(state, target)
    return moved, (command, *navigation)


_ACTION_RESULT: dict[tuple[ConsumerActionKind, ApplicationScreen], ApplicationScreen] = {
    (ConsumerActionKind.REGISTRY_ADD, ConsumerScreen.REGISTRY_REVIEW): ConsumerScreen.REGISTRIES,
    (ConsumerActionKind.REGISTRY_SYNC, ConsumerScreen.REGISTRY_SYNC): ConsumerScreen.REGISTRIES,
    (ConsumerActionKind.REGISTRY_REMOVE, ConsumerScreen.REGISTRY_REMOVE): ConsumerScreen.REGISTRIES,
    (ConsumerActionKind.SOURCE_REMOVE, MaintainerScreen.SOURCE_REMOVE): MaintainerScreen.SOURCES,
    (
        ConsumerActionKind.SOURCE_ADD,
        MaintainerScreen.SOURCE_ADD_REVIEW,
    ): MaintainerScreen.SOURCES,
    (
        ConsumerActionKind.REGISTRY_INIT,
        MaintainerScreen.REGISTRY_INIT_REVIEW,
    ): MaintainerScreen.REGISTRY,
    (
        ConsumerActionKind.REGISTRY_REBUILD,
        MaintainerScreen.REGISTRY_REBUILD_REVIEW,
    ): MaintainerScreen.REGISTRY,
    (ConsumerActionKind.REGISTRY_PUSH, MaintainerScreen.REGISTRY_PUSH): MaintainerScreen.REGISTRY,
    (ConsumerActionKind.INSTALL, ConsumerScreen.INSTALLING): ConsumerScreen.SUCCESS,
    (ConsumerActionKind.UPDATE, ConsumerScreen.UPDATING): ConsumerScreen.ACTIVITY_DETAILS,
    (
        ConsumerActionKind.VERIFY_REPAIR,
        ConsumerScreen.VERIFY_REPAIR,
    ): ConsumerScreen.ACTIVITY_DETAILS,
    (ConsumerActionKind.UNINSTALL, ConsumerScreen.UNINSTALLING): ConsumerScreen.ACTIVITY_DETAILS,
    (
        ConsumerActionKind.SOURCE_SYNC,
        MaintainerScreen.SOURCE_SYNC,
    ): MaintainerScreen.SOURCE_SYNC_RESULT,
    (
        ConsumerActionKind.REPOSITORY_ADOPT,
        MaintainerScreen.ADOPTION_REVIEW,
    ): MaintainerScreen.REGISTRY,
    (
        ConsumerActionKind.REPOSITORY_ADOPT_UPDATE,
        MaintainerScreen.ADOPTION_REVIEW,
    ): MaintainerScreen.REGISTRY,
    # A replaced credential is still there to look at; a deleted one is not, so its list is.
    (
        ConsumerActionKind.CREDENTIAL_REPLACE,
        ConsumerScreen.CREDENTIAL_REVIEW,
    ): ConsumerScreen.CREDENTIAL_DETAILS,
    (
        ConsumerActionKind.CREDENTIAL_SET,
        ConsumerScreen.CREDENTIAL_REVIEW,
    ): ConsumerScreen.CREDENTIAL_DETAILS,
    (
        ConsumerActionKind.CREDENTIAL_DELETE,
        ConsumerScreen.CREDENTIAL_REVIEW,
    ): ConsumerScreen.CREDENTIALS,
    (
        ConsumerActionKind.CONFIGURE,
        ConsumerScreen.CONFIGURATION_REVIEW,
    ): ConsumerScreen.USER_INPUT_DETAILS,
}


#: The screens an action states itself on: the review it opens before running, and the screen the
#: run lands on afterwards. Derived for the same reason the request screens are -- a review whose
#: plan is not drawn is a screen asking somebody to confirm nothing, and a result whose stages are
#: not drawn is a run that reports only that it happened (`QA-024`).
ACTION_ANSWER_SCREENS: frozenset[ApplicationScreen] = frozenset(
    _ACTION_REVIEW.values()
) | frozenset(_ACTION_RESULT.values())


def _owning_screen(
    action: ConsumerActionKind, screen: ApplicationScreen
) -> ApplicationScreen | None:
    """Where a run confirmed on this screen belongs once it is over, however it ended.

    A refused run and a recorded one leave for the same place, because the operator was never
    asking to be on a review screen: they were asking for the run, and the run is finished.
    """

    return _ACTION_RESULT.get((action, screen))


def _action_failed(
    state: ConsumerUiState, event: ConsumerUiEvent
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    """An attempted run stopped, so its review becomes the finished result of that attempt.

    The screen does not move. The refusal is drawn where it was caused, and moving away from it
    would take the explanation with it. What changes is that there is no plan left to confirm:
    `action` clears, and `failed_action` says which run this screen is now the end of (`QA-033`).
    """

    action = event.action
    if action is None or action is not state.action:
        return state, ()
    return replace(state, action=None, failed_action=action, quit_pending=False), ()


def _action_recorded(
    state: ConsumerUiState, event: ConsumerUiEvent
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    action = event.action
    if action is None or action is not state.action or not event.text:
        return state, ()
    if action in (
        ConsumerActionKind.AUTHOR_WORKSPACE,
        ConsumerActionKind.AUTHOR_CHECK,
        ConsumerActionKind.AUTHOR_INIT,
    ):
        settings = (
            replace(state.settings, author_workspace=event.text)
            if action is ConsumerActionKind.AUTHOR_WORKSPACE
            else state.settings
        )
        author_target = (
            ConsumerScreen.AUTHOR
            if action is ConsumerActionKind.AUTHOR_WORKSPACE
            else ConsumerScreen.AUTHOR_CHECK
        )
        session = (
            state.session
            if state.session.screen is author_target
            else state.session.navigate(author_target)
        )
        return replace(
            state,
            session=session,
            settings=settings,
            action=None,
            focus="" if action is ConsumerActionKind.AUTHOR_WORKSPACE else event.text,
            quit_pending=False,
        ), (ConsumerUiCommand(ConsumerUiCommandKind.LOAD_SCREEN, author_target),)
    if action is ConsumerActionKind.MCP_TEST:
        # The answer is drawn where it was asked for, and Success behind it is unchanged: a test
        # is not a lifecycle result, so it moves nothing and clears nothing the install left.
        return replace(state, action=None, quit_pending=False), ()
    origins = {
        ConsumerActionKind.REGISTRY_INIT: RegistryCommitOrigin.INIT_REGISTRY,
        ConsumerActionKind.REGISTRY_REBUILD: RegistryCommitOrigin.REBUILD_REGISTRY,
        ConsumerActionKind.CANDIDATE_PROMOTION: RegistryCommitOrigin.PROMOTE,
        ConsumerActionKind.BULK_PROMOTION: RegistryCommitOrigin.BULK_PROMOTE,
        ConsumerActionKind.COLLECTION_DEFINE: RegistryCommitOrigin.DEFINE_COLLECTION,
    }
    commit_origin = origins.get(action, state.registry_commit_origin)
    commit_subject = (
        event.registry_commit_subject
        if action is ConsumerActionKind.CANDIDATE_PROMOTION
        else ""
        if action in origins
        else state.registry_commit_subject
    )
    if (
        action in _REGISTRY_TRANSACTIONS
        and state.session.screen is MaintainerScreen.REGISTRY_COMMIT
    ):
        return replace(
            state,
            selection=(),
            quit_pending=False,
            action=None,
            registry_commit_applied=True,
            registry_commit_origin=commit_origin,
            registry_commit_subject=commit_subject,
        ), (ConsumerUiCommand(ConsumerUiCommandKind.LOAD_SCREEN, state.session.screen),)
    target = _owning_screen(action, state.session.screen)
    if target is None:
        return state, ()
    moved, commands = _navigate(state, target)
    focus = (
        state.focus
        if action in (ConsumerActionKind.SOURCE_SYNC, ConsumerActionKind.REGISTRY_SYNC)
        else event.text
    )
    return replace(
        moved,
        selection=(),
        targets=(),
        pairs=(),
        pair_scopes=(),
        harness_column=0,
        config_draft=InstallationConfigDraft(),
        config_form_active=False,
        inputs_submitted=False,
        install_default=False,
        focus=focus,
        quit_pending=False,
        action=None,
        registry_commit_origin=commit_origin,
        registry_commit_subject=commit_subject,
    ), commands


def _apply_setting(
    state: ConsumerUiState, settings: ConsumerSettings
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    """Move one preference and ask for it to be kept.

    The session's profile and the stored detail level are the same choice, so switching with `v`
    and switching on screen 28 go through here together rather than through two rules that could
    disagree. Persistence is a command because the reducer is pure: it says the preference should
    outlive the session, and the shell is what can make that true.
    """

    return (
        replace(
            state,
            session=state.session.switch_profile(settings.profile),
            settings=settings,
            quit_pending=False,
        ),
        (ConsumerUiCommand(ConsumerUiCommandKind.PERSIST_SETTINGS),),
    )


#: Where a secret entered on 07b may still be on its way to the transaction (§172.6).
_SECRET_HOLDING_SCREENS = frozenset(
    {ConsumerScreen.INSTALL_CREDENTIALS, ConsumerScreen.READY, ConsumerScreen.INSTALLING}
)


#: Events that change the state without the reader moving: the page somebody turned stays put.
_KEEPS_THE_PAGE = frozenset(
    {
        ConsumerUiEventKind.SCROLL,
        ConsumerUiEventKind.SET_ROWS,
        ConsumerUiEventKind.SET_SELECTION,
    }
)


def reduce_consumer_ui(
    state: ConsumerUiState,
    event: ConsumerUiEvent,
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    """Apply one UI event and return explicit commands for the imperative shell."""

    if not isinstance(state, ConsumerUiState) or not isinstance(event, ConsumerUiEvent):
        raise ValueError("consumer UI reduction needs typed state and event")
    if state.exited:
        return state, ()
    reduced, commands = _reduce(state, event)
    if reduced.session.screen != state.session.screen:
        # Another screen is read from its top (§206).
        reduced = replace(reduced, scroll=0, scroll_follows=True, scrollable=False)
    elif reduced is not state and event.kind not in _KEEPS_THE_PAGE:
        reduced = replace(reduced, scroll_follows=True)
    if reduced.asked_secrets and (
        reduced.session.screen not in _SECRET_HOLDING_SCREENS or reduced.exited
    ):
        # §172.6: leaving before Ready was confirmed forgets what 07b marked.
        return replace(reduced, asked_secrets=()), (
            *commands,
            ConsumerUiCommand(ConsumerUiCommandKind.DISCARD_SECRETS),
        )
    return reduced, commands


def _reduce(
    state: ConsumerUiState, event: ConsumerUiEvent
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    if event.kind is ConsumerUiEventKind.SCROLL:
        step = max(state.viewport_rows // 2, 1)
        delta = -step if event.text == "up" else step
        return replace(state, scroll=max(state.scroll + delta, 0), scroll_follows=False), ()
    if event.kind is ConsumerUiEventKind.NAVIGATE:
        return _navigate(state, event.screen)
    if event.kind is ConsumerUiEventKind.BACK:
        return _back(state)
    if event.kind is ConsumerUiEventKind.SET_ROWS:
        return _set_rows(state, event.rows)
    if event.kind is ConsumerUiEventKind.MOVE:
        return _move(state, event.text)
    if event.kind is ConsumerUiEventKind.MOVE_COLUMN:
        return _move_column(state, event.text)
    if event.kind is ConsumerUiEventKind.SET_SELECTION:
        return _set_selection(state, event.rows)
    if event.kind is ConsumerUiEventKind.TOGGLE_SELECTION:
        return _toggle_selection(state, event.key)
    if event.kind is ConsumerUiEventKind.REQUEST_ACTION:
        return _request_action(state, event.action)
    if event.kind is ConsumerUiEventKind.ACTION_PREPARED:
        return _action_prepared(state, event)
    if event.kind is ConsumerUiEventKind.CONFIRM_ACTION:
        return _confirm_action(state)
    if event.kind is ConsumerUiEventKind.ACTION_RECORDED:
        return _action_recorded(state, event)
    if event.kind is ConsumerUiEventKind.ACTION_FAILED:
        return _action_failed(state, event)
    if event.kind is ConsumerUiEventKind.EDIT_PUBLICATION_BRANCH:
        if state.session.screen is not MaintainerScreen.REGISTRY_PUSH:
            return state, ()
        return replace(
            state,
            publication_branch=event.text,
            session=replace(state.session, review_digest=None),
            quit_pending=False,
        ), ()
    if event.kind is ConsumerUiEventKind.REQUEST_SECRET:
        if (
            state.session.screen is not ConsumerScreen.INSTALL_CREDENTIALS
            or state.action is not ConsumerActionKind.INSTALL
            or event.key in (CONFIG_SET_LATER_ROW, CONFIG_CONTINUE_ROW)
            or event.key not in state.rows
        ):
            return state, ()
        return replace(state, quit_pending=False), (
            ConsumerUiCommand(
                ConsumerUiCommandKind.ASK_SECRET,
                action=ConsumerActionKind.INSTALL,
                focus=event.key,
            ),
        )
    if event.kind is ConsumerUiEventKind.SECRET_ASKED:
        if state.session.screen is not ConsumerScreen.INSTALL_CREDENTIALS:
            return state, ()
        held = tuple(item for item in state.asked_secrets if item != event.key)
        if not event.accepted:
            return replace(state, asked_secrets=held), ()
        # Storing changed the machine, so the install was prepared again: its review is the one
        # Ready confirms now (§207).
        session = state.session
        if event.review_digest:
            session = replace(
                session,
                semantic_identity=event.semantic_identity or None,
                selection_identity=event.selection_identity or None,
                review_digest=event.review_digest,
            )
        return replace(state, session=session, asked_secrets=(*held, event.key)), ()
    if event.kind is ConsumerUiEventKind.EDIT_INSTALL_CONFIG:
        if (
            state.session.screen is ConsumerScreen.REQUIRED_INPUTS
            and state.config_form_active
            and event.key == CONFIG_SET_LATER_ROW
            and event.accepted is True
            and state.config_draft.fields
        ):
            return _request_action(
                replace(state, config_draft=state.config_draft.set_later()),
                ConsumerActionKind.INSTALL,
            )
        if (
            state.session.screen is not ConsumerScreen.REQUIRED_INPUTS
            or not state.config_form_active
            or all(item.row != event.key for item in state.config_draft.fields)
        ):
            return state, ()
        if event.accepted is True:
            edited_config = state.config_draft.accept(event.key)
            if not any(item.row == event.key and item.accepted for item in edited_config.fields):
                return replace(state, config_draft=edited_config, quit_pending=False), ()
            return (
                replace(
                    state,
                    config_draft=edited_config,
                    cursor=(state.cursor + 1) % max(len(state.rows), 1),
                    quit_pending=False,
                ),
                (),
            )
        edited_config = state.config_draft.edit(event.key, event.text)
        return replace(state, config_draft=edited_config, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.EDIT_CONFIGURATION:
        if state.session.screen is not ConsumerScreen.CONFIGURATION_VALUE or all(
            item.id != event.key for item in state.configuration_draft.fields
        ):
            return state, ()
        if event.accepted is True:
            config_draft = state.configuration_draft.accept(event.key)
            if not any(item.id == event.key and item.accepted for item in config_draft.fields):
                return replace(state, configuration_draft=config_draft, quit_pending=False), ()
            return (
                replace(
                    state,
                    configuration_draft=config_draft,
                    cursor=(state.cursor + 1) % max(len(state.rows), 1),
                    quit_pending=False,
                ),
                (),
            )
        config_draft = state.configuration_draft.edit(event.key, event.text)
        return replace(state, configuration_draft=config_draft, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.EDIT_AUTHOR:
        allowed: dict[ApplicationScreen, tuple[str, ...]] = {
            ConsumerScreen.AUTHOR_WORKSPACE: ("workspace",),
            ConsumerScreen.AUTHOR_INIT: ("kind", "name", "into"),
        }
        if event.key not in allowed.get(state.session.screen, ()):
            return state, ()
        return replace(
            state,
            author_draft=replace(state.author_draft, **{event.key: event.text}),
            failed_action=None,
        ), ()
    if event.kind is ConsumerUiEventKind.EDIT_REGISTRY:
        if state.session.screen is not ConsumerScreen.REGISTRY_ADD:
            return state, ()
        draft = state.registry_draft
        if event.key == "alias":
            draft = replace(draft, alias=event.text)
        elif event.key == "url":
            draft = replace(draft, location=event.text)
        elif event.key == "ref":
            draft = replace(draft, ref=event.text)
        elif event.key == "default" and event.accepted is not None:
            draft = replace(draft, make_default=event.accepted)
        elif event.key == "kind":
            # Space cycles the two transports rather than accepting typed text, for the same
            # reason screen 31a does: the set is closed, and a typed kind is one nobody built.
            offset = REGISTRY_SOURCE_KINDS.index(draft.kind)
            draft = replace(
                draft, kind=REGISTRY_SOURCE_KINDS[(offset + 1) % len(REGISTRY_SOURCE_KINDS)]
            )
        else:
            return state, ()
        return replace(state, registry_draft=draft, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.EDIT_SOURCE:
        if state.session.screen is not MaintainerScreen.SOURCE_ADD:
            return state, ()
        source_draft = state.source_draft
        if event.key == "alias":
            source_draft = replace(source_draft, alias=event.text)
        elif event.key == "location":
            source_draft = replace(source_draft, location=event.text)
        elif event.key == "ref":
            source_draft = replace(source_draft, ref=event.text)
        elif event.key == "kind":
            # Space cycles the two authoring kinds rather than accepting typed text: the set is
            # closed by 164.2, and a form that let one be typed would let `registry-git` in.
            offset = AUTHORING_SOURCE_KINDS.index(source_draft.kind)
            source_draft = replace(
                source_draft,
                kind=AUTHORING_SOURCE_KINDS[(offset + 1) % len(AUTHORING_SOURCE_KINDS)],
            )
        else:
            return state, ()
        return replace(state, source_draft=source_draft, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.EDIT_REGISTRY_INIT:
        if state.session.screen is not MaintainerScreen.REGISTRY_INIT:
            return state, ()
        init_draft = state.registry_init_draft
        if event.key == "id":
            init_draft = replace(init_draft, registry_id=event.text)
        elif event.key == "name":
            init_draft = replace(init_draft, display_name=event.text)
        elif event.key == "commit" and event.accepted is not None:
            init_draft = replace(init_draft, commit=event.accepted)
        else:
            return state, ()
        return replace(state, registry_init_draft=init_draft, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.EDIT_COLLECTION:
        if state.session.screen is not MaintainerScreen.COLLECTION_EDITOR:
            return state, ()
        collection_draft = state.collection_draft
        if event.key == "name":
            collection_draft = replace(collection_draft, name=event.text)
        elif event.key == "summary":
            collection_draft = replace(collection_draft, summary=event.text)
        else:
            return state, ()
        return replace(state, collection_draft=collection_draft, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.EDIT_REPOSITORY_SCAN:
        if state.session.screen is not MaintainerScreen.REPOSITORY_SCAN:
            return state, ()
        scan_draft = state.repository_scan_draft
        if event.key == "url":
            scan_draft = replace(scan_draft, url=event.text)
        elif event.key == "ref":
            scan_draft = replace(scan_draft, ref=event.text)
        else:
            return state, ()
        return replace(state, repository_scan_draft=scan_draft, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.EDIT_ADOPTION_NAME:
        if state.session.screen is not MaintainerScreen.SCAN_RESULT or not event.key:
            return state, ()
        names = tuple(item for item in state.adoption_names if item[0] != event.key)
        if event.text:
            names = (*names, (event.key, event.text))
        return replace(state, adoption_names=names, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.TOGGLE_PROFILE:
        return _apply_setting(state, state.settings.toggled("detail-level"))
    if event.kind is ConsumerUiEventKind.TOGGLE_DETAILS:
        if event.accepted is None:
            return state, ()
        if state.session.screen is ConsumerScreen.MARKETPLACE:
            return replace(state, marketplace_details=event.accepted, quit_pending=False), ()
        if state.session.screen in _INSTALLATION_LISTS:
            return replace(state, installed_details=event.accepted, quit_pending=False), ()
        return state, ()
    if event.kind is ConsumerUiEventKind.TOGGLE_EVERYWHERE:
        if event.accepted is None or state.session.screen not in _INSTALLATION_LISTS:
            return state, ()
        return replace(state, installed_everywhere=event.accepted, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.TOGGLE_SETTING:
        if state.session.screen is not ConsumerScreen.SETTINGS or (
            event.key not in SETTING_ROWS
            and default_harness_from_row(event.key) is None
            and usage_harness_from_row(event.key) is None
        ):
            return state, ()
        return _apply_setting(state, state.settings.toggled(event.key))
    if event.kind is ConsumerUiEventKind.TOGGLE_PROMOTION_MODE:
        if state.session.screen is not MaintainerScreen.PROMOTION_MODE:
            return state, ()
        chosen = (
            RegistryContentMode.PINNED_REFERENCE
            if state.content_mode is RegistryContentMode.SELF_CONTAINED
            else RegistryContentMode.SELF_CONTAINED
        )
        return replace(state, content_mode=chosen, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.TOGGLE_CANDIDATE_FILTER:
        # Screen 53's rows are facet values, so a row is parsed back into the typed facet it
        # addresses rather than being pulled apart here. A row nothing can be made of changes
        # nothing, which is what an unaddressable row should do.
        if state.session.screen is not MaintainerScreen.CANDIDATE_FILTERS:
            return state, ()
        parsed = parse_candidate_filter_row(event.key)
        if parsed is None:
            return state, ()
        facet, value = parsed
        return (
            replace(
                state,
                candidate_filter=state.candidate_filter.toggled(facet, value),
                quit_pending=False,
            ),
            (),
        )
    if event.kind is ConsumerUiEventKind.SEARCH:
        if state.session.screen not in _SEARCHABLE:
            return state, ()
        return replace(state, search=event.text, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.SEARCH_OPEN:
        if state.session.screen not in _SEARCHABLE:
            return state, ()
        return replace(state, searching=True, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.SEARCH_CLOSE:
        if not state.searching:
            return state, ()
        kept = state.search if event.accepted is True else ""
        return replace(state, searching=False, search=kept, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.HELP:
        return replace(state, help_visible=not state.help_visible, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.QUIT:
        if state.selection:
            return replace(state, quit_pending=True), (
                ConsumerUiCommand(ConsumerUiCommandKind.CONFIRM_QUIT),
            )
        return replace(state, exited=True), (ConsumerUiCommand(ConsumerUiCommandKind.EXIT),)
    if event.kind is ConsumerUiEventKind.CONFIRM_QUIT and state.quit_pending:
        if event.accepted is True:
            return replace(state, exited=True, quit_pending=False), (
                ConsumerUiCommand(ConsumerUiCommandKind.EXIT),
            )
        return replace(state, quit_pending=False), ()
    return state, ()


#: Names the terminal shell gives the keys that are not one printable character.
_SPECIAL_KEYS = frozenset(
    {"page-up", "page-down", "up", "down", "left", "right", "enter", "escape", "backspace"}
)


@dataclass(frozen=True, slots=True)
class _ScreenBinding:
    """A screen-specific shortcut, including both its event and its displayed meaning."""

    display: KeyBinding
    event: ConsumerUiEvent


def _navigate_binding(key: str, label: str, screen: ApplicationScreen) -> _ScreenBinding:
    return _ScreenBinding(
        KeyBinding(key, label),
        ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=screen),
    )


def _action_binding(key: str, label: str, action: ConsumerActionKind) -> _ScreenBinding:
    return _ScreenBinding(
        KeyBinding(key, label),
        ConsumerUiEvent(ConsumerUiEventKind.REQUEST_ACTION, action=action),
    )


def _event_binding(key: str, label: str, kind: ConsumerUiEventKind) -> _ScreenBinding:
    return _ScreenBinding(KeyBinding(key, label), ConsumerUiEvent(kind))


#: The lists of installations, whose details `d` shows together (§199).
_INSTALLATION_LISTS = frozenset({ConsumerScreen.INSTALLED, ConsumerScreen.UPDATES})


def details_shown(state: ConsumerUiState) -> bool:
    """Whether the list on this screen draws its detail columns (§196, §199)."""

    if state.session.screen in _INSTALLATION_LISTS:
        return state.installed_details
    return state.marketplace_details


def _details_binding(label: str, *, shown: bool) -> _ScreenBinding:
    """`d` on a list, as the binding that shows the details or the one that hides them."""

    return _ScreenBinding(
        KeyBinding("d", label),
        ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_DETAILS, accepted=shown),
    )


def _everywhere_binding(label: str, *, shown: bool) -> _ScreenBinding:
    """`a` on Installed and Updates: every project's installations, or only those reached here."""

    return _ScreenBinding(
        KeyBinding("a", label),
        ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_EVERYWHERE, accepted=shown),
    )


#: The contextual letter keys have one authority: :func:`key_event` translates this table and the
#: footer displays it. Adding a route without its explanation, or explaining a key that routes
#: nowhere, is therefore not representable (`QA-026`). Structural keys such as Space and Enter are
#: derived below from the same screen sets and review maps that the reducer uses.
_SCREEN_BINDINGS: dict[ApplicationScreen, tuple[_ScreenBinding, ...]] = {
    ConsumerScreen.AUTHOR: (
        _navigate_binding("w", "Workspace", ConsumerScreen.AUTHOR_WORKSPACE),
        _navigate_binding("n", "New artifact", ConsumerScreen.AUTHOR_INIT),
        _action_binding("r", "Check", ConsumerActionKind.AUTHOR_CHECK),
    ),
    ConsumerScreen.AUTHOR_CHECK: (
        _action_binding("r", "Re-run check", ConsumerActionKind.AUTHOR_CHECK),
    ),
    ConsumerScreen.AUTHOR_MANIFEST: (
        _action_binding("r", "Re-run check", ConsumerActionKind.AUTHOR_CHECK),
    ),
    ConsumerScreen.MARKETPLACE: (
        _action_binding("i", "Install", ConsumerActionKind.INSTALL),
        # One key, two bindings: the footer names what `d` does next, and only that one is on.
        _details_binding("Details", shown=True),
        _details_binding("Hide details", shown=False),
    ),
    ConsumerScreen.COLLECTION_PREVIEW: (
        _action_binding("i", "Install", ConsumerActionKind.INSTALL),
    ),
    ConsumerScreen.COLLECTION_CUSTOMIZE: (
        _action_binding("i", "Install", ConsumerActionKind.INSTALL),
    ),
    ConsumerScreen.UPDATES: (
        _action_binding("i", "Update", ConsumerActionKind.UPDATE),
        _details_binding("Details", shown=True),
        _details_binding("Hide details", shown=False),
        _everywhere_binding("All projects", shown=True),
        _everywhere_binding("This project", shown=False),
    ),
    ConsumerScreen.INSTALLED: (
        _action_binding("u", "Uninstall", ConsumerActionKind.UNINSTALL),
        _action_binding("t", "Test MCP", ConsumerActionKind.MCP_TEST),
        _details_binding("Details", shown=True),
        _details_binding("Hide details", shown=False),
        _everywhere_binding("All projects", shown=True),
        _everywhere_binding("This project", shown=False),
    ),
    ConsumerScreen.INSTALLED_ARTIFACT_DETAILS: (
        _action_binding("r", "Repair", ConsumerActionKind.VERIFY_REPAIR),
        _action_binding("u", "Uninstall", ConsumerActionKind.UNINSTALL),
        _action_binding("t", "Test MCP", ConsumerActionKind.MCP_TEST),
    ),
    ConsumerScreen.INSTALLED_COLLECTION_DETAILS: (
        _action_binding("u", "Uninstall", ConsumerActionKind.UNINSTALL),
    ),
    ConsumerScreen.DOCTOR: (
        _action_binding("r", "Repair issues", ConsumerActionKind.VERIFY_REPAIR),
    ),
    ConsumerScreen.REGISTRIES: (
        _navigate_binding("a", "Add Registry", ConsumerScreen.REGISTRY_ADD),
        _action_binding("s", "Sync", ConsumerActionKind.REGISTRY_SYNC),
        _action_binding("d", "Disconnect", ConsumerActionKind.REGISTRY_REMOVE),
    ),
    MaintainerScreen.SOURCES: (
        _navigate_binding("a", "Add upstream", MaintainerScreen.SOURCE_ADD),
        _action_binding("s", "Sync", ConsumerActionKind.SOURCE_SYNC),
        _action_binding("d", "Remove", ConsumerActionKind.SOURCE_REMOVE),
    ),
    MaintainerScreen.SOURCE_DETAILS: (
        _action_binding("s", "Sync", ConsumerActionKind.SOURCE_SYNC),
    ),
    MaintainerScreen.CANDIDATES: (
        _navigate_binding("f", "Filters", MaintainerScreen.CANDIDATE_FILTERS),
    ),
    MaintainerScreen.CANDIDATE_DETAILS: (
        _navigate_binding("d", "Diff", MaintainerScreen.CANDIDATE_DIFF),
        _navigate_binding("r", "Lifecycle", MaintainerScreen.CANDIDATE_LIFECYCLE),
    ),
    # Screen 39 is a drill-down, not a dead end. The evidence was already produced before the
    # screen opened, so continuing to the policy that judges it needs no second action (`QA-074`).
    MaintainerScreen.VALIDATION_DETAILS: (
        _navigate_binding("Enter", "Policy", MaintainerScreen.POLICY_REVIEW),
    ),
    MaintainerScreen.PROMOTION_MODE: (
        _event_binding("m", "Toggle mode", ConsumerUiEventKind.TOGGLE_PROMOTION_MODE),
    ),
    MaintainerScreen.REGISTRY: (
        # §202: the list acts on no Registry. Initialize is for a directory that holds none, so it
        # is the one command offered here, and only while there is no Registry to open.
        _navigate_binding("n", "Initialize", MaintainerScreen.REGISTRY_INIT),
    ),
    # The Registry in this directory, opened from its row, and every command acting on it (§202).
    MaintainerScreen.REGISTRY_DETAILS: (
        _navigate_binding("c", "Candidates", MaintainerScreen.CANDIDATES),
        _navigate_binding("b", "Rebuild", MaintainerScreen.REGISTRY_REBUILD),
        _navigate_binding("s", "Scan Repository", MaintainerScreen.REPOSITORY_SCAN),
        _navigate_binding("u", "Check upstream", MaintainerScreen.ADOPTED_ARTIFACTS),
        _action_binding("p", "Push", ConsumerActionKind.REGISTRY_PUSH),
        _navigate_binding("o", "Collections", MaintainerScreen.COLLECTIONS),
    ),
    # The end of a Source journey. Enter is bound here rather than left to the generic rule
    # because a result screen has nothing to open, and an Enter that does nothing is how somebody
    # ends up pressing Esc through every screen they just walked (`QA-027`).
    MaintainerScreen.SOURCE_SYNC_RESULT: (
        _navigate_binding("Enter", "Upstream repositories", MaintainerScreen.SOURCES),
    ),
    MaintainerScreen.SCAN_RESULT: (
        _action_binding("a", "Adopt", ConsumerActionKind.REPOSITORY_ADOPT),
    ),
    MaintainerScreen.UPSTREAM_CHECK: (
        _action_binding("a", "Review new version", ConsumerActionKind.REPOSITORY_ADOPT_UPDATE),
    ),
    MaintainerScreen.ADOPTED_ARTIFACTS: (
        _action_binding("Enter", "Check upstream", ConsumerActionKind.REPOSITORY_UPSTREAM_CHECK),
    ),
    MaintainerScreen.BULK_PROMOTION: (
        _action_binding("Enter", "Review promotion", ConsumerActionKind.BULK_PROMOTION),
    ),
    MaintainerScreen.REGISTRY_DIFF: (
        _action_binding("Enter", "Review promotion", ConsumerActionKind.CANDIDATE_PROMOTION),
    ),
    MaintainerScreen.REGISTRY_REBUILD: (
        _action_binding("Enter", "Review run", ConsumerActionKind.REGISTRY_REBUILD),
    ),
}

#: What Space changes on each form that has something to change, said by name.
#:
#: `QA-088`: no sentence on the screen says "Space toggles default" or "Space switches kind", so a
#: shared "Toggle" would drop the only word that says what the key is for.
_FORM_TOGGLE_LABELS: dict[ApplicationScreen, str] = {
    ConsumerScreen.AUTHOR_INIT: "Switch kind",
    ConsumerScreen.REGISTRY_ADD: "Make default",
    MaintainerScreen.SOURCE_ADD: "Switch kind",
    MaintainerScreen.REGISTRY_INIT: "Local commit",
}
#: The row Space toggles on each form that has one.
_FORM_TOGGLE_ROWS: dict[ApplicationScreen, str] = {
    ConsumerScreen.AUTHOR_INIT: "kind",
    ConsumerScreen.REGISTRY_ADD: "default",
    MaintainerScreen.SOURCE_ADD: "kind",
    MaintainerScreen.REGISTRY_INIT: "commit",
}
#: The rows of each fixed form that take typed text. Every other row -- a toggle, the submit row --
#: takes none, so the universal letters are commands there rather than characters (D-269).
_FORM_TEXT_ROWS: dict[ApplicationScreen, frozenset[str]] = {
    ConsumerScreen.AUTHOR_WORKSPACE: frozenset({"workspace"}),
    ConsumerScreen.AUTHOR_INIT: frozenset({"name", "into"}),
    ConsumerScreen.REGISTRY_ADD: frozenset({"alias", "url", "ref"}),
    MaintainerScreen.SOURCE_ADD: frozenset({"alias", "location", "ref"}),
    MaintainerScreen.REGISTRY_INIT: frozenset({"id", "name"}),
    MaintainerScreen.COLLECTION_EDITOR: frozenset({"name", "summary"}),
    MaintainerScreen.REPOSITORY_SCAN: frozenset({"url", "ref"}),
    MaintainerScreen.REGISTRY_PUSH: frozenset({"branch"}),
}
#: The keys every screen offers, which a form gives up while the cursor is on a text field.
_UNIVERSAL_LETTERS: dict[str, ConsumerUiEventKind] = {
    "q": ConsumerUiEventKind.QUIT,
    "?": ConsumerUiEventKind.HELP,
    "v": ConsumerUiEventKind.TOGGLE_PROFILE,
}


def _form_text_rows(state: ConsumerUiState) -> frozenset[str] | None:
    """The rows of the open form that take typed text, or None when no form is open."""

    screen = state.session.screen
    if screen is MaintainerScreen.SCAN_RESULT:
        # 46d is a list, not a form; only its Registry name rows take text (INV-279).
        row = state.current_row
        return frozenset({row}) if row.startswith(ADOPTION_NAME_ROW) else None
    if screen is ConsumerScreen.CONFIGURATION_VALUE:
        return frozenset(item.id for item in state.configuration_draft.fields)
    if screen is ConsumerScreen.REQUIRED_INPUTS:
        return (
            frozenset(item.row for item in state.config_draft.fields)
            if state.config_form_active
            else None
        )
    return _FORM_TEXT_ROWS.get(screen)


#: Screen 52's submit row. Every row between the text fields and this one is a member.
COLLECTION_SAVE_ROW = "save"
#: Screen 46d's row for the Registry name of the scanned artifact it prefixes (INV-279).
ADOPTION_NAME_ROW = "name:"


def _collection_member_row(state: ConsumerUiState) -> bool:
    return state.session.screen is MaintainerScreen.COLLECTION_EDITOR and state.current_row not in {
        "",
        "name",
        "summary",
        COLLECTION_SAVE_ROW,
    }


def typing_text(state: ConsumerUiState) -> bool:
    """Whether a printable key is text here: the cursor is on a form field that takes it.

    §167 keeps text entry literal, so a field has to be able to hold a `v`, a `?` and a `q`. The
    same letters are commands on every other row, a form's toggles and its submit row included,
    which is what keeps Help and Quit reachable from a form at all (D-269).
    """

    rows = _form_text_rows(state)
    return rows is not None and state.current_row in rows


_CONFIRM_SCREENS = frozenset(
    {
        ConsumerScreen.READY,
        ConsumerScreen.UPDATE_INPUTS,
        ConsumerScreen.UNINSTALL_REVIEW,
        ConsumerScreen.VERIFY_REPAIR,
        ConsumerScreen.REGISTRY_REVIEW,
        ConsumerScreen.REGISTRY_SYNC,
        ConsumerScreen.REGISTRY_REMOVE,
        MaintainerScreen.SOURCE_REMOVE,
        MaintainerScreen.SOURCE_SYNC,
        MaintainerScreen.REGISTRY_COMMIT,
        MaintainerScreen.ADOPTION_REVIEW,
        MaintainerScreen.SOURCE_ADD_REVIEW,
        MaintainerScreen.REGISTRY_INIT_REVIEW,
        MaintainerScreen.REGISTRY_REBUILD_REVIEW,
        MaintainerScreen.REGISTRY_PUSH,
        ConsumerScreen.CREDENTIAL_REVIEW,
        ConsumerScreen.CONFIGURATION_REVIEW,
        ConsumerScreen.MCP_TEST,
    }
)

#: Screens whose rows are the actions themselves: Enter requests the one under the cursor, and the
#: legend names it. The subject stays the screen's focus -- on screen 24 the credential reference --
#: so moving among the verbs never changes what they act on (CP-23 task 12, D-262).
_ROW_ACTIONS: dict[ApplicationScreen, dict[str, tuple[ConsumerActionKind, str]]] = {
    ConsumerScreen.CREDENTIAL_ACTION: {
        "verify": (ConsumerActionKind.CREDENTIAL_VERIFY, "Verify"),
        "set": (ConsumerActionKind.CREDENTIAL_SET, "Review setup"),
        "replace": (ConsumerActionKind.CREDENTIAL_REPLACE, "Review replacement"),
        "delete": (ConsumerActionKind.CREDENTIAL_DELETE, "Review deletion"),
    },
    # One of Success's rows is an action rather than a destination: the test it reviews is about
    # the transaction Success shows, which stays the subject (§170.4). The other rows still open.
    ConsumerScreen.SUCCESS: {
        ConsumerScreen.MCP_TEST.value: (ConsumerActionKind.MCP_TEST, "Review MCP test"),
    },
}


def _row_action(state: ConsumerUiState, cursor: str = "") -> tuple[ConsumerActionKind, str] | None:
    return _ROW_ACTIONS.get(state.session.screen, {}).get(cursor or state.current_row or "")


def _answered_in_place(state: ConsumerUiState) -> bool:
    """A credential was verified and its answer is on 24a: Enter goes back to that credential."""

    return (
        state.session.screen is ConsumerScreen.CREDENTIAL_REVIEW
        and state.action is None
        and state.failed_action is None
    )


def installation_is_mcp(installation: str) -> bool:
    """Whether an installation key (`alias/kind/name@version#harness`) names an MCP."""

    parts = installation.split("/")
    return len(parts) >= 3 and parts[1] == "mcp"


def _uninstall_finished(state: ConsumerUiState) -> bool:
    """An uninstall started on Installed has run, and its receipt is on Activity Details."""

    history = state.session.history
    return (
        state.session.screen is ConsumerScreen.ACTIVITY_DETAILS
        and state.action is None
        and ConsumerScreen.UNINSTALLING in history
        and ConsumerScreen.INSTALLED in history
    )


def _mcp_test_answered(state: ConsumerUiState) -> bool:
    """The MCP test ran and its stages are on 11a: Enter goes back to the Success it followed."""

    return (
        state.session.screen is ConsumerScreen.MCP_TEST
        and state.action is None
        and state.failed_action is None
    )


def _mcp_test_origin(state: ConsumerUiState) -> str:
    """Where Enter leaves a finished MCP test for: the screen it was asked from."""

    origin = state.session.history[-1] if state.session.history else ConsumerScreen.SUCCESS
    names: dict[ApplicationScreen, str] = {
        ConsumerScreen.INSTALLED: "Installed",
        ConsumerScreen.INSTALLED_ARTIFACT_DETAILS: "details",
    }
    return names.get(origin, "Success")


def _binding_enabled(binding: _ScreenBinding, state: ConsumerUiState) -> bool:
    if typing_text(state) and len(binding.display.key) == 1:
        # A letter typed into a field is text, so it is not also offered as a command.
        return False
    if (
        binding.event.action is ConsumerActionKind.MCP_TEST
        and state.session.screen is ConsumerScreen.INSTALLED_ARTIFACT_DETAILS
    ):
        # A details screen is one installation, so the test is offered only where it is an MCP.
        return installation_is_mcp(state.focus)
    if binding.event.action in (
        ConsumerActionKind.REGISTRY_SYNC,
        ConsumerActionKind.REGISTRY_REMOVE,
        ConsumerActionKind.SOURCE_REMOVE,
    ):
        return state.current_row not in ("", "add-registry")
    if binding.event.kind is ConsumerUiEventKind.TOGGLE_DETAILS:
        return binding.event.accepted is not details_shown(state)
    if binding.event.kind is ConsumerUiEventKind.TOGGLE_EVERYWHERE:
        return binding.event.accepted is not state.installed_everywhere
    if binding.event.action is ConsumerActionKind.REGISTRY_PUSH:
        return state.current_row == REGISTRY_WORKSPACE_READY_ROW
    if binding.event.screen is MaintainerScreen.REGISTRY_INIT:
        # A directory that already holds a Registry opens it instead (§202).
        return not any(
            row in (REGISTRY_WORKSPACE_ROW, REGISTRY_WORKSPACE_READY_ROW) for row in state.rows
        )
    return True


def _screen_binding(key: str, state: ConsumerUiState) -> _ScreenBinding | None:
    return next(
        (
            binding
            for binding in _SCREEN_BINDINGS.get(state.session.screen, ())
            if binding.display.key.lower() == key and _binding_enabled(binding, state)
        ),
        None,
    )


def key_bindings(
    state: ConsumerUiState, *, detail: ApplicationScreen | None = None
) -> tuple[KeyBinding, ...]:
    """Return the keys that can act in this exact UI state, specific actions first."""

    if not isinstance(state, ConsumerUiState) or not (
        detail is None or isinstance(detail, (ConsumerScreen, MaintainerScreen))
    ):
        raise ValueError("key bindings need consumer UI state and an optional detail screen")
    if state.quit_pending:
        return (KeyBinding("y/Enter", "Quit"), KeyBinding("n/Esc", "Stay"))
    if state.searching:
        return (
            KeyBinding("Type", "Search"),
            KeyBinding("Backspace", "Edit"),
            KeyBinding("Enter", "Apply"),
            KeyBinding("Esc", "Cancel"),
        )

    bindings = [
        binding.display
        for binding in _SCREEN_BINDINGS.get(state.session.screen, ())
        if _binding_enabled(binding, state)
    ]
    keys = {binding.key.lower() for binding in bindings}
    text_rows = _form_text_rows(state)
    typing = typing_text(state)
    if text_rows is not None:
        # `QA-088`: a form's keys are in the legend, in the order a reader uses them: change a
        # field, then move on. D-269: only the keys the row under the cursor takes, because the
        # audit found Backspace offered on Continue and Space on rows it does not toggle.
        def acts(name: str) -> bool:
            return key_event(name, state, detail=detail) is not None

        if typing:
            bindings.append(KeyBinding("Type", "Edit"))
            bindings.append(KeyBinding("Backspace", "Delete"))
        toggling = state.current_row == _FORM_TOGGLE_ROWS.get(state.session.screen)
        if toggling and acts(" "):
            bindings.append(KeyBinding("Space", _FORM_TOGGLE_LABELS[state.session.screen]))
        elif _collection_member_row(state) and acts(" "):
            toggling = True
            label = "Leave out" if state.current_row in state.selection else "Include"
            bindings.append(KeyBinding("Space", label))
        if acts("enter"):
            label = "Next" if typing or toggling else "Continue"
            if state.current_row == CONFIG_SET_LATER_ROW:
                label = "Set later"
            bindings.append(KeyBinding("Enter", label))
    elif state.session.screen is ConsumerScreen.SETTINGS:
        bindings.append(KeyBinding("Space/Enter", "Change"))
    elif state.session.screen is MaintainerScreen.CANDIDATE_FILTERS:
        # With nothing composed there is no value to tick, so the key is not offered.
        if state.rows:
            bindings.append(KeyBinding("Space/Enter", "Toggle filter"))
    else:
        if matrix_columns(state.rows) and " " not in keys:
            bindings.extend((KeyBinding("Space", "Tick"), KeyBinding("←/→", "Harness")))
        elif scope_matrix_columns(state.rows) and " " not in keys:
            bindings.extend((KeyBinding("Space", "Choose"), KeyBinding("←/→", "Scope")))
        elif state.session.screen in _SELECTABLE and " " not in keys:
            label = (
                "Deselect"
                if state.session.screen is ConsumerScreen.MARKETPLACE
                and state.current_row in state.selection
                else "Select"
            )
            bindings.append(KeyBinding("Space", label))
        chosen = _row_action(state)
        if chosen is not None and "enter" not in keys:
            bindings.append(KeyBinding("Enter", chosen[1]))
        elif state.session.screen is ConsumerScreen.INSTALL_CREDENTIALS and "enter" not in keys:
            row = state.current_row
            if row == CONFIG_SET_LATER_ROW:
                bindings.append(KeyBinding("Enter", "Set later"))
            elif row == CONFIG_CONTINUE_ROW:
                bindings.append(KeyBinding("Enter", "Continue"))
            elif row:
                label = "Enter again" if row in state.asked_secrets else "Enter value"
                bindings.append(KeyBinding("Enter", label))
        elif _answered_in_place(state) and "enter" not in keys:
            bindings.append(KeyBinding("Enter", "Credential details"))
        elif _uninstall_finished(state) and "enter" not in keys:
            bindings.append(KeyBinding("Enter", "Back to Installed"))
        elif _mcp_test_answered(state) and "enter" not in keys:
            bindings.append(KeyBinding("Enter", "Back to " + _mcp_test_origin(state)))
        elif state.failed_action is not None and "enter" not in keys:
            # The run is over. The only thing Enter can honestly do here is leave.
            bindings.append(KeyBinding("Enter", "Back to list"))
        elif state.session.screen in _CONFIRM_SCREENS and "enter" not in keys:
            label = "Continue" if state.action is None else "Confirm"
            bindings.append(KeyBinding("Enter", label))
        elif (
            state.session.screen in (ConsumerScreen.REVIEW_SELECTION, ConsumerScreen.INSTALL_SCOPE)
            and "enter" not in keys
        ):
            # D-270 (revising D-260's "always advertises"): Enter is offered once the prepared
            # plan matches the chosen harnesses, because only then does it advance; while the
            # choice is incomplete the status says what is missing instead of a key doing nothing.
            if detail is not None:
                bindings.append(KeyBinding("Enter", "Continue"))
        elif detail is not None and "enter" not in keys:
            # Success's rows are choices rather than things to open, so Enter says which one.
            choices: dict[ConsumerScreen | MaintainerScreen, str] = {}
            if state.session.screen is ConsumerScreen.SUCCESS:
                choices = dict(SUCCESS_CHOICES)
            label = choices.get(detail, "Open")
            bindings.append(KeyBinding("Enter", label))
        elif (
            state.session.screen is MaintainerScreen.REGISTRY_COMMIT
            and state.action is None
            and "enter" not in keys
        ):
            bindings.append(KeyBinding("Enter", "Registry"))
    if state.session.screen in _SEARCHABLE and not typing:
        bindings.append(KeyBinding("/", "Search"))
    if state.scrollable and not state.searching:
        bindings.append(KeyBinding("PgUp/PgDn", "Scroll"))
    if not typing:
        bindings.append(KeyBinding("v", state.session.profile.toggle_label))
    bindings.extend((KeyBinding("↑/↓", "Move"), KeyBinding("Esc", "Back")))
    if not typing:
        bindings.extend((KeyBinding("?", "Help"), KeyBinding("q", "Quit")))
    return tuple(bindings)


def key_event(
    key: str,
    state: ConsumerUiState,
    *,
    cursor: str = "",
    detail: ApplicationScreen | None = None,
) -> ConsumerUiEvent | None:
    """The event one key means here, or None where it means nothing on this screen.

    Mode comes first deliberately.  While the quit prompt or the search filter is open the
    global bindings do not apply at all: during a search `q` types a q, and at the prompt `n`
    answers the question rather than doing whatever `n` would otherwise do.

    `detail` is what Enter opens from the current row, which only the screen knows.
    """

    if not isinstance(state, ConsumerUiState):
        raise ValueError("key translation needs a key name and consumer UI state")
    if (
        not isinstance(key, str)
        or not key
        or (len(key) != 1 and key not in _SPECIAL_KEYS and _form_text_rows(state) is None)
        or not (detail is None or isinstance(detail, (ConsumerScreen, MaintainerScreen)))
    ):
        raise ValueError("key translation needs a key name and consumer UI state")

    if state.quit_pending:
        if key in ("y", "Y", "enter"):
            return ConsumerUiEvent(ConsumerUiEventKind.CONFIRM_QUIT, accepted=True)
        if key in ("n", "N", "escape"):
            return ConsumerUiEvent(ConsumerUiEventKind.CONFIRM_QUIT, accepted=False)
        return None

    if state.searching:
        if key == "escape":
            return ConsumerUiEvent(ConsumerUiEventKind.SEARCH_CLOSE, accepted=False)
        if key == "enter":
            return ConsumerUiEvent(ConsumerUiEventKind.SEARCH_CLOSE, accepted=True)
        if key == "backspace":
            return ConsumerUiEvent(ConsumerUiEventKind.SEARCH, text=state.search[:-1])
        if len(key) == 1 and key.isprintable():
            return ConsumerUiEvent(ConsumerUiEventKind.SEARCH, text=state.search + key)
        return None

    if key in ("page-up", "page-down"):
        return ConsumerUiEvent(
            ConsumerUiEventKind.SCROLL, text="up" if key == "page-up" else "down"
        )

    text_rows = _form_text_rows(state)
    if (
        text_rows is not None
        and (cursor or state.current_row) not in text_rows
        and key in _UNIVERSAL_LETTERS
    ):
        return ConsumerUiEvent(_UNIVERSAL_LETTERS[key])

    if state.session.screen is MaintainerScreen.SCAN_RESULT and (
        cursor or state.current_row
    ).startswith(ADOPTION_NAME_ROW):
        coordinate = (cursor or state.current_row).removeprefix(ADOPTION_NAME_ROW)
        typed = dict(state.adoption_names).get(coordinate, "")
        if key == "escape":
            return ConsumerUiEvent(ConsumerUiEventKind.BACK)
        if key in ("up", "down", "enter"):
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="up" if key == "up" else "down")
        if key == "backspace":
            return ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_ADOPTION_NAME, key=coordinate, text=typed[:-1]
            )
        if key.isprintable():
            text = key if len(key) > 1 else typed + key
            return ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_ADOPTION_NAME, key=coordinate, text=text
            )
        return None

    # Screen 46j answers every other key itself, so the universal letters have to be settled above
    # it: D-269 keeps `v`, `?` and `q` working on a form's non-field rows, and reading `continue`
    # here had returned None for all three while the legend went on offering them.
    if state.session.screen is MaintainerScreen.REGISTRY_PUSH and state.rows:
        row = cursor or state.current_row
        if key == "escape":
            return ConsumerUiEvent(ConsumerUiEventKind.BACK)
        if key == "up":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="up")
        if key == "down":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
        if row == "branch":
            if key == "enter":
                return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
            if key == "backspace":
                return ConsumerUiEvent(
                    ConsumerUiEventKind.EDIT_PUBLICATION_BRANCH,
                    text=state.publication_branch[:-1],
                )
            if len(key) == 1 and key.isprintable():
                return ConsumerUiEvent(
                    ConsumerUiEventKind.EDIT_PUBLICATION_BRANCH,
                    text=state.publication_branch + key,
                )
            return None
        if row == "continue" and key == "enter":
            return ConsumerUiEvent(
                ConsumerUiEventKind.CONFIRM_ACTION
                if state.session.review_digest
                else ConsumerUiEventKind.REQUEST_ACTION,
                action=(None if state.session.review_digest else ConsumerActionKind.REGISTRY_PUSH),
            )
        return None

    if state.session.screen is ConsumerScreen.CONFIGURATION_VALUE:
        row = cursor or state.current_row
        if key == "escape":
            return ConsumerUiEvent(ConsumerUiEventKind.BACK)
        if key == "up":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="up")
        if key == "down":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
        if key == "enter":
            if row == CONFIG_CONTINUE_ROW:
                return (
                    ConsumerUiEvent(
                        ConsumerUiEventKind.REQUEST_ACTION,
                        action=ConsumerActionKind.CONFIGURE,
                    )
                    if state.configuration_draft.ready
                    else None
                )
            if any(item.id == row for item in state.configuration_draft.fields):
                return ConsumerUiEvent(
                    ConsumerUiEventKind.EDIT_CONFIGURATION,
                    key=row,
                    accepted=True,
                )
            return None
        if any(item.id == row for item in state.configuration_draft.fields) and key == "backspace":
            return ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_CONFIGURATION,
                key=row,
                text=state.configuration_draft.value(row)[:-1],
            )
        if any(item.id == row for item in state.configuration_draft.fields) and key.isprintable():
            value = key if len(key) > 1 else state.configuration_draft.value(row) + key
            return ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_CONFIGURATION,
                key=row,
                text=value,
            )
        return None

    if state.session.screen is ConsumerScreen.INSTALL_PATH and key == "enter":
        # Either row starts the install; which one is the path (§173.7).
        return (
            ConsumerUiEvent(ConsumerUiEventKind.REQUEST_ACTION, action=ConsumerActionKind.INSTALL)
            if cursor or state.current_row
            else None
        )

    if (
        state.session.screen is ConsumerScreen.INSTALL_CREDENTIALS
        and key == "enter"
        and (cursor or state.current_row) not in ("", CONFIG_SET_LATER_ROW, CONFIG_CONTINUE_ROW)
    ):
        # §172.6: a secret row is marked for the store to ask while installing; nothing is typed.
        return ConsumerUiEvent(ConsumerUiEventKind.REQUEST_SECRET, key=cursor or state.current_row)

    if state.session.screen is ConsumerScreen.REQUIRED_INPUTS and state.config_form_active:
        row = cursor or state.current_row
        if key == "escape":
            return ConsumerUiEvent(ConsumerUiEventKind.BACK)
        if key == "up":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="up")
        if key == "down":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
        if key == "enter":
            if row == CONFIG_SET_LATER_ROW:
                return ConsumerUiEvent(
                    ConsumerUiEventKind.EDIT_INSTALL_CONFIG, key=row, accepted=True
                )
            if row == CONFIG_CONTINUE_ROW:
                return (
                    ConsumerUiEvent(
                        ConsumerUiEventKind.REQUEST_ACTION,
                        action=ConsumerActionKind.INSTALL,
                    )
                    if state.config_draft.ready
                    else None
                )
            if any(item.row == row for item in state.config_draft.fields):
                return ConsumerUiEvent(
                    ConsumerUiEventKind.EDIT_INSTALL_CONFIG,
                    key=row,
                    accepted=True,
                )
            return None
        if any(item.row == row for item in state.config_draft.fields) and key == "backspace":
            return ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_INSTALL_CONFIG,
                key=row,
                text=state.config_draft.value(row)[:-1],
            )
        if any(item.row == row for item in state.config_draft.fields) and key.isprintable():
            value = key if len(key) > 1 else state.config_draft.value(row) + key
            return ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_INSTALL_CONFIG,
                key=row,
                text=value,
            )
        return None

    if state.session.screen is MaintainerScreen.REGISTRY_INIT:
        row = cursor or state.current_row
        values = {
            "id": state.registry_init_draft.registry_id,
            "name": state.registry_init_draft.display_name,
        }
        if key == "escape":
            return ConsumerUiEvent(ConsumerUiEventKind.BACK)
        if key == "up":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="up")
        if key == "down":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
        if key == " " and row == "commit":
            return ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_REGISTRY_INIT,
                key="commit",
                accepted=not state.registry_init_draft.commit,
            )
        if key == "enter":
            if row == "initialize":
                return ConsumerUiEvent(
                    ConsumerUiEventKind.REQUEST_ACTION,
                    action=ConsumerActionKind.REGISTRY_INIT,
                )
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
        if row in values and key == "backspace":
            return ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_REGISTRY_INIT, key=row, text=values[row][:-1]
            )
        if row in values and key.isprintable():
            text = key if len(key) > 1 else values[row] + key
            return ConsumerUiEvent(ConsumerUiEventKind.EDIT_REGISTRY_INIT, key=row, text=text)
        return None

    if (
        state.session.screen is ConsumerScreen.AUTHOR
        and key == "enter"
        and state.current_row == "check"
    ):
        return ConsumerUiEvent(
            ConsumerUiEventKind.REQUEST_ACTION, action=ConsumerActionKind.AUTHOR_CHECK
        )
    if state.session.screen in (ConsumerScreen.AUTHOR_WORKSPACE, ConsumerScreen.AUTHOR_INIT):
        row = cursor or state.current_row
        draft = state.author_draft
        values = {"workspace": draft.workspace, "name": draft.name, "into": draft.into}
        if key == "escape":
            return ConsumerUiEvent(ConsumerUiEventKind.BACK)
        if key in ("up", "down"):
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text=key)
        if key == " " and row == "kind":
            kind = GENERATED_KINDS[(GENERATED_KINDS.index(draft.kind) + 1) % len(GENERATED_KINDS)]
            return ConsumerUiEvent(ConsumerUiEventKind.EDIT_AUTHOR, key="kind", text=kind)
        if key == "enter":
            if row == "save":
                action = (
                    ConsumerActionKind.AUTHOR_WORKSPACE
                    if state.session.screen is ConsumerScreen.AUTHOR_WORKSPACE
                    else ConsumerActionKind.AUTHOR_INIT
                )
                return ConsumerUiEvent(ConsumerUiEventKind.REQUEST_ACTION, action=action)
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
        if row in values and key == "backspace":
            return ConsumerUiEvent(ConsumerUiEventKind.EDIT_AUTHOR, key=row, text=values[row][:-1])
        if row in values and key.isprintable():
            return ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_AUTHOR,
                key=row,
                text=key if len(key) > 1 else values[row] + key,
            )
        return None
    if state.session.screen is MaintainerScreen.COLLECTION_EDITOR:
        row = cursor or state.current_row
        values = {"name": state.collection_draft.name, "summary": state.collection_draft.summary}
        if key == "escape":
            # An applied filter is cleared first, so leaving never costs the draft by surprise.
            if state.search:
                return ConsumerUiEvent(ConsumerUiEventKind.SEARCH, text="")
            return ConsumerUiEvent(ConsumerUiEventKind.BACK)
        if key == "up":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="up")
        if key == "down":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
        if key == "/" and row not in values:
            return ConsumerUiEvent(ConsumerUiEventKind.SEARCH_OPEN)
        if key == " " and row not in values and row != COLLECTION_SAVE_ROW:
            return ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_SELECTION, key=row)
        if key == "enter":
            if row == COLLECTION_SAVE_ROW:
                return ConsumerUiEvent(
                    ConsumerUiEventKind.REQUEST_ACTION,
                    action=ConsumerActionKind.COLLECTION_DEFINE,
                )
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
        if row in values and key == "backspace":
            return ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_COLLECTION, key=row, text=values[row][:-1]
            )
        if row in values and key.isprintable():
            text = key if len(key) > 1 else values[row] + key
            return ConsumerUiEvent(ConsumerUiEventKind.EDIT_COLLECTION, key=row, text=text)
        return None

    if state.session.screen is MaintainerScreen.REPOSITORY_SCAN:
        row = cursor or state.current_row
        values = {
            "url": state.repository_scan_draft.url,
            "ref": state.repository_scan_draft.ref,
        }
        if key == "escape":
            return ConsumerUiEvent(ConsumerUiEventKind.BACK)
        if key == "up":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="up")
        if key == "down":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
        if key == "enter":
            if row == "scan":
                return ConsumerUiEvent(
                    ConsumerUiEventKind.REQUEST_ACTION,
                    action=ConsumerActionKind.REPOSITORY_SCAN,
                )
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
        if row in values and key == "backspace":
            return ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_REPOSITORY_SCAN,
                key=row,
                text=values[row][:-1],
            )
        if row in values and key.isprintable():
            text = key if len(key) > 1 else values[row] + key
            return ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_REPOSITORY_SCAN,
                key=row,
                text=text,
            )
        return None

    if state.session.screen is MaintainerScreen.SOURCE_ADD:
        row = cursor or state.current_row
        values = {
            "alias": state.source_draft.alias,
            "location": state.source_draft.location,
            "ref": state.source_draft.ref,
        }
        if key == "escape":
            return ConsumerUiEvent(ConsumerUiEventKind.BACK)
        if key == "up":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="up")
        if key == "down":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
        if key == " " and row == "kind":
            return ConsumerUiEvent(ConsumerUiEventKind.EDIT_SOURCE, key="kind")
        if key == "enter":
            if row == "connect":
                return ConsumerUiEvent(
                    ConsumerUiEventKind.REQUEST_ACTION,
                    action=ConsumerActionKind.SOURCE_ADD,
                )
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
        if row in values and key == "backspace":
            return ConsumerUiEvent(ConsumerUiEventKind.EDIT_SOURCE, key=row, text=values[row][:-1])
        if row in values and key.isprintable():
            text = key if len(key) > 1 else values[row] + key
            return ConsumerUiEvent(ConsumerUiEventKind.EDIT_SOURCE, key=row, text=text)
        return None

    if state.session.screen is ConsumerScreen.REGISTRY_ADD:
        row = cursor or state.current_row
        values = {
            "alias": state.registry_draft.alias,
            "url": state.registry_draft.location,
            "ref": state.registry_draft.ref,
        }
        if key == "escape":
            return ConsumerUiEvent(ConsumerUiEventKind.BACK)
        if key == "up":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="up")
        if key == "down":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
        if key == " " and row == "kind":
            return ConsumerUiEvent(ConsumerUiEventKind.EDIT_REGISTRY, key="kind")
        if key == " " and row == "default":
            return ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_REGISTRY,
                key="default",
                accepted=not state.registry_draft.make_default,
            )
        if key == "enter":
            if row == "connect":
                return ConsumerUiEvent(
                    ConsumerUiEventKind.REQUEST_ACTION,
                    action=ConsumerActionKind.REGISTRY_ADD,
                )
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
        if row in values and key == "backspace":
            return ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_REGISTRY, key=row, text=values[row][:-1]
            )
        if row in values and key.isprintable():
            text = key if len(key) > 1 else values[row] + key
            return ConsumerUiEvent(ConsumerUiEventKind.EDIT_REGISTRY, key=row, text=text)
        return None

    if key == "q":
        return ConsumerUiEvent(ConsumerUiEventKind.QUIT)
    if key in ("enter", "escape") and _uninstall_finished(state):
        # The installations it was about are gone, so neither their review nor their details is
        # somewhere to go back to: both keys return to the list, refreshed (D-400).
        return ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=ConsumerScreen.INSTALLED)
    if key == "escape":
        return ConsumerUiEvent(ConsumerUiEventKind.BACK)
    if key == "/":
        return ConsumerUiEvent(ConsumerUiEventKind.SEARCH_OPEN)
    if key == "?":
        return ConsumerUiEvent(ConsumerUiEventKind.HELP)
    if key == "v":
        return ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_PROFILE)
    binding = _screen_binding(key, state)
    if binding is not None:
        return binding.event
    # Screen 28 is the one screen whose rows are settings rather than artifacts, so space and
    # Enter move a preference here instead of ticking or opening something.
    if key in (" ", "enter") and state.session.screen is ConsumerScreen.SETTINGS:
        row = cursor or state.current_row
        return None if not row else ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_SETTING, key=row)
    # Screen 53's rows are facet values, not artifacts: ticking one narrows the list rather than
    # putting anything in `selection`, which is what every action reads.
    if key in (" ", "enter") and state.session.screen is MaintainerScreen.CANDIDATE_FILTERS:
        row = cursor or state.current_row
        return (
            None
            if not row
            else ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_CANDIDATE_FILTER, key=row)
        )
    if key in ("left", "right") and (
        matrix_columns(state.rows) or scope_matrix_columns(state.rows)
    ):
        return ConsumerUiEvent(ConsumerUiEventKind.MOVE_COLUMN, text=key)
    if key == " ":
        selected = cursor or state.current_row
        return ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_SELECTION, key=selected)
    if key in ("up", "k"):
        return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="up")
    if key in ("down", "j"):
        return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
    # Screen 45 keeps its receipt on screen after the commit, so Enter means "confirm" only while
    # there is something to confirm; once the write happened it means "go on to the registry".
    if (
        key == "enter"
        and state.action is None
        and state.session.screen is MaintainerScreen.REGISTRY_COMMIT
    ):
        return ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=MaintainerScreen.REGISTRY)
    # A run that stopped leaves the same way a run that finished does, for the screen that owns
    # it -- the review it was confirmed from is now that attempt's result (`QA-033`).
    if key == "enter" and state.failed_action is not None:
        owner = _owning_screen(state.failed_action, state.session.screen)
        if owner is not None:
            return ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=owner)
        return ConsumerUiEvent(ConsumerUiEventKind.BACK)
    if key == "enter" and _answered_in_place(state):
        return ConsumerUiEvent(
            ConsumerUiEventKind.NAVIGATE, screen=ConsumerScreen.CREDENTIAL_DETAILS
        )
    if key == "enter" and _mcp_test_answered(state):
        return ConsumerUiEvent(ConsumerUiEventKind.BACK)
    if key == "enter" and state.session.screen in _CONFIRM_SCREENS:
        return ConsumerUiEvent(ConsumerUiEventKind.CONFIRM_ACTION)
    if key == "enter" and state.session.screen in _ROW_ACTIONS:
        chosen = _row_action(state, cursor)
        if chosen is not None:
            return ConsumerUiEvent(ConsumerUiEventKind.REQUEST_ACTION, action=chosen[0])
        # A screen whose rows are only partly actions still opens the rest (Success, §170.4).
        if detail is None:
            return None
    if key == "enter" and detail is not None:
        return ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=detail)
    return None
