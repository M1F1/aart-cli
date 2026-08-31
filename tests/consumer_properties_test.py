"""CP-13 — properties the consumer projections hold for every plan, not just the worked examples.

Fast and Verbose are the same semantics rendered at two levels of disclosure.  These tests fix
that as a property rather than as an example: whatever the plan, switching profile may not change
what was selected, what will happen, or the identity somebody reviewed; Fast may not drop a
material risk; and no arrangement of inputs gives a credential a value channel.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import unittest

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_artifacts.application.consumer_views import (
    ConfigInputView,
    ConsumerSession,
    CredentialInputView,
    PresentationProfile,
    SelectionMode,
    consumer_plan_to_data,
    project_activity,
    project_install_plan,
    project_required_inputs,
    project_selection,
)
from agent_artifacts.domain.candidates import CandidateId
from agent_artifacts.domain.credentials import CredentialProviderRef
from agent_artifacts.domain.effects import (
    ConfigureHarness,
    CopyTree,
    RiskClass,
    StoreCredential,
    WriteFile,
)
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
from agent_artifacts.tui_consumer import render_activity, render_install_plan, render_ready
from tests.consumer_activity_test import lifecycle_outcome

from agent_artifacts.application.consumer_views import ActivityRecord  # isort: skip

NAME = st.from_regex(r"\A[a-z][a-z0-9]{0,4}(?:-[a-z0-9]{1,4})?\Z")
VERSION = st.from_regex(r"\A[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,2}\Z")
PROFILES = st.sampled_from(tuple(PresentationProfile))
SETTINGS = settings(max_examples=40, deadline=None, suppress_health_check=(HealthCheck.too_slow,))


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


COORDINATE = st.builds(
    ArtifactCoordinate,
    st.builds(SourceAlias, NAME),
    st.builds(ArtifactIdentity, NAME, NAME),
    VERSION,
)


def _resolved(coordinate: ArtifactCoordinate, ownership: OwnershipReason) -> ResolvedArtifact:
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


@st.composite
def plans(draw: st.DrawFn) -> InstallPlan:
    """A canonical install plan whose shape varies over everything the projection reads."""

    coordinate = draw(COORDINATE)
    ownership = OwnershipReason(
        draw(st.sampled_from(tuple(OwnershipKind))), str(coordinate) or "owner"
    )
    selection = ResolvedSelection(
        ArtifactSelection(
            (
                ArtifactRequest(
                    coordinate.artifact,
                    VersionConstraint(coordinate.version or "1.0.0"),
                    coordinate.source,
                ),
            )
        ),
        (_resolved(coordinate, ownership),),
    )

    requirements = []
    for name, state in draw(
        st.lists(
            st.tuples(NAME, st.sampled_from(tuple(RequirementState))),
            min_size=0,
            max_size=3,
            unique_by=lambda item: item[0],
        )
    ):
        requirement = draw(
            st.sampled_from(
                (
                    RuntimeRequirement(RequirementId(name), "python", ">=3.11"),
                    CredentialRequirement(RequirementId(name), "macos-keychain"),
                )
            )
        )
        requirements.append(
            OwnedAssessment(OwnedRequirement(requirement, (coordinate,)), state, f"observed {name}")
        )

    remediations = tuple(
        PlannedRemediation(
            ConfigureCredential(RequirementId(name), "macos-keychain"),
            (coordinate,),
            RiskClass.CREDENTIAL_MUTATION,
        )
        for name in draw(st.lists(NAME, min_size=0, max_size=2, unique=True))
    )

    effects = draw(
        st.lists(
            st.one_of(
                st.builds(CopyTree, st.just("payload"), NAME),
                st.builds(StoreCredential, NAME, st.just("macos-keychain")),
                st.builds(ConfigureHarness, NAME, st.just(str(coordinate)), NAME),
                st.builds(WriteFile, NAME, st.just(str(_digest("f"))), st.booleans()),
            ),
            min_size=1,
            max_size=4,
        )
    )
    planned = tuple(PlannedEffect(effect, (coordinate,)) for effect in effects)
    return InstallPlan(
        selection,
        draw(st.sampled_from(("darwin", "linux"))),
        tuple(requirements),
        remediations,
        MutationPlan(planned, tuple({effect.risk for effect in effects})),
        _digest("e"),
    )


def _human(value: str) -> str:
    return value.replace("_", "-").lower().replace("-", " ")


class PresentationProfileIdentityTest(unittest.TestCase):
    @SETTINGS
    @given(plans(), st.lists(PROFILES, min_size=1, max_size=6))
    def test_switching_profile_never_changes_what_was_selected_or_reviewed(
        self, plan: InstallPlan, profiles: list[PresentationProfile]
    ) -> None:
        view = project_install_plan(plan)
        session = ConsumerSession.from_plan(view)
        identity, machine = session.semantic_identity, consumer_plan_to_data(view)

        for profile in profiles:
            session = session.switch_profile(profile)
            self.assertEqual(session.profile, profile)
            self.assertEqual(session.semantic_identity, identity)
            self.assertEqual(consumer_plan_to_data(view), machine)

        self.assertEqual(view.review_digest, str(plan.review_digest))
        self.assertEqual(machine["review_digest"], str(plan.review_digest))

    @SETTINGS
    @given(plans())
    def test_fast_discloses_less_than_verbose_but_never_a_different_plan(
        self, plan: InstallPlan
    ) -> None:
        view = project_install_plan(plan)

        fast = render_install_plan(view, PresentationProfile.FAST)
        verbose = render_install_plan(view, PresentationProfile.VERBOSE)

        self.assertIn(view.review_digest, "\n".join(fast))
        self.assertIn(view.review_digest, "\n".join(verbose))
        self.assertLessEqual(len(fast), len(verbose))


class FastHidesNoMaterialRiskTest(unittest.TestCase):
    @SETTINGS
    @given(plans())
    def test_every_risk_the_plan_carries_is_named_in_the_fast_projection(
        self, plan: InstallPlan
    ) -> None:
        view = project_install_plan(plan)

        rendered = "\n".join(render_install_plan(view, PresentationProfile.FAST)).lower()

        for risk in plan.mutation.risks:
            self.assertIn(_human(risk.name), rendered)
        self.assertIn(view.review_digest, rendered)

    @SETTINGS
    @given(plans())
    def test_a_remediation_decision_is_never_hidden_by_the_fast_projection(
        self, plan: InstallPlan
    ) -> None:
        view = project_install_plan(plan)

        rendered = "\n".join(render_install_plan(view, PresentationProfile.FAST)).lower()

        if plan.remediations:
            self.assertIn("remediation", rendered)
            for remediation in view.remediations:
                self.assertIn(_human(remediation.kind), rendered)
        for assessment in plan.requirements:
            if assessment.state is not RequirementState.SATISFIED:
                self.assertIn(str(assessment.requirement.requirement.id), rendered)

    @SETTINGS
    @given(plans())
    def test_the_screen_somebody_confirms_from_names_the_same_risks(
        self, plan: InstallPlan
    ) -> None:
        """Screen 09 compresses the review. Compression is not permission to go quiet: whatever
        risk or remediation the full plan carries is on the screen the decision is made on."""

        view = project_install_plan(plan)

        rendered = "\n".join(render_ready(view, PresentationProfile.FAST)).lower()

        for risk in plan.mutation.risks:
            self.assertIn(_human(risk.name), rendered)
        for remediation in view.remediations:
            self.assertIn(_human(remediation.kind), rendered)
        self.assertIn(view.review_digest, rendered)


class NoCredentialValueChannelTest(unittest.TestCase):
    @SETTINGS
    @given(
        st.lists(
            st.tuples(NAME, st.booleans()),
            min_size=1,
            max_size=5,
            unique_by=lambda item: item[0],
        ),
        st.text(
            alphabet=st.characters(blacklist_categories=("Cs", "Cc")), min_size=1, max_size=20
        ).map(str.strip),
    )
    def test_no_arrangement_of_inputs_gives_a_credential_a_value_field(
        self, declared: list[tuple[str, bool]], value: str
    ) -> None:
        inputs: list[SecretInput | ConfigInput] = []
        bound: list[BoundInput] = []
        for name, secret in declared:
            identifier = InputId(name)
            binding = EnvironmentBinding(name.upper().replace("-", "_"))
            if secret:
                runtime_input = SecretInput(identifier, binding)
                provider = CredentialProviderRef("macos-keychain", "aart", name)
                bound.append(
                    BoundInput(runtime_input, SecretProviderReference(identifier, provider))
                )
            else:
                runtime_input = ConfigInput(identifier, binding)
                bound.append(
                    BoundInput(runtime_input, PersistedConfigValue(identifier, value or "unset"))
                )
            inputs.append(runtime_input)

        projected = project_required_inputs(tuple(inputs), bound_inputs=BoundInputs(tuple(bound)))

        secrets = {name for name, secret in declared if secret}
        for view in projected:
            encoded = json.dumps(
                dataclasses.asdict(view), sort_keys=True, default=str, ensure_ascii=False
            )
            if view.id in secrets:
                self.assertIsInstance(view, CredentialInputView)
                names = {field.name for field in dataclasses.fields(CredentialInputView)}
                self.assertFalse(names & {"value", "default", "material", "secret"})
                self.assertIn("macos-keychain", encoded)
            else:
                self.assertIsInstance(view, ConfigInputView)
                self.assertEqual(view.current, value or "unset")
                self.assertEqual(json.loads(encoded)["current"], view.current)
        self.assertEqual(len(projected), len(declared))


class CollectionIdentityTest(unittest.TestCase):
    @SETTINGS
    @given(COORDINATE, NAME, VERSION)
    def test_an_exact_collection_never_shares_identity_with_a_customized_one(
        self, coordinate: ArtifactCoordinate, collection_name: str, collection_version: str
    ) -> None:
        collection = CollectionCoordinate(coordinate.source, collection_name, collection_version)
        exact = ResolvedSelection(
            ArtifactSelection(collections=(collection,)),
            (_resolved(coordinate, OwnershipReason(OwnershipKind.COLLECTION, str(collection))),),
        )
        custom = ResolvedSelection(
            ArtifactSelection(
                (
                    ArtifactRequest(
                        coordinate.artifact,
                        VersionConstraint(coordinate.version or "1.0.0"),
                        coordinate.source,
                    ),
                ),
                derived_from=(collection,),
            ),
            (_resolved(coordinate, OwnershipReason(OwnershipKind.DIRECT, str(coordinate))),),
        )

        exact_view, custom_view = project_selection(exact), project_selection(custom)

        self.assertEqual(exact_view.mode, SelectionMode.EXACT_COLLECTION)
        self.assertEqual(custom_view.mode, SelectionMode.CUSTOM_COLLECTION)
        self.assertNotEqual(exact_view.semantic_identity, custom_view.semantic_identity)


class ActivityOrderingTest(unittest.TestCase):
    @SETTINGS
    @given(
        st.lists(
            st.datetimes(
                min_value=dt.datetime(2024, 1, 1),
                max_value=dt.datetime(2026, 12, 31),
                timezones=st.just(dt.timezone.utc),
            ),
            min_size=0,
            max_size=8,
            unique=True,
        ),
        st.dates(min_value=dt.date(2024, 1, 1), max_value=dt.date(2026, 12, 31)),
    )
    def test_a_timeline_reads_newest_first_and_loses_nothing(
        self, moments: list[dt.datetime], today: dt.date
    ) -> None:
        outcome = lifecycle_outcome()
        records = tuple(ActivityRecord(moment.isoformat(), outcome) for moment in moments)

        view = project_activity(records, today=today)

        self.assertEqual(len(view.entries), len(records))
        days = [day.entries[0].recorded_at[:10] for day in view.days]
        self.assertEqual(days, sorted(days, reverse=True))
        self.assertEqual(len(set(days)), len(days))
        for day in view.days:
            times = [entry.recorded_at for entry in day.entries]
            self.assertEqual(times, sorted(times, reverse=True))
        rendered = "\n".join(render_activity(view, PresentationProfile.FAST))
        self.assertNotIn("sha256:", rendered)


if __name__ == "__main__":
    unittest.main()
