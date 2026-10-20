"""§177, INV-276: a documented command is one the parser accepts (#47, DOC003).

Every `aart-cli …` line in a fenced block of the README or a user-facing document is handed to
`build_parser()` by `make docs-check`. A renamed or removed command then fails `pr-check` instead of
waiting for a reader to find it at the shell. `docs/refactor/` and the Product Specification are
left out: they describe history and the target, and name commands on purpose that do not exist.
"""

from __future__ import annotations

import argparse
import pathlib
import tempfile
import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.cli_parser import build_parser
from tests.quality_gates_test import ROOT, _load_script

docs_check = _load_script("docs_check")
PARSER = build_parser()


def _leaf_paths(parser: argparse.ArgumentParser, path: tuple[str, ...] = ()):
    groups = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not groups:
        yield path
        return
    for name, child in groups[0].choices.items():
        yield from _leaf_paths(child, (*path, name))


LEAF_PATHS = tuple(_leaf_paths(PARSER))


def _codes(text: str, relative: str = "docs/guide.md") -> list[tuple[int, str]]:
    with tempfile.TemporaryDirectory() as raw:
        root = pathlib.Path(raw)
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        found = docs_check.validate_markdown(path, text, root, parser=PARSER)
    return [(item.line, item.code) for item in found]


class FencedCommandParseTest(unittest.TestCase):
    def test_a_fenced_command_the_parser_rejects_is_reported_at_its_line(self) -> None:
        text = "# Guide\n\n```sh\naart-cli consume list\naart-cli consume instal x\n```\n"

        self.assertEqual(_codes(text), [(5, "DOC003")])

    def test_an_unknown_option_is_reported_too(self) -> None:
        text = "```sh\naart-cli consume status --profiles claude\n```\n"

        self.assertEqual(_codes(text), [(2, "DOC003")])

    def test_the_way_documents_write_commands_parses(self) -> None:
        text = (
            "```console\n"
            "$ aart-cli consume install <alias>/<kind>/<name> --profile <harness>\n"
            "aart-cli consume mcp test company/mcp/github@1.0.0 --harness opencode "
            '--scope project --project "$PWD"\n'
            "aart-cli consume search review --json | jq '.results[0]'\n"
            "aart-cli doctor --repair company/mcp/github --yes --expect <digest>  # apply it\n"
            "AART_CLI_HOME=/tmp/aart aart-cli reset --yes\n"
            "aart-cli maintain registry validate --help\n"
            "aart-cli\n"
            "```\n"
        )

        self.assertEqual(_codes(text), [])

    def test_the_module_spelling_is_held_to_the_same_parser(self) -> None:
        text = (
            "```sh\n"
            "python3 -m aart_cli.cli consume list\n"
            "python -m aart_cli consume list\n"
            "python3 -m aart_cli.cli source add --alias x\n"
            "```\n"
        )

        self.assertEqual(_codes(text), [(4, "DOC003")])

    def test_a_continued_command_is_checked_whole_and_reported_where_it_starts(self) -> None:
        text = (
            "```sh\n"
            "aart-cli security scan object.json --registry /r \\\n"
            "  --artifact skill/review \\\n"
            "  --cache-dir /c\n"
            "```\n"
        )

        self.assertEqual(_codes(text), [(2, "DOC003")])

    def test_prose_and_output_lines_are_not_commands(self) -> None:
        text = (
            "Run aart-cli consume instal to see.\n\n"
            "```text\n"
            "aart-cli: error: invalid choice\n"
            "Reviewed only; re-run with --yes to apply.\n"
            "```\n"
        )

        self.assertEqual(_codes(text), [])

    def test_history_and_the_specification_are_not_held_to_the_parser(self) -> None:
        text = "```sh\naart-cli registry policy-check\n```\n"

        self.assertEqual(_codes(text, "docs/refactor/NEXT.md"), [])
        self.assertEqual(_codes(text, "docs/product-specification/PRODUCT_SPECIFICATION.md"), [])
        self.assertEqual(_codes(text, "README.md"), [(2, "DOC003")])

    def test_the_repository_documents_only_commands_that_parse(self) -> None:
        self.assertEqual(docs_check.check_repository(ROOT), ())


class FencedCommandPropertyTest(unittest.TestCase):
    @given(st.sampled_from(LEAF_PATHS))
    def test_every_shipped_command_passes_and_a_flag_it_lacks_does_not(self, path) -> None:
        command = " ".join(("aart-cli", *path))

        self.assertEqual(_codes(f"```sh\n{command} --help\n```\n"), [])
        self.assertEqual(_codes(f"```sh\n{command} --no-such-flag\n```\n"), [(2, "DOC003")])


if __name__ == "__main__":
    unittest.main()
