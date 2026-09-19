"""`aart author init` writes a whole authoring workspace, or it writes nothing at all.

The generator is tested against the parser in `author_skeleton_test`; what is left to hold is the
command around it. Two claims matter here and neither is about YAML. The first is that what lands
on the disk is exactly what the generator produced, so the file an author opens is the file the
oracle checked. The second is that a refusal leaves the directory as it was: `init` is the first
command an author runs, often into a directory that already holds something, and a half-written
workspace would be blamed on their own edits.
"""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest import mock

from agent_artifacts.authoring.skeleton import (
    GENERATED_KINDS,
    PayloadFile,
    author_skeleton,
)
from agent_artifacts.cli import main
from agent_artifacts.command_outcome import ERROR, OK, USAGE
from agent_artifacts.commands.author import run
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.author_workspace import write_author_skeleton
from agent_artifacts.model import Request
from agent_artifacts.protocol.authoring import (
    DiscoveredAuthorManifest,
    parse_author_manifest,
)
from agent_artifacts.protocol.paths import parse_relative_path

_NAME = "github-mcp"


@contextmanager
def _workspace():
    with tempfile.TemporaryDirectory() as root:
        yield Path(root)


def _init(into: Path | None, *, kind: str = "mcp", name: str = _NAME) -> int:
    return _reported(into, kind=kind, name=name)[0]


def _reported(into: Path | None, *, kind: str = "mcp", name: str = _NAME) -> tuple[int, str]:
    argv = ["author", "init", "--kind", kind, "--name", name]
    if into is not None:
        argv += ["--into", str(into)]
    printed = io.StringIO()
    with redirect_stdout(printed):
        code = main(argv)
    return code, printed.getvalue()


def _tree(root: Path) -> set[str]:
    return {
        str(path.relative_to(root)) for path in root.rglob("*") if path.is_file() or path.is_dir()
    }


def _generated():
    result = author_skeleton("mcp", _NAME)
    assert isinstance(result, Ok), result
    return result.value


class InitTest(unittest.TestCase):
    def test_the_manifest_and_every_payload_file_are_written(self) -> None:
        with _workspace() as root:
            self.assertEqual(_init(root), OK)

            written = _tree(root)

        self.assertIn("aart.yaml", written)
        for file in _generated().payload:
            self.assertIn(file.path, written)

    def test_what_is_written_is_exactly_what_the_generator_produced(self) -> None:
        """The oracle checks the generated text; this is what makes it the text on the disk."""

        skeleton = _generated()

        with _workspace() as root:
            _init(root)

            self.assertEqual((root / "aart.yaml").read_text(encoding="utf-8"), skeleton.manifest)
            for file in skeleton.payload:
                self.assertEqual((root / file.path).read_text(encoding="utf-8"), file.content)

    def test_a_hook_script_is_written_executable(self) -> None:
        with _workspace() as root:
            self.assertEqual(_init(root, kind="hook", name="guard-bash"), OK)

            self.assertTrue(os.access(root / "run.sh", os.X_OK))

    def test_the_written_manifest_parses(self) -> None:
        with _workspace() as root:
            _init(root)
            text = (root / "aart.yaml").read_bytes()

        path = parse_relative_path("aart.yaml")
        assert isinstance(path, Ok), path

        self.assertIsInstance(parse_author_manifest(DiscoveredAuthorManifest(path.value, text)), Ok)

    def test_a_directory_that_does_not_exist_yet_is_created(self) -> None:
        with _workspace() as root:
            target = root / "artifacts" / "github-mcp"

            self.assertEqual(_init(target), OK)
            self.assertTrue((target / "aart.yaml").is_file())

    def test_every_written_path_is_named_in_what_the_command_prints(self) -> None:
        """An agent reads the report; a path written but unreported is a file nobody edits."""

        with _workspace() as root:
            code, printed = _reported(root)

            self.assertEqual(code, OK)
            self.assertIn(str(root), printed)
            for path in _tree(root):
                if (root / path).is_file():
                    self.assertIn(path, printed)

    def test_into_defaults_to_the_working_directory(self) -> None:
        previous = os.getcwd()
        with _workspace() as root:
            os.chdir(root)
            try:
                self.assertEqual(_init(None), OK)
            finally:
                os.chdir(previous)

            self.assertTrue((root / "aart.yaml").is_file())


class RefusalTest(unittest.TestCase):
    """A refusal leaves the directory exactly as it was."""

    def test_an_existing_manifest_is_never_overwritten(self) -> None:
        with _workspace() as root:
            (root / "aart.yaml").write_text("mine\n", encoding="utf-8")

            self.assertEqual(_init(root), ERROR)
            self.assertEqual((root / "aart.yaml").read_text(encoding="utf-8"), "mine\n")
            self.assertEqual(_tree(root), {"aart.yaml"})

    def test_an_existing_payload_file_stops_the_manifest_being_written(self) -> None:
        """The conflict is found before anything is written, not while writing."""

        with _workspace() as root:
            taken = _generated().payload[0].path
            (root / taken).write_text("mine\n", encoding="utf-8")

            self.assertEqual(_init(root), ERROR)
            self.assertEqual(_tree(root), {taken})

    def test_a_kind_this_build_does_not_generate_writes_nothing(self) -> None:
        """No accepted kind is ungenerated any more, so this goes through the command directly.

        The `--kind` choices are `get_args(AuthorKind)`, so argparse refuses anything else before
        the command sees it. The refusal below is the one that would matter again the day the
        parser accepts a kind no blueprint has been written for.
        """

        with _workspace() as root:
            code = run(
                Request(
                    command="author",
                    author_action="init",
                    artifact_kind="plugin",
                    author_name=_NAME,
                    author_into=str(root),
                )
            )

            self.assertEqual(code, ERROR)
            self.assertEqual(_tree(root), set())

    def test_every_kind_this_build_generates_writes_a_workspace(self) -> None:
        for kind in GENERATED_KINDS:
            with self.subTest(kind=kind), _workspace() as root:
                self.assertEqual(_init(root, kind=kind, name="code-review"), OK)
                self.assertTrue((root / "aart.yaml").is_file())

    def test_a_name_the_parser_rejects_writes_nothing(self) -> None:
        with _workspace() as root:
            self.assertEqual(_init(root, name="Not A Slug"), ERROR)
            self.assertEqual(_tree(root), set())

    def test_a_kind_outside_the_parser_vocabulary_is_a_usage_error(self) -> None:
        with (
            _workspace() as root,
            redirect_stdout(io.StringIO()),
            self.assertRaises(SystemExit) as raised,
        ):
            _init(root, kind="plugin")

        self.assertEqual(raised.exception.code, USAGE)

    def test_a_symlink_where_a_target_would_go_is_not_written_through(self) -> None:
        """A link that points nowhere is still something the author put there."""

        with _workspace() as root:
            elsewhere = root / "elsewhere"
            elsewhere.mkdir()
            (elsewhere / "aart.yaml").symlink_to(elsewhere / "absent.yaml")

            self.assertEqual(_init(elsewhere), ERROR)
            self.assertFalse((elsewhere / "absent.yaml").exists())

    def test_a_file_where_the_workspace_should_be_is_refused(self) -> None:
        with _workspace() as root:
            target = root / "occupied"
            target.write_text("not a directory\n", encoding="utf-8")

            self.assertEqual(_init(target), ERROR)
            self.assertEqual(target.read_text(encoding="utf-8"), "not a directory\n")


class WriterTest(unittest.TestCase):
    """What the writer refuses about the generator, rather than about the author."""

    def test_a_failure_part_way_through_leaves_nothing_behind(self) -> None:
        """The claim the docstring makes: either the whole workspace, or the directory as it was.

        Reached by making the second write fail, because the interesting case is the one where
        some of the workspace is already on the disk when the failure arrives.
        """

        real = Path.write_text
        calls: list[Path] = []

        def once(self: Path, *arguments: object, **keywords: object):
            calls.append(self)
            if len(calls) > 1:
                raise OSError("no space left on device")
            return real(self, *arguments, **keywords)  # type: ignore[arg-type]

        with _workspace() as root:
            target = root / "workspace"
            with mock.patch.object(Path, "write_text", once):
                written = write_author_skeleton(_generated(), into=str(target))

            assert isinstance(written, Err), written
            self.assertGreater(len(calls), 1)
            self.assertFalse(target.exists())

    def test_a_refusal_an_author_can_act_on_says_what_to_do(self) -> None:
        """A refusal with no remediation makes the author guess at what AART wants."""

        with _workspace() as root:
            (root / "aart.yaml").write_text("mine\n", encoding="utf-8")
            written = write_author_skeleton(_generated(), into=str(root))

            assert isinstance(written, Err), written
            self.assertTrue(written.diagnostics[0].remediation)

    def test_a_payload_path_that_climbs_out_of_the_workspace_is_refused(self) -> None:
        """The paths come from the generator, which is exactly why they are checked here."""

        escaping = replace(_generated(), payload=(PayloadFile("../escape.py", "nothing\n"),))

        with _workspace() as root:
            written = write_author_skeleton(escaping, into=str(root / "inside"))

            assert isinstance(written, Err), written
            self.assertFalse((root / "escape.py").exists())
            self.assertFalse((root / "inside").exists())


if __name__ == "__main__":
    unittest.main()
