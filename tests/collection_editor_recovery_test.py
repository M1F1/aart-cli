"""INV-283: a refused or abandoned Collection review comes back to the Collection it was about.

The owner pressed Continue from a directory that was not the Registry checkout. The refusal was
about "promotion", and the editor came back empty saying "Open a Collection from screen 51 first":
the review screen had replaced the editor's subject with the row Continue was on. Screen numbers
are the specification's, never the reader's, so no message names one.
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib
import re
import subprocess
import tempfile
import unittest

from aart_cli.application.consumer_ui import (
    COLLECTION_SAVE_ROW,
    ConsumerActionKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    key_event,
    reduce_consumer_ui,
)
from aart_cli.application.maintainer_promotion import RegistryBaselineMismatch
from aart_cli.application.maintainer_views import MaintainerScreen, collection_row
from aart_cli.configuration.model import ConfiguredSource
from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Err
from aart_cli.io.maintainer_promotion import _registry_baseline_mismatch, _workspace_refusal
from aart_cli.sources.model import SourceKind
from aart_cli.tui_consumer import CanonicalScreenSource, _reload, frame
from tests.collection_editor_search_test import _editor, _on, _press, _source

_PACKAGE = pathlib.Path(__file__).resolve().parents[1] / "aart_cli"
_SCREEN_NUMBER = re.compile(r"\b[Ss]creens? \d+[a-z]?\b")


def _continued():
    state = _press(_editor(), *"dev")
    state = _press(_on(state, "mcp/notes"), " ")
    state = _on(state, COLLECTION_SAVE_ROW)
    event = key_event("enter", state)
    assert event is not None
    reviewing, _commands = reduce_consumer_ui(state, event)
    return reviewing


class RefusedCollectionTest(unittest.TestCase):
    def test_a_refused_continue_returns_to_the_same_collection_with_its_draft(self) -> None:
        reviewing = _continued()
        self.assertIs(reviewing.session.screen, MaintainerScreen.REGISTRY_VALIDATION)

        refused, _commands = reduce_consumer_ui(
            reviewing,
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED, action=ConsumerActionKind.COLLECTION_DEFINE
            ),
        )
        notice = ("- aart-cli was started in /tmp/elsewhere",)
        source = CanonicalScreenSource(dataclasses.replace(_source()._screens, notice=notice))
        refused = _reload(source, refused)

        self.assertIs(refused.session.screen, MaintainerScreen.COLLECTION_EDITOR)
        self.assertEqual(refused.focus, collection_row("company", None))
        drawn = "\n".join(frame(source, refused))
        self.assertIn("Name: dev", drawn)
        self.assertIn("[x] mcp/notes", drawn)
        self.assertIn("aart-cli was started in /tmp/elsewhere", drawn)
        self.assertIsNone(_SCREEN_NUMBER.search(drawn), drawn)

    def test_back_from_the_review_returns_to_the_same_collection(self) -> None:
        reviewing = _continued()

        back = _reload(_source(), _press(reviewing, "escape"))

        self.assertIs(back.session.screen, MaintainerScreen.COLLECTION_EDITOR)
        self.assertIn("Name: dev", "\n".join(frame(_source(), back)))


def _strings(tree: ast.AST):
    """Every string literal that is not a bare statement: what the program can say to somebody.

    A string standing alone as a statement is a docstring, of a module, class, function or
    attribute, and is never shown.
    """

    unsaid = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in unsaid:
                yield node


class NoScreenNumbersTest(unittest.TestCase):
    def test_no_message_names_a_screen_by_its_number(self) -> None:
        found = [
            f"{path.relative_to(_PACKAGE.parent)}:{node.lineno}: {node.value!r}"
            for path in sorted(_PACKAGE.rglob("*.py"))
            for node in _strings(ast.parse(path.read_text(encoding="utf-8")))
            if _SCREEN_NUMBER.search(node.value)
        ]

        self.assertEqual(found, [])


def _git(root: pathlib.Path, *arguments: str) -> None:
    subprocess.run(("git", "-C", str(root), *arguments), check=True, capture_output=True, text=True)


class WrongWorkspaceTest(unittest.TestCase):
    def test_another_repository_is_refused_naming_it_and_the_registry(self) -> None:
        registry = ConfiguredSource(
            SourceAlias("company"),
            SourceKind.REGISTRY_GIT,
            "https://git.example/company/registry.git",
            "main",
            True,
        )
        with tempfile.TemporaryDirectory() as directory:
            elsewhere = pathlib.Path(directory).resolve() / "my-project"
            elsewhere.mkdir()
            _git(elsewhere, "init", "-q")
            _git(elsewhere, "remote", "add", "origin", "https://git.example/me/my-project.git")

            mismatch = _registry_baseline_mismatch(str(elsewhere), registry, "a" * 40)
            refusal = _workspace_refusal(str(elsewhere), registry, mismatch)

        self.assertIs(mismatch, RegistryBaselineMismatch.WRONG_WORKSPACE)
        assert isinstance(refusal, Err)
        (diagnostic,) = refusal.diagnostics
        said = " ".join((diagnostic.message, *diagnostic.remediation))
        self.assertIn(str(elsewhere), said)
        self.assertIn("Registry company", said)
        self.assertIn("https://git.example/company/registry.git", said)
        self.assertNotIn("promotion", said)

    def test_any_other_mismatch_is_left_to_the_baseline_check(self) -> None:
        registry = ConfiguredSource(
            SourceAlias("company"),
            SourceKind.REGISTRY_GIT,
            "https://git.example/r.git",
            "main",
            True,
        )
        for mismatch in RegistryBaselineMismatch:
            if mismatch is RegistryBaselineMismatch.WRONG_WORKSPACE:
                continue
            with self.subTest(mismatch=mismatch):
                self.assertIsNone(_workspace_refusal("/somewhere", registry, mismatch))


if __name__ == "__main__":
    unittest.main()
