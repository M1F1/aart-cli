"""CP-32.13: the focused offer's full details stay under Marketplace More info."""

from __future__ import annotations

import dataclasses
import re
import unittest

from aart_cli.application.consumer_ui import key_event, reduce_consumer_ui
from aart_cli.application.consumer_views import (
    ConfigInputView,
    ConsumerScreen,
    CredentialInputView,
    PresentationProfile,
)
from aart_cli.application.credential_guidance import CredentialGuidance
from aart_cli.tui_consumer import (
    MarketplaceEntry,
    _reload,
    frame,
    render_marketplace_artifact,
)
from tests.marketplace_cursor_description_test import _distinct, _listed, _on


def _flat(lines):
    return "".join("".join(lines).split())


class MarketplaceInlineDetailsTest(unittest.TestCase):
    def test_every_previous_details_field_is_available_on_the_focused_offer(self):
        screens = _distinct()
        entry = screens.marketplace[0]
        row = dataclasses.replace(
            entry.row,
            source_origin="https://registry.example/approved.git",
            source_revision="f" * 40,
            manifest_digest="sha256:" + "1" * 64,
            payload_digest="sha256:" + "2" * 64,
            object_digest="sha256:" + "3" * 64,
            trust_evidence_digest="sha256:" + "4" * 64,
        )
        screens = dataclasses.replace(
            screens, marketplace=(MarketplaceEntry(row), *screens.marketplace[1:])
        )
        source, state = _listed(screens)
        state = _on(state, row.key)
        description = source.description(state)
        previous = render_marketplace_artifact(row, PresentationProfile.MORE_INFO)
        for line in previous:
            if line.strip():
                self.assertIn(_flat((line,)), _flat(description), line)
        for value in (
            row.source_origin,
            row.source_revision,
            row.manifest_digest,
            row.payload_digest,
            row.object_digest,
            row.trust_evidence_digest,
        ):
            self.assertIn(value, _flat(description))
        self.assertIs(state.session.screen, ConsumerScreen.MARKETPLACE)
        self.assertIn("registry.example", "\n".join(frame(source, state)))

    def test_enter_does_not_open_another_artifact_view_or_change_browsing_state(self):
        source, state = _listed(_distinct(), profile=PresentationProfile.LESS_INFO)
        state = _reload(source, dataclasses.replace(state, search="review"))
        self.assertTrue(state.rows)
        state = dataclasses.replace(state, selection=(state.current_row,))
        event = key_event("enter", state, detail=source.detail(state))
        after, commands = (state, ()) if event is None else reduce_consumer_ui(state, event)
        self.assertEqual(after, state)
        self.assertEqual(commands, ())
        verbose, _ = reduce_consumer_ui(state, key_event("v", state))
        self.assertEqual(
            (verbose.selection, verbose.search, verbose.cursor),
            (state.selection, state.search, state.cursor),
        )
        self.assertIs(verbose.session.screen, ConsumerScreen.MARKETPLACE)
        self.assertIn("security", "\n".join(source.description(verbose)))

    def test_declared_input_guidance_is_disclosed_without_an_installation_answer(self):
        screens = _distinct()
        entry = screens.marketplace[0]
        field = ConfigInputView(
            "site",
            "Service site",
            True,
            "environment",
            "process-env",
            "Choose your company's service URL.",
            "https://example.test",
            "an HTTPS URL",
            ("Service settings", "https://help.example.test/settings"),
            "Must use HTTPS",
            "https://default.example.test",
            "installation-only-answer",
            True,
            "persisted",
        )
        entry = dataclasses.replace(entry, inputs=(field,))
        screens = dataclasses.replace(screens, marketplace=(entry, *screens.marketplace[1:]))
        source, state = _listed(screens)
        shown = "\n".join(source.description(_on(state, entry.key)))
        for value in (
            field.label,
            field.description,
            field.format_hint,
            field.validation_hint,
            field.obtain_from[0],
            field.obtain_from[1],
            field.default,
            field.example,
            field.binding,
            field.exposure,
        ):
            self.assertIn(value, shown)
        self.assertNotIn(field.current, shown)
        self.assertIn(f"({field.id})", shown)
        self.assertIn("Configuration", shown)
        self.assertRegex(shown, r"Declared required\s+yes")
        for label, value in (
            ("Input", f"{field.label} ({field.id})"),
            ("Type", "Configuration"),
            ("Binding", f"{field.binding} ({field.exposure})"),
            ("Description", field.description),
            ("Format", field.format_hint),
            ("Get from", field.obtain_from[0]),
            ("Guide", field.obtain_from[1]),
            ("Example", field.example),
            ("Validation", field.validation_hint),
            ("Declared default", field.default),
        ):
            self.assertRegex(
                shown,
                re.compile(
                    r"^  " + re.escape(label) + r" +" + re.escape(value) + r"$", re.MULTILINE
                ),
            )

    def test_optional_declarations_need_no_missing_guidance_fields(self):
        screens = _distinct()
        field = ConfigInputView(
            "site",
            "Service site",
            False,
            "environment",
            "process-env",
            "",
            None,
            None,
            None,
            "",
            None,
            None,
            False,
            None,
        )
        entry = dataclasses.replace(screens.marketplace[0], inputs=(field,))
        screens = dataclasses.replace(screens, marketplace=(entry, *screens.marketplace[1:]))
        source, state = _listed(screens)
        shown = "\n".join(source.description(_on(state, entry.key)))
        self.assertIn("Service site", shown)
        self.assertNotIn("None", shown)

    def test_secret_guidance_does_not_disclose_an_existing_owners_provider_state(self):
        screens = _distinct()
        field = CredentialInputView(
            "api-token",
            "API token",
            False,
            "environment",
            "process-env",
            "Create a token for the declared read-only operation.",
            "A service token",
            ("API settings", "https://help.example.test/api"),
            "owner-only-reference",
            "macos-keychain",
            "available",
            "present",
            "owner-only-detail",
        )
        group = CredentialGuidance(
            (screens.marketplace[0].key,),
            "Read-only service token",
            description="Grant read scope for the advertised operation.",
            obtain_label="Service access settings",
            obtain_url="https://help.example.test/read-only-token",
            validation_hint="Select the read scope.",
        )
        field = dataclasses.replace(field, guidance=(group,))
        entry = dataclasses.replace(screens.marketplace[0], inputs=(field,))
        screens = dataclasses.replace(screens, marketplace=(entry, *screens.marketplace[1:]))
        source, state = _listed(screens)
        shown = "\n".join(source.description(_on(state, entry.key)))
        for value in (
            field.label,
            field.description,
            field.format_hint,
            field.obtain_from[0],
            field.obtain_from[1],
        ):
            self.assertIn(value, shown)
        for value in (
            group.label,
            group.description,
            group.obtain_label,
            group.obtain_url,
            group.validation_hint,
        ):
            self.assertIn(value, shown)
        self.assertRegex(shown, re.compile(r"^  Type +Credential$", re.MULTILINE))
        self.assertRegex(shown, r"Declared required\s+no")
        self.assertNotIn(field.provider_reference, shown)
        self.assertNotIn(field.detail, shown)
