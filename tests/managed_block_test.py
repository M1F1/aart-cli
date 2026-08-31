"""A region of a file AART owns, inside a file it does not.

A Skill is delivered: AART writes the whole destination and owns every byte of it. A memory
artifact is not. Its body goes into `CLAUDE.md`, `TABNINE.md` or `AGENTS.md` -- files a person
writes in, edits and keeps notes in -- so installing one means owning a named region and leaving
everything around it exactly as it was. `DeliverArtifact` replaces its destination, which is why
using it here would delete the file it merged into (B-034).

The legacy engine already does this in two places with two different markers, and the semantics
here are the stronger half of each: the markdown-comment delimiters memory files use, refusing a
file that already holds two blocks for one name rather than picking one, and refusing a half-open
block rather than truncating the file from the opening marker -- which is what the legacy memory
path does, and it destroys everything the user wrote below it.
"""

from __future__ import annotations

import unittest

from agent_artifacts.domain.managed_blocks import (
    BlockPosition,
    managed_block,
    merge_managed_block,
    remove_managed_block,
)
from agent_artifacts.domain.result import Err, Ok

NAME = "house-style"
BODY = "Always name the failure.\n"
NOTES = "# My notes\n\nSomething I wrote.\n"


def _merged(existing: str = "", body: str = BODY, **kwargs) -> str:
    result = merge_managed_block(existing, NAME, body, **kwargs)
    assert isinstance(result, Ok), getattr(result, "diagnostics", ())
    return result.value


class ManagedBlockRenderingTest(unittest.TestCase):
    def test_the_block_is_delimited_by_markers_that_name_what_owns_it(self) -> None:
        block = managed_block(NAME, BODY)

        self.assertTrue(block.startswith("<!-- >>> agent-artifacts memory:house-style >>> -->\n"))
        self.assertTrue(block.endswith("\n<!-- <<< agent-artifacts memory:house-style <<< -->"))
        self.assertIn("Always name the failure.", block)

    def test_a_markdown_comment_is_invisible_to_the_harness_that_reads_the_file(self) -> None:
        """The harness reads this file as instructions. A marker it rendered as content would
        become part of what the agent is told."""

        self.assertIn("<!--", managed_block(NAME, BODY))
        self.assertNotIn("# ", managed_block(NAME, BODY).splitlines()[0])

    def test_the_body_is_carried_without_a_trailing_blank_line_of_its_own(self) -> None:
        self.assertEqual(managed_block(NAME, "one\n\n\n"), managed_block(NAME, "one"))


class ManagedBlockInsertionTest(unittest.TestCase):
    def test_an_empty_file_becomes_the_block_and_nothing_else(self) -> None:
        self.assertEqual(f"{managed_block(NAME, BODY)}\n", _merged(""))

    def test_what_the_user_wrote_survives_the_merge(self) -> None:
        merged = _merged(NOTES)

        self.assertIn("Something I wrote.", merged)
        self.assertIn(managed_block(NAME, BODY), merged)

    def test_appending_puts_the_block_after_what_was_there(self) -> None:
        merged = _merged(NOTES, position=BlockPosition.BOTTOM)

        self.assertLess(merged.index("Something I wrote."), merged.index("agent-artifacts"))

    def test_prepending_puts_the_block_before_what_was_there(self) -> None:
        merged = _merged(NOTES, position=BlockPosition.TOP)

        self.assertLess(merged.index("agent-artifacts"), merged.index("Something I wrote."))

    def test_a_file_with_no_final_newline_does_not_lose_its_last_line(self) -> None:
        merged = _merged("no trailing newline", position=BlockPosition.BOTTOM)

        self.assertIn("no trailing newline\n", merged)


class ManagedBlockReplacementTest(unittest.TestCase):
    def test_merging_again_replaces_the_region_rather_than_adding_a_second(self) -> None:
        once = _merged(NOTES)
        twice = merge_managed_block(once, NAME, "Different guidance.\n")

        assert isinstance(twice, Ok), getattr(twice, "diagnostics", ())
        self.assertEqual(1, twice.value.count("<!-- >>> agent-artifacts memory:house-style"))
        self.assertIn("Different guidance.", twice.value)
        self.assertNotIn("Always name the failure.", twice.value)

    def test_merging_the_same_body_twice_changes_nothing_at_all(self) -> None:
        """Reconciliation compares before it writes, so an unchanged merge has to be a no-op
        byte for byte -- otherwise every repair would report drift it created itself."""

        once = _merged(NOTES)
        twice = merge_managed_block(once, NAME, BODY)

        assert isinstance(twice, Ok)
        self.assertEqual(once, twice.value)

    def test_text_on_either_side_of_the_region_is_left_alone(self) -> None:
        base = _merged("# Top\n", position=BlockPosition.BOTTOM) + "\n# Bottom\n"
        replaced = merge_managed_block(base, NAME, "New.\n")

        assert isinstance(replaced, Ok), getattr(replaced, "diagnostics", ())
        self.assertIn("# Top", replaced.value)
        self.assertIn("# Bottom", replaced.value)

    def test_another_artifacts_block_in_the_same_file_is_untouched(self) -> None:
        base = _merged(NOTES)
        other = merge_managed_block(base, "other-memory", "Theirs.\n")
        assert isinstance(other, Ok), getattr(other, "diagnostics", ())

        mine = merge_managed_block(other.value, NAME, "Mine.\n")

        assert isinstance(mine, Ok), getattr(mine, "diagnostics", ())
        self.assertIn("Theirs.", mine.value)
        self.assertIn("Mine.", mine.value)


class ManagedBlockRefusalTest(unittest.TestCase):
    def test_a_file_holding_two_blocks_for_one_name_is_refused_not_guessed_at(self) -> None:
        doubled = _merged(NOTES) + "\n" + managed_block(NAME, "A second one.\n") + "\n"

        self.assertIsInstance(merge_managed_block(doubled, NAME, BODY), Err)

    def test_an_opening_marker_with_no_close_is_refused_rather_than_truncating(self) -> None:
        """The legacy path writes from the opening marker to the end of the file, which destroys
        everything the user wrote below a block somebody half-deleted."""

        damaged = "<!-- >>> agent-artifacts memory:house-style >>> -->\nbody\n" + NOTES

        merged = merge_managed_block(damaged, NAME, BODY)

        self.assertIsInstance(merged, Err)

    def test_a_body_carrying_the_marker_that_would_end_it_is_refused(self) -> None:
        """Otherwise the artifact chooses where AART's region stops, and everything after that
        marker becomes the user's text as far as a later withdrawal is concerned."""

        escaping = f"fine\n{managed_block(NAME, 'x')}\nnot fine\n"

        self.assertIsInstance(merge_managed_block("", NAME, escaping), Err)

    def test_a_name_that_would_not_survive_a_round_trip_is_refused(self) -> None:
        for name in ("", " ", "has space", "has\nnewline", "has>>>marker"):
            with self.subTest(name=name):
                self.assertIsInstance(merge_managed_block("", name, BODY), Err)


class ManagedBlockRemovalTest(unittest.TestCase):
    def test_removing_takes_the_region_and_leaves_the_file(self) -> None:
        merged = _merged(NOTES)

        removed = remove_managed_block(merged, NAME)

        assert isinstance(removed, Ok), getattr(removed, "diagnostics", ())
        self.assertNotIn("agent-artifacts", removed.value)
        self.assertIn("Something I wrote.", removed.value)

    def test_removing_what_was_never_there_leaves_the_file_exactly_as_it_was(self) -> None:
        removed = remove_managed_block(NOTES, NAME)

        assert isinstance(removed, Ok), getattr(removed, "diagnostics", ())
        self.assertEqual(NOTES, removed.value)

    def test_removing_the_only_content_leaves_an_empty_file_rather_than_a_stray_newline(
        self,
    ) -> None:
        removed = remove_managed_block(_merged(""), NAME)

        assert isinstance(removed, Ok), getattr(removed, "diagnostics", ())
        self.assertEqual("", removed.value)

    def test_removing_one_artifacts_block_leaves_anothers_standing(self) -> None:
        base = _merged(NOTES)
        other = merge_managed_block(base, "other-memory", "Theirs.\n")
        assert isinstance(other, Ok)

        removed = remove_managed_block(other.value, NAME)

        assert isinstance(removed, Ok), getattr(removed, "diagnostics", ())
        self.assertIn("Theirs.", removed.value)
        self.assertNotIn("Always name the failure.", removed.value)

    def test_a_file_holding_two_blocks_for_one_name_is_refused_here_too(self) -> None:
        doubled = _merged(NOTES) + "\n" + managed_block(NAME, "A second one.\n") + "\n"

        self.assertIsInstance(remove_managed_block(doubled, NAME), Err)


if __name__ == "__main__":
    unittest.main()
