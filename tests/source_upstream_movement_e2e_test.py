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

Every scenario here runs over one real temporary machine with one real local source that the test
republishes into, through `aart source sync`, `aart marketplace status` and `aart marketplace
update`. Nothing below the CLI is mocked.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.marketplace_lifecycle_e2e_test import _COORDINATE
from tests.source_sync_command_e2e_test import (
    _current_digest,
    _environment_over_a_writable_source,
    _source_json,
)

_PAYLOAD = ("artifacts", "skill", "code-review", "payload", "SKILL.md")
_SECOND = "# Code Review\n\nSecond revision.\n"


def _payload_file(location: Path) -> Path:
    return location.joinpath(*_PAYLOAD)


def _record(env) -> dict:
    state = json.loads((env.project / ".agent-artifacts" / "manifest.json").read_text())
    installations = state["installations"]
    assert len(installations) == 1, state
    return installations[0]


class UpstreamMovementTest(unittest.TestCase):
    def test_a_sync_does_not_rewrite_what_an_installation_was_installed_from(self) -> None:
        """INV-219: the record is historical truth, and `sync` is not a reconciliation.

        This one is a guard rather than a regression: nothing on the sync path writes install
        state today, so there is no mutation of shipped code that turns it red. What makes it a
        real assertion rather than a vacuous one is its sibling three tests down, which changes
        exactly these fields through exactly this comparison when an update runs -- so the
        comparison is known to be capable of seeing a rewrite, and this test says the sync path
        must never be the thing that causes one.
        """

        with _environment_over_a_writable_source() as (env, location):
            env.run("marketplace", "install", _COORDINATE, "--profile", "claude", "--yes")
            installed_from = _record(env)
            first = _current_digest(env)
            _payload_file(location).write_text(_SECOND, encoding="utf-8")

            code, payload = _source_json(env, "source", "sync")

            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["sources"][0]["disposition"], "published")
            self.assertNotEqual(_current_digest(env), first)
            # The store moved and the record did not: every field of it, not just the revision,
            # because a rewrite that preserved the revision and changed the origin would be the
            # same defect wearing a different field.
            self.assertEqual(_record(env), installed_from)
            self.assertEqual(installed_from["source"]["resolved_commit"], f"local:{first[7:]}")

    def test_the_new_revision_is_offered_rather_than_applied(self) -> None:
        """INV-210: a registry change raises a finding; mutating an installation needs a plan."""

        with _environment_over_a_writable_source() as (env, location):
            env.run("marketplace", "install", _COORDINATE, "--profile", "claude", "--yes")
            placed = env.project / ".claude" / "skills" / "code-review" / "SKILL.md"
            first_bytes = placed.read_bytes()
            _payload_file(location).write_text(_SECOND, encoding="utf-8")
            _source_json(env, "source", "sync")

            code, status = env.run("marketplace", "status", "--profile", "claude")

            self.assertEqual(code, 0, status)
            self.assertEqual([item["status"] for item in status["items"]], ["update-available"])
            # Named, and not yet done: the file on disk is still the revision that was reviewed.
            self.assertEqual(placed.read_bytes(), first_bytes)

    def test_an_explicit_update_is_what_rebinds_the_record(self) -> None:
        """The counterpart: the record is not frozen, it is only not rewritten behind the operator."""

        with _environment_over_a_writable_source() as (env, location):
            env.run("marketplace", "install", _COORDINATE, "--profile", "claude", "--yes")
            _payload_file(location).write_text(_SECOND, encoding="utf-8")
            _source_json(env, "source", "sync")
            second = _current_digest(env)

            code, payload = env.run("marketplace", "update", "--profile", "claude", "--yes")

            self.assertEqual(code, 0, payload)
            self.assertEqual([item["status"] for item in payload["items"]], ["changed"])
            self.assertEqual(_record(env)["source"]["resolved_commit"], f"local:{second[7:]}")
            placed = env.project / ".claude" / "skills" / "code-review" / "SKILL.md"
            self.assertEqual(placed.read_text(encoding="utf-8"), _SECOND)

    def test_a_rolled_back_upstream_is_a_new_state_rather_than_an_erased_one(self) -> None:
        """INV-216: a correction is something that happened, not something that unhappened.

        This is where content addressing bites. Republishing the first revision's bytes produces
        the first revision's snapshot digest, so the store looks exactly as it did before the
        second revision existed. If reconciliation compared the store against itself it would call
        this installation current and quietly leave the second revision's payload in the project.
        It compares against the record instead, so the rollback is offered as work to do.
        """

        with _environment_over_a_writable_source() as (env, location):
            payload_file = _payload_file(location)
            original = payload_file.read_bytes()
            env.run("marketplace", "install", _COORDINATE, "--profile", "claude", "--yes")
            first = _current_digest(env)
            payload_file.write_text(_SECOND, encoding="utf-8")
            _source_json(env, "source", "sync")
            env.run("marketplace", "update", "--profile", "claude", "--yes")

            payload_file.write_bytes(original)
            _source_json(env, "source", "sync")

            # The store is byte-for-byte back where it started, and this installation is not.
            self.assertEqual(_current_digest(env), first)
            code, status = env.run("marketplace", "status", "--profile", "claude")
            self.assertEqual(code, 0, status)
            self.assertEqual([item["status"] for item in status["items"]], ["update-available"])
            placed = env.project / ".claude" / "skills" / "code-review" / "SKILL.md"
            self.assertEqual(placed.read_text(encoding="utf-8"), _SECOND)

            code, applied = env.run("marketplace", "update", "--profile", "claude", "--yes")

            self.assertEqual(code, 0, applied)
            self.assertEqual(placed.read_bytes(), original)
            self.assertEqual(_record(env)["source"]["resolved_commit"], f"local:{first[7:]}")


if __name__ == "__main__":
    unittest.main()
