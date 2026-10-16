"""CP-23 task 08, folded into Ready by D-403: the final review says what AART will change.

Screen 08 opened with ``2 thing(s) need preparing first``, which reads as chores the reader must do,
over rows in effect vocabulary (``configure credential (credential mutation)``). It then promised
``Nothing outside this installation will be modified.``, a guarantee no plan establishes, and ended
with ``[ Continue ]`` printed among the facts while Enter did the continuing.

The changes AART will make are stated as outcomes that name their subject. Material impact stays in
plain words in Fast; the effect vocabulary and owners are Verbose. Since D-403 they are no longer
a screen of their own with a Continue row: the operator asked *"czy daloby sie scalic Remediation
i Ready widoki w jeden"*, and confirming Ready is what agrees to them. Routine derived harness
configuration stays More info's (D-258, D-398).
"""

from __future__ import annotations

import dataclasses
import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.consumer_ui import ConsumerUiState
from aart_cli.application.consumer_views import (
    ConsumerScreen,
    PresentationProfile,
    RemediationView,
    install_flow_screens,
)
from aart_cli.tui_consumer import (
    CanonicalScreenSource,
    _reload,
    frame,
    remediation_change,
    render_ready,
)
from aart_cli.tui_layout import list_item
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
    profile: PresentationProfile = PresentationProfile.LESS_INFO,
    inputs: bool = True,
) -> tuple[CanonicalScreenSource, ConsumerUiState]:
    _, state = at(screen, profile)
    source = CanonicalScreenSource(
        dataclasses.replace(flow_screens(), plan=_plan(*remediations, inputs=inputs))
    )
    return source, _reload(source, state, entering=True)


def _drawn(*remediations: RemediationView, profile=PresentationProfile.LESS_INFO) -> str:
    source, state = _on(ConsumerScreen.READY, *remediations, profile=profile)
    return "\n".join(frame(source, state))


class ReadyStatesTheChangesAartWillMakeTest(unittest.TestCase):
    def test_the_review_announces_changes_aart_makes_rather_than_chores(self) -> None:
        many = _drawn(CREDENTIAL, RUNTIME)
        one = _drawn(CREDENTIAL)

        self.assertIn("AART will make these changes when you confirm:", many)
        self.assertIn("AART will make this change when you confirm:", one)
        for drawn in (many, one):
            self.assertNotIn("need preparing", drawn)
            self.assertNotIn("thing(s)", drawn)

    def test_each_change_is_an_outcome_that_names_its_subject(self) -> None:
        for remediation, words in (
            (CREDENTIAL, ("store", "credential", "securely", "macos keychain")),
            (RUNTIME, ("install", "python", ">=3.11")),
            (EXECUTABLE, ("install", "node")),
            (PACKAGES, ("install", "Python dependencies", "uv")),
            (NETWORK, ("network access", "api.github.com")),
            (PROVIDER, ("onepassword",)),
        ):
            with self.subTest(kind=remediation.kind):
                drawn = _drawn(remediation)
                for word in words:
                    self.assertIn(word, drawn)
                # The bare kind label as an item, not a sentence that happens to open with it.
                self.assertNotRegex(
                    drawn, rf"(?m)^\s*(- )?{remediation.kind.replace('-', ' ')}\s*$"
                )

    def test_the_changes_are_parted_from_their_sentence_and_from_each_other(self) -> None:
        lines = render_ready(_plan(CREDENTIAL, RUNTIME), PresentationProfile.LESS_INFO)
        opening = lines.index("AART will make these changes when you confirm:")

        self.assertEqual(lines[opening - 1], "")
        self.assertEqual(lines[opening + 1], "")
        self.assertTrue(lines[opening + 2].startswith("  - store the credential"))
        self.assertEqual(lines[opening + 3], "")
        self.assertTrue(lines[opening + 4].startswith("  - install the python"))

    def test_fast_keeps_material_impact_in_plain_words_and_verbose_adds_the_effect_terms(
        self,
    ) -> None:
        remediations = (CREDENTIAL, RUNTIME, NETWORK)
        fast = _drawn(*remediations)
        verbose = _drawn(*remediations, profile=PresentationProfile.MORE_INFO)

        for impact in ("credential", "install the python", "network access to api.github.com"):
            self.assertIn(impact, fast.lower())
        for term in ("credential mutation", "executable install", "network mutation", _OWNER):
            with self.subTest(term=term):
                self.assertNotIn(term, fast)
                self.assertIn(term, verbose)

    def test_each_change_is_said_once_with_no_summary_repeating_it(self) -> None:
        # D-397: *"informacje w Remediation ... sa zduplikowane"* -- a line per kind of impact under
        # the list said again what the list had just said. On Ready that is the risk sentence too.
        view = dataclasses.replace(
            _plan(*_DECISIONS), risks=("credential-mutation", "network-mutation")
        )
        drawn = "\n".join(render_ready(view, PresentationProfile.LESS_INFO))

        for repeated in (
            "installed on this machine",
            "never shows its value",
            "will be configured",
            "stores a credential",
            "changes network access",
        ):
            self.assertNotIn(repeated, drawn)

    def test_a_material_risk_no_change_names_is_still_said(self) -> None:
        # INV-151: Fast cannot hide it, so only a listed change may stand in for the sentence.
        view = dataclasses.replace(_plan(RUNTIME), risks=("network-mutation",))

        self.assertIn(
            "This install changes network access.",
            render_ready(view, PresentationProfile.LESS_INFO),
        )

    def test_no_profile_claims_a_guarantee_the_plan_does_not_establish(self) -> None:
        for profile in PresentationProfile:
            with self.subTest(profile=profile):
                drawn = _drawn(*_EVERY, profile=profile)

                self.assertNotIn("Nothing outside this installation", drawn)
                self.assertNotIn("will not modify", drawn)


class ThereIsNoSeparateStopTest(unittest.TestCase):
    def test_ready_leaves_the_routine_changes_to_more_info(self) -> None:
        # D-398: *"AART will also: configure the opencode integration ... zbedne dla widoku non
        # verbose"*. The harness counts and Harnesses line already say it; `[v]` keeps the rest.
        plan = _plan(_harness("claude"), _harness("codex"))
        fast = "\n".join(render_ready(plan, PresentationProfile.LESS_INFO))
        verbose = "\n".join(render_ready(plan, PresentationProfile.MORE_INFO))

        self.assertNotIn("AART will make", fast)
        self.assertNotIn("integration", fast)
        self.assertIn("[v] for more info", fast)
        for harness in ("claude", "codex"):
            self.assertIn(harness, verbose)

    @given(chosen=st.lists(st.sampled_from(_EVERY), max_size=5, unique=True))
    def test_every_plan_goes_to_ready_which_lists_exactly_its_material_changes(
        self, chosen: list[RemediationView]
    ) -> None:
        plan = _plan(*chosen, inputs=False)
        source, state = _on(ConsumerScreen.REVIEW_SELECTION, *chosen, inputs=False)
        fast = render_ready(plan, PresentationProfile.LESS_INFO)

        self.assertEqual(
            install_flow_screens(plan)[-3:],
            (ConsumerScreen.READY, ConsumerScreen.INSTALLING, ConsumerScreen.SUCCESS),
        )
        self.assertEqual(install_flow_screens(plan)[:-3], (ConsumerScreen.REVIEW_SELECTION,))
        self.assertIs(source.detail(state), ConsumerScreen.READY)
        listed = tuple(line for line in fast if line.startswith("  - "))
        self.assertEqual(
            listed,
            tuple(
                list_item(remediation_change(item))
                for item in chosen
                if item.kind != "configure-harness"
            ),
        )


if __name__ == "__main__":
    unittest.main()
