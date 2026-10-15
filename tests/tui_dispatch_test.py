"""The shell routes a command to the same function the flag-mode CLI does, without reading `cli`.

`tui._dispatch` used to prefer `cli.DISPATCH`, which made `tui` import the module that launches
it (B-186). It now imports `commands.<name>` and calls `run`, so the claim worth holding is that
this is the very function `DISPATCH` would have called for every command.
"""

from __future__ import annotations

import importlib
import unittest
from unittest import mock

from aart_cli import cli, tui
from aart_cli.model import Request


class TheShellDispatchesLikeTheCliTest(unittest.TestCase):
    def test_every_cli_command_is_its_command_module_run(self) -> None:
        for name, handler in cli.DISPATCH.items():
            module = importlib.import_module(f"aart_cli.commands.{name}")
            original = module.run
            with (
                self.subTest(command=name),
                mock.patch.object(module, "run", return_value=7) as run,
            ):
                request = Request(command=name)

                self.assertEqual(7, tui._dispatch(request))
                # `DISPATCH` holds either the function itself or a shim that imports and calls it.
                if handler is not original:
                    self.assertEqual(7, handler(request))
                    self.assertEqual(2, run.call_count)
                else:
                    self.assertEqual(1, run.call_count)


if __name__ == "__main__":
    unittest.main()
