"""CP-03 contracts for the five canonical AART algebras."""

from __future__ import annotations

import dataclasses
import json
import unittest

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts.domain.artifacts import (
    ArtifactFormat,
    ArtifactKind,
    ArtifactPackage,
    Capability,
    Compatibility,
    Provenance,
    artifact_to_data,
)
from agent_artifacts.domain.effects import (
    ConfigureHarness,
    CopyTree,
    CreatePythonEnvironment,
    EffectCapabilities,
    ReplaceCredential,
    RiskClass,
    effect_to_data,
)
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    ObjectDigest,
    SourceAlias,
)
from agent_artifacts.domain.policies import EffectivePolicy, PolicyOverlay, compose_policy
from agent_artifacts.domain.remediations import (
    ConfigureCredential,
    InstallRuntime,
    remediation_to_data,
)
from agent_artifacts.domain.requirements import (
    CredentialRequirement,
    RequirementAssessment,
    RequirementId,
    RequirementState,
    RuntimeRequirement,
    requirement_to_data,
)
from agent_artifacts.domain.serialization import canonical_json_bytes


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _artifact(*capabilities: str) -> ArtifactPackage:
    return ArtifactPackage(
        coordinate=ArtifactCoordinate(
            SourceAlias("company"), ArtifactIdentity("mcp", "github"), "1.4.0"
        ),
        kind=ArtifactKind.MCP,
        format=ArtifactFormat("aart-mcp/v1"),
        protocol="mcp/2025-06-18",
        payload_digest=_digest("a"),
        provenance=Provenance(
            source="git.company/ai/mcp",
            revision="b" * 40,
            manifest_path="github/aart.yaml",
            input_digest=_digest("c"),
            compiler="aart-cli/0.0.1",
        ),
        compatibility=Compatibility(platforms=("darwin",), harnesses=("tabnine",), python=">=3.11"),
        capabilities=tuple(Capability(value) for value in capabilities),
    )


class ArtifactAlgebraTest(unittest.TestCase):
    def test_artifact_envelope_is_frozen_canonical_and_dimensionally_explicit(self) -> None:
        artifact = _artifact("network", "stdio", "network")

        self.assertEqual(tuple(item.value for item in artifact.capabilities), ("network", "stdio"))
        self.assertEqual(artifact.kind.value, "mcp")
        self.assertEqual(artifact.protocol, "mcp/2025-06-18")
        self.assertEqual(artifact_to_data(artifact)["format"], "aart-mcp/v1")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            artifact.protocol = None  # type: ignore[misc]

    def test_artifact_kind_must_agree_with_coordinate(self) -> None:
        artifact = _artifact()
        with self.assertRaises(ValueError):
            dataclasses.replace(artifact, kind=ArtifactKind.SKILL)


class RequirementAndRemediationAlgebraTest(unittest.TestCase):
    def test_requirements_describe_conditions_and_assessments_not_effects(self) -> None:
        credential = CredentialRequirement(
            RequirementId("github-token"), provider=None, required=True
        )
        runtime = RuntimeRequirement(RequirementId("python"), "python", ">=3.11")
        assessment = RequirementAssessment(credential, RequirementState.UNSATISFIED)

        self.assertEqual(requirement_to_data(credential)["kind"], "credential")
        self.assertEqual(requirement_to_data(runtime)["constraint"], ">=3.11")
        self.assertEqual(assessment.state, RequirementState.UNSATISFIED)
        self.assertNotIn("value", requirement_to_data(credential))

    def test_remediations_reference_requirements_without_performing_mutation(self) -> None:
        credential = ConfigureCredential(RequirementId("github-token"), "macos-keychain")
        runtime = InstallRuntime(RequirementId("python"), "python", ">=3.11")

        self.assertEqual(remediation_to_data(credential)["provider"], "macos-keychain")
        self.assertEqual(remediation_to_data(runtime)["kind"], "install-runtime")


class EffectAlgebraTest(unittest.TestCase):
    def test_effects_carry_explicit_risk_and_repair_capabilities(self) -> None:
        copy = CopyTree("payload", ".aart/mcp/github/payload")
        runtime = CreatePythonEnvironment(
            "github", ".aart/mcp/github/runtime/.venv", "/usr/bin/python3"
        )
        credential = ReplaceCredential("github-token", "macos-keychain")
        harness = ConfigureHarness("tabnine", "github", ".tabnine/agent/settings.json")

        self.assertEqual(copy.risk, RiskClass.LOCAL_MUTATION)
        self.assertTrue(runtime.capabilities.independently_repairable)
        self.assertEqual(credential.risk, RiskClass.CREDENTIAL_MUTATION)
        self.assertFalse(credential.capabilities.reversible)
        self.assertEqual(harness.risk, RiskClass.CONFIGURATION_MUTATION)
        self.assertNotIn("value", effect_to_data(credential))

    def test_invalid_capability_claim_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            EffectCapabilities(
                inspectable=False,
                idempotent=False,
                reversible=True,
                independently_repairable=True,
            )


class PolicyAlgebraTest(unittest.TestCase):
    def test_composition_narrows_allows_widens_denies_and_accumulates_checks(self) -> None:
        base = EffectivePolicy(
            allowed_registries=frozenset({"company", "community"}),
            allowed_runtimes=frozenset({"python", "oci"}),
            forbidden_effects=frozenset({"external-script"}),
            required_checks=frozenset({"schema"}),
            risk_ceiling=RiskClass.HIGH_RISK_EXECUTION,
        )
        overlay = PolicyOverlay(
            allowed_registries=frozenset({"company"}),
            allowed_runtimes=frozenset({"python"}),
            forbidden_effects=frozenset({"network-mutation"}),
            required_checks=frozenset({"security"}),
            risk_ceiling=RiskClass.CREDENTIAL_MUTATION,
        )

        effective = compose_policy(base, overlay)

        self.assertEqual(effective.allowed_registries, frozenset({"company"}))
        self.assertEqual(effective.allowed_runtimes, frozenset({"python"}))
        self.assertEqual(
            effective.forbidden_effects, frozenset({"external-script", "network-mutation"})
        )
        self.assertEqual(effective.required_checks, frozenset({"schema", "security"}))
        self.assertEqual(effective.risk_ceiling, RiskClass.CREDENTIAL_MUTATION)

    @given(
        base=st.sets(st.sampled_from(("company", "team", "community"))),
        overlay=st.sets(st.sampled_from(("company", "team", "community"))),
    )
    def test_allowed_registry_composition_is_monotonic(
        self, base: set[str], overlay: set[str]
    ) -> None:
        effective = compose_policy(
            EffectivePolicy(allowed_registries=frozenset(base)),
            PolicyOverlay(allowed_registries=frozenset(overlay)),
        )

        self.assertTrue(effective.allowed_registries <= frozenset(base))
        self.assertTrue(effective.allowed_registries <= frozenset(overlay))

    @given(
        first=st.sets(st.text(alphabet="abc-", min_size=1, max_size=12)),
        second=st.sets(st.text(alphabet="abc-", min_size=1, max_size=12)),
    )
    def test_forbidden_effect_composition_is_union(self, first: set[str], second: set[str]) -> None:
        effective = compose_policy(
            EffectivePolicy(forbidden_effects=frozenset(first)),
            PolicyOverlay(forbidden_effects=frozenset(second)),
        )
        self.assertEqual(effective.forbidden_effects, frozenset(first | second))


class CanonicalProjectionPropertyTest(unittest.TestCase):
    @given(st.lists(st.sampled_from(("stdio", "network", "filesystem")), max_size=20))
    def test_artifact_projection_is_deterministic_for_capability_order(
        self, capabilities: list[str]
    ) -> None:
        forward = artifact_to_data(_artifact(*capabilities))
        reverse = artifact_to_data(_artifact(*reversed(capabilities)))

        self.assertEqual(forward, reverse)
        encoded = canonical_json_bytes(forward)
        self.assertEqual(json.loads(encoded), forward)
        self.assertNotIn(b"secret_value", encoded)


if __name__ == "__main__":
    unittest.main()
