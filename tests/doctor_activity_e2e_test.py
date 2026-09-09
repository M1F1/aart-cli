"""End to end: the audit trail, and the undo Doctor must not invent.

INV-191 makes Activity and Receipt the audit and recovery evidence. `project_activity`,
`activity_from_receipts`, `activity_view_to_data` and `render_activity` all exist, and they are
referenced by `application/consumer_session.py` and by nothing under `agent_artifacts/commands/` --
so the record of what AART did to a machine is reachable from the interactive shell and from
nowhere else. Anyone reading a support report, or working on a box with no terminal to drive,
cannot see it at all.

INV-192 is what makes exposing it non-trivial: Doctor must not invent stronger undo guarantees than
a receipt carries. The pair below is the whole point, and one run produces both halves. An install
that placed a payload and a delivery reports an undo naming exactly those components. The uninstall
that follows reports none -- nothing retained can reverse a removal -- and says so instead of
offering a restore that cannot happen. The absence is evidence because the presence is right beside
it in the same trail (D-138).

Note that `marketplace receipt show` is a different record: it shows the *setup* receipt for one
coordinate, with its own retry and rollback commands. The timeline here carries lifecycle receipts
-- install, update, uninstall, repair -- which is the trail 165 means by Activity, and which no
command surfaced before this.
"""

from __future__ import annotations

import sys
import unittest

from tests.configured_setup_gap_test import CONFIGURED, COORDINATE, _declaring_setup

_VERSIONED = f"{COORDINATE}@1.2.0"
_INSTALL = (
    "marketplace",
    "install",
    COORDINATE,
    "--profile",
    "claude",
    "--yes",
    "--approve-setup-effects",
)
_UNINSTALL = ("marketplace", "uninstall", COORDINATE, "--profile", "claude", "--yes")


@unittest.skipUnless(
    sys.platform == "darwin",
    "the fixture's artifact declares setup, which the setup engine accepts only on darwin "
    "(setup.py:562)",
)
class DoctorActivityE2ETest(unittest.TestCase):
    def _entries(self, payload: dict) -> list[dict]:
        return [entry for day in payload["activity"]["days"] for entry in day["entries"]]

    def test_a_machine_that_has_done_nothing_reports_an_empty_timeline(self) -> None:
        """The baseline that stops every assertion below from passing for the wrong reason."""

        with _declaring_setup() as env:
            code, payload = env.run("doctor")

            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["activity"]["days"], [])
            self.assertEqual(payload["recorded_actions"], [])

            code, output = env.run_text("doctor")

            self.assertEqual(code, 0, output)
            # A bare "Recent activity:" header with nothing under it reads as a rendering that
            # failed, not as a machine that has done nothing. The empty case says so in words.
            self.assertIn("nothing has been recorded on this machine yet", output)

    def test_the_audit_trail_is_reachable_without_the_interactive_shell(self) -> None:
        """INV-191, through a verb rather than through the shell's own assembly."""

        with _declaring_setup() as env:
            code, installed = env.run(*_INSTALL)
            self.assertEqual(code, 0, installed)

            code, payload = env.run("doctor")

            self.assertEqual(code, 0, payload)
            entries = self._entries(payload)
            self.assertTrue(entries, payload["activity"])
            # The exact version, which is the identity the receipt recorded.
            self.assertIn(_VERSIONED, {entry["artifact"] for entry in entries})
            self.assertEqual(
                [item["recorded_at"] for item in payload["recorded_actions"]],
                [entry["recorded_at"] for entry in entries],
                "the timeline and the recorded actions are one observation, not two",
            )
            # Every field the payload publishes is a field something reads: scoped mutation found
            # `artifact` and `status` emitted with nothing holding either.
            recorded = payload["recorded_actions"][0]
            self.assertEqual(recorded["artifact"], _VERSIONED)
            self.assertEqual(recorded["status"], "completed")

    def test_the_trail_is_newest_first_and_holds_every_action_of_the_run(self) -> None:
        with _declaring_setup() as env:
            self.assertEqual(env.run(*_INSTALL)[0], 0)
            self.assertEqual(env.run(*_UNINSTALL)[0], 0)

            code, payload = env.run("doctor")

            self.assertEqual(code, 0, payload)
            actions = payload["recorded_actions"]
            self.assertEqual([item["intent"] for item in actions], ["uninstall", "install"])
            moments = [item["recorded_at"] for item in actions]
            self.assertEqual(moments, sorted(moments, reverse=True), actions)

    def test_an_undo_is_offered_only_where_the_receipt_records_one(self) -> None:
        """INV-192, as a pair: what took effect can be reversed, a removal cannot.

        The false half is evidence only because the true half sits beside it in the same trail --
        an absence asserted where nothing could have been present measures nothing (D-138).
        """

        with _declaring_setup() as env:
            self.assertEqual(env.run(*_INSTALL)[0], 0)
            self.assertTrue((env.project / CONFIGURED).exists(), "the setup wrote nothing")
            self.assertEqual(env.run(*_UNINSTALL)[0], 0)

            code, payload = env.run("doctor")

            self.assertEqual(code, 0, payload)
            by_intent = {item["intent"]: item["undo"] for item in payload["recorded_actions"]}
            placed = by_intent["install"]
            self.assertTrue(placed["available"], by_intent)
            # Named components, not a bare yes: the answer says what it would reverse.
            self.assertEqual(sorted(placed["components"]), ["delivery:claude", "payload"])

            removed = by_intent["uninstall"]
            self.assertFalse(removed["available"], by_intent)
            self.assertEqual(removed["components"], [], "a refusal names nothing to reverse")
            self.assertIn("nothing retained", removed["reason"])

    def test_the_human_report_names_the_actions_and_invents_no_undo(self) -> None:
        with _declaring_setup() as env:
            self.assertEqual(env.run(*_INSTALL)[0], 0)
            self.assertEqual(env.run(*_UNINSTALL)[0], 0)

            code, output = env.run_text("doctor")

            self.assertEqual(code, 0, output)
            self.assertIn("Recent activity:", output)
            # The components too, not just the verdict: with two of them the separator is
            # observable, and an operator reading this needs to know what would be reversed.
            self.assertIn(f"{_VERSIONED} (install) can be undone: delivery:claude, payload", output)
            self.assertIn(f"{_VERSIONED} (uninstall) cannot be undone", output)


if __name__ == "__main__":
    unittest.main()
