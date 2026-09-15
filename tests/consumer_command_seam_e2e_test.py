"""What the four public consumer commands promise, pinned before their dispatch is rerouted.

`install`, `update`, `uninstall` and `status` are about to stop running through the legacy consumer
service and start running through `begin_installation` / `execute_installation` /
`record_installation`. That is a change of machinery, not of contract, and the way to keep it one is
to write down the contract first -- while the legacy path is still the thing answering, so that what
is written down is what is actually true rather than what the replacement happens to do.

Every assertion here is therefore a characterization: it describes the seam as it behaves today. If
rerouting moves one of them, that is the test doing its job, and the choice becomes explicit --
either the reroute is wrong, or the contract is being changed deliberately and this file changes
with it. Nothing here is a wish about the canonical path.

Three properties matter most, because they are the ones a swap of machinery is most likely to break
quietly:

* **Durability.** `status` answers from disk. The process that reports an installation is not the
  process that performed it and holds nothing from it, so an in-memory shortcut cannot pass.
* **One plan, two renderings.** `--json` and the human text are projections of the same review, and
  the review digest is what proves it. An agent and a person must be authorizing the same thing.
* **Fail-closed review.** Without `--yes` nothing is finalized and nothing reaches the disk, and the
  review still carries the digest a later invocation must match.
"""

from __future__ import annotations

import json
import unittest

from tests.marketplace_lifecycle_e2e_test import _COORDINATE, _environment

#: Every machine-readable payload carries these, whatever the command and whatever the outcome. An
#: agent that cannot find them cannot tell a refusal from a success.
_ENVELOPE = frozenset({"schema_version", "ok", "operation", "finalized"})


class DurableStatusTest(unittest.TestCase):
    """`status` reports the disk, not a memory of what this process did."""

    def test_a_later_invocation_names_what_an_earlier_one_installed(self) -> None:
        with _environment() as env:
            installed, _ = env.run(
                "marketplace", "install", _COORDINATE, "--profile", "claude", "--yes"
            )
            self.assertEqual(installed, 0)

            code, payload = env.run("marketplace", "status", "--profile", "claude")

            self.assertEqual(code, 0, payload)
            self.assertEqual([item["status"] for item in payload["items"]], ["current"])
            self.assertTrue(
                payload["items"][0]["key"].startswith(_COORDINATE),
                payload["items"][0]["key"],
            )

    def test_status_after_an_uninstall_names_nothing(self) -> None:
        """Without this the test above would pass over a `status` that always says "current"."""

        with _environment() as env:
            env.run("marketplace", "install", _COORDINATE, "--profile", "claude", "--yes")
            env.run("marketplace", "uninstall", _COORDINATE, "--profile", "claude", "--yes")

            code, payload = env.run("marketplace", "status", "--profile", "claude")

            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["items"], [])

    def test_status_on_a_machine_that_installed_nothing_is_empty_rather_than_a_failure(
        self,
    ) -> None:
        with _environment() as env:
            code, payload = env.run("marketplace", "status", "--profile", "claude")

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["items"], [])


class MachineOutputTest(unittest.TestCase):
    """What an agent reading only `--json` is entitled to find."""

    def test_every_seam_answers_in_the_same_envelope(self) -> None:
        with _environment() as env:
            env.run("marketplace", "install", _COORDINATE, "--profile", "claude", "--yes")
            payloads = {
                "install": env.run(
                    "marketplace", "install", _COORDINATE, "--profile", "claude", "--force", "--yes"
                )[1],
                "update": env.run("marketplace", "update", "--profile", "claude", "--yes")[1],
                "status": env.run("marketplace", "status", "--profile", "claude")[1],
                "uninstall": env.run(
                    "marketplace", "uninstall", _COORDINATE, "--profile", "claude", "--yes"
                )[1],
            }

        for action, payload in payloads.items():
            with self.subTest(action=action):
                self.assertLessEqual(_ENVELOPE, set(payload), payload)
                self.assertEqual(payload["operation"], f"marketplace.{action}")
                self.assertTrue(payload["ok"], payload)
                self.assertTrue(payload["finalized"], payload)

    def test_a_finalized_action_reports_every_artifact_it_touched(self) -> None:
        """One confirmation, one item per artifact: an agent counts effects from this list."""

        with _environment() as env:
            code, payload = env.run(
                "marketplace", "install", _COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, payload)
            self.assertEqual(len(payload["items"]), 1, payload)
            item = payload["items"][0]
            self.assertLessEqual({"key", "status", "detail"}, set(item), item)
            self.assertTrue(item["key"].startswith(_COORDINATE), item)

    def test_a_review_names_the_artifacts_it_would_install(self) -> None:
        """The review body, not merely its digest: a digest nobody can read is not a review."""

        with _environment() as env:
            code, payload = env.run("marketplace", "install", _COORDINATE, "--profile", "claude")

            self.assertEqual(code, 0, payload)
            self.assertIn("review", payload)
            keys = [item["key"] for item in payload["review"]["items"]]
            self.assertEqual(len(keys), 1, payload["review"])
            self.assertTrue(keys[0].startswith(_COORDINATE), keys)

    def test_a_refusal_is_reported_in_the_envelope_rather_than_as_a_crash(self) -> None:
        with _environment() as env:
            code, payload = env.run(
                "marketplace", "install", "reference/skill/nothing-here", "--profile", "claude"
            )

            self.assertNotEqual(code, 0)
            self.assertLessEqual({"schema_version", "ok", "operation"}, set(payload), payload)
            self.assertFalse(payload["ok"])
            self.assertTrue(payload["diagnostics"], payload)


class OnePlanTwoRenderingsTest(unittest.TestCase):
    """`--json` selects a rendering; it never selects a different plan."""

    def test_the_text_review_and_the_json_review_carry_one_digest(self) -> None:
        with _environment() as env:
            _, payload = env.run("marketplace", "install", _COORDINATE, "--profile", "claude")
            code, text = env.run_text("marketplace", "install", _COORDINATE, "--profile", "claude")

            self.assertEqual(code, 0, text)
            self.assertIn(payload["review_digest"], text)

    def test_neither_rendering_finalizes_without_yes(self) -> None:
        with _environment() as env:
            env.run("marketplace", "install", _COORDINATE, "--profile", "claude")
            env.run_text("marketplace", "install", _COORDINATE, "--profile", "claude")

            self.assertEqual(list(env.project.iterdir()), [], "a review must write nothing")


class FailClosedReviewTest(unittest.TestCase):
    """A plan nobody authorized is a plan that did not run."""

    def test_a_review_is_not_finalized_and_leaves_no_installation_record(self) -> None:
        with _environment() as env:
            code, payload = env.run("marketplace", "install", _COORDINATE, "--profile", "claude")

            self.assertEqual(code, 0, payload)
            self.assertFalse(payload["finalized"], payload)
            self.assertFalse((env.project / ".agent-artifacts" / "manifest.json").exists())

    def test_the_review_carries_the_digest_a_later_invocation_must_match(self) -> None:
        """Consent travels between two commands as a digest, so it has to be in the payload."""

        with _environment() as env:
            _, review = env.run("marketplace", "install", _COORDINATE, "--profile", "claude")

            code, payload = env.run(
                "marketplace",
                "install",
                _COORDINATE,
                "--profile",
                "claude",
                "--expect",
                review["review_digest"],
                "--yes",
            )

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["finalized"], payload)
            state = json.loads((env.project / ".agent-artifacts" / "manifest.json").read_text())
            self.assertEqual(len(state["installations"]), 1, state)


if __name__ == "__main__":
    unittest.main()
