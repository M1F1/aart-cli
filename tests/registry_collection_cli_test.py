"""`registry collection` defines a Collection from approved artifacts (§173.3, D-430, INV-266).

The Registry owns Collections. The command pins each named member at its highest approved version
and publishes the Collection's next version in one reviewed transaction: it only reviews without
`--yes`. Promoting a newer version of a member publishes the Collection's next version with it.
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
        for path in (home, self.author / "gh"):
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
        _git(self.author, "add", "-A")
        _git(self.author, "commit", "-qm", "v1")
        _git(self.registry, "init", "-q", "-b", "main")
        code, said = _cli(
            "maintain",
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
        code, said = _cli("maintain", "upstream", "scan", *self.common, "--json")
        self.assertEqual(code, 0, said)
        return json.loads(said)

    def _promote_member(self, *flags: str) -> tuple[int, str]:
        (member,) = self._scan()["candidates"]
        return _cli(
            "maintain",
            "candidate",
            "promote",
            *self.common,
            "--candidate",
            member["candidate_id"],
            *flags,
        )

    def _collection(self, *flags: str, summary: str | None = "Approved data engineering tools."):
        return _cli(
            "maintain",
            "registry",
            "collection",
            "--source",
            str(self.registry),
            "data-engineer",
            *(() if summary is None else ("--summary", summary)),
            "--include",
            "mcp/github-mcp",
            *flags,
        )

    def _published(self) -> dict[str, list[str]]:
        persisted = FilesystemPromotionOutput(str(self.registry)).current()
        assert isinstance(persisted, Ok), persisted
        versions = load_registry_versions(persisted.value)
        assert isinstance(versions, Ok), versions
        published = {}
        for item in versions.value:
            if item.coordinate.artifact.kind != "collection":
                continue
            read = read_registry_collection(persisted.value, item)
            assert isinstance(read, Ok), read
            published[str(read.value.coordinate)] = [
                str(member.request) for member in read.value.members
            ]
        return published

    def _change_member(self) -> None:
        (self.author / "gh" / "server.py").write_text("print('v2')\n", encoding="utf-8")
        _git(self.author, "commit", "-qam", "v2")

    def test_without_yes_it_reviews_the_pinned_members_and_writes_nothing(self) -> None:
        self.assertEqual(self._promote_member("--yes")[0], 0)

        code, said = self._collection("--json")

        self.assertEqual(code, 0, said)
        review = json.loads(said)
        self.assertEqual(review["phase"], "review")
        self.assertEqual(review["collection"], "company/collection/data-engineer@1.0.0")
        self.assertEqual(review["members"], ["mcp/github-mcp@1.0.0"])
        self.assertEqual(self._published(), {})

    def test_with_yes_it_publishes_the_collection_and_the_registry_reads_it_back(self) -> None:
        self.assertEqual(self._promote_member("--yes")[0], 0)

        code, said = self._collection("--yes")

        self.assertEqual(code, 0, said)
        self.assertIn("Published company/collection/data-engineer@1.0.0 locally", said)
        self.assertEqual(
            self._published(),
            {"company/collection/data-engineer@1.0.0": ["mcp/github-mcp@1.0.0"]},
        )

    def test_a_published_collection_passes_the_registry_s_own_checks(self) -> None:
        self.assertEqual(self._promote_member("--yes")[0], 0)
        self.assertEqual(self._collection("--yes")[0], 0)

        # The same gates the generated Registry CI runs; each one compiled the Collection's version
        # as a native package and refused it for having no artifact.json (D-473).
        for action in (("validate",), ("audit",), ("build", "--check"), ("format", "--check")):
            code, said = _cli("maintain", "registry", *action, "--source", str(self.registry))
            self.assertEqual(code, 0, f"{action}: {said}")

    def test_a_member_the_registry_has_not_approved_is_refused_by_name(self) -> None:
        self.assertEqual(self._promote_member("--yes")[0], 0)

        code, said = _cli(
            "maintain",
            "registry",
            "collection",
            "--source",
            str(self.registry),
            "data-engineer",
            "--summary",
            "Tools.",
            "--include",
            "mcp/github-mcp",
            "--include",
            "skill/absent",
            "--yes",
        )

        self.assertNotEqual(code, 0, said)
        self.assertIn("skill/absent has no approved version in company", said)
        self.assertEqual(self._published(), {})

    def test_the_same_definition_again_publishes_nothing(self) -> None:
        self.assertEqual(self._promote_member("--yes")[0], 0)
        self.assertEqual(self._collection("--yes")[0], 0)

        code, said = self._collection("--yes", summary=None)

        self.assertEqual(code, 0, said)
        self.assertIn("nothing to publish", said)
        self.assertEqual(list(self._published()), ["company/collection/data-engineer@1.0.0"])

    def test_promoting_a_member_s_new_version_reviews_and_publishes_the_collection_bump(
        self,
    ) -> None:
        self.assertEqual(self._promote_member("--yes")[0], 0)
        self.assertEqual(self._collection("--yes")[0], 0)
        self._change_member()

        code, said = self._promote_member("--json")
        self.assertEqual(code, 0, said)
        self.assertEqual(
            json.loads(said)["collections"], ["company/collection/data-engineer@1.0.1"]
        )
        code, said = self._promote_member("--yes")

        self.assertEqual(code, 0, said)
        self.assertEqual(
            self._published(),
            {
                "company/collection/data-engineer@1.0.0": ["mcp/github-mcp@1.0.0"],
                "company/collection/data-engineer@1.0.1": ["mcp/github-mcp@1.0.1"],
            },
        )


if __name__ == "__main__":
    unittest.main()
