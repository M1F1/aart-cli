from __future__ import annotations

import argparse
import ast
import re
import unittest
from pathlib import Path

from agent_artifacts import __version__, cli, model, wizard

_ROOT = Path(__file__).resolve().parents[1]
_README = (_ROOT / "README.md").read_text(encoding="utf-8")
_SPELLED = {9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}


def _command_surface() -> dict[str, frozenset[str]]:
    """The shipped command tree, read off the parser rather than listed here.

    A list written in a test is a second place to forget: it goes stale in the same direction as
    the README it is checking, and then agrees with it for the wrong reason.
    """

    def actions(parser: argparse.ArgumentParser) -> list[argparse._SubParsersAction]:
        return [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]

    surface: dict[str, frozenset[str]] = {}
    for top in actions(cli.build_parser()):
        for name, sub in top.choices.items():
            nested = {child for action in actions(sub) for child in action.choices}
            surface[name] = frozenset(nested)
    return surface


class ReadmeCommandSurfaceTest(unittest.TestCase):
    """The README is where a reader learns what the tool can do, so it is a claim about the
    command tree and drifts from it silently.  Both directions matter and they fail differently:
    a command the README invents wastes a reader's time at the shell, and a command the README
    omits is capability nobody can find."""

    def test_every_shipped_top_level_command_is_named(self) -> None:
        surface = _command_surface()

        # Plain `aart <name>`, not a backticked spelling: most of these appear inside fenced
        # shell blocks, where there are no backticks, and requiring them made this test report
        # five commands the README documents perfectly well.
        mentioned = set(re.findall(r"\baart ([a-z][a-z-]+)", _README))
        missing = sorted(set(surface) - mentioned)

        self.assertEqual(
            missing,
            [],
            "the README documents no route to these shipped commands",
        )

    def test_the_readme_invents_no_command(self) -> None:
        surface = _command_surface()

        invented = sorted(
            {
                f"{group} {sub}"
                for group, sub in re.findall(r"aart ([a-z][a-z-]+) ([a-z][a-z-]+)", _README)
                if group in surface and surface[group] and sub not in surface[group]
            }
        )

        self.assertEqual(invented, [], "the README names subcommands the CLI does not have")

    def test_this_guard_is_not_vacuous(self) -> None:
        surface = _command_surface()

        self.assertGreater(len(surface), 5)
        self.assertIn("marketplace", surface)
        self.assertIn("install", surface["marketplace"])


class RootDocumentAuthorityTest(unittest.TestCase):
    """A newcomer opening a root-level markdown file has met this repository's authority, whether
    or not the file meant to be authoritative.

    Three of them -- `PLAN.md`, `PROGRESS.md`, `TODO.md` -- are the completed `M1F1/agent-artifacts`
    1.0 program, and `TODO.md` opened by saying its GitHub issues "remain the source of truth for
    discussion and status", which sends a reader to a repository CLAUDE.md names as legacy. That the
    contract file classifies them as historical does not help someone who never opened it, so the
    documents say it themselves.
    """

    LEGACY_PROGRAM = "M1F1/agent-artifacts/"

    def _root_documents(self) -> list[Path]:
        return sorted(p for p in _ROOT.glob("*.md"))

    def test_a_root_document_citing_the_legacy_program_says_it_is_historical(self) -> None:
        for path in self._root_documents():
            text = path.read_text(encoding="utf-8")
            if self.LEGACY_PROGRAM not in text:
                continue
            with self.subTest(document=path.name):
                head = text[:600]
                self.assertIn("[!WARNING]", head, f"{path.name} cites the legacy program unmarked")
                self.assertIn("PRODUCT_SPECIFICATION.md", head)

    def test_no_root_document_sends_a_reader_to_the_legacy_issue_tracker_for_status(self) -> None:
        for path in self._root_documents():
            text = path.read_text(encoding="utf-8")
            with self.subTest(document=path.name):
                self.assertNotIn("GitHub issues remain the source of truth", text)

    def test_this_guard_is_not_vacuous(self) -> None:
        citing = [p.name for p in self._root_documents() if self.LEGACY_PROGRAM in p.read_text()]

        self.assertEqual(sorted(citing), ["PLAN.md", "PROGRESS.md", "TODO.md"])


class RemediationNamesRealCommandsTest(unittest.TestCase):
    """A diagnostic's remediation is documentation the user reads at the worst moment, and it
    names commands the way a page does -- so it drifts the way a page does, with no reader to
    notice until someone is already stuck.

    Scoped to `aart <group> <subcommand>` where the group is real, which is the shape that can be
    checked without guessing: bare `aart <word>` also matches the managed-block marker
    `# >>> aart setup: ... >>>` and ordinary prose like "aart installs", neither of which is a
    command anyone is being told to run.
    """

    def test_no_user_facing_string_names_a_subcommand_that_does_not_exist(self) -> None:
        surface = _command_surface()
        invented: dict[str, set[str]] = {}

        for module in sorted((_ROOT / "agent_artifacts").rglob("*.py")):
            try:
                tree = ast.parse(module.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover - the package parses
                continue
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                    continue
                for group, sub in re.findall(r"aart ([a-z][a-z-]+) ([a-z][a-z-]+)", node.value):
                    if group in surface and surface[group] and sub not in surface[group]:
                        name = str(module.relative_to(_ROOT))
                        invented.setdefault(name, set()).add(f"{group} {sub}")

        self.assertEqual(invented, {}, "these strings tell a user to run a command that is gone")

    def test_this_guard_is_not_vacuous(self) -> None:
        surface = _command_surface()
        sources = list((_ROOT / "agent_artifacts").rglob("*.py"))

        self.assertGreater(len(sources), 100)
        self.assertIn("uninstall", surface["marketplace"])


class ReadmeAdoptionTest(unittest.TestCase):
    def _install_section(self) -> str:
        start = _README.index("## Install and quick start")
        return _README[start : _README.index("The editable install is", start)]

    def test_the_page_names_no_address_a_fork_would_have_to_correct(self) -> None:
        """The exact commands belong on the release, not here.

        A README cannot know which instance it is being read on -- nothing interpolates a variable
        into a markdown file -- so an address written here is upstream's address, wrong in every
        fork, and a line every fork would have to edit and then re-edit on each merge. The release
        page can know: `cut_release.py` derives it from the remote it is publishing to.
        """

        section = self._install_section()
        for address in ("https://github.com/", "http://", "ghe.corp", "nexus.corp"):
            with self.subTest(address=address):
                self.assertNotIn(address, section)
        # Relative on purpose: it resolves inside whatever repository the file lives in.
        self.assertIn("[Releases page](../../releases)", section)
        self.assertIn("python scripts/install_commands.py", section)

    def test_install_grid_covers_three_installers_against_a_named_placeholder(self) -> None:
        section = self._install_section()
        for installer in ("python -m pip install", "pipx install", "uv tool install"):
            with self.subTest(installer=installer):
                self.assertGreaterEqual(section.count(installer), 3)
        # One placeholder, defined once, used everywhere an address would have gone.
        self.assertIn("`<repository>` is the address of the", section)
        self.assertGreaterEqual(section.count("git+<repository>.git@v"), 3)
        # Taken from the executable, not written here: a literal passes while the README goes
        # stale, which is exactly how 2.8.0 nearly shipped a matrix still naming 2.7.1.  A wheel
        # filename is not an address, so it stays whole.
        self.assertGreaterEqual(section.count(f"./aart_cli-{__version__}-py3-none-any.whl"), 3)
        self.assertIn("The editable install is for working on AART itself", _README)

    def test_the_enterprise_section_still_says_which_sources_stop_working(self) -> None:
        """A private instance narrows the grid, and the narrowing has to be written down.

        Only the Git row carries credentials there: `pip`, `pipx` and `uv` send no token when they
        fetch a URL, so a release asset on a private repository answers with a sign-in page and the
        installer fails on a corrupt archive rather than on a refusal.  A reader who copies the
        public table and swaps the host gets that failure with no clue in it.
        """

        start = _README.index("### On a private Enterprise instance")
        section = _README[start : _README.index("The editable install is", start)]
        self.assertIn(f'"aart-cli=={__version__}"', section)
        self.assertIn("Release wheel by URL", section)
        self.assertIn("**No.**", section)

    def test_the_gate_table_lists_every_gate_the_runner_actually_builds(self) -> None:
        """The heading said nine for as long as there were ten.

        `secret-shape-check` was added and the prose was not, so the page under-reported the work
        by one gate -- harmless in itself, and exactly the drift that makes a reader stop trusting
        the rest of the table.  Reading the names off `build_gates` closes it: a gate added without
        a row fails here.
        """

        import sys

        sys.path.insert(0, str(_ROOT / "scripts"))
        import quality

        names = [gate.name for gate in quality.build_gates(_ROOT / "unused")]
        for name in names:
            with self.subTest(gate=name):
                self.assertIn(f"| `{name}` |", _README)
        self.assertIn(f"### The {_SPELLED[len(names)]} gates", _README)

    def test_the_release_section_describes_the_release_that_actually_happens(self) -> None:
        """A release page that has drifted is worse than none: it is followed.

        There is no local half any more and no button: a person merges a pull request whose title
        classifies it, and later merges the release pull request. So what has to be on the page is
        the classification -- which the writer of every pull request needs and no script can
        supply -- and the two commands that are still commands.
        """

        section = _README[_README.index("## Releasing") : _README.index("## License")]
        for phrase in (
            "fix(tui): preserve selected artifact after refresh",
            "feat(registry)!: replace legacy source schema",
            "python scripts/conventional_title.py",
            "python scripts/release_artifact.py --tag",
            # Automating the arithmetic is not automating the decision, and a reader has to be
            # told which half is which.
            "Nothing merges that pull request for you.",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, section)
        # The one thing this walk proved the hard way, and the reason a re-run looks like a no-op.
        self.assertIn("read from the tag, not from `main`", section)
        # The retired half is gone from the page, not merely unlinked from it.
        for retired in ("prepare_release", "cut_release", "changelog.py", "scripts/version.py"):
            with self.subTest(retired=retired):
                self.assertNotIn(retired, section)

    def test_registry_entrance_names_vendoring_and_links_the_walked_tutorial(self) -> None:
        for phrase in (
            "`vendor` is the foreign-repository path",
            "`provenance.json`",
            "`revendor`",
            "docs/tutorials/company-registry-tabnine-v1.md",
        ):
            self.assertIn(phrase, _README)


class CollectionVocabularyTest(unittest.TestCase):
    def test_dead_bundle_model_and_tui_vocabulary_are_gone(self) -> None:
        self.assertFalse(hasattr(model, "Bundle"))
        self.assertFalse(hasattr(model, "Catalog"))
        self.assertFalse(hasattr(model, "ResolvedBundle"))
        self.assertEqual(
            wizard.BasketItem("collection", "company/collection/base", "base").kind,
            "collection",
        )


if __name__ == "__main__":
    unittest.main()
