from __future__ import annotations

import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.mcp_smoke import select_installed_mcps
from aart_cli.domain.harness import Scope
from aart_cli.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    ObjectDigest,
    SourceAlias,
)
from aart_cli.domain.installation_owner import InstallationOwner, installation_key
from aart_cli.domain.launch import Transport
from aart_cli.domain.receipts import InstallationReceipt, InstalledRecord

DIGEST = ObjectDigest("sha256", "a" * 64)


def installed(alias: str, harness: str, *, root: str = "/work") -> InstalledRecord:
    coordinate = ArtifactCoordinate(
        SourceAlias(alias), ArtifactIdentity("mcp", "identity"), "1.0.0"
    )
    owner = InstallationOwner(coordinate.source, coordinate.artifact, Scope.PROJECT, root, harness)
    tree = f"{root}/.{harness}/aart-cli/mcp/{alias}/identity"
    return InstalledRecord(
        coordinate,
        InstallationReceipt(
            "mcp/identity",
            tree,
            f"{tree}/launch",
            DIGEST,
            "/usr/bin/python3",
            Transport.STDIO,
            owner=owner,
            object_digest=DIGEST,
        ),
    )


class McpSmokeSelectionTest(unittest.TestCase):
    @given(
        selected=st.sets(st.sampled_from(("opencode", "tabnine", "claude")), min_size=1),
        aliases=st.lists(st.sampled_from(("local", "remote", "company")), min_size=1, unique=True),
    )
    def test_all_never_crosses_the_requested_harness_boundary(
        self, selected: set[str], aliases: list[str]
    ) -> None:
        records = tuple(
            installed(alias, harness)
            for alias in aliases
            for harness in ("opencode", "tabnine", "claude")
        )
        result = select_installed_mcps(
            records,
            scope=Scope.PROJECT,
            root="/work",
            harnesses=frozenset(selected),
            selectors=(),
            all_installed=True,
        )
        self.assertIsNone(result.failure)
        self.assertTrue(result.targets)
        self.assertEqual(
            {record.receipt.owner.harness for record in result.targets},  # type: ignore[union-attr]
            selected,
        )

    def test_all_stays_inside_scope_root_and_explicit_harnesses(self) -> None:
        records = (
            installed("local", "opencode"),
            installed("remote", "tabnine"),
            installed("local", "claude"),
            installed("local", "opencode", root="/other"),
        )
        selected = select_installed_mcps(
            records,
            scope=Scope.PROJECT,
            root="/work",
            harnesses=frozenset({"opencode", "tabnine"}),
            selectors=(),
            all_installed=True,
        )
        self.assertIsNone(selected.failure)
        self.assertEqual(
            {record.receipt.owner.harness for record in selected.targets},  # type: ignore[union-attr]
            {"opencode", "tabnine"},
        )
        self.assertEqual(
            {record.coordinate.source.value for record in selected.targets},
            {"local", "remote"},
        )

    def test_a_selector_never_launches_uninstalled_or_wrong_owner_content(self) -> None:
        opencode = installed("local", "opencode")
        key = installation_key(opencode.coordinate, opencode.receipt.owner)
        selected = select_installed_mcps(
            (opencode,),
            scope=Scope.PROJECT,
            root="/work",
            harnesses=frozenset({"opencode"}),
            selectors=(key,),
            all_installed=False,
        )
        self.assertEqual(selected.targets, (opencode,))

        absent = select_installed_mcps(
            (opencode,),
            scope=Scope.PROJECT,
            root="/work",
            harnesses=frozenset({"opencode"}),
            selectors=("remote/mcp/identity@1.0.0",),
            all_installed=False,
        )
        self.assertEqual(absent.targets, ())
        self.assertIn("no installed MCP", absent.failure or "")

    def test_empty_and_implicit_selection_are_non_success(self) -> None:
        for all_installed, selectors in ((False, ()), (True, ("mcp/identity",))):
            with self.subTest(all_installed=all_installed, selectors=selectors):
                result = select_installed_mcps(
                    (),
                    scope=Scope.PROJECT,
                    root="/work",
                    harnesses=frozenset({"opencode"}),
                    selectors=selectors,
                    all_installed=all_installed,
                )
                self.assertIsNotNone(result.failure)


if __name__ == "__main__":
    unittest.main()
