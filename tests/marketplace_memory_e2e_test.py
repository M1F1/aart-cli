"""End-to-end proof that a memory installed from a Registry reaches the file the harness reads.

A memory is one managed block in the harness instruction file. These tests drive the real CLI over
a real project and assert the bytes on disk: the block is written, hand-written content around it
is kept, several memories share one file, and uninstall takes back exactly its own block.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.marketplace_lifecycle_e2e_test import _environment
from tests.reference_registry import (
    ESSENTIALS,
    memory,
    reference_snapshot,
    skill,
    write_reference_registry,
)

_MEMORY = "reference/memory/house@1.0.0"
_SENTINEL_OPEN = "<!-- >>> aart-cli memory:house >>> -->"


def _instruction_file(environment) -> Path:
    return environment.project / "CLAUDE.md"


class MemoryE2ETest(unittest.TestCase):
    def test_two_named_memories_share_one_tabnine_file_and_uninstall_independently(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            registry = write_reference_registry(
                Path(raw) / "registry",
                reference_snapshot(
                    skill(),
                    memory(),
                    memory("rules", "# Testing rules\n\nRun tests twice.\n"),
                    ESSENTIALS,
                ),
            )

            with _environment(registry) as environment:
                for coordinate in ("reference/memory/house@1.0.0", "reference/memory/rules@1.0.0"):
                    code, payload = environment.run(
                        "consume", "install", coordinate, "--profile", "tabnine", "--yes"
                    )
                    self.assertEqual(code, 0, payload)
                destination = environment.project / "TABNINE.md"
                rendered = destination.read_text()
                self.assertIn("memory:house", rendered)
                self.assertIn("memory:rules", rendered)
                status, status_payload = environment.run(
                    "consume", "status", "--profile", "tabnine"
                )
                self.assertEqual(status, 0, status_payload)
                self.assertEqual({item["status"] for item in status_payload["items"]}, {"current"})

                removed, removed_payload = environment.run(
                    "consume",
                    "uninstall",
                    "reference/memory/house",
                    "--profile",
                    "tabnine",
                    "--yes",
                )
                self.assertEqual(removed, 0, removed_payload)
                rendered = destination.read_text()
                self.assertNotIn("memory:house", rendered)
                self.assertIn("memory:rules", rendered)

                last, last_payload = environment.run(
                    "consume",
                    "uninstall",
                    "reference/memory/rules",
                    "--profile",
                    "tabnine",
                    "--yes",
                )
                self.assertEqual(last, 0, last_payload)
                # The file AART created stays behind empty for now (B-204).
                self.assertNotIn("aart-cli memory:", destination.read_text())

    def test_a_memory_writes_the_managed_block_into_a_fresh_file(self) -> None:
        with _environment() as environment:
            destination = _instruction_file(environment)

            code, payload = environment.run(
                "consume", "install", _MEMORY, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, payload)
            self.assertIn(_SENTINEL_OPEN, destination.read_text(encoding="utf-8"))

    def test_hand_written_content_stays_and_uninstall_restores_it_exactly(self) -> None:
        with _environment() as environment:
            destination = _instruction_file(environment)
            original = "# Existing\n\nHand-written guidance.\n"
            destination.write_text(original, encoding="utf-8")

            code, payload = environment.run(
                "consume", "install", _MEMORY, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, payload)
            rendered = destination.read_text(encoding="utf-8")
            self.assertTrue(rendered.startswith(original), rendered)
            self.assertIn(_SENTINEL_OPEN, rendered)

            code, payload = environment.run(
                "consume", "uninstall", _MEMORY, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, payload)
            self.assertEqual(destination.read_text(encoding="utf-8"), original)

    def test_review_without_yes_writes_no_instruction_file(self) -> None:
        with _environment() as environment:
            destination = _instruction_file(environment)

            code, payload = environment.run("consume", "install", _MEMORY, "--profile", "claude")

            self.assertEqual(code, 0, payload)
            self.assertFalse(destination.exists(), "review must not create the destination")


if __name__ == "__main__":
    unittest.main()
