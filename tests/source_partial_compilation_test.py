"""One malformed manifest is one refused manifest, not a refused Source (`QA-063`)."""

from __future__ import annotations

import json
import unittest

from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.protocol.authoring import (
    compile_author_manifests,
    compile_author_snapshot,
)
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
)
from agent_artifacts.protocol.paths import parse_relative_path

_SOURCE = "https://git.example/authors.git"
_REVISION = "a" * 40


def _entry(path: str, content: str) -> SnapshotEntry:
    parsed = parse_relative_path(path)
    assert isinstance(parsed, Ok)
    return SnapshotEntry(parsed.value, SnapshotEntryKind.FILE, content.encode())


def _manifest(name: str, version: str) -> str:
    return json.dumps(
        {
            "schema": "aart.dev/mcp/v1",
            "artifact": {"name": name, "kind": "mcp", "version": version},
            "payload": {"include": ["server.py"]},
            "transport": {"type": "stdio"},
            "runtime": {"type": "python", "version": ">=3.11"},
            "launch": {"type": "python", "entrypoint": "server.py"},
        },
        indent=2,
    )


def _snapshot(*directories: tuple[str, str]) -> SourceSnapshot:
    entries = []
    for name, version in directories:
        entries.append(_entry(f"{name}/aart.json", _manifest(f"{name}-mcp", version)))
        entries.append(_entry(f"{name}/server.py", f"print({name!r})\n"))
    return SourceSnapshot(SnapshotOrigin.IMMUTABLE_GIT, tuple(entries))


def _compiled(snapshot: SourceSnapshot):
    return compile_author_manifests(
        snapshot, source_alias=SourceAlias("authors"), source=_SOURCE, revision=_REVISION
    )


class _Compiled:
    """The pair `compile_author_manifests` answers with, named so the tests read as prose."""

    def __init__(self, value) -> None:
        self.artifacts, self.refusals = value


class SourcePartialCompilationTest(unittest.TestCase):
    """`QA-063`: `artifact.version: not-a-version` in one manifest failed the entire Sync.

    `CandidateState.INVALID` exists so that a bad artifact can be reported as a bad Candidate.
    A Source-wide abort spends it: the operator learns that something somewhere is malformed, every
    healthy artifact beside it goes unscanned, and the message names no manifest.
    """

    def test_a_neighbour_of_a_malformed_manifest_still_compiles(self) -> None:
        compiled = _compiled(_snapshot(("good", "1.0.0"), ("bad", "not-a-version")))

        self.assertIsInstance(compiled, Ok, getattr(compiled, "diagnostics", ()))
        self.assertEqual(
            ["good-mcp"],
            [item.package.coordinate.artifact.name for item in _Compiled(compiled.value).artifacts],
        )

    def test_the_malformed_manifest_is_reported_as_a_refusal_that_names_its_path(self) -> None:
        """The operator has to know which file to open; `bad SemVer` alone names nothing."""

        compiled = _compiled(_snapshot(("good", "1.0.0"), ("bad", "not-a-version")))

        self.assertIsInstance(compiled, Ok, getattr(compiled, "diagnostics", ()))
        self.assertEqual(
            ["bad/aart.json"],
            [str(item.manifest_path) for item in _Compiled(compiled.value).refusals],
        )
        refusal = _Compiled(compiled.value).refusals[0]
        self.assertTrue(refusal.diagnostics)
        self.assertIn("not-a-version", refusal.diagnostics[0].message)

    def test_a_source_whose_every_manifest_is_malformed_compiles_nothing_and_refuses_each(
        self,
    ) -> None:
        """Nothing usable is still an answer about each manifest, not one about the Source."""

        compiled = _compiled(_snapshot(("first", "nope"), ("second", "also-nope")))

        self.assertIsInstance(compiled, Ok, getattr(compiled, "diagnostics", ()))
        self.assertEqual((), _Compiled(compiled.value).artifacts)
        self.assertEqual(
            ["first/aart.json", "second/aart.json"],
            sorted(str(item.manifest_path) for item in _Compiled(compiled.value).refusals),
        )

    def test_a_manifest_whose_schema_cannot_be_read_is_refused_rather_than_skipped(self) -> None:
        """A Collection manifest is not this compiler's; an unreadable one is not the same thing.

        Both leave the artifact list unchanged, which is why they are easy to conflate. Skipping
        the second loses the manifest without a word -- exactly the silence `QA-063` is about,
        moved one step earlier.
        """

        unreadable = SourceSnapshot(
            SnapshotOrigin.IMMUTABLE_GIT,
            (
                _entry("good/aart.json", _manifest("good-mcp", "1.0.0")),
                _entry("good/server.py", "print('good')\n"),
                _entry("odd/aart.json", json.dumps({"artifact": {"name": "odd"}}, indent=2)),
            ),
        )

        compiled = _compiled(unreadable)

        self.assertIsInstance(compiled, Ok, getattr(compiled, "diagnostics", ()))
        answer = _Compiled(compiled.value)
        self.assertEqual(
            ["good-mcp"], [item.package.coordinate.artifact.name for item in answer.artifacts]
        )
        self.assertEqual(["odd/aart.json"], [str(item.manifest_path) for item in answer.refusals])

    def test_a_healthy_source_refuses_nothing(self) -> None:
        compiled = _compiled(_snapshot(("good", "1.0.0"), ("other", "2.1.0")))

        self.assertIsInstance(compiled, Ok, getattr(compiled, "diagnostics", ()))
        self.assertEqual((), _Compiled(compiled.value).refusals)
        self.assertEqual(2, len(_Compiled(compiled.value).artifacts))

    def test_a_snapshot_that_is_not_a_source_at_all_still_refuses_outright(self) -> None:
        """Per-manifest tolerance is about manifests. A broken Source is still a broken Source.

        A duplicated path is a fault in the tree rather than in any one manifest -- there is no
        manifest to attribute it to -- so it stays a refusal of the whole compilation.
        """

        duplicated = SourceSnapshot(
            SnapshotOrigin.IMMUTABLE_GIT,
            (
                _entry("good/aart.json", _manifest("good-mcp", "1.0.0")),
                _entry("good/aart.json", _manifest("good-mcp", "1.0.0")),
            ),
        )

        broken = _compiled(duplicated)

        self.assertIsInstance(broken, Err)

    def test_publishing_and_adoption_keep_the_strict_answer(self) -> None:
        """`compile_author_snapshot` is what vendors and adopts, and there a refusal is fatal.

        Tolerating a malformed manifest will be right while watching a Source somebody else edits.
        It is wrong when the result is written into a registry, so that caller refuses whole -- and
        for now `compile_author_source` does too, because nothing downstream can yet carry a
        refusal and dropping one silently would be worse than the fault `QA-063` names.
        """

        strict = compile_author_snapshot(
            _snapshot(("good", "1.0.0"), ("bad", "not-a-version")),
            source_alias=SourceAlias("authors"),
            source=_SOURCE,
            revision=_REVISION,
        )

        self.assertIsInstance(strict, Err)
        self.assertIn("not-a-version", strict.diagnostics[0].message)


if __name__ == "__main__":
    unittest.main()
