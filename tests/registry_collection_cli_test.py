"""`registry scan` and `registry promote` carry Collection Candidates (§173.3, D-427).

The CLI route compiles a Source the way Source Sync does, so a Collection authored beside its
members is a Candidate there too: listed by `scan`, approved by `promote` with its ID, and refused,
naming the member, while the Registry has not approved what it lists.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aart_cli import cli
from aart_cli.application.promotion import load_registry_versions
from aart_cli.application.registry_collections import read_registry_collection
from aart_cli.domain.result import Ok
from aart_cli.io.registry_promotion import FilesystemPromotionOutput

_SOURCE = (
    "--source-alias",
    "authors",
    "--source-url",
    "https://git.example.test/authors.git",
    "--target-registry",
    "company",
)

_MEMBER = {
    "schema": "aart-cli.dev/mcp/v1",
    "artifact": {"name": "github-mcp", "kind": "mcp", "summary": "GitHub MCP server."},
    "payload": {"include": ["server.py"]},
    "transport": {"type": "stdio"},
    "runtime": {"type": "python", "version": ">=3.11"},
    "launch": {"type": "python", "entrypoint": "server.py"},
}

_COLLECTION = {
    "schema": "aart-cli.dev/collection/v1",
    "name": "data-engineer",
    "summary": "Approved data engineering tools.",
    "artifacts": ["mcp/github-mcp@^1"],
}


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", "-C", str(root), *arguments), check=True, capture_output=True, text=True
    ).stdout.strip()


def _cli(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


class RegistryCollectionCliTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name).resolve()
        home, self.author, self.registry = (root / name for name in ("home", "author", "reg"))
        for path in (home, self.author / "gh", self.author / "collections" / "data-engineer"):
            path.mkdir(parents=True)
        self.registry.mkdir()
        patcher = mock.patch.dict(
            os.environ,
            {
                "AART_CLI_HOME": str(home / ".aart-cli"),
                "HOME": str(home),
                "GIT_AUTHOR_NAME": "AART Test",
                "GIT_AUTHOR_EMAIL": "aart@example.invalid",
                "GIT_COMMITTER_NAME": "AART Test",
                "GIT_COMMITTER_EMAIL": "aart@example.invalid",
                "XDG_CONFIG_HOME": str(home / ".config"),
                "XDG_DATA_HOME": str(home / ".local" / "share"),
            },
            clear=False,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        _git(self.author, "init", "-q", "-b", "main")
        (self.author / "gh" / "aart-cli.json").write_text(json.dumps(_MEMBER), encoding="utf-8")
        (self.author / "gh" / "server.py").write_text("print('v1')\n", encoding="utf-8")
        (self.author / "collections" / "data-engineer" / "aart-cli.json").write_text(
            json.dumps(_COLLECTION), encoding="utf-8"
        )
        _git(self.author, "add", "-A")
        _git(self.author, "commit", "-qm", "v1")
        _git(self.registry, "init", "-q", "-b", "main")
        code, said = _cli(
            "registry",
            "init",
            "--source",
            str(self.registry),
            "--source-id",
            "company",
            "--display-name",
            "Company",
            "--yes",
        )
        self.assertEqual(code, 0, said)
        self.common = (
            "--source",
            str(self.registry),
            "--checkout",
            str(self.author),
            *_SOURCE,
        )

    def _scan(self) -> dict:
        code, said = _cli("registry", "scan", *self.common, "--json")
        self.assertEqual(code, 0, said)
        return json.loads(said)

    def test_scan_lists_the_collection_and_names_its_unapproved_member(self) -> None:
        (collection,) = self._scan()["collections"]

        self.assertEqual(collection["coordinate"], "company/collection/data-engineer@1.0.0")
        self.assertEqual(collection["state"], "invalid")
        self.assertEqual(
            collection["findings"],
            ["member mcp/github-mcp@^1 matches no approved version in company"],
        )

    def test_promoting_it_before_its_member_is_refused_naming_the_member(self) -> None:
        (collection,) = self._scan()["collections"]

        code, said = _cli(
            "registry", "promote", *self.common, "--candidate", collection["candidate_id"], "--yes"
        )

        self.assertNotEqual(code, 0, said)
        self.assertIn("mcp/github-mcp@^1 matches no approved version in company", said)
        self.assertFalse((self.registry / "artifacts" / "collection").exists())

    def test_once_its_member_is_approved_it_is_promoted_and_read_back(self) -> None:
        (member,) = self._scan()["candidates"]
        code, said = _cli(
            "registry", "promote", *self.common, "--candidate", member["candidate_id"], "--yes"
        )
        self.assertEqual(code, 0, said)
        (collection,) = self._scan()["collections"]
        self.assertEqual(collection["state"], "ready")

        code, said = _cli(
            "registry", "promote", *self.common, "--candidate", collection["candidate_id"], "--yes"
        )

        self.assertEqual(code, 0, said)
        persisted = FilesystemPromotionOutput(str(self.registry)).current()
        assert isinstance(persisted, Ok), persisted
        versions = load_registry_versions(persisted.value)
        assert isinstance(versions, Ok), versions
        published = next(
            item for item in versions.value if item.coordinate.artifact.kind == "collection"
        )
        read = read_registry_collection(persisted.value, published)
        assert isinstance(read, Ok), read
        self.assertEqual(str(read.value.coordinate), "company/collection/data-engineer@1.0.0")
        self.assertEqual([str(item.request) for item in read.value.members], ["mcp/github-mcp@^1"])


if __name__ == "__main__":
    unittest.main()
