"""§170.4, INV-251: the optional MCP test offered after an install, and only an addition to it.

The install commits and reports success first. Success then offers to test the MCP installations
that transaction made; nothing runs until it is chosen and confirmed on 11a, which first states
each installation's declared tool and arguments and that the call reaches the configured service.
Whatever the test finds, the installation records are exactly the ones the install wrote.
"""

from __future__ import annotations

import dataclasses
import json
import unittest

from aart_cli.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    key_bindings,
    key_event,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import (
    ConsumerScreen,
    McpTestEntryView,
    McpTestResultView,
    McpTestStageView,
    McpTestView,
)
from aart_cli.domain.result import Ok
from aart_cli.io.installed_smoke import LocalMcpTest
from aart_cli.io.receipt_store import LocalReceiptStore
from aart_cli.tui_consumer import CanonicalScreenSource, _reload, frame, render_mcp_test
from tests.configured_install_command_e2e_test import _environment
from tests.consumer_application_e2e_test import _actions, _at, _drive
from tests.consumer_shell_test import DOWN, ENTER, INSTALL_CUSTOM, RIGHT, SPACE
from tests.consumer_shell_test import screens as shell_screens
from tests.installation_success_actions_test import _success
from tests.mcp_smoke_stdio_test import SERVER

_HARNESSES = ["claude", "opencode", "tabnine"]


def _manifest(smoke: dict | None) -> tuple[tuple[str, str], ...]:
    manifest = {
        "schema": "aart-cli.dev/mcp/v1",
        "artifact": {"name": "dummy", "kind": "mcp"},
        "payload": {"include": ["server.py"]},
        "transport": {"type": "stdio"},
        "runtime": {"type": "python", "version": ">=3.10"},
        "launch": {"type": "python", "entrypoint": "server.py"},
        "compatibility": {"harnesses": _HARNESSES},
    }
    if smoke is not None:
        manifest["smoke_test"] = smoke
    return (("dummy/aart-cli.json", json.dumps(manifest)), ("dummy/server.py", SERVER))


_DECLARED = {"tool": "read_identity", "read_only": True}

#: Marketplace to Success for one MCP, delivered to opencode only.
_INSTALL = (SPACE, *INSTALL_CUSTOM, RIGHT, SPACE, ENTER, ENTER, ENTER)

#: From Success's first row to the test offer: past Installed and Receipt, then Enter.
_OPEN_TEST = (DOWN, DOWN, ENTER)


def _records(env) -> str:
    stored = LocalReceiptStore(str(env.paths.data_root) + "/state").installations()
    assert isinstance(stored, Ok), getattr(stored, "diagnostics", ())
    return repr(stored.value)


class _Watched:
    """The production test, plus what the installation records were the moment it was asked to run.

    That moment is after the install committed and before anything was tested, so comparing it
    with the records afterwards is comparing the install with the install-plus-test.
    """

    def __init__(self, env) -> None:
        self._env = env
        self._real = LocalMcpTest(str(env.paths.data_root))
        self.before_run: str | None = None

    def installations(self, **kwargs):
        return self._real.installations(**kwargs)

    def plan(self, records):
        return self._real.plan(records)

    def run(self, records):
        self.before_run = _records(self._env)
        return self._real.run(records)


def _session(env, *codes: int):
    handler = _actions(env)
    watched = _Watched(env)
    handler._mcp_test = watched
    finished, terminal, _ = _drive(env, _at(ConsumerScreen.MARKETPLACE), *codes, actions=handler)
    return finished, terminal, watched


class PostInstallMcpTestE2ETest(unittest.TestCase):
    def test_nothing_runs_until_the_test_is_chosen_and_the_offer_names_the_call(self) -> None:
        with _environment(authored=_manifest(_DECLARED)) as env:
            offered, terminal, watched = _session(env, *_INSTALL, *_OPEN_TEST)

        self.assertIs(offered.session.screen, ConsumerScreen.MCP_TEST, terminal.last)
        self.assertIs(offered.action, ConsumerActionKind.MCP_TEST)
        self.assertIn("read_identity {}", terminal.last)
        self.assertIn("configured service", terminal.last)
        self.assertNotIn("mcp-startup-and-protocol", terminal.last)
        self.assertIsNone(watched.before_run)

    def test_a_confirmed_test_reports_both_stages_and_leaves_the_install_records_alone(
        self,
    ) -> None:
        with _environment(authored=_manifest(_DECLARED)) as env:
            tested, terminal, watched = _session(env, *_INSTALL, *_OPEN_TEST, ENTER)
            after_test = _records(env)

        self.assertIs(tested.session.screen, ConsumerScreen.MCP_TEST, terminal.last)
        self.assertIsNone(tested.action)
        self.assertIn("✓", terminal.last)
        self.assertIn("installation-configuration", terminal.last)
        self.assertIn("mcp-startup-and-protocol", terminal.last)
        self.assertIsNotNone(watched.before_run)
        self.assertEqual(after_test, watched.before_run)

    def test_enter_after_the_answer_returns_to_the_same_success(self) -> None:
        with _environment(authored=_manifest(_DECLARED)) as env:
            back, terminal, _ = _session(env, *_INSTALL, *_OPEN_TEST, ENTER, ENTER)

        self.assertIs(back.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertIn("Test installed MCPs", terminal.last)
        self.assertIn("Succeeded", terminal.last)

    def test_a_failing_server_is_a_failed_test_and_still_a_successful_install(self) -> None:
        broken = (_manifest(_DECLARED)[0], ("dummy/server.py", "print('not an MCP server')\n"))
        with _environment(authored=broken) as env:
            tested, terminal, watched = _session(env, *_INSTALL, *_OPEN_TEST, ENTER)
            after_test = _records(env)

        self.assertIs(tested.session.screen, ConsumerScreen.MCP_TEST, terminal.last)
        self.assertIn("✗", terminal.last)
        self.assertIn("installation is unchanged", terminal.last)
        self.assertEqual(after_test, watched.before_run)

    def test_an_offer_that_cannot_be_read_never_reaches_the_install(self) -> None:
        """INV-251: a failure finding what to test withholds the offer and nothing else."""

        class Unreadable(_Watched):
            def installations(self, **kwargs):
                raise OSError("state unreadable")

        with _environment(authored=_manifest(_DECLARED)) as env:
            handler = _actions(env)
            handler._mcp_test = Unreadable(env)
            finished, terminal, _ = _drive(
                env, _at(ConsumerScreen.MARKETPLACE), *_INSTALL, actions=handler
            )

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertIn("Succeeded", terminal.last)
        self.assertNotIn("Test installed MCPs", terminal.last)

    def test_an_install_that_made_no_mcp_offers_no_test(self) -> None:
        from tests.installation_harness_choice_test import _AUTHORED_SKILL

        with _environment(authored=_AUTHORED_SKILL) as env:
            success, terminal, _ = _session(env, *_INSTALL)

        self.assertIs(success.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertNotIn(ConsumerScreen.MCP_TEST.value, success.rows)
        self.assertNotIn("Test installed MCPs", terminal.last)


class PostInstallMcpTestScreenTest(unittest.TestCase):
    """The reducer and drawing, over composed views and without any process."""

    def _offered(self):
        source, state = _success(receipts=shell_screens().receipts)
        composed = dataclasses.replace(
            source._screens, mcp_test=McpTestView(("company/mcp/github@1.0.0#opencode",))
        )
        source = CanonicalScreenSource(composed)
        return source, _reload(source, state, entering=True)

    def test_the_test_row_is_an_action_and_its_neighbours_still_open(self) -> None:
        source, state = self._offered()
        self.assertIn(ConsumerScreen.MCP_TEST.value, state.rows)

        on_test = dataclasses.replace(state, cursor=state.rows.index(ConsumerScreen.MCP_TEST.value))
        event = key_event("enter", on_test, detail=source.detail(on_test))
        self.assertEqual(
            event,
            ConsumerUiEvent(ConsumerUiEventKind.REQUEST_ACTION, action=ConsumerActionKind.MCP_TEST),
        )
        moved, commands = reduce_consumer_ui(on_test, event)
        self.assertIs(moved.session.screen, ConsumerScreen.MCP_TEST)
        prepare = next(
            item for item in commands if item.kind is ConsumerUiCommandKind.PREPARE_ACTION
        )
        # The subject is the receipt Success is about, not the row's name.
        self.assertEqual(prepare.focus, state.focus)
        self.assertIn("Review MCP test", {binding.label for binding in key_bindings(on_test)})

        on_receipt = dataclasses.replace(
            state, cursor=state.rows.index(ConsumerScreen.RECEIPT_DETAILS.value)
        )
        opened = key_event("enter", on_receipt, detail=source.detail(on_receipt))
        self.assertEqual(
            opened,
            ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=ConsumerScreen.RECEIPT_DETAILS),
        )

    def test_without_an_offer_success_has_its_three_rows(self) -> None:
        _, state = _success()

        self.assertNotIn(ConsumerScreen.MCP_TEST.value, state.rows)
        self.assertEqual(len(state.rows), 3)

    def test_a_recorded_test_stays_on_11a_and_enter_returns_to_the_same_success(self) -> None:
        source, state = self._offered()
        on_test = dataclasses.replace(state, cursor=state.rows.index(ConsumerScreen.MCP_TEST.value))
        requested, _ = reduce_consumer_ui(
            on_test,
            ConsumerUiEvent(ConsumerUiEventKind.REQUEST_ACTION, action=ConsumerActionKind.MCP_TEST),
        )
        prepared, _ = reduce_consumer_ui(
            requested,
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=ConsumerActionKind.MCP_TEST,
                review_digest="a" * 64,
            ),
        )
        confirmed, commands = reduce_consumer_ui(
            prepared, key_event("enter", prepared, detail=None)
        )
        self.assertEqual([item.kind for item in commands], [ConsumerUiCommandKind.EXECUTE_ACTION])
        answered, _ = reduce_consumer_ui(
            confirmed,
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_RECORDED,
                action=ConsumerActionKind.MCP_TEST,
                text="2026-10-14T00:00:00+00:00",
            ),
        )

        self.assertIs(answered.session.screen, ConsumerScreen.MCP_TEST)
        self.assertIsNone(answered.action)
        self.assertIn("Back to Success", {binding.label for binding in key_bindings(answered)})
        back, _ = reduce_consumer_ui(answered, key_event("enter", answered, detail=None))
        self.assertIs(back.session.screen, ConsumerScreen.SUCCESS)
        self.assertEqual(back.focus, state.focus)

    def test_the_offer_states_the_call_and_the_service_before_anything_runs(self) -> None:
        offer = "\n".join(
            render_mcp_test(
                McpTestView(
                    ("a#opencode", "b#opencode"),
                    (
                        McpTestEntryView(
                            "a#opencode", "read_identity", '{"tenant": {"configuration": "tenant"}}'
                        ),
                        McpTestEntryView("b#opencode", "", ""),
                    ),
                )
            )
        )

        self.assertIn('a#opencode: read_identity {"tenant": {"configuration": "tenant"}}', offer)
        self.assertIn("b#opencode: NOT CONFIGURED", offer)
        self.assertIn("configured service", offer)
        self.assertNotIn("PASS", offer)

    def test_results_name_both_stages_and_say_the_install_is_unchanged(self) -> None:
        drawn = "\n".join(
            render_mcp_test(
                McpTestView(
                    ("a#opencode",),
                    results=(
                        McpTestResultView(
                            "a#opencode",
                            (
                                McpTestStageView("installation-configuration", "PASS", "usable"),
                                McpTestStageView("mcp-startup-and-protocol", "FAIL", "isError"),
                            ),
                        ),
                    ),
                )
            )
        )

        self.assertIn("✗ a#opencode", drawn)
        self.assertIn("FAIL", drawn)
        self.assertIn("installation is unchanged", drawn)

    def test_the_screen_is_drawn_inside_the_frame(self) -> None:
        source, state = self._offered()
        on_test = dataclasses.replace(state, cursor=state.rows.index(ConsumerScreen.MCP_TEST.value))
        moved, _ = reduce_consumer_ui(
            on_test,
            ConsumerUiEvent(ConsumerUiEventKind.REQUEST_ACTION, action=ConsumerActionKind.MCP_TEST),
        )

        drawn = "\n".join(frame(source, _reload(source, moved, entering=True)))

        self.assertIn("Test MCP Installations", drawn)


if __name__ == "__main__":
    unittest.main()
