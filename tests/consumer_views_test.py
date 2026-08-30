from __future__ import annotations

import dataclasses
import json
import unittest

from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    CredentialInputView,
    PresentationProfile,
    SelectionMode,
    consumer_plan_to_data,
    install_flow_screens,
    project_collection,
    project_install_plan,
    project_required_inputs,
    project_selection,
)
from agent_artifacts.domain.candidates import CandidateId
from agent_artifacts.domain.credentials import (
    CredentialObservation,
    CredentialProviderRef,
    CredentialState,
    ProviderState,
)
from agent_artifacts.domain.effects import CopyTree, RiskClass, StoreCredential
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    InputId,
    ObjectDigest,
    SourceAlias,
)
from agent_artifacts.domain.inputs import (
    BoundInput,
    BoundInputs,
    ConfigInput,
    EnvironmentBinding,
    InputGuidance,
    PersistedConfigValue,
    SecretInput,
    SecretProviderReference,
)
from agent_artifacts.domain.plans import (
    InstallPlan,
    MutationPlan,
    OwnedAssessment,
    OwnedRequirement,
    PlannedEffect,
    PlannedRemediation,
)
from agent_artifacts.domain.registry import (
    PromotionMode,
    PublicationStage,
    RegistryArtifactVersion,
)
from agent_artifacts.domain.remediations import ConfigureCredential
from agent_artifacts.domain.requirements import (
    CredentialRequirement,
    RequirementId,
    RequirementState,
    RuntimeRequirement,
)
from agent_artifacts.domain.selection import (
    ArtifactRequest,
    ArtifactSelection,
    CollectionCoordinate,
    OwnershipKind,
    OwnershipReason,
    ResolvedArtifact,
    ResolvedSelection,
    VersionConstraint,
)
from agent_artifacts.tui_consumer import (
    render_collection,
    render_install_plan,
    render_marketplace_artifact,
    render_required_inputs,
)
from agent_artifacts.tui_marketplace import MarketplaceTarget, project_marketplace_rows
from tests.tui_marketplace_test import _catalog as marketplace_catalog


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _resolved(*, ownership: OwnershipReason) -> ResolvedArtifact:
    coordinate = ArtifactCoordinate(
        SourceAlias("company"), ArtifactIdentity("mcp", "github"), "1.0.0"
    )
    version = RegistryArtifactVersion(
        coordinate,
        CandidateId("1" * 64),
        _digest("a"),
        _digest("b"),
        _digest("c"),
        _digest("d"),
        PromotionMode.VENDORED,
        PublicationStage.PUBLISHED,
    )
    return ResolvedArtifact(version, (ownership,))


def _artifact_request() -> ArtifactRequest:
    return ArtifactRequest(
        ArtifactIdentity("mcp", "github"),
        VersionConstraint("1.0.0"),
        SourceAlias("company"),
    )


def _selection() -> ResolvedSelection:
    artifact = _resolved(
        ownership=OwnershipReason(OwnershipKind.DIRECT, "company/mcp/github@1.0.0")
    )
    return ResolvedSelection(ArtifactSelection((_artifact_request(),)), (artifact,))


def _plan() -> InstallPlan:
    selection = _selection()
    owner = selection.artifacts[0].version.coordinate
    python = RuntimeRequirement(RequirementId("python"), "python", ">=3.11")
    credential = CredentialRequirement(RequirementId("github-token"), "macos-keychain")
    remediation = ConfigureCredential(credential.id, "macos-keychain")
    copy = CopyTree("payload", ".aart/artifacts/github")
    store = StoreCredential("github-token", "macos-keychain")
    return InstallPlan(
        selection,
        "darwin",
        (
            OwnedAssessment(
                OwnedRequirement(python, (owner,)),
                RequirementState.SATISFIED,
                "observed 3.12.1; expected >=3.11",
            ),
            OwnedAssessment(
                OwnedRequirement(credential, (owner,)),
                RequirementState.UNKNOWN,
                "provider has not been inspected",
            ),
        ),
        (PlannedRemediation(remediation, (owner,), RiskClass.CREDENTIAL_MUTATION),),
        MutationPlan(
            (PlannedEffect(copy, (owner,)), PlannedEffect(store, (owner,))),
            (RiskClass.LOCAL_MUTATION, RiskClass.CREDENTIAL_MUTATION),
        ),
        _digest("e"),
    )


def _credential_input() -> tuple[SecretInput, BoundInputs, CredentialObservation]:
    input_id = InputId("github-token")
    runtime_input = SecretInput(
        input_id,
        EnvironmentBinding("GITHUB_TOKEN"),
        guidance=InputGuidance(
            "GitHub credential",
            "Used to call the GitHub API.",
            format_hint="fine-grained access token",
        ),
    )
    provider = CredentialProviderRef("macos-keychain", "github.com", "work")
    bound = BoundInputs((BoundInput(runtime_input, SecretProviderReference(input_id, provider)),))
    observation = CredentialObservation(
        bound.credential_references[0],
        ProviderState.AVAILABLE,
        CredentialState.PRESENT,
        "reference resolves",
    )
    return runtime_input, bound, observation


class ConsumerPlanProjectionTest(unittest.TestCase):
    def test_fast_and_verbose_are_projections_of_one_semantic_plan(self) -> None:
        runtime_input, bound, observation = _credential_input()
        plan = _plan()
        view = project_install_plan(
            plan,
            inputs=(runtime_input,),
            bound_inputs=bound,
            credential_observations=(observation,),
        )
        session = ConsumerSession.from_plan(view)

        fast = render_install_plan(view, PresentationProfile.FAST)
        verbose = render_install_plan(view, PresentationProfile.VERBOSE)
        switched = session.switch_profile(PresentationProfile.VERBOSE)

        self.assertEqual(session.semantic_identity, switched.semantic_identity)
        self.assertEqual(view.review_digest, str(plan.review_digest))
        self.assertNotEqual(fast, verbose)
        self.assertNotIn("observed 3.12.1", "\n".join(fast))
        self.assertIn("observed 3.12.1", "\n".join(verbose))

    def test_fast_keeps_every_material_risk_and_review_action_visible(self) -> None:
        view = project_install_plan(_plan())

        rendered = "\n".join(render_install_plan(view, PresentationProfile.FAST))

        self.assertIn("local mutation", rendered.lower())
        self.assertIn("credential mutation", rendered.lower())
        self.assertIn("review", rendered.lower())
        self.assertIn(view.review_digest, rendered)

    def test_machine_projection_is_complete_regardless_of_human_profile(self) -> None:
        view = project_install_plan(_plan())
        session = ConsumerSession.from_plan(view)

        before = consumer_plan_to_data(view)
        session = session.switch_profile(PresentationProfile.VERBOSE)
        after = consumer_plan_to_data(view)

        self.assertEqual(before, after)
        self.assertEqual(len(before["requirements"]), 2)
        self.assertEqual(len(before["effects"]), 2)
        self.assertEqual(before["review_digest"], view.review_digest)
        self.assertEqual(session.profile, PresentationProfile.VERBOSE)

    def test_required_credential_view_has_no_value_channel(self) -> None:
        runtime_input, bound, observation = _credential_input()

        projected = project_required_inputs(
            (runtime_input,),
            bound_inputs=bound,
            credential_observations=(observation,),
        )

        self.assertEqual(len(projected), 1)
        self.assertIsInstance(projected[0], CredentialInputView)
        names = {field.name for field in dataclasses.fields(CredentialInputView)}
        self.assertFalse(names & {"value", "default", "material"})
        encoded = json.dumps(dataclasses.asdict(projected[0]), sort_keys=True)
        self.assertNotIn('"value"', encoded)
        self.assertIn("macos-keychain", encoded)
        self.assertIn("present", encoded)

    def test_exact_collection_and_customized_selection_stay_distinct(self) -> None:
        collection = CollectionCoordinate(SourceAlias("company"), "developer", "1.0.0")
        exact_artifact = _resolved(
            ownership=OwnershipReason(OwnershipKind.COLLECTION, str(collection))
        )
        custom_artifact = _resolved(
            ownership=OwnershipReason(OwnershipKind.DIRECT, "company/mcp/github@1.0.0")
        )
        exact = ResolvedSelection(ArtifactSelection(collections=(collection,)), (exact_artifact,))
        custom = ResolvedSelection(
            ArtifactSelection((_artifact_request(),), derived_from=(collection,)),
            (custom_artifact,),
        )

        exact_view = project_selection(exact)
        custom_view = project_selection(custom)

        self.assertEqual(exact_view.mode, SelectionMode.EXACT_COLLECTION)
        self.assertEqual(custom_view.mode, SelectionMode.CUSTOM_COLLECTION)
        self.assertNotEqual(exact_view.semantic_identity, custom_view.semantic_identity)
        self.assertIn("exact Collection", exact_view.explanation)
        self.assertIn("custom selection", custom_view.explanation)

    def test_install_flow_includes_only_required_conditional_screens(self) -> None:
        plan = _plan()
        input_view = project_required_inputs((_credential_input()[0],))

        complete = install_flow_screens(project_install_plan(plan, inputs=_credential_input()[:1]))
        routine_plan = dataclasses.replace(plan, remediations=())
        routine = install_flow_screens(project_install_plan(routine_plan))

        self.assertIn(ConsumerScreen.REQUIRED_INPUTS, complete)
        self.assertIn(ConsumerScreen.REMEDIATION, complete)
        self.assertNotIn(ConsumerScreen.REQUIRED_INPUTS, routine)
        self.assertNotIn(ConsumerScreen.REMEDIATION, routine)
        self.assertEqual(len(input_view), 1)

    def test_required_inputs_reuse_config_but_never_display_credential_material(self) -> None:
        runtime_input, bound, observation = _credential_input()
        org_id = InputId("github-org")
        org = ConfigInput(
            org_id,
            EnvironmentBinding("GITHUB_ORG"),
            guidance=InputGuidance("GitHub organization", example="acme-engineering"),
        )
        inputs = project_required_inputs(
            (runtime_input, org),
            bound_inputs=BoundInputs(
                (*bound.inputs, BoundInput(org, PersistedConfigValue(org_id, "platform-team")))
            ),
            credential_observations=(observation,),
        )

        fast = "\n".join(render_required_inputs(inputs, PresentationProfile.FAST))
        verbose = "\n".join(render_required_inputs(inputs, PresentationProfile.VERBOSE))

        self.assertIn("platform-team", fast)
        self.assertIn("Configured securely", fast)
        self.assertNotIn("macos-keychain:github.com/work", fast)
        self.assertIn("macos-keychain:github.com/work", verbose)

    def test_marketplace_fast_uses_outcome_language_and_verbose_discloses_evidence(self) -> None:
        catalog = marketplace_catalog()
        row = project_marketplace_rows(
            catalog,
            MarketplaceTarget(("claude",), "darwin", "project", "copy"),
        )[0]

        fast = "\n".join(render_marketplace_artifact(row, PresentationProfile.FAST))
        verbose = "\n".join(render_marketplace_artifact(row, PresentationProfile.VERBOSE))

        self.assertIn(row.summary, fast)
        self.assertNotIn("manifest", fast.lower())
        self.assertNotIn(row.object_digest, fast)
        self.assertIn("digests", verbose)
        self.assertIn(row.object_digest, verbose)

    def test_collection_member_change_is_visible_as_custom_before_review(self) -> None:
        collection = CollectionCoordinate(SourceAlias("company"), "developer", "1.0.0")
        members = (
            _artifact_request(),
            ArtifactRequest(
                ArtifactIdentity("skill", "review"),
                VersionConstraint("1.0.0"),
                SourceAlias("company"),
            ),
        )
        from agent_artifacts.domain.selection import Collection, CollectionMember

        definition = Collection(
            collection,
            "Developer tools",
            tuple(CollectionMember(item) for item in members),
            _digest("f"),
        )

        exact = project_collection(definition)
        custom = project_collection(definition, selected=(str(members[0]),))

        self.assertTrue(exact.exact)
        self.assertFalse(custom.exact)
        self.assertNotEqual(exact.semantic_identity, custom.semantic_identity)
        rendered = "\n".join(render_collection(custom, PresentationProfile.FAST))
        self.assertIn("1 / 2 selected", rendered)
        self.assertIn("Custom selection", rendered)


if __name__ == "__main__":
    unittest.main()
