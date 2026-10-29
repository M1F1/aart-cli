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


def installed(
    alias: str,
    harness: str,
    *,
    root: str = "/work",
    name: str = "identity",
    version: str = "1.0.0",
) -> InstalledRecord:
    coordinate = ArtifactCoordinate(SourceAlias(alias), ArtifactIdentity("mcp", name), version)
    owner = InstallationOwner(coordinate.source, coordinate.artifact, Scope.PROJECT, root, harness)
    tree = f"{root}/.{harness}/aart-cli/mcp/{alias}/{name}"
    return InstalledRecord(
        coordinate,
        InstallationReceipt(
            f"mcp/{name}",
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


def _select(records: tuple[InstalledRecord, ...], *selectors: str, harnesses=("opencode",)):
    return select_installed_mcps(
        records,
        scope=Scope.PROJECT,
        root="/work",
        harnesses=frozenset(harnesses),
        selectors=selectors,
        all_installed=False,
    )


class SelectorWithoutVersionTest(unittest.TestCase):
    """`ALIAS/KIND/NAME[@VERSION]`, as `consume inputs` reads it (§170.1)."""

    def test_a_coordinate_without_its_version_selects_the_installation(self) -> None:
        opencode = installed("company", "opencode")

        selected = _select((opencode,), "company/mcp/identity")

        self.assertIsNone(selected.failure)
        self.assertEqual(selected.targets, (opencode,))

    def test_it_selects_the_artifact_in_every_requested_harness(self) -> None:
        records = (
            installed("company", "opencode"),
            installed("company", "claude", version="2.0.0"),
        )

        selected = _select(records, "company/mcp/identity", harnesses=("opencode", "claude"))

        self.assertEqual(
            {record.receipt.owner.harness for record in selected.targets},  # type: ignore[union-attr]
            {"opencode", "claude"},
        )

    def test_an_artifact_is_named_whole(self) -> None:
        records = (installed("company", "opencode", name="identity"),)

        for selector in ("company/mcp/ident", "company/mcp/identity-extra", "mcp/identity"):
            with self.subTest(selector=selector):
                self.assertEqual(_select(records, selector).targets, ())

    def test_another_version_is_refused_and_the_installed_one_is_named(self) -> None:
        records = (installed("company", "opencode", version="1.0.0"),)

        selected = _select(records, "company/mcp/identity@0.9.0")

        self.assertEqual(selected.targets, ())
        self.assertIn("names no installed MCP target", selected.failure or "")
        self.assertIn("did you mean company/mcp/identity@1.0.0?", selected.failure or "")

    def test_nothing_alike_installed_suggests_nothing(self) -> None:
        selected = _select((installed("company", "opencode"),), "company/mcp/other")

        self.assertNotIn("did you mean", selected.failure or "")

    @given(
        harnesses=st.sets(st.sampled_from(("opencode", "claude")), min_size=1),
        version=st.sampled_from(("1.0.0", "2.3.4-rc.1", "1.0.0+corp")),
        form=st.sampled_from(("bare", "versioned", "key")),
    )
    def test_every_form_selects_what_the_installation_key_selects(
        self, harnesses: set[str], version: str, form: str
    ) -> None:
        records = tuple(
            installed("company", harness, version=version) for harness in ("opencode", "claude")
        ) + (installed("other", "opencode", version=version),)
        requested = tuple(record for record in records if record.receipt.owner.harness in harnesses)  # type: ignore[union-attr]
        wanted = tuple(
            record for record in requested if record.coordinate.source.value == "company"
        )
        selectors = {
            "bare": ("company/mcp/identity",),
            "versioned": (f"company/mcp/identity@{version}",),
            "key": tuple(
                installation_key(record.coordinate, record.receipt.owner) for record in wanted
            ),
        }[form]

        selected = _select(records, *selectors, harnesses=tuple(harnesses))

        self.assertIsNone(selected.failure)
        self.assertEqual(set(selected.targets), set(wanted))


if __name__ == "__main__":
    unittest.main()
