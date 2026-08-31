"""CP-07 immutable facts, assessment, remediation and canonical planning."""

from __future__ import annotations

import dataclasses
import json
import unittest

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts.application.installation_planning import (
    NO_ALLOWED_REMEDIATION,
    POLICY_VIOLATION,
    REQUIREMENT_CONFLICT,
    ArtifactInstallIntent,
    aggregate_requirements,
    allowed_remediations,
    assess_requirements,
    prepare_install_plan,
)
from agent_artifacts.domain.candidates import CandidateId
from agent_artifacts.domain.effects import (
    ConfigureHarness,
    CopyTree,
    CreatePythonEnvironment,
    RiskClass,
)
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    ObjectDigest,
    SourceAlias,
)
from agent_artifacts.domain.inspection import (
    EnvironmentFact,
    EnvironmentFacts,
    FactState,
    RemediationCapability,
    RemediationCapabilityKind,
    environment_facts_to_data,
)
from agent_artifacts.domain.plans import install_plan_to_data
from agent_artifacts.domain.policies import EffectivePolicy, PolicyOverlay, compose_policy
from agent_artifacts.domain.registry import (
    PromotionMode,
    PublicationStage,
    RegistryArtifactVersion,
)
from agent_artifacts.domain.remediations import ConfigureCredential, InstallRuntime
from agent_artifacts.domain.requirements import (
    CredentialRequirement,
    ExecutableRequirement,
    RequirementId,
    RequirementState,
    RuntimeRequirement,
)
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.domain.selection import (
    ArtifactRequest,
    ArtifactSelection,
    OwnershipKind,
    OwnershipReason,
    ResolvedArtifact,
    ResolvedSelection,
    VersionConstraint,
)


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _resolved(name: str, *, character: str) -> ResolvedArtifact:
    coordinate = ArtifactCoordinate(SourceAlias("company"), ArtifactIdentity("mcp", name), "1.0.0")
    version = RegistryArtifactVersion(
        coordinate,
        CandidateId(character * 64),
        _digest("a"),
        _digest(character),
        _digest(character),
        _digest(character),
        _digest("f"),
        PromotionMode.VENDORED,
        PublicationStage.PUBLISHED,
    )
    return ResolvedArtifact(
        version,
        (OwnershipReason(OwnershipKind.DIRECT, str(coordinate)),),
    )


def _selection(*artifacts: ResolvedArtifact) -> ResolvedSelection:
    intent = ArtifactSelection(
        tuple(
            ArtifactRequest(
                artifact.version.coordinate.artifact,
                VersionConstraint(artifact.version.coordinate.version or "*"),
                artifact.version.coordinate.source,
            )
            for artifact in artifacts
        )
    )
    return ResolvedSelection(intent, artifacts)


class EnvironmentFactTest(unittest.TestCase):
    def test_facts_are_frozen_canonical_and_contain_no_general_value_channel(self) -> None:
        python = EnvironmentFact(RequirementId("python"), FactState.AVAILABLE, "3.11.0")
        credential = EnvironmentFact(RequirementId("github-token"), FactState.UNAVAILABLE)
        provider = RemediationCapability(
            RemediationCapabilityKind.CREDENTIAL_PROVIDER,
            "macos-keychain",
        )

        facts = EnvironmentFacts("darwin", (python, credential), (provider,))
        encoded = json.dumps(environment_facts_to_data(facts), sort_keys=True)

        self.assertEqual(
            tuple(item.requirement.value for item in facts.facts),
            ("github-token", "python"),
        )
        self.assertNotIn("secret", encoded.lower())
        self.assertNotIn('"value"', encoded)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            facts.platform = "linux"  # type: ignore[misc]

    def test_fact_identity_cannot_be_ambiguous(self) -> None:
        with self.assertRaises(ValueError):
            EnvironmentFacts(
                "darwin",
                (
                    EnvironmentFact(RequirementId("python"), FactState.AVAILABLE, "3.11.0"),
                    EnvironmentFact(RequirementId("python"), FactState.UNKNOWN),
                ),
            )


class RequirementAssessmentTest(unittest.TestCase):
    def test_runtime_assessment_is_pure_and_three_state(self) -> None:
        requirements = (
            RuntimeRequirement(RequirementId("python"), "python", ">=3.11,<3.13"),
            ExecutableRequirement(RequirementId("git"), "git"),
            CredentialRequirement(RequirementId("github-token"), "macos-keychain"),
        )
        facts = EnvironmentFacts(
            "darwin",
            (
                EnvironmentFact(RequirementId("python"), FactState.AVAILABLE, "3.12.1"),
                EnvironmentFact(RequirementId("git"), FactState.UNAVAILABLE),
            ),
        )
        owner = ArtifactCoordinate(
            SourceAlias("company"), ArtifactIdentity("mcp", "github"), "1.0.0"
        )
        aggregated = aggregate_requirements(((owner, requirements),))
        assert isinstance(aggregated, Ok), aggregated

        assessed = assess_requirements(aggregated.value, facts)

        self.assertEqual(
            {item.requirement.requirement.id.value: item.state for item in assessed},
            {
                "git": RequirementState.UNSATISFIED,
                "github-token": RequirementState.UNKNOWN,
                "python": RequirementState.SATISFIED,
            },
        )
        python = next(
            item for item in assessed if item.requirement.requirement.id.value == "python"
        )
        self.assertIn("3.12.1", python.detail)

    def test_equivalent_bulk_requirements_deduplicate_and_retain_every_dependant(self) -> None:
        github = ArtifactCoordinate(
            SourceAlias("company"), ArtifactIdentity("mcp", "github"), "1.0.0"
        )
        jira = ArtifactCoordinate(SourceAlias("company"), ArtifactIdentity("mcp", "jira"), "1.0.0")
        python = RuntimeRequirement(RequirementId("python"), "python", ">=3.11")

        result = aggregate_requirements(((jira, (python,)), (github, (python,))))

        assert isinstance(result, Ok), result
        self.assertEqual(len(result.value), 1)
        self.assertEqual(result.value[0].owners, (github, jira))

    def test_conflicting_semantics_under_one_requirement_id_fail_explicitly(self) -> None:
        owner = ArtifactCoordinate(
            SourceAlias("company"), ArtifactIdentity("mcp", "github"), "1.0.0"
        )

        result = aggregate_requirements(
            (
                (owner, (RuntimeRequirement(RequirementId("python"), "python", ">=3.11"),)),
                (
                    owner,
                    (RuntimeRequirement(RequirementId("python"), "python", ">=3.12"),),
                ),
            )
        )

        assert isinstance(result, Err), result
        self.assertEqual(result.diagnostics[0].code, REQUIREMENT_CONFLICT)


class RemediationPolicyTest(unittest.TestCase):
    def test_choices_are_the_intersection_of_need_capability_policy_and_risk(self) -> None:
        owner = ArtifactCoordinate(
            SourceAlias("company"), ArtifactIdentity("mcp", "github"), "1.0.0"
        )
        credential = CredentialRequirement(RequirementId("github-token"))
        aggregated = aggregate_requirements(((owner, (credential,)),))
        assert isinstance(aggregated, Ok)
        facts = EnvironmentFacts(
            "darwin",
            (EnvironmentFact(credential.id, FactState.UNAVAILABLE),),
            (
                RemediationCapability(RemediationCapabilityKind.CREDENTIAL_PROVIDER, "environment"),
                RemediationCapability(
                    RemediationCapabilityKind.CREDENTIAL_PROVIDER, "macos-keychain"
                ),
            ),
        )
        assessments = assess_requirements(aggregated.value, facts)
        policy = EffectivePolicy(
            allowed_credential_providers=frozenset({"macos-keychain"}),
            risk_ceiling=RiskClass.CREDENTIAL_MUTATION,
        )

        options = allowed_remediations(assessments, facts, policy)

        self.assertEqual(len(options), 1)
        self.assertEqual(
            options[0].remediation,
            ConfigureCredential(RequirementId("github-token"), "macos-keychain"),
        )
        self.assertEqual(options[0].risk, RiskClass.CREDENTIAL_MUTATION)

    def test_restrictive_overlay_cannot_reenable_interaction_or_raise_risk(self) -> None:
        parent = EffectivePolicy(
            interactive_remediation=False,
            risk_ceiling=RiskClass.LOCAL_MUTATION,
        )

        effective = compose_policy(
            parent,
            PolicyOverlay(
                interactive_remediation=True,
                risk_ceiling=RiskClass.HIGH_RISK_EXECUTION,
            ),
        )

        self.assertFalse(effective.interactive_remediation)
        self.assertEqual(effective.risk_ceiling, RiskClass.LOCAL_MUTATION)


class CanonicalInstallPlanningTest(unittest.TestCase):
    def test_one_bulk_plan_deduplicates_effects_and_retains_all_owners(self) -> None:
        github = _resolved("github", character="1")
        jira = _resolved("jira", character="2")
        selection = _selection(jira, github)
        python = RuntimeRequirement(RequirementId("python"), "python", ">=3.11")
        shared_effect = CopyTree("payload", ".aart/shared")
        intents = (
            ArtifactInstallIntent(jira, (python,), (shared_effect,), runtime="python"),
            ArtifactInstallIntent(github, (python,), (shared_effect,), runtime="python"),
        )
        facts = EnvironmentFacts(
            "darwin",
            (EnvironmentFact(python.id, FactState.AVAILABLE, "3.12.0"),),
        )

        result = prepare_install_plan(
            selection,
            intents,
            facts,
            EffectivePolicy(
                allowed_registries=frozenset({"company"}),
                allowed_runtimes=frozenset({"python"}),
            ),
        )

        assert isinstance(result, Ok), result
        plan = result.value
        self.assertEqual(len(plan.requirements), 1)
        self.assertEqual(len(plan.mutation.effects), 1)
        self.assertEqual(
            plan.mutation.effects[0].owners,
            (github.version.coordinate, jira.version.coordinate),
        )
        self.assertEqual(plan.mutation.risks, (RiskClass.LOCAL_MUTATION,))
        self.assertEqual(plan.selection, selection)
        self.assertNotIn("secret", json.dumps(install_plan_to_data(plan)).lower())

    def test_unsatisfied_requirement_needs_one_explicit_allowed_remediation(self) -> None:
        github = _resolved("github", character="1")
        selection = _selection(github)
        python = RuntimeRequirement(RequirementId("python"), "python", ">=3.11")
        intent = ArtifactInstallIntent(github, (python,), (), runtime="python")
        facts = EnvironmentFacts(
            "darwin",
            (EnvironmentFact(python.id, FactState.UNAVAILABLE),),
            (
                RemediationCapability(
                    RemediationCapabilityKind.RUNTIME_INSTALLER,
                    "python",
                ),
            ),
        )
        policy = EffectivePolicy(allowed_runtimes=frozenset({"python"}))

        unresolved = prepare_install_plan(selection, (intent,), facts, policy)
        remediated = prepare_install_plan(
            selection,
            (intent,),
            facts,
            policy,
            selected_remediations=(InstallRuntime(python.id, "python", ">=3.11"),),
        )

        assert isinstance(unresolved, Err), unresolved
        self.assertEqual(unresolved.diagnostics[0].code, NO_ALLOWED_REMEDIATION)
        assert isinstance(remediated, Ok), remediated
        self.assertEqual(remediated.value.remediations[0].risk, RiskClass.EXECUTABLE_INSTALL)

    def test_policy_rejects_forbidden_registry_runtime_transport_and_effect_before_plan(
        self,
    ) -> None:
        github = _resolved("github", character="1")
        selection = _selection(github)
        intent = ArtifactInstallIntent(
            github,
            (),
            (ConfigureHarness("codex", "github", ".codex/config.json"),),
            runtime="python",
            transport="stdio",
        )
        cases = (
            EffectivePolicy(allowed_registries=frozenset({"other"})),
            EffectivePolicy(allowed_runtimes=frozenset({"oci"})),
            EffectivePolicy(allowed_transports=frozenset({"http"})),
            EffectivePolicy(forbidden_effects=frozenset({"configure-harness"})),
            EffectivePolicy(risk_ceiling=RiskClass.READ_ONLY),
        )

        for policy in cases:
            with self.subTest(policy=policy):
                result = prepare_install_plan(
                    selection,
                    (intent,),
                    EnvironmentFacts("darwin"),
                    policy,
                )
                assert isinstance(result, Err), result
                self.assertEqual(result.diagnostics[0].code, POLICY_VIOLATION)

    def test_noninteractive_policy_fails_without_offering_a_wizard(self) -> None:
        github = _resolved("github", character="1")
        selection = _selection(github)
        credential = CredentialRequirement(RequirementId("github-token"))
        intent = ArtifactInstallIntent(github, (credential,), ())
        facts = EnvironmentFacts(
            "darwin",
            (EnvironmentFact(credential.id, FactState.UNAVAILABLE),),
            (
                RemediationCapability(
                    RemediationCapabilityKind.CREDENTIAL_PROVIDER,
                    "macos-keychain",
                ),
            ),
        )

        result = prepare_install_plan(
            selection,
            (intent,),
            facts,
            EffectivePolicy(interactive_remediation=False),
        )

        assert isinstance(result, Err), result
        self.assertEqual(result.diagnostics[0].code, NO_ALLOWED_REMEDIATION)
        self.assertIn("non-interactive", result.diagnostics[0].message)

    @given(st.permutations(("github", "jira")))
    def test_intent_order_cannot_change_review_identity(self, names: tuple[str, ...]) -> None:
        artifacts = {
            "github": _resolved("github", character="1"),
            "jira": _resolved("jira", character="2"),
        }
        selection = _selection(*artifacts.values())
        facts = EnvironmentFacts("darwin")
        intents = tuple(
            ArtifactInstallIntent(
                artifacts[name],
                (),
                (CreatePythonEnvironment(name, f".aart/{name}/.venv", "/usr/bin/python3"),),
            )
            for name in names
        )

        result = prepare_install_plan(selection, intents, facts, EffectivePolicy())
        assert isinstance(result, Ok), result
        canonical = prepare_install_plan(
            selection,
            tuple(reversed(intents)),
            facts,
            EffectivePolicy(),
        )
        assert isinstance(canonical, Ok), canonical

        self.assertEqual(result.value, canonical.value)
        self.assertEqual(result.value.review_digest, canonical.value.review_digest)


if __name__ == "__main__":
    unittest.main()
