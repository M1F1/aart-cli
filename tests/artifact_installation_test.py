"""Turning what an artifact declares into the installation this machine would perform.

`propose_installation` lowers a `PlannedInstallation` into the plan somebody reviews and the effects
that run. Producing that `PlannedInstallation` is the step before it, and it is where the two halves
of an install meet: what the package declares -- a runtime, a dependency descriptor, the inputs it
is started with -- and what this machine offers -- a root to install into, an interpreter to build
from, values for the inputs, and harnesses to register with.

Nothing here touches a filesystem, starts a process or reads a secret. The values arrive as
references and the launcher is derived, not written.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass

from agent_artifacts.application.artifact_installation import (
    INSTALLATION_NOT_DESCRIBED,
    installation_remediations,
    plan_artifact_installation,
    requirements_for,
)
from agent_artifacts.application.installation_planning import (
    ArtifactInstallIntent,
    inspect_requirements,
    prepare_install_plan,
)
from agent_artifacts.domain.credentials import CredentialProviderRef, CredentialReference
from agent_artifacts.domain.harness import Scope, mcp_target
from agent_artifacts.domain.identifiers import InputId
from agent_artifacts.domain.inputs import (
    ConfigInput,
    EnvironmentBinding,
    InputValueSource,
    PersistedConfigValue,
    SecretInput,
    SecretProviderReference,
)
from agent_artifacts.domain.inspection import (
    EnvironmentFact,
    EnvironmentFacts,
    FactState,
    RemediationCapability,
    RemediationCapabilityKind,
)
from agent_artifacts.domain.install_description import InstallDescription
from agent_artifacts.domain.launch import LaunchContract, Transport
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.python_runtime import PyProjectSpec, RequirementsFile
from agent_artifacts.domain.requirements import (
    CredentialRequirement,
    HarnessRequirement,
    PythonPackageRequirement,
    RuntimeRequirement,
)
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.domain.selection import (
    ArtifactRequest,
    ArtifactSelection,
    ResolvedSelection,
    VersionConstraint,
)
from tests.installation_proposal_test import KIT, ROOT, _resolved

TOKEN = InputId("github-token")
ORG = InputId("github-org")
PAYLOAD_SOURCE = "/var/lib/aart/store/mcp/github/1.5.0"
INTERPRETER = "/usr/bin/python3"


class _Keychain:
    provider = "macos-keychain"

    def resolution_argv(self, reference: CredentialReference) -> tuple[str, ...]:
        return (
            "security",
            "find-generic-password",
            "-w",
            "-s",
            reference.provider.service,
            "-a",
            reference.provider.account,
        )


def _description(**overrides: object) -> InstallDescription:
    fields: dict[str, object] = {
        "contract": LaunchContract("server.py", Transport.STDIO, ("--strict",)),
        "runtime": "python",
        "runtime_version": ">=3.11",
        "inputs": (
            SecretInput(TOKEN, EnvironmentBinding("GITHUB_TOKEN")),
            ConfigInput(ORG, EnvironmentBinding("GITHUB_ORG"), default="acme"),
        ),
        "dependencies": RequirementsFile("requirements.txt"),
    }
    fields.update(overrides)
    return InstallDescription(**fields)  # type: ignore[arg-type]


def _facts(*installers: str) -> EnvironmentFacts:
    return EnvironmentFacts(
        "darwin",
        remediation_capabilities=tuple(
            RemediationCapability(RemediationCapabilityKind.PYTHON_INSTALLER, name)
            for name in (installers or ("pip",))
        ),
    )


def _sources() -> tuple[InputValueSource, ...]:
    return (
        SecretProviderReference(
            TOKEN, CredentialProviderRef("macos-keychain", "aart", "github-token")
        ),
        PersistedConfigValue(ORG, "acme"),
    )


def _plan(
    description: InstallDescription | None = None,
    *,
    resolved: object | None = None,
    **overrides: object,
):
    fields: dict[str, object] = {
        "root": ROOT,
        "payload_source": PAYLOAD_SOURCE,
        "sources": _sources(),
        "policy": EffectivePolicy(),
        "facts": _facts(),
        "base_interpreter": INTERPRETER,
        "targets": (mcp_target("tabnine", Scope.PROJECT),),
        "resolvers": (_Keychain(),),
    }
    fields.update(overrides)
    return plan_artifact_installation(
        _resolved() if resolved is None else resolved,  # type: ignore[arg-type]
        description or _description(),
        **fields,  # type: ignore[arg-type]
    )


def _reason(result) -> str:
    return result.diagnostics[0].message


def _capabilities() -> tuple[RemediationCapability, ...]:
    return (
        RemediationCapability(RemediationCapabilityKind.PYTHON_INSTALLER, "pip"),
        RemediationCapability(RemediationCapabilityKind.CREDENTIAL_PROVIDER, "macos-keychain"),
        RemediationCapability(RemediationCapabilityKind.HARNESS_CONFIGURATION, "tabnine"),
    )


@dataclass(frozen=True, slots=True)
class _Inspector:
    """A machine with a usable Python and no opinion about anything else.

    Saying Unknown rather than Unavailable for the rest is the point: a credential this inspector
    cannot see is not a credential that is absent, and both lead to the same offer.
    """

    remediation_capabilities: tuple[RemediationCapability, ...] = ()

    def inspect(self, requirements) -> Ok:
        facts = tuple(
            EnvironmentFact(item.id, FactState.AVAILABLE, "3.11.9")
            if isinstance(item, RuntimeRequirement)
            else EnvironmentFact(item.id, FactState.UNKNOWN)
            for item in requirements
        )
        return Ok(EnvironmentFacts("darwin", facts, self.remediation_capabilities))


def _selection(planned) -> ResolvedSelection:
    coordinate = planned.coordinate
    return ResolvedSelection(
        ArtifactSelection(
            (
                ArtifactRequest(
                    coordinate.artifact,
                    VersionConstraint(coordinate.version or "*"),
                    coordinate.source,
                ),
            )
        ),
        (planned.artifact,),
    )


def _intent(planned) -> ArtifactInstallIntent:
    return ArtifactInstallIntent(
        planned.artifact,
        planned.requirements,
        (),
        runtime=planned.runtime,
        transport=planned.contract.transport.value,
    )


class DeclaredRequirementsTest(unittest.TestCase):
    def test_every_declaration_becomes_a_requirement_somebody_can_check(self) -> None:
        requirements = requirements_for(
            _description(), targets=(mcp_target("tabnine", Scope.PROJECT),)
        )

        self.assertIn(RuntimeRequirement.__name__, [type(item).__name__ for item in requirements])
        self.assertEqual(
            {type(item).__name__ for item in requirements},
            {
                "RuntimeRequirement",
                "PythonPackageRequirement",
                "CredentialRequirement",
                "HarnessRequirement",
            },
        )

    def test_the_runtime_requirement_carries_the_declared_constraint(self) -> None:
        runtime = next(
            item
            for item in requirements_for(_description())
            if isinstance(item, RuntimeRequirement)
        )

        self.assertEqual((runtime.runtime, runtime.constraint), ("python", ">=3.11"))

    def test_a_runtime_declared_without_a_version_is_unconstrained_not_invented(self) -> None:
        runtime = next(
            item
            for item in requirements_for(_description(runtime_version=None))
            if isinstance(item, RuntimeRequirement)
        )

        self.assertEqual(runtime.constraint, "*")

    def test_the_package_requirement_names_the_descriptor_and_the_lock_format(self) -> None:
        described = _description(dependencies=PyProjectSpec("pyproject.toml", "uv.lock", "uv"))

        packages = next(
            item
            for item in requirements_for(described)
            if isinstance(item, PythonPackageRequirement)
        )

        self.assertEqual(packages.descriptor, "pyproject")
        self.assertEqual(packages.path, "pyproject.toml")
        self.assertEqual(packages.lock_format, "uv")

    def test_only_a_secret_input_becomes_a_credential_requirement(self) -> None:
        credentials = [
            item
            for item in requirements_for(_description())
            if isinstance(item, CredentialRequirement)
        ]

        self.assertEqual([str(item.id) for item in credentials], ["github-token"])

    def test_an_optional_secret_is_a_requirement_that_says_it_is_optional(self) -> None:
        described = _description(
            inputs=(SecretInput(TOKEN, EnvironmentBinding("GITHUB_TOKEN"), required=False),)
        )

        credential = next(
            item for item in requirements_for(described) if isinstance(item, CredentialRequirement)
        )

        self.assertFalse(credential.required)

    def test_a_harness_requirement_exists_only_for_the_harnesses_asked_for(self) -> None:
        requirements = requirements_for(_description())

        self.assertEqual(
            [item for item in requirements if isinstance(item, HarnessRequirement)], []
        )

    def test_an_artifact_that_declares_nothing_requires_nothing(self) -> None:
        self.assertEqual(requirements_for(InstallDescription()), ())


class PlannedFromDescriptionTest(unittest.TestCase):
    def test_a_described_artifact_becomes_an_installation_this_machine_could_perform(self) -> None:
        planned = _plan()

        self.assertIsInstance(planned, Ok)
        installation = planned.value
        self.assertEqual(installation.environment.root, ROOT)
        self.assertEqual(installation.payload_source, PAYLOAD_SOURCE)
        self.assertEqual(installation.base_interpreter, INTERPRETER)
        self.assertEqual(installation.runtime, "python")
        self.assertEqual(
            installation.dependencies,
            (f"{ROOT}/payload/requirements.txt", "requirements", "pip"),
        )
        self.assertEqual(installation.artifact.ownership, (KIT,))

    def test_the_launcher_is_generated_into_the_root_the_artifact_owns(self) -> None:
        planned = _plan()

        assert isinstance(planned, Ok)
        self.assertTrue(planned.value.launcher.path.startswith(f"{ROOT}/"))

    def test_every_harness_asked_for_is_registered_against_the_generated_launcher(self) -> None:
        planned = _plan(targets=(mcp_target("tabnine", Scope.PROJECT),))

        assert isinstance(planned, Ok)
        registration = planned.value.registrations[0]
        self.assertEqual(registration.command, planned.value.launcher.command)
        self.assertEqual(registration.server, "github")
        self.assertEqual(registration.transport, Transport.STDIO)

    def test_the_plan_never_carries_the_secret_it_arranges_to_read(self) -> None:
        planned = _plan()

        assert isinstance(planned, Ok)
        self.assertNotIn("ghp_", planned.value.launcher.content)
        self.assertIn("security", planned.value.launcher.content)

    def test_the_requirements_travel_with_the_installation_they_belong_to(self) -> None:
        planned = _plan()

        assert isinstance(planned, Ok)
        self.assertIn("python-runtime", [str(item.id) for item in planned.value.requirements])
        self.assertIn("harness-tabnine", [str(item.id) for item in planned.value.requirements])


class RefusedInstallationTest(unittest.TestCase):
    def test_an_artifact_with_nothing_to_start_is_refused_by_name(self) -> None:
        refused = _plan(
            _description(contract=None, runtime=None, runtime_version=None, dependencies=None)
        )

        self.assertIsInstance(refused, Err)
        self.assertEqual(refused.diagnostics[0].code, INSTALLATION_NOT_DESCRIBED)
        self.assertIn("does not declare how it starts", _reason(refused))

    def test_a_required_input_with_no_value_stops_the_plan(self) -> None:
        refused = _plan(sources=(PersistedConfigValue(ORG, "acme"),))

        self.assertIsInstance(refused, Err)
        self.assertIn("github-token", _reason(refused))

    def test_dependencies_with_no_interpreter_to_build_from_are_refused(self) -> None:
        refused = _plan(base_interpreter=None)

        self.assertIsInstance(refused, Err)
        self.assertIn("interpreter", _reason(refused))

    def test_a_platform_with_no_usable_installer_says_which_set_emptied(self) -> None:
        refused = _plan(
            _description(dependencies=PyProjectSpec("pyproject.toml", "uv.lock", "uv")),
            facts=_facts("pip"),
        )

        self.assertIsInstance(refused, Err)
        self.assertIn("available", _reason(refused))

    def test_a_binding_the_launcher_cannot_deliver_is_refused_here_too(self) -> None:
        from agent_artifacts.domain.inputs import StdinBinding

        refused = _plan(
            _description(inputs=(SecretInput(TOKEN, StdinBinding()),)), sources=_sources()[:1]
        )

        self.assertIsInstance(refused, Err)
        self.assertIn("stdin", _reason(refused))


class OfferedRemediationTest(unittest.TestCase):
    """What a person is offered has to be what the plan will then accept."""

    def _inspected(self, planned, capabilities):
        inspected = inspect_requirements(planned.requirements, _Inspector(capabilities))
        assert isinstance(inspected, Ok), getattr(inspected, "diagnostics", ())
        return inspected.value

    def test_a_machine_that_can_fix_something_is_offered_that_fix(self) -> None:
        planned = _plan()
        assert isinstance(planned, Ok)
        facts = self._inspected(planned.value, _capabilities())

        offered = installation_remediations((planned.value,), facts, EffectivePolicy())

        assert isinstance(offered, Ok)
        self.assertEqual(
            sorted(str(item.remediation.requirement) for item in offered.value),
            ["github-token", "harness-tabnine", "python-packages"],
        )

    def test_a_machine_that_can_fix_nothing_offers_nothing(self) -> None:
        planned = _plan()
        assert isinstance(planned, Ok)
        facts = self._inspected(planned.value, ())

        offered = installation_remediations((planned.value,), facts, EffectivePolicy())

        assert isinstance(offered, Ok)
        self.assertEqual(offered.value, ())

    def test_every_offered_remediation_is_one_the_plan_accepts(self) -> None:
        planned = _plan()
        assert isinstance(planned, Ok)
        facts = self._inspected(planned.value, _capabilities())
        offered = installation_remediations((planned.value,), facts, EffectivePolicy())
        assert isinstance(offered, Ok)

        prepared = prepare_install_plan(
            _selection(planned.value),
            (_intent(planned.value),),
            facts,
            EffectivePolicy(),
            selected_remediations=tuple(item.remediation for item in offered.value),
        )

        self.assertIsInstance(prepared, Ok, getattr(prepared, "diagnostics", ()))


if __name__ == "__main__":
    unittest.main()
