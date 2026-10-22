"""§190, INV-291, D-472: the Registry view names what each promotion published.

The owner found the Recent promotions list on the Maintainer Registry screen unreadable: every
line was a digest, the snapshot a promotion produced and the candidate ids it promoted, so nobody
could tell which artifacts had been promoted. The approved versions already say which
`kind/name@version` each candidate became, so the view names them and keeps the digests for
Verbose.
"""

from __future__ import annotations

import re
import unittest
from dataclasses import replace

from aart_cli.application.maintainer_sync import ApprovedRegistryState
from aart_cli.application.maintainer_views import (
    MaintainerPromotedVersionView,
    MaintainerRegistryTransactionView,
    project_maintainer_registry,
)
from aart_cli.domain.identifiers import SourceAlias
from aart_cli.protocol.native_tree import SnapshotOrigin, SourceSnapshot
from aart_cli.tui_maintainer import maintainer_registry_detail, render_maintainer_registry
from tests.maintainer_registry_view_test import _bundle, _digest, _promote

_HEX = re.compile(r"[0-9a-f]{8,}")


class ReadablePromotionsTest(unittest.TestCase):
    def setUp(self) -> None:
        empty = SourceSnapshot(SnapshotOrigin.LOCAL, ())
        state = ApprovedRegistryState(SourceAlias("company"), "f" * 40, _digest("e"), ())
        first, earlier, _ = _promote(_bundle(name="github-mcp"), empty, state)
        self.later = _bundle(name="jira-mcp", version="2.3.0")
        self.registry, latest, _ = _promote(self.later, first, earlier)
        # The synchronized state holds every approved version, not only the latest promotion's.
        self.state = replace(latest, versions=earlier.versions + latest.versions)
        self.view = project_maintainer_registry(
            SourceAlias("company"), self.state, self.registry, self.registry
        )

    def _promotions(self, lines: tuple[str, ...]) -> list[str]:
        start = next(index for index, line in enumerate(lines) if "Recent promotions" in line)
        return list(lines[start + 1 :])

    def test_each_promotion_names_the_versions_it_published(self) -> None:
        self.assertEqual(
            [[item.artifact for item in step.versions] for step in self.view.transactions],
            [["mcp/jira-mcp@2.3.0"], ["mcp/github-mcp@1.0.0"]],
        )

    def test_the_list_shows_names_newest_first_and_no_digest(self) -> None:
        promotions = self._promotions(render_maintainer_registry(self.view, selected=True))

        self.assertEqual(
            [line.strip() for line in promotions],
            [
                "1. 1 version",
                "mcp/jira-mcp@2.3.0",
                "2. 1 version",
                "mcp/github-mcp@1.0.0",
            ],
        )
        self.assertEqual([line for line in promotions if _HEX.search(line)], [])

    def test_verbose_keeps_every_digest_beside_the_name(self) -> None:
        detail = "\n".join(maintainer_registry_detail(self.view))
        transaction = self.view.transactions[0]

        self.assertIn(transaction.snapshot_after, detail)
        self.assertIn(f"mcp/jira-mcp@2.3.0  candidate {self.later.candidate.id.value}", detail)

    def test_a_version_no_longer_published_is_said_so_with_its_candidate(self) -> None:
        gone = "c" * 64
        transaction = MaintainerRegistryTransactionView(
            "a" * 64,
            "b" * 64,
            "self-contained",
            (
                MaintainerPromotedVersionView(gone, None),
                MaintainerPromotedVersionView("d" * 64, "skill/review@1.0.0"),
            ),
        )
        view = replace(self.view, transactions=(transaction,))

        promotions = [
            line.strip()
            for line in self._promotions(render_maintainer_registry(view, selected=False))
        ]

        # A named version sorts first; one the Registry no longer publishes is still accounted for.
        self.assertEqual(promotions[0], "1. 2 versions")
        self.assertEqual(promotions[1], "skill/review@1.0.0")
        self.assertTrue(promotions[2].startswith("no longer in this Registry (candidate cccc"))
        self.assertEqual(transaction.candidate_ids, ("d" * 64, gone))

    def test_an_unaudited_version_is_named_in_the_diagnostic(self) -> None:
        stripped = SourceSnapshot(
            self.registry.origin,
            tuple(
                item
                for item in self.registry.entries
                if not str(item.path).startswith("registry/promotions/")
            ),
        )

        view = project_maintainer_registry(SourceAlias("company"), self.state, stripped, stripped)

        (message,) = [line for line in view.diagnostics if "approval" in line]
        self.assertIn("mcp/github-mcp@1.0.0", message)
        self.assertIn("mcp/jira-mcp@2.3.0", message)
        self.assertIsNone(_HEX.search(message), message)


if __name__ == "__main__":
    unittest.main()
