"""CP-25.13: screen 22a parts Configuration from Credentials (issue #16).

The screen has two semantic sections and drew them packed: each heading sat against its own first
row and against the other section's block, so the two headings read as labels on a single list
rather than as the boundary between two kinds of thing -- values AART stores, and references it
deliberately never reads.

One empty line after each heading, and one between a completed Configuration block and the
Credentials heading. The spacing is layout only: it manufactures no row, so the cursor still lands
on identifiers and references, and no credential material appears because none is ever in the view.
"""

from __future__ import annotations

import datetime as dt
import unittest

from aart_cli.application.consumer_session import assemble_consumer_machine
from aart_cli.application.consumer_ui import (
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import (
    ConfigurationFileView,
    ConsumerScreen,
    ConsumerSession,
    CredentialRecordView,
    PresentationProfile,
)
from aart_cli.tui_consumer import (
    CanonicalScreenSource,
    _reload,
    frame,
    render_artifact_user_inputs,
    screens_from,
)
from tests.consumer_session_test import TOKEN, inspection, observed
from tests.credential_fixtures import access_token

COORDINATE = "public/mcp/github@1.6.0"
SECRET = access_token()


def _configuration(*values: tuple[str, str]) -> ConfigurationFileView:
    return ConfigurationFileView(
        COORDINATE,
        "claude",
        "/opt/agents/mcp/github/config/claude.conf",
        "matched",
        values,
        inputs=tuple(name for name, _ in values),
    )


def _credential(name: str = "github-token", health: str = "present") -> CredentialRecordView:
    return CredentialRecordView(
        f"macos-keychain:github.com:{name}",
        name,
        "macos-keychain",
        "github.com",
        "work",
        "available",
        health,
        "reference resolves",
        (COORDINATE,),
        ("verify",),
    )


def _drawn(configurations, credentials, current_row: str = "") -> tuple[str, ...]:
    return render_artifact_user_inputs(
        COORDINATE, configurations, credentials, current_row, PresentationProfile.FAST
    )


class TheTwoSectionsAreDrawnApartTest(unittest.TestCase):
    def test_both_sections_are_parted_and_each_heading_stands_off_its_rows(self) -> None:
        drawn = _drawn((_configuration(("github-org", "acme")),), (_credential(),))

        self.assertEqual(
            drawn,
            (
                "Configuration",
                "",
                "  github-org",
                "    claude: acme — matched",
                "",
                "Credentials",
                "",
                "  github-token: Configured securely",
            ),
        )

    def test_configuration_alone_ends_with_its_last_value(self) -> None:
        """No trailing blank: the separator belongs between sections, not after the last one."""

        drawn = _drawn((_configuration(("github-org", "acme")),), ())

        self.assertEqual(
            drawn,
            (
                "Configuration",
                "",
                "  github-org",
                "    claude: acme — matched",
            ),
        )

    def test_credentials_alone_open_on_their_own_heading(self) -> None:
        """Nothing precedes them, so there is nothing to be parted from."""

        drawn = _drawn((), (_credential(),))

        self.assertEqual(
            drawn,
            (
                "Credentials",
                "",
                "  github-token: Configured securely",
            ),
        )

    def test_an_artifact_declaring_neither_draws_no_section_at_all(self) -> None:
        self.assertEqual(_drawn((), ()), ())

    def test_the_cursor_still_marks_the_row_it_is_on(self) -> None:
        """Spacing is layout: it moves no row and takes no mark with it."""

        drawn = _drawn(
            (_configuration(("github-org", "acme")),),
            (_credential(),),
            current_row="configuration:github-org",
        )
        marked = [line for line in drawn if line.startswith(">")]

        self.assertEqual(len(marked), 1)
        self.assertIn("github-org", marked[0])

    def test_no_blank_line_is_ever_a_value_row(self) -> None:
        """A blank between sections must not read as a harness with nothing in it."""

        drawn = _drawn(
            (_configuration(("github-org", "acme"), ("github-team", "platform")),),
            (_credential(), _credential("jira-token", "missing")),
        )
        blanks = [index for index, line in enumerate(drawn) if not line]

        self.assertEqual(len(blanks), 3)
        for index in blanks:
            self.assertFalse(drawn[index].strip())
            self.assertNotIn("    ", drawn[index])

    def test_two_credentials_are_one_block_under_one_heading(self) -> None:
        """The blank follows the heading once; the references below it are one list."""

        drawn = _drawn((), (_credential(), _credential("jira-token", "missing")))

        self.assertEqual(
            drawn,
            (
                "Credentials",
                "",
                "  github-token: Configured securely",
                "  jira-token: Missing",
            ),
        )


class TheCredentialBoundaryIsUnchangedTest(unittest.TestCase):
    def test_a_reference_is_drawn_by_name_and_health_and_never_by_value(self) -> None:
        """The view holds no material to leak, and this is the test that keeps it that way."""

        drawn = "\n".join(_drawn((), (_credential(),)))

        self.assertIn("github-token", drawn)
        self.assertIn("Configured securely", drawn)
        self.assertNotIn(SECRET, drawn)
        self.assertNotIn("macos-keychain", drawn)

    def test_a_configuration_value_still_names_the_harness_that_holds_it(self) -> None:
        drawn = _drawn((_configuration(("github-org", "acme")),), ())

        self.assertIn("    claude: acme — matched", drawn)


if __name__ == "__main__":
    unittest.main()


class TheSpacingIsNotARowTest(unittest.TestCase):
    """Through the real screen source: a blank line the frame draws is never one the cursor visits."""

    def _details(self):
        machine = assemble_consumer_machine(
            (inspection(),), credentials=(observed(TOKEN),), today=dt.date(2026, 9, 14)
        )
        source = CanonicalScreenSource(screens_from(machine))
        state = _reload(
            source, ConsumerUiState(ConsumerSession(ConsumerScreen.CREDENTIALS)), entering=True
        )
        details, _ = reduce_consumer_ui(
            state,
            ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=ConsumerScreen.USER_INPUT_DETAILS),
        )
        return source, _reload(source, details, entering=True)

    def test_every_row_is_something_to_press(self) -> None:
        _, details = self._details()

        self.assertTrue(details.rows)
        self.assertTrue(all(row.strip() for row in details.rows))

    def test_the_drawn_screen_opens_and_closes_on_content(self) -> None:
        source, details = self._details()

        drawn = frame(source, details)

        self.assertTrue(drawn[0].strip())
        self.assertTrue(drawn[-1].strip())
        self.assertNotIn("\n\n\n", "\n".join(drawn))
