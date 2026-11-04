"""D-520: the opencode usage plugin is loaded by both of opencode's plugin runtimes.

OpenCode 1.x (from 1.18.29) takes a module whose default export is `{ id?, server }` and calls
`server(ctx)` for its hooks; OpenCode 2 takes `{ id, setup }` and calls `setup(ctx)`, where the
plugin registers `ctx.tool.hook("execute.before", ...)`. Builds on the OpenCode 2 runtime refuse a
module with no such default export ("Plugin must export a default definition with an id and an
effect or setup function").

These tests import the plugin aart-cli writes into node and drive it the way each runtime does,
with the usage hook replaced by a script that keeps what it is handed. They need node and are
skipped without it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

from aart_cli.application.usage_recording import (
    HOOK_SCRIPT,
    OPENCODE_PLUGIN_MARK,
    UsageHook,
    opencode_plugin,
)

_NODE = shutil.which("node")
_SECRET = "query-text-never-handed-over"

# What each runtime does with the module, and what the module looks like to it.
_DRIVER = textwrap.dedent(
    """
    import { pathToFileURL } from "node:url"

    const module = await import(pathToFileURL(process.argv[2]).href)
    const plugin = module.default
    const said = { exports: Object.keys(module).sort(), id: plugin?.id }
    said.server = typeof plugin?.server
    said.setup = typeof plugin?.setup

    // OpenCode 1.x.
    const hooks = await plugin.server({ directory: "/one" })
    const before = hooks["tool.execute.before"]
    await before({ tool: "skill", sessionID: "s-one" }, { args: { name: "review" } })
    await before({ tool: "jira_search", sessionID: "s-one" }, { args: { q: process.argv[3] } })
    await before({ tool: "read", sessionID: "s-one" }, { args: { filePath: "/etc/hosts" } })

    // OpenCode 2.
    const registered = []
    const ctx = {
      location: { directory: "/two" },
      tool: { hook: async (name, callback) => { registered.push([name, callback]); return {} } },
    }
    said.returned = typeof (await plugin.setup(ctx))
    said.registered = registered.map(([name]) => name)
    const [, hook] = registered[0]
    said.results = [
      hook({ tool: "skill", sessionID: "s-two", input: { id: "review" } }),
      hook({ tool: "github_search_code", sessionID: "s-two", input: { q: process.argv[3] } }),
      hook({ tool: "bash", sessionID: "s-two", input: { command: "ls" } }),
      hook(undefined),
      hook({ tool: { toString() { throw new Error("no") } } }),
    ].map((value) => typeof value)

    // A context without the OpenCode 2 tool domain registers nothing and does not throw.
    await plugin.setup({ directory: "/one", tool: {} })
    await plugin.setup(undefined)
    said.after = registered.length

    console.log(JSON.stringify(said))
    """
)

# Stands in for the usage hook: appends what it was handed, one JSON document a line.
_KEEPER = textwrap.dedent(
    """
    import sys

    with open(sys.argv[2], "a", encoding="utf-8") as kept:
        kept.write(sys.stdin.read().strip() + "\\n")
    """
)


@unittest.skipIf(_NODE is None, "node runs the plugin")
class ThePluginInBothRuntimesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)
        self.kept = self.root / "kept.jsonl"
        keeper = self.root / HOOK_SCRIPT
        keeper.parent.mkdir(parents=True)
        keeper.write_text(_KEEPER)
        hook = UsageHook("opencode", sys.executable, str(keeper), str(self.kept))
        self.plugin = self.root / "aart-cli-usage.js"
        self.plugin.write_text(opencode_plugin(hook))
        driver = self.root / "driver.mjs"
        driver.write_text(_DRIVER)
        assert _NODE is not None
        ran = subprocess.run(
            [_NODE, str(driver), str(self.plugin), _SECRET],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(ran.returncode, 0, ran.stderr)
        self.said = json.loads(ran.stdout.strip().splitlines()[-1])

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def _handed(self, count: int) -> list[dict[str, object]]:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            lines = self.kept.read_text().splitlines() if self.kept.exists() else []
            if len(lines) >= count:
                break
            time.sleep(0.05)
        return sorted(
            (json.loads(line) for line in lines),
            key=lambda item: (str(item.get("directory")), str(item.get("tool"))),
        )

    def test_its_one_export_is_a_definition_both_runtimes_load(self) -> None:
        self.assertTrue(self.plugin.read_text().startswith(OPENCODE_PLUGIN_MARK))
        self.assertEqual(self.said["exports"], ["default"])
        self.assertEqual(self.said["id"], "aart-cli-usage")
        self.assertEqual((self.said["server"], self.said["setup"]), ("function", "function"))

    def test_opencode_2_gets_one_tool_hook_and_no_cleanup_it_did_not_ask_for(self) -> None:
        self.assertEqual(self.said["registered"], ["execute.before"])
        self.assertEqual(self.said["returned"], "undefined")
        self.assertEqual(self.said["after"], 1)

    def test_a_hook_never_throws_into_opencode_2_s_tool_call(self) -> None:
        self.assertEqual(self.said["results"], ["undefined"] * 5)

    def test_each_runtime_hands_over_its_skill_and_mcp_calls_by_name_only(self) -> None:
        self.assertEqual(
            self._handed(4),
            [
                {"tool": "jira_search", "directory": "/one", "session": "s-one"},
                {"tool": "skill", "skill": "review", "directory": "/one", "session": "s-one"},
                {"tool": "github_search_code", "directory": "/two", "session": "s-two"},
                {"tool": "skill", "skill": "review", "directory": "/two", "session": "s-two"},
            ],
        )
        self.assertNotIn(_SECRET, self.kept.read_text())


if __name__ == "__main__":
    unittest.main()
