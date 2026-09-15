"""Verify-and-repair converges one recorded installation without resolving anything.

A repair is the lifecycle that has to work when nothing else does: the source may be gone, the
registry unreachable and the network down, and the question is still only whether this machine
matches what it recorded. So these tests break the machine after the source has been removed from
the configuration, and prove the repair puts it back anyway.

The boundary is proven too. A receipt records the digest its launcher had, never its content, so a
repair that would have to rewrite the launcher fails at that step naming what nothing here holds,
rather than writing something nobody planned (D-086).
"""

from __future__ import annotations

import datetime as dt
import os
import shutil
import stat
import unittest

from agent_artifacts.domain.harness import Scope
from agent_artifacts.domain.identifiers import ObjectDigest
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.configured_installation_action import InstallationHost
from agent_artifacts.io.configured_repair_action import (
    complete_configured_repair,
    prepare_configured_repair,
)
from agent_artifacts.io.consumer_machine import read_installed_inspections
from tests.configured_install_command_e2e_test import COORDINATE, _environment
from tests.configured_uninstall_command_e2e_test import _delivered

TODAY = dt.date(2026, 9, 1)
RECORDED_AT = "2026-09-01T09:15:00+00:00"


def _delete_delivery(env) -> None:
    """Take the delivered tree away the way losing it actually happens.

    A payload copied out of the object store carries the store's read-only modes, so the tree is
    made removable first -- exactly as the delivery interpreter does, and inside the same tree.
    """

    tree = _delivered(env).parent
    for root, directories, files in os.walk(tree):
        for name in (*directories, *files):
            path = os.path.join(root, name)
            os.chmod(path, os.stat(path).st_mode | stat.S_IWUSR)
    os.chmod(tree, os.stat(tree).st_mode | stat.S_IWUSR)
    shutil.rmtree(tree)


class ConfiguredRepairActionTest(unittest.TestCase):
    def _host(self, env) -> InstallationHost:
        return InstallationHost(
            env.paths.data_root,
            str(env.project),
            str(env.home),
            Scope.PROJECT,
            ("claude",),
        )

    def _inspection(self, env):
        host = self._host(env)
        inspected = read_installed_inspections(
            state_root=host.state_root,
            harness_root=host.harness_root,
            scope=host.scope,
            profiles=host.profiles,
        )
        self.assertIsInstance(inspected, Ok, inspected)
        self.assertEqual(len(inspected.value.inspections), 1, inspected.value.inspections)
        return inspected.value.inspections[0]

    def _repaired(self, env) -> None:
        """Converge the machine back onto its receipt, as a second actor would."""

        prepared = prepare_configured_repair(self._inspection(env), policy=EffectivePolicy())
        assert isinstance(prepared, Ok), prepared
        completed = complete_configured_repair(
            prepared.value,
            expected_review_digest=prepared.value.review_digest,
            host=self._host(env),
            policy=EffectivePolicy(),
            recorded_at="2026-09-01T09:00:00+00:00",
            today=TODAY,
        )
        assert isinstance(completed, Ok), completed

    def _installed(self, env) -> None:
        code, payload = env.run(
            "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
        )
        self.assertEqual(code, 0, payload)
        self.assertTrue(_delivered(env).exists())

    def test_a_machine_that_matches_its_receipt_plans_nothing(self) -> None:
        with _environment() as env:
            self._installed(env)

            prepared = prepare_configured_repair(self._inspection(env), policy=EffectivePolicy())

            self.assertIsInstance(prepared, Ok, prepared)
            self.assertTrue(prepared.value.converged)
            self.assertEqual(prepared.value.plan.repair.steps, ())

    def test_a_deleted_delivery_is_planned_and_put_back_without_the_source(self) -> None:
        with _environment() as env:
            self._installed(env)
            _delete_delivery(env)
            env.disable_source()

            prepared = prepare_configured_repair(self._inspection(env), policy=EffectivePolicy())
            self.assertIsInstance(prepared, Ok, prepared)
            self.assertFalse(prepared.value.converged)
            self.assertFalse(_delivered(env).exists(), "preparation touched the machine")

            completed = complete_configured_repair(
                prepared.value,
                expected_review_digest=prepared.value.review_digest,
                host=self._host(env),
                policy=EffectivePolicy(),
                recorded_at=RECORDED_AT,
                today=TODAY,
            )

            self.assertIsInstance(completed, Ok, completed)
            self.assertTrue(_delivered(env).exists(), "the repair did not restore the delivery")
            self.assertEqual(completed.value.outcome.status.value, "completed")

    def test_the_repair_reaches_the_timeline_and_the_machine_it_left_behind(self) -> None:
        with _environment() as env:
            self._installed(env)
            _delete_delivery(env)
            prepared = prepare_configured_repair(self._inspection(env), policy=EffectivePolicy())
            self.assertIsInstance(prepared, Ok, prepared)

            completed = complete_configured_repair(
                prepared.value,
                expected_review_digest=prepared.value.review_digest,
                host=self._host(env),
                policy=EffectivePolicy(),
                recorded_at=RECORDED_AT,
                today=TODAY,
            )

            self.assertIsInstance(completed, Ok, completed)
            recorded = completed.value.recorded.receipt
            self.assertEqual(recorded.recorded_at, RECORDED_AT)
            self.assertEqual(recorded.intent, "repair")
            machine = completed.value.machine
            self.assertEqual([item.coordinate for item in machine.installed], [recorded.artifact])
            self.assertEqual(machine.installed[0].health, "ready")
            self.assertIn(RECORDED_AT, [entry.recorded_at for entry in machine.activity.entries])

    def test_a_confirmed_digest_that_is_not_this_plans_is_refused(self) -> None:
        with _environment() as env:
            self._installed(env)
            _delete_delivery(env)
            prepared = prepare_configured_repair(self._inspection(env), policy=EffectivePolicy())
            self.assertIsInstance(prepared, Ok, prepared)

            completed = complete_configured_repair(
                prepared.value,
                expected_review_digest=ObjectDigest("sha256", "b" * 64),
                host=self._host(env),
                policy=EffectivePolicy(),
                recorded_at=RECORDED_AT,
                today=TODAY,
            )

            self.assertIsInstance(completed, Err)
            self.assertIn("since it was reviewed", completed.diagnostics[0].message)
            self.assertFalse(_delivered(env).exists(), "a refused repair still wrote")

    def test_a_machine_that_moved_after_the_review_is_refused_under_the_lease(self) -> None:
        """The precondition is re-measured inside the lease, not assumed to have held."""

        with _environment() as env:
            self._installed(env)
            _delete_delivery(env)
            prepared = prepare_configured_repair(self._inspection(env), policy=EffectivePolicy())
            self.assertIsInstance(prepared, Ok, prepared)
            # Somebody else put it back between the review and the confirmation.
            self._repaired(env)

            completed = complete_configured_repair(
                prepared.value,
                expected_review_digest=prepared.value.review_digest,
                host=self._host(env),
                policy=EffectivePolicy(),
                recorded_at=RECORDED_AT,
                today=TODAY,
            )

            self.assertIsInstance(completed, Err)
            self.assertIn("changed after Review", completed.diagnostics[0].message)

    def test_preparing_a_repair_needs_an_inspected_installation(self) -> None:
        prepared = prepare_configured_repair("company/skill/x", policy=EffectivePolicy())

        self.assertIsInstance(prepared, Err)
        self.assertIn("one inspected installation", prepared.diagnostics[0].message)


if __name__ == "__main__":
    unittest.main()
