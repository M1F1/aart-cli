"""CP-23 task 08: Remediation says what AART will change, and Continue is a control, not a string.

Screen 08 opened with ``2 thing(s) need preparing first``, which reads as chores the reader must do,
over rows in effect vocabulary (``configure credential (credential mutation)``). It then promised
``Nothing outside this installation will be modified.``, a guarantee no plan establishes, and ended
with ``[ Continue ]`` printed among the facts while Enter did the continuing.

Now the screen states the changes AART will make once the final review is confirmed, each as an
outcome that names its subject. Material impact stays in plain words in Fast; the effect vocabulary
and owners are Verbose. Continue is the screen's one row. The stop itself is conditional
(§161.5, INV-197): a plan whose only remediations are routine derived harness configuration
goes straight to Ready, which still discloses those changes (D-258).
"""

from __future__ import annotations

import dataclasses
import unittest

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts.application.consumer_ui import (
    ConsumerUiCommandKind,
    ConsumerUiState,
    key_bindings,
    key_event,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    PresentationProfile,
    RemediationView,
    install_flow_screens,
)
from agent_artifacts.tui_consumer import CanonicalScreenSource, _reload, frame, render_ready
from tests.consumer_install_flow_shell_test import at, plan_view
from tests.consumer_install_flow_shell_test import screens as flow_screens

_OWNER = "public/mcp/github@1.6.0"


def _harness(name: str) -> RemediationView:
    return RemediationView(
        "configure-harness",
        "configuration-mutation",
        (f"{name}:project",),
        f"configure-harness: harness={name}",
    )


CREDENTIAL = RemediationView(
    "configure-credential",
    "credential-mutation",
    (_OWNER,),
    "configure-credential: provider=macos-keychain",
)
RUNTIME = RemediationView(
    "install-runtime",
    "executable-install",
    (_OWNER,),
    "install-runtime: constraint=>=3.11, runtime=python",
)
EXECUTABLE = RemediationView(
    "install-executable", "executable-install", (_OWNER,), "install-executable: executable=node"
)
PACKAGES = RemediationView(
    "install-python-packages",
    "executable-install",
    (_OWNER,),
    "install-python-packages: installer=uv",
)
NETWORK = RemediationView(
    "configure-network", "network-mutation", (_OWNER,), "configure-network: host=api.github.com"
)
PROVIDER = RemediationView(
    "select-alternative-provider",
    "configuration-mutation",
    (_OWNER,),
    "select-alternative-provider: provider=onepassword",
)
_EVERY = (_harness("claude"), CREDENTIAL, RUNTIME, EXECUTABLE, PACKAGES, NETWORK, PROVIDER)
_DECISIONS = (CREDENTIAL, RUNTIME, EXECUTABLE, PACKAGES, NETWORK, PROVIDER)


def _plan(*remediations: RemediationView, inputs: bool = True):
    view = dataclasses.replace(plan_view(), remediations=remediations)
    return view if inputs else dataclasses.replace(view, inputs=())


def _on(
    screen: ConsumerScreen,
    *remediations: RemediationView,
    profile: PresentationProfile = PresentationProfile.FAST,
    inputs: bool = True,
) -> tuple[CanonicalScreenSource, ConsumerUiState]:
    _, state = at(screen, profile)
    source = CanonicalScreenSource(
        dataclasses.replace(flow_screens(), plan=_plan(*remediations, inputs=inputs))
    )
    return source, _reload(source, state, entering=True)


def _drawn(*remediations: RemediationView, profile=PresentationProfile.FAST) -> str:
    source, state = _on(ConsumerScreen.REMEDIATION, *remediations, profile=profile)
    return "\n".join(frame(source, state))


class RemediationStatesTheChangesAartWillMakeTest(unittest.TestCase):
    def test_the_screen_announces_changes_aart_makes_rather_than_chores(self) -> None:
        many = _drawn(CREDENTIAL, _harness("claude"))
        one = _drawn(CREDENTIAL)

        self.assertIn("AART will make these changes", many)
        self.assertIn("AART will make this change", one)
        for drawn in (many, one):
            self.assertNotIn("need preparing", drawn)
            self.assertNotIn("thing(s)", drawn)

    def test_each_change_is_an_outcome_that_names_its_subject(self) -> None:
        for remediation, words in (
            (_harness("claude"), ("Configure", "claude")),
            (CREDENTIAL, ("Store", "credential", "securely", "macos keychain")),
            (RUNTIME, ("Install", "python", ">=3.11")),
            (EXECUTABLE, ("Install", "node")),
            (PACKAGES, ("Install", "Python dependencies", "uv")),
            (NETWORK, ("network access", "api.github.com")),
            (PROVIDER, ("onepassword",)),
        ):
            with self.subTest(kind=remediation.kind):
                drawn = _drawn(remediation)
                for word in words:
                    self.assertIn(word, drawn)
                self.assertNotIn(remediation.kind.replace("-", " "), drawn)

    def test_rows_that_differ_only_by_harness_are_still_told_apart(self) -> None:
        source, state = _on(
            ConsumerScreen.REMEDIATION,
            CREDENTIAL,
            _harness("claude"),
            _harness("codex"),
            _harness("opencode"),
        )

        status = source.status(state)
        named = [line for line in status if "integration" in line]

        self.assertEqual(len(named), 3)
        self.assertEqual(len(set(named)), 3, named)

    def test_fast_keeps_material_impact_in_plain_words_and_verbose_adds_the_effect_terms(
        self,
    ) -> None:
        remediations = (CREDENTIAL, RUNTIME, NETWORK)
        fast = _drawn(*remediations)
        verbose = _drawn(*remediations, profile=PresentationProfile.VERBOSE)

        for impact in ("credential", "installed on this machine", "network access"):
            self.assertIn(impact, fast.lower())
        for term in ("credential mutation", "executable install", "network mutation", _OWNER):
            with self.subTest(term=term):
                self.assertNotIn(term, fast)
                self.assertIn(term, verbose)

    def test_no_profile_claims_a_guarantee_the_plan_does_not_establish(self) -> None:
        for profile in PresentationProfile:
            with self.subTest(profile=profile):
                drawn = _drawn(*_EVERY, profile=profile)

                self.assertNotIn("Nothing outside this installation", drawn)
                self.assertNotIn("will not modify", drawn)


class ContinueIsAControlTest(unittest.TestCase):
    def test_continue_is_the_only_row_and_not_a_string_among_the_facts(self) -> None:
        for profile in PresentationProfile:
            with self.subTest(profile=profile):
                source, state = _on(ConsumerScreen.REMEDIATION, CREDENTIAL, profile=profile)

                self.assertEqual(state.rows, (ConsumerScreen.READY.value,))
                self.assertEqual(source.actions(state), ("> Continue",))
                self.assertNotIn("Continue", "\n".join(source.status(state)))
                self.assertNotIn("[ Continue ]", "\n".join(frame(source, state)))

    def test_the_legend_names_enter_continue(self) -> None:
        source, state = _on(ConsumerScreen.REMEDIATION, CREDENTIAL)

        legend = key_bindings(state, detail=source.detail(state))

        self.assertIn(("Enter", "Continue"), {(item.key, item.label) for item in legend})

    def test_continue_reaches_the_final_review_and_changes_nothing(self) -> None:
        source, state = _on(ConsumerScreen.REMEDIATION, CREDENTIAL, RUNTIME)

        event = key_event("enter", state, detail=source.detail(state))
        assert event is not None
        moved, commands = reduce_consumer_ui(state, event)

        self.assertIs(moved.session.screen, ConsumerScreen.READY)
        self.assertIsNone(moved.action)
        self.assertEqual(
            {command.kind for command in commands}, {ConsumerUiCommandKind.LOAD_SCREEN}
        )

    def test_verbose_describes_where_continue_goes_and_fast_does_not(self) -> None:
        source, verbose = _on(
            ConsumerScreen.REMEDIATION, CREDENTIAL, profile=PresentationProfile.VERBOSE
        )
        _, fast = _on(ConsumerScreen.REMEDIATION, CREDENTIAL)

        described = source.description(verbose)

        self.assertTrue(described)
        self.assertIn("nothing has changed yet", " ".join(described))
        fast_drawn = "\n".join(frame(source, fast))
        self.assertFalse(any(line in fast_drawn for line in described))


class TheStopIsConditionalTest(unittest.TestCase):
    def test_routine_harness_configuration_alone_goes_straight_to_ready(self) -> None:
        routine = (_harness("claude"), _harness("codex"))

        for screen, inputs in (
            (ConsumerScreen.REQUIRED_INPUTS, True),
            (ConsumerScreen.REVIEW_SELECTION, False),
        ):
            with self.subTest(screen=screen.value):
                source, state = _on(screen, *routine, inputs=inputs)

                self.assertIs(source.detail(state), ConsumerScreen.READY)
        self.assertNotIn(
            ConsumerScreen.REMEDIATION, install_flow_screens(_plan(*routine, inputs=False))
        )

    def test_ready_still_discloses_the_routine_changes_it_skipped_to(self) -> None:
        drawn = "\n".join(
            render_ready(_plan(_harness("claude"), _harness("codex")), PresentationProfile.FAST)
        )

        self.assertIn("claude", drawn)
        self.assertIn("codex", drawn)
        self.assertIn("integration", drawn)

    def test_every_non_routine_change_is_a_stop(self) -> None:
        for remediation in _DECISIONS:
            with self.subTest(kind=remediation.kind):
                source, state = _on(ConsumerScreen.REQUIRED_INPUTS, _harness("claude"), remediation)

                self.assertIs(source.detail(state), ConsumerScreen.REMEDIATION)

    @given(chosen=st.lists(st.sampled_from(_EVERY), max_size=5, unique=True))
    def test_the_flow_and_the_screen_route_agree_on_one_rule(
        self, chosen: list[RemediationView]
    ) -> None:
        needed = any(item.kind != "configure-harness" for item in chosen)
        flow = install_flow_screens(_plan(*chosen, inputs=False))
        source, state = _on(ConsumerScreen.REVIEW_SELECTION, *chosen, inputs=False)

        self.assertIs(ConsumerScreen.REMEDIATION in flow, needed)
        self.assertIs(
            source.detail(state),
            ConsumerScreen.REMEDIATION if needed else ConsumerScreen.READY,
        )


if __name__ == "__main__":
    unittest.main()
