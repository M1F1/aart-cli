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

_HEADINGS = ("Artifact", "Registry", "Upstream", "Status", "Scope", "Harnesses", "Configuration")


def _offered(coordinate: str) -> str:
    """The Artifact column: the offer without its Registry alias, which has its own (§181)."""

    return coordinate.partition("/")[2]


def _rows(env, screen: ConsumerScreen) -> list[str]:
    with mock.patch.dict(os.environ, env.xdg, clear=False):
        source = _actions(env).source()
        empty = ConsumerUiState(ConsumerSession(screen))
        state = ConsumerUiState(ConsumerSession(screen), rows=source.rows(empty))
        if screen is not ConsumerScreen.MARKETPLACE:
            return [line for line in frame(source, state) if "[ ]" in line]
        lines = source.actions(state)
        starts = [lines[0].index(label) for label in _HEADINGS]
        rows = []
        for line in lines[1:]:
            if "[ ]" in line:
                rows.append(["" for _ in starts])
            if line.strip() and rows:
                for i, start in enumerate(starts):
                    end = starts[i + 1] if i < len(starts) - 1 else len(line)
                    rows[-1][i] += " " + line[start:end].strip()
        return ["  ".join(cell.strip() for cell in row).rstrip() for row in rows]


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

        held = next(line for line in offers if _offered(COORDINATE) in line)
        other = next(line for line in offers if _offered(SECOND) in line)
        # Both Skills declare claude alone, so opencode is detected and not eligible.
        for cell in ("installed", "1 project", "claude ✓"):
            self.assertIn(cell, held)
        self.assertIn("not installed", other)
        self.assertTrue(other.endswith("  claude"), other)
        self.assertNotIn("opencode", held + other)
        (row,) = installations
        self.assertIn(COORDINATE, row)
        self.assertIn(" · claude", row)
        self.assertIn("project", row)
        self.assertIn(project, row)
        # Header alignment and lossless wrapping are held across generated widths in
        # marketplace_readable_rows_test; here the installed facts come from real receipts.


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
                "skill/review@1.2.0",
                "company",
                "",
                "update available",
                "user + 2 projects",
                "claude ✓, codex ✓, opencode",
                "not configured (3 missing)",
            ),
        )
        self.assertEqual(
            marketplace_cells("company/skill/lint@1.0.0", installed, ()),
            ("skill/lint@1.0.0", "company", "", "not installed", "", "", ""),
        )

    def test_an_installation_names_its_scope_and_project(self) -> None:
        self.assertEqual(
            installed_cells(_view("company/mcp/x@1.0.0", "claude", unset=("A",)), "ready"),
            ("ready", "project", "a", "not configured (1 missing)"),
        )
        self.assertEqual(
            installed_cells(_view("company/mcp/x@1.0.0", "claude", scope="user"), "ready"),
            ("ready", "user", "", "configured"),
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
        self.assertEqual(cells[3], expected_status)
        user = any(scope == "user" for _, scope, _, _ in made)
        count = f"{len(projects)} project{'s' if len(projects) != 1 else ''}" if projects else ""
        self.assertEqual(cells[4], " + ".join(part for part in ("user" * user, count) if part))
        holding = {harness for harness, *_ in made}
        self.assertEqual(cells[5].count("✓"), len(holding))


if __name__ == "__main__":
    unittest.main()
