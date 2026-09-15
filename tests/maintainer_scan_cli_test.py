"""Public CP-05 maintainer Source Scan over a pinned local Git checkout."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from agent_artifacts import cli


def _git(root: Path, *arguments: str) -> None:
    completed = subprocess.run(
        ("git", "-C", str(root), *arguments),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr)


def _author_checkout(root: Path) -> None:
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "AART Test")
    _git(root, "config", "user.email", "aart@example.invalid")
    package = root / "github"
    package.mkdir()
    manifest = {
        "schema": "aart.dev/mcp/v1",
        "artifact": {"name": "github-mcp", "kind": "mcp", "version": "1.0.0"},
        "payload": {"include": ["server.py"]},
        "transport": {"type": "stdio"},
        "runtime": {"type": "python", "version": ">=3.11"},
        "launch": {"type": "python", "entrypoint": "server.py"},
    }
    (package / "aart.json").write_text(json.dumps(manifest), encoding="utf-8")
    (package / "server.py").write_text("print('ready')\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "author artifact")


class MaintainerScanCliTest(unittest.TestCase):
    def test_parser_maps_explicit_scan_boundaries(self) -> None:
        request = cli._to_request(
            cli.build_parser().parse_args(
                [
                    "registry",
                    "scan",
                    "--checkout",
                    "/tmp/authors",
                    "--source-alias",
                    "authors",
                    "--source-url",
                    "https://git.example/authors.git",
                    "--target-registry",
                    "company",
                ]
            )
        )

        self.assertEqual(request.registry_action, "scan")
        self.assertEqual(request.candidate_checkout, "/tmp/authors")
        self.assertEqual(request.candidate_source_alias, "authors")
        self.assertEqual(request.candidate_source_url, "https://git.example/authors.git")
        self.assertEqual(request.target_registry_alias, "company")

    def test_scan_reports_candidates_and_does_not_mutate_the_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _author_checkout(root)
            before = subprocess.run(
                ("git", "-C", str(root), "status", "--porcelain"),
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                status = cli.main(
                    [
                        "registry",
                        "scan",
                        "--checkout",
                        str(root),
                        "--source-alias",
                        "authors",
                        "--source-url",
                        "https://git.example/authors.git",
                        "--target-registry",
                        "company",
                        "--json",
                    ]
                )

            payload = json.loads(output.getvalue())
            self.assertEqual(status, 0)
            self.assertEqual(payload["operation"], "registry.scan")
            self.assertEqual(payload["manifest_count"], 1)
            self.assertEqual(payload["registry_mutations"], 0)
            self.assertEqual(payload["candidates"][0]["state"], "new")
            self.assertEqual(payload["candidates"][0]["coordinate"], "authors/mcp/github-mcp@1.0.0")
            after = subprocess.run(
                ("git", "-C", str(root), "status", "--porcelain"),
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            self.assertEqual(before, after)

    def test_scan_refuses_an_uncommitted_source_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _author_checkout(root)
            (root / "github" / "server.py").write_text("print('dirty')\n", encoding="utf-8")
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                status = cli.main(
                    [
                        "registry",
                        "scan",
                        "--checkout",
                        str(root),
                        "--source-alias",
                        "authors",
                        "--source-url",
                        "https://git.example/authors.git",
                        "--target-registry",
                        "company",
                    ]
                )

            self.assertNotEqual(status, 0)
            self.assertIn("clean pinned Git checkout", output.getvalue())

    def test_explicit_candidate_promotion_reviews_then_applies_locally_without_commit_or_push(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            author = root / "author"
            registry = root / "registry"
            author.mkdir()
            registry.mkdir()
            _author_checkout(author)
            _git(registry, "init", "-q")
            scan_output = io.StringIO()
            common = [
                "--source",
                str(registry),
                "--checkout",
                str(author),
                "--source-alias",
                "authors",
                "--source-url",
                "https://git.example/authors.git",
                "--target-registry",
                "company",
            ]
            with contextlib.redirect_stdout(scan_output):
                scan_status = cli.main(["registry", "scan", *common, "--json"])
            self.assertEqual(scan_status, 0)
            candidate_id = json.loads(scan_output.getvalue())["candidates"][0]["candidate_id"]
            promote = [
                "registry",
                "promote",
                *common,
                "--candidate",
                candidate_id,
                "--validation-report",
                "sha256:" + "7" * 64,
                "--policy-result",
                "sha256:" + "8" * 64,
                "--json",
            ]
            review_output = io.StringIO()

            with contextlib.redirect_stdout(review_output):
                review_status = cli.main(promote)

            review = json.loads(review_output.getvalue())
            self.assertEqual(review_status, 0)
            self.assertEqual(review["phase"], "review")
            self.assertFalse(review["applied"])
            self.assertFalse(review["commit"])
            self.assertFalse(review["push"])
            self.assertFalse((registry / "artifacts").exists())
            apply_output = io.StringIO()

            with contextlib.redirect_stdout(apply_output):
                apply_status = cli.main([*promote, "--yes"])

            applied = json.loads(apply_output.getvalue())
            self.assertEqual(apply_status, 0)
            self.assertEqual(applied["phase"], "promoted-local")
            self.assertTrue(applied["applied"])
            self.assertFalse(applied["commit"])
            self.assertFalse(applied["push"])
            self.assertTrue(
                (registry / "artifacts/mcp/github-mcp/1.0.0/payload/server.py").is_file()
            )
            status = subprocess.run(
                ("git", "-C", str(registry), "status", "--porcelain"),
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            self.assertIn("?? artifacts/", status)
            rescanned_output = io.StringIO()
            with contextlib.redirect_stdout(rescanned_output):
                rescanned_status = cli.main(["registry", "scan", *common, "--json"])
            self.assertEqual(rescanned_status, 0)
            self.assertEqual(
                json.loads(rescanned_output.getvalue())["candidates"][0]["state"],
                "promoted",
            )


if __name__ == "__main__":
    unittest.main()
