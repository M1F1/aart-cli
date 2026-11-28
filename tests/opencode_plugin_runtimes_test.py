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
    RECORDER_ENVIRONMENT,
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

    // What opencode holds that the recorder must never be given.
    process.env.OPENCODE_PASSWORD = process.argv[3]
    process.env.ANTHROPIC_API_KEY = process.argv[3]
    process.env.https_proxy = "http://proxy.invalid:3128"

    // OpenCode 1.x: its servers come from `client.mcp.status()`.
    const client = { mcp: { status: async () => ({ data: { jira: { status: "connected" } } }) } }
    const hooks = await plugin.server({ client, directory: "/one" })
    const before = hooks["tool.execute.before"]
    await before({ tool: "skill", sessionID: "s-one" }, { args: { name: "review" } })
    await before({ tool: "jira_search", sessionID: "s-one" }, { args: { q: process.argv[3] } })
    await before({ tool: "read", sessionID: "s-one" }, { args: { filePath: "/etc/hosts" } })
    await before({ tool: "experimental_image_generate", sessionID: "s-one" }, { args: {} })
    await before({ tool: "notes_append", sessionID: "s-one" }, { args: {} })
    // Without a client to ask, no tool is taken for an MCP's.
    const bare = await plugin.server({ directory: "/bare" })
    await bare["tool.execute.before"]({ tool: "jira_search", sessionID: "s-bare" }, { args: {} })

    // OpenCode 2.
    const registered = []
    said.asked = 0
    const ctx = {
      location: { directory: "/two" },
      mcp: {
        list: async () => {
          said.asked += 1
          return { data: [{ name: "github" }, { name: "github.enterprise" }] }
        },
      },
      tool: { hook: async (name, callback) => { registered.push([name, callback]); return {} } },
    }
    said.returned = typeof (await plugin.setup(ctx))
    said.registered = registered.map(([name]) => name)
    const [, hook] = registered[0]
    // OpenCode 2 awaits what a hook returns, and a rejection fails the tool call.
    said.results = await Promise.all(
      [
        hook({ tool: "skill", sessionID: "s-two", input: { id: "review" } }),
        hook({ tool: "github_search_code", sessionID: "s-two", input: { q: process.argv[3] } }),
        hook({ tool: "github_enterprise_search", sessionID: "s-two", input: {} }),
        hook({ tool: "opencode_list_mcp_resources", sessionID: "s-two", input: {} }),
        hook({ tool: "bash", sessionID: "s-two", input: { command: "ls" } }),
        hook(undefined),
        hook({ tool: { toString() { throw new Error("no") } } }),
      ].map((value) => Promise.resolve(value).then((done) => typeof done, () => "rejected")),
    )

    // A context without the OpenCode 2 tool domain registers nothing and does not throw.
    await plugin.setup({ directory: "/one", tool: {} })
    await plugin.setup(undefined)
    said.after = registered.length

    // Every hook has handed over what it will before this process says it is done.
    await new Promise((resolve) => setTimeout(resolve, 200))
    console.log(JSON.stringify(said))
    """
)

# Stands in for the usage hook: appends what it was handed, one JSON document a line, and beside
# it the environment it was given and whether it runs in a session of its own (detached).
_KEEPER = textwrap.dedent(
    """
    import json, os, sys, time

    handed = sys.stdin.read().strip()
    if os.path.exists(sys.argv[2] + ".delay"):
        time.sleep(float(open(sys.argv[2] + ".delay").read()))
    with open(sys.argv[2], "a", encoding="utf-8") as kept:
        kept.write(handed + "\\n")
    with open(sys.argv[2] + ".env", "a", encoding="utf-8") as kept:
        kept.write(json.dumps({"env": sorted(os.environ), "own": os.getsid(0) == os.getpid()}))
        kept.write("\\n")
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

    def _environments(self, count: int) -> list[dict[str, object]]:
        self._handed(count)
        path = Path(f"{self.kept}.env")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and len(path.read_text().splitlines()) < count:
            time.sleep(0.05)
        return [json.loads(line) for line in path.read_text().splitlines()]

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
        self.assertEqual(self.said["results"], ["undefined"] * 7)

    def test_calls_made_together_ask_the_runtime_for_its_servers_once(self) -> None:
        # Each hook now waits for the answer, so three at once must not ask three times.
        self.assertEqual(self.said["asked"], 1)

    def test_each_runtime_hands_over_its_skill_and_mcp_calls_by_name_only(self) -> None:
        # B-277: a tool is an MCP's only when opencode has a server it fits, the longest such.
        self.assertEqual(
            self._handed(5),
            [
                {
                    "tool": "jira_search",
                    "server": "jira",
                    "directory": "/one",
                    "session": "s-one",
                    "runtime": 1,
                },
                {
                    "tool": "skill",
                    "skill": "review",
                    "directory": "/one",
                    "session": "s-one",
                    "runtime": 1,
                },
                {
                    "tool": "github_enterprise_search",
                    "server": "github.enterprise",
                    "directory": "/two",
                    "session": "s-two",
                    "runtime": 2,
                },
                {
                    "tool": "github_search_code",
                    "server": "github",
                    "directory": "/two",
                    "session": "s-two",
                    "runtime": 2,
                },
                {
                    "tool": "skill",
                    "skill": "review",
                    "directory": "/two",
                    "session": "s-two",
                    "runtime": 2,
                },
            ],
        )
        self.assertNotIn(_SECRET, self.kept.read_text())

    def test_the_recorder_runs_detached_with_nothing_opencode_holds(self) -> None:
        # B-277: let go of, so opencode's exit does not take it; given only what it needs.
        for environment in self._environments(5):
            with self.subTest(environment=environment):
                self.assertTrue(environment["own"])
                given = set(environment["env"])
                self.assertFalse({"OPENCODE_PASSWORD", "ANTHROPIC_API_KEY"} & given, sorted(given))
                self.assertIn("https_proxy", given)
                # Beside those kept, only what the OS or Python sets for any process.
                allowed = {*RECORDER_ENVIRONMENT, "__CF_USER_TEXT_ENCODING", "PWD", "SHLVL", "_"}
                extra = [
                    name
                    for name in given
                    if name.upper() not in allowed and not name.upper().startswith("LC_")
                ]
                self.assertEqual([], extra)


# OpenCode 2 ending the run right after a tool call: its process group goes, with every child the
# recorder did not let go of (B-277, measured on 2.3.2 with `opencode run`).
_EXITING = textwrap.dedent(
    """
    import { pathToFileURL } from "node:url"

    const plugin = (await import(pathToFileURL(process.argv[2]).href)).default
    const registered = []
    await plugin.setup({
      location: { directory: "/two" },
      mcp: { list: async () => ({ data: [{ name: "github" }] }) },
      tool: { hook: async (name, callback) => { registered.push(callback) } },
    })
    registered[0]({ tool: "skill", sessionID: "s", input: { id: "review" } })
    registered[0]({ tool: "github_search", sessionID: "s", input: {} })
    await new Promise((resolve) => setTimeout(resolve, 300))
    process.kill(-process.pid, "SIGKILL")
    """
)


@unittest.skipIf(_NODE is None or sys.platform == "win32", "node runs the plugin; POSIX groups")
class OpenCodeExitingTest(unittest.TestCase):
    def test_the_last_uses_are_recorded_after_opencode_and_its_group_are_gone(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            kept = root / "kept.jsonl"
            keeper = root / HOOK_SCRIPT
            keeper.parent.mkdir(parents=True)
            keeper.write_text(_KEEPER)
            Path(f"{kept}.delay").write_text("0.5")
            plugin = root / "aart-cli-usage.js"
            plugin.write_text(
                opencode_plugin(UsageHook("opencode", sys.executable, str(keeper), str(kept)))
            )
            driver = root / "exiting.mjs"
            driver.write_text(_EXITING)
            assert _NODE is not None
            subprocess.run(
                [_NODE, str(driver), str(plugin)],
                capture_output=True,
                timeout=60,
                check=False,
                start_new_session=True,
            )

            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                lines = kept.read_text().splitlines() if kept.exists() else []
                if len(lines) >= 2:
                    break
                time.sleep(0.05)

            self.assertEqual(
                sorted(json.loads(line)["tool"] for line in lines), ["github_search", "skill"]
            )


# opencode exiting as soon as the tool call its hook was awaited for returns, before the runtime
# has said which servers it has: the first MCP call of a run (B-277). `late` answers after
# 150 ms, `never` never does; the last argument is the runtime whose hook is called.
_QUICK = textwrap.dedent(
    """
    import { pathToFileURL } from "node:url"

    const plugin = (await import(pathToFileURL(process.argv[2]).href)).default
    // opencode's own server keeps it running; the plugin's timer must not.
    setInterval(() => {}, 1000)
    const answer = (value) =>
      process.argv[3] === "late"
        ? new Promise((resolve) => setTimeout(() => resolve(value), 150))
        : new Promise(() => {})
    const client = { mcp: { status: async () => answer({ data: { jira: {} } }) } }
    const hooks = await plugin.server({ client, directory: "/one" })
    const registered = []
    await plugin.setup({
      location: { directory: "/two" },
      mcp: { list: async () => answer({ data: [{ name: "github" }] }) },
      tool: { hook: async (name, callback) => { registered.push(callback) } },
    })
    const started = Date.now()
    if (process.argv[4] === "1") {
      await hooks["tool.execute.before"]({ tool: "jira_search", sessionID: "s" }, { args: {} })
    } else {
      await registered[0]({ tool: "github_search", sessionID: "s", input: {} })
    }
    console.log(JSON.stringify({ waited: Date.now() - started }))
    process.kill(-process.pid, "SIGKILL")
    """
)


@unittest.skipIf(_NODE is None or sys.platform == "win32", "node runs the plugin; POSIX groups")
class OpenCodeExitingRightAfterTheFirstCallTest(unittest.TestCase):
    def _run(self, answer: str, runtime: str) -> tuple[list[str], int]:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            kept = root / "kept.jsonl"
            keeper = root / HOOK_SCRIPT
            keeper.parent.mkdir(parents=True)
            keeper.write_text(_KEEPER)
            plugin = root / "aart-cli-usage.js"
            plugin.write_text(
                opencode_plugin(UsageHook("opencode", sys.executable, str(keeper), str(kept)))
            )
            driver = root / "quick.mjs"
            driver.write_text(_QUICK)
            assert _NODE is not None
            ran = subprocess.run(
                [_NODE, str(driver), str(plugin), answer, runtime],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                start_new_session=True,
            )
            waited = int(json.loads(ran.stdout.strip().splitlines()[-1])["waited"])
            deadline = time.monotonic() + (10 if answer == "late" else 2)
            lines: list[str] = []
            while time.monotonic() < deadline:
                lines = kept.read_text().splitlines() if kept.exists() else []
                if lines:
                    break
                time.sleep(0.05)
            return [json.loads(line)["tool"] for line in lines], waited

    def test_the_first_mcp_call_is_recorded_when_opencode_exits_right_after_it(self) -> None:
        for runtime, tool in (("1", "jira_search"), ("2", "github_search")):
            with self.subTest(runtime=runtime):
                self.assertEqual(self._run("late", runtime)[0], [tool])

    def test_a_runtime_that_never_names_its_servers_holds_a_tool_call_a_second_at_most(
        self,
    ) -> None:
        for runtime in ("1", "2"):
            with self.subTest(runtime=runtime):
                tools, waited = self._run("never", runtime)
                self.assertEqual(tools, [])
                self.assertLess(waited, 1500)


# What OpenCode 2's `ctx.app` might hold, one `setup` each, its skill named after the case; and
# OpenCode 1.x's path, which reads no version (D-536).
_VERSIONS = textwrap.dedent(
    """
    import { pathToFileURL } from "node:url"

    const plugin = (await import(pathToFileURL(process.argv[2]).href)).default
    const throwing = {}
    Object.defineProperty(throwing, "version", { get() { throw new Error("no") } })
    const cases = {
      "plain": { version: "2.3.2" },
      "beta": { version: "2.4.0-beta.1" },
      "none": undefined,
      "null": null,
      "number": { version: 232 },
      "function": { version: () => "2.3.2" },
      "empty": { version: "" },
      "latest": { version: "latest" },
      "prefixed": { version: "v2.3.2" },
      "path": { version: "/Users/someone/opencode-v2.3.2" },
      "appended": { version: "2.3.2; x" },
      "long": { version: "2.3.2-" + "a".repeat(200) },
      "throwing": throwing,
    }
    const said = { registered: 0, results: [] }
    for (const [name, app] of Object.entries(cases)) {
      const ctx = {
        location: { directory: "/two" },
        mcp: { list: async () => ({ data: [] }) },
        tool: { hook: async (_, callback) => { said.registered += 1; ctx.hook = callback } },
      }
      if (name !== "none") ctx.app = app
      await plugin.setup(ctx)
      said.results.push(typeof (await ctx.hook({ tool: "skill", sessionID: "s", input: { id: name } })))
    }
    const client = { mcp: { status: async () => ({ data: {} }) } }
    const hooks = await plugin.server({ client, directory: "/one", app: { version: "1.19.5" } })
    await hooks["tool.execute.before"]({ tool: "skill", sessionID: "s" }, { args: { name: "one" } })
    console.log(JSON.stringify(said))
    """
)


@unittest.skipIf(_NODE is None, "node runs the plugin")
class OpenCodeSVersionTest(unittest.TestCase):
    def test_only_a_version_of_the_pattern_read_from_ctx_app_is_handed_over(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            kept = root / "kept.jsonl"
            keeper = root / HOOK_SCRIPT
            keeper.parent.mkdir(parents=True)
            keeper.write_text(_KEEPER)
            plugin = root / "aart-cli-usage.js"
            plugin.write_text(
                opencode_plugin(UsageHook("opencode", sys.executable, str(keeper), str(kept)))
            )
            driver = root / "versions.mjs"
            driver.write_text(_VERSIONS)
            assert _NODE is not None
            ran = subprocess.run(
                [_NODE, str(driver), str(plugin)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(ran.returncode, 0, ran.stderr)
            said = json.loads(ran.stdout.strip().splitlines()[-1])
            deadline = time.monotonic() + 30
            lines: list[str] = []
            while time.monotonic() < deadline:
                lines = kept.read_text().splitlines() if kept.exists() else []
                if len(lines) >= 14:
                    break
                time.sleep(0.05)
            handed = {item["skill"]: item for item in map(json.loads, lines)}

        # Every case registered its hook and none of them threw into the tool call.
        self.assertEqual(said, {"registered": 13, "results": ["undefined"] * 13})
        self.assertEqual(len(handed), 14)
        versions = {name: item.get("harness_version") for name, item in handed.items()}
        self.assertEqual(
            {name: version for name, version in versions.items() if version is not None},
            {"plain": "2.3.2", "beta": "2.4.0-beta.1"},
        )
        self.assertNotIn("harness_version", handed["one"])
        self.assertEqual(handed["one"]["runtime"], 1)


if __name__ == "__main__":
    unittest.main()
