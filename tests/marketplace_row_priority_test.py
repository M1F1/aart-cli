"""CP-25.09: a Marketplace row leads with state and harnesses, not with prose (issue #10).

The Fast block put the complete artifact description on the focused row and Verbose repeated it,
which made the list hard to scan while leaving out the two facts that decide anything there:
whether the artifact is already installed, and which harnesses it can go into. The description is
not deleted -- it moves behind Verbose and Artifact Details, and search still reads it either way.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from aart_cli.application.consumer_views import PresentationProfile
from aart_cli.lifecycle.model import LifecycleItem, LifecycleKey, LifecycleStatus
from aart_cli.tui_consumer import render_marketplace_artifact
from aart_cli.tui_marketplace import (
    MarketplaceFilters,
    MarketplaceTarget,
    filter_marketplace_rows,
    project_marketplace_rows,
)
from tests.tui_marketplace_test import _catalog

KEY = "company/skill/review@1.0.0"

#: Long enough that rendering it unwrapped is the reported layout fault rather than a short label.
LONG_SUMMARY = (
    "Use review to improve agent work by reading the diff, naming what changed, and explaining "
    "the consequence of each change to somebody who did not write it."
)


def _rows(*profiles: str, lifecycle: tuple[LifecycleItem, ...] = ()):
    return project_marketplace_rows(
        _catalog(),
        MarketplaceTarget(profiles, "darwin", "project", "copy"),
        lifecycle=lifecycle,
    )


def _row(*profiles: str, lifecycle: tuple[LifecycleItem, ...] = ()):
    return next(row for row in _rows(*profiles, lifecycle=lifecycle) if row.key == KEY)


def _installed(row, profile: str, status: LifecycleStatus) -> tuple[LifecycleItem, ...]:
    return (LifecycleItem(LifecycleKey(row.coordinate, profile, "project"), status),)


def _fast(row) -> str:
    return "\n".join(render_marketplace_artifact(row, PresentationProfile.FAST))


def _verbose(row) -> str:
    return "\n".join(render_marketplace_artifact(row, PresentationProfile.VERBOSE))


class TheFastRowLeadsWithWhatDecidesTest(unittest.TestCase):
    def test_an_uninstalled_artifact_says_so_before_it_says_anything_else(self) -> None:
        rendered = _fast(_row("claude", "opencode"))

        self.assertIn("Not installed", rendered)
        self.assertLess(rendered.index("Not installed"), rendered.index("Eligible installation"))

    def test_a_current_installation_is_named_with_its_harness(self) -> None:
        bare = _row("claude")
        row = _row("claude", lifecycle=_installed(bare, "claude", LifecycleStatus.CURRENT))

        self.assertIn("Installed: claude:current", _fast(row))

    def test_an_update_available_installation_is_not_flattened_into_installed(self) -> None:
        """`current` and `update-available` are different answers to "should I act on this?"."""

        bare = _row("claude")
        row = _row("claude", lifecycle=_installed(bare, "claude", LifecycleStatus.UPDATE_AVAILABLE))

        self.assertIn("Installed: claude:update-available", _fast(row))

    def test_every_eligible_harness_is_named_on_the_fast_row(self) -> None:
        row = _row("claude", "codex", "opencode")

        rendered = _fast(row)

        for harness in row.eligible_harnesses:
            with self.subTest(harness=harness):
                self.assertIn(f"  - {harness}", rendered)


class TheDescriptionIsDisclosedRatherThanRepeatedTest(unittest.TestCase):
    def test_fast_does_not_carry_the_long_description(self) -> None:
        row = replace(_row("claude", "opencode"), summary=LONG_SUMMARY)

        self.assertNotIn(LONG_SUMMARY, _fast(row))

    def test_verbose_carries_it_exactly_once(self) -> None:
        row = replace(_row("claude", "opencode"), summary=LONG_SUMMARY)

        # Verbose wraps to the content measure, so compare on the collapsed text rather than on
        # the literal, which the wrap would break.
        collapsed = " ".join(_verbose(row).split())

        self.assertEqual(collapsed.count(" ".join(LONG_SUMMARY.split())), 1)

    def test_the_fast_block_stays_inside_a_narrow_terminal(self) -> None:
        """The reported fault was the layout, so the fixture has to be the long one.

        An unwrapped description on the focused row is what overflowed; every other line the block
        emits is a label, a coordinate or an indented harness name, all of which already fit.
        """

        row = replace(_row("claude", "opencode"), summary=LONG_SUMMARY)

        for line in render_marketplace_artifact(row, PresentationProfile.FAST):
            with self.subTest(line=line):
                self.assertLessEqual(len(line), 72)


class SearchStillReadsWhatTheRowNoLongerShowsTest(unittest.TestCase):
    def test_a_word_only_in_the_description_still_finds_the_artifact(self) -> None:
        rows = tuple(
            replace(row, summary=LONG_SUMMARY) if row.key == KEY else row
            for row in _rows("claude", "opencode")
        )

        found = filter_marketplace_rows(rows, MarketplaceFilters(text="consequence"))

        self.assertEqual(tuple(row.key for row in found), (KEY,))
        self.assertNotIn("consequence", _fast(next(row for row in rows if row.key == KEY)))


class TheStateComesFromTheLifecycleViewTest(unittest.TestCase):
    def test_the_renderer_reports_exactly_what_the_projection_recorded(self) -> None:
        """The renderer must not probe the machine or infer state from the artifact kind."""

        bare = _row("claude")
        row = _row("claude", lifecycle=_installed(bare, "claude", LifecycleStatus.DRIFTED))

        self.assertEqual(row.installed_statuses, ("claude:drifted",))
        self.assertIn("Installed: claude:drifted", _fast(row))

    def test_an_artifact_with_no_lifecycle_record_is_not_called_installed(self) -> None:
        row = _row("claude")

        self.assertEqual(row.installed_statuses, ())
        self.assertFalse(row.installed)
        self.assertIn("Not installed", _fast(row))


if __name__ == "__main__":
    unittest.main()
