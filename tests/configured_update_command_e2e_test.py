"""The public update command converges an approved registry install onto a newer approved version.

Update is not install-with-a-different-word. Three things separate them, and each is asserted here
rather than assumed. It acts on something already installed, so an artifact this seam has no record
of is left to the characterized path instead of being installed under the name `update`. It is a
transition, so the plan carries the version being left as well as the one being taken -- which is
what lets the review state what changes, and what makes a request to move backwards a downgrade
somebody has to ask for by name. And it converges: `artifact_root` is version-independent, so the
newer version replaces the older one in place rather than being installed beside it.

INV-188 is the reason the no-op case is a test rather than a footnote. A registry that has synced
past the installed version has not updated anything, and running `update` when the approved version
is the one already installed must report exactly that and touch nothing.
"""

from __future__ import annotations

import json
import pathlib
import unittest

from tests.configured_install_command_e2e_test import COORDINATE, _environment
from tests.placed_installation_e2e_test import (
    SKILL_BODY,
    STYLE_BODY,
    as_delivered,
)

#: The same Skill as the installed fixture, one minor version further on. Only the version and the
#: body differ, so what an update has to converge is the delivered content and the recorded version
#: -- not a different artifact that happens to share a name.
UPDATED_SKILL_BODY = "# Code review\n\nRead reference/style.md, then comment on intent.\n"


def _authored(
    version: str, body: str, harnesses: tuple[str, ...] = ("claude",)
) -> tuple[tuple[str, str], ...]:
    manifest = {
        "schema": "aart-cli.dev/skill/v1",
        "artifact": {"name": "code-review", "kind": "skill", "version": version},
        "payload": {"include": ["SKILL.md", "reference/style.md"]},
        "compatibility": {"harnesses": list(harnesses)},
    }
    return (
        ("code-review/aart-cli.json", json.dumps(manifest)),
        ("code-review/SKILL.md", body),
        ("code-review/reference/style.md", STYLE_BODY),
    )


AUTHORED_SKILL_1_3_0 = _authored("1.3.0", UPDATED_SKILL_BODY)
AUTHORED_SKILL_1_1_0 = _authored("1.1.0", "# Code review\n\nAn older body.\n")

#: The same two versions, declared for two harnesses, because that is what an update of more than
#: one installation needs a package to allow (§169.3).
TWO_HARNESSES = ("claude", "opencode")
AUTHORED_FOR_TWO_1_2_0 = _authored("1.2.0", SKILL_BODY, TWO_HARNESSES)
AUTHORED_FOR_TWO_1_3_0 = _authored("1.3.0", UPDATED_SKILL_BODY, TWO_HARNESSES)


def _delivered(env) -> pathlib.Path:
    return env.project / ".claude/skills/code-review-company-project/SKILL.md"


class ConfiguredUpdateCommandTest(unittest.TestCase):
    def _installed(self, env) -> None:
        code, payload = env.run(
            "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
        )
        self.assertEqual(code, 0, payload)
        self.assertEqual(_delivered(env).read_text(encoding="utf-8"), as_delivered(SKILL_BODY))

    def test_update_before_any_canonical_install_leaves_the_selection_to_the_legacy_path(
        self,
    ) -> None:
        with _environment() as env:
            code, payload = env.run("marketplace", "update", COORDINATE, "--profile", "claude")

            # Whatever the characterized path answers, it must not have installed anything: an
            # artifact nobody installed cannot be updated, and quietly installing it under this
            # verb would make `update` a second install with no review of that fact.
            self.assertFalse(_delivered(env).exists(), payload)

    def test_update_at_the_approved_version_reports_current_and_changes_nothing(self) -> None:
        with _environment() as env:
            self._installed(env)
            before = _delivered(env).stat().st_mtime_ns

            code, payload = env.run(
                "marketplace", "update", COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["operation"], "marketplace.update")
            self.assertEqual(len(payload["items"]), 1)
            self.assertEqual(payload["items"][0]["key"], "company/skill/code-review@1.2.0")
            self.assertEqual(payload["items"][0]["status"], "current")
            self.assertEqual(_delivered(env).read_text(encoding="utf-8"), as_delivered(SKILL_BODY))
            self.assertEqual(_delivered(env).stat().st_mtime_ns, before)

    def test_review_names_the_newer_approved_version_and_writes_nothing(self) -> None:
        with _environment() as env:
            self._installed(env)
            env.publish(AUTHORED_SKILL_1_3_0)

            code, payload = env.run("marketplace", "update", COORDINATE, "--profile", "claude")

            self.assertEqual(code, 0, payload)
            self.assertFalse(payload["finalized"])
            self.assertEqual(payload["review_digest"], payload["review"]["review_digest"])
            self.assertEqual(
                payload["review"]["items"][0]["key"], "company/skill/code-review@1.3.0"
            )
            self.assertEqual(_delivered(env).read_text(encoding="utf-8"), as_delivered(SKILL_BODY))

    def test_confirmed_update_converges_the_delivery_in_place_and_records_the_new_version(
        self,
    ) -> None:
        with _environment() as env:
            self._installed(env)
            env.publish(AUTHORED_SKILL_1_3_0)
            _, review = env.run("marketplace", "update", COORDINATE, "--profile", "claude")

            code, payload = env.run(
                "marketplace",
                "update",
                COORDINATE,
                "--profile",
                "claude",
                "--expect",
                review["review_digest"],
                "--yes",
            )

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["finalized"])
            self.assertEqual(payload["items"][0]["key"], "company/skill/code-review@1.3.0")
            self.assertEqual(
                _delivered(env).read_text(encoding="utf-8"), as_delivered(UPDATED_SKILL_BODY)
            )

            status_code, status = env.run("marketplace", "status", "--profile", "claude")
            self.assertEqual(status_code, 0, status)
            self.assertEqual(
                [item["key"] for item in status["items"]], ["company/skill/code-review@1.3.0"]
            )

    def test_a_stale_update_review_is_refused_before_the_delivery_is_touched(self) -> None:
        with _environment() as env:
            self._installed(env)
            env.publish(AUTHORED_SKILL_1_3_0)

            code, payload = env.run(
                "marketplace",
                "update",
                COORDINATE,
                "--profile",
                "claude",
                "--expect",
                "sha256:" + "0" * 64,
                "--yes",
            )

            self.assertNotEqual(code, 0)
            self.assertFalse(payload["ok"])
            self.assertFalse(payload["finalized"])
            self.assertEqual(_delivered(env).read_text(encoding="utf-8"), as_delivered(SKILL_BODY))

    def test_an_approved_version_older_than_the_installed_one_is_refused_as_a_downgrade(
        self,
    ) -> None:
        with _environment() as env:
            self._installed(env)
            env.publish(AUTHORED_SKILL_1_1_0)

            code, payload = env.run(
                "marketplace", "update", COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertNotEqual(code, 0)
            self.assertFalse(payload["ok"])
            self.assertIn("downgrade", payload["diagnostics"][0]["message"])
            self.assertEqual(_delivered(env).read_text(encoding="utf-8"), as_delivered(SKILL_BODY))

    def test_both_installations_of_one_artifact_are_updated_and_neither_is_forgotten(self) -> None:
        """§169.3: two harnesses are two installations, so an update converges two of them.

        The whole operation used to be refused -- "an artifact was superseded twice" -- because the
        state being left was keyed by the artifact, and two installations of one artifact name it
        twice. The key is the installation; what proves it is that both trees move, since an update
        that forgot one would leave that harness on the old body while reporting success.
        """

        with _environment(authored=AUTHORED_FOR_TWO_1_2_0) as env:
            code, installed = env.run(
                "marketplace",
                "install",
                COORDINATE,
                "--profile",
                "claude",
                "--profile",
                "opencode",
                "--yes",
            )
            self.assertEqual(code, 0, installed)
            delivered = {
                harness: env.project / f".{harness}/skills/code-review-company-project/SKILL.md"
                for harness in TWO_HARNESSES
            }
            for harness, path in delivered.items():
                self.assertEqual(
                    path.read_text(encoding="utf-8"), as_delivered(SKILL_BODY), harness
                )
            env.publish(AUTHORED_FOR_TWO_1_3_0)

            code, payload = env.run(
                "marketplace",
                "update",
                COORDINATE,
                "--profile",
                "claude",
                "--profile",
                "opencode",
                "--yes",
            )

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["finalized"], payload)
            self.assertEqual(
                [item["key"] for item in payload["items"]],
                ["company/skill/code-review@1.3.0"] * 2,
            )
            for harness, path in delivered.items():
                self.assertEqual(
                    path.read_text(encoding="utf-8"), as_delivered(UPDATED_SKILL_BODY), harness
                )

    def test_update_without_a_coordinate_converges_everything_canonically_installed(self) -> None:
        with _environment() as env:
            self._installed(env)
            env.publish(AUTHORED_SKILL_1_3_0)

            code, payload = env.run("marketplace", "update", "--profile", "claude", "--yes")

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["finalized"])
            self.assertEqual(payload["items"][0]["key"], "company/skill/code-review@1.3.0")
            self.assertEqual(
                _delivered(env).read_text(encoding="utf-8"), as_delivered(UPDATED_SKILL_BODY)
            )


if __name__ == "__main__":
    unittest.main()
