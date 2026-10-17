"""§173.8: Marketplace and Installed rows carry the columns a person decides with.

A Marketplace row says, besides the offer: whether it is installed, in which scope and how many
projects, which harnesses hold it, which detected harnesses could, and how many inputs are still
`AART_NOT_SET`. Installed draws each installation as its own row with its scope and project.
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.consumer_ui import ConsumerUiState
from aart_cli.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    InstalledArtifactView,
    PresentationProfile,
    installed_cells,
    marketplace_cells,
)
from aart_cli.tui_consumer import frame, render_installed_artifact
from tests.configured_install_command_e2e_test import COORDINATE
from tests.consumer_application_e2e_test import _actions
from tests.installed_multi_uninstall_e2e_test import SECOND, _two_skills


def _rows(env, screen: ConsumerScreen) -> list[str]:
    with mock.patch.dict(os.environ, env.xdg, clear=False):
        source = _actions(env).source()
        empty = ConsumerUiState(ConsumerSession(screen))
        state = ConsumerUiState(ConsumerSession(screen), rows=source.rows(empty))
        return [line for line in frame(source, state) if "[ ]" in line]


class MarketplaceColumnsTest(unittest.TestCase):
    def test_marketplace_and_installed_rows_carry_the_columns(self) -> None:
        with _two_skills() as env:
            code, installed = env.run(
                "consume", "install", COORDINATE, "--profile", "claude", "--yes"
            )
            self.assertEqual(code, 0, installed)
            offers = _rows(env, ConsumerScreen.MARKETPLACE)
            installations = _rows(env, ConsumerScreen.INSTALLED)
            project = env.project.name

        held = next(line for line in offers if COORDINATE in line)
        other = next(line for line in offers if SECOND in line)
        # Both Skills declare claude alone, so opencode is detected and not eligible.
        for cell in ("installed", "1 project", "claude ✓"):
            self.assertIn(cell, held)
        self.assertIn("not installed", other)
        self.assertTrue(other.endswith("  claude"), other)
        self.assertNotIn("opencode", held + other)
        (row,) = installations
        self.assertIn(COORDINATE, row)
        self.assertIn("#claude", row)
        self.assertIn("project", row)
        self.assertIn(project, row)
        self.assertEqual(
            held.index("installed"),
            other.index("not installed"),
            "the columns are not one grid",
        )


def _view(coordinate, harness, health="ready", scope="project", root="/p/a", unset=()):
    return InstalledArtifactView(
        coordinate,
        health,
        (),
        (),
        (),
        scope=scope,
        harness=harness,
        placeholders=unset,
        root=root,
    )


class CellsTest(unittest.TestCase):
    def test_an_offer_counts_projects_scopes_harnesses_and_unset_inputs(self) -> None:
        installed = (
            _view("company/skill/review@1.0.0", "codex", "update", root="/p/a", unset=("A",)),
            _view("company/skill/review@1.2.0", "claude", root="/p/b", unset=("A", "B")),
            _view("company/skill/review@1.2.0", "claude", scope="user", root="/home"),
            _view("company/skill/review-extra@1.2.0", "opencode"),
        )

        self.assertEqual(
            marketplace_cells("company/skill/review@1.2.0", installed, ("claude", "opencode")),
            (
                "company/skill/review@1.2.0",
                "update available",
                "user + 2 projects",
                "claude ✓, codex ✓, opencode",
                "3 not set",
            ),
        )
        self.assertEqual(
            marketplace_cells("company/skill/lint@1.0.0", installed, ()),
            ("company/skill/lint@1.0.0", "not installed", "", "", ""),
        )

    def test_an_installation_names_its_scope_and_project(self) -> None:
        self.assertEqual(
            installed_cells(_view("company/mcp/x@1.0.0", "claude", unset=("A",)), "ready"),
            ("ready", "project", "a", "1 not set"),
        )
        self.assertEqual(
            installed_cells(_view("company/mcp/x@1.0.0", "claude", scope="user"), "ready"),
            ("ready", "user", "", ""),
        )

    def test_more_info_names_the_project_directory_and_the_harness(self) -> None:
        view = _view("company/mcp/x@1.0.0", "claude", root="/p/a")

        detailed = render_installed_artifact(view, PresentationProfile.MORE_INFO)
        brief = render_installed_artifact(view, PresentationProfile.LESS_INFO)

        self.assertIn("Project: /p/a", detailed)
        self.assertIn("Harness: claude", detailed)
        self.assertNotIn("Project: /p/a", brief)

    @given(
        st.lists(
            st.tuples(
                st.sampled_from(("claude", "codex", "opencode")),
                st.sampled_from(("user", "project")),
                st.sampled_from(("/p/a", "/p/b", "/p/c")),
                st.sampled_from(("ready", "update", "attention")),
            ),
            max_size=8,
        )
    )
    def test_the_status_and_project_count_follow_the_installations(self, made) -> None:
        installed = tuple(
            _view("company/skill/review@1.0.0", harness, health, scope, root)
            for harness, scope, root, health in made
        )

        cells = marketplace_cells("company/skill/review@1.2.0", installed, ())

        projects = {root for _, scope, root, _ in made if scope == "project"}
        expected_status = (
            "not installed"
            if not made
            else "update available"
            if any(health == "update" for *_, health in made)
            else "installed"
        )
        self.assertEqual(cells[1], expected_status)
        user = any(scope == "user" for _, scope, _, _ in made)
        count = f"{len(projects)} project{'s' if len(projects) != 1 else ''}" if projects else ""
        self.assertEqual(cells[2], " + ".join(part for part in ("user" * user, count) if part))
        holding = {harness for harness, *_ in made}
        self.assertEqual(cells[3].count("✓"), len(holding))


if __name__ == "__main__":
    unittest.main()
