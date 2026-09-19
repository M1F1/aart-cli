from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from aart_cli import cli

ROOT = Path(__file__).resolve().parents[1]


def _run(*arguments: str) -> tuple[int, str]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = cli.main(list(arguments))
    return code, output.getvalue()


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _tree_bytes(root: Path) -> tuple[tuple[str, bytes], ...]:
    return tuple(
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    )


class RegistryCliIntegrationTest(unittest.TestCase):
    def test_registry_lifecycle_has_non_mutating_check_and_quality_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "registry"
            root.mkdir()
            _git(root, "init", "-q")

            code, output = _run(
                "registry",
                "init",
                "--source",
                str(root),
                "--source-id",
                "company-registry",
                "--display-name",
                "Company Registry",
                "--yes",
                "--json",
            )
            self.assertEqual(code, 0, output)
            finalized = json.loads(output)
            self.assertEqual(finalized["phase"], "finalized")
            self.assertEqual(finalized["review"]["phase"], "review")
            self.assertEqual(finalized["outcome"]["status"], "succeeded")
            self.assertTrue((root / ".github/workflows/aart-registry.yml").is_file())

            before_reads = _tree_bytes(root)
            for arguments in (
                ("validate",),
                ("audit",),
                ("diff",),
            ):
                code, output = _run("registry", *arguments, "--source", str(root), "--json")
                self.assertEqual(code, 0, output)
                self.assertEqual(_tree_bytes(root), before_reads)

            code, output = _run("registry", "lock", "--source", str(root), "--check", "--json")
            self.assertEqual(code, 0, output)
            self.assertFalse((root / "aart.lock.json").exists())
            self.assertEqual(_run("registry", "lock", "--source", str(root), "--yes")[0], 0)

            code, output = _run("registry", "build", "--source", str(root), "--check", "--json")
            self.assertEqual(code, 1, output)
            self.assertFalse((root / "aart.index.json").exists())
            self.assertEqual(_run("registry", "build", "--source", str(root), "--yes")[0], 0)
            self.assertTrue((root / "registry/index.json").is_file())
            self.assertTrue((root / "registry/snapshot.json").is_file())

            marker = root / "aart-registry.json"
            marker.write_text("{ " + marker.read_text(encoding="utf-8")[1:], encoding="utf-8")
            noncanonical = marker.read_bytes()
            code, output = _run("registry", "format", "--source", str(root), "--check", "--json")
            self.assertEqual(code, 1, output)
            self.assertEqual(marker.read_bytes(), noncanonical)
            self.assertEqual(_run("registry", "format", "--source", str(root), "--yes")[0], 0)
            self.assertNotEqual(marker.read_bytes(), noncanonical)

    def test_a_confirmed_init_states_each_warning_once_on_the_human_path(self) -> None:
        """`QA-014`/`D-182`: the review and the outcome are one run, not two reports.

        A confirmed action prints its review and then its result. Before this, every warning the
        review carried was printed again by the outcome, the outcome restated the review's own path
        count as `observed:`, and the first follow-up command re-listed every changed path. The
        `--json` envelope still carries the review and the outcome in full, so nothing was moved out
        of the record — only out of the second printing of it.
        """

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "registry"
            root.mkdir()
            _git(root, "init", "-q")

            code, output = _run(
                "registry",
                "init",
                "--source",
                str(root),
                "--source-id",
                "company-registry",
                "--display-name",
                "Company Registry",
                "--yes",
            )

            self.assertEqual(code, 0, output)
            warnings = [line for line in output.splitlines() if "warning:" in line]
            self.assertEqual(len(warnings), len(set(warnings)), output)
            self.assertTrue(warnings, output)
            self.assertEqual([line for line in output.splitlines() if "observed:" in line], [])
            self.assertNotIn("git -C", output)
            self.assertIn("review the working-tree diff afterward", output)
            self.assertIn("init: Changed 6 managed paths.", output)

    def test_a_retired_authoring_workspace_is_refused_by_name_without_mutation(self) -> None:
        """CP-26.5: the retired representation has no compiler left, so it is named, not read.

        `aart.lock.json`, `aart.index.json` and `entries/` were the authoring workspace's own files.
        Nothing writes them any more, so a checkout carrying them is a checkout someone else wrote;
        the read-only gates refuse it by path rather than compiling a catalog from it (`D-318`).
        """

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "registry"
            root.mkdir()
            _git(root, "init", "-q")
            self.assertEqual(
                _run(
                    "registry",
                    "init",
                    "--source",
                    str(root),
                    "--source-id",
                    "company-registry",
                    "--display-name",
                    "Company Registry",
                    "--yes",
                )[0],
                0,
            )
            (root / "entries/skill").mkdir(parents=True)
            (root / "entries/skill/code-review.json").write_text("{}\n", encoding="utf-8")
            (root / "aart.lock.json").write_text("{}\n", encoding="utf-8")

            before = _tree_bytes(root)
            for arguments in (("validate",), ("audit",)):
                code, output = _run("registry", *arguments, "--source", str(root), "--json")
                self.assertNotEqual(code, 0, output)
                self.assertIn("retired authoring-workspace", output)
                self.assertIn("aart.lock.json", output)
                self.assertIn("entries/skill/code-review.json", output)
                self.assertEqual(_tree_bytes(root), before)


if __name__ == "__main__":
    unittest.main()
