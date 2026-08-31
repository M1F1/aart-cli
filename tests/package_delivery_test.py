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
from agent_artifacts.protocol.authoring import package_delivery
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
