"""`aart author check` answers with the parser, not with a lint of its own.

The loop this command exists for is amend, check, amend, and the only verdict worth having in it is
the one the Registry will later issue. So the claim held here is not "the checker reports errors" —
it is that the checker's yes and the parser's yes are the same yes, proved by feeding it a manifest
the parser refuses for a reason no reasonable lint would think to check.

A checker that is merely stricter is as bad as one that is laxer: it would refuse manifests AART
accepts, and an author would edit a correct file until a wrong one passed.

The second claim is the one a person cannot check by eye: the manifest compiles to the canonical
package `registry scan` would accept. `PromotionTest` is written against a manifest the parser
accepts and the compiler does not, because that gap is the whole reason the claim exists.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path

from agent_artifacts.authoring.skeleton import author_skeleton
from agent_artifacts.cli import main
from agent_artifacts.command_outcome import ERROR, OK
from agent_artifacts.domain.result import Ok
from agent_artifacts.io.author_workspace import write_author_skeleton

_NAME = "github-mcp"


@contextmanager
def _workspace(kind: str = "mcp", name: str = _NAME):
    """A directory holding exactly what `aart author init` would have written."""

    with tempfile.TemporaryDirectory() as root:
        generated = author_skeleton(kind, name)
        assert isinstance(generated, Ok), generated
        written = write_author_skeleton(generated.value, into=str(Path(root) / name))
        assert isinstance(written, Ok), written
        yield Path(root)


def _check(root: Path, *, as_json: bool = False) -> tuple[int, str]:
    argv = ["author", "check", "--source", str(root)]
    if as_json:
        argv.append("--json")
    printed = io.StringIO()
    with redirect_stdout(printed):
        code = main(argv)
    return code, printed.getvalue()


def _manifest(root: Path) -> Path:
    return next(root.rglob("aart.yaml"))


def _write_collection(directory: Path) -> None:
    """A Collection manifest: discovered by the same walk, compiled by a different function."""

    directory.mkdir(parents=True)
    (directory / "aart.json").write_text(
        json.dumps(
            {
                "schema": "aart.dev/collection/v1",
                "name": "data-engineer",
                "version": "2.1.0",
                "summary": "Approved data engineering tools.",
                "artifacts": ["company/mcp/github@^2"],
            }
        ),
        encoding="utf-8",
    )


class AcceptanceTest(unittest.TestCase):
    def test_a_generated_workspace_passes(self) -> None:
        """What `init` writes is what `check` accepts, or one of the two is wrong."""

        with _workspace() as root:
            code, printed = _check(root)

            self.assertEqual(code, OK)
            self.assertIn("aart.yaml", printed)

    def test_every_generated_kind_passes(self) -> None:
        for kind, name in (("mcp", _NAME), ("skill", "code-review")):
            with self.subTest(kind=kind), _workspace(kind, name) as root:
                self.assertEqual(_check(root)[0], OK)

    def test_two_artifacts_in_one_tree_are_both_reported(self) -> None:
        with _workspace() as root:
            second = author_skeleton("skill", "code-review")
            assert isinstance(second, Ok), second
            written = write_author_skeleton(second.value, into=str(root / "code-review"))
            assert isinstance(written, Ok), written

            code, printed = _check(root)

            self.assertEqual(code, OK)
            self.assertIn(f"{_NAME}/aart.yaml", printed)
            self.assertIn("code-review/aart.yaml", printed)


class RefusalTest(unittest.TestCase):
    def test_a_manifest_the_parser_refuses_is_refused_here_in_the_parser_words(self) -> None:
        """The rule chosen is one no lint would invent: a secret's guidance may carry no example.

        §91 keeps the confidential class free of any field a real credential could be written
        into. A checker with its own idea of validity would pass this file, and `registry scan`
        would then refuse it.
        """

        with _workspace() as root:
            manifest = _manifest(root)
            text = manifest.read_text(encoding="utf-8")
            text = text.replace(
                "      format_hint: A provider-issued access token, on one line.",
                "      example: exa_0123456789\n"
                "      format_hint: A provider-issued access token, on one line.",
            )
            manifest.write_text(_enabled_inputs(text), encoding="utf-8")

            code, printed = _check(root)

            self.assertEqual(code, ERROR)
            self.assertIn("example", printed)

    def test_a_manifest_that_is_not_yaml_at_all_is_reported_with_its_path(self) -> None:
        with _workspace() as root:
            _manifest(root).write_text("\tnot: yaml\n", encoding="utf-8")

            code, printed = _check(root)

            self.assertEqual(code, ERROR)
            self.assertIn("aart.yaml", printed)

    def test_a_directory_holding_no_manifest_is_not_a_pass(self) -> None:
        """Nothing found is not everything fine: the exit code an agent branches on says so."""

        with tempfile.TemporaryDirectory() as empty:
            code, printed = _check(Path(empty))

            self.assertEqual(code, ERROR)
            self.assertIn("no author manifest", printed)

    def test_the_empty_tree_refusal_names_the_command_that_writes_one(self) -> None:
        """An author who mistyped a directory is one command from a manifest, and told which."""

        with tempfile.TemporaryDirectory() as empty:
            self.assertIn("aart author init", _check(Path(empty))[1])

    def test_a_source_that_does_not_exist_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            code, _printed = _check(Path(root) / "absent")

            self.assertEqual(code, ERROR)

    def test_one_bad_manifest_beside_a_good_one_fails_the_whole_check(self) -> None:
        with _workspace() as root:
            broken = root / "broken"
            broken.mkdir()
            (broken / "aart.yaml").write_text("schema: aart.dev/mcp/v1\n", encoding="utf-8")

            code, printed = _check(root)

            self.assertEqual(code, ERROR)
            self.assertIn("broken/aart.yaml", printed)

    def test_every_discovered_manifest_is_reported_however_the_one_before_it_ended(self) -> None:
        """A report that stopped at the first refusal would hide the manifests after it.

        The three kinds of verdict are laid out in discovery order, so a loop that gave up on any
        one of them loses a path this asserts is present.
        """

        with _workspace() as root:
            broken = root / "aaa-broken"
            broken.mkdir()
            (broken / "aart.yaml").write_text("schema: aart.dev/mcp/v1\n", encoding="utf-8")
            _write_collection(root / "bbb-collection")

            code, printed = _check(root)

            self.assertEqual(code, ERROR)
            for path in ("aaa-broken/aart.yaml", "bbb-collection/aart.json", f"{_NAME}/aart.yaml"):
                self.assertIn(path, printed)


class PromotionTest(unittest.TestCase):
    """The second claim of §1.4: the manifest compiles to a package `registry scan` would take.

    Every case here starts from a manifest the parser accepts, because a parse refusal would prove
    nothing about compilation.
    """

    def test_a_manifest_the_parser_accepts_and_the_compiler_refuses_is_refused(self) -> None:
        """`payload.include` is a list of strings to the parser and a file selection to the
        compiler. Naming a file the payload does not select parses cleanly and cannot be promoted,
        which is the gap an author cannot see and `registry scan` would have found later."""

        with _workspace() as root:
            manifest = _manifest(root)
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace("    - server.py", "    - absent.py"),
                encoding="utf-8",
            )

            code, printed = _check(root)

            self.assertEqual(code, ERROR)
            self.assertIn("outside the declared payload", printed)

    def test_the_coordinate_a_manifest_compiles_to_is_what_the_check_reports(self) -> None:
        """An author who reads `mcp/github-mcp@0.1.0` knows the compile ran, not just the parse."""

        with _workspace() as root:
            code, printed = _check(root)

            self.assertEqual(code, OK)
            self.assertIn(f"mcp/{_NAME}@0.1.0", printed)

    def test_a_collection_manifest_is_not_judged_as_a_broken_artifact(self) -> None:
        """`registry scan` compiles artifacts and passes over Collections, so this check must too.

        Parsing one as an artifact reports "missing required field 'artifact'" about a file that is
        correct -- §1.4's stricter-is-no-better failure, in the form an author would actually hit.
        """

        with _workspace() as root:
            _write_collection(root / "collections" / "data-engineer")

            code, printed = _check(root)

            self.assertEqual(code, OK)
            self.assertIn("data-engineer/aart.json", printed)
            self.assertNotIn("missing required field", printed)


class JsonTest(unittest.TestCase):
    """An agent runs this in a loop, so the machine-readable answer is part of the contract."""

    def test_a_passing_check_reports_every_manifest_it_read(self) -> None:
        with _workspace() as root:
            code, printed = _check(root, as_json=True)
            report = json.loads(printed)

            self.assertEqual(code, OK)
            self.assertIs(report["ok"], True)
            self.assertEqual(report["operation"], "author.check")
            self.assertEqual([item["path"] for item in report["manifests"]], [f"{_NAME}/aart.yaml"])

    def test_a_failing_check_carries_the_diagnostics_under_the_manifest(self) -> None:
        with _workspace() as root:
            _manifest(root).write_text("schema: aart.dev/mcp/v1\n", encoding="utf-8")

            code, printed = _check(root, as_json=True)
            report = json.loads(printed)

            self.assertEqual(code, ERROR)
            self.assertIs(report["ok"], False)
            (entry,) = report["manifests"]
            self.assertIs(entry["ok"], False)
            self.assertTrue(entry["diagnostics"])

    def test_an_accepted_manifest_names_the_package_it_compiles_to(self) -> None:
        with _workspace() as root:
            code, printed = _check(root, as_json=True)
            (entry,) = json.loads(printed)["manifests"]

            self.assertEqual(code, OK)
            self.assertEqual(entry["package"], f"mcp/{_NAME}@0.1.0")

    def test_a_manifest_this_check_does_not_compile_says_so_rather_than_claiming_a_package(
        self,
    ) -> None:
        with _workspace() as root:
            _write_collection(root / "collections" / "data-engineer")

            report = json.loads(_check(root, as_json=True)[1])
            entry = next(item for item in report["manifests"] if item["path"].endswith("aart.json"))

            self.assertIs(entry["ok"], True)
            self.assertIs(entry["checked"], False)
            self.assertIsNone(entry["package"])


def _enabled_inputs(text: str) -> str:
    """The skeleton ships `inputs` disabled; this check needs it live."""

    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip(" ")
        if stripped.startswith("## ") or stripped.startswith("#? "):
            continue
        if stripped.startswith("# "):
            indent = len(line) - len(stripped)
            lines.append(" " * indent + stripped[2:])
            continue
        lines.append(line)
    return "".join(f"{line}\n" for line in lines)


if __name__ == "__main__":
    unittest.main()
