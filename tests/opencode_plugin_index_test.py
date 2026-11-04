"""D-521: the `index.js` in a plugin's tree hands each opencode runtime the plugin it loads.

A plugin is registered by its tree's directory, because OpenCode 2 loads only directories, and
OpenCode 1.x resolves the same directory to its `index.js` (measured on 1.19.4 and 2.1.3). That
file is written by aart-cli and loads the payload's entry module. What each runtime then sees is
what these tests import into node:
- every export of the module, so OpenCode 1.x finds the plugin it always found;
- the module's own default, which OpenCode 2 takes, and for a module with none, its first function,
  which OpenCode 1.x already loads under its own name and does not load twice.

They need node and are skipped without it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from aart_cli.domain.hooks import PLUGIN_INDEX, PluginEntry, plugin_index

_NODE = shutil.which("node")
_MODULE = "payload/.opencode/plugins/probe.js"

_DRIVER = textwrap.dedent(
    """
    import { pathToFileURL } from "node:url"

    const module = await import(pathToFileURL(process.argv[2]).href)
    const original = await import(pathToFileURL(process.argv[3]).href)
    const same = Object.fromEntries(
      Object.keys(module).map((name) => [name, module[name] === (original[name] ?? null)]),
    )
    const first = Object.values(original).find((value) => typeof value === "function")
    console.log(JSON.stringify({
      exports: Object.keys(module).sort(),
      same,
      defaultIsFirstFunction: module.default !== undefined && module.default === first,
      defaultType: typeof module.default,
    }))
    """
)

_DUAL = 'export default { id: "probe", server: async () => ({}), setup: async () => {} }\n'
_LEGACY = (
    "export const config = { name: 'probe' }\n"
    "export const Probe = async () => ({})\n"
    "export const Other = async () => ({})\n"
)
_FUNCTION_DEFAULT = "export const Plugin = async () => ({})\nexport default Plugin\n"


@unittest.skipIf(_NODE is None, "node imports the index")
class ThePluginIndexTest(unittest.TestCase):
    def _seen(self, module: str) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as raw:
            tree = Path(raw) / "tree"
            (tree / _MODULE).parent.mkdir(parents=True)
            (tree / _MODULE).write_text(module)
            (tree / "package.json").write_text('{"type": "module"}\n')
            index = tree / PLUGIN_INDEX
            index.write_text(plugin_index(PluginEntry("./tree", _MODULE)))
            driver = Path(raw) / "driver.mjs"
            driver.write_text(_DRIVER)
            assert _NODE is not None
            ran = subprocess.run(
                [_NODE, str(driver), str(index), str(tree / _MODULE)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        self.assertEqual(ran.returncode, 0, ran.stderr)
        return json.loads(ran.stdout.strip().splitlines()[-1])

    def test_a_definition_for_both_runtimes_is_passed_through_as_it_is(self) -> None:
        seen = self._seen(_DUAL)

        self.assertEqual(["default"], seen["exports"])
        self.assertEqual({"default": True}, seen["same"])

    def test_a_1x_plugin_keeps_its_exports_and_its_first_function_becomes_the_default(
        self,
    ) -> None:
        seen = self._seen(_LEGACY)

        self.assertEqual(["Other", "Probe", "config", "default"], seen["exports"])
        self.assertEqual(
            {"Other": True, "Probe": True, "config": True},
            {name: same for name, same in seen["same"].items() if name != "default"},
        )
        self.assertTrue(seen["defaultIsFirstFunction"])

    def test_a_default_function_stays_the_default(self) -> None:
        seen = self._seen(_FUNCTION_DEFAULT)

        self.assertEqual(["Plugin", "default"], seen["exports"])
        self.assertEqual({"Plugin": True, "default": True}, seen["same"])


if __name__ == "__main__":
    unittest.main()
