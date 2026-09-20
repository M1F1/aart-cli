"""CP-07 immutable facts, assessment, remediation and canonical planning."""

from __future__ import annotations

import dataclasses
import json
import unittest

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from aart_cli.application.installation_planning import (
    NO_ALLOWED_REMEDIATION,
    POLICY_VIOLATION,
    REQUIREMENT_CONFLICT,
    ArtifactInstallIntent,
    aggregate_requirements,
    allowed_remediations,
    assess_requirements,
    prepare_install_plan,
)
from aart_cli.application.python_environment import select_python_installer
from aart_cli.domain.candidates import CandidateId
from aart_cli.domain.effects import (
    ConfigureHarness,
    CopyTree,
    CreatePythonEnvironment,
    RiskClass,
)
from aart_cli.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    ObjectDigest,
    SourceAlias,
)
from aart_cli.domain.inspection import (
    EnvironmentFact,
    EnvironmentFacts,
    FactState,
    RemediationCapability,
    RemediationCapabilityKind,
    environment_facts_to_data,
)
from aart_cli.domain.plans import PlannedRemediation, install_plan_to_data
from aart_cli.domain.policies import EffectivePolicy, PolicyOverlay, compose_policy
from aart_cli.domain.python_runtime import PyProjectSpec
from aart_cli.domain.registry import (
    PromotionMode,
    PublicationStage,
    RegistryArtifactVersion,
)
from aart_cli.domain.remediations import (
    ConfigureCredential,
    InstallPythonPackages,
    InstallRuntime,
)
from aart_cli.domain.requirements import (
    CredentialRequirement,
    ExecutableRequirement,
    PythonPackageRequirement,
    RequirementId,
    RequirementState,
    RuntimeRequirement,
)
from aart_cli.domain.result import Err, Ok
from aart_cli.domain.selection import (
    ArtifactRequest,
    ArtifactSelection,
    OwnershipKind,
    OwnershipReason,
    ResolvedArtifact,
    ResolvedSelection,
    VersionConstraint,
)

# `differing_executors` is suppressed for the reason `doctor_properties_test` records: the scoped
# `make mutants` run re-runs the same test method object from a fresh runner per mutant, which is
# what the check detects. These properties are pure functions of generated input.
MUTATION_SETTINGS = settings(suppress_health_check=(HealthCheck.differing_executors,))


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


class PythonInstallerOfferTest(unittest.TestCase):
    """One dependency contract is one change to approve, named by the backend that will run it."""

    def _options(
        self,
        facts_installers: tuple[str, ...],
        *,
        policy: EffectivePolicy | None = None,
        lock_format: str | None = None,
        requirement: PythonPackageRequirement | None = None,
    ) -> tuple[PlannedRemediation, ...]:
        owner = ArtifactCoordinate(
            SourceAlias("company"), ArtifactIdentity("mcp", "github"), "1.0.0"
        )
        dependencies = requirement or PythonPackageRequirement(
            RequirementId("python-packages"),
            "requirements",
            "requirements.txt",
            lock_format=lock_format,
        )
        aggregated = aggregate_requirements(((owner, (dependencies,)),))
        assert isinstance(aggregated, Ok), aggregated
        facts = EnvironmentFacts(
            "darwin",
            (EnvironmentFact(dependencies.id, FactState.UNAVAILABLE),),
            tuple(
                RemediationCapability(RemediationCapabilityKind.PYTHON_INSTALLER, name)
                for name in facts_installers
            ),
        )
        assessments = assess_requirements(aggregated.value, facts)
        return allowed_remediations(assessments, facts, policy or EffectivePolicy())

    def _spec_choice(
        self,
        facts_installers: tuple[str, ...],
        *,
        policy: EffectivePolicy | None = None,
        lock_format: str | None = None,
    ) -> str:
        spec = PyProjectSpec("pyproject.toml", lock_format=lock_format)
        facts = EnvironmentFacts(
            "darwin",
            (),
            tuple(
                RemediationCapability(RemediationCapabilityKind.PYTHON_INSTALLER, name)
                for name in facts_installers
            ),
        )
        chosen = select_python_installer(spec, facts, policy or EffectivePolicy())
        assert isinstance(chosen, Ok), chosen
        return chosen.value.value

    def test_two_usable_backends_are_one_offer_naming_the_one_that_will_run(self) -> None:
        options = self._options(("pip", "uv"))

        self.assertEqual(len(options), 1)
        self.assertEqual(
            options[0].remediation,
            InstallPythonPackages(
                RequirementId("python-packages"), self._spec_choice(("pip", "uv"))
            ),
        )

    def test_the_only_backend_the_platform_runs_is_the_one_offered(self) -> None:
        for available in (("pip",), ("uv",)):
            with self.subTest(available=available):
                options = self._options(available)

                self.assertEqual(len(options), 1)
                self.assertEqual(
                    options[0].remediation,
                    InstallPythonPackages(RequirementId("python-packages"), available[0]),
                )

    def test_policy_narrowing_to_one_backend_leaves_that_backend_named(self) -> None:
        policy = EffectivePolicy(allowed_python_installers=frozenset({"uv"}))

        options = self._options(("pip", "uv"), policy=policy)

        self.assertEqual(len(options), 1)
        self.assertEqual(
            options[0].remediation,
            InstallPythonPackages(RequirementId("python-packages"), "uv"),
        )

    def test_a_lock_narrows_the_offer_to_the_backend_that_wrote_it(self) -> None:
        options = self._options(("pip", "uv"), lock_format="uv")

        self.assertEqual(len(options), 1)
        self.assertEqual(
            options[0].remediation,
            InstallPythonPackages(RequirementId("python-packages"), "uv"),
        )

    def test_no_backend_the_platform_runs_is_no_offer_at_all(self) -> None:
        self.assertEqual(self._options(()), ())

    def test_an_artifact_without_dependencies_is_offered_no_installer(self) -> None:
        owner = ArtifactCoordinate(
            SourceAlias("company"), ArtifactIdentity("mcp", "github"), "1.0.0"
        )
        executable = ExecutableRequirement(RequirementId("git"), "git")
        aggregated = aggregate_requirements(((owner, (executable,)),))
        assert isinstance(aggregated, Ok), aggregated
        facts = EnvironmentFacts(
            "darwin",
            (EnvironmentFact(executable.id, FactState.UNAVAILABLE),),
            (RemediationCapability(RemediationCapabilityKind.PYTHON_INSTALLER, "pip"),),
        )

        options = allowed_remediations(
            assess_requirements(aggregated.value, facts), facts, EffectivePolicy()
        )

        self.assertEqual(options, ())

    def test_every_pair_of_usable_backends_is_still_one_offer(self) -> None:
        for available in (("pip", "uv"), ("uv", "pip")):
            with self.subTest(available=available):
                installers = {
                    option.remediation.installer
                    for option in self._options(available)
                    if isinstance(option.remediation, InstallPythonPackages)
                }

                self.assertEqual(len(installers), 1)


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

    @MUTATION_SETTINGS
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
