"""End to end: an installation the policy in force would no longer allow, and how it is told.

Product Specification 165.21 says health includes effective policy compliance, and that an artifact
previously allowed may later become non-compliant -- and that the drift produces an explicit
remediation decision rather than a silent mutation of installed state. 165.23 says development
installations are clearly marked and that their nature keeps being surfaced afterwards.

Both are answered by the same fact about one installation, which is why they are measured together:
what a machine's policy says about the trust an artifact is installed at. `aart marketplace install`
already refuses a user-scope install below `minimum_trust_for_user_scope`; the question this file
asks is what happens to the one that got in before the rule existed, and whether anyone is ever told
that its source was a mutable local directory rather than a reviewed registry.

The policy is an administrator's file at a machine path -- `/Library/Application Support/...` or
`/etc/...` -- so it is injected here through the one override the resolver already takes, rather
than by writing outside the temporary machine.
"""

from __future__ import annotations

import json
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from agent_artifacts.configuration.paths import PathOverrides, resolve_config_paths
from tests.marketplace_lifecycle_e2e_test import _COORDINATE
from tests.source_sync_command_e2e_test import (
    _environment_over_a_writable_source,
    _source_json,
)
from tests.withdrawal_and_purge_e2e_test import _withdraw

_PERMISSIVE: dict[str, object] = {"schema_version": 1}
_STRICT: dict[str, object] = {
    "schema_version": 1,
    "minimum_trust_for_user_scope": "registry-reviewed",
}
_INSTALL = (
    "marketplace",
    "install",
    _COORDINATE,
    "--profile",
    "claude",
    "--scope",
    "user",
    "--yes",
)
_STATUS = ("marketplace", "status", "--scope", "user", "--profile", "claude")


@contextmanager
def _machine_policy(path: Path):
    """Point every configuration read at one policy file, the way an administrator's file is one."""

    real = resolve_config_paths

    def patched(platform, **kwargs):
        kwargs["overrides"] = PathOverrides(policy_file=str(path))
        return real(platform, **kwargs)

    with (
        mock.patch("agent_artifacts.commands._configured_runtime.resolve_config_paths", patched),
        mock.patch("agent_artifacts.consumer.runtime.resolve_config_paths", patched),
    ):
        yield


def _write(path: Path, policy: dict[str, object]) -> None:
    path.write_text(json.dumps(policy), encoding="utf-8")


def _item(payload: dict) -> dict:
    assert len(payload["items"]) == 1, payload
    return payload["items"][0]


class PolicyDriftE2ETest(unittest.TestCase):
    @contextmanager
    def _installed_before_the_rule(self):
        """One user-scope installation from a local source, made while the policy allowed it."""

        with _environment_over_a_writable_source() as (env, location):
            policy = Path(env.root) / "policy.json"
            _write(policy, _PERMISSIVE)
            with _machine_policy(policy):
                code, payload = env.run(*_INSTALL)
            self.assertEqual(code, 0, payload)
            yield env, location, policy

    def test_the_installation_is_not_mutated_by_a_policy_that_would_now_refuse_it(self) -> None:
        """165.21's second sentence: drift is a decision to make, never a change already made."""

        with self._installed_before_the_rule() as (env, _location, policy):
            placed = sorted(str(path) for path in Path(env.home).rglob("*") if path.is_file())
            _write(policy, _STRICT)

            with _machine_policy(policy):
                code, payload = env.run(*_STATUS)

            self.assertEqual(code, 0, payload)
            self.assertEqual(
                sorted(str(path) for path in Path(env.home).rglob("*") if path.is_file()), placed
            )

    def test_the_gate_that_let_it_in_would_refuse_it_now(self) -> None:
        """The premise the rest of the file rests on, asserted rather than assumed."""

        with self._installed_before_the_rule() as (env, _location, policy):
            _write(policy, _STRICT)

            with _machine_policy(policy):
                code, payload = env.run(*_INSTALL)

            self.assertNotEqual(code, 0)
            self.assertEqual(payload["diagnostics"][0]["code"], "install-policy-denied")

    def test_status_says_the_installation_no_longer_complies(self) -> None:
        """The invariant itself. An artifact that would be refused today, reported as fine, is the
        one answer that leaves an operator with nothing to act on."""

        with self._installed_before_the_rule() as (env, _location, policy):
            _write(policy, _STRICT)

            with _machine_policy(policy):
                code, payload = env.run(*_STATUS)

            self.assertEqual(code, 0, payload)
            self.assertEqual(_item(payload)["policy_status"], "non-compliant")

    def test_it_says_which_requirement_is_unmet(self) -> None:
        """ "No longer complies" without the reason is a dead end; 165.21 renders a Reason."""

        with self._installed_before_the_rule() as (env, _location, policy):
            _write(policy, _STRICT)

            with _machine_policy(policy):
                code, payload = env.run(*_STATUS)

            detail = _item(payload)["policy_detail"]
            self.assertIn("registry-reviewed", detail)
            self.assertIn("local", detail)

    def test_the_same_installation_complies_while_the_policy_allows_it(self) -> None:
        """The flag is about the policy in force, not about the artifact.

        Without this, a report that always said "non-compliant" would pass every other test here.
        """

        with self._installed_before_the_rule() as (env, _location, policy):
            with _machine_policy(policy):
                code, payload = env.run(*_STATUS)

            self.assertEqual(code, 0, payload)
            self.assertEqual(_item(payload)["policy_status"], "compliant")

    def test_a_damaged_installation_still_reports_where_its_content_came_from(self) -> None:
        """The case D-136 exists for: one slot, two things to say.

        A payload edited under AART's feet owns the status -- that is local damage and it needs
        fixing. The policy question is about the artifact's *origin* and is answered the same either
        way, so an operator deciding whether to repair or remove needs both halves at once. Found by
        `make mutants`: dropping the standing on exactly this branch killed no test.
        """

        with self._installed_before_the_rule() as (env, _location, policy):
            placed = next(
                path for path in Path(env.home).rglob("SKILL.md") if ".claude" in path.parts
            )
            placed.write_text("# edited by hand\n", encoding="utf-8")
            _write(policy, _STRICT)

            with _machine_policy(policy):
                code, payload = env.run(*_STATUS)

            self.assertEqual(code, 0, payload)
            item = _item(payload)
            self.assertNotEqual(item["status"], "current")
            self.assertEqual(item["policy_status"], "non-compliant")
            self.assertEqual(item["trust"], "local")

    def test_the_human_rendering_carries_the_warning_too(self) -> None:
        """An operator who did not ask for JSON is the one who most needs to be told."""

        with self._installed_before_the_rule() as (env, _location, policy):
            _write(policy, _STRICT)

            with _machine_policy(policy):
                code, text = env.run_text(*_STATUS)

            self.assertEqual(code, 0, text)
            self.assertIn("policy", text.lower())
            self.assertIn("registry-reviewed", text)


class DevelopmentInstallVisibilityTest(unittest.TestCase):
    """165.23: a development install stays distinguishable from a reviewed one, afterwards."""

    def test_status_names_the_trust_the_artifact_is_installed_at(self) -> None:
        """A local source is a mutable directory on somebody's disk -- the development case.

        `marketplace list` has said `trust` since the marketplace existed. What is *installed* said
        only `current`, so the one place an operator looks to see what a project is running could
        not tell a reviewed registry artifact from a working tree.
        """

        with _environment_over_a_writable_source() as (env, _location):
            policy = Path(env.root) / "policy.json"
            _write(policy, _PERMISSIVE)
            with _machine_policy(policy):
                code, payload = env.run(*_INSTALL)
                self.assertEqual(code, 0, payload)
                status_code, status = env.run(*_STATUS)

            self.assertEqual(status_code, 0, status)
            self.assertEqual(_item(status)["trust"], "local")

    def test_a_trust_that_cannot_be_measured_is_not_reported_as_compliant(self) -> None:
        """When upstream withdraws the artifact there is no current trust to judge.

        Reporting that as compliant would be asserting a measurement that was never taken -- the
        same reason `InstalledHealth.UNKNOWN` exists rather than defaulting to ready.
        """

        with _environment_over_a_writable_source() as (env, location):
            policy = Path(env.root) / "policy.json"
            _write(policy, _PERMISSIVE)
            with _machine_policy(policy):
                code, payload = env.run(*_INSTALL)
                self.assertEqual(code, 0, payload)
            _withdraw(location)
            synced, report = _source_json(env, "source", "sync")
            self.assertEqual(synced, 0, report)
            _write(policy, _STRICT)

            with _machine_policy(policy):
                status_code, status = env.run(*_STATUS)

            item = _item(status)
            self.assertEqual(item["status"], "removed-upstream")
            self.assertEqual(item["policy_status"], "not-evaluated")
            self.assertEqual(item["trust"], "")


if __name__ == "__main__":  # pragma: no cover - unittest entry point
    unittest.main()
