"""`QA-028`: a new form opens empty, and a refused one keeps what was typed.

Adding a second Source opened screen 31a still holding the first Source's alias, URL and branch,
with nothing on screen saying whether confirming would edit that subscription or create another.
In the operator's words: they could not tell whether they were replacing the old Source or adding a
completely new one.

The draft lives in `ConsumerUiState` and was never reset, which is also what makes `QA-018` work:
when a preparation refuses, the session returns to the form with everything still in it, because
retyping a whole form to fix one field is the defect `D-184` closed. So the reset belongs on
*entering* the form, not on leaving it -- the two look alike from the screen and are opposite
requirements.
"""

from __future__ import annotations

import unittest

from aart_cli.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    RegistryDraft,
    RegistryInitDraft,
    RepositoryScanDraft,
    SourceDraft,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
)
from aart_cli.application.maintainer_views import MaintainerScreen

TYPED = {
    "registry_draft": RegistryDraft(alias="old", location="https://git.example/old.git"),
    "source_draft": SourceDraft(alias="old", location="https://git.example/old.git"),
    "registry_init_draft": RegistryInitDraft(registry_id="old", display_name="Old"),
    "repository_scan_draft": RepositoryScanDraft(url="https://git.example/old.git"),
}

#: Each form, the list it is opened from, and the draft field it owns.
FORMS: tuple[tuple[object, object, str], ...] = (
    (ConsumerScreen.REGISTRIES, ConsumerScreen.REGISTRY_ADD, "registry_draft"),
    (MaintainerScreen.SOURCES, MaintainerScreen.SOURCE_ADD, "source_draft"),
    (MaintainerScreen.REGISTRY, MaintainerScreen.REGISTRY_INIT, "registry_init_draft"),
    (MaintainerScreen.REGISTRY, MaintainerScreen.REPOSITORY_SCAN, "repository_scan_draft"),
)


def _holding(screen) -> ConsumerUiState:
    """A session on `screen` still carrying every draft somebody typed earlier."""

    return ConsumerUiState(
        ConsumerSession(screen),
        settings=ConsumerSettings().with_maintainer_mode(True),
        **TYPED,
    )


class FormDraftLifecycleTest(unittest.TestCase):
    def test_opening_a_form_gives_a_new_one(self) -> None:
        for origin, form, field in FORMS:
            with self.subTest(form=form):
                opened, _ = reduce_consumer_ui(
                    _holding(origin),
                    ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=form),
                )

                self.assertEqual(getattr(opened, field), type(TYPED[field])())

    def test_opening_one_form_leaves_the_others_alone(self) -> None:
        """Each form owns its own draft; entering one is not a reason to discard another."""

        for origin, form, field in FORMS:
            with self.subTest(form=form):
                opened, _ = reduce_consumer_ui(
                    _holding(origin),
                    ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=form),
                )

                for other, typed in TYPED.items():
                    if other != field:
                        self.assertEqual(getattr(opened, other), typed)

    def test_a_refused_preparation_returns_to_the_form_still_holding_it(self) -> None:
        """`QA-018`/`D-184`: the reset is on entry precisely so this stays true."""

        for origin, form, field in FORMS[:3]:
            review = {
                ConsumerScreen.REGISTRY_ADD: ConsumerScreen.REGISTRY_REVIEW,
                MaintainerScreen.SOURCE_ADD: MaintainerScreen.SOURCE_ADD_REVIEW,
                MaintainerScreen.REGISTRY_INIT: MaintainerScreen.REGISTRY_INIT_REVIEW,
            }[form]
            action = {
                ConsumerScreen.REGISTRY_ADD: ConsumerActionKind.REGISTRY_ADD,
                MaintainerScreen.SOURCE_ADD: ConsumerActionKind.SOURCE_ADD,
                MaintainerScreen.REGISTRY_INIT: ConsumerActionKind.REGISTRY_INIT,
            }[form]
            with self.subTest(form=form):
                on_review = ConsumerUiState(
                    ConsumerSession(review, history=(origin, form)),
                    settings=ConsumerSettings().with_maintainer_mode(True),
                    action=action,
                    **TYPED,
                )

                declined, _ = reduce_consumer_ui(
                    on_review,
                    ConsumerUiEvent(ConsumerUiEventKind.ACTION_PREPARED, action=action),
                )

                self.assertIs(declined.session.screen, form)
                self.assertEqual(getattr(declined, field), TYPED[field])

    def test_stepping_back_onto_a_form_does_not_throw_the_typing_away(self) -> None:
        """Esc from the review is somebody going back to edit, not opening a new form."""

        for origin, form, field in FORMS[:3]:
            with self.subTest(form=form):
                on_review = ConsumerUiState(
                    ConsumerSession(form, history=(origin,)),
                    settings=ConsumerSettings().with_maintainer_mode(True),
                    **TYPED,
                )
                stepped, _ = reduce_consumer_ui(
                    on_review, ConsumerUiEvent(ConsumerUiEventKind.BACK)
                )

                self.assertEqual(getattr(stepped, field), TYPED[field])


class NewSubscriptionIsStatedTest(unittest.TestCase):
    """The other half of the operator's question: an empty form, and what confirming it means."""

    def _body(self, screen) -> str:
        from aart_cli.tui_consumer import CanonicalScreenSource, frame
        from tests.consumer_shell_test import screens

        state = ConsumerUiState(
            ConsumerSession(screen),
            settings=ConsumerSettings().with_maintainer_mode(True),
            rows=("alias",),
        )
        return "\n".join(frame(CanonicalScreenSource(screens()), state))

    def test_the_add_forms_say_they_do_not_replace_what_is_connected(self) -> None:
        for screen, noun in (
            (ConsumerScreen.REGISTRY_ADD, "registry"),
            (MaintainerScreen.SOURCE_ADD, "Source"),
        ):
            with self.subTest(screen=screen):
                self.assertIn(
                    f"This adds another {noun}. Nothing already connected is changed.",
                    self._body(screen),
                )


if __name__ == "__main__":
    unittest.main()
