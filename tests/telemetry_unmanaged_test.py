"""CP-52, D-508: uses of skills and MCPs aart-cli did not install are sent unless chosen not to.

§213 as amended, INV-323, INV-330. The build sets the default with the release variable
`AART_CLI_TELEMETRY_UNMANAGED_USES` (unset sends them); a person changes it at any time in Settings
or with `consume telemetry unmanaged on|off`. It is read when events are sent, so a use waiting
when it is turned off is skipped, never sent.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import string
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from hypothesis import given
from hypothesis import strategies as st

from aart_cli import _default_telemetry, cli
from aart_cli.application.consumer_views import (
    SETTING_ROWS,
    ConsumerSettings,
    setting_purpose,
    settings_from_data,
    settings_to_data,
)
from aart_cli.configuration.seed import baked_unmanaged_uses
from aart_cli.domain.artifact_usage import InstalledName, UsageKind, resolve_installed
from aart_cli.domain.result import Err, Ok
from aart_cli.domain.telemetry import (
    UNMANAGED_USED,
    TelemetryEvent,
    parse_unmanaged_uses,
    use_event,
)
from aart_cli.io.consumer_settings import read_consumer_settings, write_consumer_settings
from aart_cli.io.telemetry_consent import announce_turned_on
from aart_cli.io.telemetry_store import TelemetrySetting
from aart_cli.tui_consumer import render_settings
from tests.release_default_telemetry_injection_test import _load
from tests.telemetry_sync_test import Clock, FakeServer, Home, _sync

ID = "7515ec68-1e98-46ca-bd90-9f6a70c84d11"
MOMENT = "2026-10-30T09:00:00Z"
INSTALLED = (
    InstalledName("claude", UsageKind.SKILL, "release-notes", "corp/skill/release-notes", "1.2.0"),
    InstalledName("opencode", UsageKind.MCP, "jira", "corp/mcp/jira-mcp", "2.0.1"),
)
ROW = "telemetry-unmanaged"


class AUseIsSentAsWhatItIsTest(unittest.TestCase):
    def test_a_use_nothing_installed_answers_to_is_sent_by_the_name_the_harness_used(
        self,
    ) -> None:
        for harness, kind, name, source in (
            ("claude", UsageKind.SKILL, "superpowers:brainstorming", "claude_hook"),
            ("claude", UsageKind.MCP, "context7", "claude_hook"),
            ("opencode", UsageKind.MCP, "context7_resolve-library-id", "opencode_plugin"),
        ):
            with self.subTest(name=name):
                event = use_event(ID, MOMENT, harness, kind, name, INSTALLED, unmanaged=True)

                self.assertEqual(
                    event.document(),
                    {
                        "event_id": ID,
                        "occurred_at": MOMENT,
                        "event_type": UNMANAGED_USED,
                        "source": source,
                        "artifact_id": name,
                        "artifact_type": kind.value,
                    },
                )

    def test_without_the_choice_it_is_not_an_event(self) -> None:
        self.assertIsNone(
            use_event(ID, MOMENT, "claude", UsageKind.SKILL, "brainstorming", INSTALLED)
        )

    def test_an_installed_artifact_is_never_sent_as_unmanaged(self) -> None:
        event = use_event(
            ID, MOMENT, "opencode", UsageKind.MCP, "jira_search", INSTALLED, unmanaged=True
        )

        self.assertEqual(
            (event.event_type, event.artifact_id, event.artifact_version),
            ("artifact.used", "jira-mcp", "2.0.1"),
        )

    def test_a_name_the_contract_cannot_carry_is_not_sent(self) -> None:
        for name in ("my skill", "team/skill", "x" * 201):
            with self.subTest(name=name):
                self.assertIsNone(
                    use_event(ID, MOMENT, "claude", UsageKind.SKILL, name, (), unmanaged=True)
                )

    def test_an_unmanaged_use_never_carries_a_version_or_comes_from_aart_cli(self) -> None:
        for source, version in (("claude_hook", "1.0.0"), ("aart_cli", None)):
            with self.subTest(source=source), self.assertRaises(ValueError):
                TelemetryEvent(
                    ID, MOMENT, UNMANAGED_USED, source, "brainstorming", "skill", version
                )


_NAMES = st.text(alphabet=string.ascii_lowercase + "-_:", min_size=1, max_size=12)


@given(
    harness=st.sampled_from(("claude", "opencode")),
    kind=st.sampled_from(tuple(UsageKind)),
    name=_NAMES,
    installed=st.lists(
        st.tuples(
            st.sampled_from(("claude", "opencode")), st.sampled_from(tuple(UsageKind)), _NAMES
        ),
        max_size=4,
    ),
    unmanaged=st.booleans(),
)
def test_each_use_is_sent_once_as_the_installation_or_by_its_own_name_only_when_chosen(
    harness, kind, name, installed, unmanaged
) -> None:
    """INV-323, INV-330: attributed means `artifact.used`; otherwise only when chosen."""

    names = tuple(
        InstalledName(where, what, called, f"corp/{what.value}/{called.replace(':', '-')}", "1.0")
        for where, what, called in installed
    )
    resolved = resolve_installed(harness, kind, name, names)
    event = use_event(ID, MOMENT, harness, kind, name, names, unmanaged=unmanaged)

    if resolved is not None:
        assert event == use_event(ID, MOMENT, harness, kind, name, names)
        assert event is not None and event.event_type == "artifact.used"
    elif unmanaged:
        assert event is not None
        assert (event.event_type, event.artifact_id, event.artifact_version) == (
            UNMANAGED_USED,
            name,
            None,
        )
    else:
        assert event is None


class TheBuildSetsTheDefaultTest(unittest.TestCase):
    def test_unset_and_on_send_them_off_does_not_anything_else_is_refused(self) -> None:
        for raw, expected in (
            ("", True),
            ("  ", True),
            ("on", True),
            ("TRUE", True),
            (" off\n", False),
            ("false", False),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(parse_unmanaged_uses(raw), Ok(expected))
        for raw in ("no", "0", "maybe"):
            with self.subTest(raw=raw):
                self.assertIsInstance(parse_unmanaged_uses(raw), Err)

    def test_the_source_tree_sends_them_and_a_refused_value_sends_nothing(self) -> None:
        self.assertEqual(_default_telemetry.UNMANAGED_USES, "")
        self.assertTrue(baked_unmanaged_uses())
        self.assertFalse(baked_unmanaged_uses("off"))
        self.assertFalse(baked_unmanaged_uses("maybe"))

    def test_the_injector_bakes_it_beside_the_address_and_refuses_what_aart_cli_would(
        self,
    ) -> None:
        injector = _load("inject_default_telemetry")
        namespace: dict[str, object] = {}
        rendered = injector.render_from("", "test", unmanaged=" OFF ")
        exec(compile(rendered, "<rendered>", "exec"), namespace)  # noqa: S102

        self.assertEqual((namespace["ENDPOINT"], namespace["UNMANAGED_USES"]), ("", "off"))
        self.assertFalse(baked_unmanaged_uses(str(namespace["UNMANAGED_USES"])))
        with self.assertRaises(SystemExit):
            injector.render_from("", "test", unmanaged="maybe")

    def test_the_release_passes_it_and_its_receipt_records_it(self) -> None:
        root = Path(__file__).resolve().parent.parent
        workflow = (root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        variable = "AART_CLI_TELEMETRY_UNMANAGED_USES"

        self.assertEqual(workflow.count(f"{variable}: ${{{{ vars.{variable} }}}}"), 2)
        release = _load("release")
        # The receipt records what the injected build does, for every value the injector accepts.
        for raw in ("", "on", "true", "off", "false", " Off\n", "FALSE"):
            with self.subTest(raw=raw), mock.patch.dict(os.environ, {variable: raw}):
                self.assertEqual(
                    release.telemetry_unmanaged_uses_value(), parse_unmanaged_uses(raw).value
                )


class APersonChoosesInSettingsTest(unittest.TestCase):
    def test_nobody_chose_means_the_build_decides_and_a_choice_overrules_it(self) -> None:
        self.assertIsNone(ConsumerSettings().telemetry_unmanaged)
        with mock.patch.object(_default_telemetry, "UNMANAGED_USES", "off"):
            self.assertFalse(ConsumerSettings().sends_unmanaged_uses)
            self.assertTrue(ConsumerSettings(telemetry_unmanaged=True).sends_unmanaged_uses)
        self.assertTrue(ConsumerSettings().sends_unmanaged_uses)
        self.assertFalse(ConsumerSettings(telemetry_unmanaged=False).sends_unmanaged_uses)

    def test_the_row_moves_it_from_what_is_in_effect(self) -> None:
        self.assertIn(ROW, SETTING_ROWS)
        self.assertIs(ConsumerSettings().toggled(ROW).telemetry_unmanaged, False)
        twice = ConsumerSettings().toggled(ROW).toggled(ROW)
        self.assertEqual(twice, ConsumerSettings(telemetry_unmanaged=True))
        self.assertEqual(
            [
                key
                for key in settings_to_data(twice)
                if key not in settings_to_data(ConsumerSettings())
            ],
            ["telemetry_unmanaged_uses"],
        )
        with mock.patch.object(_default_telemetry, "UNMANAGED_USES", "off"):
            self.assertIs(ConsumerSettings().toggled(ROW).telemetry_unmanaged, True)

    def test_a_choice_is_kept_and_nobody_choosing_is_kept_as_nothing(self) -> None:
        self.assertNotIn("telemetry_unmanaged_uses", settings_to_data(ConsumerSettings()))
        for chosen in (True, False):
            with self.subTest(chosen=chosen):
                data = settings_to_data(ConsumerSettings(telemetry_unmanaged=chosen))
                self.assertEqual(
                    settings_from_data(data), Ok(ConsumerSettings(telemetry_unmanaged=chosen))
                )
        self.assertIsInstance(settings_from_data({"telemetry_unmanaged_uses": "yes"}), Err)

    def test_settings_draws_it_under_telemetry_and_says_what_it_sends(self) -> None:
        drawn = "\n".join(render_settings(ConsumerSettings(), focus=ROW))

        self.assertIn("Telemetry\n> Uses of tools aart-cli did not install: sent", drawn)
        off = "\n".join(render_settings(ConsumerSettings(telemetry_unmanaged=False)))
        self.assertIn("Uses of tools aart-cli did not install: not sent", off)
        purpose = setting_purpose(ROW)
        self.assertIn("by the name", purpose)
        self.assertIn("only while telemetry is on", purpose)


class SendingReadsTheChoiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Home(self)
        self.home.enable()
        self.server = FakeServer()
        self.clock = Clock()

    def _choose(self, chosen: bool) -> None:
        kept = write_consumer_settings(
            ConsumerSettings(telemetry_unmanaged=chosen), data_root=self.home.path
        )
        self.assertIsInstance(kept, Ok)

    def test_by_default_a_use_of_something_else_is_sent_by_its_name(self) -> None:
        self.home.use(name="context7")
        self.home.use(name="github")

        report = _sync(self.home, self.server, self.clock)

        self.assertEqual((report.sent, report.skipped), (2, 0))
        sent = {event["artifact_id"]: event["event_type"] for event in self.server.stored.values()}
        self.assertEqual(sent, {"context7": UNMANAGED_USED, "github": "artifact.used"})
        self.assertNotIn("/work/project", json.dumps(self.server.requests))

    def test_turned_off_a_waiting_use_is_skipped_and_never_sent(self) -> None:
        self.home.use(name="context7")
        self._choose(False)
        self.home.use(name="github")

        report = _sync(self.home, self.server, self.clock)

        self.assertEqual((report.sent, report.skipped), (1, 1))
        self.assertNotIn("context7", json.dumps(self.server.requests))

    def test_settings_aart_cli_cannot_read_send_nothing_of_them(self) -> None:
        settings = Path(self.home.state) / "consumer-settings.json"
        settings.write_text("{not json", encoding="utf-8")
        self.home.use(name="context7")

        report = _sync(self.home, self.server, self.clock)

        self.assertEqual((report.sent, report.skipped), (0, 1))


class TheCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Home(self)
        user = tempfile.TemporaryDirectory()
        self.addCleanup(user.cleanup)
        self.environment = {"HOME": user.name, "AART_CLI_HOME": self.home.path}

    def _run(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with (
            mock.patch.dict(os.environ, self.environment),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            code = cli.main(["consume", "telemetry", *argv])
        return code, out.getvalue()

    def test_off_and_on_are_kept_in_settings_and_status_says_who_chose(self) -> None:
        code, out = self._run("status", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["unmanaged_uses"], {"sent": True, "chosen": False})

        code, out = self._run("unmanaged", "off")

        self.assertEqual(code, 0, out)
        self.assertIn("not sent", out)
        settings = read_consumer_settings(self.home.path)
        self.assertEqual(settings, Ok(ConsumerSettings(telemetry_unmanaged=False)))
        code, out = self._run("status")
        self.assertIn("uses of tools aart-cli did not install: not sent (your choice)", out)
        self.assertFalse(self.home.outbox.exists())

        code, out = self._run("unmanaged", "on", "--json")

        self.assertEqual(json.loads(out)["unmanaged_uses"], {"sent": True, "chosen": True})

    def test_a_choice_keeps_every_other_setting(self) -> None:
        before = replace(ConsumerSettings(), show_updates=False)
        write_consumer_settings(before, data_root=self.home.path)

        self._run("unmanaged", "off")

        self.assertEqual(
            read_consumer_settings(self.home.path),
            Ok(replace(before, telemetry_unmanaged=False)),
        )

    def test_enable_says_whether_they_are_sent(self) -> None:
        code, out = self._run("enable", "--endpoint", "http://127.0.0.1:9")

        self.assertEqual(code, 0, out)
        self.assertIn("each use of a skill or MCP aart-cli did not install", out)


class TheAnnouncementSaysItTest(unittest.TestCase):
    def test_it_names_them_when_they_are_sent_and_not_otherwise(self) -> None:
        setting = TelemetrySetting(True, "https://telemetry.example.com", ID, "key")
        for unmanaged in (True, False):
            with self.subTest(unmanaged=unmanaged):
                said: list[str] = []
                announce_turned_on(setting, said.append, unmanaged=unmanaged)
                text = " ".join(said)
                self.assertEqual("did not install" in text, unmanaged)
                if unmanaged:
                    self.assertIn("Settings", text)


if __name__ == "__main__":
    unittest.main()
