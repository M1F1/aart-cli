"""A local author repository with a virtual environment works out of the box.

The author keeps `.venv/` in the repository and ignores it, as every Python project does. Its
`bin/python` is a symlink, and AART refuses symlinks in a Source; before, `author check` and
subscribing the checkout as a `source-local` both stopped on it. Both now read what Git would
commit, through the real CLI.
"""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from aart_cli.authoring.skeleton import author_skeleton
from aart_cli.cli import main
from aart_cli.command_outcome import OK
from aart_cli.domain.result import Ok
from aart_cli.io.author_workspace import write_author_skeleton


def _run(*argv: str) -> tuple[int, str]:
    printed = io.StringIO()
    with redirect_stdout(printed), redirect_stderr(printed):
        code = main(list(argv))
    return code, printed.getvalue()


class WorkingTreeSourceEndToEndTest(unittest.TestCase):
    def test_an_ignored_venv_stops_neither_author_check_nor_source_local(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(os.path.realpath(raw))
            repository = base / "authors"
            generated = author_skeleton("skill", "code-review")
            assert isinstance(generated, Ok), generated
            written = write_author_skeleton(generated.value, into=str(repository / "code-review"))
            assert isinstance(written, Ok), written
            (repository / ".gitignore").write_text(".venv/\n")
            subprocess.run(("git", "-C", str(repository), "init", "-q"), check=True)
            (repository / ".venv" / "bin").mkdir(parents=True)
            (repository / ".venv" / "bin" / "python").symlink_to("/usr/bin/python3")

            with mock.patch.dict(os.environ, {"AART_CLI_HOME": str(base / "home")}):
                checked, check_output = _run("author", "check", "--source", str(repository))
                added, add_output = _run(
                    "source",
                    "add",
                    "--alias",
                    "authors",
                    "--kind",
                    "source-local",
                    "--location",
                    str(repository),
                )

        self.assertEqual(checked, OK, check_output)
        self.assertIn("skill/code-review", check_output)
        self.assertNotIn(".venv", check_output)
        self.assertEqual(added, OK, add_output)
        self.assertIn("source added: authors", add_output)


if __name__ == "__main__":
    unittest.main()
