from __future__ import annotations

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

            run = execute_stdio_smoke(str(launcher), declaration, cwd=str(root))

            assert isinstance(run, Ok), getattr(run, "diagnostics", ())
            evaluated = evaluate_tool_call(declaration, run.value.tools, run.value.result)
            self.assertEqual(evaluated.protocol.outcome, SmokeOutcome.PASS)
            self.assertEqual(evaluated.service.outcome, SmokeOutcome.NOT_VERIFIED)

    def test_timeout_is_a_visible_failure_and_the_process_is_terminated(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            launcher = root / "launch"
            launcher.write_text(
                "#!/usr/bin/env python3\nimport time\ntime.sleep(5)\n", encoding="utf-8"
            )
            launcher.chmod(0o700)

            run = execute_stdio_smoke(
                str(launcher), SmokeDeclaration("read", JsonObject(()), 1), cwd=str(root)
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
            )
            self.assertIsInstance(run, Err)
            self.assertIn("before invocation", run.diagnostics[0].message)
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
