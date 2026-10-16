"""§171: a plugin owns one path in the harness's plugin list, and registering it is high risk.

OpenCode 1.18 reads the plugins it loads from the `plugin` list of `opencode.json`, beside npm specs
and paths somebody else put there. Installing one owns exactly one member of that list, spelled as
the entry module's path relative to the file (§171.3), and leaves the rest as it was (INV-257). The
path is the whole identity: nothing else in a string can tell two plugins apart, and nothing else
may be written, because an npm spec or a git URL would load whatever it resolves to on the day,
not what was reviewed (INV-255).

Registering one is what makes the harness run the code, so it is the effect that carries
`high-risk-execution` (INV-256), while a hook's entry stays a configuration mutation.
"""

from __future__ import annotations

import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.domain.effects import MergeSettingsEntry, RiskClass, UnmergeSettingsEntry
from aart_cli.domain.harness import Scope, plugin_target
from aart_cli.domain.hooks import (
    HookEntry,
    HookEntryShape,
    PluginEntry,
    merge_settings_entry,
    remove_settings_entry,
    settings_entry_at,
    settings_entry_to_json,
)
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.receipts import (
    ArtifactSettingsEntry,
    PlacedArtifactReceipt,
    placed_artifact_receipt_from_data,
    placed_artifact_receipt_to_data,
)
from aart_cli.domain.result import Ok
from aart_cli.protocol.hashing import sha256_bytes

PATH = "plugin"
REFERENCE = (
    "./.opencode/aart-cli/plugin/company/superpowers/payload/.opencode/plugins/superpowers.js"
)
ENTRY = PluginEntry(REFERENCE)
THEIRS = ["opencode-wakatime", "./mine/plugin.ts"]


def _merged(document: dict, entry: PluginEntry = ENTRY) -> dict:
    result = merge_settings_entry(document, PATH, entry)
    assert isinstance(result, Ok), getattr(result, "diagnostics", ())
    return result.value


class APluginEntryIsARelativePathToReviewedCodeTest(unittest.TestCase):
    def test_it_is_written_as_the_path_itself(self) -> None:
        self.assertEqual(REFERENCE, settings_entry_to_json(ENTRY))

    def test_only_a_relative_path_inside_the_tree_to_a_module_is_accepted(self) -> None:
        for refused in (
            "/abs/plugin.js",
            "opencode-wakatime",
            "opencode-wakatime@1.2.0",
            "file:///abs/plugin.js",
            "git+https://example.invalid/p.git",
            "./a/../../escape.js",
            "./a/plugin.json",
            "./a/plugin.js\n",
            "",
        ):
            with self.subTest(reference=refused), self.assertRaises(ValueError):
                PluginEntry(refused)
        for accepted in ("./p.js", "./a/b/p.mjs", "./a/p.ts"):
            with self.subTest(reference=accepted):
                self.assertEqual(accepted, PluginEntry(accepted).reference)

    @given(st.text(min_size=1, max_size=40))
    def test_nothing_that_is_not_a_dot_slash_path_becomes_an_entry(self, raw: str) -> None:
        try:
            entry = PluginEntry(raw)
        except ValueError:
            return
        self.assertTrue(entry.reference.startswith("./"))
        self.assertNotIn("..", entry.reference.split("/"))
        self.assertNotIn(":", entry.reference)


class APluginOwnsOneMemberOfTheListTest(unittest.TestCase):
    def test_a_file_without_the_list_gains_it_with_the_entry(self) -> None:
        self.assertEqual({"plugin": [REFERENCE]}, _merged({}))

    def test_everybody_elses_plugins_and_keys_stay_as_found(self) -> None:
        document = {"$schema": "https://opencode.ai/config.json", "plugin": list(THEIRS)}

        merged = _merged(document)

        self.assertEqual([*THEIRS, REFERENCE], merged["plugin"])
        self.assertEqual("https://opencode.ai/config.json", merged["$schema"])

    def test_merging_twice_converges_on_one_entry(self) -> None:
        self.assertEqual(_merged({}), _merged(_merged({})))

    def test_it_is_found_by_its_path_and_only_by_its_path(self) -> None:
        document = _merged({"plugin": list(THEIRS)})

        self.assertEqual(Ok(REFERENCE), settings_entry_at(document, PATH, ENTRY))
        self.assertEqual(Ok(None), settings_entry_at({"plugin": list(THEIRS)}, PATH, ENTRY))

    def test_removal_takes_this_entry_and_leaves_the_list(self) -> None:
        removed = remove_settings_entry(_merged({"plugin": list(THEIRS)}), PATH, ENTRY)

        self.assertEqual(Ok({"plugin": THEIRS}), removed)

    @given(st.lists(st.sampled_from(("a", "b", "./c.js", "./d/e.ts")), max_size=5))
    def test_install_then_uninstall_leaves_any_list_as_it_was(self, theirs: list[str]) -> None:
        document = {"plugin": list(theirs)}

        removed = remove_settings_entry(_merged(document), PATH, ENTRY)

        self.assertEqual(Ok({"plugin": [item for item in theirs if item != REFERENCE]}), removed)


class RegisteringAPluginIsHighRiskTest(unittest.TestCase):
    def test_loading_a_plugin_is_high_risk_and_every_other_list_entry_is_not(self) -> None:
        hook = HookEntry(HookEntryShape.NESTED_COMMAND, "Bash", "/artifacts/lint/run.sh")
        settings = ("claude", "company/hook/lint", "/p/.claude/settings.json", "hooks.Stop")
        plugin = ("opencode", "company/plugin/superpowers", "/p/opencode.json", PATH)

        self.assertIs(RiskClass.HIGH_RISK_EXECUTION, MergeSettingsEntry(*plugin, ENTRY).risk)
        # Taking the entry out stops the code from running; it changes configuration and no more.
        for risk in (
            UnmergeSettingsEntry(*plugin, ENTRY).risk,
            MergeSettingsEntry(*settings, hook).risk,
            UnmergeSettingsEntry(*settings, hook).risk,
        ):
            self.assertIs(RiskClass.CONFIGURATION_MUTATION, risk)

    def test_a_ceiling_below_high_risk_refuses_the_plugin_and_not_the_hook(self) -> None:
        policy = EffectivePolicy(risk_ceiling=RiskClass.CONFIGURATION_MUTATION)
        hook = HookEntry(HookEntryShape.NESTED_COMMAND, "Bash", "/artifacts/lint/run.sh")
        settings = ("claude", "company/hook/lint", "/p/.claude/settings.json", "hooks.Stop")
        plugin = ("opencode", "company/plugin/superpowers", "/p/opencode.json", PATH)

        self.assertFalse(policy.permits_effect(MergeSettingsEntry(*plugin, ENTRY)))
        self.assertTrue(policy.permits_effect(MergeSettingsEntry(*settings, hook)))
        # Removing a plugin is what a cautious policy wants to allow.
        self.assertTrue(policy.permits_effect(UnmergeSettingsEntry(*plugin, ENTRY)))


class APluginReceiptReadsBackAsWrittenTest(unittest.TestCase):
    def test_the_entry_survives_a_round_trip(self) -> None:
        receipt = PlacedArtifactReceipt(
            "company/plugin/superpowers",
            "/p/.opencode/aart-cli/plugin/company/superpowers",
            sha256_bytes(b"payload"),
            settings=(ArtifactSettingsEntry("opencode", "/p/opencode.json", PATH, ENTRY),),
        )

        self.assertEqual(
            Ok(receipt), placed_artifact_receipt_from_data(placed_artifact_receipt_to_data(receipt))
        )


class OpenCodeIsTheMeasuredPluginHostTest(unittest.TestCase):
    def test_project_and_user_scope_name_the_list_in_opencode_json(self) -> None:
        self.assertEqual(("opencode.json", "plugin"), _where(Scope.PROJECT))
        self.assertEqual((".config/opencode/opencode.json", "plugin"), _where(Scope.USER))

    def test_an_unmeasured_harness_has_no_plugin_target(self) -> None:
        for harness in ("claude", "codex", "tabnine"):
            with self.subTest(harness=harness), self.assertRaises(KeyError):
                plugin_target(harness, Scope.PROJECT)


def _where(scope: Scope) -> tuple[str, str]:
    target = plugin_target("opencode", scope)
    return target.settings, target.path


if __name__ == "__main__":
    unittest.main()
