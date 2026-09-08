"""B-083/QA-009: the Maintainer shell can subscribe to an authoring Source.

Maintainer Sources could inspect and synchronize a configured authoring Source but could not
create one, so the TUI could not build the precondition its own Candidate and Promotion screens
need. The operator had to leave for a terminal, run `aart source add`, and come back.

This is deliberately not a widening of Add Registry. Product Specification 164.2 makes a Source an
authoring/discovery location that is *not* an approved registry; screen 21a accepts only an
approved remote Git registry, and teaching it `source-git` would erase that boundary. The surface
added here is a Maintainer form that chooses `source-git` or `source-local` explicitly, reviews the
exact identity, and runs the same canonical source-add transaction the CLI runs.
"""

from __future__ import annotations

import unittest
from unittest import mock

from agent_artifacts.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    SourceDraft,
    key_event,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
)
from agent_artifacts.application.maintainer_views import MaintainerScreen
from agent_artifacts.domain.result import Ok
from agent_artifacts.tui_consumer import CanonicalScreenSource, frame
from tests.consumer_shell_test import screens


def _state(screen, **changes) -> ConsumerUiState:
    return ConsumerUiState(
        ConsumerSession(screen),
        settings=ConsumerSettings().with_maintainer_mode(True),
        **changes,
    )


class MaintainerSourceAdditionInteractionTest(unittest.TestCase):
    def test_maintainer_sources_offers_a_real_add_route(self) -> None:
        state = _state(MaintainerScreen.SOURCES)

        event = key_event("a", state)

        self.assertIsNotNone(event)
        assert event is not None
        self.assertIs(event.kind, ConsumerUiEventKind.NAVIGATE)
        self.assertIs(event.screen, MaintainerScreen.SOURCE_ADD)

    def test_the_add_route_is_not_reachable_with_maintainer_mode_off(self) -> None:
        """The Source screens are the mode's, and so is the form that creates one."""

        state = ConsumerUiState(ConsumerSession(ConsumerScreen.REGISTRIES))

        event = key_event("a", state)

        self.assertIsNotNone(event)
        assert event is not None
        self.assertIs(event.screen, ConsumerScreen.REGISTRY_ADD)

    def test_the_form_names_the_two_authoring_kinds_and_the_fields_each_needs(self) -> None:
        state = _state(MaintainerScreen.SOURCE_ADD)
        source = CanonicalScreenSource(screens())
        state, _ = reduce_consumer_ui(
            state,
            ConsumerUiEvent(ConsumerUiEventKind.SET_ROWS, rows=source.rows(state)),
        )

        drawn = "\n".join(frame(source, state))

        self.assertIn("Alias", drawn)
        self.assertIn("Kind", drawn)
        self.assertIn("source-git", drawn)
        self.assertIn("Location", drawn)
        self.assertIn("Branch or tag", drawn)

    def test_space_chooses_between_the_two_kinds_and_nothing_else(self) -> None:
        state = _state(
            MaintainerScreen.SOURCE_ADD,
            rows=("alias", "kind", "location", "ref", "connect"),
            cursor=1,
        )

        self.assertEqual(state.source_draft.kind, "source-git")
        state, _ = reduce_consumer_ui(state, key_event(" ", state))  # type: ignore[arg-type]
        self.assertEqual(state.source_draft.kind, "source-local")
        state, _ = reduce_consumer_ui(state, key_event(" ", state))  # type: ignore[arg-type]
        self.assertEqual(state.source_draft.kind, "source-git")

    def test_typing_a_url_stays_text_rather_than_firing_hotkeys(self) -> None:
        state = _state(
            MaintainerScreen.SOURCE_ADD,
            rows=("alias", "kind", "location", "ref", "connect"),
        )

        for character in "superpowers":
            state, _ = reduce_consumer_ui(state, key_event(character, state))  # type: ignore[arg-type]

        self.assertEqual(state.source_draft.alias, "superpowers")
        self.assertEqual(state.cursor, 0)

    def test_confirming_the_form_carries_the_exact_draft_into_one_review(self) -> None:
        draft = SourceDraft("superpowers", "source-git", "https://git.example/sp.git", "main")
        state = _state(
            MaintainerScreen.SOURCE_ADD,
            rows=("alias", "kind", "location", "ref", "connect"),
            source_draft=draft,
            cursor=4,
        )

        event = key_event("enter", state)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertIs(event.kind, ConsumerUiEventKind.REQUEST_ACTION)

        reviewed, commands = reduce_consumer_ui(state, event)

        self.assertIs(reviewed.session.screen, MaintainerScreen.SOURCE_ADD_REVIEW)
        self.assertIs(reviewed.action, ConsumerActionKind.SOURCE_ADD)
        self.assertEqual(commands[0].source_draft, draft)
        self.assertIs(commands[0].action, ConsumerActionKind.SOURCE_ADD)


class MaintainerSourceAdditionCompositionTest(unittest.TestCase):
    """The form runs the same transaction as the CLI, not a second implementation of it."""

    def _composed(self, env):
        from agent_artifacts import tui

        composed = tui._canonical_consumer_actions(
            project=str(env.project), user_home=str(env.home), today=tui.date.today()
        )
        assert isinstance(composed, Ok), composed
        return composed.value

    def test_the_composed_action_calls_the_canonical_source_add_transaction(self) -> None:
        """Both kinds, because the kind the form chose is the thing being carried.

        One kind would leave `source_kind` provably free to be a constant: `source-git` is the
        default a hardcoded value would happen to match, so only the local case can catch it.
        """

        from tests.configured_install_command_e2e_test import _environment

        drafts = (
            SourceDraft("superpowers", "source-git", "https://git.example/sp.git", "main"),
            SourceDraft("local-authors", "source-local", "/srv/authors", ""),
        )
        for draft in drafts:
            with self.subTest(kind=draft.kind):
                from tests.configured_install_command_e2e_test import _environment

                with _environment() as env, mock.patch.dict(env.xdg, clear=False):
                    actions = self._composed(env)
                    connector = actions._source_connection
                    self.assertIsNotNone(connector)
                    with mock.patch(
                        "agent_artifacts.commands.source.add_configured_source",
                        return_value=Ok(object()),
                    ) as add:
                        connected = connector(draft)  # type: ignore[misc]

                self.assertIsInstance(connected, Ok, connected)
                request = add.call_args.args[0]
                self.assertEqual(request.source_alias, draft.alias)
                self.assertEqual(request.source_kind, draft.kind)
                self.assertEqual(request.source_location, draft.location)
                self.assertEqual(request.ref, draft.ref or None)
                # An authoring Source is never a default registry: that flag is screen 21a's.
                self.assertIs(request.source_make_default, False)

    def test_a_local_authoring_path_is_accepted_where_a_registry_would_be_refused(self) -> None:
        """The whole point of the separate form: 164.2's local authoring case has a home."""

        from tests.configured_install_command_e2e_test import _environment

        with _environment() as env, mock.patch.dict(env.xdg, clear=False):
            actions = self._composed(env)
            calls: list[SourceDraft] = []
            actions._source_connection = lambda value: (
                calls.append(value)
                or Ok(  # type: ignore[assignment,func-returns-value]
                    actions._context
                )
            )
            draft = SourceDraft("local-authors", "source-local", str(env.project), "")
            prepared = actions.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.PREPARE_ACTION,
                    action=ConsumerActionKind.SOURCE_ADD,
                    source_draft=draft,
                )
            )

        self.assertTrue(prepared.event.review_digest)
        notice = "\n".join(prepared.source.screens.notice)
        self.assertIn("Source connection review", notice)
        self.assertIn("source-local", notice)

    def test_a_kind_screen_21a_owns_is_refused_by_this_form(self) -> None:
        from tests.configured_install_command_e2e_test import _environment

        with _environment() as env, mock.patch.dict(env.xdg, clear=False):
            actions = self._composed(env)
            called: list[SourceDraft] = []
            actions._source_connection = lambda value: called.append(value)  # type: ignore[assignment,func-returns-value]
            update = actions.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.PREPARE_ACTION,
                    action=ConsumerActionKind.SOURCE_ADD,
                    source_draft=SourceDraft("company", "registry-git", "https://x/y.git", "main"),
                )
            )

        self.assertEqual(called, [])
        self.assertEqual(update.event.review_digest, "")


if __name__ == "__main__":
    unittest.main()
