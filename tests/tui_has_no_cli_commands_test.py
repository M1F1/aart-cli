"""No TUI frame tells the operator to go and run a command.

`QA-017`/`B-091`. Adding an already-connected Registry produced domain diagnostics whose
remediation is literally `aart source sync …`, `aart source resubscribe …` and `aart source remove
…`, and the interactive adapter copied them into the notice verbatim. The line was long enough to
be clipped after `aart source remove`, so the interactive application answered a refusal by sending
the operator to a terminal and then cut the instruction in half.

The CLI and the JSON envelope keep their complete remediation contracts — that is where those
commands belong. What the interactive adapter renders is `Diagnostic.interactive`: prose written for
somebody who is already inside the application. A diagnostic that has none falls back to the
remediation steps that name no command, so an unconverted producer degrades to saying less rather
than to printing shell syntax.
"""

from __future__ import annotations

import re
import unittest

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts.application.consumer_ui import ConsumerUiState
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
    project_dashboard,
)
from agent_artifacts.application.maintainer_views import MaintainerScreen
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.result import Err
from agent_artifacts.io.consumer_actions import _ELSEWHERE, _refusal
from agent_artifacts.tui_consumer import CanonicalScreenSource, ConsumerScreens, frame
from agent_artifacts.tui_sources import plan_source_addition
from tests.source_remediation_test import _registry, _view

CODE = DiagnosticCode("source-selection-invalid")


def _diagnostic(message: str, *remediation: str, interactive: tuple[str, ...] = ()) -> Diagnostic:
    return Diagnostic(
        CODE,
        Severity.ERROR,
        message,
        remediation=tuple(remediation),
        interactive=interactive,
    )


class InteractiveRefusalTest(unittest.TestCase):
    def test_a_diagnostic_with_interactive_prose_renders_that_and_not_its_commands(self) -> None:
        rendered = _refusal(
            (
                _diagnostic(
                    "source alias is already configured: company",
                    "run `aart source sync --alias company` to refresh it",
                    interactive=(
                        "This registry is already connected. Refresh it from Registries.",
                    ),
                ),
            )
        )

        self.assertIn("source alias is already configured: company", rendered)
        self.assertIn("This registry is already connected. Refresh it from Registries.", rendered)
        self.assertFalse(any("aart " in line for line in rendered), rendered)

    def test_a_command_free_remediation_is_still_shown_when_there_is_no_prose(self) -> None:
        """Dropping every step would answer `QA-019` with the defect it just removed."""

        rendered = _refusal(
            (_diagnostic("source has an invalid Git origin", "use an https:// URL with no secret"),)
        )

        self.assertIn("use an https:// URL with no secret", rendered)

    def test_a_refusal_whose_every_step_is_a_command_still_says_something(self) -> None:
        rendered = _refusal(
            (
                _diagnostic(
                    "source origin and ref are already configured as company",
                    "run `aart source sync --alias company` to refresh it",
                    "`aart source remove --alias company` to free the origin",
                ),
            )
        )

        self.assertFalse(any("aart " in line for line in rendered), rendered)
        self.assertGreater(len(rendered), 1, rendered)

    def test_the_message_itself_is_never_dropped(self) -> None:
        rendered = _refusal((_diagnostic("nothing canonical is installed here"),))

        self.assertEqual(rendered, ("nothing canonical is installed here",))


class NoCommandReachesTheInteractiveAdapterTest(unittest.TestCase):
    """The property `B-091` asks for, over generated remediation rather than four examples."""

    @given(
        message=st.text(min_size=1, max_size=60).filter(lambda item: item.strip() != ""),
        steps=st.lists(
            st.one_of(
                st.text(min_size=1, max_size=60),
                st.builds(
                    lambda verb, rest: f"run `aart {verb} {rest}` to fix it",
                    st.sampled_from(("source sync", "source remove", "registry audit")),
                    st.text(
                        alphabet=st.characters(min_codepoint=97, max_codepoint=122),
                        min_size=1,
                        max_size=8,
                    ),
                ),
                st.builds(lambda rest: f"aart {rest}", st.text(min_size=1, max_size=20)),
            ),
            max_size=5,
        ),
    )
    def test_no_rendered_line_ever_contains_an_aart_command(
        self, message: str, steps: list[str]
    ) -> None:
        rendered = _refusal((_diagnostic(message, *steps),))

        for line in rendered[1:]:
            self.assertNotIn("aart ", line)


class DuplicateConnectionSpeaksInteractivelyTest(unittest.TestCase):
    """`QA-017`'s own scenario: the alias and the origin that are already connected.

    The fallback in `_refusal` keeps an unconverted producer from printing shell syntax, but it can
    only say that the next step is elsewhere. These two refusals are the ones the acceptance run
    actually hit, so they say what is true about *this* machine — which alias holds it, and what to
    do from Registries — while the CLI keeps its exact commands.
    """

    def test_a_duplicate_alias_says_what_is_already_connected(self) -> None:
        held = _registry("registry", "https://git.example.test/team/registry.git")
        duplicate = _registry("registry", "https://git.example.test/other/registry.git")

        refused = plan_source_addition(_view(held), duplicate)

        assert isinstance(refused, Err), refused
        rendered = _refusal(refused.diagnostics)
        self.assertTrue(any("already connected" in line for line in rendered), rendered)
        self.assertTrue(any("registry" in line for line in rendered), rendered)
        self.assertFalse(any("aart " in line for line in rendered), rendered)
        self.assertNotIn(_ELSEWHERE, rendered)

    def test_a_duplicate_origin_names_the_alias_that_already_holds_it(self) -> None:
        held = _registry("registry", "https://git.example.test/team/registry.git")
        same_origin = _registry("second", "https://git.example.test/team/registry.git")

        refused = plan_source_addition(_view(held), same_origin)

        assert isinstance(refused, Err), refused
        rendered = _refusal(refused.diagnostics)
        self.assertTrue(any("already connected as registry" in line for line in rendered), rendered)
        self.assertFalse(any("aart " in line for line in rendered), rendered)
        self.assertNotIn(_ELSEWHERE, rendered)

    def test_the_cli_contract_still_carries_the_exact_commands(self) -> None:
        """`remediation` is where those commands belong, and this change did not take them away."""

        held = _registry("registry", "https://git.example.test/team/registry.git")
        duplicate = _registry("registry", "https://git.example.test/other/registry.git")

        refused = plan_source_addition(_view(held), duplicate)

        assert isinstance(refused, Err), refused
        self.assertTrue(
            any(
                "aart source sync" in step
                for item in refused.diagnostics
                for step in item.remediation
            ),
            refused.diagnostics,
        )


class NoFrameDrawsACommandTest(unittest.TestCase):
    """`B-091`'s audit, as a sweep rather than a reading: every screen, with a refusal on it."""

    #: A command, not a filename. `aart.yaml`, `aart-registry.json` and the `AART /` title are all
    #: legitimate; `aart source sync --alias company` is the thing this must never draw.
    COMMAND = re.compile(
        r"aart (source|registry|marketplace|setup|doctor|security|memory|reporting)\b"
    )

    def _source(self) -> CanonicalScreenSource:
        notice = _refusal(
            (
                _diagnostic(
                    "source alias is already configured: company",
                    "run `aart source sync --alias company` to refresh it, "
                    "`aart source remove --alias company` to subscribe to a different origin",
                ),
            )
        )
        return CanonicalScreenSource(
            ConsumerScreens(project_dashboard((), registry_count=0), notice=notice)
        )

    def test_no_screen_draws_a_command_even_while_a_refusal_is_on_it(self) -> None:
        source = self._source()
        settings = ConsumerSettings().with_maintainer_mode(True)

        for screen in (*ConsumerScreen, *MaintainerScreen):
            with self.subTest(screen=screen.value):
                state = ConsumerUiState(ConsumerSession(screen), settings=settings)

                for line in frame(source, state):
                    self.assertIsNone(self.COMMAND.search(line), f"{screen.value}: {line}")

    def test_the_sweep_would_see_a_command_if_one_were_drawn(self) -> None:
        """Without this, a sweep that stopped reaching the notice would pass by drawing nothing."""

        planted = CanonicalScreenSource(
            ConsumerScreens(
                project_dashboard((), registry_count=0),
                notice=("run `aart source sync --alias company`",),
            )
        )
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.REGISTRY_REVIEW),
            settings=ConsumerSettings().with_maintainer_mode(True),
        )

        self.assertTrue(
            any(self.COMMAND.search(line) for line in frame(planted, state)),
            frame(planted, state),
        )


if __name__ == "__main__":
    unittest.main()
