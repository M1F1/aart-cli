"""CP-23 task 11 — Artifact Details offers real controls and target truth."""

from __future__ import annotations

import json
import unittest
from dataclasses import replace

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_bindings,
    key_event,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    PresentationProfile,
    project_dashboard,
    target_from_row,
)
from aart_cli.configuration.model import SourceKind
from aart_cli.domain.harness import Scope
from aart_cli.domain.result import Err, Ok
from aart_cli.io.artifact_placement import PLACEMENT_UNAVAILABLE
from aart_cli.io.environment_inspection import platform_name
from aart_cli.marketplace.catalog import build_marketplace
from aart_cli.protocol.native_models import CompatibilitySpec
from aart_cli.tui_consumer import (
    CanonicalScreenSource,
    ConsumerActionUpdate,
    ConsumerScreens,
    MarketplaceEntry,
    frame,
    render_marketplace_artifact,
    run_consumer_shell,
)
from aart_cli.tui_marketplace import MarketplaceTarget, project_marketplace_rows
from tests.configured_install_command_e2e_test import _environment
from tests.consumer_application_e2e_test import OFFERED, _delivered, _drive
from tests.consumer_marketplace_shell_test import drive, screens
from tests.consumer_shell_test import ENTER, ESCAPE, SPACE, FakeTerminal, _at
from tests.marketplace_fixtures import (
    artifact,
    configured_source,
    effective_configuration,
    graph,
    source_state,
)
from tests.measured_host_profiles_test import _PlacementFixture
from tests.tui_marketplace_test import _catalog

_MEASURED = ("claude", "codex", "opencode", "tabnine")
#: A platform this machine is not, so an artifact declaring only it excludes this machine.
_ELSEWHERE = "windows" if platform_name() != "windows" else "linux"


def _row(*profiles: str):
    return next(
        row
        for row in project_marketplace_rows(
            _catalog(), MarketplaceTarget(profiles, "darwin", "project", "copy")
        )
        if row.key == "company/skill/review@1.0.0"
    )


def _source(*profiles: str, notice: tuple[str, ...] = ()) -> CanonicalScreenSource:
    row = _row(*profiles)
    return CanonicalScreenSource(
        ConsumerScreens(
            project_dashboard((), registry_count=1),
            marketplace=(MarketplaceEntry(row),),
            notice=notice,
        )
    )


def _details_state(key: str, *, selected: bool = False) -> ConsumerUiState:
    return ConsumerUiState(
        ConsumerSession(
            ConsumerScreen.ARTIFACT_DETAILS,
            history=(ConsumerScreen.MARKETPLACE,),
        ),
        selection=(key,) if selected else (),
        focus=key,
    )


class ArtifactDetailsCompatibilityTest(unittest.TestCase):
    def test_one_eligible_harness_keeps_the_artifact_available(self) -> None:
        row = _row("claude", "opencode", "tabnine")

        rendered = "\n".join(render_marketplace_artifact(row, PresentationProfile.FAST))

        self.assertTrue(row.compatible)
        self.assertEqual(row.eligible_harnesses, ("claude",))
        self.assertEqual(row.unavailable_harnesses, ("opencode", "tabnine"))
        self.assertIn("Eligible installation harnesses\n  - claude", rendered)
        self.assertIn("Detected but not eligible\n  - opencode\n  - tabnine", rendered)
        self.assertNotIn("Actions: select, install, verbose.", rendered)
        needs = rendered.split("What it needs", 1)[1]
        self.assertNotIn("opencode", needs)
        self.assertNotIn("tabnine", needs)

    def test_no_eligible_harness_is_a_visible_blocker_with_reasons(self) -> None:
        row = _row("opencode", "tabnine")

        rendered = "\n".join(render_marketplace_artifact(row, PresentationProfile.FAST))

        self.assertFalse(row.compatible)
        self.assertEqual(row.eligible_harnesses, ())
        self.assertIn("No eligible installation harness is available on this machine.", rendered)
        self.assertIn("Why installation is unavailable", rendered)
        self.assertIn("opencode:", rendered)
        self.assertIn("tabnine:", rendered)

    def test_verbose_calls_each_detected_harness_eligible_or_unavailable(self) -> None:
        rendered = "\n".join(
            render_marketplace_artifact(_row("claude", "opencode"), PresentationProfile.VERBOSE)
        )

        self.assertIn("installation harnesses", rendered)
        self.assertIn("claude", rendered)
        self.assertIn("eligible", rendered)
        self.assertIn("opencode", rendered)
        self.assertIn("detected, unavailable", rendered)


class ArtifactDetailsControlTest(unittest.TestCase):
    def test_space_selects_and_deselects_the_focused_artifact(self) -> None:
        state = _details_state("company/skill/review@1.0.0")

        event = key_event(" ", state)
        self.assertEqual(
            event,
            ConsumerUiEvent(
                ConsumerUiEventKind.TOGGLE_SELECTION,
                key=state.focus,
            ),
        )
        assert event is not None
        selected, commands = reduce_consumer_ui(state, event)

        self.assertEqual(selected.selection, (state.focus,))
        self.assertEqual(selected.focus, state.focus)
        self.assertIs(selected.session.screen, ConsumerScreen.ARTIFACT_DETAILS)
        self.assertEqual(commands, ())
        self.assertIn("Selected for installation.", "\n".join(_source("claude").status(selected)))
        self.assertIn("Space", {item.key for item in key_bindings(selected)})
        self.assertIn("Deselect", {item.label for item in key_bindings(selected)})

        event = key_event(" ", selected)
        assert event is not None
        deselected, _commands = reduce_consumer_ui(selected, event)
        self.assertEqual(deselected.selection, ())
        self.assertEqual(deselected.focus, state.focus)

    def test_selection_survives_back_and_keeps_the_marketplace_cursor_identity(self) -> None:
        offered = screens().marketplace[0].key

        finished, _terminal = drive(
            ENTER,
            SPACE,
            ESCAPE,
            state=_at(ConsumerScreen.MARKETPLACE),
        )

        self.assertIs(finished.session.screen, ConsumerScreen.MARKETPLACE)
        self.assertEqual(finished.selection, (offered,))
        self.assertEqual(finished.current_row, offered)

    def test_details_frame_advertises_each_working_control_without_decorative_prose(self) -> None:
        source = _source("claude", "opencode")
        state = _details_state("company/skill/review@1.0.0")

        rendered = "\n".join(frame(source, state))

        self.assertIn("[i] Install", rendered)
        self.assertIn("[Space] Select", rendered)
        self.assertIn("[v] Fast / Verbose", rendered)
        self.assertNotIn("Actions: select, install, verbose.", rendered)

    def test_install_from_details_needs_no_marketplace_tick(self) -> None:
        with _environment() as env:
            finished, _terminal, _handler = _drive(
                env,
                _at(ConsumerScreen.MARKETPLACE),
                ENTER,
                ord("i"),
                SPACE,
                ENTER,
                ENTER,
            )

            self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS)
            self.assertTrue(_delivered(env).exists())

    def test_no_eligible_harness_refuses_install_back_on_details(self) -> None:
        unavailable = _source("opencode", "tabnine")
        declined = _source(
            "opencode",
            "tabnine",
            notice=("No eligible installation harness is available.",),
        )
        key = "company/skill/review@1.0.0"

        class Handler:
            def handle(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
                self.command = command
                return ConsumerActionUpdate(
                    declined,
                    ConsumerUiEvent(
                        ConsumerUiEventKind.ACTION_PREPARED,
                        action=ConsumerActionKind.INSTALL,
                    ),
                )

        handler = Handler()
        terminal = FakeTerminal(ord("i"), ord("q"))
        finished = run_consumer_shell(
            unavailable,
            terminal,
            state=_details_state(key),
            action_handler=handler,
        )

        self.assertIs(handler.command.kind, ConsumerUiCommandKind.PREPARE_ACTION)
        self.assertEqual(handler.command.focus, key)
        self.assertIs(finished.session.screen, ConsumerScreen.ARTIFACT_DETAILS)
        self.assertIsNone(finished.action)
        self.assertTrue(
            terminal.screen_containing("No eligible installation harness is available.")
        )


def _declaring(profiles: tuple[str, ...], platforms: tuple[str, ...], *detected: str):
    """The Details row for one artifact declaring exactly this compatibility."""

    company = configured_source("company", SourceKind.REGISTRY_GIT)
    declared = replace(
        artifact("company-registry", "review"),
        compatibility=CompatibilitySpec(profiles, platforms),
    )
    built = build_marketplace(
        graph((company, "company-registry", (declared,))),
        effective_configuration((company,), default_registry="company"),
        (source_state(company, "company-registry", display_order=0),),
    )
    assert isinstance(built, Ok), built
    rows = project_marketplace_rows(
        built.value, MarketplaceTarget(detected, platform_name(), "project", "copy")
    )
    return next(row for row in rows if row.key == "company/skill/review@1.0.0")


def _skill(harnesses: list[str] | None = None, platforms: list[str] | None = None):
    manifest: dict[str, object] = {
        "schema": "aart.dev/skill/v1",
        "artifact": {"name": "code-review", "kind": "skill", "version": "1.2.0"},
        "payload": {"include": ["SKILL.md"]},
    }
    compatibility: dict[str, list[str]] = {}
    if harnesses is not None:
        compatibility["harnesses"] = harnesses
    if platforms is not None:
        compatibility["platforms"] = platforms
    if compatibility:
        manifest["compatibility"] = compatibility
    return (
        ("code-review/aart.json", json.dumps(manifest)),
        ("code-review/SKILL.md", "# Code review\n"),
    )


class OneEligibilityRuleTest(unittest.TestCase):
    """Details and installation read one rule: an empty declaration is unconstrained (D-231/D-261)."""

    @given(
        declared=st.sets(st.sampled_from(_MEASURED)),
        detected=st.sets(st.sampled_from(_MEASURED), min_size=1),
        platforms=st.sampled_from(((), ("here",), (_ELSEWHERE,), ("here", _ELSEWHERE))),
    )
    def test_details_eligibility_is_declared_or_unconstrained_on_this_platform(
        self, declared: set[str], detected: set[str], platforms: tuple[str, ...]
    ) -> None:
        profiles = tuple(sorted(declared))
        named = tuple(platform_name() if item == "here" else item for item in platforms)
        seen = tuple(item for item in _MEASURED if item in detected)

        row = _declaring(profiles, named, *seen)

        platform_ok = not named or platform_name() in named
        expected = tuple(
            item for item in seen if platform_ok and (not profiles or item in profiles)
        )
        self.assertEqual(row.eligible_harnesses, expected)
        self.assertEqual(
            row.unavailable_harnesses, tuple(item for item in seen if item not in expected)
        )
        self.assertIs(row.compatible, bool(expected))
        needs = "\n".join(render_marketplace_artifact(row, PresentationProfile.FAST)).split(
            "What it needs", 1
        )[1]
        for item in row.unavailable_harnesses:
            self.assertNotIn(item, needs)

    def test_an_undeclared_platform_is_not_reported_as_unsupported(self) -> None:
        row = _declaring(("claude",), (), "claude", "codex")

        reasons = [reason.code for item in row.compatibility for reason in item.reasons]

        self.assertEqual(row.eligible_harnesses, ("claude",))
        self.assertNotIn("platform-unsupported", reasons)
        self.assertNotIn(
            "supported platforms: none",
            "\n".join(render_marketplace_artifact(row, PresentationProfile.VERBOSE)),
        )


class ADeclaredPlatformNarrowsInstallationTest(_PlacementFixture):
    manifest = {
        "schema": "aart.dev/skill/v1",
        "artifact": {"name": "elsewhere-check", "kind": "skill", "version": "1.0.0"},
        "payload": {"include": ["SKILL.md"]},
        "compatibility": {"harnesses": ["claude"], "platforms": [_ELSEWHERE]},
    }
    files = (("SKILL.md", "# elsewhere\n"),)

    def test_a_platform_this_machine_is_not_refuses_placement_by_name(self) -> None:
        for requested in (False, True):
            with self.subTest(profiles_requested=requested):
                placed = self._place(
                    scope=Scope.PROJECT,
                    harness_root=self.project,
                    profiles=("claude",),
                    profiles_requested=requested,
                )

                self.assertIsInstance(placed, Err)
                assert isinstance(placed, Err)
                self.assertIs(placed.diagnostics[0].code, PLACEMENT_UNAVAILABLE)
                self.assertIn(_ELSEWHERE, placed.diagnostics[0].message)
                self.assertIn(platform_name(), placed.diagnostics[0].message)


class ThisPlatformIsDeclaredTest(_PlacementFixture):
    manifest = {
        "schema": "aart.dev/skill/v1",
        "artifact": {"name": "here-check", "kind": "skill", "version": "1.0.0"},
        "payload": {"include": ["SKILL.md"]},
        "compatibility": {"harnesses": ["claude"], "platforms": [platform_name(), _ELSEWHERE]},
    }
    files = (("SKILL.md", "# here\n"),)

    def test_a_declared_platform_including_this_machine_still_places(self) -> None:
        placed = self._place(
            scope=Scope.PROJECT,
            harness_root=self.project,
            profiles=_MEASURED,
            profiles_requested=False,
        )

        self.assertIsInstance(placed, Ok, getattr(placed, "diagnostics", ()))
        assert isinstance(placed, Ok)
        self.assertEqual([item.harness for item in placed.value.deliveries], ["claude"])


class DetailsAgreesWithReviewSelectionE2ETest(unittest.TestCase):
    """The production composition: what Details calls eligible is what screen 05 offers."""

    def _details_then_review(self, authored):
        with _environment(authored=authored) as env:
            details, _terminal, handler = _drive(env, _at(ConsumerScreen.MARKETPLACE), ENTER)
            row = handler.source().screens.offered(OFFERED)
            review, terminal, handler = _drive(
                env, _at(ConsumerScreen.MARKETPLACE), ENTER, ord("i"), actions=handler
            )
            delivered = _delivered(env).exists()
        self.assertIs(details.session.screen, ConsumerScreen.ARTIFACT_DETAILS)
        assert row is not None
        return row.row, review, terminal, delivered

    def test_the_eligible_harnesses_are_the_review_target_rows(self) -> None:
        for harnesses, expected in (
            (["claude"], ("claude",)),
            (["claude", "opencode", "tabnine"], ("claude", "opencode", "tabnine")),
            (None, ("claude", "codex", "opencode", "tabnine")),
        ):
            with self.subTest(harnesses=harnesses):
                row, review, _terminal, _ = self._details_then_review(_skill(harnesses))

                self.assertIs(review.session.screen, ConsumerScreen.REVIEW_SELECTION)
                # Screen 05 also carries the installation-scope rows (issue #11a), which are a
                # different question; the harnesses are the target rows.
                offered = tuple(
                    harness
                    for harness in (target_from_row(item) for item in review.rows)
                    if harness is not None
                )
                self.assertEqual(row.eligible_harnesses, offered)
                self.assertTrue(set(expected) >= set(offered))
                self.assertIn("claude", offered)

    def test_a_platform_excluding_this_machine_is_unavailable_on_both_screens(self) -> None:
        row, review, terminal, delivered = self._details_then_review(
            _skill(["claude"], [_ELSEWHERE])
        )

        self.assertEqual(row.eligible_harnesses, ())
        self.assertIsNot(review.session.screen, ConsumerScreen.REVIEW_SELECTION)
        self.assertIsNone(review.action)
        self.assertFalse(delivered)
        self.assertTrue(terminal.screen_containing(_ELSEWHERE))


if __name__ == "__main__":
    unittest.main()
