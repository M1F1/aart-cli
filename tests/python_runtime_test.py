"""CP-09 Python dependency specification, installer selection and environment ownership."""

from __future__ import annotations

import unittest

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts.application.python_environment import (
    NO_COMPATIBLE_INSTALLER,
    PYTHON_ENVIRONMENT_INVALID,
    plan_python_environment,
    select_python_installer,
)
from agent_artifacts.domain.effects import (
    CreatePythonEnvironment,
    InstallPythonDependencies,
    RiskClass,
)
from agent_artifacts.domain.inspection import (
    EnvironmentFacts,
    RemediationCapability,
    RemediationCapabilityKind,
)
from agent_artifacts.domain.policies import EffectivePolicy, PolicyOverlay, compose_policy
from agent_artifacts.domain.python_runtime import (
    ArtifactEnvironment,
    PyProjectSpec,
    PythonInstaller,
    RequirementsFile,
    compatible_installers,
    dependency_spec_to_data,
    spec_kind,
)
from agent_artifacts.domain.result import Err, Ok

BASE = "/usr/local/bin/python3.11"


def _facts(*installers: str) -> EnvironmentFacts:
    return EnvironmentFacts(
        "darwin",
        (),
        tuple(
            RemediationCapability(RemediationCapabilityKind.PYTHON_INSTALLER, name)
            for name in installers
        ),
    )


class DependencySpecificationTest(unittest.TestCase):
    def test_a_specification_names_no_installer(self) -> None:
        requirements = RequirementsFile("requirements.txt")
        project = PyProjectSpec("pyproject.toml")

        rendered = (dependency_spec_to_data(requirements), dependency_spec_to_data(project))

        self.assertEqual(spec_kind(requirements), "requirements")
        self.assertEqual(spec_kind(project), "pyproject")
        for data in rendered:
            self.assertNotIn("pip", str(data))
            self.assertNotIn("uv", str(data))
            self.assertNotIn("installer", data)

    def test_a_descriptor_path_cannot_leave_the_artifact_payload(self) -> None:
        for path in ("../secrets.txt", "/etc/passwd.txt", "a/../../b.txt", "", "a\nb.txt"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                RequirementsFile(path)

    def test_a_lock_and_its_format_are_declared_together_or_not_at_all(self) -> None:
        with self.assertRaises(ValueError):
            PyProjectSpec("pyproject.toml", lock="uv.lock")
        with self.assertRaises(ValueError):
            PyProjectSpec("pyproject.toml", lock_format="uv")
        self.assertEqual(
            PyProjectSpec("pyproject.toml", lock="uv.lock", lock_format="uv").lock_format, "uv"
        )

    def test_compatibility_is_a_property_of_the_specification_not_of_the_platform(self) -> None:
        both = frozenset({PythonInstaller.PIP, PythonInstaller.UV})
        self.assertEqual(compatible_installers(RequirementsFile("requirements.txt")), both)
        self.assertEqual(compatible_installers(PyProjectSpec("pyproject.toml")), both)
        # A lock is only meaningful to the resolver that wrote it.
        self.assertEqual(
            compatible_installers(PyProjectSpec("pyproject.toml", "uv.lock", "uv")),
            frozenset({PythonInstaller.UV}),
        )


class InstallerSelectionTest(unittest.TestCase):
    def test_selection_is_capability_and_policy_and_preference_in_that_order(self) -> None:
        spec = RequirementsFile("requirements.txt")

        available = select_python_installer(spec, _facts("pip", "uv"), EffectivePolicy())
        assert isinstance(available, Ok), available
        self.assertEqual(available.value, PythonInstaller.PIP)

        preferred = select_python_installer(
            spec, _facts("pip", "uv"), EffectivePolicy(), preferred=PythonInstaller.UV
        )
        assert isinstance(preferred, Ok), preferred
        self.assertEqual(preferred.value, PythonInstaller.UV)

        # A preference is not a permission: policy still decides.
        overruled = select_python_installer(
            spec,
            _facts("pip", "uv"),
            EffectivePolicy(allowed_python_installers=frozenset({"pip"})),
            preferred=PythonInstaller.UV,
        )
        assert isinstance(overruled, Ok), overruled
        self.assertEqual(overruled.value, PythonInstaller.PIP)

    def test_an_unavailable_installer_is_never_selected_however_preferred(self) -> None:
        result = select_python_installer(
            RequirementsFile("requirements.txt"),
            _facts("pip"),
            EffectivePolicy(),
            preferred=PythonInstaller.UV,
        )

        assert isinstance(result, Ok), result
        self.assertEqual(result.value, PythonInstaller.PIP)

    def test_an_empty_intersection_fails_closed_and_says_which_set_was_empty(self) -> None:
        spec = PyProjectSpec("pyproject.toml", "uv.lock", "uv")

        no_capability = select_python_installer(spec, _facts("pip"), EffectivePolicy())
        assert isinstance(no_capability, Err), no_capability
        self.assertEqual(no_capability.diagnostics[0].code, NO_COMPATIBLE_INSTALLER)

        no_policy = select_python_installer(
            RequirementsFile("requirements.txt"),
            _facts("pip", "uv"),
            EffectivePolicy(allowed_python_installers=frozenset()),
        )
        assert isinstance(no_policy, Err), no_policy
        self.assertEqual(no_policy.diagnostics[0].code, NO_COMPATIBLE_INSTALLER)

    def test_selection_does_not_depend_on_capability_ordering(self) -> None:
        spec = RequirementsFile("requirements.txt")
        forward = select_python_installer(spec, _facts("pip", "uv"), EffectivePolicy())
        backward = select_python_installer(spec, _facts("uv", "pip"), EffectivePolicy())

        assert isinstance(forward, Ok) and isinstance(backward, Ok)
        self.assertEqual(forward.value, backward.value)


class ArtifactEnvironmentTest(unittest.TestCase):
    def test_an_environment_belongs_to_exactly_one_artifact_and_derives_its_own_paths(self) -> None:
        environment = ArtifactEnvironment("github", "/home/dev/.aart/mcp/github")

        self.assertEqual(environment.environment, "/home/dev/.aart/mcp/github/runtime/.venv")
        self.assertEqual(
            environment.interpreter, "/home/dev/.aart/mcp/github/runtime/.venv/bin/python"
        )
        self.assertEqual(environment.payload, "/home/dev/.aart/mcp/github/payload")
        # Derived, not settable: an environment cannot be pointed at a global interpreter.
        with self.assertRaises(AttributeError):
            environment.interpreter = "/usr/bin/python3"  # type: ignore[misc]

    def test_an_environment_knows_what_it_owns(self) -> None:
        environment = ArtifactEnvironment("github", "/home/dev/.aart/mcp/github")

        self.assertTrue(environment.owns(environment.interpreter))
        self.assertTrue(environment.owns(environment.payload + "/server.py"))
        self.assertFalse(environment.owns("/usr/bin/python3"))
        self.assertFalse(environment.owns("/home/dev/.aart/mcp/github-other/x"))

    def test_a_root_that_could_escape_itself_is_refused(self) -> None:
        for root in ("", "  ", "/a/../b", "/a\nb", "relative/../../escape"):
            with self.subTest(root=root), self.assertRaises(ValueError):
                ArtifactEnvironment("github", root)


class EnvironmentPlanningTest(unittest.TestCase):
    def test_a_plan_records_the_interpreter_and_the_installer_it_was_approved_with(self) -> None:
        environment = ArtifactEnvironment("github", "/home/dev/.aart/mcp/github")

        planned = plan_python_environment(
            environment, RequirementsFile("requirements.txt"), PythonInstaller.UV, BASE
        )

        assert isinstance(planned, Ok), planned
        create, install = planned.value
        assert isinstance(create, CreatePythonEnvironment)
        assert isinstance(install, InstallPythonDependencies)
        self.assertEqual(create.destination, environment.environment)
        self.assertEqual(create.base_interpreter, BASE)
        self.assertEqual(install.environment, environment.environment)
        self.assertEqual(install.installer, "uv")
        self.assertEqual(install.descriptor, "/home/dev/.aart/mcp/github/payload/requirements.txt")

    def test_changing_the_installer_changes_the_plan_a_reviewer_approves(self) -> None:
        environment = ArtifactEnvironment("github", "/home/dev/.aart/mcp/github")
        spec = RequirementsFile("requirements.txt")

        with_pip = plan_python_environment(environment, spec, PythonInstaller.PIP, BASE)
        with_uv = plan_python_environment(environment, spec, PythonInstaller.UV, BASE)

        assert isinstance(with_pip, Ok) and isinstance(with_uv, Ok)
        self.assertNotEqual(with_pip.value, with_uv.value)

    def test_the_base_interpreter_may_not_be_the_environment_being_built(self) -> None:
        environment = ArtifactEnvironment("github", "/home/dev/.aart/mcp/github")

        result = plan_python_environment(
            environment,
            RequirementsFile("requirements.txt"),
            PythonInstaller.PIP,
            environment.interpreter,
        )

        assert isinstance(result, Err), result
        self.assertEqual(result.diagnostics[0].code, PYTHON_ENVIRONMENT_INVALID)

    def test_no_planned_effect_touches_anything_outside_the_artifact_root(self) -> None:
        environment = ArtifactEnvironment("github", "/home/dev/.aart/mcp/github")

        planned = plan_python_environment(
            environment, PyProjectSpec("pyproject.toml"), PythonInstaller.PIP, BASE
        )

        assert isinstance(planned, Ok), planned
        create, install = planned.value
        # The base interpreter is read, never written; every written path is owned.
        self.assertTrue(environment.owns(create.destination))
        self.assertTrue(environment.owns(install.environment))
        self.assertTrue(environment.owns(install.descriptor))
        self.assertFalse(environment.owns(create.base_interpreter))

    def test_environment_creation_and_dependency_installation_are_executable_install_risk(
        self,
    ) -> None:
        planned = plan_python_environment(
            ArtifactEnvironment("github", "/home/dev/.aart/mcp/github"),
            RequirementsFile("requirements.txt"),
            PythonInstaller.PIP,
            BASE,
        )

        assert isinstance(planned, Ok), planned
        for effect in planned.value:
            with self.subTest(effect=type(effect).__name__):
                self.assertEqual(effect.risk, RiskClass.EXECUTABLE_INSTALL)
                # Recreating an environment is how it is repaired; it is not reversible.
                self.assertTrue(effect.capabilities.independently_repairable)
                self.assertFalse(effect.capabilities.reversible)


class InstallerPolicyPropertyTest(unittest.TestCase):
    @given(
        parent=st.sets(st.sampled_from(("pip", "uv")), min_size=0, max_size=2),
        child=st.sets(st.sampled_from(("pip", "uv")), min_size=0, max_size=2),
    )
    def test_a_restrictive_overlay_can_never_add_an_installer(
        self, parent: set[str], child: set[str]
    ) -> None:
        base = EffectivePolicy(allowed_python_installers=frozenset(parent))
        composed = compose_policy(base, PolicyOverlay(allowed_python_installers=frozenset(child)))

        assert composed.allowed_python_installers is not None
        assert base.allowed_python_installers is not None
        self.assertLessEqual(composed.allowed_python_installers, base.allowed_python_installers)
        self.assertLessEqual(composed.allowed_python_installers, frozenset(child))

    @given(installers=st.sets(st.sampled_from(("pip", "uv")), min_size=1, max_size=2))
    def test_a_selected_installer_is_always_compatible_with_the_specification(
        self, installers: set[str]
    ) -> None:
        spec = PyProjectSpec("pyproject.toml", "uv.lock", "uv")
        result = select_python_installer(spec, _facts(*sorted(installers)), EffectivePolicy())

        if isinstance(result, Ok):
            self.assertIn(result.value, compatible_installers(spec))
            self.assertIn(result.value.value, installers)


if __name__ == "__main__":
    unittest.main()
