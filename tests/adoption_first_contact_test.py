from __future__ import annotations

import argparse
import ast
import re
import unittest
from pathlib import Path

from agent_artifacts import cli, model, wizard
from agent_artifacts.domain.artifacts import ArtifactKind
from tests.source_remediation_test import _parse_failure

_ROOT = Path(__file__).resolve().parents[1]
_README = (_ROOT / "README.md").read_text(encoding="utf-8")
_SPELLED = {9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}
#: Substituted for every `<…>` before a route command is handed to the parser.
_PLACEHOLDER = "placeholder"
#: The four things §1.6 says a new user has to be able to tell apart.
_STAGES = ("Source", "Candidate", "Registry", "Marketplace")


def _section(heading: str) -> str:
    """One top-level section, sliced at the next top-level heading rather than at a named one.

    Naming the section that follows would couple these tests to an ordering CP-26 is still free to
    change, and would turn a reordering into a slice error instead of the ordering failure the
    tests below are written to report.
    """

    start = _README.index(f"## {heading}")
    following = re.search(r"^## ", _README[start + 1 :], re.M)
    assert following is not None, f"{heading} is the last section"
    return _README[start : start + 1 + following.start()]


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


class QuickStartRouteTest(unittest.TestCase):
    """The README's first section is a route somebody runs, so it is held as commands, not prose.

    CP-26 §1.6 fixes what a new reader meets first: the shortest supported sequence from no AART
    installation to an installed artifact they can verify. A route that reads well and does not
    run is the failure this is written against -- the reader is at a shell, and a flag the parser
    does not have costs them the afternoon the page was meant to save.
    """

    #: The five steps §1.6 names, as the command that performs each one.
    ROUTE = ("source add", "marketplace search", "marketplace install", "marketplace status")

    def _quick_start(self) -> str:
        return _section("Install an artifact")

    def test_the_route_is_the_first_thing_after_the_title(self) -> None:
        """Not merely present: first. A new user must not read an architecture section to reach
        the commands, which is the ordering §1.6 fixes."""

        headings = re.findall(r"^## (.+)$", _README, re.M)

        self.assertEqual(headings[0], "Install an artifact")

    def test_the_route_is_complete(self) -> None:
        quick_start = self._quick_start()

        for step in self.ROUTE:
            with self.subTest(step=step):
                self.assertIn(f"aart {step}", quick_start)

    def test_the_review_step_is_shown_before_the_step_that_applies_it(self) -> None:
        """Every mutation is two commands, and a route that showed only `--yes` would teach a
        reader to skip the half where nothing has happened yet."""

        quick_start = self._quick_start()
        reviewed = quick_start.index("aart marketplace install")
        finalized = quick_start.index("--yes")

        self.assertLess(reviewed, finalized)
        self.assertNotIn("--yes", quick_start[reviewed : quick_start.index("\n", reviewed)])

    def test_the_tui_is_offered_as_the_route_for_a_person(self) -> None:
        self.assertIn("aart\n", self._quick_start())

    def test_every_command_in_the_route_is_one_the_parser_accepts(self) -> None:
        """The claim worth holding. Placeholders are substituted with a token that is merely a
        value, so what is parsed is the reader's command with their answers in it."""

        commands = re.findall(r"^aart .+$", self._quick_start(), re.M)
        self.assertGreaterEqual(len(commands), len(self.ROUTE))

        for command in commands:
            with self.subTest(command=command):
                rejected = _parse_failure(re.sub(r"<[^>]+>", _PLACEHOLDER, command))

                self.assertIsNone(rejected, rejected)

    def test_the_route_names_no_address_a_fork_would_have_to_correct(self) -> None:
        """The same rule as the install grid: nothing here can know which instance it is read on."""

        quick_start = self._quick_start()

        for address in ("https://github.com/", "http://", "ghe.corp", "nexus.corp"):
            with self.subTest(address=address):
                self.assertNotIn(address, quick_start)


class OrientationTest(unittest.TestCase):
    """§1.6's second section: what AART is, read by somebody who has already installed something.

    It sits after the route on purpose, and the failure it is written against is the one every
    README drifts into -- the orientation grows into an architecture chapter, and the page is back
    to explaining itself before it is of any use.
    """

    HEADING = "What AART is"

    def test_the_orientation_follows_the_route_rather_than_preceding_it(self) -> None:
        headings = re.findall(r"^## (.+)$", _README, re.M)

        self.assertEqual(headings[:2], ["Install an artifact", self.HEADING])

    def test_the_orientation_stays_a_fraction_of_the_route_it_explains(self) -> None:
        """Bounded, held against the thing it introduces rather than against a number chosen here.

        A ceiling written as a line count is a number somebody raises by one. Half the route is a
        ratio: the orientation has room for another paragraph and no room for a chapter, and the
        claim survives step 15 moving material off this page.

        Merely `shorter than the route` was the first version of this and it did not hold -- forty
        lines of invented architecture still fit under the route's length, which is precisely the
        section §1.6 refuses. A bound that a mutation walks through is not a bound.
        """

        orientation = _section(self.HEADING).splitlines()
        route = _section("Install an artifact").splitlines()

        self.assertLess(2 * len(orientation), len(route))

    def test_the_orientation_names_every_artifact_family_this_build_installs(self) -> None:
        """Read off `ArtifactKind`, because a family AART installs and the page omits is a
        capability a reader concludes the tool does not have."""

        orientation = _section(self.HEADING).lower()

        for kind in ArtifactKind:
            with self.subTest(kind=kind.value):
                self.assertIn(kind.value, orientation)

    def test_the_orientation_names_the_path_an_artifact_travels_in_order(self) -> None:
        """Source, Candidate, Registry, Marketplace are four different things and a new user who
        conflates any two of them cannot read a diagnostic that names one of them."""

        orientation = _section(self.HEADING)
        positions = [orientation.find(stage) for stage in _STAGES]

        self.assertNotIn(-1, positions)
        self.assertEqual(positions, sorted(positions))


class DocumentationIndexTest(unittest.TestCase):
    """The index is the half of link checking `docs-check` cannot do.

    That gate reads every link in the repository and refuses one whose target is missing. Nothing
    reads the documents and refuses one that no link reaches -- and unreachable is the more common
    failure of the two: a page is written, merged, and then found by nobody, while the README goes
    on sending readers to the handful somebody remembered.
    """

    HEADING = "Documentation"

    def _public_documents(self) -> list[str]:
        """Everything this repository publishes. `docs/refactor` is the working record of the
        migration -- evidence for the next agent, not something a user is offered."""

        return sorted(
            str(path.relative_to(_ROOT))
            for path in (_ROOT / "docs").rglob("*.md")
            if "refactor" not in path.relative_to(_ROOT / "docs").parts
        )

    def _linked(self) -> set[str]:
        return set(re.findall(r"\]\((docs/[^)#]+)\)", _section(self.HEADING)))

    def test_this_guard_is_not_vacuous(self) -> None:
        self.assertGreater(len(self._public_documents()), 20)

    def test_every_public_document_is_reachable_from_the_index(self) -> None:
        linked = self._linked()

        unreachable = [path for path in self._public_documents() if path not in linked]

        self.assertEqual(unreachable, [], "no link on this page reaches these documents")

    def test_the_index_sends_no_reader_into_the_migration_record(self) -> None:
        self.assertNotIn("docs/refactor/", _section(self.HEADING))

    def test_the_index_is_grouped_and_no_link_floats_outside_a_group(self) -> None:
        """Categorized is the point: twenty-five links under one heading is a directory listing,
        which is what the reader already had."""

        index = _section(self.HEADING)
        groups = [match.start() for match in re.finditer(r"^\*\*(.+?)\*\*", index, re.M)]
        links = [match.start() for match in re.finditer(r"\]\(docs/", index)]

        self.assertGreaterEqual(len(groups), 6)
        self.assertTrue(links)
        self.assertGreater(min(links), min(groups))


class RootDocumentAuthorityTest(unittest.TestCase):
    """A newcomer opening a root-level markdown file has met this repository's authority, whether
    or not the file meant to be authoritative.

    So no root document may send a reader to a predecessor repository, which CLAUDE.md names as
    reference only: not for behaviour, and not for status in its issue tracker.
    """

    LEGACY_REPOSITORY = "M1F1/agent-artifacts/"

    def _root_documents(self) -> list[Path]:
        return sorted(p for p in _ROOT.glob("*.md"))

    def test_no_root_document_cites_a_predecessor_repository(self) -> None:
        documents = self._root_documents()
        self.assertGreater(len(documents), 2)
        for path in documents:
            with self.subTest(document=path.name):
                self.assertNotIn(self.LEGACY_REPOSITORY, path.read_text(encoding="utf-8"))

    def test_no_root_document_sends_a_reader_to_the_legacy_issue_tracker_for_status(self) -> None:
        for path in self._root_documents():
            text = path.read_text(encoding="utf-8")
            with self.subTest(document=path.name):
                self.assertNotIn("GitHub issues remain the source of truth", text)


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
        # The release is a placeholder too: the exact version is printed by
        # `scripts/install_commands.py` and carried by the release body, so nothing here goes stale.
        self.assertIn("`X.Y.Z` is the release you want", section)
        self.assertGreaterEqual(section.count("git+<repository>.git@vX.Y.Z"), 3)
        self.assertGreaterEqual(section.count("./aart_cli-X.Y.Z-py3-none-any.whl"), 3)
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
        self.assertIn('"aart-cli==X.Y.Z"', section)
        self.assertIn("Release wheel by URL", section)
        self.assertIn("**No.**", section)

    def test_the_gate_table_lists_every_gate_the_runner_actually_builds(self) -> None:
        """The heading said nine for as long as there were ten.

        `secret-shape-check` was added and the prose was not, so the page under-reported the work
        by one gate -- harmless in itself, and exactly the drift that makes a reader stop trusting
        the rest of the table.  Reading the names off `build_gates` closes it: a gate added without
        a row fails here.

        The heading counts `QUALITY_GATES` rather than everything built, because the two differ
        since CP-25: `release-bump` is selectable by name and deliberately outside the full run
        (INV-096).  It still needs a row -- the loop below is over every gate that exists -- but it
        is not one of the ten `python scripts/quality.py` runs, and a heading that said eleven
        would send a reader looking for an eleventh line of output.
        """

        import sys

        sys.path.insert(0, str(_ROOT / "scripts"))
        import quality

        for gate in quality.build_gates(_ROOT / "unused"):
            with self.subTest(gate=gate.name):
                self.assertIn(f"| `{gate.name}` |", _README)
        self.assertIn(f"### The {_SPELLED[len(quality.QUALITY_GATES)]} gates", _README)

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
