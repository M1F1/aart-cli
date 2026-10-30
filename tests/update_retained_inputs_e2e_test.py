"""§38, INV-196, B-261: an update keeps the configuration its installation already holds.

What an installation was configured with belongs to that installation (its complete identity:
Registry alias, artifact, scope, root and harness), so its update binds those values again rather
than asking for them, and `--set-later` fills only what has no value. A value the new version no
longer accepts, a placeholder, and an input the new version adds are still asked for. The fixture
MCP has configuration and no credential, so no credential store takes part.
"""

from __future__ import annotations

import datetime as dt
import json
import unittest
from unittest import mock

from aart_cli.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
)
from aart_cli.consumer_actions import ConsumerActionContext, LocalConsumerActions
from aart_cli.domain.harness import Scope
from aart_cli.domain.inputs import SKIPPED_INPUT
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.result import Ok
from aart_cli.io.configured_installation_action import InstallationHost
from aart_cli.io.consumer_machine import read_consumer_machine, read_installed_inspections
from tests.configured_install_command_e2e_test import _environment
from tests.marketplace_fixtures import effective_configuration
from tests.mcp_stdio_e2e_test import SERVER_SOURCE

WAREHOUSE = "company/mcp/warehouse"


def _input(identifier: str, variable: str, **more: object) -> dict[str, object]:
    return {
        "id": identifier,
        "kind": "config",
        "inject": {"type": "environment", "variable": variable},
        "help": {"label": identifier},
        **more,
    }


WORKSPACE = _input("workspace", "WAREHOUSE_WORKSPACE")
REGION = _input("region", "WAREHOUSE_REGION", default="westeurope")
PROJECT = _input("project-id", "WAREHOUSE_PROJECT")
NOTE = _input("note", "WAREHOUSE_NOTE", required=False)


def _authored(version: str, *inputs: dict[str, object]) -> tuple[tuple[str, str], ...]:
    manifest = {
        "schema": "aart-cli.dev/mcp/v1",
        "artifact": {"name": "warehouse", "kind": "mcp", "x-fixture-version": version},
        "payload": {"include": ["server.py", "requirements.txt"]},
        "transport": {"type": "stdio"},
        "runtime": {"type": "python", "version": ">=3.10"},
        "launch": {"type": "python", "entrypoint": "server.py"},
        "inputs": list(inputs),
        "python": {"dependencies": {"type": "requirements", "path": "requirements.txt"}},
    }
    return (
        ("warehouse/aart-cli.json", json.dumps(manifest)),
        ("warehouse/server.py", SERVER_SOURCE),
        ("warehouse/requirements.txt", "# no third-party packages\n"),
    )


FIRST = _authored("1.5.0", WORKSPACE, REGION)
NEXT = _authored("1.6.0", WORKSPACE, REGION)
#: The next version asks for one more thing, which nobody has answered yet.
WIDER = _authored("1.6.0", WORKSPACE, REGION, PROJECT)
#: Only an optional input: an update of it needs no answer at all, and must still keep it.
OPTIONAL_FIRST = _authored("1.5.0", NOTE)
OPTIONAL_NEXT = _authored("1.6.0", NOTE)
#: The same, with an optional input the form shows beside the new one.
NOTED = _authored("1.5.0", WORKSPACE, REGION, NOTE)
NOTED_WIDER = _authored("1.6.0", WORKSPACE, REGION, PROJECT, NOTE)
#: The next version accepts only workspaces named `ws-…`.
STRICTER = _authored(
    "1.6.0",
    {**WORKSPACE, "validation": {"type": "pattern", "pattern": "^ws-[a-z]+$"}},
    REGION,
)


def _run(env, *argv: str) -> tuple[int, dict]:
    # No credential store: the fixture has no credential, and the real Keychain is never touched.
    with mock.patch("aart_cli.commands.marketplace._credential_providers", return_value=()):
        return env.run(*argv)


def _config(env, harness: str = "claude"):
    return env.project / f".{harness}/aart-cli/mcp/company/warehouse/config/{harness}.conf"


def _values(env, harness: str = "claude") -> dict[str, str]:
    config = _config(env, harness)
    return dict(
        line.split("=", 1)
        for line in config.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )


def _configured(env, **values: str) -> None:
    """Installed at 1.5.0 with `--set-later`, then configured the way a person does it."""

    code, payload = _run(
        env, "consume", "install", WAREHOUSE, "--profile", "claude", "--set-later", "--yes"
    )
    assert code == 0, payload
    for identifier, value in values.items():
        code, payload = _run(
            env, "consume", "inputs", "set", WAREHOUSE, f"{identifier}={value}", "--yes"
        )
        assert code == 0, payload


def _update(env, *flags: str) -> tuple[int, dict]:
    return _run(env, "consume", "update", WAREHOUSE, "--profile", "claude", *flags)


def _unanswered(payload: dict) -> list[str]:
    return [item["id"] for item in payload.get("inputs", ())]


class AnUpdateKeepsTheInstallationsValuesTest(unittest.TestCase):
    def test_the_update_needs_no_answer_and_keeps_every_value(self) -> None:
        with _environment(authored=FIRST) as env:
            _configured(env, workspace="analytics", region="northeurope")
            env.publish(NEXT)

            code, payload = _update(env, "--yes")

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["finalized"], payload)
            self.assertEqual(payload["items"][0]["key"], f"{WAREHOUSE}@1.6.0")
            # The stored region wins over the new version's default.
            self.assertEqual(_values(env), {"workspace": "analytics", "region": "northeurope"})

    def test_an_optional_value_is_kept_when_nothing_else_is_asked(self) -> None:
        with _environment(authored=OPTIONAL_FIRST) as env:
            code, payload = _run(
                env,
                "consume", "install", WAREHOUSE, "--profile", "claude",
                "--input", f"{WAREHOUSE}:note=read-only", "--yes",
            )  # fmt: skip
            self.assertEqual(code, 0, payload)
            env.publish(OPTIONAL_NEXT)

            code, payload = _update(env, "--yes")

            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["items"][0]["key"], f"{WAREHOUSE}@1.6.0")
            self.assertEqual(_values(env), {"note": "read-only"})
            # The file is still the installation's own, not left behind beside it.
            code, payload = _run(
                env, "consume", "inputs", "set", WAREHOUSE, "note=changed", "--yes"
            )
            self.assertEqual(code, 0, payload)
            self.assertEqual(_values(env), {"note": "changed"})

    def test_set_later_never_writes_the_placeholder_over_a_value(self) -> None:
        with _environment(authored=FIRST) as env:
            _configured(env, workspace="analytics")
            env.publish(NEXT)

            code, payload = _update(env, "--set-later", "--yes")

            self.assertEqual(code, 0, payload)
            self.assertEqual(_values(env), {"workspace": "analytics", "region": "westeurope"})

    def test_an_answer_on_the_command_line_replaces_the_kept_value(self) -> None:
        with _environment(authored=FIRST) as env:
            _configured(env, workspace="analytics", region="northeurope")
            env.publish(NEXT)

            code, payload = _update(env, "--input", f"{WAREHOUSE}:workspace=finance", "--yes")

            self.assertEqual(code, 0, payload)
            self.assertEqual(_values(env), {"workspace": "finance", "region": "northeurope"})


class AnUpdateAsksOnlyWhatIsNewOrNoLongerFitsTest(unittest.TestCase):
    def test_an_input_the_new_version_adds_is_the_only_question(self) -> None:
        with _environment(authored=FIRST) as env:
            _configured(env, workspace="analytics")
            env.publish(WIDER)

            code, payload = _update(env, "--yes")

            self.assertNotEqual(code, 0, payload)
            self.assertEqual(_unanswered(payload), ["project-id"])

            code, payload = _update(env, "--set-later", "--yes")

            self.assertEqual(code, 0, payload)
            self.assertEqual(
                _values(env),
                {"workspace": "analytics", "region": "westeurope", "project-id": SKIPPED_INPUT},
            )

    def test_a_value_the_new_version_refuses_is_asked_again(self) -> None:
        with _environment(authored=FIRST) as env:
            _configured(env, workspace="analytics")
            env.publish(STRICTER)

            code, payload = _update(env, "--yes")

            self.assertNotEqual(code, 0, payload)
            self.assertEqual(_unanswered(payload), ["workspace"])

    def test_a_placeholder_is_no_value_and_is_asked_again(self) -> None:
        with _environment(authored=FIRST) as env:
            _configured(env)
            env.publish(NEXT)

            code, payload = _update(env, "--yes")

            self.assertNotEqual(code, 0, payload)
            self.assertEqual(_unanswered(payload), ["workspace"])


def _tui(env):
    """The TUI's own handler, and the key of the one installation it updates from screen 15."""

    host = InstallationHost(
        env.paths.data_root, str(env.project), str(env.home), Scope.PROJECT, ("claude",)
    )
    machine = read_consumer_machine(
        state_root=host.state_root,
        harness_root=host.harness_root,
        today=dt.date(2026, 10, 30),
        project_root=host.project_root,
        user_home=host.user_home,
        data_root=host.data_root,
    )
    inspected = read_installed_inspections(
        state_root=host.state_root,
        harness_root=host.harness_root,
        scope=host.scope,
        profiles=host.profiles,
        credential_providers=(),
    )
    assert isinstance(machine, Ok) and isinstance(inspected, Ok)
    (installation,) = inspected.value.inspections
    handler = LocalConsumerActions(
        ConsumerActionContext(
            host,
            effective_configuration((env.source,), default_registry="company"),
            machine.value,
            policy=EffectivePolicy(),
            credential_providers=(),
        )
    )
    return handler, installation.installation


def _prepare(handler, focus: str, *answers: tuple[str, str]):
    return handler.handle(
        ConsumerUiCommand(
            ConsumerUiCommandKind.PREPARE_ACTION,
            action=ConsumerActionKind.UPDATE,
            focus=focus,
            config_answers=answers,
        )
    )


class EachInstallationKeepsOnlyItsOwnTest(unittest.TestCase):
    def test_another_harness_never_receives_the_value(self) -> None:
        with _environment(authored=FIRST) as env:
            code, payload = _run(
                env,
                "consume", "install", WAREHOUSE, "--profile", "claude,opencode",
                "--set-later", "--yes",
            )  # fmt: skip
            self.assertEqual(code, 0, payload)
            code, payload = _run(
                env,
                "consume", "inputs", "set", WAREHOUSE, "workspace=analytics",
                "--harness", "claude", "--yes",
            )  # fmt: skip
            self.assertEqual(code, 0, payload)
            env.publish(NEXT)

            code, payload = _run(
                env,
                "consume", "update", WAREHOUSE, "--profile", "claude,opencode",
                "--set-later", "--yes",
            )  # fmt: skip

            self.assertEqual(code, 0, payload)
            self.assertEqual(_values(env, "claude")["workspace"], "analytics")
            self.assertEqual(_values(env, "opencode")["workspace"], SKIPPED_INPUT)

    def test_a_file_changed_outside_aart_cli_gives_nothing_to_keep(self) -> None:
        with _environment(authored=FIRST) as env:
            _configured(env, workspace="analytics")
            config = _config(env)
            config.write_text(
                config.read_text(encoding="utf-8").replace("analytics", "by-hand"),
                encoding="utf-8",
            )
            env.publish(NEXT)

            code, payload = _update(env, "--yes")

            self.assertNotEqual(code, 0, payload)
            self.assertEqual(_unanswered(payload), ["workspace"])


class TheTuiUpdateTest(unittest.TestCase):
    def test_the_update_is_reviewed_with_the_kept_values(self) -> None:
        with _environment(authored=FIRST) as env:
            _configured(env, workspace="analytics")
            env.publish(NEXT)

            update = _prepare(*_tui(env))

            self.assertTrue(update.event.review_digest, update.source.screens.notice)
            self.assertIsNone(update.event.config_draft)

    def test_a_new_value_is_asked_on_the_form_and_the_update_keeps_the_rest(self) -> None:
        with _environment(authored=FIRST) as env:
            _configured(env, workspace="analytics", region="northeurope")
            env.publish(WIDER)
            handler, focus = _tui(env)

            asked = _prepare(handler, focus)

            self.assertFalse(asked.event.review_digest)
            draft = asked.event.config_draft
            self.assertEqual([item.id for item in draft.fields], ["project-id"])
            (field,) = draft.fields

            reviewed = _prepare(handler, focus, (field.row, "p-42"))

            self.assertTrue(reviewed.event.review_digest, reviewed.source.screens.notice)
            done = handler.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.EXECUTE_ACTION,
                    action=ConsumerActionKind.UPDATE,
                    focus=focus,
                    review_digest=reviewed.event.review_digest,
                )
            )
            self.assertFalse(done.source.screens.notice, done.source.screens.notice)
            self.assertEqual(
                _values(env),
                {"workspace": "analytics", "region": "northeurope", "project-id": "p-42"},
            )

    def test_the_form_starts_from_what_the_installation_holds(self) -> None:
        with _environment(authored=NOTED) as env:
            code, payload = _run(
                env,
                "consume", "install", WAREHOUSE, "--profile", "claude",
                "--input", f"{WAREHOUSE}:note=read-only", "--set-later", "--yes",
            )  # fmt: skip
            self.assertEqual(code, 0, payload)
            env.publish(NOTED_WIDER)

            asked = _prepare(*_tui(env))

            fields = {item.id: item.value for item in asked.event.config_draft.fields}
            # The placeholder is no value, so workspace is asked as well.
            self.assertEqual(fields, {"project-id": "", "workspace": "", "note": "read-only"})


if __name__ == "__main__":
    unittest.main()
