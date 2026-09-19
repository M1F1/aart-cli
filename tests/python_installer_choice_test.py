"""CP-25.11: the Python dependency backend is a per-install choice seeded by Settings (issue #11b).

`preferred_installer` was plumbed from the effect boundary down to `chosen_installer` and never
supplied by anything: every install took the name-ordered default. This makes the preference real
-- Settings carries it, one operation may differ from it without rewriting it, and the flow offers
only the backends that could actually run this contract on this machine under this policy.

Separate from the installation scope (issue #11a, D-295): scope decides where files land, the
backend decides what resolves the dependencies.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import pathlib
import tempfile
import unittest
from dataclasses import replace
from unittest import mock

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.consumer_session import assemble_consumer_machine
from aart_cli.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerSession,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import (
    ConsumerScreen,
    ConsumerSettings,
    HarnessTargetView,
    PythonInstallerChoiceView,
    installer_from_row,
    installer_row,
    offer_python_installers,
    project_install_plan,
    scope_row,
    target_row,
)
from aart_cli.application.python_environment import (
    select_python_installer,
    usable_python_installers,
)
from aart_cli.domain.inspection import (
    EnvironmentFacts,
    RemediationCapability,
    RemediationCapabilityKind,
)
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.python_runtime import (
    PyProjectSpec,
    PythonInstaller,
    RequirementsFile,
)
from aart_cli.domain.result import Err, Ok
from aart_cli.tui_consumer import CanonicalScreenSource, frame, screens_from
from tests.artifact_installation_test import _facts as _plan_facts
from tests.artifact_installation_test import _plan
from tests.configured_install_command_e2e_test import _environment
from tests.consumer_application_e2e_test import _actions, _drive
from tests.consumer_shell_test import DOWN, SPACE, _at
from tests.consumer_views_test import _plan as _view_plan

BACKENDS = ("pip", "uv")


def _facts(*available: str) -> EnvironmentFacts:
    return EnvironmentFacts(
        "darwin",
        (),
        tuple(
            RemediationCapability(RemediationCapabilityKind.PYTHON_INSTALLER, name)
            for name in available
        ),
    )


def _offer(*declared, preferred: str = "pip"):
    return offer_python_installers(tuple(declared), preferred=preferred)


class WhatCouldActuallyRunThisContractTest(unittest.TestCase):
    """The intersection `select_python_installer` already took, said out loud so a screen can use it.

    A screen that offers a backend the plan would refuse is worse than one that offers nothing: the
    operator reads the refusal as a fault in their choice.
    """

    def test_an_unlocked_contract_on_a_machine_with_both_backends_offers_both(self) -> None:
        usable = usable_python_installers(
            RequirementsFile("requirements.txt"), _facts("pip", "uv"), EffectivePolicy()
        )

        self.assertEqual(usable, frozenset(PythonInstaller))

    def test_a_locked_contract_narrows_to_the_resolver_that_wrote_the_lock(self) -> None:
        usable = usable_python_installers(
            PyProjectSpec("pyproject.toml", lock="uv.lock", lock_format="uv"),
            _facts("pip", "uv"),
            EffectivePolicy(),
        )

        self.assertEqual(usable, frozenset({PythonInstaller.UV}))

    def test_a_backend_this_machine_does_not_have_is_not_usable(self) -> None:
        usable = usable_python_installers(
            RequirementsFile("requirements.txt"), _facts("pip"), EffectivePolicy()
        )

        self.assertEqual(usable, frozenset({PythonInstaller.PIP}))

    def test_policy_removes_a_backend_the_machine_could_otherwise_run(self) -> None:
        usable = usable_python_installers(
            RequirementsFile("requirements.txt"),
            _facts("pip", "uv"),
            EffectivePolicy(allowed_python_installers=frozenset({"uv"})),
        )

        self.assertEqual(usable, frozenset({PythonInstaller.UV}))

    def test_the_selection_never_chooses_outside_what_it_calls_usable(self) -> None:
        """One rule, two callers: the offer and the plan cannot disagree about what may run."""

        for available in (("pip",), ("uv",), ("pip", "uv")):
            with self.subTest(available=available):
                facts, policy = _facts(*available), EffectivePolicy()
                spec = RequirementsFile("requirements.txt")
                selected = select_python_installer(spec, facts, policy)

                assert isinstance(selected, Ok), selected
                self.assertIn(selected.value, usable_python_installers(spec, facts, policy))


class TheOfferIsWhatCouldRunTest(unittest.TestCase):
    def test_two_usable_backends_are_a_choice(self) -> None:
        offered = _offer(BACKENDS)

        assert isinstance(offered, Ok)
        self.assertEqual(offered.value.offered, BACKENDS)
        self.assertTrue(offered.value.is_a_choice)

    def test_one_usable_backend_is_a_fact_rather_than_a_control(self) -> None:
        offered = _offer(("uv",))

        assert isinstance(offered, Ok)
        self.assertEqual(offered.value.selected, "uv")
        self.assertFalse(offered.value.is_a_choice)

    def test_a_multi_artifact_selection_offers_only_what_every_contract_allows(self) -> None:
        offered = _offer(BACKENDS, ("uv",), BACKENDS)

        assert isinstance(offered, Ok)
        self.assertEqual(offered.value.offered, ("uv",))

    def test_contracts_with_no_backend_in_common_are_refused_rather_than_guessed(self) -> None:
        offered = _offer(("pip",), ("uv",))

        self.assertIsInstance(offered, Err)

    def test_nothing_declaring_dependencies_is_not_a_question_to_ask(self) -> None:
        """An install with no Python dependencies has no backend to choose."""

        self.assertIsInstance(_offer(), Err)

    def test_the_offer_opens_on_the_preference_when_the_preference_can_run(self) -> None:
        offered = _offer(BACKENDS, preferred="uv")

        assert isinstance(offered, Ok)
        self.assertEqual(offered.value.selected, "uv")

    def test_a_preference_this_contract_cannot_use_is_not_offered_as_though_it_could(self) -> None:
        offered = _offer(("uv",), preferred="pip")

        assert isinstance(offered, Ok)
        self.assertEqual(offered.value.offered, ("uv",))
        self.assertEqual(offered.value.selected, "uv")

    @given(
        st.lists(
            st.sets(st.sampled_from(BACKENDS), min_size=1).map(lambda item: tuple(sorted(item))),
            min_size=1,
            max_size=4,
        )
    )
    def test_the_offer_is_exactly_the_intersection_of_the_declared_contracts(
        self, declared: list[tuple[str, ...]]
    ) -> None:
        expected = set(BACKENDS).intersection(*(set(item) for item in declared))
        offered = offer_python_installers(tuple(declared), preferred="pip")

        if not expected:
            self.assertIsInstance(offered, Err)
            return
        assert isinstance(offered, Ok)
        self.assertEqual(set(offered.value.offered), expected)
        self.assertIn(offered.value.selected, expected)


class TheChoiceViewCannotHoldAnImpossibleOfferTest(unittest.TestCase):
    def test_an_empty_offer_is_not_representable(self) -> None:
        with self.assertRaises(ValueError):
            PythonInstallerChoiceView((), "pip")

    def test_a_selection_outside_the_offer_is_not_representable(self) -> None:
        with self.assertRaises(ValueError):
            PythonInstallerChoiceView(("uv",), "pip")

    def test_a_backend_nobody_implements_is_not_representable(self) -> None:
        with self.assertRaises(ValueError):
            PythonInstallerChoiceView(("poetry",), "poetry")

    def test_choosing_moves_the_selection_without_changing_the_offer(self) -> None:
        chosen = PythonInstallerChoiceView(BACKENDS, "pip").choose("uv")

        self.assertEqual(chosen.selected, "uv")
        self.assertEqual(chosen.offered, BACKENDS)

    def test_choosing_something_not_offered_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            PythonInstallerChoiceView(("pip",), "pip").choose("uv")


class TheSettingsCarryThePreferenceTest(unittest.TestCase):
    def test_the_default_preference_is_the_backend_every_python_already_has(self) -> None:
        self.assertEqual(ConsumerSettings().python_installer, "pip")

    def test_the_preference_is_binary_like_every_other_control_on_screen_28(self) -> None:
        toggled = ConsumerSettings().toggled("python-installer")

        self.assertEqual(toggled.python_installer, "uv")
        self.assertEqual(toggled.toggled("python-installer").python_installer, "pip")

    def test_a_preference_no_backend_answers_to_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            ConsumerSettings(python_installer="poetry")

    def test_toggling_the_backend_changes_nothing_else(self) -> None:
        settings = ConsumerSettings()

        toggled = settings.toggled("python-installer")

        self.assertEqual(toggled.default_scope, settings.default_scope)
        self.assertEqual(toggled.profile, settings.profile)
        self.assertEqual(toggled.show_updates, settings.show_updates)


class TheCommandCarriesTheChoiceTest(unittest.TestCase):
    def test_the_command_carries_the_chosen_backend(self) -> None:
        command = ConsumerUiCommand(
            ConsumerUiCommandKind.PREPARE_ACTION,
            action=ConsumerActionKind.INSTALL,
            python_installer="uv",
        )

        self.assertEqual(command.python_installer, "uv")

    def test_a_command_cannot_name_a_backend_that_does_not_exist(self) -> None:
        with self.assertRaises(ValueError):
            ConsumerUiCommand(
                ConsumerUiCommandKind.PREPARE_ACTION,
                action=ConsumerActionKind.INSTALL,
                python_installer="conda",
            )

    def test_an_empty_backend_means_follow_the_preference(self) -> None:
        command = ConsumerUiCommand(
            ConsumerUiCommandKind.PREPARE_ACTION, action=ConsumerActionKind.INSTALL
        )

        self.assertEqual(command.python_installer, "")

    def test_the_state_holds_no_choice_until_one_is_made(self) -> None:
        self.assertEqual(ConsumerUiState().python_installer, "")

    def test_the_state_cannot_hold_a_backend_that_does_not_exist(self) -> None:
        with self.assertRaises(ValueError):
            ConsumerUiState(python_installer="conda")


if __name__ == "__main__":
    unittest.main()


class ThePreferenceReachesThePlanTest(unittest.TestCase):
    """The end of the seam: what the plan records is what execution will run.

    `preferred_installer` existed from the effect boundary down to `chosen_installer` before this
    task and nothing ever supplied it, so no test noticed that the argument was inert. These are
    the tests that notice.
    """

    def test_a_plan_with_no_preference_takes_the_name_ordered_default(self) -> None:
        planned = _plan(facts=_plan_facts("pip", "uv"))

        assert isinstance(planned, Ok), planned
        self.assertEqual(planned.value.dependencies[2], "pip")

    def test_the_preference_decides_which_backend_the_plan_records(self) -> None:
        planned = _plan(facts=_plan_facts("pip", "uv"), preferred_installer=PythonInstaller.UV)

        assert isinstance(planned, Ok), planned
        self.assertEqual(planned.value.dependencies[2], "uv")

    def test_a_preference_this_machine_cannot_run_falls_to_one_it_can(self) -> None:
        """A default that loses is still a default: it never widens what may run."""

        planned = _plan(facts=_plan_facts("pip"), preferred_installer=PythonInstaller.UV)

        assert isinstance(planned, Ok), planned
        self.assertEqual(planned.value.dependencies[2], "pip")

    def test_a_preference_policy_forbids_is_not_honoured(self) -> None:
        planned = _plan(
            facts=_plan_facts("pip", "uv"),
            policy=EffectivePolicy(allowed_python_installers=frozenset({"pip"})),
            preferred_installer=PythonInstaller.UV,
        )

        assert isinstance(planned, Ok), planned
        self.assertEqual(planned.value.dependencies[2], "pip")


class TheChoiceTravelsFromTheScreenTest(unittest.TestCase):
    def test_choosing_a_backend_re_prepares_the_plan_at_that_backend(self) -> None:
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.REVIEW_SELECTION),
            action=ConsumerActionKind.INSTALL,
            selection=("company/skill/code-review@1.2.0",),
        )

        chosen, commands = reduce_consumer_ui(
            state,
            ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_SELECTION, key=installer_row("uv")),
        )

        self.assertEqual(chosen.python_installer, "uv")
        self.assertEqual(len(commands), 1)
        self.assertIs(commands[0].kind, ConsumerUiCommandKind.PREPARE_ACTION)
        self.assertEqual(commands[0].python_installer, "uv")

    def test_the_backend_and_the_scope_are_answered_separately(self) -> None:
        """Choosing where files land says nothing about what resolves their dependencies."""

        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.REVIEW_SELECTION),
            action=ConsumerActionKind.INSTALL,
            selection=("company/skill/code-review@1.2.0",),
            python_installer="uv",
        )

        chosen, commands = reduce_consumer_ui(
            state, ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_SELECTION, key=scope_row("user"))
        )

        self.assertEqual(chosen.install_scope, "user")
        self.assertEqual(chosen.python_installer, "uv")
        self.assertEqual(commands[0].python_installer, "uv")

    def test_a_row_naming_no_backend_is_not_a_backend_choice(self) -> None:
        for row in ("installer:conda", "installer:", "uv", target_row("claude")):
            with self.subTest(row=row):
                self.assertIsNone(installer_from_row(row))


class TheQuestionThatDoesNotAriseTest(unittest.TestCase):
    def test_a_selection_with_no_python_dependencies_draws_no_backend_rows(self) -> None:
        """The production composition, over an artifact that needs no Python at all."""

        with _environment() as env:
            finished, terminal, _ = _drive(env, _at(ConsumerScreen.MARKETPLACE), SPACE, ord("i"))

            self.assertIs(finished.session.screen, ConsumerScreen.REVIEW_SELECTION)
            self.assertFalse([row for row in finished.rows if installer_from_row(row)])
            self.assertNotIn("Dependencies with", terminal.last)


class TheReviewScreenOffersTheBackendTest(unittest.TestCase):
    """Screen 05 draws the backend the same way it draws the scope: a radio, after the harnesses."""

    def _source(self, choice: PythonInstallerChoiceView | None) -> CanonicalScreenSource:
        view = project_install_plan(_view_plan())
        artifact = view.selection.resolved[0]
        plan = replace(
            view,
            targets=(HarnessTargetView("claude", (artifact,)),),
            installer_choice=choice,
        )
        machine = assemble_consumer_machine((), today=dt.date(2026, 9, 14))
        return CanonicalScreenSource(screens_from(machine, plan=plan))

    def _state(self) -> ConsumerUiState:
        return ConsumerUiState(
            ConsumerSession(ConsumerScreen.REVIEW_SELECTION),
            selection=("company/mcp/github@1.0.0",),
            action=ConsumerActionKind.INSTALL,
        )

    def test_both_usable_backends_are_rows_below_the_harnesses(self) -> None:
        source = self._source(PythonInstallerChoiceView(BACKENDS, "pip"))

        rows = source.rows(self._state())

        self.assertEqual(rows, (target_row("claude"), installer_row("pip"), installer_row("uv")))

    def test_the_offer_opens_on_the_backend_the_plan_was_prepared_with(self) -> None:
        source = self._source(PythonInstallerChoiceView(BACKENDS, "uv"))
        state = self._state()
        drawn = "\n".join(frame(source, replace(state, rows=source.rows(state))))

        self.assertIn("( ) Dependencies with: pip", drawn)
        self.assertIn("(*) Dependencies with: uv", drawn)

    def test_one_usable_backend_is_disclosed_rather_than_offered(self) -> None:
        source = self._source(PythonInstallerChoiceView(("uv",), "uv"))

        self.assertEqual(source.rows(self._state()), (target_row("claude"),))

    def test_a_plan_with_no_python_dependencies_offers_nothing(self) -> None:
        source = self._source(None)

        self.assertEqual(source.rows(self._state()), (target_row("claude"),))


_DEPENDENT_MANIFEST = {
    "schema": "aart.dev/mcp/v1",
    "artifact": {"name": "code-review", "kind": "mcp", "version": "1.2.0"},
    "payload": {"include": ["server.py", "requirements.txt"]},
    "transport": {"type": "stdio"},
    "runtime": {"type": "python", "version": ">=3.10"},
    "launch": {"type": "python", "entrypoint": "server.py"},
    "python": {"dependencies": {"type": "requirements", "path": "requirements.txt"}},
    "compatibility": {"harnesses": ["claude"]},
}
#: An artifact that actually needs Python resolved, which the standard fixture does not. Without
#: one the backend rows can never appear, and every claim about them is a claim about nothing.
AUTHORED_DEPENDENT = (
    ("code-review/aart.json", json.dumps(_DEPENDENT_MANIFEST)),
    ("code-review/server.py", "print('code review')\n"),
    ("code-review/requirements.txt", "attrs\n"),
)


@contextlib.contextmanager
def _machine_with_both_backends():
    """A machine that reports uv as well as pip, without requiring uv to be installed to test it.

    `observe_python_installers` locates uv on PATH, so a stub on PATH is exactly the observation
    being faked -- the backend is never run here, only planned with.
    """

    with tempfile.TemporaryDirectory() as raw:
        stub = pathlib.Path(raw) / "uv"
        stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)
        with mock.patch.dict(
            os.environ, {"PATH": f"{raw}{os.pathsep}{os.environ['PATH']}"}, clear=False
        ):
            yield


class ThePreferenceReachesTheRealCompositionTest(unittest.TestCase):
    """The mirror of D-295's scope drive test, and for the same reason.

    A targeted mutation pinning the composition's preference to pip survived every unit-level test
    here: nothing drove the production composition over an artifact that needs Python, so nothing
    noticed that Settings were read and discarded.
    """

    def _reviewed(self, env, *codes, preference: str = "pip"):
        """Screen 05 as this machine draws it, with the preference already stored.

        The drawn screen is the assertion rather than the held plan: the plan the shell reviewed
        is not handed back, and what the operator is told is the claim that matters anyway.
        """

        actions = _actions(env)
        actions.save_settings(replace(actions.settings, python_installer=preference))
        return _drive(
            env, _at(ConsumerScreen.MARKETPLACE), SPACE, ord("i"), *codes, actions=actions
        )

    def test_the_review_offers_both_backends_when_the_machine_has_both(self) -> None:
        with _machine_with_both_backends(), _environment(authored=AUTHORED_DEPENDENT) as env:
            finished, terminal, _ = self._reviewed(env)

            self.assertIs(finished.session.screen, ConsumerScreen.REVIEW_SELECTION)
            self.assertEqual(
                tuple(row for row in finished.rows if installer_from_row(row)),
                (installer_row("pip"), installer_row("uv")),
            )
            self.assertIn("Dependencies with: uv", terminal.last)

    def test_the_stored_preference_is_the_backend_the_reviewed_plan_names(self) -> None:
        with _machine_with_both_backends(), _environment(authored=AUTHORED_DEPENDENT) as env:
            _, terminal, _ = self._reviewed(env, preference="uv")

            self.assertIn("(*) Dependencies with: uv", terminal.last)
            self.assertIn("( ) Dependencies with: pip", terminal.last)

    def test_choosing_the_other_backend_re_prepares_the_plan_at_it(self) -> None:
        with _machine_with_both_backends(), _environment(authored=AUTHORED_DEPENDENT) as env:
            # Past the harness and both scope rows to `installer:pip`, then choose it.
            _, terminal, _ = self._reviewed(env, DOWN, DOWN, DOWN, SPACE, preference="uv")

            self.assertIn("(*) Dependencies with: pip", terminal.last)
            self.assertIn("( ) Dependencies with: uv", terminal.last)

    def test_choosing_a_backend_does_not_rewrite_the_stored_preference(self) -> None:
        with _machine_with_both_backends(), _environment(authored=AUTHORED_DEPENDENT) as env:
            self._reviewed(env, DOWN, DOWN, DOWN, SPACE, preference="uv")

            self.assertEqual(_actions(env).settings.python_installer, "uv")
