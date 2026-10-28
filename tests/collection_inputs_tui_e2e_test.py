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
# The review offers a dependency manager only when the host has more than one; pin both so the
# keys below land on the same rows whether or not this machine has uv.
_INSTALLERS = tuple(
    RemediationCapability(RemediationCapabilityKind.PYTHON_INSTALLER, name)
    for name in ("pip", "uv")
)
_STARTER = RegistryCollection("starter", "GitHub and Jira.", ("mcp/github", "mcp/jira"))


def _with_starter(_authored, **keywords):
    return _published_registries(AUTHORED_MCP, _AUTHORED_JIRA, _STARTER, **keywords)


class CollectionInputsShellTest(unittest.TestCase):
    def test_07_and_07b_ask_each_member_once_and_set_later_blocks_nothing(self) -> None:
        provider = _Keeping()
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
                env,
                _at(ConsumerScreen.MARKETPLACE),
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
                # 07: GitHub's default cleared, Jira's kept; Set later, above the first value; the
                # dependency manager as it is.
                *((BACKSPACE,) * len("acme")),
                UP,
                ENTER,
                ENTER,
                # 07b: Set later, above the first credential; then Ready.
                UP,
                ENTER,
                ENTER,
                actions=handler,
            )
            configs = {
                (path.parent.parent.name, path.stem): path.read_text(encoding="utf-8")
                for path in env.project.rglob("config/*.conf")
            }

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
        ready = terminal.screen_containing("ready to install")
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
