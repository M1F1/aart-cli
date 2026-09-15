"""The adapter that writes one artifact's region into a file the user owns.

The destination is not AART's, so this interpreter cannot prove ownership structurally the way the
file interpreter does. It proves it the way the delivery and harness interpreters do (D-072): it is
handed the merges it may make, and a region it was not given is refused rather than written.

What the tests here are really about is everything the interpreter must not do to a file it does
not own -- change its permissions, follow a symlink out of the tree, take away the user's own
writing, or improvise when the markers are damaged.
"""

from __future__ import annotations

import os
import pathlib
import tempfile
import unittest

from agent_artifacts.domain.effects import (
    DeliverArtifact,
    DeliveryKind,
    MergeManagedBlock,
    UnmergeManagedBlock,
)
from agent_artifacts.domain.managed_blocks import BlockPosition, managed_block_body
from agent_artifacts.domain.receipts import ArtifactMerge
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.execution import ManagedBlockInterpreter
from agent_artifacts.protocol.hashing import sha256_bytes

ARTIFACT = "company/memory/house-style"
REGION = "house-style"
BODY = "Prefer small pull requests.\n"


class ManagedBlockInterpreterTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = pathlib.Path(self._temporary.name)
        self.source = self.root / "artifact/payload/MEMORY.md"
        self.source.parent.mkdir(parents=True)
        self.source.write_text(BODY, encoding="utf-8")
        self.destination = self.root / "project/CLAUDE.md"
        self.destination.parent.mkdir(parents=True)
        self.merge = ArtifactMerge(
            "claude",
            str(self.source),
            str(self.destination),
            REGION,
            sha256_bytes(BODY.strip().encode("utf-8")),
        )
        self.interpreter = ManagedBlockInterpreter(ARTIFACT, (self.merge,))

    def _merge(self, **overrides) -> MergeManagedBlock:
        values = {
            "harness": "claude",
            "artifact": ARTIFACT,
            "destination": str(self.destination),
            "region": REGION,
            "source": str(self.source),
            "position": BlockPosition.BOTTOM,
        }
        values.update(overrides)
        return MergeManagedBlock(**values)

    def test_it_writes_the_region_into_a_file_that_does_not_exist_yet(self) -> None:
        applied = self.interpreter.apply(self._merge())

        self.assertIsInstance(applied, Ok)
        self.assertEqual(
            managed_block_body(self.destination.read_text(encoding="utf-8"), REGION).value,
            BODY.strip(),
        )

    def test_what_the_user_wrote_survives(self) -> None:
        self.destination.write_text("# Our conventions\n\nNever force-push main.\n", "utf-8")

        self.interpreter.apply(self._merge())

        self.assertIn("Never force-push main.", self.destination.read_text(encoding="utf-8"))

    def test_the_users_permissions_on_their_own_file_are_left_alone(self) -> None:
        self.destination.write_text("Mine.\n", encoding="utf-8")
        os.chmod(self.destination, 0o644)

        self.interpreter.apply(self._merge())

        self.assertEqual(0o644, os.stat(self.destination).st_mode & 0o777)

    def test_applying_twice_leaves_one_block(self) -> None:
        self.interpreter.apply(self._merge())
        first = self.destination.read_text(encoding="utf-8")

        self.interpreter.apply(self._merge())

        self.assertEqual(first, self.destination.read_text(encoding="utf-8"))

    def test_a_region_this_interpreter_was_not_given_is_refused(self) -> None:
        applied = self.interpreter.apply(self._merge(region="something-else"))

        self.assertIsInstance(applied, Err)
        self.assertFalse(self.destination.exists())

    def test_a_destination_this_interpreter_was_not_given_is_refused(self) -> None:
        elsewhere = self.root / "project/AGENTS.md"

        applied = self.interpreter.apply(self._merge(destination=str(elsewhere)))

        self.assertIsInstance(applied, Err)
        self.assertFalse(elsewhere.exists())

    def test_another_artifacts_merge_is_refused(self) -> None:
        applied = self.interpreter.apply(self._merge(artifact="company/memory/other"))

        self.assertIsInstance(applied, Err)

    def test_a_delivery_is_not_a_merge(self) -> None:
        effect = DeliverArtifact(
            "claude", ARTIFACT, str(self.source), str(self.destination), DeliveryKind.FILE
        )

        self.assertFalse(self.interpreter.supports(effect))
        self.assertIsInstance(self.interpreter.apply(effect), Err)

    def test_a_source_that_is_not_there_leaves_the_file_as_it_was(self) -> None:
        self.destination.write_text("Mine.\n", encoding="utf-8")
        self.source.unlink()

        applied = self.interpreter.apply(self._merge())

        self.assertIsInstance(applied, Err)
        self.assertEqual("Mine.\n", self.destination.read_text(encoding="utf-8"))

    def test_a_destination_that_is_not_text_is_refused_rather_than_overwritten(self) -> None:
        self.destination.write_bytes(b"\xff\xfe\x00binary")

        applied = self.interpreter.apply(self._merge())

        self.assertIsInstance(applied, Err)
        self.assertEqual(b"\xff\xfe\x00binary", self.destination.read_bytes())

    def test_a_damaged_region_is_refused_rather_than_rewritten(self) -> None:
        self.destination.write_text(
            "Mine.\n<!-- >>> agent-artifacts memory:house-style >>> -->\nstill mine\n", "utf-8"
        )
        before = self.destination.read_text(encoding="utf-8")

        applied = self.interpreter.apply(self._merge())

        self.assertIsInstance(applied, Err)
        self.assertEqual(before, self.destination.read_text(encoding="utf-8"))

    def test_a_symlinked_destination_is_refused_rather_than_followed(self) -> None:
        # D-078: an installation writes inside the tree it was given. Replacing a symlink would
        # either write through it into somewhere nobody reviewed, or silently unlink the user's
        # own arrangement.
        real = self.root / "elsewhere/NOTES.md"
        real.parent.mkdir()
        real.write_text("Somewhere else.\n", encoding="utf-8")
        self.destination.symlink_to(real)

        applied = self.interpreter.apply(self._merge())

        self.assertIsInstance(applied, Err)
        self.assertEqual("Somewhere else.\n", real.read_text(encoding="utf-8"))

    def test_a_directory_where_the_file_should_be_is_refused(self) -> None:
        self.destination.mkdir()

        self.assertIsInstance(self.interpreter.apply(self._merge()), Err)


class UnmergeManagedBlockTest(ManagedBlockInterpreterTest):
    def _unmerge(self, **overrides) -> UnmergeManagedBlock:
        values = {
            "harness": "claude",
            "artifact": ARTIFACT,
            "destination": str(self.destination),
            "region": REGION,
        }
        values.update(overrides)
        return UnmergeManagedBlock(**values)

    def test_withdrawal_takes_the_region_and_leaves_the_file(self) -> None:
        self.destination.write_text("Never force-push main.\n", encoding="utf-8")
        self.interpreter.apply(self._merge())

        applied = self.interpreter.apply(self._unmerge())

        self.assertIsInstance(applied, Ok)
        self.assertTrue(self.destination.exists(), "removing a block removed the user's file")
        text = self.destination.read_text(encoding="utf-8")
        self.assertIsNone(managed_block_body(text, REGION).value)
        self.assertIn("Never force-push main.", text)

    def test_withdrawing_a_region_that_is_not_there_converges(self) -> None:
        self.destination.write_text("Never force-push main.\n", encoding="utf-8")

        applied = self.interpreter.apply(self._unmerge())

        self.assertIsInstance(applied, Ok)
        self.assertEqual("Never force-push main.\n", self.destination.read_text(encoding="utf-8"))

    def test_withdrawing_from_a_file_that_is_gone_converges(self) -> None:
        self.assertIsInstance(self.interpreter.apply(self._unmerge()), Ok)

    def test_a_region_this_interpreter_was_not_given_is_refused_on_the_way_out_too(self) -> None:
        self.destination.write_text("Mine.\n", encoding="utf-8")

        applied = self.interpreter.apply(self._unmerge(region="something-else"))

        self.assertIsInstance(applied, Err)


if __name__ == "__main__":
    unittest.main()
