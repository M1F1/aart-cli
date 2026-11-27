"""Which OpenCode a project plugin is installed for, and where it goes for each (§171.3, D-532).

OpenCode 1.x loads a project plugin only from the `plugin` list of the project's `opencode.json`.
OpenCode 2 loads one from a directory of its own under `.opencode/plugins/`, by itself and from any
subdirectory, while a list entry is resolved from where it was started and is lost from a
subdirectory; and it loads a plugin named both ways twice (B-276). So one installation suits one of
them, chosen -- the build's default until a person says otherwise -- never detected.

What is held here: the choice and its default, and the loader OpenCode 2's directory holds -- the
entry module imported by a path relative to itself. The public command end to end is
`opencode2_project_plugin_e2e_test`; the build's default, `opencode_default_injection_test`.
"""

from __future__ import annotations

import unittest
import unittest.mock

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from aart_cli.application.consumer_views import (
    OPENCODE_ROW,
    SETTING_ROWS,
    ConsumerSettings,
    settings_from_data,
    settings_to_data,
)
from aart_cli.configuration.seed import baked_opencode_runtime
from aart_cli.domain.diagnostics import Severity
from aart_cli.domain.harness import Scope, plugin_directory
from aart_cli.domain.hooks import plugin_loader, plugin_loader_at
from aart_cli.domain.opencode_runtime import OPENCODE_RUNTIME_INVALID, parse_opencode_runtime
from aart_cli.domain.result import Err, Ok
from tests.plugin_installation_e2e_test import (
    ENTRY_MODULE,
)

#: mutmut runs these from another executor than unittest does.
_MUTATION = (HealthCheck.differing_executors,)

#: Where OpenCode 2 finds the fixture plugin: its installed name, under `.opencode/plugins/`.
LOADER = ".opencode/plugins/superpowers-company-project"
#: The module, as the loader imports it: out of `.opencode/plugins/<name>/`, into the tree.
IMPORTED = "../../aart-cli/plugin/company/superpowers/payload/.opencode/plugins/superpowers.js"


class TheChoiceTest(unittest.TestCase):
    def test_empty_is_opencode_1_and_each_runtime_is_itself(self) -> None:
        self.assertEqual(Ok(1), parse_opencode_runtime(""))
        self.assertEqual(Ok(1), parse_opencode_runtime("  "))
        self.assertEqual(Ok(1), parse_opencode_runtime("1"))
        self.assertEqual(Ok(2), parse_opencode_runtime(" 2 "))

    @settings(suppress_health_check=_MUTATION)
    @given(st.text(max_size=6))
    def test_anything_else_fails_the_release_rather_than_meaning_1(self, raw: str) -> None:
        if raw.strip() in {"", "1", "2"}:
            return
        parsed = parse_opencode_runtime(raw)
        self.assertIsInstance(parsed, Err)
        assert isinstance(parsed, Err)
        (diagnostic,) = parsed.diagnostics
        self.assertEqual(OPENCODE_RUNTIME_INVALID, diagnostic.code)
        self.assertIs(Severity.ERROR, diagnostic.severity)
        # The release log says what it was given, so the variable can be found and fixed.
        self.assertIn(repr(raw), diagnostic.message)

    def test_the_source_tree_bakes_opencode_1_and_a_bad_stamp_reads_as_it(self) -> None:
        self.assertEqual(1, baked_opencode_runtime())
        self.assertEqual(2, baked_opencode_runtime("2"))
        self.assertEqual(1, baked_opencode_runtime("two"))

    def test_until_somebody_chooses_the_build_decides(self) -> None:
        self.assertIsNone(ConsumerSettings().opencode_runtime)
        self.assertEqual(baked_opencode_runtime(), ConsumerSettings().opencode)
        self.assertNotIn("opencode_runtime", settings_to_data(ConsumerSettings()))

    def test_the_row_flips_it_and_the_flip_is_a_choice_kept_as_one(self) -> None:
        self.assertIn(OPENCODE_ROW, SETTING_ROWS)
        once = ConsumerSettings().toggled(OPENCODE_ROW)
        twice = once.toggled(OPENCODE_ROW)

        self.assertEqual(2, once.opencode)
        self.assertEqual(1, twice.opencode)
        # Flipped back, it is still somebody's choice: a later build default does not overrule it.
        self.assertEqual(1, twice.opencode_runtime)
        self.assertEqual(Ok(twice), settings_from_data(settings_to_data(twice)))
        self.assertEqual(
            {"opencode_runtime": 2},
            {
                key: value
                for key, value in settings_to_data(once).items()
                if settings_to_data(ConsumerSettings()).get(key) != value
            },
        )

    def test_a_stored_value_it_cannot_mean_is_refused(self) -> None:
        for stored in (3, 0, True, "2", 2.0, None):
            with self.subTest(stored=stored):
                data = {"opencode_runtime": stored}
                read = settings_from_data(data)
                if stored is None:
                    self.assertEqual(Ok(ConsumerSettings()), read)
                else:
                    self.assertIsInstance(read, Err)
        with self.assertRaises(ValueError):
            ConsumerSettings(opencode_runtime=3)
        with self.assertRaises(ValueError):
            ConsumerSettings(opencode_runtime=True)  # type: ignore[arg-type]


class TheLoaderTest(unittest.TestCase):
    def test_it_is_the_project_s_own_directory_and_no_other_scope_s(self) -> None:
        self.assertEqual(
            LOADER, plugin_directory("opencode", Scope.PROJECT, LOADER.rsplit("/")[-1])
        )
        with self.assertRaises(KeyError):
            plugin_directory("opencode", Scope.USER, "superpowers-company-user")
        with self.assertRaises(KeyError):
            plugin_directory("claude", Scope.PROJECT, "superpowers-company-project")
        with self.assertRaises(ValueError):
            plugin_directory("opencode", Scope.PROJECT, "../escape")

    def test_it_imports_the_module_from_itself_not_from_where_opencode_started(self) -> None:
        project = "/work/project"
        text = plugin_loader_at(f"{project}/{LOADER}", f"{project}/{ENTRY_MODULE}")

        self.assertIn(f'export * from "{IMPORTED}"\n', text)
        self.assertIn(f'import * as plugin from "{IMPORTED}"\n', text)
        self.assertNotIn(project, text)

    def test_it_is_exactly_the_loader_opencode_2_starts(self) -> None:
        # OpenCode 2 starts a plugin by its default export, so the default is the contract: the
        # module's own, or its first function when it has none (§171.3).
        self.assertEqual(
            "// Written by aart-cli: loads this plugin for OpenCode 2.\n"
            'export * from "../Tree/v1.2/XModule.mjs"\n'
            'import * as plugin from "../Tree/v1.2/XModule.mjs"\n'
            "export default plugin.default ??\n"
            '  Object.values(plugin).find((value) => typeof value === "function")\n',
            plugin_loader("../Tree/v1.2/XModule.mjs"),
        )

    def test_it_is_placed_and_loads_by_absolute_paths_only(self) -> None:
        for directory, module in (
            ("work/project/.opencode/plugins/x", "/work/project/module.js"),
            ("/work/project/.opencode/plugins/x", "work/project/module.js"),
        ):
            with self.subTest(directory=directory, module=module):
                with self.assertRaises(ValueError):
                    plugin_loader_at(directory, module)

    def test_a_module_it_could_not_import_is_refused(self) -> None:
        for module in (
            "./here.js",
            "tree/module.js",
            "/abs/module.js",
            "../tree/module.json",
            "../a//b.js",
            "../a/./b.js",
            "../a\nb.js",
            "../a\rb.js",
            "../a\\b.js",
        ):
            with self.subTest(module=module):
                with self.assertRaises(ValueError):
                    plugin_loader(module)


if __name__ == "__main__":
    unittest.main()
