"""INV-286: a Registry other people install from holds only versions from remote upstreams.

A maintainer tried artifacts out by promoting them from checkouts on their own machine, and those
versions record the checkout's absolute path as their origin. Nothing stopped them reaching the
Registry's default branch. The generated Registry CI now runs `registry audit
--for-default-branch`, which refuses every such version; a plain audit, which `publish` runs,
still lets a trial Registry work and says which versions came from a local checkout.
"""

from __future__ import annotations

import unittest

from aart_cli.cli_parser import build_parser
from aart_cli.domain.diagnostics import Severity
from aart_cli.domain.result import Ok
from aart_cli.protocol.capabilities import Capability
from aart_cli.protocol.semver import SemVer
from aart_cli.registry_commands.planning import audit_registry_workspace
from aart_cli.registry_commands.publication import REGISTRY_PUBLICATION_GATES
from aart_cli.registry_commands.templates import REGISTRY_CI_WORKFLOW
from aart_cli.registry_maintenance.model import adoption_record
from tests.registry_maintenance_fixtures import approved_registry_snapshot

CAPABILITIES = (
    Capability("artifact-manifest-v1"),
    Capability("lockfile-v1"),
    Capability("registry-entry-v1"),
)
MODES = ("self-contained", "pinned-reference")


def _origin_findings(snapshot, *, require: bool):
    audited = audit_registry_workspace(
        snapshot,
        executable_version=SemVer(1, 0, 0),
        available_capabilities=CAPABILITIES,
        for_default_branch=require,
    )
    assert isinstance(audited, Ok), audited
    findings = tuple(
        diagnostic
        for check in audited.value.checks
        for diagnostic in check.diagnostics
        if "local checkout" in diagnostic.message
    )
    return audited.value.passed, findings


class RemoteOriginsTest(unittest.TestCase):
    def test_ci_refuses_every_version_promoted_from_a_local_checkout(self) -> None:
        for mode in MODES:
            with self.subTest(mode=mode):
                passed, findings = _origin_findings(
                    approved_registry_snapshot(local=True, mode=mode), require=True
                )

                self.assertFalse(passed)
                self.assertEqual(len(findings), 1, findings)
                self.assertIs(findings[0].severity, Severity.ERROR)
                self.assertIn("mcp/github-mcp@1.0.0", findings[0].message)
                self.assertIn("/home/author/servers", findings[0].message)
                self.assertIn("maintain upstream adopt", " ".join(findings[0].remediation))

    def test_a_trial_registry_still_passes_and_is_told(self) -> None:
        for mode in MODES:
            with self.subTest(mode=mode):
                passed, findings = _origin_findings(
                    approved_registry_snapshot(local=True, mode=mode), require=False
                )

                self.assertTrue(passed)
                self.assertEqual(len(findings), 1, findings)
                self.assertIs(findings[0].severity, Severity.WARNING)

    def test_versions_from_remote_upstreams_say_nothing_either_way(self) -> None:
        adopted = adoption_record("main", True)
        for require in (False, True):
            with self.subTest(require=require):
                passed, findings = _origin_findings(
                    approved_registry_snapshot(adoption=adopted), require=require
                )

                self.assertTrue(passed)
                self.assertEqual(findings, ())

    def test_the_generated_registry_ci_requires_remote_origins(self) -> None:
        audit = next(gate for gate in REGISTRY_PUBLICATION_GATES if gate.name == "audit")
        command = "aart-cli maintain registry audit --source . --for-default-branch"

        self.assertEqual(audit.commands, (command,))
        self.assertIn(f"run: {command}".encode(), REGISTRY_CI_WORKFLOW)
        parsed = build_parser().parse_args(command.split()[1:])
        self.assertTrue(parsed.for_default_branch)


if __name__ == "__main__":
    unittest.main()
