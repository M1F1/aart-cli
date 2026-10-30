"""CP-48: artifact usage in Settings, on Activity, from the command line, and by default (§212).

Recording is on without asking only in the harnesses the build bakes from
`AART_CLI_DEFAULT_USAGE_HARNESSES`; a build that bakes none, as the public one, records nowhere
until a harness is turned on. Each harness has one Settings row; what it records stands on the screen when the cursor
is on that row; Activity ranks what was used. Every test works in a temporary home.
"""

from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import os
import pathlib
import unittest
from unittest import mock

from aart_cli import _default_usage, cli
from aart_cli.application.consumer_ui import ConsumerUiState
from aart_cli.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
    artifact_usage_row,
    project_activity,
    project_dashboard,
    settings_from_data,
    settings_to_data,
)
from aart_cli.application.usage_recording import ArtifactUsageView, usage_disclosure
from aart_cli.domain.artifact_usage import ArtifactUse, UsageKind, UsageRank
from aart_cli.domain.result import Err, Ok
from aart_cli.io.activity_store import ActivityDatabase
from aart_cli.io.telemetry_store import TelemetryOutbox
from aart_cli.io.telemetry_sync import new_installation_id
from aart_cli.io.usage_hooks import harness_file, read_artifact_usage, usage_hooked
from aart_cli.tui_consumer import CanonicalScreenSource, ConsumerScreens, _reload, frame
from tests.configured_install_command_e2e_test import _environment
from tests.consumer_application_e2e_test import _actions
from tests.consumer_shell_test import TODAY

_ENDPOINT = "https://telemetry.example.test"

_USAGE = ArtifactUsageView(
    "/home/me/.aart-cli/state/activity.sqlite3",
    (
        ("claude", "/home/me/.claude/settings.json"),
        ("opencode", "/home/me/.config/opencode/plugins/aart-cli-usage.js"),
    ),
    ("opencode",),
    (
        UsageRank(
            "company/mcp/jira", UsageKind.MCP, "opencode", 12, "2026-10-28T14:02:00+00:00", True
        ),
        UsageRank("my-own", UsageKind.SKILL, "opencode", 2, "2026-10-27T09:00:00+00:00", False),
    ),
)


def _baked(value: str):
    """A build whose release baked `AART_CLI_DEFAULT_USAGE_HARNESSES=value`."""

    return mock.patch.object(_default_usage, "HARNESSES", value)


def _drawn(screen: ConsumerScreen, *, row: str = "", usage=_USAGE) -> str:
    settings = ConsumerSettings()
    source = CanonicalScreenSource(
        ConsumerScreens(
            project_dashboard((), registry_count=1),
            (),
            project_activity((), today=TODAY),
            settings=settings,
            harnesses=("claude", "opencode", "tabnine"),
            usage=usage,
        )
    )
    state = _reload(
        source,
        dataclasses.replace(
            ConsumerUiState(ConsumerSession(screen), settings=settings),
            viewport_columns=140,
            viewport_rows=80,
            workspace="/work/shop",
        ),
        entering=True,
    )
    if row:
        state = dataclasses.replace(state, cursor=state.rows.index(row))
    return "\n".join(frame(source, state))


class TheSettingTest(unittest.TestCase):
    def test_a_build_that_bakes_no_harness_records_nowhere_until_one_is_turned_on(self) -> None:
        self.assertEqual(ConsumerSettings().recorded_usage, ())
        on = ConsumerSettings().toggled(artifact_usage_row("claude"))
        self.assertEqual(on.recorded_usage, ("claude",))

    def test_a_build_records_where_it_baked_until_somebody_chooses(self) -> None:
        with _baked("opencode"):
            self.assertEqual(ConsumerSettings().recorded_usage, ("opencode",))
        with _baked("claude,opencode"):
            self.assertEqual(ConsumerSettings().recorded_usage, ("claude", "opencode"))

    @_baked("opencode")
    def test_turning_one_on_keeps_the_default_and_turning_it_off_is_remembered(self) -> None:
        claude = ConsumerSettings().toggled(artifact_usage_row("claude"))
        self.assertEqual(claude.recorded_usage, ("opencode", "claude"))

        neither = claude.toggled(artifact_usage_row("opencode")).toggled(
            artifact_usage_row("claude")
        )
        self.assertEqual(neither.recorded_usage, ())
        self.assertEqual(settings_from_data(settings_to_data(neither)), Ok(neither))

    def test_nothing_chosen_is_not_written_down(self) -> None:
        self.assertNotIn("artifact_usage", settings_to_data(ConsumerSettings()))
        self.assertEqual(settings_from_data({}), Ok(ConsumerSettings()))

    def test_a_harness_without_hooks_is_refused(self) -> None:
        self.assertIsInstance(settings_from_data({"artifact_usage": ["tabnine"]}), Err)
        with self.assertRaises(ValueError):
            artifact_usage_row("tabnine")


class TheDisclosureTest(unittest.TestCase):
    """B-259: what turning usage on says about sending follows telemetry's state."""

    def _said(self, endpoint: str) -> str:
        return "\n".join(
            usage_disclosure(
                "opencode",
                database="/home/me/.aart-cli/state/activity.sqlite3",
                changed_file="/home/me/.config/opencode/plugins/aart-cli-usage.js",
                telemetry_endpoint=endpoint,
            )
        )

    def test_with_telemetry_off_nothing_is_sent(self) -> None:
        said = self._said("")

        self.assertIn("Kept only on this machine", said)
        self.assertIn("Nothing is sent anywhere.", said)
        self.assertNotIn("Telemetry", said)

    def test_with_telemetry_on_it_names_where_uses_go_and_how_to_stop_it(self) -> None:
        said = self._said(_ENDPOINT)

        self.assertNotIn("Nothing is sent", said)
        self.assertNotIn("Kept only", said)
        self.assertIn("/home/me/.aart-cli/state/activity.sqlite3", said)
        self.assertIn(
            f"Telemetry is on: each use of an artifact aart-cli installed is sent to {_ENDPOINT}",
            said,
        )
        self.assertIn("never the project", said)
        self.assertIn("aart-cli consume telemetry disable", said)


class SettingsScreenTest(unittest.TestCase):
    @_baked("opencode")
    def test_one_row_per_detected_harness_that_can_record(self) -> None:
        drawn = _drawn(ConsumerScreen.SETTINGS)

        self.assertIn("Artifact usage", drawn)
        self.assertIn("Artifact usage claude: off", drawn)
        self.assertIn("Artifact usage opencode: on", drawn)
        self.assertNotIn("Artifact usage tabnine", drawn)

    def test_a_build_that_bakes_no_harness_shows_every_row_off(self) -> None:
        drawn = _drawn(ConsumerScreen.SETTINGS)

        self.assertIn("Artifact usage claude: off", drawn)
        self.assertIn("Artifact usage opencode: off", drawn)

    def test_what_it_records_stands_on_the_screen_on_its_row(self) -> None:
        drawn = _drawn(ConsumerScreen.SETTINGS, row=artifact_usage_row("claude"))

        self.assertIn("Never records what a tool is called with, prompts or answers.", drawn)
        self.assertIn("/home/me/.claude/settings.json", drawn)
        self.assertIn("/home/me/.aart-cli/state/activity.sqlite3", drawn)
        self.assertIn("Nothing is sent anywhere.", drawn)

    def test_with_telemetry_on_the_row_says_where_uses_are_sent(self) -> None:
        drawn = _drawn(
            ConsumerScreen.SETTINGS,
            row=artifact_usage_row("claude"),
            usage=dataclasses.replace(_USAGE, telemetry_endpoint=_ENDPOINT),
        )

        self.assertIn(_ENDPOINT, drawn)
        self.assertNotIn("Nothing is sent anywhere.", drawn)

    @_baked("opencode")
    def test_it_says_when_a_recording_harness_has_no_hook_yet(self) -> None:
        drawn = _drawn(
            ConsumerScreen.SETTINGS,
            row=artifact_usage_row("opencode"),
            usage=dataclasses.replace(_USAGE, hooked=()),
        )

        self.assertIn("is added on the next start", drawn)


class ActivityScreenTest(unittest.TestCase):
    def test_activity_ranks_the_most_used_and_says_where_it_is_recorded(self) -> None:
        drawn = _drawn(ConsumerScreen.ACTIVITY)

        self.assertIn("most used:", drawn)
        self.assertIn("12  company/mcp/jira  MCP  opencode  last 2026-10-28 14:02 UTC", drawn)
        self.assertIn("my-own (not installed by aart-cli)", drawn)
        self.assertIn("artifact usage is recorded in opencode; Settings turns it off.", drawn)

    def test_activity_says_when_nothing_records(self) -> None:
        drawn = _drawn(
            ConsumerScreen.ACTIVITY, usage=dataclasses.replace(_USAGE, hooked=(), ranking=())
        )

        self.assertNotIn("most used:", drawn)
        self.assertIn("artifact usage is not recorded in any harness", drawn)


class TheProductionCompositionTest(unittest.TestCase):
    @_baked("opencode")
    def test_the_baked_harness_is_hooked_at_start_and_claude_is_not(self) -> None:
        with _environment() as env:
            (env.home / ".claude").mkdir()
            (env.home / ".config" / "opencode").mkdir(parents=True)
            actions = _actions(env)

            self.assertEqual(actions.record_usage_by_default(), ("opencode",))

            self.assertTrue(usage_hooked("opencode", user_home=str(env.home)))
            self.assertFalse(usage_hooked("claude", user_home=str(env.home)))
            self.assertFalse((env.home / ".claude" / "settings.json").exists())
            usage = actions.source().screens.usage
            assert usage is not None
            self.assertEqual(usage.hooked, ("opencode",))

    def test_a_build_that_bakes_no_harness_hooks_nothing_at_start(self) -> None:
        with _environment() as env:
            (env.home / ".claude").mkdir()
            (env.home / ".config" / "opencode").mkdir(parents=True)
            actions = _actions(env)

            self.assertEqual(actions.record_usage_by_default(), ())

            self.assertFalse((env.home / ".config" / "opencode" / "plugins").exists())
            self.assertFalse((env.home / ".claude" / "settings.json").exists())

    def test_turning_claude_on_in_settings_writes_its_hook(self) -> None:
        with _environment() as env:
            actions = _actions(env)

            kept = actions.save_settings(actions.settings.toggled(artifact_usage_row("claude")))

            self.assertIn("claude", kept.recorded_usage)
            self.assertTrue(usage_hooked("claude", user_home=str(env.home)))

    def test_a_hook_that_cannot_be_written_leaves_the_setting_off(self) -> None:
        with _environment() as env:
            settings = pathlib.Path(harness_file("claude", user_home=str(env.home)))
            settings.parent.mkdir()
            settings.write_text("not json")
            actions = _actions(env)

            kept = actions.save_settings(actions.settings.toggled(artifact_usage_row("claude")))

            self.assertNotIn("claude", kept.recorded_usage)
            self.assertEqual(settings.read_text(), "not json")


def _cli(env, *argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with (
        mock.patch.dict(os.environ, env.xdg, clear=False),
        contextlib.redirect_stdout(out),
        contextlib.redirect_stderr(io.StringIO()),
        mock.patch("os.getcwd", return_value=str(env.project)),
    ):
        code = cli.main(list(argv))
    return code, out.getvalue()


class TheCommandLineTest(unittest.TestCase):
    def test_enable_show_disable_and_forget(self) -> None:
        with _environment() as env:
            code, out = _cli(env, "consume", "usage", "enable", "--harness", "claude")
            self.assertEqual(code, 0, out)
            self.assertIn("Nothing is sent anywhere.", out)
            self.assertTrue(usage_hooked("claude", user_home=str(env.home)))

            state = str(pathlib.Path(env.paths.data_root) / "state")
            ActivityDatabase(state).record_use(
                ArtifactUse("claude", UsageKind.SKILL, "code-review"), "2026-10-28T10:00:00+00:00"
            )
            code, out = _cli(env, "consume", "usage", "show", "--json")
            shown = json.loads(out)
            self.assertEqual(code, 0)
            self.assertEqual(
                {item["harness"]: item["recording"] for item in shown["harnesses"]},
                {"claude": True, "opencode": False},
            )
            self.assertEqual(
                [(item["artifact"], item["uses"]) for item in shown["ranking"]],
                [("code-review", 1)],
            )

            code, out = _cli(env, "consume", "usage", "disable", "--harness", "claude", "--forget")
            self.assertEqual(code, 0, out)
            self.assertIn("claude: 1 recorded uses deleted.", out)
            self.assertFalse(usage_hooked("claude", user_home=str(env.home)))
            _, out = _cli(env, "consume", "usage", "show", "--json")
            self.assertEqual(json.loads(out)["ranking"], [])

    def test_with_telemetry_on_enable_says_where_uses_are_sent(self) -> None:
        with _environment() as env:
            state = str(pathlib.Path(env.paths.data_root) / "state")
            TelemetryOutbox(state).enable(_ENDPOINT, new_installation_id())

            code, out = _cli(env, "consume", "usage", "enable", "--harness", "claude")

            self.assertEqual(code, 0, out)
            self.assertIn(_ENDPOINT, out)
            self.assertNotIn("Nothing is sent anywhere.", out)
            self.assertEqual(
                read_artifact_usage(
                    data_root=env.paths.data_root, user_home=str(env.home)
                ).telemetry_endpoint,
                _ENDPOINT,
            )

    def test_with_telemetry_turned_off_enable_says_nothing_is_sent(self) -> None:
        with _environment() as env:
            state = str(pathlib.Path(env.paths.data_root) / "state")
            TelemetryOutbox(state).enable(_ENDPOINT, new_installation_id())
            TelemetryOutbox(state).disable(forget=False)

            code, out = _cli(env, "consume", "usage", "enable", "--harness", "claude")

            self.assertEqual(code, 0, out)
            self.assertIn("Nothing is sent anywhere.", out)
            self.assertNotIn(_ENDPOINT, out)
            self.assertEqual(
                read_artifact_usage(
                    data_root=env.paths.data_root, user_home=str(env.home)
                ).telemetry_endpoint,
                "",
            )

    def test_a_harness_without_hooks_is_refused(self) -> None:
        with _environment() as env:
            code, out = _cli(env, "consume", "usage", "enable", "--harness", "tabnine")

            self.assertNotEqual(code, 0)
            self.assertIn("artifact usage can be recorded in claude, opencode", out)


if __name__ == "__main__":
    unittest.main()
