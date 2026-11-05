"""§173.5, §172.3, §172.6: a Collection's members are configured once each, under their own names.

The Registry here approved two MCP servers, each with a configuration value and a credential, and a
Collection naming both. Installing the Collection through the real shell, 07 lists each member's
configuration under that member and 07b each member's credential once. Set later keeps what a field
holds and leaves an empty one `AART_NOT_SET`, per member; Ready lists each placeholder, and nothing
blocks the install.
"""

from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from unittest import mock

from aart_cli.application.consumer_views import ConsumerScreen
from aart_cli.domain.inputs import SKIPPED_INPUT
from aart_cli.domain.inspection import RemediationCapability, RemediationCapabilityKind
from aart_cli.tui_consumer import PREPARING_INSTALL
from tests.artifact_installation_e2e_test import MANIFEST
from tests.configured_install_command_e2e_test import _environment
from tests.configured_installation_draft_e2e_test import (
    AUTHORED_MCP,
    RegistryCollection,
    _published_registries,
)
from tests.consumer_application_e2e_test import _actions, _at, _drive
from tests.consumer_shell_test import BACKSPACE, DOWN, ENTER, INSTALL_CUSTOM, RIGHT, SPACE, UP
from tests.credential_guidance_test import _Journal
from tests.install_credentials_test import _Keeping

_JIRA = copy.deepcopy(MANIFEST)
_JIRA["artifact"]["name"] = "jira"
_JIRA["inputs"][0].update(
    id="jira-token",
    inject={"type": "environment", "variable": "JIRA_TOKEN"},
    help={"label": "Jira token"},
)
_JIRA["inputs"][1].update(
    id="jira-site",
    default="example",
    inject={"type": "environment", "variable": "JIRA_SITE"},
    help={"label": "Jira site"},
)
_AUTHORED_JIRA = tuple(
    (
        path.replace("github/", "jira/"),
        json.dumps(_JIRA) if path.endswith("aart-cli.json") else content,
    )
    for path, content in AUTHORED_MCP
)
# Both dependency managers, pinned so the keys below are the same whether or not this machine has
# uv: neither is asked for, because the install takes Settings' (D-526).
_INSTALLERS = tuple(
    RemediationCapability(RemediationCapabilityKind.PYTHON_INSTALLER, name)
    for name in ("pip", "uv")
)
_STARTER = RegistryCollection("starter", "GitHub and Jira.", ("mcp/github", "mcp/jira"))


def _with_starter(_authored, **keywords):
    return _published_registries(AUTHORED_MCP, _AUTHORED_JIRA, _STARTER, **keywords)


class _Beats:
    """Stands in for the shell's heartbeat and keeps every frame it would beat over (§203)."""

    frames: list[tuple[str, ...]] = []

    def __init__(self, _terminal, lines, **_keywords) -> None:
        type(self).frames.append(lines)

    def show(self, lines) -> None:
        type(self).frames.append(lines)

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        return None


#: Marketplace to Success for the Collection on claude and opencode, with Set later on 07 and 07b.
_SET_LATER_INSTALL = (
    # Marketplace rows are the two servers, then the Collection; preview, install.
    DOWN,
    DOWN,
    ENTER,
    *INSTALL_CUSTOM,
    # 05: the Collection on claude and opencode.
    SPACE,
    RIGHT,
    SPACE,
    ENTER,
    # 07a as it is (§209).
    ENTER,
    # 07: GitHub's default cleared, Jira's kept; Set later, above the first value. The
    # dependency manager is Settings' (D-526), so 07b comes next.
    *((BACKSPACE,) * len("acme")),
    UP,
    ENTER,
    # 07b: Set later, above the first credential; then Ready.
    UP,
    ENTER,
    ENTER,
)


class CollectionInputsShellTest(unittest.TestCase):
    def _install(self, provider, keys=_SET_LATER_INSTALL):
        with (
            mock.patch(
                "tests.configured_install_command_e2e_test._published_registry", _with_starter
            ),
            mock.patch(
                "aart_cli.io.configured_installation_action.observe_python_installers",
                return_value=_INSTALLERS,
            ),
            _environment() as env,
        ):
            base = _actions(env)
            handler = type(base)(
                replace(base._context, credential_providers=(provider,)),  # noqa: SLF001
                terminal_handover=_Journal().handover,
            )
            finished, terminal, _ = _drive(
                env, _at(ConsumerScreen.MARKETPLACE), *keys, actions=handler
            )
            configs = {
                (path.parent.parent.name, path.stem): path.read_text(encoding="utf-8")
                for path in env.project.rglob("config/*.conf")
            }
        return finished, terminal, configs

    def test_while_set_later_prepares_the_install_the_screen_names_no_form_row(self) -> None:
        # The frame beaten over while the answers are prepared was drawn from 07's form rows on
        # 05, each one `[ ] None`, for as long as a Collection took to prepare.
        _Beats.frames = []
        with mock.patch("aart_cli.tui_consumer.Heartbeat", _Beats):
            finished, terminal, _ = self._install(_Keeping())

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertTrue(_Beats.frames)
        drawn = ["\n".join(frame) for frame in _Beats.frames]
        for frame in drawn:
            self.assertNotIn("None", frame)
            self.assertNotIn("not offered", frame)
        # 05 shows what was chosen while it is prepared, or, before it has rows, that it is.
        for frame in (frame for frame in drawn if frame.split("\n", 1)[0].endswith("Selection")):
            self.assertTrue(
                "company/collection/starter" in frame or PREPARING_INSTALL.lower() in frame.lower(),
                frame,
            )
        # Preparing before 05 has rows of its own says so, rather than that nothing is planned.
        self.assertTrue(any(PREPARING_INSTALL.lower() in frame.lower() for frame in drawn))
        self.assertFalse(any("nothing has been planned" in frame.lower() for frame in drawn))

    def test_after_07_the_screen_stays_on_07_until_the_next_one_is_ready(self) -> None:
        # D-526: submitting 07 rewinds to 05 and prepares again. The beat was drawn over 05, so 05
        # appeared a second time and then left by itself for 07b.
        # With pip and uv both usable, 05 also came back to ask which (D-526): it no longer does.
        _Beats.frames = []
        with mock.patch("aart_cli.tui_consumer.Heartbeat", _Beats):
            finished, terminal, _ = self._install(_Keeping())

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)

        def after_the_form(frames) -> list[str]:
            screens = [frame[0].rsplit(" / ", 1)[-1] for frame in frames]
            return (
                screens[screens.index("Required Inputs") :] if "Required Inputs" in screens else []
            )

        # Neither a drawn frame nor one beaten over while preparing goes back to 05 after 07, and
        # the preparation after 07 is beaten over 07 itself.
        drawn, beaten = after_the_form(terminal.frames), after_the_form(_Beats.frames)
        self.assertTrue(beaten, [frame[0] for frame in _Beats.frames])
        self.assertNotIn("Review Selection", drawn, drawn)
        self.assertNotIn("Review Selection", beaten, beaten)

    def test_while_the_collection_installs_each_member_is_named(self) -> None:
        # Installing a Collection drew only "Installing (6 of 7 done)": every member numbers its
        # steps from one, so their reports overwrote each other and no frame named a member.
        _Beats.frames = []
        with mock.patch("aart_cli.tui_consumer.Heartbeat", _Beats):
            finished, terminal, _ = self._install(_Keeping())

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        running = [
            "\n".join(frame)
            for frame in _Beats.frames
            if any(line.strip().lower().startswith("installing 2 artifacts") for line in frame)
        ]
        self.assertTrue(running, [frame[:4] for frame in _Beats.frames])
        first, last = running[0], running[-1]
        self.assertIn("▸ company/mcp/github", first)
        self.assertIn("· company/mcp/jira", first)
        self.assertIn("✓ company/mcp/github", last)
        self.assertIn("company/mcp/jira", last)
        self.assertTrue(any("▸ company/mcp/jira" in frame for frame in running))

    def test_07_and_07b_ask_each_member_once_and_set_later_blocks_nothing(self) -> None:
        provider = _Keeping()
        # `[v]` on Ready before confirming: what is left as the placeholder is More info's (D-525).
        keys = (*_SET_LATER_INSTALL[:-1], "v", _SET_LATER_INSTALL[-1])
        finished, terminal, configs = self._install(provider, keys)

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        configuration = terminal.screen_containing("Jira site (jira-site)")
        self.assertEqual(configuration.count("GitHub organisation (github-org)"), 1)
        self.assertEqual(configuration.count("Jira site (jira-site)"), 1)
        self.assertLess(
            configuration.index("company/mcp/github"), configuration.index("GitHub organisation")
        )
        self.assertLess(configuration.index("company/mcp/jira"), configuration.index("Jira site"))
        credentials = terminal.screen_containing("Jira token (jira-token)")
        self.assertEqual(credentials.count("GitHub token (github-token)"), 1)
        self.assertEqual(credentials.count("Jira token (jira-token)"), 1)
        self.assertNotIn(SKIPPED_INPUT, terminal.screen_containing("ready to install"))
        ready = terminal.screen_containing("install plan (Verbose)")
        for item in (
            "company/mcp/github: github-org",
            "company/mcp/github: github-token",
            "company/mcp/jira: jira-token",
        ):
            self.assertIn(item, ready)
        self.assertNotIn("company/mcp/jira: jira-site", ready)
        # Asked once per member, written into that member's installation on each harness.
        self.assertEqual(provider.handed, [SKIPPED_INPUT] * 4)
        self.assertEqual(len(provider.stored), 4)
        self.assertEqual(len(configs), 4, sorted(configs))
        for harness in ("claude", "opencode"):
            self.assertIn(f"github-org={SKIPPED_INPUT}\n", configs["github", harness])
            self.assertIn("jira-site=example\n", configs["jira", harness])


if __name__ == "__main__":
    unittest.main()
