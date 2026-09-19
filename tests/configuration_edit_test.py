"""CP-23 task 16.4: a configuration edit is exactly the chosen harness files."""

from __future__ import annotations

import datetime as dt
import unittest
from dataclasses import replace

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.configuration_edit import plan_configuration_edit
from aart_cli.application.consumer_session import assemble_consumer_machine
from aart_cli.application.consumer_ui import (
    CONFIG_CONTINUE_ROW,
    ConsumerActionKind,
    ConsumerUiCommandKind,
    ConsumerUiState,
    InstallationConfigDraft,
    InstallationConfigField,
    key_event,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import (
    ConfigurationFileView,
    ConsumerScreen,
    ConsumerSession,
    LifecycleDriftView,
    LifecyclePlanView,
    PresentationProfile,
)
from aart_cli.domain.configuration_files import (
    ConfigurationFileRecord,
    render_configuration_file,
)
from aart_cli.domain.effects import WriteFile
from aart_cli.domain.identifiers import InputId
from aart_cli.domain.inputs import InputValidation
from aart_cli.domain.result import Err, Ok
from aart_cli.protocol.hashing import sha256_bytes
from aart_cli.tui_consumer import (
    CanonicalScreenSource,
    _reload,
    compose_frame,
    configuration_review_status,
    configuration_value_status,
    frame,
    screens_from,
)
from tests.consumer_session_test import inspection, receipt
from tests.credential_fixtures import access_token
from tests.frame_contract import frame_violations

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


def _source_and_state(values: dict[str, str] | None = None, *, lifecycle=None):
    coordinate = str(inspection().record.coordinate)
    held = values or {harness: "old-team" for harness in ("claude", "opencode", "tabnine")}
    configurations = tuple(
        ConfigurationFileView(
            coordinate,
            harness,
            f"/opt/agents/mcp/github/config/{harness}.conf",
            "matched",
            ((INPUT.value, value),),
        )
        for harness, value in held.items()
    )
    machine = assemble_consumer_machine(
        (inspection(),), configurations=configurations, today=dt.date(2026, 9, 14)
    )
    source = CanonicalScreenSource(replace(screens_from(machine), lifecycle=lifecycle))
    state = ConsumerUiState(
        ConsumerSession(ConsumerScreen.USER_INPUT_DETAILS),
        focus=coordinate,
        user_inputs_artifact=coordinate,
    )
    return source, _reload(source, state, entering=True)


def _cleared(source, state):
    while state.configuration_draft.value(INPUT.value):
        state, _ = _key(source, state, "backspace")
    return state


def _editing(source, state):
    """From 22a on the value row, through 22b with every harness ticked, onto 22c."""

    state, _ = _key(source, state, "enter")
    state, _ = _key(source, state, "enter")
    assert state.session.screen is ConsumerScreen.CONFIGURATION_VALUE
    return state


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

        state = _cleared(source, state)
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

        state = _cleared(source, state)
        state, _ = _key(source, state, credential)
        state, _ = _key(source, state, "enter")
        drawn = "\n".join(frame(source, state))

        self.assertFalse(state.configuration_draft.ready)
        self.assertNotIn(credential, drawn)
        self.assertIn("looks like a credential", drawn)


class ConfigurationValueOpensOnWhatIsHeldTest(unittest.TestCase):
    """CP-23 task 14: 22c opened empty although the chosen harnesses already hold a value."""

    def test_the_field_opens_holding_the_value_the_chosen_harnesses_share(self) -> None:
        source, state = _source_and_state()

        state = _editing(source, state)

        self.assertEqual(state.configuration_draft.value(INPUT.value), "old-team")
        self.assertFalse(state.configuration_draft.ready)
        self.assertIn(f"> {INPUT.value} [old-team]", source.actions(state))

    def test_harnesses_holding_different_values_open_an_empty_field_and_say_so(self) -> None:
        source, state = _source_and_state({"claude": "team-a", "opencode": "team-b"})

        state = _editing(source, state)

        self.assertEqual(state.configuration_draft.value(INPUT.value), "")
        status = "\n".join(source.status(state))
        self.assertIn("claude: team-a", status)
        self.assertIn("opencode: team-b", status)

    def test_entering_the_field_again_does_not_undo_what_was_typed(self) -> None:
        source, state = _source_and_state()
        state = _editing(source, state)
        state = _cleared(source, state)
        state, _ = _key(source, state, "typed")

        self.assertEqual(_reload(source, state).configuration_draft.value(INPUT.value), "typed")


_DIGEST = "sha256:" + "f" * 64


def _configure_plan(*harnesses: str) -> LifecyclePlanView:
    return LifecyclePlanView(
        "configure",
        str(inspection().record.coordinate),
        False,
        (),
        (),
        tuple(LifecycleDriftView(f"configuration:{item}", "changed", True) for item in harnesses),
        (),
        (),
        ("local-mutation",),
        True,
        _DIGEST,
    )


class ConfigurationReviewNamesTheChangeTest(unittest.TestCase):
    """CP-23 task 14: 22d said `Review configure for …` and a digest instead of the change."""

    def _review(self, profile: PresentationProfile = PresentationProfile.FAST):
        source, state = _source_and_state(
            {"claude": "old-team", "opencode": "old-team", "tabnine": "other-team"},
            lifecycle=_configure_plan("claude", "tabnine"),
        )
        draft = InstallationConfigDraft((InstallationConfigField(INPUT.value, "new-team"),))
        state = replace(
            state,
            session=ConsumerSession(ConsumerScreen.CONFIGURATION_REVIEW, profile),
            configuration_input=INPUT.value,
            configuration_targets=("claude", "tabnine"),
            configuration_draft=draft.accept(INPUT.value),
        )
        return source, _reload(source, state)

    def test_fast_names_the_input_and_each_harness_old_and_new_value(self) -> None:
        source, state = self._review()

        status = "\n".join(compose_frame(source, state).status)

        self.assertIn(f"Change {INPUT.value} for {inspection().record.coordinate}", status)
        self.assertIn("claude: old-team → new-team", status)
        self.assertIn("tabnine: other-team → new-team", status)
        self.assertNotIn("opencode", status)
        self.assertNotIn("Review configure", status)
        self.assertNotIn(_DIGEST, status)
        self.assertIn("Risks: local mutation.", status)
        self.assertEqual(frame_violations(source, state), ())

    def test_verbose_adds_the_review_identity(self) -> None:
        source, state = self._review(PresentationProfile.VERBOSE)

        status = "\n".join(compose_frame(source, state).status)

        self.assertIn(f"Review identity: {_DIGEST}", status)
        self.assertIn("claude: old-team → new-team", status)


class ConfigurationStatusWordsTest(unittest.TestCase):
    """22c and 22d's status, line for line (task 15: mutmut found the words and groups unheld)."""

    _KIND = (
        "This is ordinary configuration stored beside the artifact.",
        "Credentials stay with their provider and are not accepted here.",
    )

    def test_a_shared_value_says_what_is_changed_where_and_nothing_about_differing(self) -> None:
        held = (("claude", "same"), ("tabnine", "same"))

        status = configuration_value_status("c", "org", ("claude", "tabnine"), held)

        self.assertEqual(
            status, ("Change org for c", "Harnesses: claude, tabnine", "", *self._KIND)
        )

    def test_differing_values_list_each_harness_and_a_harness_with_none_is_not_set(self) -> None:
        held = (("claude", "team-a"), ("tabnine", None))

        status = configuration_value_status("c", "org", ("claude", "tabnine"), held)

        self.assertEqual(
            status,
            (
                "Change org for c",
                "Harnesses: claude, tabnine",
                "",
                "The chosen harnesses hold different values, so the field starts empty:",
                "  claude: team-a",
                "  tabnine: not set",
                "",
                *self._KIND,
            ),
        )

    def test_the_review_names_every_risk_and_says_read_only_when_there_is_none(self) -> None:
        plan = _configure_plan("claude", "tabnine")
        held = (("claude", "team-a"),)
        for risks, said in (
            ((), "Risks: read only."),
            (
                ("local-mutation", "configuration-mutation"),
                "Risks: local mutation, configuration mutation.",
            ),
        ):
            with self.subTest(risks=risks):
                status = configuration_review_status(
                    replace(plan, risks=risks), "org", held, "new", PresentationProfile.FAST
                )

                self.assertEqual(
                    status,
                    (
                        f"Change org for {plan.artifact}",
                        "  claude: team-a → new",
                        "  tabnine: not set → new",
                        "",
                        said,
                    ),
                )


if __name__ == "__main__":
    unittest.main()
