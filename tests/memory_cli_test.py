"""CLI/TUI surface for the `memory` artifact type.

Pure wiring (mirrors cli_test.py): the marketplace handler is stubbed via ``cli.DISPATCH`` so
we assert only what the parser accepts and that the TUI's display order knows the type. No
command logic runs.

Run: ``python -m unittest discover -s tests -p "memory_cli_test.py" -v``
"""

import contextlib
import io
import unittest
from unittest.mock import patch

from aart_cli import cli, cli_parser


def _dispatch(argv, *, command, code=0):
    """Run ``cli.main(argv)`` with ``command``'s handler stubbed; return (rc, captured Request)."""
    calls = []

    def run(request):
        calls.append(request)
        return code

    with patch.dict(cli.DISPATCH, {command: run}):
        rc = cli.main(argv)
    return rc, (calls[0] if calls else None)


class TestPlacementFlagsAreGone(unittest.TestCase):
    def test_install_offers_neither_a_memory_mode_nor_a_placement_mode(self):
        # A Registry installation copies, and a memory is one managed block that keeps the
        # content around it, so neither flag has anything left to choose (CP-32, D-444).
        for flag, value in (("--memory-mode", "append"), ("--mode", "symlink")):
            with self.subTest(flag=flag), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    cli.build_parser().parse_args(
                        [
                            "consume",
                            "install",
                            "team/memory/house",
                            "--profile",
                            "claude",
                            flag,
                            value,
                        ]
                    )
                self.assertEqual(ctx.exception.code, 2)


class TestTypeFilterMemory(unittest.TestCase):
    def test_memory_in_cli_type_choices(self):
        self.assertIn("memory", cli_parser._ARTIFACT_TYPES)


class TestTuiKnowsMemory(unittest.TestCase):
    def test_the_browsable_kinds_include_memory(self):
        """Retargeted from the retired wizard's `tui._TYPE_ORDER`.

        The claim is unchanged -- a Memory is a first-class artifact kind an interface offers, not
        a CLI-only one -- but the set that decides it now lives with the marketplace projection.
        """

        from aart_cli.tui_marketplace import _KINDS

        self.assertIn("memory", _KINDS)


if __name__ == "__main__":
    unittest.main()
