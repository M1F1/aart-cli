"""D-457: a kind the harness only reads is delivered from the canonical object, not a second copy.

The owner saw every Skill twice in a project's `.tabnine/`: once in `agent/skills/<name>`, which the
harness reads, and once in `aart-cli/skill/<registry>/<name>/payload`, which nothing read. These run
the real commands and hold that only the delivered copy is written beside the harness, that a repair
re-delivers from the object in the application home, and that uninstalling leaves that object to
the store.
"""

from __future__ import annotations

import json
import pathlib
import unittest

from tests.configured_install_command_e2e_test import COORDINATE, _environment
from tests.configured_repair_action_e2e_test import _delete_delivery
from tests.configured_uninstall_command_e2e_test import _delivered

INSTALLED_COORDINATE = "company/skill/code-review@1.2.0"


def _receipts(env) -> list[dict]:
    root = pathlib.Path(env.xdg["AART_CLI_HOME"]) / "state" / "installations"
    return [json.loads(path.read_text()) for path in sorted(root.rglob("*.json"))]


def _placed(env) -> dict:
    found = [
        item.get("receipt", item)
        for item in _receipts(env)
        if "deliveries" in item.get("receipt", item)
    ]
    assert len(found) == 1, found
    return found[0]


class SharedPayloadTest(unittest.TestCase):
    def _installed(self, env) -> None:
        code, payload = env.run("consume", "install", COORDINATE, "--profile", "claude", "--yes")
        self.assertEqual(code, 0, payload)
        self.assertTrue(_delivered(env).exists())

    def test_a_skill_leaves_no_private_tree_beside_the_harness(self) -> None:
        with _environment() as env:
            self._installed(env)

            self.assertFalse((env.project / ".claude" / "aart-cli").exists())
            receipt = _placed(env)
            objects = pathlib.Path(env.xdg["AART_CLI_HOME"]) / "objects"
            self.assertTrue(pathlib.Path(receipt["payload"]).is_relative_to(objects), receipt)
            self.assertTrue(pathlib.Path(receipt["payload"]).is_dir())
            for delivery in receipt["deliveries"]:
                self.assertTrue(delivery["source"].startswith(receipt["payload"]), delivery)

            code, review = env.run("doctor", "--repair", INSTALLED_COORDINATE)
            self.assertEqual(code, 0, review)
            self.assertEqual(
                (review["review"]["drift"], review["review"]["steps"]),
                ([], []),
                "a healthy install reads as drift",
            )

    def test_doctor_repairs_a_deleted_skill_from_the_canonical_object(self) -> None:
        with _environment() as env:
            self._installed(env)
            _delete_delivery(env)
            env.disable_source()

            code, review = env.run("doctor", "--repair", INSTALLED_COORDINATE)
            self.assertEqual(code, 0, review)
            code, payload = env.run(
                "doctor",
                "--repair",
                INSTALLED_COORDINATE,
                "--yes",
                "--expect",
                review["review_digest"],
            )

            self.assertEqual(code, 0, payload)
            self.assertTrue(_delivered(env).exists())
            self.assertFalse((env.project / ".claude" / "aart-cli").exists())

    def test_uninstall_withdraws_the_skill_and_leaves_the_object_to_the_store(self) -> None:
        with _environment() as env:
            self._installed(env)
            canonical = pathlib.Path(_placed(env)["payload"])

            code, payload = env.run(
                "consume", "uninstall", COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, payload)
            self.assertFalse(_delivered(env).exists())
            self.assertTrue(canonical.is_dir(), "uninstalling deleted the canonical object")


if __name__ == "__main__":
    unittest.main()
