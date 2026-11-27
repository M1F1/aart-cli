"""A real OpenCode 2 loads the project plugin aart-cli installed for it, from a subdirectory (D-532).

Local evidence only, like every live harness test here: it runs where `opencode2` is installed and
skips everywhere else, CI included. It is the claim the loader exists for -- that OpenCode 2 finds
`.opencode/plugins/<name>/index.js` by itself and that its relative import reaches the module in the
private tree -- measured against the program rather than against what we believe of it.

`opencode2 run --standalone` against a stub model in this process, because `debug config` loads
plugins in the background and may print before they have run (B-278). The plugin writes a mark when
it is imported and when OpenCode 2 starts it, into a file this test owns.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from aart_cli import cli
from tests.configured_install_command_e2e_test import _Environment
from tests.plugin_installation_e2e_test import COORDINATE, MANIFEST

OPENCODE2 = shutil.which("opencode2")


def _module(marks: pathlib.Path) -> str:
    """A plugin written for OpenCode 2: a default definition with an `id` and a `setup`.

    OpenCode 2 (beta 19271) starts nothing else, from `.opencode/plugins/` or from the `plugin`
    list alike: a module exporting only an OpenCode 1.x function is imported and then refused,
    "Plugin must export a default definition with an id and an effect or setup function" (D-532).
    So whether a plugin runs on OpenCode 2 is its author's to make true; where it is put is ours.
    """

    path = json.dumps(str(marks))
    return (
        'import fs from "node:fs"\n'
        f'fs.appendFileSync({path}, "imported\\n")\n'
        "export default {\n"
        '  id: "superpowers",\n'
        "  setup: async () => {\n"
        f'    fs.appendFileSync({path}, "started\\n")\n'
        "    return {}\n"
        "  },\n"
        "}\n"
    )


class _Model(BaseHTTPRequestHandler):
    """An OpenAI-compatible model that answers every turn with one streamed `ok`."""

    def log_message(self, *_: object) -> None:
        return

    def do_GET(self) -> None:
        body = json.dumps({"object": "list", "data": [{"id": "m", "object": "model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for delta, finish in (({"role": "assistant", "content": "ok"}, None), ({}, "stop")):
            chunk = {
                "id": "c",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "m",
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


@unittest.skipIf(OPENCODE2 is None, "OpenCode 2 is not installed here (`opencode2`)")
class OpenCode2LoadsTheProjectPluginTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name).resolve()
        self.marks = self.root / "marks"
        self.env = _Environment(self.root)
        self.env.publish(
            (
                ("superpowers/aart-cli.json", json.dumps(MANIFEST)),
                ("superpowers/.opencode/plugins/superpowers.js", _module(self.marks)),
                ("superpowers/skills/brainstorming/SKILL.md", "---\nname: brainstorming\n---\n"),
                ("superpowers/skills/writing-plans/SKILL.md", "---\nname: writing-plans\n---\n"),
            )
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Model)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.port = server.server_address[1]

    def _choose_opencode_2(self) -> None:
        output = io.StringIO()
        with (
            mock.patch.dict(os.environ, self.env.xdg, clear=False),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(0, cli.main(["consume", "opencode", "2", "--json"]), output.getvalue())

    def _run_opencode_2(
        self, cwd: pathlib.Path, *, as_a_launcher: bool = False
    ) -> subprocess.CompletedProcess[str]:
        config: dict[str, object] = {
            "$schema": "https://opencode.ai/config.json",
            "provider": {
                "fake": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "Fake",
                    "options": {"baseURL": f"http://127.0.0.1:{self.port}/v1", "apiKey": "x"},
                    "models": {"m": {"name": "m"}},
                }
            },
            "model": "fake/m",
        }
        # Nothing of the person running it: no `OPENCODE_*`, no `XDG_*`, a home of its own.
        environment = {
            "HOME": str(self.env.home),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "TERM": "dumb",
            "TMPDIR": str(self.root),
            "OPENCODE_DB": str(self.root / "opencode.db"),
        }
        if as_a_launcher:
            # What a launcher does, as measured (B-276): the project's own configuration off, and
            # its plugins handed over instead -- a project entry's path as written, which OpenCode 2
            # then resolves from where it was started, and a plugin directory as an absolute path.
            environment["OPENCODE_CONFIG_PROJECT_DISABLE"] = "true"
            settings = self.env.project / "opencode.json"
            entries = json.loads(settings.read_text())["plugin"] if settings.exists() else []
            plugins = self.env.project / ".opencode" / "plugins"
            directories = (
                sorted(str(path) for path in plugins.iterdir()) if plugins.is_dir() else []
            )
            config["plugin"] = [*entries, *directories]
        environment["OPENCODE_CONFIG_CONTENT"] = json.dumps(config)
        assert OPENCODE2 is not None
        return subprocess.run(
            (OPENCODE2, "run", "--standalone", "--model", "fake/m", "go"),
            cwd=cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=240,
        )

    def _installed_from_a_subdirectory(self) -> pathlib.Path:
        self._choose_opencode_2()
        code, payload = self.env.run(
            "consume", "install", COORDINATE, "--profile", "opencode", "--yes"
        )
        self.assertEqual(0, code, payload)
        subdirectory = self.env.project / "src" / "deep"
        subdirectory.mkdir(parents=True)
        return subdirectory

    def _assert_started_once(self, completed: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(0, completed.returncode, completed.stderr[-2000:])
        marks = self.marks.read_text(encoding="utf-8").split() if self.marks.exists() else []
        # Once each: a plugin OpenCode 2 also found in `opencode.json` would be loaded twice.
        self.assertEqual(["imported", "started"], marks, completed.stderr[-2000:])

    def test_it_is_imported_and_started_from_a_subdirectory(self) -> None:
        subdirectory = self._installed_from_a_subdirectory()

        self._assert_started_once(self._run_opencode_2(subdirectory))

    def test_it_is_started_from_a_subdirectory_as_a_launcher_starts_opencode_2(self) -> None:
        subdirectory = self._installed_from_a_subdirectory()

        self._assert_started_once(self._run_opencode_2(subdirectory, as_a_launcher=True))


if __name__ == "__main__":
    unittest.main()
