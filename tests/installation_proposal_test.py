"""One lowering behind the plan somebody reviews and the effects that actually run.

An install is described twice: once as the review a person confirms, and once as the desired state
a reconciler drives. If those two descriptions are written separately they can disagree, and a
person then confirms one thing while another runs. Everything here exists to make that impossible:
a single :class:`PlannedInstallation` is lowered into both, and an :class:`InstallationProposal`
cannot be constructed unless every effect that will run is named in the plan that was reviewed.
"""

from __future__ import annotations

import json
import unittest

from agent_artifacts.application.installation_proposal import (
    PROPOSAL_INVALID,
    InstallationProposal,
    PlannedInstallation,
    desired_state_for,
    intended_receipt,
    propose_installation,
)
from agent_artifacts.application.installation_verification import InstallationObservation
from agent_artifacts.application.installed_state import (
    current_state_from_observation,
    desired_state_from_receipt,
)
from agent_artifacts.application.runtime_projection import RuntimeProjection
from agent_artifacts.domain.candidates import CandidateId
from agent_artifacts.domain.credentials import CredentialProviderRef
from agent_artifacts.domain.effects import (
    ConfigureHarness,
    CopyTree,
    CreatePythonEnvironment,
    InstallPythonDependencies,
    ReplaceCredential,
    RiskClass,
    StoreCredential,
    WriteFile,
)
from agent_artifacts.domain.harness import McpRegistration, Scope, mcp_target
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
from agent_artifacts.domain.inspection import EnvironmentFacts
from agent_artifacts.domain.launch import LaunchContract, Transport
from agent_artifacts.domain.plans import install_plan_to_data
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.python_runtime import ArtifactEnvironment
from agent_artifacts.domain.reconciliation import (
    Component,
    ComponentId,
    ComponentState,
    CurrentState,
    ObservedComponent,
)
from agent_artifacts.domain.registry import (
    PromotionMode,
    PublicationStage,
    RegistryArtifactVersion,
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

ROOT = "/home/agent/.tabnine/agent/aart/mcp/github"
ENVIRONMENT = ArtifactEnvironment("mcp/github", ROOT)
COORDINATE = ArtifactCoordinate(SourceAlias("public"), ArtifactIdentity("mcp", "github"), "1.5.0")
KIT = OwnershipReason(OwnershipKind.COLLECTION, "public/collection/data-scientist@1.0.0")
TOKEN = InputId("github-token")
ORG = InputId("github-org")


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _resolved(name: str = "github", *, version: str = "1.5.0") -> ResolvedArtifact:
    coordinate = ArtifactCoordinate(SourceAlias("public"), ArtifactIdentity("mcp", name), version)
    return ResolvedArtifact(
        RegistryArtifactVersion(
            coordinate,
            CandidateId("b" * 64),
            _digest("a"),
            _digest("c"),
            _digest("d"),
            _digest("e"),
            PromotionMode.VENDORED,
            PublicationStage.PUBLISHED,
        ),
        (KIT,),
    )


def _selection(*artifacts: ResolvedArtifact) -> ResolvedSelection:
    return ResolvedSelection(
        ArtifactSelection(
            tuple(
                ArtifactRequest(
                    item.version.coordinate.artifact,
                    VersionConstraint(item.version.coordinate.version or "*"),
                    item.version.coordinate.source,
                )
                for item in artifacts
            )
        ),
        artifacts,
    )


def _bound() -> BoundInputs:
    return BoundInputs(
        (
            BoundInput(
                SecretInput(TOKEN, EnvironmentBinding("GITHUB_TOKEN")),
                SecretProviderReference(
                    TOKEN, CredentialProviderRef("macos-keychain", "aart", "github-token")
                ),
            ),
            BoundInput(
                ConfigInput(ORG, EnvironmentBinding("GITHUB_ORG")),
                PersistedConfigValue(ORG, "acme"),
            ),
        )
    )


#: A launcher body shaped like a real one: it names the variables and the resolution command,
#: which is exactly the material a review plan must carry only by digest.
LAUNCHER_BODY = (
    "#!/bin/sh\n"
    'if ! GITHUB_TOKEN="$(security find-generic-password -w -s aart -a github-token)"; then\n'
    "  exit 78\n"
    "fi\n"
    "export GITHUB_TOKEN\n"
    "GITHUB_ORG=acme\n"
    "export GITHUB_ORG\n"
    "exec true\n"
)


def _launcher(path: str = f"{ROOT}/launch") -> RuntimeProjection:
    return RuntimeProjection(path, LAUNCHER_BODY, _digest("1"))


def _planned(
    artifact: ResolvedArtifact | None = None,
    *,
    environment: ArtifactEnvironment = ENVIRONMENT,
    launcher: RuntimeProjection | None = None,
    registrations: tuple[McpRegistration, ...] | None = None,
    **overrides: object,
) -> PlannedInstallation:
    projection = launcher or _launcher()
    registered = (
        registrations
        if registrations is not None
        else (McpRegistration(mcp_target("tabnine", Scope.PROJECT), "github", projection.command),)
    )
    fields: dict[str, object] = {
        "bound": _bound(),
        "declared": tuple(item.input for item in _bound().inputs),
        "registrations": registered,
        "payload_source": "/var/lib/aart/store/github",
        "base_interpreter": "/usr/bin/python3",
        "dependencies": (f"{environment.payload}/requirements.txt", "requirements", "pip"),
        "runtime": "python",
    }
    fields.update(overrides)
    return PlannedInstallation(
        artifact or _resolved(),
        environment,
        LaunchContract("server.py", Transport.STDIO, ("--strict",)),
        projection,
        **fields,  # type: ignore[arg-type]
    )


def _nothing_installed(planned: PlannedInstallation) -> CurrentState:
    """What an inspector reports about a machine where this artifact is not installed."""

    return current_state_from_observation(
        desired_state_for(planned),
        intended_receipt(planned),
        InstallationObservation(),
        credentials=((str(TOKEN), ComponentState.ABSENT),),
    )


class PlannedInstallationTest(unittest.TestCase):
    def test_a_planned_installation_lowers_into_every_part_an_install_establishes(self) -> None:
        desired = desired_state_for(_planned())

        self.assertEqual(
            [str(component.id) for component in desired.components],
            [
                "payload",
                "runtime-environment",
                "runtime-dependencies",
                "credential:github-token",
                "launcher",
                "harness:tabnine",
            ],
        )
        self.assertEqual(desired.artifact, COORDINATE)

    def test_the_state_an_install_converges_to_is_the_state_a_repair_later_keeps(self) -> None:
        """The install and the repair are the same builder over the same receipt.

        A separate builder for "what to install" would be free to drift from "what to keep", and
        the first repair after an install would then quietly change the installation.
        """

        planned = _planned()

        rebuilt = desired_state_from_receipt(
            COORDINATE,
            intended_receipt(planned),
            base_interpreter=planned.base_interpreter,
            dependencies=planned.dependencies,
            payload_source=planned.payload_source,
        )

        self.assertEqual(rebuilt, desired_state_for(planned))

    def test_the_receipt_an_install_intends_is_the_one_it_will_leave_behind(self) -> None:
        receipt = intended_receipt(_planned())

        self.assertEqual(receipt.root, ROOT)
        self.assertEqual(receipt.launcher, f"{ROOT}/launch")
        self.assertEqual(receipt.interpreter, ENVIRONMENT.interpreter)
        self.assertEqual(receipt.base_interpreter, "/usr/bin/python3")
        self.assertIs(receipt.transport, Transport.STDIO)
        self.assertEqual([str(item.input) for item in receipt.credentials], ["github-token"])

    def test_a_harness_entry_that_names_something_other_than_the_planned_launcher_is_refused(
        self,
    ) -> None:
        stray = McpRegistration(mcp_target("tabnine", Scope.PROJECT), "github", f"{ROOT}/other")

        with self.assertRaises(ValueError):
            _planned(registrations=(stray,))

    def test_a_launcher_outside_the_artifact_root_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            _planned(launcher=_launcher("/usr/local/bin/github"), registrations=())

    def test_dependencies_without_the_interpreter_that_builds_them_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            _planned(base_interpreter=None)

    def test_omitting_what_a_plan_does_not_know_omits_the_component_rather_than_inventing_it(
        self,
    ) -> None:
        desired = desired_state_for(
            _planned(payload_source=None, base_interpreter=None, dependencies=None)
        )

        self.assertEqual(
            [str(component.id) for component in desired.components],
            ["credential:github-token", "launcher", "harness:tabnine"],
        )


class InstallationProposalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.planned = _planned()
        self.selection = _selection(self.planned.artifact)
        self.facts = EnvironmentFacts("darwin", ())

    def propose(self, **overrides):
        arguments: dict[str, object] = {
            "installations": (self.planned,),
            "selection": self.selection,
            "facts": self.facts,
            "policy": EffectivePolicy(),
            "observed": ((COORDINATE, _nothing_installed(self.planned)),),
        }
        arguments.update(overrides)
        return propose_installation(
            arguments.pop("installations"),  # type: ignore[arg-type]
            arguments.pop("selection"),  # type: ignore[arg-type]
            arguments.pop("facts"),  # type: ignore[arg-type]
            arguments.pop("policy"),  # type: ignore[arg-type]
            **arguments,  # type: ignore[arg-type]
        )

    def test_everything_that_will_run_is_named_in_the_plan_somebody_reviews(self) -> None:
        proposed = self.propose()

        self.assertIsInstance(proposed, Ok, getattr(proposed, "diagnostics", ()))
        proposal = proposed.value
        reviewed = {item.effect for item in proposal.plan.mutation.effects}
        running = {step.effect for plan in proposal.lifecycle for step in plan.repair.steps}
        self.assertTrue(running)
        self.assertEqual(running, reviewed)

    def test_a_fresh_machine_is_planned_as_the_whole_installation(self) -> None:
        proposal = self.propose().value

        self.assertEqual(
            sorted(type(item.effect).__name__ for item in proposal.plan.mutation.effects),
            [
                ConfigureHarness.__name__,
                CopyTree.__name__,
                CreatePythonEnvironment.__name__,
                InstallPythonDependencies.__name__,
                StoreCredential.__name__,
                WriteFile.__name__,
            ],
        )
        self.assertIn(RiskClass.CREDENTIAL_MUTATION, proposal.plan.mutation.risks)

    def test_a_credential_that_is_already_there_and_wrong_is_replaced_and_the_review_says_so(
        self,
    ) -> None:
        """The review is derived from the reconciliation, not assumed from a fresh install.

        Storing a credential that is absent and replacing one that is wrong are different acts, and
        a review that always claimed the first would misdescribe the second.
        """

        credential = ComponentId(Component.CREDENTIAL, str(TOKEN))
        observed = CurrentState(
            COORDINATE,
            tuple(
                ObservedComponent(
                    component.id,
                    ComponentState.DIVERGENT
                    if component.id == credential
                    else ComponentState.MATCHED,
                )
                for component in desired_state_for(self.planned).components
            ),
        )

        proposal = self.propose(observed=((COORDINATE, observed),)).value

        kinds = {type(item.effect).__name__ for item in proposal.plan.mutation.effects}
        self.assertIn(ReplaceCredential.__name__, kinds)
        self.assertNotIn(StoreCredential.__name__, kinds)

    def test_an_installation_that_is_already_what_was_wanted_proposes_nothing_to_run(self) -> None:
        converged = CurrentState(
            COORDINATE,
            tuple(
                ObservedComponent(component.id, ComponentState.MATCHED)
                for component in desired_state_for(self.planned).components
            ),
        )

        proposal = self.propose(observed=((COORDINATE, converged),)).value

        self.assertEqual(proposal.plan.mutation.effects, ())
        self.assertEqual(proposal.lifecycle[0].repair.steps, ())

    def test_an_artifact_nobody_looked_at_is_refused_rather_than_assumed_absent(self) -> None:
        refused = self.propose(observed=())

        self.assertIsInstance(refused, Err)
        self.assertIs(refused.diagnostics[0].code, PROPOSAL_INVALID)

    def test_an_effect_the_policy_forbids_stops_the_proposal(self) -> None:
        refused = self.propose(policy=EffectivePolicy(risk_ceiling=RiskClass.READ_ONLY))

        self.assertIsInstance(refused, Err)

    def test_the_proposal_carries_one_lifecycle_plan_for_each_artifact_it_reviews(self) -> None:
        second = _resolved("jira", version="2.0.0")
        environment = ArtifactEnvironment("mcp/jira", "/home/agent/.tabnine/agent/aart/mcp/jira")
        other = _planned(
            second,
            environment=environment,
            launcher=_launcher(f"{environment.root}/launch"),
            registrations=(),
            dependencies=(f"{environment.payload}/requirements.txt", "requirements", "pip"),
        )

        proposal = self.propose(
            installations=(self.planned, other),
            selection=_selection(self.planned.artifact, second),
            observed=(
                (COORDINATE, _nothing_installed(self.planned)),
                (second.version.coordinate, _nothing_installed(other)),
            ),
        ).value

        self.assertEqual(
            [str(item.intent.desired.artifact) for item in proposal.lifecycle],
            ["public/mcp/github@1.5.0", "public/mcp/jira@2.0.0"],
        )

    def test_who_asked_for_the_artifact_survives_into_the_action_that_installs_it(self) -> None:
        proposal = self.propose().value

        self.assertEqual(proposal.lifecycle[0].intent.resulting_ownership, (KIT,))

    def test_a_proposal_whose_plan_does_not_cover_what_would_run_cannot_exist(self) -> None:
        proposal = self.propose().value
        narrowed = self.propose(
            observed=(
                (
                    COORDINATE,
                    CurrentState(
                        COORDINATE,
                        tuple(
                            ObservedComponent(component.id, ComponentState.MATCHED)
                            for component in desired_state_for(self.planned).components
                        ),
                    ),
                ),
            )
        ).value

        with self.assertRaises(ValueError):
            InstallationProposal(narrowed.plan, proposal.lifecycle)

    def test_the_plan_names_the_launcher_by_digest_and_never_carries_what_is_in_it(self) -> None:
        """A launcher body holds bound values and a provider command; a review plan holds neither.

        The plan is written to disk, printed, and shown in a TUI, so what it may carry about a
        launcher is the digest that identifies it and nothing that was rendered into it.
        """

        proposal = self.propose().value

        encoded = json.dumps(install_plan_to_data(proposal.plan), sort_keys=True)

        self.assertIn(self.planned.launcher.digest.value, encoded)
        for rendered in ("GITHUB_TOKEN", "GITHUB_ORG", "acme", "find-generic-password"):
            self.assertNotIn(rendered, encoded)


if __name__ == "__main__":
    unittest.main()
