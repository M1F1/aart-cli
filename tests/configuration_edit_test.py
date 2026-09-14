"""CP-23 task 16.4: a configuration edit is exactly the chosen harness files."""

from __future__ import annotations

import datetime as dt
import unittest
from dataclasses import replace

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts.application.configuration_edit import plan_configuration_edit
from agent_artifacts.application.consumer_session import assemble_consumer_machine
from agent_artifacts.application.consumer_ui import (
    CONFIG_CONTINUE_ROW,
    ConsumerActionKind,
    ConsumerUiCommandKind,
    ConsumerUiState,
    key_event,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import (
    ConfigurationFileView,
    ConsumerScreen,
    ConsumerSession,
)
from agent_artifacts.domain.configuration_files import (
    ConfigurationFileRecord,
    render_configuration_file,
)
from agent_artifacts.domain.effects import WriteFile
from agent_artifacts.domain.identifiers import InputId
from agent_artifacts.domain.inputs import InputValidation
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.protocol.hashing import sha256_bytes
from agent_artifacts.tui_consumer import CanonicalScreenSource, _reload, frame, screens_from
from tests.consumer_session_test import inspection, receipt
from tests.credential_fixtures import access_token

INPUT = InputId("github-org")


def _configured(harnesses: tuple[str, ...]):
    base = receipt()
    contents = tuple(
        (
            harness,
            render_configuration_file(
                base.artifact, harness, ((INPUT, f"old-{harness}"),)
            ).encode(),
        )
        for harness in harnesses
    )
    records = tuple(
        ConfigurationFileRecord(
            harness,
            f"{base.root}/config/{harness}.conf",
            sha256_bytes(content),
        )
        for harness, content in contents
    )
    return replace(base, configuration_files=records), contents


class ConfigurationEditPlanningTest(unittest.TestCase):
    @given(selected=st.sets(st.sampled_from(("claude", "opencode", "tabnine")), min_size=1))
    def test_touched_components_equal_the_chosen_harnesses(self, selected: set[str]) -> None:
        receipt_value, contents = _configured(("claude", "opencode", "tabnine"))

        planned = plan_configuration_edit(
            receipt_value,
            input_id=INPUT,
            harnesses=tuple(sorted(selected)),
            value="new-team",
            current_files=contents,
        )

        self.assertIsInstance(planned, Ok, getattr(planned, "diagnostics", ()))
        assert isinstance(planned, Ok)
        touched = {
            component.id.name
            for component in planned.value.replacements
            if isinstance(component.effects[0], WriteFile)
        }
        self.assertEqual(touched, selected)
        self.assertEqual({item.harness for item in planned.value.files}, selected)
        unchanged = set(receipt_value.configuration_files) - {
            item.previous for item in planned.value.files
        }
        self.assertEqual(
            unchanged,
            set(planned.value.receipt.configuration_files)
            - {item.updated for item in planned.value.files},
        )

    @given(
        value=st.sampled_from(
            (
                access_token("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
                "github" + "_pat_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
                "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            )
        )
    )
    def test_credential_shapes_are_refused_without_echoing_them(self, value: str) -> None:
        receipt_value, contents = _configured(("claude",))

        planned = plan_configuration_edit(
            receipt_value,
            input_id=INPUT,
            harnesses=("claude",),
            value=value,
            current_files=contents,
        )

        self.assertIsInstance(planned, Err)
        self.assertNotIn(value, repr(planned))
        self.assertIn("credential", planned.diagnostics[0].message)

    def test_empty_stale_and_changed_selections_are_refused(self) -> None:
        receipt_value, contents = _configured(("claude", "tabnine"))
        cases = (
            ((), contents, "at least one"),
            (("removed",), contents, "not installed"),
            (("claude",), (("claude", b"changed elsewhere\n"),), "changed outside AART"),
        )
        for selected, current, message in cases:
            with self.subTest(selected=selected):
                planned = plan_configuration_edit(
                    receipt_value,
                    input_id=INPUT,
                    harnesses=selected,
                    value="new-team",
                    current_files=current,
                )
                self.assertIsInstance(planned, Err)
                self.assertIn(message, planned.diagnostics[0].message)

    def test_declared_validation_refuses_without_echoing_the_candidate(self) -> None:
        receipt_value, contents = _configured(("claude",))
        candidate = "not/the-required-shape"

        planned = plan_configuration_edit(
            receipt_value,
            input_id=INPUT,
            harnesses=("claude",),
            value=candidate,
            current_files=contents,
            validation=InputValidation("pattern", pattern=r"[a-z]+-[a-z]+"),
        )

        self.assertIsInstance(planned, Err)
        self.assertNotIn(candidate, repr(planned))
        self.assertIn("declared pattern rule", planned.diagnostics[0].message)


def _source_and_state():
    coordinate = str(inspection().record.coordinate)
    configurations = tuple(
        ConfigurationFileView(
            coordinate,
            harness,
            f"/opt/agents/mcp/github/config/{harness}.conf",
            "matched",
            ((INPUT.value, "old-team"),),
        )
        for harness in ("claude", "opencode", "tabnine")
    )
    machine = assemble_consumer_machine(
        (inspection(),), configurations=configurations, today=dt.date(2026, 9, 14)
    )
    source = CanonicalScreenSource(screens_from(machine))
    state = ConsumerUiState(
        ConsumerSession(ConsumerScreen.USER_INPUT_DETAILS),
        focus=coordinate,
        user_inputs_artifact=coordinate,
    )
    return source, _reload(source, state, entering=True)


def _key(source, state, key):
    event = key_event(key, state, detail=source.detail(state))
    assert event is not None, (key, state.session.screen, state.rows)
    changed, commands = reduce_consumer_ui(state, event)
    entering = changed.session.screen is not state.session.screen
    return _reload(source, changed, entering=entering), commands


class ConfigurationEditInteractionTest(unittest.TestCase):
    def test_configuration_row_opens_all_harnesses_selected_and_empty_cannot_continue(self) -> None:
        source, state = _source_and_state()

        state, _ = _key(source, state, "enter")

        self.assertIs(state.session.screen, ConsumerScreen.CONFIGURATION_TARGETS)
        self.assertEqual(set(state.configuration_targets), {"claude", "opencode", "tabnine"})
        self.assertIn("[x] claude", "\n".join(frame(source, state)))
        for harness in ("claude", "opencode", "tabnine"):
            while state.current_row != f"target:{harness}":
                state, _ = _key(source, state, "down")
            state, _ = _key(source, state, " ")
        self.assertEqual(state.configuration_targets, ())
        self.assertIsNone(key_event("enter", state, detail=source.detail(state)))

    def test_chosen_harnesses_and_accepted_value_become_one_prepare_command(self) -> None:
        source, state = _source_and_state()
        state, _ = _key(source, state, "enter")
        while state.current_row != "target:opencode":
            state, _ = _key(source, state, "down")
        state, _ = _key(source, state, " ")
        state, _ = _key(source, state, "enter")
        self.assertIs(state.session.screen, ConsumerScreen.CONFIGURATION_VALUE)

        state, _ = _key(source, state, "new-team")
        state, _ = _key(source, state, "enter")
        self.assertTrue(state.configuration_draft.ready)
        self.assertEqual(state.current_row, CONFIG_CONTINUE_ROW)
        state, commands = _key(source, state, "enter")

        self.assertIs(state.session.screen, ConsumerScreen.CONFIGURATION_REVIEW)
        prepare = next(
            item for item in commands if item.kind is ConsumerUiCommandKind.PREPARE_ACTION
        )
        self.assertIs(prepare.action, ConsumerActionKind.CONFIGURE)
        self.assertEqual(prepare.focus, str(inspection().record.coordinate))
        self.assertEqual(set(prepare.targets), {"claude", "tabnine"})
        self.assertEqual(prepare.config_answers, ((INPUT.value, "new-team"),))

    def test_a_credential_shaped_edit_is_masked_and_cannot_be_submitted(self) -> None:
        source, state = _source_and_state()
        state, _ = _key(source, state, "enter")
        state, _ = _key(source, state, "enter")
        credential = access_token("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")

        state, _ = _key(source, state, credential)
        state, _ = _key(source, state, "enter")
        drawn = "\n".join(frame(source, state))

        self.assertFalse(state.configuration_draft.ready)
        self.assertNotIn(credential, drawn)
        self.assertIn("looks like a credential", drawn)


if __name__ == "__main__":
    unittest.main()
