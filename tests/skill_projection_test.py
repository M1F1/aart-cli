"""A canonical Skill becomes the private document a harness can discover."""

from __future__ import annotations

import unittest

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from aart_cli.application.skill_projection import (
    SKILL_PROJECTION_INVALID,
    project_skill_document,
)
from aart_cli.domain.result import Err, Ok

MUTATION_SETTINGS = settings(suppress_health_check=(HealthCheck.differing_executors,))

#: Names the projection may be asked for: the grammar `installed_name` composes (`§169.7`).
NAMES = st.from_regex(r"\A[a-z][a-z0-9]*(?:-[a-z0-9]+){0,3}\Z", fullmatch=True)
#: Bodies an author may have written, frontmatter excluded -- that is the other branch's subject.
BODIES = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    max_size=60,
).filter(lambda text: not text.startswith("---"))


class SkillProjectionTest(unittest.TestCase):
    def test_a_plain_canonical_document_gains_the_installed_name_and_summary(self) -> None:
        canonical = b"# Code review\n\nReview the change.\n"

        projected = project_skill_document(
            canonical,
            installed_name="code-review-company-project",
            summary="Code review skill.",
        )

        assert isinstance(projected, Ok), projected
        self.assertEqual(
            projected.value,
            b'---\nname: code-review-company-project\ndescription: "Code review skill."\n---\n\n'
            + canonical,
        )
        self.assertEqual(canonical, b"# Code review\n\nReview the change.\n")

    def test_existing_frontmatter_keeps_its_description_and_body_but_changes_the_name(self) -> None:
        canonical = b"---\nname: code-review\ndescription: Existing words.\n---\n\nBody.\n"

        projected = project_skill_document(
            canonical,
            installed_name="code-review-company-user",
            summary="Unused fallback.",
        )

        assert isinstance(projected, Ok), projected
        self.assertEqual(
            projected.value,
            b"---\nname: code-review-company-user\ndescription: Existing words.\n---\n\nBody.\n",
        )

    def test_frontmatter_without_a_description_is_given_the_manifest_summary(self) -> None:
        canonical = b"---\nname: code-review\n---\n\nBody.\n"

        projected = project_skill_document(
            canonical, installed_name="code-review-company-project", summary="What it is for."
        )

        assert isinstance(projected, Ok), projected
        self.assertEqual(
            projected.value,
            b'---\nname: code-review-company-project\ndescription: "What it is for."\n'
            b"---\n\nBody.\n",
        )

    def test_frontmatter_that_names_nothing_is_named_before_what_it_does_say(self) -> None:
        canonical = b"---\ndescription: Existing words.\n---\n\nBody.\n"

        projected = project_skill_document(
            canonical, installed_name="code-review-company-project", summary="Unused fallback."
        )

        assert isinstance(projected, Ok), projected
        self.assertEqual(
            projected.value,
            b"---\nname: code-review-company-project\ndescription: Existing words.\n---\n\nBody.\n",
        )

    def test_a_summary_is_delivered_as_written_rather_than_escaped(self) -> None:
        """The description is what the harness shows a person, so a summary in their own language
        has to arrive as the author wrote it and not as a row of escape sequences."""

        projected = project_skill_document(
            b"Body.\n", installed_name="code-review-company-project", summary="Przegląd kodu"
        )

        assert isinstance(projected, Ok), projected
        self.assertIn('description: "Przegląd kodu"\n', projected.value.decode("utf-8"))

    def test_frontmatter_written_with_windows_line_endings_is_still_frontmatter(self) -> None:
        """`\\r\\n` is what an author on Windows commits, and reading its marker as ordinary prose
        would push a second header in front of the one they wrote."""

        canonical = b"---\r\nname: code-review\r\ndescription: Existing.\r\n---\r\n\r\nBody.\r\n"

        projected = project_skill_document(
            canonical, installed_name="code-review-company-project", summary="Unused fallback."
        )

        assert isinstance(projected, Ok), projected
        self.assertEqual(
            projected.value,
            b"---\r\nname: code-review-company-project\r\ndescription: Existing.\r\n"
            b"---\r\n\r\nBody.\r\n",
        )

    def test_the_ending_is_read_off_the_first_row_and_not_off_a_blank_line(self) -> None:
        """A document with no blank line anywhere still ends its rows some way, and the row this
        writes has to end that way too."""

        projected = project_skill_document(
            b"---\r\nname: code-review\r\ndescription: Existing.\r\n---\r\nBody.\r\n",
            installed_name="code-review-company-project",
            summary="Unused fallback.",
        )

        assert isinstance(projected, Ok), projected
        self.assertIn(b"name: code-review-company-project\r\n", projected.value)

    def test_a_stray_carriage_return_in_the_prose_is_not_the_document_s_line_ending(self) -> None:
        """A lone `\\r` is data, not a row terminator, and reading it as one wrote the whole
        header as a single line no frontmatter parser can read."""

        projected = project_skill_document(
            b"Body with a stray \r in it.\n",
            installed_name="code-review-company-project",
            summary="A summary.",
        )

        assert isinstance(projected, Ok), projected
        self.assertTrue(projected.value.startswith(b"---\nname: code-review-company-project\n"))
        self.assertTrue(projected.value.endswith(b"Body with a stray \r in it.\n"))

    # -- what it refuses rather than guesses at ------------------------------------------------

    def _refusal(self, canonical: bytes) -> Err:
        projected = project_skill_document(
            canonical, installed_name="code-review-company-project", summary="A summary."
        )
        assert isinstance(projected, Err), projected
        self.assertIs(projected.diagnostics[0].code, SKILL_PROJECTION_INVALID)
        return projected

    def test_frontmatter_that_never_closes_is_refused_rather_than_closed_here(self) -> None:
        """Closing it would put the rest of the document inside a header the author never opened
        for it, and the harness would read prose as configuration."""

        self._refusal(b"---\nname: code-review\n\nBody with no closing marker.\n")

    def test_frontmatter_that_says_the_name_twice_is_refused_rather_than_half_rewritten(
        self,
    ) -> None:
        self._refusal(b"---\nname: one\nname: two\n---\n\nBody.\n")

    def test_frontmatter_that_says_the_description_twice_is_refused(self) -> None:
        self._refusal(b"---\ndescription: one\ndescription: two\n---\n\nBody.\n")

    def test_a_document_that_is_not_text_is_refused_rather_than_mangled(self) -> None:
        self._refusal(b"\xff\xfe not utf-8 \x00\x80")

    def test_a_name_that_could_forge_a_second_field_is_a_programming_error(self) -> None:
        """A newline in the name would write a line of frontmatter nobody asked for, so it is
        refused at the boundary rather than carried into the document."""

        for name, summary in (("code-review\ndescription: x", "A summary."), ("ok", "a\nb")):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    project_skill_document(b"Body.\n", installed_name=name, summary=summary)

    def test_nothing_but_bytes_and_two_lines_will_do(self) -> None:
        for canonical, name, summary in (
            ("not bytes", "ok", "A summary."),
            (b"Body.\n", "", "A summary."),
            (b"Body.\n", "ok", ""),
            (b"Body.\n", 7, "A summary."),
        ):
            with self.subTest(name=repr(name)):
                with self.assertRaises(ValueError):
                    project_skill_document(
                        canonical,  # type: ignore[arg-type]
                        installed_name=name,  # type: ignore[arg-type]
                        summary=summary,
                    )


class WhateverWasAuthoredTest(unittest.TestCase):
    """The universal half of the claim: whatever the author wrote, two things hold of the result.

    `§169.7` needs the installed copy to name its own directory, and the payload is what a repair
    compares against -- so the projection may add a header and may not touch the body. Three
    examples cannot say that about every document somebody might author, and this is exactly the
    shape of claim a property states better than a chosen case.
    """

    @MUTATION_SETTINGS
    @given(BODIES, NAMES)
    def test_the_authored_body_survives_under_the_installed_name(
        self, body: str, name: str
    ) -> None:
        canonical = body.encode("utf-8")

        projected = project_skill_document(
            canonical, installed_name=name, summary="What it is for."
        )

        assert isinstance(projected, Ok), projected
        text = projected.value.decode("utf-8")
        self.assertTrue(text.endswith(body), "the authored body was not delivered intact")
        self.assertIn(f"name: {name}\n", text)

    @MUTATION_SETTINGS
    @given(BODIES, NAMES)
    def test_projecting_twice_says_the_same_thing_as_projecting_once(
        self, body: str, name: str
    ) -> None:
        """A second install of the same artifact re-delivers from the same payload, so the
        projection has to be a statement about the document rather than an accumulation on it."""

        once = project_skill_document(
            body.encode("utf-8"), installed_name=name, summary="What it is for."
        )
        assert isinstance(once, Ok), once
        twice = project_skill_document(once.value, installed_name=name, summary="What it is for.")

        assert isinstance(twice, Ok), twice
        self.assertEqual(once.value, twice.value)


if __name__ == "__main__":
    unittest.main()
