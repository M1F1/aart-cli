"""INV-280: a Marketplace offer says which Registry offers it and which upstream it came from.

The owner adopted the same Skill name from two repositories under two Registry names, and the
Marketplace could not tell them apart at a glance: the Artifact column carried the Registry alias
and nothing said where the work came from. Registry and Upstream are columns now, drawn with the
details `d` shows (§196); the Artifact column is `name@version` and the kind is its Type.
"""

from __future__ import annotations

import dataclasses
import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.consumer_views import marketplace_cells, short_upstream
from aart_cli.tui_consumer import frame
from aart_cli.tui_marketplace_rows import render_marketplace_rows
from tests.credential_fixtures import credential_url
from tests.marketplace_cursor_description_test import _distinct, _listed

_SEGMENT = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_.", min_size=1, max_size=12
).filter(lambda item: item not in (".", "..") and not item.endswith(".git"))


class ShortUpstreamTest(unittest.TestCase):
    def test_known_forms_read_as_owner_and_repository(self) -> None:
        for url, expected in (
            ("https://github.com/obra/superpowers.git", "obra/superpowers"),
            ("https://github.com/obra/superpowers/", "obra/superpowers"),
            ("git@github.com:obra/superpowers.git", "obra/superpowers"),
            ("ssh://git@git.example:2222/group/sub/tools.git", "sub/tools"),
            (credential_url("git.example", "/acme/skills", held="token"), "acme/skills"),
            ("/home/me/src/authors", "src/authors"),
            ("file:///home/me/src/authors", "src/authors"),
            ("", ""),
        ):
            with self.subTest(url=url):
                self.assertEqual(short_upstream(url), expected)

    @given(
        st.sampled_from(("https://", "http://", "ssh://", "git+ssh://")),
        st.sampled_from(("", "user@", "user:secret-token@")),
        st.sampled_from(("github.com", "git.example:2222", "10.0.0.1")),
        st.lists(_SEGMENT, min_size=0, max_size=2),
        _SEGMENT,
        _SEGMENT,
        st.sampled_from(("", ".git", "/", ".git/")),
    )
    def test_any_url_reads_as_its_last_two_path_segments_and_never_its_host_or_secret(
        self, scheme, userinfo, host, groups, owner, repository, suffix
    ) -> None:
        url = f"{scheme}{userinfo}{host}/{'/'.join((*groups, owner, repository))}{suffix}"

        shown = short_upstream(url)

        self.assertEqual(shown, f"{owner}/{repository}")
        if userinfo:
            self.assertNotIn(userinfo, shown)


class MarketplaceUpstreamColumnsTest(unittest.TestCase):
    def test_an_offer_s_cells_lead_with_artifact_registry_and_upstream(self) -> None:
        self.assertEqual(
            marketplace_cells(
                "company/skill/review@1.2.0",
                (),
                ("claude",),
                upstream="https://github.com/obra/superpowers.git",
            ),
            (
                "review@1.2.0",
                "Skill",
                "company",
                "obra/superpowers",
                "not installed",
                "",
                "claude",
                "",
            ),
        )

    def test_the_rows_are_keyed_by_offer_while_the_artifact_column_drops_the_alias(self) -> None:
        cells = (
            "review@1.2.0",
            "Skill",
            "company",
            "obra/superpowers",
            "not installed",
            "",
            "",
            "",
        )
        key = "company/skill/review@1.2.0"

        lines = render_marketplace_rows(
            (cells,), current=key, selected=(key,), keys=(key,), width=120, details=True
        )

        self.assertEqual(
            lines[0].split(),
            [
                "Artifact",
                "Type",
                "Registry",
                "Upstream",
                "Status",
                "Scope",
                "Harnesses",
                "Configuration",
            ],
        )
        self.assertTrue(lines[2].startswith("> [x] review@1.2.0"), lines)
        self.assertNotIn("company/skill", lines[2])

    def test_the_marketplace_frame_shows_the_columns_and_more_info_the_whole_upstream(self) -> None:
        composed = _distinct()
        first = composed.marketplace[0]
        url = "https://git.example/acme/superpowers.git"
        offer = dataclasses.replace(first, row=dataclasses.replace(first.row, upstream=url))
        source, state = _listed(
            dataclasses.replace(composed, marketplace=(offer, *composed.marketplace[1:]))
        )
        state = dataclasses.replace(
            state, cursor=0, viewport_columns=160, viewport_rows=60, marketplace_details=True
        )

        drawn = "\n".join(frame(source, state))

        row = offer.row
        self.assertIn("Registry", drawn)
        self.assertIn("Upstream", drawn)
        line = next(item for item in drawn.splitlines() if item.startswith(">"))
        self.assertIn(f"{row.identity.name}@{row.version}", line)
        self.assertIn(str(row.source_alias), line)
        self.assertIn("acme/superpowers", line)
        self.assertNotIn(row.key, line)
        self.assertIn(f"Upstream {url}", " ".join(" ".join(source.description(state)).split()))

    def test_more_info_redacts_credentials_in_the_upstream_and_the_row_never_shows_them(
        self,
    ) -> None:
        composed = _distinct()
        first = composed.marketplace[0]
        url = credential_url("git.example", "/acme/superpowers.git", held="secret-token")
        offer = dataclasses.replace(first, row=dataclasses.replace(first.row, upstream=url))
        source, state = _listed(
            dataclasses.replace(composed, marketplace=(offer, *composed.marketplace[1:]))
        )
        state = dataclasses.replace(state, cursor=0, viewport_columns=160, viewport_rows=60)

        drawn = "\n".join((*frame(source, state), *source.description(state)))

        self.assertNotIn("secret-token", drawn)
        self.assertIn(
            "Upstream https://[redacted]@git.example/acme/superpowers.git",
            " ".join(" ".join(source.description(state)).split()),
        )


if __name__ == "__main__":
    unittest.main()
