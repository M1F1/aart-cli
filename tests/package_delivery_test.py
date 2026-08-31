"""What a compiled package offers a harness: where inside its payload, and what is there.

The package half of a delivery. `_INSTALL_EFFECTS` already records what each kind is installed by
-- a Skill is a copy-tree, a guideline is a write-file -- and this reads the same fact back out of
a compiled package so the installing machine never has to consult the author's repository, which it
has not seen (D-056).

A guideline that carries more than one payload file is refused rather than resolved by picking one.
Two candidate files is an author saying something the format cannot express, and guessing which one
a harness should read would install a file nobody chose under a name it did not have.
"""

from __future__ import annotations

import unittest

from agent_artifacts.domain.artifacts import ArtifactKind
from agent_artifacts.domain.effects import DeliveryKind
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.protocol.authoring import package_delivery, package_merge
from agent_artifacts.protocol.hashing import sha256_bytes
from agent_artifacts.protocol.native_tree import SnapshotEntry, SnapshotEntryKind
from agent_artifacts.protocol.paths import parse_relative_path


def _entry(path: str, content: bytes = b"", *, directory: bool = False) -> SnapshotEntry:
    parsed = parse_relative_path(path)
    assert isinstance(parsed, Ok)
    kind = SnapshotEntryKind.DIRECTORY if directory else SnapshotEntryKind.FILE
    return SnapshotEntry(parsed.value, kind, content)


def _skill() -> tuple[SnapshotEntry, ...]:
    return (
        _entry("artifact.json", b"{}"),
        _entry("payload", directory=True),
        _entry("payload/SKILL.md", b"# review\n"),
        _entry("payload/reference.md", b"detail\n"),
    )


def _guideline() -> tuple[SnapshotEntry, ...]:
    return (
        _entry("artifact.json", b"{}"),
        _entry("payload", directory=True),
        _entry("payload/house-style.md", b"be kind\n"),
    )


class PackageDeliveryTest(unittest.TestCase):
    def test_a_skill_delivers_its_whole_payload_as_a_tree(self) -> None:
        offered = package_delivery(ArtifactKind.SKILL, _skill())
        assert isinstance(offered, Ok)
        self.assertEqual("", offered.value.source)
        self.assertEqual(DeliveryKind.TREE, offered.value.delivery)

    def test_a_guideline_delivers_the_one_file_it_carries(self) -> None:
        offered = package_delivery(ArtifactKind.GUIDELINE, _guideline())
        assert isinstance(offered, Ok)
        self.assertEqual("house-style.md", offered.value.source)
        self.assertEqual(DeliveryKind.FILE, offered.value.delivery)

    def test_the_digest_is_of_what_is_delivered_and_not_of_the_package(self) -> None:
        one = package_delivery(ArtifactKind.GUIDELINE, _guideline())
        other = package_delivery(
            ArtifactKind.GUIDELINE,
            (
                _entry("artifact.json", b"{'different': true}"),
                _entry("payload", directory=True),
                _entry("payload/house-style.md", b"be kind\n"),
            ),
        )
        assert isinstance(one, Ok) and isinstance(other, Ok)
        self.assertEqual(one.value.digest, other.value.digest)

    def test_a_changed_payload_changes_the_digest(self) -> None:
        one = package_delivery(ArtifactKind.SKILL, _skill())
        other = package_delivery(
            ArtifactKind.SKILL,
            (
                _entry("artifact.json", b"{}"),
                _entry("payload", directory=True),
                _entry("payload/SKILL.md", b"# review\n"),
                _entry("payload/reference.md", b"edited\n"),
            ),
        )
        assert isinstance(one, Ok) and isinstance(other, Ok)
        self.assertNotEqual(one.value.digest, other.value.digest)

    def test_a_guideline_with_two_payload_files_is_refused_not_resolved(self) -> None:
        entries = (*_guideline(), _entry("payload/other.md", b"also\n"))
        self.assertIsInstance(package_delivery(ArtifactKind.GUIDELINE, entries), Err)

    def test_a_guideline_with_no_payload_file_is_refused(self) -> None:
        entries = (_entry("artifact.json", b"{}"), _entry("payload", directory=True))
        self.assertIsInstance(package_delivery(ArtifactKind.GUIDELINE, entries), Err)

    def test_a_skill_with_an_empty_payload_is_refused(self) -> None:
        entries = (_entry("artifact.json", b"{}"), _entry("payload", directory=True))
        self.assertIsInstance(package_delivery(ArtifactKind.SKILL, entries), Err)

    def test_a_kind_that_starts_a_process_is_not_delivered(self) -> None:
        self.assertIsInstance(package_delivery(ArtifactKind.MCP, _skill()), Err)

    def test_a_kind_that_merges_into_a_file_it_does_not_own_is_not_delivered(self) -> None:
        for kind in (ArtifactKind.HOOK, ArtifactKind.MEMORY):
            self.assertIsInstance(package_delivery(kind, _skill()), Err)


if __name__ == "__main__":
    unittest.main()


def _memory() -> tuple[SnapshotEntry, ...]:
    return (
        _entry("artifact.json", b"{}"),
        _entry("payload", directory=True),
        _entry("payload/MEMORY.md", b"\nPrefer small pull requests.\n\n"),
    )


class PackageMergeTest(unittest.TestCase):
    """What a package offers a file the user owns: one body, and the digest of that body.

    A memory artifact is not delivered -- every measured target is a shared instruction file, so
    what is installed is a delimited region of it (B-034). The digest therefore covers the body as
    it will be stored in that region, not the file it goes into: digesting the file would report
    every note the user added to their own `CLAUDE.md` as drift in an unchanged artifact.
    """

    def test_a_memory_offers_the_one_file_it_carries(self) -> None:
        offered = package_merge(ArtifactKind.MEMORY, _memory())
        assert isinstance(offered, Ok)
        self.assertEqual("MEMORY.md", offered.value.source)

    def test_the_digest_covers_the_body_as_it_will_be_stored(self) -> None:
        offered = package_merge(ArtifactKind.MEMORY, _memory())
        assert isinstance(offered, Ok)
        self.assertEqual(sha256_bytes(b"Prefer small pull requests."), offered.value.digest)

    def test_the_same_body_with_different_surrounding_blank_lines_is_the_same_digest(self) -> None:
        padded = (
            _entry("artifact.json", b"{}"),
            _entry("payload", directory=True),
            _entry("payload/MEMORY.md", b"Prefer small pull requests."),
        )

        self.assertEqual(
            package_merge(ArtifactKind.MEMORY, _memory()).value.digest,  # type: ignore[union-attr]
            package_merge(ArtifactKind.MEMORY, padded).value.digest,  # type: ignore[union-attr]
        )

    def test_a_memory_carrying_two_files_is_refused_rather_than_picked_between(self) -> None:
        two = (*_memory(), _entry("payload/OTHER.md", b"else\n"))

        self.assertIsInstance(package_merge(ArtifactKind.MEMORY, two), Err)

    def test_a_memory_carrying_nothing_is_refused(self) -> None:
        self.assertIsInstance(
            package_merge(ArtifactKind.MEMORY, (_entry("artifact.json", b"{}"),)), Err
        )

    def test_a_body_that_is_not_text_is_refused_rather_than_written_into_the_users_file(
        self,
    ) -> None:
        binary = (
            _entry("artifact.json", b"{}"),
            _entry("payload", directory=True),
            _entry("payload/MEMORY.md", b"\xff\xfe\x00"),
        )

        self.assertIsInstance(package_merge(ArtifactKind.MEMORY, binary), Err)

    def test_a_body_carrying_a_managed_marker_is_refused(self) -> None:
        # Otherwise an artifact could close its own region early and take ownership of whatever the
        # user wrote after it.
        forged = (
            _entry("artifact.json", b"{}"),
            _entry("payload", directory=True),
            _entry("payload/MEMORY.md", b"<!-- <<< agent-artifacts memory:x <<< -->\n"),
        )

        self.assertIsInstance(package_merge(ArtifactKind.MEMORY, forged), Err)

    def test_a_skill_is_delivered_rather_than_merged(self) -> None:
        self.assertIsInstance(package_merge(ArtifactKind.SKILL, _skill()), Err)

    def test_a_memory_is_merged_rather_than_delivered(self) -> None:
        self.assertIsInstance(package_delivery(ArtifactKind.MEMORY, _memory()), Err)
