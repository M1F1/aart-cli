"""CP-15: what a moving upstream may and may not rewrite.

`INV-219` says historical provenance is not rewritten when upstream moves, and `INV-210` says
registry changes may raise findings but installation mutations still require an explicit
reconciliation plan. Both are about the same fear: that publishing a new revision quietly changes
what an already-installed artifact claims to be.

Neither had a public-flow test. The behaviour is right today -- these tests were written green and
each is proven against a mutation below -- and it is right for a reason worth writing down, because
the reason is not obvious from the values involved: a snapshot is identified by its content, so an
upstream that is rolled back republishes the *same digest the first revision had*. Digest equality
therefore cannot mean "nothing has happened here since". What remembers is the installation record,
and that is exactly what neither a sync nor a rollback is allowed to touch.

Every scenario here runs over one real temporary machine with one real local Registry that the test
republishes into, through `aart-cli consume registry sync`, `aart-cli consume status` and
`aart-cli consume update`. Nothing below the CLI is mocked.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from tests.marketplace_lifecycle_e2e_test import _COORDINATE, _PLACED
from tests.reference_registry import ESSENTIALS, memory, republish, skill
from tests.source_sync_command_e2e_test import (
    _current_digest,
    _environment_over_a_writable_source,
    _installation_records,
    _source,
)

_SECOND = "# Code Review\n\nSecond revision.\n"


def _publish_second(location: Path) -> None:
    """The Maintainer approves 1.1.0 beside 1.0.0, the way a Registry moves."""

    republish(location, skill(), skill("1.1.0", _SECOND), memory(), ESSENTIALS)


def _withdraw_second(location: Path) -> None:
    """The Registry goes back to offering only 1.0.0: a rollback, published as a new revision."""

    republish(location, skill(), memory(), ESSENTIALS)


def _installed(env) -> list[str]:
    code, status = env.run("consume", "status", "--profile", "claude")
    assert code == 0, status
    return [item["key"] for item in status["items"]]


class UpstreamMovementTest(unittest.TestCase):
    def test_a_sync_does_not_rewrite_what_an_installation_was_installed_from(self) -> None:
        """INV-219: the record is historical truth, and `sync` is not a reconciliation."""

        with _environment_over_a_writable_source() as (env, location):
            env.run("consume", "install", _COORDINATE, "--profile", "claude", "--yes")
            recorded = _installation_records(env)
            first = _current_digest(env)
            _publish_second(location)

            code, text = _source(env, "consume", "registry", "sync")

            self.assertEqual(code, 0, text)
            self.assertIn("reference: published", text)
            self.assertNotEqual(_current_digest(env), first)
            # The store moved and the record did not, byte for byte.
            self.assertEqual(_installation_records(env), recorded)

    def test_the_new_version_is_offered_rather_than_applied(self) -> None:
        """INV-210: a Registry change raises a finding; mutating an installation needs a plan."""

        with _environment_over_a_writable_source() as (env, location):
            env.run("consume", "install", _COORDINATE, "--profile", "claude", "--yes")
            placed = env.project / _PLACED / "SKILL.md"
            first_bytes = placed.read_bytes()
            _publish_second(location)

            code, text = _source(env, "consume", "registry", "sync")

            self.assertEqual(code, 0, text)
            self.assertIn("aart-cli consume update", text)
            # Named, and not yet done: the file on disk is still the version that was reviewed.
            self.assertEqual(_installed(env), [f"{_COORDINATE}@1.0.0"])
            self.assertEqual(placed.read_bytes(), first_bytes)

    def test_an_explicit_update_is_what_rebinds_the_record(self) -> None:
        """The counterpart: the record is not frozen, it is only not rewritten behind the operator."""

        with _environment_over_a_writable_source() as (env, location):
            env.run("consume", "install", _COORDINATE, "--profile", "claude", "--yes")
            _publish_second(location)
            _source(env, "consume", "registry", "sync")

            code, payload = env.run("consume", "update", "--profile", "claude", "--yes")

            self.assertEqual(code, 0, payload)
            self.assertEqual(
                [(item["key"], item["status"]) for item in payload["items"]],
                [(f"{_COORDINATE}@1.1.0", "completed")],
            )
            self.assertEqual(_installed(env), [f"{_COORDINATE}@1.1.0"])
            self.assertIn("Second revision.", (env.project / _PLACED / "SKILL.md").read_text())

    def test_a_rolled_back_registry_is_a_new_state_rather_than_an_erased_one(self) -> None:
        """INV-216: a correction is something that happened, not something that unhappened.

        Content addressing makes the rolled-back Registry the first revision's snapshot again, so
        the store looks as it did before 1.1.0 existed. The installation still remembers 1.1.0,
        and `update` names the move back as a downgrade instead of quietly taking it.
        """

        with _environment_over_a_writable_source() as (env, location):
            env.run("consume", "install", _COORDINATE, "--profile", "claude", "--yes")
            first = _current_digest(env)
            _publish_second(location)
            _source(env, "consume", "registry", "sync")
            env.run("consume", "update", "--profile", "claude", "--yes")
            placed = (env.project / _PLACED / "SKILL.md").read_bytes()

            _withdraw_second(location)
            _source(env, "consume", "registry", "sync")

            self.assertEqual(_current_digest(env), first)
            self.assertEqual(_installed(env), [f"{_COORDINATE}@1.1.0"])
            code, refused = env.run("consume", "update", "--profile", "claude", "--yes")
            self.assertEqual(code, 1, refused)
            self.assertIn("is a downgrade", refused["diagnostics"][0]["message"])
            self.assertEqual((env.project / _PLACED / "SKILL.md").read_bytes(), placed)


if __name__ == "__main__":
    unittest.main()
