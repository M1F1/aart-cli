"""CP-23 task 10 — screen 05 carries explicit harness intent into the reviewed plan."""

from __future__ import annotations

import datetime as dt
import json
import unittest
from dataclasses import replace
from types import SimpleNamespace

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts.application.consumer_session import assemble_consumer_machine
from agent_artifacts.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEventKind,
    ConsumerUiState,
)
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    HarnessTargetView,
    PresentationProfile,
    project_install_plan,
    target_row,
)
from agent_artifacts.domain.effects import RiskClass
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.receipts import receipt_profiles
from agent_artifacts.domain.result import Ok
from agent_artifacts.io.consumer_actions import LocalConsumerActions, _installation_targets
from agent_artifacts.io.receipt_store import LocalReceiptStore
from agent_artifacts.tui_consumer import CanonicalScreenSource, frame, render_ready, screens_from
from tests.configured_install_command_e2e_test import _environment
from tests.consumer_application_e2e_test import _actions, _at, _drive
from tests.consumer_shell_test import DOWN, ENTER, SPACE
from tests.consumer_views_test import _plan

_COMPATIBLE = ["claude", "opencode", "tabnine"]
_SKILL_MANIFEST = {
    "schema": "aart.dev/skill/v1",
    "artifact": {"name": "code-review", "kind": "skill", "version": "1.2.0"},
    "payload": {"include": ["SKILL.md"]},
    "compatibility": {"harnesses": _COMPATIBLE},
}
_AUTHORED_SKILL = (
    ("code-review/aart.json", json.dumps(_SKILL_MANIFEST)),
    ("code-review/SKILL.md", "# Code review\n\nChosen harness delivery.\n"),
)
_MCP_MANIFEST = {
    "schema": "aart.dev/mcp/v1",
    "artifact": {"name": "dummy", "kind": "mcp", "version": "1.0.0"},
    "payload": {"include": ["server.py"]},
    "transport": {"type": "stdio"},
    "runtime": {"type": "python", "version": ">=3.10"},
    "launch": {"type": "python", "entrypoint": "server.py"},
    "compatibility": {"harnesses": _COMPATIBLE},
}
_AUTHORED_MCP = (
    ("dummy/aart.json", json.dumps(_MCP_MANIFEST)),
    ("dummy/server.py", "print('dummy')\n"),
)


def _view(*, chosen: tuple[str, ...] = ()):
    view = project_install_plan(_plan())
    artifact = view.selection.resolved[0]
    return replace(
        view,
        targets=(
            HarnessTargetView("claude", (artifact,)),
            HarnessTargetView("opencode", (artifact,)),
            HarnessTargetView("tabnine", (artifact,)),
        ),
        chosen_targets=chosen,
    )


def _source(*, chosen: tuple[str, ...] = ()) -> CanonicalScreenSource:
    machine = assemble_consumer_machine((), today=dt.date(2026, 9, 14))
    return CanonicalScreenSource(screens_from(machine, plan=_view(chosen=chosen)))


def _state(*, targets: tuple[str, ...] = (), verbose: bool = False) -> ConsumerUiState:
    return ConsumerUiState(
        ConsumerSession(
            ConsumerScreen.REVIEW_SELECTION,
            PresentationProfile.VERBOSE if verbose else PresentationProfile.FAST,
        ),
        selection=("company/mcp/github@1.0.0",),
        targets=targets,
        action=ConsumerActionKind.INSTALL,
    )


class HarnessTargetScreenTest(unittest.TestCase):
    @given(st.sets(st.sampled_from(_COMPATIBLE), min_size=1))
    def test_every_nonempty_eligible_subset_is_confirmable(self, selected: set[str]) -> None:
        chosen = tuple(harness for harness in _COMPATIBLE if harness in selected)
        source = _source(chosen=chosen)
        state = _state(targets=chosen)

        self.assertIsNotNone(source.detail(state))

    @given(
        st.sets(st.sampled_from(_COMPATIBLE), min_size=1),
        st.lists(st.sampled_from(("back", "verbose")), min_size=1, max_size=20),
    )
    def test_back_and_verbose_preserve_harness_intent(
        self, selected: set[str], events: list[str]
    ) -> None:
        chosen = tuple(harness for harness in _COMPATIBLE if harness in selected)
        state = replace(
            _state(targets=chosen),
            session=ConsumerSession(
                ConsumerScreen.REVIEW_SELECTION,
                history=(ConsumerScreen.MARKETPLACE,),
            ),
        )

        from agent_artifacts.application.consumer_ui import ConsumerUiEvent, reduce_consumer_ui

        for event in events:
            state, _commands = reduce_consumer_ui(
                state,
                ConsumerUiEvent(
                    ConsumerUiEventKind.BACK
                    if event == "back"
                    else ConsumerUiEventKind.TOGGLE_PROFILE
                ),
            )

        self.assertEqual(state.targets, chosen)

    def test_screen_05_has_unselected_harness_rows_below_the_selection_review(self) -> None:
        source = _source()
        state = _state()
        rows = source.rows(state)
        state = replace(state, rows=rows)

        drawn = "\n".join(frame(source, state))

        self.assertEqual(
            rows,
            (target_row("claude"), target_row("opencode"), target_row("tabnine")),
        )
        self.assertIn("[ ] claude", drawn)
        self.assertIn("[ ] opencode", drawn)
        self.assertIn("[ ] tabnine", drawn)
        self.assertIn("unique artifact(s) will be installed", drawn)
        self.assertIn("Choose at least one harness to install into.", drawn)
        self.assertIn("[Enter] Continue", drawn)

    def test_a_stale_choice_stays_visible_and_refuses_to_continue(self) -> None:
        source = _source()
        state = _state(targets=("removed-harness",))
        rows = source.rows(state)
        state = replace(state, rows=rows, cursor=len(rows) - 1)

        drawn = "\n".join(frame(source, state))

        self.assertEqual(rows[-1], target_row("removed-harness"))
        self.assertIn("[x] removed-harness", drawn)
        self.assertIn("removed-harness cannot host anything", drawn)
        self.assertIsNone(source.detail(state))

    def test_only_the_exact_reprepared_choice_can_continue(self) -> None:
        pending = _source(chosen=("opencode",))
        mismatch = _state(targets=("claude",))
        confirmed = _state(targets=("opencode",))

        self.assertIsNone(pending.detail(mismatch))
        self.assertIs(pending.detail(confirmed), ConsumerScreen.REMEDIATION)
        self.assertIn("Installing into: opencode", "\n".join(pending.status(confirmed)))

    def test_verbose_cursor_description_names_artifacts_the_harness_can_host(self) -> None:
        source = _source()
        state = _state(verbose=True)
        rows = source.rows(state)
        state = replace(state, rows=rows, cursor=1)

        described = "\n".join(source.description(state))

        self.assertIn("opencode", described)
        self.assertIn("company/mcp/github@1.0.0", described)

    def test_ready_names_the_chosen_harnesses_as_user_intent(self) -> None:
        rendered = "\n".join(
            render_ready(_view(chosen=("opencode", "tabnine")), PresentationProfile.FAST)
        )

        self.assertIn("Harnesses: opencode, tabnine", rendered)
        self.assertNotIn("every harness this machine measured", rendered)


class HarnessEligibilityProjectionTest(unittest.TestCase):
    def test_multi_artifact_eligibility_comes_from_each_real_placement_channel(self) -> None:
        def item(harness: str):
            return SimpleNamespace(harness=harness)

        prepared = SimpleNamespace(
            draft=SimpleNamespace(
                placements=(
                    SimpleNamespace(
                        coordinate="company/mcp/github@1.0.0",
                        targets=(item("claude"), item("opencode")),
                        deliveries=(),
                        merges=(),
                    ),
                    SimpleNamespace(
                        coordinate="company/skill/review@2.0.0",
                        targets=(),
                        deliveries=(item("claude"), item("tabnine")),
                        merges=(),
                    ),
                    SimpleNamespace(
                        coordinate="company/memory/rules@3.0.0",
                        targets=(),
                        deliveries=(),
                        merges=(item("opencode"),),
                    ),
                )
            )
        )

        projected = _installation_targets(  # type: ignore[arg-type]
            prepared, ("claude", "opencode", "tabnine", "cursor")
        )

        self.assertEqual(
            projected,
            (
                HarnessTargetView(
                    "claude",
                    ("company/mcp/github@1.0.0", "company/skill/review@2.0.0"),
                ),
                HarnessTargetView(
                    "opencode",
                    ("company/mcp/github@1.0.0", "company/memory/rules@3.0.0"),
                ),
                HarnessTargetView("tabnine", ("company/skill/review@2.0.0",)),
            ),
        )


class ChosenHarnessDeliveryE2ETest(unittest.TestCase):
    def _install(self, env, harness: str):
        offset = _COMPATIBLE.index(harness)
        finished, terminal, _handler = _drive(
            env,
            _at(ConsumerScreen.MARKETPLACE),
            SPACE,
            ord("i"),
            *((DOWN,) * offset),
            SPACE,
            ENTER,
            ENTER,
        )
        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        stored = LocalReceiptStore(str(env.paths.data_root) + "/state").installations()
        self.assertIsInstance(stored, Ok, getattr(stored, "diagnostics", ()))
        assert isinstance(stored, Ok)
        self.assertEqual(len(stored.value), 1)
        self.assertEqual(receipt_profiles(stored.value[0].receipt), frozenset({harness}))

    def test_skill_is_delivered_only_to_the_chosen_opencode_or_tabnine_target(self) -> None:
        destinations = {
            "claude": ".claude/skills/code-review/SKILL.md",
            "opencode": ".opencode/skills/code-review/SKILL.md",
            "tabnine": ".tabnine/agent/skills/code-review/SKILL.md",
        }
        for chosen in ("opencode", "tabnine"):
            with self.subTest(chosen=chosen), _environment(authored=_AUTHORED_SKILL) as env:
                self._install(env, chosen)

                for harness, relative in destinations.items():
                    self.assertEqual(
                        (env.project / relative).exists(),
                        harness == chosen,
                        f"{harness} delivery disagrees with {chosen} choice",
                    )

    def test_more_than_one_chosen_harness_is_delivered_and_recorded_exactly(self) -> None:
        with _environment(authored=_AUTHORED_SKILL) as env:
            finished, terminal, _handler = _drive(
                env,
                _at(ConsumerScreen.MARKETPLACE),
                SPACE,
                ord("i"),
                DOWN,
                SPACE,
                DOWN,
                SPACE,
                ENTER,
                ENTER,
            )

            self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
            self.assertFalse((env.project / ".claude/skills/code-review/SKILL.md").exists())
            self.assertTrue((env.project / ".opencode/skills/code-review/SKILL.md").is_file())
            self.assertTrue((env.project / ".tabnine/agent/skills/code-review/SKILL.md").is_file())
            stored = LocalReceiptStore(str(env.paths.data_root) + "/state").installations()
            assert isinstance(stored, Ok)
            self.assertEqual(
                receipt_profiles(stored.value[0].receipt),
                frozenset({"opencode", "tabnine"}),
            )

    def test_mcp_is_registered_only_with_the_chosen_opencode_or_tabnine_target(self) -> None:
        settings = {
            "claude": (".mcp.json", "mcpServers"),
            "opencode": ("opencode.json", "mcp"),
            "tabnine": (".tabnine/agent/settings.json", "mcpServers"),
        }
        for chosen in ("opencode", "tabnine"):
            with self.subTest(chosen=chosen), _environment(authored=_AUTHORED_MCP) as env:
                self._install(env, chosen)

                for harness, (relative, server_map) in settings.items():
                    path = env.project / relative
                    self.assertEqual(
                        path.exists(),
                        harness == chosen,
                        f"{harness} registration disagrees with {chosen} choice",
                    )
                    if harness == chosen:
                        document = json.loads(path.read_text(encoding="utf-8"))
                        self.assertIn("dummy", document[server_map])

    def test_execution_boundary_refuses_an_empty_choice_without_mutation(self) -> None:
        with _environment(authored=_AUTHORED_SKILL) as env:
            handler = _actions(env)
            prepared = handler.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.PREPARE_ACTION,
                    action=ConsumerActionKind.INSTALL,
                    selection=("company/skill/code-review@1.2.0",),
                )
            )
            self.assertIs(prepared.event.kind, ConsumerUiEventKind.ACTION_PREPARED)
            self.assertTrue(prepared.event.review_digest)

            refused = handler.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.EXECUTE_ACTION,
                    action=ConsumerActionKind.INSTALL,
                    selection=("company/skill/code-review@1.2.0",),
                    review_digest=prepared.event.review_digest,
                )
            )

            self.assertIs(refused.event.kind, ConsumerUiEventKind.ACTION_FAILED)
            self.assertIn(
                "no installation harness was chosen", "\n".join(refused.source.screens.notice)
            )
            self.assertFalse((env.project / ".claude").exists())
            self.assertFalse((env.project / ".opencode").exists())
            self.assertFalse((env.project / ".tabnine").exists())
            stored = LocalReceiptStore(str(env.paths.data_root) + "/state").installations()
            assert isinstance(stored, Ok)
            self.assertEqual(stored.value, ())

    def test_policy_refusal_never_exposes_targets_or_mutates_a_harness(self) -> None:
        with _environment(authored=_AUTHORED_SKILL) as env:
            composed = _actions(env)
            handler = LocalConsumerActions(
                replace(
                    composed._context,  # noqa: SLF001 - policy-bound composition under test
                    policy=EffectivePolicy(risk_ceiling=RiskClass.READ_ONLY),
                )
            )

            refused = handler.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.PREPARE_ACTION,
                    action=ConsumerActionKind.INSTALL,
                    selection=("company/skill/code-review@1.2.0",),
                )
            )

            self.assertIs(refused.event.kind, ConsumerUiEventKind.ACTION_PREPARED)
            self.assertFalse(refused.event.review_digest)
            self.assertIsNone(refused.source.screens.plan)
            self.assertFalse((env.project / ".claude").exists())
            self.assertFalse((env.project / ".opencode").exists())
            self.assertFalse((env.project / ".tabnine").exists())


if __name__ == "__main__":
    unittest.main()
