"""CP-42: an installation is measured, and changed, only where it was made.

The Enterprise owner's Doctor reported `harness:opencode: missing` for every project installation
of one MCP, and Repair changed nothing. The machine read resolved each project installation's
harness entry against the directory aart-cli was opened in, not against the project it was
installed into, so another project's entry was looked for here. A repair planned from that
reading would also have written the entry into this project (D-479).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import pathlib
import tempfile
import unittest

from aart_cli.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
)
from aart_cli.consumer_actions import ConsumerActionContext, LocalConsumerActions
from aart_cli.domain.harness import Scope
from aart_cli.domain.installation_owner import InstallationOwner
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.result import Ok
from aart_cli.io.configured_installation_action import InstallationHost
from aart_cli.io.consumer_machine import read_consumer_machine
from aart_cli.io.receipt_store import LocalReceiptStore
from tests import configured_configuration_action_e2e_test as configured
from tests.artifact_installation_e2e_test import ORG
from tests.repair_e2e_test import COORDINATE, InstalledFixture

TODAY = dt.date(2026, 10, 23)


class AnotherProjectsInstallationIsMeasuredInThatProject(InstalledFixture):
    def setUp(self) -> None:
        super().setUp()
        owner = InstallationOwner(
            COORDINATE.source, COORDINATE.artifact, Scope.PROJECT, str(self.scope), "tabnine"
        )
        self.state_root = str(self.scope / "state")
        recorded = LocalReceiptStore(self.state_root).record_installation(
            COORDINATE, dataclasses.replace(self.receipt, owner=owner)
        )
        self.assertIsInstance(recorded, Ok, getattr(recorded, "diagnostics", ()))
        elsewhere = tempfile.TemporaryDirectory()
        self.addCleanup(elsewhere.cleanup)
        self.elsewhere = pathlib.Path(elsewhere.name)

    def _drift_read_from(self, project: pathlib.Path) -> list[tuple[str, str]]:
        read = read_consumer_machine(
            state_root=self.state_root,
            harness_root=str(project),
            today=TODAY,
            project_root=str(project),
            user_home=str(self.scope / "home"),
            data_root=str(self.scope / "data"),
        )
        self.assertIsInstance(read, Ok, getattr(read, "diagnostics", ()))
        (installed,) = read.value.installed
        return [(item.component, item.kind) for item in installed.drift]

    def test_opened_in_another_project_it_reads_as_it_does_in_its_own(self) -> None:
        self.assertEqual(self._drift_read_from(self.elsewhere), self._drift_read_from(self.scope))

    def test_its_harness_entry_is_not_reported_missing_from_another_project(self) -> None:
        drift = self._drift_read_from(self.elsewhere)

        self.assertFalse([item for item in drift if item[0].startswith("harness")], drift)


class AnotherProjectsInstallationIsChangedOnlyThere(unittest.TestCase):
    """The real handler, opened in a second project over the first project's installations."""

    setUp = configured.ConfiguredConfigurationActionE2ETest.setUp
    _inspection = configured.ConfiguredConfigurationActionE2ETest._inspection

    def _handler_elsewhere(self) -> LocalConsumerActions:
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        host = InstallationHost(
            self.data_root, str(elsewhere), self.user_home, Scope.PROJECT, configured.HARNESSES
        )
        machine = read_consumer_machine(
            state_root=host.state_root,
            harness_root=host.harness_root,
            today=TODAY,
            project_root=host.project_root,
            user_home=host.user_home,
            data_root=host.data_root,
            credential_providers=(self.provider,),
        )
        assert isinstance(machine, Ok), machine
        return LocalConsumerActions(
            ConsumerActionContext(
                host,
                self.effective,
                machine.value,
                policy=EffectivePolicy(),
                credential_providers=(self.provider,),
            )
        )

    def test_every_change_is_refused_and_says_where_to_make_it(self) -> None:
        installation = self._inspection().installation
        handler = self._handler_elsewhere()
        before = sorted(str(path) for path in self.root.rglob("*"))

        for action, extra in (
            (ConsumerActionKind.VERIFY_REPAIR, {}),
            (ConsumerActionKind.UPDATE, {}),
            (ConsumerActionKind.UNINSTALL, {}),
            (
                ConsumerActionKind.CONFIGURE,
                {"targets": ("claude",), "config_answers": ((ORG.value, "other-team"),)},
            ),
        ):
            with self.subTest(action=action):
                update = handler.handle(
                    ConsumerUiCommand(
                        ConsumerUiCommandKind.PREPARE_ACTION,
                        action=action,
                        focus=installation,
                        **extra,
                    )
                )

                said = "\n".join(update.source.screens.notice)
                self.assertFalse(update.event.review_digest, said)
                self.assertIn("installed in another project", said)
                self.assertIn(f"open aart-cli in {self.project_root}", said)
        self.assertEqual(sorted(str(path) for path in self.root.rglob("*")), before)

    def test_the_project_it_was_made_in_may_still_change_it(self) -> None:
        machine = read_consumer_machine(
            state_root=self.host.state_root,
            harness_root=self.host.harness_root,
            today=TODAY,
            project_root=self.host.project_root,
            user_home=self.host.user_home,
            data_root=self.host.data_root,
            credential_providers=(self.provider,),
        )
        assert isinstance(machine, Ok), machine
        handler = LocalConsumerActions(
            ConsumerActionContext(
                self.host,
                self.effective,
                machine.value,
                policy=EffectivePolicy(),
                credential_providers=(self.provider,),
            )
        )

        update = handler.handle(
            ConsumerUiCommand(
                ConsumerUiCommandKind.PREPARE_ACTION,
                action=ConsumerActionKind.VERIFY_REPAIR,
                focus=self._inspection().installation,
            )
        )

        self.assertNotIn("installed in another project", "\n".join(update.source.screens.notice))
        self.assertTrue(update.event.review_digest, update.source.screens.notice)


if __name__ == "__main__":
    unittest.main()
