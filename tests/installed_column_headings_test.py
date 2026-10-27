"""INV-285, INV-300: Installed names its columns on Marketplace's grid, with details one key away.

The owner opened Installed and saw `ready  configured` with nothing saying which column was which,
so Installed drew headings over a ruled grid (INV-285). Later they asked for it to read like
Marketplace (§199): a row says which artifact it is as `name@version`, its Type, the harness it is
installed in and its health; `d` adds Registry, Scope, Project and Configuration; a cell too long
for its column is cut, not wrapped; and More info describes the installation under the cursor whole.
"""

from __future__ import annotations

import dataclasses
import re
import unittest

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from aart_cli.application.consumer_ui import (
    ConsumerUiState,
    key_bindings,
    key_event,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import (
    ConfigurationFileView,
    ConsumerScreen,
    ConsumerSession,
    CredentialRecordView,
    InstalledArtifactView,
    OwnershipView,
    PresentationProfile,
    installed_collection_cells,
    installed_row_cells,
    project_activity,
    project_dashboard,
    project_installed_collection,
)
from aart_cli.application.intents import InstalledHealth, MemberHealth
from aart_cli.tui_consumer import (
    _INSTALLED_COLUMNS,
    CanonicalScreenSource,
    ConsumerScreens,
    _reload,
    frame,
)
from aart_cli.tui_marketplace_rows import render_columns
from tests.consumer_shell_test import TODAY

_BRIEF = ("Artifact", "Type", "Harness", "Health")
_DETAILS = ("Registry", "Scope", "Project", "Configuration")
ROOT = "/work/clients/shop"

GITHUB = InstalledArtifactView(
    "public/mcp/github@1.6.0",
    "update",
    (OwnershipView("direct", "public/mcp/github@1.6.0"),),
    (),
    ("details", "verify", "update", "uninstall"),
    scope="project",
    harness="claude",
    placeholders=("api-url",),
    root=ROOT,
    available="1.7.0",
)
NOTES = InstalledArtifactView(
    "company/skill/notes@2.0.0",
    "ready",
    (OwnershipView("direct", "company/skill/notes@2.0.0"),),
    (),
    ("details", "verify", "uninstall"),
    scope="user",
    harness="opencode",
)
KIT = project_installed_collection(
    "public/collection/kit@1.0.0", (MemberHealth(GITHUB.row, InstalledHealth.UPDATE),)
)


#: A credential the provider holds, and so says only that it does: aart-cli never has its value.
TOKEN = CredentialRecordView(
    "keychain:aart-cli/github-token",
    "github-token",
    "macos-keychain",
    "aart-cli",
    "github-token",
    "present",
    "present",
    "",
    (GITHUB.row,),
    ("replace",),
)
SETTINGS = ConfigurationFileView(
    GITHUB.coordinate,
    "claude",
    f"{ROOT}/.claude/aart/github.json",
    "matched",
    (("api-url", "AART_NOT_SET"),),
    inputs=("api-url",),
    installation=GITHUB.row,
)


def _source() -> CanonicalScreenSource:
    artifacts = (GITHUB, NOTES)
    return CanonicalScreenSource(
        ConsumerScreens(
            project_dashboard(artifacts, registry_count=1),
            artifacts,
            project_activity((), today=TODAY),
            installed_collections=(KIT,),
            credentials=(TOKEN,),
            configurations=(SETTINGS,),
        )
    )


def _state(**fields) -> tuple[CanonicalScreenSource, ConsumerUiState]:
    source = _source()
    state = _reload(
        source, ConsumerUiState(ConsumerSession(ConsumerScreen.INSTALLED)), entering=True
    )
    return source, dataclasses.replace(state, viewport_columns=120, viewport_rows=30, **fields)


def _drawn(**fields) -> list[str]:
    return list(frame(*_state(**fields)))


def _grid(lines: list[str]) -> tuple[str, str, list[str]]:
    at = next(index for index, line in enumerate(lines) if line.lstrip().startswith("Artifact"))
    rows = [line for line in lines[at + 2 :] if line.startswith(("> [", "  ["))]
    return lines[at], lines[at + 1], rows


class InstalledColumnHeadingsTest(unittest.TestCase):
    def test_the_headings_sit_over_their_cells_with_a_rule_between(self) -> None:
        heading, rule, rows = _grid(_drawn(installed_details=True))

        self.assertEqual(heading.split(), [*_BRIEF, *_DETAILS])
        self.assertEqual(
            [match.start() for match in re.finditer(r"─+", rule)],
            [heading.index(name) for name in (*_BRIEF, *_DETAILS)],
        )
        kit, github, notes = rows
        self.assertTrue(kit.startswith("> [ ] kit@1.0.0"), rows)
        self.assertEqual(kit[heading.index("Type") :].split()[0], "Collection")
        # A member is drawn under its Collection; the Type, Harness and Health columns stay put.
        self.assertTrue(github.startswith("  [ ]   github@1.6.0"), rows)
        for column, value in (
            ("Type", "MCP"),
            ("Harness", "claude"),
            ("Health", "update"),
            ("Registry", "public"),
            ("Scope", "project"),
            ("Project", "shop"),
        ):
            with self.subTest(column=column):
                self.assertEqual(github[heading.index(column) :].split()[0], value)
        self.assertEqual(
            github[heading.index("Configuration") :].strip(), "not configured (1 missing)"
        )
        self.assertEqual(notes[heading.index("Harness") :].split()[0], "opencode")
        self.assertEqual(notes[heading.index("Scope") :].split()[0], "user")

    def test_without_details_a_row_is_what_it_is_and_whether_it_is_healthy(self) -> None:
        lines = _drawn()
        heading, _rule, rows = _grid(lines)

        self.assertEqual(heading.split(), list(_BRIEF))
        for name in _DETAILS:
            self.assertNotIn(name, heading)
        self.assertNotIn(ROOT, "\n".join(lines))
        self.assertIn("update → 1.7.0", rows[1])

    def test_a_cell_too_long_for_its_column_is_cut_and_the_row_stays_one_line(self) -> None:
        source, state = _state(installed_details=True)
        narrow = dataclasses.replace(state, viewport_columns=60)

        heading, _rule, rows = _grid(list(frame(source, narrow)))

        self.assertEqual(len(rows), 3)
        for line in (heading, *rows):
            self.assertLessEqual(len(line), 60, line)


class DTogglesInstalledDetails(unittest.TestCase):
    def test_the_footer_says_what_d_does_next(self) -> None:
        for screen in (ConsumerScreen.INSTALLED, ConsumerScreen.UPDATES):
            with self.subTest(screen=screen):
                state = ConsumerUiState(ConsumerSession(screen))
                offered = [item.label for item in key_bindings(state) if item.key == "d"]
                shown = dataclasses.replace(state, installed_details=True)
                hidden = [item.label for item in key_bindings(shown) if item.key == "d"]
                self.assertEqual((offered, hidden), (["Details"], ["Hide details"]))

    @given(st.integers(min_value=1, max_value=4))
    @settings(suppress_health_check=(HealthCheck.differing_executors,))
    def test_d_toggles_installed_and_leaves_marketplace_alone(self, presses: int) -> None:
        _, state = _state()
        cursor, rows = state.cursor, state.rows

        for _ in range(presses):
            event = key_event("d", state)
            self.assertIsNotNone(event)
            state, _commands = reduce_consumer_ui(state, event)

        self.assertIs(state.installed_details, presses % 2 == 1)
        self.assertFalse(state.marketplace_details)
        self.assertEqual((state.cursor, state.rows), (cursor, rows))


class MoreInfoDescribesTheInstallation(unittest.TestCase):
    def _described(self, row: str) -> str:
        source, state = _state()
        state = dataclasses.replace(
            state,
            session=dataclasses.replace(state.session, profile=PresentationProfile.MORE_INFO),
            cursor=state.rows.index(row),
        )
        return "\n".join(source.description(state))

    def test_the_installation_under_the_cursor_is_said_whole(self) -> None:
        described = self._described(GITHUB.row)

        for expected in (
            "Artifact",
            "github",
            "1.6.0",
            "MCP",
            "public",
            "claude",
            "Project",
            ROOT,
            "update → 1.7.0",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, described)

    def test_each_input_is_named_with_its_value_or_its_state(self) -> None:
        described = self._described(GITHUB.row)

        self.assertRegex(described, r"api-url +AART_NOT_SET")
        self.assertRegex(described, r"github-token +Configured securely")

    def test_less_info_describes_nothing(self) -> None:
        source, state = _state()

        self.assertNotIn(ROOT, "\n".join(frame(source, state)))

    def test_a_collection_says_what_it_includes(self) -> None:
        described = self._described(KIT.collection)

        self.assertIn("kit", described)
        self.assertIn("1 artifact", described)
        self.assertRegex(described, r"Health +update")


class TheGridHoldsForAnyRows(unittest.TestCase):
    @given(
        st.lists(
            st.tuples(
                st.text(alphabet="abcdefghijklmnop-", min_size=1, max_size=30),
                st.sampled_from(("claude", "opencode", "")),
                st.booleans(),
            ),
            min_size=1,
            max_size=8,
        ),
        st.integers(min_value=20, max_value=160),
        st.booleans(),
    )
    @settings(suppress_health_check=(HealthCheck.differing_executors,))
    def test_every_row_is_one_line_within_the_window(self, entries, width, details) -> None:
        rows = []
        indents = []
        for index, (name, harness, member) in enumerate(entries):
            coordinate = f"public/mcp/{name}{index}@1.0.0"
            view = InstalledArtifactView(
                coordinate, "ready", (), (), (), scope="user", harness=harness
            )
            rows.append(
                installed_row_cells(view, "ready")
                if index
                else installed_collection_cells(coordinate, "ready")
            )
            indents.append(2 if member and index else 0)
        keys = tuple(f"row{index}" for index in range(len(rows)))

        drawn = render_columns(
            _INSTALLED_COLUMNS,
            rows,
            current=keys[0],
            selected=(),
            width=width,
            keys=keys,
            details=details,
            indents=indents,
        )

        marked = [line for line in drawn if line.startswith(("> [", "  ["))]
        self.assertEqual(len(marked), len(rows))
        for line in drawn:
            self.assertLessEqual(len(line), width, line)
        for line, indent in zip(marked, indents, strict=True):
            if indent and len(line) > 8:
                self.assertTrue(line[6:].startswith("  "), line)


if __name__ == "__main__":
    unittest.main()
