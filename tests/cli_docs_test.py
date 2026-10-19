"""§177, INV-276: the command reference is the parser, read when the CLI runs (#47).

`aart-cli docs` walks `build_parser()` each time it runs, so nothing is committed and nothing goes
stale: a command added to the parser is in the reference without anyone touching a document.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli import __version__, cli
from aart_cli.cli_parser import build_parser


def _nodes(parser: argparse.ArgumentParser, path: tuple[str, ...] = ()):
    """Every command and group, found independently of the module under test."""
    groups = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    yield path, parser, bool(groups)
    for group in groups:
        for name, child in group.choices.items():
            yield from _nodes(child, (*path, name))


NODES = tuple(_nodes(build_parser()))
LEAVES = tuple((path, parser) for path, parser, is_group in NODES if not is_group)


def _run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(["docs", *argv])
    return code, out.getvalue(), err.getvalue()


class EveryLeafIsDocumentedTest(unittest.TestCase):
    def test_the_parser_has_leaves_to_walk(self) -> None:
        self.assertGreater(len(LEAVES), 40)

    def test_every_command_and_group_carries_a_description(self) -> None:
        for path, node, _ in NODES:
            with self.subTest(command=" ".join(path) or "aart-cli"):
                self.assertTrue((node.description or "").strip(), "no description=")

    def test_every_argument_and_option_says_what_it_is(self) -> None:
        for path, leaf in LEAVES:
            for action in leaf._actions:
                with self.subTest(command=" ".join(path), argument=action.dest):
                    self.assertTrue((action.help or "").strip(), "no help=")


class DocsJsonTest(unittest.TestCase):
    def test_json_lists_every_leaf_the_parser_has_and_nothing_else(self) -> None:
        code, out, _ = _run("--json")

        self.assertEqual(code, 0)
        document = json.loads(out)
        self.assertEqual(document["prog"], "aart-cli")
        self.assertEqual(document["version"], __version__)
        self.assertEqual(
            [entry["path"] for entry in document["commands"]],
            [" ".join(path) for path, _ in LEAVES],
        )

    def test_each_entry_carries_what_the_parser_says(self) -> None:
        _, out, _ = _run("--json")
        entries = {entry["path"]: entry for entry in json.loads(out)["commands"]}

        for path, leaf in LEAVES:
            entry = entries[" ".join(path)]
            with self.subTest(command=entry["path"]):
                self.assertEqual(entry["description"], leaf.description)
                self.assertEqual(entry["usage"], leaf.format_usage().strip())
                flags = {flag for argument in entry["arguments"] for flag in argument["flags"]}
                for action in leaf._actions:
                    if isinstance(action, argparse._HelpAction):
                        self.assertFalse(set(action.option_strings) & flags)
                    else:
                        self.assertTrue(
                            set(action.option_strings) <= flags
                            or any(a["name"] == action.dest for a in entry["arguments"])
                        )

    def test_a_default_and_its_choices_are_reported(self) -> None:
        _, out, _ = _run("maintain", "registry", "test", "--json")
        (entry,) = json.loads(out)["commands"]
        (compatibility,) = [a for a in entry["arguments"] if "--compatibility" in a["flags"]]

        self.assertEqual(compatibility["default"], "all")
        self.assertEqual(compatibility["choices"], ["minimum", "latest", "all"])
        self.assertFalse(compatibility["required"])

    def test_a_group_path_lists_the_leaves_under_it(self) -> None:
        _, out, _ = _run("consume", "receipt", "--json")

        self.assertEqual(
            [entry["path"] for entry in json.loads(out)["commands"]],
            ["consume receipt show", "consume receipt verify", "consume receipt undo"],
        )


class DocsTextTest(unittest.TestCase):
    def test_no_arguments_prints_the_tree_with_each_commands_help(self) -> None:
        code, out, _ = _run()

        self.assertEqual(code, 0)
        for path, _leaf in LEAVES:
            with self.subTest(command=" ".join(path)):
                self.assertIn(f"aart-cli {' '.join(path)}", out)
        self.assertIn("aart-cli docs COMMAND", out)

    def test_a_command_prints_its_description_usage_and_options(self) -> None:
        code, out, _ = _run("maintain", "registry", "push")

        self.assertEqual(code, 0)
        self.assertIn("usage: aart-cli maintain registry push", out)
        self.assertIn("only a merge makes reviewed bytes the registry", out)
        self.assertIn("--branch NAME", out)

    def test_an_unknown_command_is_a_usage_error_that_names_it(self) -> None:
        code, out, err = _run("consume", "nonsense")

        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("consume nonsense", err)
        self.assertIn("aart-cli docs", err)


class DocsPropertyTest(unittest.TestCase):
    @given(st.sampled_from(LEAVES))
    def test_any_leaf_asked_for_is_exactly_that_leaf(self, leaf) -> None:
        path, parser = leaf
        _, out, _ = _run(*path, "--json")

        (entry,) = json.loads(out)["commands"]
        self.assertEqual(entry["path"], " ".join(path))
        self.assertEqual(entry["usage"], parser.format_usage().strip())


if __name__ == "__main__":
    unittest.main()
