"""An adopted identity change leaves the installations made under the old one standing.

`consume registry resubscribe` adopts a new declared identity and rebinds the configuration and the
snapshot store. It cannot touch installation records -- project isolation forbids it, and AART does
not know which projects exist -- so installations made under the old identity must not depend on it.

On the Registry path they do not: an installation's identity is its Registry alias, artifact,
scope, concrete root and harness (§169), and the identity a Registry declares is evidence about the
subscription, never part of a record. These tests drive that through the real CLI -- install under
one identity, adopt another, then reconcile in the project that owns the installation.
"""

from __future__ import annotations

import unittest

from tests.marketplace_lifecycle_e2e_test import _COORDINATE
from tests.reference_registry import REFERENCE_CONTENT, republish
from tests.source_project_isolation_test import _INSTALLED, _source, _stable_snapshot
from tests.source_sync_command_e2e_test import (
    _environment_over_a_writable_source,
    _installation_records,
)

_NEW_IDENTITY = "renamed-reference-registry"


class IdentityChangeReconciliationTest(unittest.TestCase):
    def _adopt_new_identity(self, env, location) -> None:
        """Rename the Registry's declared identity, then adopt it with `resubscribe`."""

        republish(location, *REFERENCE_CONTENT, declared_id=_NEW_IDENTITY)
        code, payload = _source(
            env, "consume", "registry", "resubscribe", "--alias", "reference", "--yes"
        )
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["transition"]["to"]["source_id"], _NEW_IDENTITY)

    def test_an_identity_change_does_not_strand_what_was_installed_under_the_old_one(self) -> None:
        with _environment_over_a_writable_source() as (env, location):
            env.run("consume", "install", _COORDINATE, "--profile", "claude", "--yes")
            records = _installation_records(env)

            self._adopt_new_identity(env, location)

            # The record names the alias, so adopting an identity leaves it byte for byte.
            self.assertEqual(_installation_records(env), records)
            code, status = env.run("consume", "status", "--profile", "claude")
            self.assertEqual(code, 0, status)
            self.assertEqual([item["status"] for item in status["items"]], ["current"])

    def test_the_resubscribe_itself_changes_nothing_beneath_the_project(self) -> None:
        """The fix must not be `resubscribe` reaching into projects."""

        with _environment_over_a_writable_source() as (env, location):
            env.run("consume", "install", _COORDINATE, "--profile", "claude", "--yes")
            before = _stable_snapshot(env.project)
            self.assertIn(str(_INSTALLED / "SKILL.md"), before)

            self._adopt_new_identity(env, location)

            self.assertEqual(_stable_snapshot(env.project), before)

    def test_update_after_the_identity_change_keeps_the_installation_current(self) -> None:
        with _environment_over_a_writable_source() as (env, location):
            env.run("consume", "install", _COORDINATE, "--profile", "claude", "--yes")
            self._adopt_new_identity(env, location)

            code, applied = env.run("consume", "update", "--profile", "claude", "--yes")

            self.assertEqual(code, 0, applied)
            self.assertTrue(applied["finalized"])
            self.assertEqual(
                [(item["key"], item["status"]) for item in applied["items"]],
                [(f"{_COORDINATE}@1.0.0", "current")],
            )
            self.assertTrue((env.project / _INSTALLED / "SKILL.md").is_file())

    def test_rs07_status_reports_the_project_when_the_only_registry_is_removed(self) -> None:
        """The project still has installations, and `status` is what reads them.

        The removal here is the one `consume registry remove` tells an operator to take. Status
        must answer about the *project* rather than refuse about the *configuration*. It does not
        yet say the Registry is gone (B-205).
        """

        with _environment_over_a_writable_source() as (env, _location):
            env.run("consume", "install", _COORDINATE, "--profile", "claude", "--yes")
            _source(env, "consume", "registry", "remove", "--alias", "reference", "--yes")

            code, status = env.run("consume", "status", "--profile", "claude")

            self.assertEqual(code, 0, status)
            self.assertEqual([item["key"] for item in status["items"]], [f"{_COORDINATE}@1.0.0"])
            self.assertTrue((env.project / _INSTALLED / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
