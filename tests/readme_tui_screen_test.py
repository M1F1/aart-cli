"""The Add Registry screen the README shows is the one the build draws.

The README illustrates connecting a Registry with a terminal frame. A frame pasted into a page is
a screenshot in the only sense that matters -- it is right on the day it is taken and nothing
notices when it stops being right. Every other claim on that page is executed by a gate, and a
picture of the product is exactly the kind of claim that rots first, because changing a label is
not the sort of change anyone expects to break documentation.

So the block is not maintained by hand. This composes the same screen through the same
`compose_frame`/`render` the shell draws with, and compares. A wording change to the form, a new
field, a different key in the legend: the README stops matching and this says so, with a diff.
"""

from __future__ import annotations

import pathlib
import re
import unittest

from aart_cli.application.consumer_ui import ConsumerUiState
from aart_cli.application.consumer_views import ConsumerScreen, ConsumerSession
from aart_cli.tui_consumer import CanonicalScreenSource, _reload, compose_frame
from aart_cli.tui_layout import render
from tests.consumer_install_flow_shell_test import screens

_README = pathlib.Path(__file__).resolve().parent.parent / "README.md"
#: The one fenced `text` block on the page: the frame, rather than a shell line.
_FRAME_BLOCK = re.compile(r"```text\n(.*?)```", re.S)


def _drawn() -> str:
    """The Add Registry screen as the shell would draw it, entered from Registries."""

    source = CanonicalScreenSource(screens())
    state = ConsumerUiState(
        ConsumerSession(
            ConsumerScreen.REGISTRY_ADD,
            history=(ConsumerScreen.DASHBOARD, ConsumerScreen.REGISTRIES),
        )
    )
    return "\n".join(render(compose_frame(source, _reload(source, state, entering=True))))


class ReadmeShowsTheScreenTheBuildDrawsTest(unittest.TestCase):
    def test_the_readme_frame_is_the_frame_the_shell_composes(self) -> None:
        blocks = _FRAME_BLOCK.findall(_README.read_text(encoding="utf-8"))

        self.assertEqual(len(blocks), 1, "the README should illustrate exactly one screen")
        self.assertEqual(blocks[0].strip("\n"), _drawn().strip("\n"))

    def test_this_guard_is_not_vacuous(self) -> None:
        """A frame that composed to nothing would let the assertion above pass over an empty page."""

        drawn = _drawn()

        self.assertIn("Add Registry", drawn)
        self.assertIn("Registry URL", drawn)
        self.assertGreater(len(drawn.splitlines()), 10)
