"""End to end: what a source withdrawing an artifact does, and what AART may claim about erasure.

Product Specification 165.10 says two things and they pull in opposite directions. The first is
about what normally happens: *"normal registry lifecycle uses deprecation, revocation and hiding
from new installs rather than physical deletion"*, with physical purge reserved for legal
requirements, malware or accidentally published secret material. The second is about what AART may
say when the exceptional case arrives: if a secret is found in canonical payload, AART *"must
clearly state that removing the current payload does not guarantee removal from Git history and that
repository-specific secret-removal and credential-rotation procedures are still required"*.

So this file measures a withdrawal from both sides. Upstream really deletes the artifact from a real
source and the source is really re-synchronized, which is the closest thing to a purge that exists
here -- AART offers no purge verb at all, which is the strongest possible form of "exceptional". The
question is then what survived and what stopped being offered. And separately, at the one place AART
tells anyone a credential is sitting in artifact content, whether the sentence it gives them is the
one 165.10 requires.

The withdrawal has to be coherent to be measured. Deleting the artifact alone leaves the fixture's
Collection referencing something that is gone, and the compiler refuses that graph -- correctly, and
before any of these questions is reached. Emptying the Collection is refused too, for its own
reason. So the Collection is re-pointed at the artifact that remains, which is what a maintainer
withdrawing one artifact would actually publish.
"""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from tests.credential_fixtures import access_token, secret_object
from tests.marketplace_lifecycle_e2e_test import _COORDINATE
from tests.security_baseline_test import _fixture, _scan
from tests.source_sync_command_e2e_test import (
    _environment_over_a_writable_source,
    _source_json,
)

#: The one artifact the fixture's Collection may still point at once the Skill is gone.
_REMAINING = {
    "type": "memory",
    "name": "house",
    "version": {"min_inclusive": "1.0.0", "max_exclusive": "2.0.0"},
}


def _withdraw(location: Path) -> None:
    """Publish the revision a maintainer would: the artifact gone, and nothing dangling."""

    shutil.rmtree(location / "artifacts" / "skill" / "code-review")
    collection = location / "collections" / "essentials.json"
    value = json.loads(collection.read_text(encoding="utf-8"))
    value["artifacts"] = [_REMAINING]
    collection.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _placed(env) -> list[str]:
    return sorted(
        str(path.relative_to(env.project)) for path in env.project.rglob("*") if path.is_file()
    )


class WithdrawnArtifactE2ETest(unittest.TestCase):
    def _withdrawn(self, env, location: Path) -> list[str]:
        """Install, then have upstream withdraw the artifact and re-synchronize. Returns files."""

        code, payload = env.run(
            "marketplace", "install", _COORDINATE, "--profile", "claude", "--yes"
        )
        self.assertEqual(code, 0, payload)
        before = _placed(env)
        _withdraw(location)
        synced, report = _source_json(env, "source", "sync")
        self.assertEqual(synced, 0, report)
        self.assertEqual([item["disposition"] for item in report["sources"]], ["published"])
        return before

    def test_a_withdrawn_artifact_stops_being_offered(self) -> None:
        with _environment_over_a_writable_source() as (env, location):
            self._withdrawn(env, location)

            code, payload = _source_json(env, "marketplace", "list")

            self.assertEqual(code, 0, payload)
            offered = [item["coordinate"] for item in payload["artifacts"]]
            self.assertNotIn(_COORDINATE + "@1.0.0", offered)
            # The source is still there and still serving; only that one row is gone.
            self.assertTrue(offered, payload)

    def test_installing_a_withdrawn_artifact_is_refused_with_a_way_to_look(self) -> None:
        with _environment_over_a_writable_source() as (env, location):
            self._withdrawn(env, location)

            code, payload = env.run(
                "marketplace", "install", _COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertNotEqual(code, 0)
            diagnostic = payload["diagnostics"][0]
            self.assertEqual(diagnostic["code"], "artifact-not-found")
            self.assertTrue(diagnostic["remediation"], diagnostic)

    def test_what_is_already_installed_is_not_deleted_with_it(self) -> None:
        """165.10's whole point: withdrawal hides from new installs, it does not reach a machine.

        A registry that could uninstall by publishing would be a registry that can reach into
        somebody's project without a plan, which is the boundary INV-210 draws.
        """

        with _environment_over_a_writable_source() as (env, location):
            before = self._withdrawn(env, location)

            self.assertEqual(_placed(env), before)
            code, payload = env.run("marketplace", "status", "--profile", "claude")
            self.assertEqual(code, 0, payload)
            item = payload["items"][0]
            # Its own word, and an honest one: the artifact is not broken and it is not current.
            self.assertEqual(item["status"], "removed-upstream")
            self.assertNotIn(item["status"], {"current", "broken", "source-unavailable"})

    def test_the_payload_bytes_stay_in_the_object_store(self) -> None:
        """Nothing physically deletes content, which is what keeps the local install whole.

        The store is content-addressed and shared, so deleting on withdrawal would take bytes away
        from whatever else references them -- and from the installation the previous test just
        showed is still standing.
        """

        with _environment_over_a_writable_source() as (env, location):
            self._withdrawn(env, location)

            objects = Path(env.paths.data_root, "objects")
            self.assertTrue(
                any(path.name == "SKILL.md" for path in objects.rglob("*") if path.is_file()),
                sorted(str(path) for path in objects.rglob("*")),
            )

    def test_an_operator_can_still_remove_what_upstream_withdrew(self) -> None:
        """The other half of not deleting: not stranding, either.

        An artifact that can never be uninstalled because its source stopped offering it would make
        withdrawal a way to pin something on a machine permanently.
        """

        with _environment_over_a_writable_source() as (env, location):
            self._withdrawn(env, location)

            code, payload = env.run(
                "marketplace", "uninstall", _COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, payload)
            self.assertNotIn(".claude/skills/code-review/SKILL.md", _placed(env))


class ErasureClaimTest(unittest.TestCase):
    """165.10's second statement, at the one place AART makes the finding it applies to.

    `embedded-credential` is the only rule that tells anyone a credential is sitting in artifact
    content, so it is the only place the required statement can be attached to. The assertion runs
    over a real scan rather than over the rule table, because the rule table is not what anybody
    reads: the finding on an assessment is, and `marketplace` renders its remediation verbatim.
    """

    def _remediation(self) -> str:
        payload = secret_object("api_token", access_token(), trailing="}")
        candidate, indexed, _ = _fixture(
            kind="mcp",
            files=(("payload/mcp.json", payload, False),),
            effects=("merge-json",),
        )
        assessment = _scan(candidate, indexed)
        findings = [item for item in assessment.findings if item.rule_id == "embedded-credential"]
        self.assertEqual(len(findings), 1, assessment.findings)
        return findings[0].remediation

    def test_a_credential_found_in_payload_says_removing_it_is_not_erasing_it(self) -> None:
        """The sentence an operator gets is the whole invariant.

        It said "remove the value, rotate it if real" -- which names rotation, and by saying
        "remove" with no caveat implies that removing is what fixes it. For content published from
        a Git-backed source that is false in the way that costs the most: the payload stops being
        current, the object stays reachable in history, and the person who read that line believes
        they are finished.
        """

        remediation = self._remediation().lower()

        self.assertIn("git history", remediation)
        # "does not guarantee" is the load-bearing half. A removal that merely *might* have been
        # enough is not something anyone should stop working on, and 165.10 asks for that word.
        self.assertIn("does not guarantee", remediation)

    def test_it_still_asks_for_the_two_things_that_do_finish_the_job(self) -> None:
        """The non-guarantee is only useful next to what to do instead.

        Rotation is what actually invalidates a leaked value, and history rewriting is
        repository-specific -- AART cannot do either, which is exactly why it has to name them.
        """

        remediation = self._remediation().lower()

        self.assertIn("rotat", remediation)
        self.assertIn("repository", remediation)

    def test_the_finding_does_not_echo_the_value_it_is_reporting(self) -> None:
        """A remediation that quoted the secret would republish it into every log that renders it.

        Held here as well as at the scanner because this is the finding whose whole subject is a
        credential: if any message were going to carry one, it is this one.
        """

        secret = access_token()

        self.assertNotIn(secret, self._remediation())


if __name__ == "__main__":  # pragma: no cover - unittest entry point
    unittest.main()
