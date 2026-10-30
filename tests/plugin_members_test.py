"""CP-51: a plugin's members are the skills its payload carries (§214, INV-329)."""

from __future__ import annotations

import tempfile
import unittest
from collections import Counter
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.consumer_views import (
    InstalledArtifactView,
    PresentationProfile,
    installed_row_cells,
)
from aart_cli.domain.artifact_usage import (
    InstalledName,
    UsageCount,
    UsageKind,
    installed_names,
    rank_usage,
    resolve_installed,
)
from aart_cli.domain.hooks import PluginEntry
from aart_cli.domain.identifiers import ArtifactCoordinate, ArtifactIdentity, SourceAlias
from aart_cli.domain.plugin_members import PluginMember, plugin_members
from aart_cli.domain.receipts import (
    ArtifactSettingsEntry,
    InstalledRecord,
    PlacedArtifactReceipt,
    placed_artifact_receipt_from_data,
    placed_artifact_receipt_to_data,
)
from aart_cli.domain.result import Err, Ok
from aart_cli.domain.telemetry import use_event
from aart_cli.protocol.authoring import package_plugin
from aart_cli.protocol.hashing import sha256_bytes
from tests.plugin_authoring_test import _MODULE, _compile, _manifest, _tree

_SEGMENT = st.sampled_from(["skills", "brainstorming", "writing-plans", "docs", "a", "SKILL.md"])
_PATH = st.lists(_SEGMENT, min_size=1, max_size=4).map("/".join)


def _expected(paths: list[str]) -> tuple[PluginMember, ...]:
    """INV-329 stated directly: each directory holding a `SKILL.md`, less the names two share."""

    holding = {
        path.rpartition("/")[0]
        for path in paths
        if path.rpartition("/")[2] == "SKILL.md" and "/" in path
    }
    named = Counter(directory.rpartition("/")[2] for directory in holding)
    return tuple(
        sorted(
            (
                PluginMember(directory.rpartition("/")[2], directory)
                for directory in holding
                if named[directory.rpartition("/")[2]] == 1
            ),
            key=lambda member: member.name,
        )
    )


class PluginMembersTest(unittest.TestCase):
    def test_each_skill_directory_is_a_member_named_by_it(self) -> None:
        members = plugin_members(
            (
                ".opencode/plugins/superpowers.js",
                "skills/writing-plans/SKILL.md",
                "skills/brainstorming/SKILL.md",
                "skills/brainstorming/visual-companion.md",
                "README.md",
            )
        )

        self.assertEqual(
            (
                PluginMember("brainstorming", "skills/brainstorming"),
                PluginMember("writing-plans", "skills/writing-plans"),
            ),
            members,
        )

    def test_a_skill_document_at_the_payload_root_is_no_member(self) -> None:
        self.assertEqual((), plugin_members(("SKILL.md", "index.js")))

    def test_a_name_two_directories_carry_is_no_member(self) -> None:
        members = plugin_members(
            ("skills/review/SKILL.md", "extra/review/SKILL.md", "skills/plan/SKILL.md")
        )

        self.assertEqual((PluginMember("plan", "skills/plan"),), members)

    def test_only_a_file_named_exactly_skill_md_makes_a_member(self) -> None:
        self.assertEqual((), plugin_members(("skills/x/skill.md", "skills/y/SKILL.md.bak")))

    @given(st.lists(_PATH, max_size=12))
    def test_members_are_exactly_the_uniquely_named_skill_directories(
        self, paths: list[str]
    ) -> None:
        self.assertEqual(_expected(paths), plugin_members(tuple(paths)))

    def test_a_member_is_refused_when_its_path_does_not_end_in_its_name(self) -> None:
        for name, path in (
            ("", "skills/"),
            ("a", "skills/b"),
            ("a/b", "skills/a/b"),
            ("a", "/skills/a"),
            ("a", "../a"),
        ):
            with self.subTest(name=name, path=path), self.assertRaises(ValueError):
                PluginMember(name, path)


class PackagedPluginMembersTest(unittest.TestCase):
    """The installing machine reads the members off the package it installs."""

    def _packaged(self, files: dict[str, str]):
        with tempfile.TemporaryDirectory() as raw:
            _tree(Path(raw), _manifest(), files)
            compiled = _compile(Path(raw))
        assert isinstance(compiled, Ok), getattr(compiled, "diagnostics", ())
        (artifact,) = compiled.value
        return package_plugin(artifact.canonical_entries)

    def test_package_plugin_carries_the_members_of_its_payload(self) -> None:
        packaged = self._packaged(
            {
                ".opencode/plugins/superpowers.js": _MODULE,
                "skills/brainstorming/SKILL.md": "---\nname: brainstorming\n---\n",
                "skills/writing-plans/SKILL.md": "---\nname: writing-plans\n---\n",
                "skills/writing-plans/notes.md": "notes\n",
            }
        )

        self.assertIsInstance(packaged, Ok, getattr(packaged, "diagnostics", ()))
        assert isinstance(packaged, Ok)
        self.assertEqual(
            (
                PluginMember("brainstorming", "skills/brainstorming"),
                PluginMember("writing-plans", "skills/writing-plans"),
            ),
            packaged.value.members,
        )

    def test_a_plugin_carrying_no_skill_has_no_members(self) -> None:
        packaged = self._packaged({".opencode/plugins/superpowers.js": _MODULE})

        assert isinstance(packaged, Ok), getattr(packaged, "diagnostics", ())
        self.assertEqual((), packaged.value.members)


_ENTRY = ArtifactSettingsEntry(
    "opencode",
    "/p/opencode.json",
    "plugin",
    PluginEntry("./.opencode/aart-cli/plugin/company/superpowers/payload/index.js"),
)


def _receipt(members: tuple[PluginMember, ...]) -> PlacedArtifactReceipt:
    return PlacedArtifactReceipt(
        "company/plugin/superpowers",
        "/p/.opencode/aart-cli/plugin/company/superpowers",
        sha256_bytes(b"payload"),
        settings=(_ENTRY,),
        members=members,
    )


class APluginReceiptRecordsItsMembersTest(unittest.TestCase):
    def test_the_members_survive_a_round_trip(self) -> None:
        receipt = _receipt(
            (
                PluginMember("brainstorming", "skills/brainstorming"),
                PluginMember("writing-plans", "skills/writing-plans"),
            )
        )

        data = placed_artifact_receipt_to_data(receipt)

        self.assertEqual(
            [
                {"name": "brainstorming", "path": "skills/brainstorming"},
                {"name": "writing-plans", "path": "skills/writing-plans"},
            ],
            data["members"],
        )
        self.assertEqual(Ok(receipt), placed_artifact_receipt_from_data(data))

    def test_a_receipt_without_members_writes_none(self) -> None:
        self.assertNotIn("members", placed_artifact_receipt_to_data(_receipt(())))

    def test_two_members_of_one_name_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            _receipt((PluginMember("a", "skills/a"), PluginMember("a", "other/a")))

    def test_a_member_that_is_not_a_skill_directory_reads_back_as_invalid(self) -> None:
        data = placed_artifact_receipt_to_data(_receipt(()))
        data["members"] = [{"name": "a", "path": "../a"}]

        self.assertIsInstance(placed_artifact_receipt_from_data(data), Err)


def _view(members: tuple[str, ...]) -> InstalledArtifactView:
    return InstalledArtifactView(
        "company/plugin/superpowers@7.0.0",
        "ready",
        (),
        (),
        ("details",),
        harness="opencode",
        members=members,
    )


class InstalledShowsAPluginsMembersTest(unittest.TestCase):
    def test_the_row_says_how_many_skills_the_plugin_carries(self) -> None:
        self.assertEqual(
            "superpowers@7.0.0 (2 skills)",
            installed_row_cells(_view(("brainstorming", "writing-plans")), "ready")[0],
        )
        self.assertEqual(
            "superpowers@7.0.0 (1 skill)", installed_row_cells(_view(("plan",)), "ready")[0]
        )
        self.assertEqual("superpowers@7.0.0", installed_row_cells(_view(()), "ready")[0])

    def test_details_name_every_member_and_say_they_go_with_the_plugin(self) -> None:
        from aart_cli.tui_consumer import render_installed_artifact

        for profile in (PresentationProfile.LESS_INFO, PresentationProfile.MORE_INFO):
            with self.subTest(profile=profile):
                text = "\n".join(
                    render_installed_artifact(_view(("brainstorming", "writing-plans")), profile)
                )
                self.assertIn(
                    "Skills it carries, installed and removed with it: "
                    "brainstorming, writing-plans.",
                    text,
                )

        self.assertNotIn(
            "Skills it carries",
            "\n".join(render_installed_artifact(_view(()), PresentationProfile.LESS_INFO)),
        )


_NAMES = st.sampled_from(["brainstorming", "writing-plans", "plan", "review", "x"])


def _plugin(members: tuple[str, ...]) -> InstalledRecord:
    return InstalledRecord(
        ArtifactCoordinate(
            SourceAlias("company"), ArtifactIdentity("plugin", "superpowers"), "7.0.0"
        ),
        _receipt(tuple(PluginMember(name, f"skills/{name}") for name in members)),
    )


class AMembersUseIsThePluginsTest(unittest.TestCase):
    MOMENT = "2026-10-30T12:00:00Z"
    ID = "7515ec68-1e98-46ca-bd90-9f6a70c84d11"

    def test_each_member_is_a_name_opencode_calls_the_plugin_by(self) -> None:
        self.assertEqual(
            (
                InstalledName(
                    "opencode",
                    UsageKind.SKILL,
                    "brainstorming",
                    "company/plugin/superpowers",
                    "7.0.0",
                    member="brainstorming",
                ),
            ),
            installed_names((_plugin(("brainstorming",)),)),
        )

    def test_activity_ranks_a_members_use_as_installed_under_the_plugin(self) -> None:
        (rank,) = rank_usage(
            (UsageCount("opencode", UsageKind.SKILL, "brainstorming", 3, self.MOMENT),),
            installed_names((_plugin(("brainstorming", "writing-plans")),)),
        )

        self.assertEqual("company/plugin/superpowers:brainstorming", rank.artifact)
        self.assertTrue(rank.installed)
        self.assertEqual(3, rank.uses)

    def test_two_members_are_ranked_apart(self) -> None:
        ranks = rank_usage(
            (
                UsageCount("opencode", UsageKind.SKILL, "brainstorming", 3, self.MOMENT),
                UsageCount("opencode", UsageKind.SKILL, "writing-plans", 1, self.MOMENT),
            ),
            installed_names((_plugin(("brainstorming", "writing-plans")),)),
        )

        self.assertEqual(
            [
                "company/plugin/superpowers:brainstorming",
                "company/plugin/superpowers:writing-plans",
            ],
            [rank.artifact for rank in ranks],
        )

    def test_telemetry_sends_it_as_a_skill_of_the_plugin_in_version_1s_fields(self) -> None:
        event = use_event(
            self.ID,
            self.MOMENT,
            "opencode",
            UsageKind.SKILL,
            "brainstorming",
            installed_names((_plugin(("brainstorming",)),)),
        )

        assert event is not None
        self.assertEqual(
            {
                "event_id": self.ID,
                "occurred_at": self.MOMENT,
                "event_type": "artifact.used",
                "source": "opencode_plugin",
                "artifact_id": "superpowers:brainstorming",
                "artifact_type": "skill",
                "artifact_version": "7.0.0",
            },
            event.document(),
        )

    @given(
        st.lists(_NAMES, unique=True, max_size=4),
        st.sampled_from(["opencode", "claude"]),
        _NAMES,
    )
    def test_a_use_is_the_plugins_exactly_when_it_names_a_member_in_its_harness(
        self, members: list[str], harness: str, used: str
    ) -> None:
        names = installed_names((_plugin(tuple(members)),))

        resolved = resolve_installed(harness, UsageKind.SKILL, used, names)
        event = use_event(self.ID, self.MOMENT, harness, UsageKind.SKILL, used, names)

        if harness == "opencode" and used in members:
            assert resolved is not None and event is not None
            self.assertEqual(
                ("company/plugin/superpowers", used), (resolved.artifact, resolved.member)
            )
            self.assertEqual(f"superpowers:{used}", event.document()["artifact_id"])
        else:
            self.assertIsNone(resolved)
            self.assertIsNone(event)

    def test_an_mcp_tool_of_a_members_name_is_not_the_plugin(self) -> None:
        names = installed_names((_plugin(("brainstorming",)),))

        self.assertIsNone(resolve_installed("opencode", UsageKind.MCP, "brainstorming_x", names))


if __name__ == "__main__":
    unittest.main()
