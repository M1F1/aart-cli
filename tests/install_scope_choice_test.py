"""CP-25.10: installation scope is a per-install choice seeded by Settings (issue #11a).

`Settings.default_scope` decided where an installation landed without ever saying so on the way
past. It becomes a default rather than a verdict: the flow offers the scopes the resolved selection
actually supports, starts on the preference, and lets this one operation differ from it without
rewriting it.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiState,
)
from aart_cli.application.consumer_views import (
    ConsumerScreen,
    InstallScopeChoiceView,
    offer_install_scopes,
)
from aart_cli.domain.result import Err, Ok
from tests.configured_install_command_e2e_test import _environment
from tests.consumer_application_e2e_test import _INSTALL, ENTER, _actions, _drive
from tests.consumer_shell_test import DOWN, SPACE, _at

SCOPES = ("project", "user")


def _offer(*declared, project_available: bool = True, preferred: str = "project"):
    return offer_install_scopes(
        tuple(declared), project_available=project_available, preferred=preferred
    )


class TheOfferIsTheIntersectionTest(unittest.TestCase):
    def test_an_artifact_supporting_both_offers_both(self) -> None:
        offered = _offer(("project", "user"))

        self.assertIsInstance(offered, Ok)
        assert isinstance(offered, Ok)
        self.assertEqual(offered.value.offered, ("project", "user"))
        self.assertTrue(offered.value.is_a_choice)

    def test_a_selection_supporting_one_scope_discloses_it_without_offering_a_fiction(self) -> None:
        offered = _offer(("user",))

        assert isinstance(offered, Ok)
        self.assertEqual(offered.value.offered, ("user",))
        self.assertEqual(offered.value.selected, "user")
        self.assertFalse(offered.value.is_a_choice)

    def test_a_multi_artifact_selection_offers_only_what_every_member_supports(self) -> None:
        offered = _offer(("project", "user"), ("user",), ("project", "user"))

        assert isinstance(offered, Ok)
        self.assertEqual(offered.value.offered, ("user",))

    def test_members_with_no_common_scope_are_refused_rather_than_guessed(self) -> None:
        """Installing them together has no answer, so the flow must not pick one."""

        refused = _offer(("project",), ("user",))

        self.assertIsInstance(refused, Err)
        assert isinstance(refused, Err)
        self.assertIn("no installation scope", refused.diagnostics[0].message)

    def test_an_empty_selection_is_refused(self) -> None:
        self.assertIsInstance(_offer(), Err)


class ThePreferenceSeedsButDoesNotDecideTest(unittest.TestCase):
    def test_the_settings_value_is_the_initial_selection(self) -> None:
        for preferred in SCOPES:
            with self.subTest(preferred=preferred):
                offered = _offer(("project", "user"), preferred=preferred)

                assert isinstance(offered, Ok)
                self.assertEqual(offered.value.selected, preferred)

    def test_a_preference_the_selection_cannot_honour_falls_to_what_it_can(self) -> None:
        """A preference that is impossible here is a default that lost, not a failure."""

        offered = _offer(("user",), preferred="project")

        assert isinstance(offered, Ok)
        self.assertEqual(offered.value.selected, "user")
        self.assertEqual(offered.value.offered, ("user",))

    def test_choosing_the_other_scope_changes_only_the_selection(self) -> None:
        offered = _offer(("project", "user"), preferred="project")
        assert isinstance(offered, Ok)

        chosen = offered.value.choose("user")

        self.assertEqual(chosen.selected, "user")
        self.assertEqual(chosen.offered, offered.value.offered)

    def test_choosing_a_scope_that_was_not_offered_is_refused(self) -> None:
        offered = _offer(("user",))
        assert isinstance(offered, Ok)

        with self.assertRaises(ValueError):
            offered.value.choose("project")


class NoProjectMeansNoProjectScopeTest(unittest.TestCase):
    def test_without_a_project_target_the_project_scope_is_not_offered(self) -> None:
        offered = _offer(("project", "user"), project_available=False)

        assert isinstance(offered, Ok)
        self.assertEqual(offered.value.offered, ("user",))
        self.assertEqual(offered.value.selected, "user")

    def test_a_project_only_artifact_without_a_project_is_refused(self) -> None:
        self.assertIsInstance(_offer(("project",), project_available=False), Err)


class TheOfferedSetIsExactlyTheIntersectionTest(unittest.TestCase):
    """The universal claim behind the examples above, over every shape of declaration."""

    @given(
        declared=st.lists(
            st.lists(st.sampled_from(SCOPES), min_size=1, max_size=2, unique=True).map(
                lambda item: tuple(sorted(item))
            ),
            min_size=1,
            max_size=4,
        ),
        project_available=st.booleans(),
        preferred=st.sampled_from(SCOPES),
    )
    def test_the_offer_is_the_intersection_minus_what_the_machine_cannot_host(
        self,
        declared: list[tuple[str, ...]],
        project_available: bool,
        preferred: str,
    ) -> None:
        expected = set(SCOPES)
        for item in declared:
            expected &= set(item)
        if not project_available:
            expected -= {"project"}

        result = offer_install_scopes(
            tuple(declared), project_available=project_available, preferred=preferred
        )

        if not expected:
            self.assertIsInstance(result, Err)
            return
        assert isinstance(result, Ok), result
        self.assertEqual(set(result.value.offered), expected)
        self.assertEqual(result.value.offered, tuple(sorted(expected)))
        self.assertIn(result.value.selected, result.value.offered)
        if preferred in expected:
            self.assertEqual(result.value.selected, preferred)


class TheViewRefusesToMisrepresentItselfTest(unittest.TestCase):
    def test_a_selection_outside_the_offer_cannot_be_constructed(self) -> None:
        with self.assertRaises(ValueError):
            InstallScopeChoiceView(("user",), "project")

    def test_an_empty_offer_cannot_be_constructed(self) -> None:
        with self.assertRaises(ValueError):
            InstallScopeChoiceView((), "user")

    def test_an_unsorted_or_repeated_offer_cannot_be_constructed(self) -> None:
        for offered in (("user", "project"), ("user", "user")):
            with self.subTest(offered=offered):
                with self.assertRaises(ValueError):
                    InstallScopeChoiceView(offered, "user")


class TheChoiceTravelsWithTheOperationTest(unittest.TestCase):
    """The scope must reach the plan on the command, not be re-read from Settings at the boundary.

    What was reviewed has to be what is executed. If the boundary read the preference again when
    the plan was built, a preference changed between review and execution would silently move
    somebody's files, which is the fault in issue #11a with the timing reversed.
    """

    def test_the_command_carries_the_chosen_scope(self) -> None:
        command = ConsumerUiCommand(
            ConsumerUiCommandKind.PREPARE_ACTION,
            action=ConsumerActionKind.INSTALL,
            install_scope="user",
        )

        self.assertEqual(command.install_scope, "user")

    def test_a_command_cannot_name_a_scope_that_does_not_exist(self) -> None:
        for scope in ("global", "Project", "machine"):
            with self.subTest(scope=scope):
                with self.assertRaises(ValueError):
                    ConsumerUiCommand(
                        ConsumerUiCommandKind.PREPARE_ACTION,
                        action=ConsumerActionKind.INSTALL,
                        install_scope=scope,
                    )

    def test_an_empty_scope_means_follow_the_preference(self) -> None:
        command = ConsumerUiCommand(
            ConsumerUiCommandKind.PREPARE_ACTION, action=ConsumerActionKind.INSTALL
        )

        self.assertEqual(command.install_scope, "")

    def test_the_state_holds_no_choice_until_one_is_made(self) -> None:
        self.assertEqual(ConsumerUiState().install_scope, "")

    def test_the_state_cannot_hold_a_scope_that_does_not_exist(self) -> None:
        with self.assertRaises(ValueError):
            ConsumerUiState(install_scope="somewhere-else")


class ThePreferenceLosesToTheChoiceOnThisMachineTest(unittest.TestCase):
    """The mirror of `test_the_chosen_scope_is_the_scope_the_next_install_lands_at`.

    That test proves the preference is honoured when nothing overrides it. This one proves the
    override wins: the stored default stays Project, one installation chooses User, and the files
    land in the user's home while the project is left alone. Without it, the seam that reads the
    choice is unheld -- a targeted mutation making `_host` ignore its argument survived every
    other test in this module.
    """

    def test_a_project_default_still_installs_into_the_user_home_when_asked(self) -> None:
        with _environment() as env:
            actions = _actions(env)
            self.assertEqual("project", actions.settings.default_scope)

            _drive(
                env,
                replace(_at(ConsumerScreen.MARKETPLACE), install_scope="user"),
                *_INSTALL,
                actions=actions,
            )

            self.assertTrue(
                (env.home / ".claude/skills/code-review-company-user/SKILL.md").exists(),
                "the chosen user scope never reached the user home",
            )
            self.assertFalse(
                (env.project / ".claude/skills/code-review-company-project/SKILL.md").exists(),
                "the preference installed into the project despite the choice",
            )

    def test_the_one_off_choice_does_not_rewrite_the_stored_preference(self) -> None:
        """A choice about this operation is not a new default."""

        with _environment() as env:
            _drive(
                env,
                replace(_at(ConsumerScreen.MARKETPLACE), install_scope="user"),
                *_INSTALL,
                actions=_actions(env),
            )

            reopened = _actions(env)

            self.assertEqual("project", reopened.settings.default_scope)


if __name__ == "__main__":
    unittest.main()


class TheReviewScreenShowsTheChoiceTest(unittest.TestCase):
    """The half of issue #11a an operator can see.

    The seam underneath could already carry a chosen scope, but nothing on screen said a choice
    existed: the review screen drew the scope rows as `[ ] None`, so the only way to reach the
    other scope was to change the stored preference first -- which is the thing this issue is
    about not having to do.
    """

    def test_the_review_screen_names_both_scopes_the_selection_supports(self) -> None:
        with _environment() as env:
            _, terminal, _ = _drive(env, _at(ConsumerScreen.MARKETPLACE), SPACE, ord("i"))

            self.assertIn("Install into: Project", terminal.last)
            self.assertIn("Install into: User", terminal.last)
            self.assertNotIn("[ ] None", terminal.last)

    def test_the_offer_opens_on_the_stored_preference(self) -> None:
        with _environment() as env:
            _, terminal, _ = _drive(env, _at(ConsumerScreen.MARKETPLACE), SPACE, ord("i"))

            self.assertIn("(*) Install into: Project", terminal.last)
            self.assertIn("( ) Install into: User", terminal.last)

    def test_choosing_the_other_scope_moves_the_mark_to_it(self) -> None:
        with _environment() as env:
            _, terminal, _ = _drive(
                env, _at(ConsumerScreen.MARKETPLACE), SPACE, ord("i"), DOWN, DOWN, SPACE
            )

            self.assertIn("( ) Install into: Project", terminal.last)
            self.assertIn("(*) Install into: User", terminal.last)

    def test_a_scope_chosen_on_the_review_screen_is_where_the_files_land(self) -> None:
        with _environment() as env:
            _drive(
                env,
                _at(ConsumerScreen.MARKETPLACE),
                SPACE,
                ord("i"),
                SPACE,
                DOWN,
                DOWN,
                SPACE,
                ENTER,
                ENTER,
                actions=_actions(env),
            )

            self.assertTrue(
                (env.home / ".claude/skills/code-review-company-user/SKILL.md").exists(),
                "the scope chosen on the review screen never reached the user home",
            )
            self.assertFalse(
                (env.project / ".claude/skills/code-review-company-project/SKILL.md").exists(),
                "the install went to the project the operator had just moved away from",
            )

    def test_a_selection_with_one_possible_scope_states_it_without_a_control(self) -> None:
        """A fact is not a choice: nothing is drawn to press when only one scope is possible."""

        offered = _offer(("user",))

        assert isinstance(offered, Ok)
        self.assertFalse(offered.value.is_a_choice)
