"""One layout rule for every screen that asks for a key press (`QA-029`).

The acceptance run reported that `Press Enter to synchronize.` was invisible: it was the last of
nine lines in an undifferentiated block, so the one sentence addressed to the operator had to be
found by reading everything above it. The operator asked for the general rule rather than one more
line on one screen -- "powinno byc wiecej pustych linii pomiedzy wierszami tekstu".

The rule: the facts, one blank line, then the single line saying what a key press will do, and
nothing after it. It is enforced at the seams every screen passes through -- `action_prompt` in the
layout kernel, and `CanonicalScreenSource.lines` -- so a screen written later obeys it without
having to remember to.
"""

from __future__ import annotations

import unittest

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_artifacts.application.consumer_ui import ConsumerUiState
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
    PresentationProfile,
    project_dashboard,
)
from agent_artifacts.application.maintainer_views import (
    MaintainerAdoptionReviewView,
    MaintainerRegistryCommitView,
    MaintainerScreen,
    MaintainerSourceSyncResultView,
    MaintainerSourceSyncReviewView,
    MaintainerTransactionCandidateView,
)
from agent_artifacts.domain.candidates import CandidateState
from agent_artifacts.tui_consumer import CanonicalScreenSource, ConsumerScreens
from agent_artifacts.tui_layout import action_prompt, is_action_prompt, separate
from agent_artifacts.tui_maintainer import (
    render_maintainer_registry_commit,
    render_repository_adoption_review,
    render_source_sync_result,
    render_source_sync_review,
)

# `differing_executors` is suppressed for the reason `doctor_properties_test` records: the scoped
# `make mutants` run re-runs the same test method object from a fresh runner per mutant, which is
# what the check detects. These properties are pure functions of generated input.
MUTATION_SETTINGS = settings(suppress_health_check=(HealthCheck.differing_executors,))

PROMPTS = (
    "Press Enter to synchronize.",
    "Enter commits this exact local transaction.",
    "Type to edit; Backspace removes; Enter advances.",
    "Space selects an adoptable artifact; a reviews the selected copies.",
)


def _assert_prompt_is_separated(case: unittest.TestCase, body: tuple[str, ...], label: str) -> None:
    """The shared assertion: at most one prompt, it is last, and a blank line precedes it."""

    prompts = [index for index, line in enumerate(body) if is_action_prompt(line)]
    if not prompts:
        return
    case.assertEqual(len(prompts), 1, f"{label}: more than one prompt line: {body}")
    case.assertEqual(prompts[0], len(body) - 1, f"{label}: the prompt is not last: {body}")
    if len(body) == 1:
        return
    case.assertEqual(body[-2], "", f"{label}: no blank line before the prompt: {body}")


class ActionPromptRuleTest(unittest.TestCase):
    def test_the_facts_are_separated_from_the_prompt(self) -> None:
        self.assertEqual(
            action_prompt(("Branch: main", "Registry mutations: none"), "Press Enter to sync."),
            ("Branch: main", "Registry mutations: none", "", "Press Enter to sync."),
        )

    def test_a_line_that_names_no_key_is_not_a_prompt(self) -> None:
        self.assertFalse(is_action_prompt("This adds another registry. Nothing is changed."))
        self.assertFalse(is_action_prompt("Registry mutations: none"))

    def test_a_line_naming_a_key_is_a_prompt(self) -> None:
        for prompt in PROMPTS:
            with self.subTest(prompt=prompt):
                self.assertTrue(is_action_prompt(prompt))

    def test_a_sentence_that_asks_for_nothing_cannot_be_a_prompt(self) -> None:
        with self.assertRaises(ValueError):
            action_prompt(("a fact",), "Registry mutations: none")

    def test_a_key_name_at_the_end_of_a_sentence_is_still_a_key_name(self) -> None:
        """The shortest prompt anybody would write, and the one the punctuation strip is for."""

        self.assertTrue(is_action_prompt("Press Enter."))
        self.assertTrue(is_action_prompt("Nothing runs until you press Enter."))

    def test_only_a_line_of_text_can_be_looked_at(self) -> None:
        for value in (None, 5, ("Press Enter.",)):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    is_action_prompt(value)  # type: ignore[arg-type]

    @MUTATION_SETTINGS
    @given(
        facts=st.lists(st.sampled_from(("a fact", "another fact", "")), max_size=8),
        prompt=st.sampled_from(PROMPTS),
    )
    def test_the_rule_holds_over_any_facts(self, facts: list[str], prompt: str) -> None:
        rendered = action_prompt(facts, prompt)

        self.assertEqual(rendered[-1], prompt)
        if len(rendered) > 1:
            self.assertEqual(rendered[-2], "")
            self.assertNotEqual(rendered[-3] if len(rendered) > 2 else "x", "")
        self.assertTrue(rendered[0].strip(), rendered)


class SeparateBlocksTest(unittest.TestCase):
    """The other half of `QA-029`: a screen is read in groups, so groups are what it is built of."""

    def test_blocks_are_joined_by_exactly_one_blank_line(self) -> None:
        self.assertEqual(
            separate(("a", "b"), ("c",), ("d", "e")),
            ("a", "b", "", "c", "", "d", "e"),
        )

    def test_an_absent_block_leaves_no_gap_of_its_own(self) -> None:
        """The bug an ad-hoc `("", *notice)` has: a missing block leaves a double blank behind."""

        self.assertEqual(separate(("a",), (), ("b",)), ("a", "", "b"))
        self.assertEqual(separate((), ()), ())

    def test_blank_lines_at_a_block_edge_do_not_double_the_separation(self) -> None:
        self.assertEqual(separate(("a", ""), ("", "b")), ("a", "", "b"))

    @MUTATION_SETTINGS
    @given(
        blocks=st.lists(
            st.lists(st.sampled_from(("a fact", "another fact", "")), max_size=4), max_size=5
        )
    )
    def test_a_join_never_doubles_a_blank_line(self, blocks: list[list[str]]) -> None:
        """What the joiner is responsible for: the seams. A block's interior is its author's."""

        stripped = [[line for line in block if line.strip()] for block in blocks]
        rendered = separate(*stripped)

        self.assertFalse(
            any(
                not first.strip() and not second.strip()
                for first, second in zip(rendered, rendered[1:], strict=False)
            ),
            rendered,
        )
        if rendered:
            self.assertTrue(rendered[0].strip() and rendered[-1].strip(), rendered)
        self.assertEqual(
            [line for line in rendered if line.strip()],
            [line for block in stripped for line in block],
        )


class EveryScreenSeparatesItsPromptTest(unittest.TestCase):
    """The sweep: no screen may bury the one line that says what a key press will do."""

    def _source(self, notice: tuple[str, ...] = ()) -> CanonicalScreenSource:
        return CanonicalScreenSource(
            ConsumerScreens(project_dashboard((), registry_count=0), notice=notice)
        )

    def _sweep(self, notice: tuple[str, ...]) -> None:
        source = self._source(notice)
        settings = ConsumerSettings().with_maintainer_mode(True)
        for screen in (*ConsumerScreen, *MaintainerScreen):
            with self.subTest(screen=screen.value):
                state = ConsumerUiState(ConsumerSession(screen), settings=settings)
                _assert_prompt_is_separated(self, source.actions(state), screen.value)

    def test_no_screen_buries_its_prompt(self) -> None:
        self._sweep(())

    def test_a_review_keeps_its_prompt_under_the_plan_it_is_about(self) -> None:
        """A notice is what the reader is being asked about, so the ask comes after it."""

        self._sweep(("Registry rebuild review:", "  lock", "  build"))

    def test_the_sweep_would_see_a_buried_prompt(self) -> None:
        with self.assertRaises(self.failureException):
            _assert_prompt_is_separated(
                self, ("a fact", "Press Enter to sync.", "another fact"), "planted"
            )
        with self.assertRaises(self.failureException):
            _assert_prompt_is_separated(self, ("a fact", "Press Enter to sync."), "planted")


class MaintainerReviewsSeparateTheirPromptTest(unittest.TestCase):
    """The three maintainer reviews, which the sweep cannot reach without their typed views."""

    def _sync_review(self) -> MaintainerSourceSyncReviewView:
        return MaintainerSourceSyncReviewView(
            alias="company",
            kind="source-git",
            location="https://git.example.test/team/source.git",
            branch="main",
            target_registry="registry",
            current_revision="a" * 40,
            candidate_count=2,
            approved_revision="b" * 40,
            approved_snapshot="c" * 64,
            review_digest="d" * 64,
        )

    def _sync_result(self) -> MaintainerSourceSyncResultView:
        return MaintainerSourceSyncResultView(
            alias="company",
            disposition="updated",
            revision="a" * 40,
            manifest_count=3,
            target_registry="registry",
            candidate_states=((CandidateState.NEW, 2), (CandidateState.READY, 1)),
            review_digest="d" * 64,
        )

    def _adoption_review(self) -> MaintainerAdoptionReviewView:
        return MaintainerAdoptionReviewView(
            url="https://git.example.test/team/repo.git",
            commit="e" * 40,
            selected=("mcp/github-mcp@1.0.0",),
            changed_paths=("registry/versions/mcp/github-mcp/1.0.0.json",),
            review_digest="f" * 64,
        )

    def _commit(self, *, applied: bool) -> MaintainerRegistryCommitView:
        return MaintainerRegistryCommitView(
            candidates=(
                MaintainerTransactionCandidateView(
                    candidate_id="1" * 64,
                    artifact="mcp/github-mcp",
                    version="1.0.0",
                    validation_report_digest="2" * 64,
                    effective_policy_digest="3" * 64,
                ),
            ),
            target_registry="registry",
            mode="vendored",
            transaction_digest="4" * 64,
            registry_snapshot_before="5" * 64,
            registry_snapshot_after="6" * 64,
            changed_paths=3,
            approved_version_count=1,
            applied=applied,
            commit_subject="promote mcp/github-mcp 1.0.0",
            commit_revision="7" * 40 if applied else None,
        )

    def test_every_profile_of_every_review_separates_its_prompt(self) -> None:
        for profile in PresentationProfile:
            for label, body in (
                ("source sync review", render_source_sync_review(self._sync_review(), profile)),
                (
                    "adoption review",
                    render_repository_adoption_review(self._adoption_review(), profile),
                ),
                (
                    "registry commit",
                    render_maintainer_registry_commit(self._commit(applied=False), profile),
                ),
                (
                    "registry commit applied",
                    render_maintainer_registry_commit(self._commit(applied=True), profile),
                ),
            ):
                with self.subTest(profile=profile.value, screen=label):
                    _assert_prompt_is_separated(self, body, f"{label}/{profile.value}")

    def test_the_source_sync_screens_are_read_as_groups_not_as_one_block(self) -> None:
        """`QA-029`'s own screen: what it is, where it stands, what it will do, and the evidence."""

        for label, body in (
            (
                "review",
                render_source_sync_review(self._sync_review(), PresentationProfile.FAST),
            ),
            (
                "result",
                render_source_sync_result(self._sync_result(), PresentationProfile.FAST),
            ),
        ):
            with self.subTest(screen=label):
                self.assertGreaterEqual(
                    sum(1 for line in body if not line.strip()), 3, f"{label}: {body}"
                )
                self.assertFalse(
                    any(
                        not first.strip() and not second.strip()
                        for first, second in zip(body, body[1:], strict=False)
                    ),
                    f"{label}: {body}",
                )

    def test_a_verbose_source_sync_review_still_ends_with_the_prompt(self) -> None:
        """Verbose adds evidence lines; evidence is a fact, so it stays above the ask."""

        body = render_source_sync_review(self._sync_review(), PresentationProfile.VERBOSE)

        self.assertEqual(body[-1], "Press Enter to synchronize.")
        self.assertTrue(any("Approved snapshot" in line for line in body), body)


if __name__ == "__main__":
    unittest.main()
