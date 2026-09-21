from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from aart_cli.application.mcp_smoke import SmokeDeclaration, SmokeOutcome, evaluate_tool_call
from aart_cli.domain.result import Err, Ok
from aart_cli.io.mcp_smoke import execute_stdio_smoke
from aart_cli.protocol.json import JsonObject

SERVER = r"""#!/usr/bin/env python3
import json, sys
for line in sys.stdin:
    message = json.loads(line)
    if message.get("method") == "initialize":
        print(json.dumps({"jsonrpc":"2.0","id":message["id"],"result":{"protocolVersion":"2025-11-25","capabilities":{"tools":{}},"serverInfo":{"name":"fixture","version":"1"}}}), flush=True)
    elif message.get("method") == "tools/list":
        print(json.dumps({"jsonrpc":"2.0","id":message["id"],"result":{"tools":[{"name":"read_identity","inputSchema":{"type":"object","properties":{},"additionalProperties":False}}]}}), flush=True)
    elif message.get("method") == "tools/call":
        assert message["params"] == {"name":"read_identity","arguments":{}}
        print(json.dumps({"jsonrpc":"2.0","id":message["id"],"result":{"content":[{"type":"text","text":"Ada"}]}}), flush=True)
        break
"""


class McpSmokeStdioTest(unittest.TestCase):
    def test_the_installed_launcher_receives_only_the_declared_call(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            launcher = root / "launch"
            launcher.write_text(textwrap.dedent(SERVER), encoding="utf-8")
            launcher.chmod(0o700)
            declaration = SmokeDeclaration("read_identity", JsonObject(()), 15)

            run = execute_stdio_smoke(str(launcher), declaration, cwd=str(root), harness="claude")

            assert isinstance(run, Ok), getattr(run, "diagnostics", ())
            evaluated = evaluate_tool_call(declaration, run.value.tools, run.value.result)
            self.assertEqual(evaluated.protocol.outcome, SmokeOutcome.PASS)
            # This declaration makes no service claim, so a protocol pass leaves nothing asked
            # and nothing owed -- the distinction INV-250 exists to keep.
            self.assertEqual(evaluated.service.outcome, SmokeOutcome.NOT_CONFIGURED)

    def test_a_declared_service_read_reaches_PASS_against_a_real_server(self) -> None:
        """B-164 end to end: a real launcher, a real call, and a service stage that can pass.

        This is the claim that had no path through the product before. The same run with the
        expectation removed is the test above, and it does not reach PASS -- so what carries the
        stage is the declared evidence rather than the call having completed.
        """

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            launcher = root / "launch"
            launcher.write_text(textwrap.dedent(SERVER), encoding="utf-8")
            launcher.chmod(0o700)
            declaration = SmokeDeclaration(
                "read_identity",
                JsonObject(()),
                15,
                JsonObject((("text_contains", "Ada"),)),
                True,
            )

            run = execute_stdio_smoke(str(launcher), declaration, cwd=str(root), harness="claude")

            assert isinstance(run, Ok), getattr(run, "diagnostics", ())
            evaluated = evaluate_tool_call(declaration, run.value.tools, run.value.result)
            self.assertEqual(evaluated.protocol.outcome, SmokeOutcome.PASS)
            self.assertEqual(evaluated.expectation.outcome, SmokeOutcome.PASS)
            self.assertEqual(evaluated.service.outcome, SmokeOutcome.PASS)

    def test_timeout_is_a_visible_failure_and_the_process_is_terminated(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            launcher = root / "launch"
            launcher.write_text(
                "#!/usr/bin/env python3\nimport time\ntime.sleep(5)\n", encoding="utf-8"
            )
            launcher.chmod(0o700)

            run = execute_stdio_smoke(
                str(launcher),
                SmokeDeclaration("read", JsonObject(()), 1),
                cwd=str(root),
                harness="claude",
            )

            self.assertIsInstance(run, Err)
            self.assertIn("timeout", run.diagnostics[0].message)

    def test_no_shell_interprets_the_launcher_path(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            marker = root / "must-not-exist"
            run = execute_stdio_smoke(
                f"{root}/missing;touch {marker}",
                SmokeDeclaration("read", JsonObject(()), 1),
                cwd=str(root),
                harness="claude",
            )
            self.assertIsInstance(run, Err)
            self.assertFalse(marker.exists())

    def test_invalid_arguments_are_refused_before_tools_call_reaches_the_server(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            marker = root / "called"
            launcher = root / "launch"
            launcher.write_text(
                "#!/usr/bin/env python3\n"
                "import json, pathlib, sys\n"
                f"marker = pathlib.Path({str(marker)!r})\n"
                "for line in sys.stdin:\n"
                " message=json.loads(line); method=message.get('method')\n"
                " if method=='initialize': print(json.dumps({'jsonrpc':'2.0','id':1,'result':{'protocolVersion':'2025-11-25'}}), flush=True)\n"
                " elif method=='tools/list': print(json.dumps({'jsonrpc':'2.0','id':2,'result':{'tools':[{'name':'read','inputSchema':{'type':'object','properties':{'tenant':{'type':'string'}},'required':['tenant']}}]}}), flush=True)\n"
                " elif method=='tools/call': marker.write_text('called'); break\n",
                encoding="utf-8",
            )
            launcher.chmod(0o700)
            run = execute_stdio_smoke(
                str(launcher),
                # Generous on purpose. What this test claims is that the schema refusal happens
                # *before* any call, which does not depend on the budget being small -- and a tight
                # one made it fail under the full suite's load, reporting a timeout instead of the
                # refusal. The two tests above own the timeout claim and keep their 1 second.
                SmokeDeclaration("read", JsonObject(()), 30),
                cwd=str(root),
                harness="claude",
            )
            self.assertIsInstance(run, Err)
            self.assertIn("before invocation", run.diagnostics[0].message)
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()


class McpSmokeLauncherContractTest(unittest.TestCase):
    """The launcher is started the way a harness registration starts it, and is heard when it dies.

    `SERVER` above is a Python fixture that ignores its argv, so every test using it passes whether
    the harness name is handed over or not. A generated launcher does not ignore it: one carrying
    configuration opens with `AART_CLI_HARNESS="${1-}"` and refuses anything that is not a slug,
    because the harness is how it finds the configuration file it must read. This route started it
    with no arguments at all, so every such installation refused, wrote the reason to a stderr the
    route sent to `DEVNULL`, and was reported as a process that closed mid-exchange (B-172).
    """

    def _harness_aware_launcher(self, root: Path, *, witness: Path) -> Path:
        """A launcher shaped like a generated one: it refuses without a harness, and records it."""

        server = root / "server.py"
        server.write_text(textwrap.dedent(SERVER), encoding="utf-8")
        launcher = root / "launch.sh"
        launcher.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            'AART_CLI_HARNESS="${1-}"\n'
            'case "$AART_CLI_HARNESS" in\n'
            "  ''|*[!a-z0-9-]*)\n"
            "    printf 'aart: fixture was started without the harness it belongs to; "
            "repair the installation\\n' >&2\n"
            "    exit 76\n"
            "    ;;\n"
            "esac\n"
            f"printf '%s' \"$AART_CLI_HARNESS\" > {str(witness)!r}\n"
            f"exec {sys.executable!r} {str(server)!r}\n",
            encoding="utf-8",
        )
        launcher.chmod(0o700)
        return launcher

    def test_the_launcher_is_started_with_the_harness_it_belongs_to(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            witness = root / "started-with"
            launcher = self._harness_aware_launcher(root, witness=witness)
            declaration = SmokeDeclaration("read_identity", JsonObject(()), 15)

            run = execute_stdio_smoke(str(launcher), declaration, cwd=str(root), harness="tabnine")

            assert isinstance(run, Ok), getattr(run, "diagnostics", ())
            # The exact slug, not merely something: the launcher composes a path from it.
            self.assertEqual(witness.read_text(encoding="utf-8"), "tabnine")

    def test_what_the_launcher_said_on_stderr_reaches_the_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            launcher = root / "launch.sh"
            launcher.write_text(
                "#!/bin/sh\nprintf 'aart: repair the installation\\n' >&2\nexit 76\n",
                encoding="utf-8",
            )
            launcher.chmod(0o700)

            run = execute_stdio_smoke(
                str(launcher),
                SmokeDeclaration("read_identity", JsonObject(()), 15),
                cwd=str(root),
                harness="tabnine",
            )

            assert isinstance(run, Err)
            message = run.diagnostics[0].message
            # Both halves: what the route observed, and the sentence that explains it.
            self.assertIn("closed before the protocol exchange completed", message)
            self.assertIn("aart: repair the installation", message)
