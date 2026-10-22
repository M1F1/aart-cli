"""§187, INV-288, D-469: an optional input is asked, and reaches the server only when answered.

An Enterprise agent found that a skipped input reached the server as the literal text
`AART_NOT_SET`, and that an optional input could not be given at all: 07 asked only the required
ones, and Set later would have put the placeholder into any field it was handed. An optional input
nobody answered is now simply absent, so the server applies its own default.
"""

from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from unittest import mock

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    InstallationConfigDraft,
    InstallationConfigField,
)
from aart_cli.application.consumer_views import ConfigInputView
from aart_cli.application.installation_inputs import (
    ArtifactAnswer,
    InstallationInputField,
    copy_artifact_answers,
)
from aart_cli.domain.harness import Scope
from aart_cli.domain.identifiers import ArtifactIdentity, InputId, SourceAlias
from aart_cli.domain.inputs import SKIPPED_INPUT, ConfigInput, EnvironmentBinding
from aart_cli.domain.installation_owner import InstallationOwner
from aart_cli.tui_consumer import render_installation_config_form
from tests.artifact_installation_e2e_test import MANIFEST, SERVER_SOURCE
from tests.command_line_inputs_e2e_test import _RecordingCredentialStore
from tests.configured_install_command_e2e_test import _environment
from tests.consumer_application_e2e_test import _actions
from tests.install_time_config_form_test import _MemoryCredentialProvider

GITHUB = "company/mcp/github"
HOST = "github-host"
_manifest = copy.deepcopy(MANIFEST)
_manifest["inputs"].append(
    {
        "id": HOST,
        "kind": "config",
        "required": False,
        "inject": {"type": "environment", "variable": "GITHUB_HOST"},
        "help": {"label": "GitHub Enterprise host"},
    }
)
#: The MCP server of `AUTHORED_MCP`, with one optional input that has no default.
AUTHORED_OPTIONAL: tuple[tuple[str, str], ...] = (
    ("github/aart-cli.json", json.dumps(_manifest)),
    ("github/server.py", SERVER_SOURCE),
    ("github/requirements.txt", "# no third-party packages\n"),
)

_VALUES = st.sampled_from(("", "acme", " padded", "x​y"))
_FIELDS = st.lists(st.tuples(st.booleans(), _VALUES, st.booleans()), min_size=1, max_size=6)


def _draft(fields) -> InstallationConfigDraft:
    return InstallationConfigDraft(
        tuple(
            InstallationConfigField(f"input-{index}", value, accepted=accepted, required=required)
            for index, (required, value, accepted) in enumerate(fields)
        )
    )


class FormDraftTest(unittest.TestCase):
    @given(_FIELDS)
    def test_set_later_fills_only_required_fields_and_drops_empty_optional_ones(
        self, fields
    ) -> None:
        later = _draft(fields).set_later()
        answers = dict(later.answers)

        self.assertTrue(later.ready)
        for field in later.fields:
            if field.required:
                self.assertIn(field.row, answers)
            else:
                self.assertNotEqual(answers.get(field.row), SKIPPED_INPUT)
                self.assertEqual(field.row in answers, bool(field.value))

    def test_an_empty_optional_field_is_ready_and_no_answer(self) -> None:
        draft = InstallationConfigDraft(
            (
                InstallationConfigField("org", "acme", accepted=True),
                InstallationConfigField(HOST, "", required=False),
            )
        )

        self.assertTrue(draft.ready)
        self.assertEqual(draft.answers, (("org", "acme"),))
        typed = draft.edit(HOST, "ghe.example.com")
        self.assertFalse(typed.ready)
        self.assertEqual(typed.accept(HOST).answers, (("org", "acme"), (HOST, "ghe.example.com")))

    def test_the_form_marks_an_optional_field(self) -> None:
        draft = InstallationConfigDraft(
            (
                InstallationConfigField("org", "acme"),
                InstallationConfigField(HOST, "", required=False),
            )
        )

        lines = render_installation_config_form((), draft, "")

        self.assertIn(f"  {HOST} ({HOST}, optional): []", lines)
        self.assertIn("  org (org): [acme]", lines)


_OWNER = InstallationOwner(
    SourceAlias("company"), ArtifactIdentity("mcp", "github"), Scope.PROJECT, "/root", "claude"
)


class CopyAnswersTest(unittest.TestCase):
    @given(st.lists(st.tuples(st.booleans(), st.booleans()), min_size=1, max_size=6))
    def test_set_later_never_puts_the_placeholder_into_an_optional_input(self, shape) -> None:
        fields = tuple(
            InstallationInputField(
                _OWNER,
                ConfigInput(InputId(f"input-{index}"), EnvironmentBinding("X"), required=required),
            )
            for index, (required, _) in enumerate(shape)
        )
        answers = tuple(
            ArtifactAnswer(_OWNER.source, _OWNER.artifact, field.input.id, "given")
            for field, (_, answered) in zip(fields, shape, strict=True)
            if answered
        )

        copied = {
            item.source.input: item.source.value  # type: ignore[union-attr]
            for item in copy_artifact_answers(fields, answers, skip_unanswered=True)
        }

        for field, (required, answered) in zip(fields, shape, strict=True):
            expected = "given" if answered else SKIPPED_INPUT if required else None
            self.assertEqual(copied.get(field.input.id), expected)


class InstallFormTest(unittest.TestCase):
    def test_07_asks_the_optional_input_and_binds_it_only_when_answered(self) -> None:
        with _environment(authored=AUTHORED_OPTIONAL) as env:
            handler = _actions(env)
            handler._context = replace(  # noqa: SLF001 - production composition under test
                handler._context,
                credential_providers=(_MemoryCredentialProvider(),),
            )

            def prepare(*answers):
                return handler.handle(
                    ConsumerUiCommand(
                        ConsumerUiCommandKind.PREPARE_ACTION,
                        action=ConsumerActionKind.INSTALL,
                        selection=(f"{GITHUB}@1.5.0",),
                        targets=("claude",),
                        config_answers=tuple((f"{GITHUB}\t{key}", value) for key, value in answers),
                    )
                )

            asked = prepare()
            draft = asked.event.config_draft
            assert draft is not None
            self.assertEqual(
                [(field.id, field.value, field.required) for field in draft.fields],
                [("github-org", "acme", True), (HOST, "", False)],
            )
            rows = {
                item.row
                for item in asked.source.screens.installation_inputs
                if isinstance(item, ConfigInputView)
            }
            self.assertIn(f"{GITHUB}\t{HOST}", rows)

            def bound():
                pending = handler._pending  # noqa: SLF001
                assert pending is not None
                composed = pending.prepared.draft.inputs
                return {
                    item.input.id.value
                    for owner in pending.prepared.draft.owners
                    for item in composed.bound_for(owner).inputs
                }

            prepare(("github-org", "acme"))
            self.assertNotIn(HOST, bound())
            prepare(("github-org", "acme"), (HOST, "ghe.example.com"))
            self.assertIn(HOST, bound())


class CommandLineTest(unittest.TestCase):
    def _install(self, env, *flags: str):
        with mock.patch(
            "aart_cli.commands.marketplace._credential_providers",
            return_value=(_RecordingCredentialStore(),),
        ):
            code, payload = env.run(
                "consume", "install", GITHUB, "--profile", "claude", *flags, "--yes"
            )
        self.assertEqual(code, 0, payload)
        config = env.project / ".claude/aart-cli/mcp/company/github/config/claude.conf"
        return config.read_text(encoding="utf-8")

    def test_set_later_leaves_an_optional_input_out_of_the_configuration(self) -> None:
        with _environment(authored=AUTHORED_OPTIONAL) as env:
            written = self._install(env, "--set-later")

        self.assertNotIn(HOST, written)
        self.assertNotIn(SKIPPED_INPUT, written)

    def test_an_optional_input_given_on_the_command_line_is_written(self) -> None:
        with _environment(authored=AUTHORED_OPTIONAL) as env:
            written = self._install(
                env, "--set-later", "--input", f"{GITHUB}:{HOST}=ghe.example.com"
            )

        self.assertIn(f"{HOST}=ghe.example.com\n", written)


if __name__ == "__main__":
    unittest.main()
