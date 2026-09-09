"""CP-09 environment and dependency interpreters against real venvs and real installers.

Nothing here reaches the network. The package installed is a wheel this test builds itself, so the
proof that a dependency lands in the artifact-owned environment -- and nowhere else -- is exact and
does not depend on an index being reachable.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from agent_artifacts.application.python_environment import (
    plan_python_environment,
    select_python_installer,
)
from agent_artifacts.domain.effects import CreatePythonEnvironment, InstallPythonDependencies
from agent_artifacts.domain.inspection import EnvironmentFacts, RemediationCapabilityKind
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.python_runtime import (
    ArtifactEnvironment,
    PyProjectSpec,
    PythonInstaller,
    RequirementsFile,
)
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.python_runtime import (
    PYTHON_RUNTIME_REFUSED,
    PYTHON_RUNTIME_UNSUPPORTED,
    LocalPythonRuntime,
    ProcessOutcome,
    observe_python_installers,
)

PACKAGE = "aart_probe_package"
VERSION = "1.0.0"


def _build_wheel(directory: Path) -> Path:
    """A minimal valid pure-Python wheel, so an offline install has something real to install."""

    dist = f"{PACKAGE}-{VERSION}.dist-info"
    files = {
        f"{PACKAGE}/__init__.py": "MARKER = 'artifact-owned environment'\n",
        f"{dist}/METADATA": f"Metadata-Version: 2.1\nName: {PACKAGE}\nVersion: {VERSION}\n\n",
        f"{dist}/WHEEL": (
            "Wheel-Version: 1.0\nGenerator: aart-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        ),
    }
    files[f"{dist}/RECORD"] = "".join(f"{name},,\n" for name in files) + f"{dist}/RECORD,,\n"
    wheel = directory / f"{PACKAGE}-{VERSION}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, body in files.items():
            archive.writestr(name, body)
    return wheel


class ScriptedRunner:
    def __init__(self, outcome: ProcessOutcome | None = None) -> None:
        self.outcome = outcome or ProcessOutcome(0)
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv: tuple[str, ...], *, timeout: float) -> ProcessOutcome:
        self.calls.append(argv)
        return self.outcome


class RuntimeRefusalTest(unittest.TestCase):
    """What the interpreter refuses before starting a process, which is the isolation boundary."""

    def setUp(self) -> None:
        self.environment = ArtifactEnvironment("github", "/opt/aart/mcp/github")
        self.runner = ScriptedRunner()
        self.runtime = LocalPythonRuntime(self.environment, run=self.runner)

    def test_it_refuses_a_destination_outside_the_artifact_root(self) -> None:
        result = self.runtime.create_environment(
            CreatePythonEnvironment("github", "/usr/local/lib/python3.11", sys.executable)
        )

        assert isinstance(result, Err), result
        self.assertEqual(result.diagnostics[0].code, PYTHON_RUNTIME_REFUSED)
        self.assertEqual(self.runner.calls, [])

    def test_it_refuses_an_effect_belonging_to_another_artifact(self) -> None:
        result = self.runtime.create_environment(
            CreatePythonEnvironment("jira", self.environment.environment, sys.executable)
        )

        assert isinstance(result, Err), result
        self.assertEqual(result.diagnostics[0].code, PYTHON_RUNTIME_REFUSED)
        self.assertEqual(self.runner.calls, [])

    def test_it_refuses_to_build_an_environment_out_of_itself(self) -> None:
        result = self.runtime.create_environment(
            CreatePythonEnvironment(
                "github", self.environment.environment, self.environment.interpreter
            )
        )

        assert isinstance(result, Err), result
        self.assertEqual(result.diagnostics[0].code, PYTHON_RUNTIME_REFUSED)
        self.assertEqual(self.runner.calls, [])

    def test_it_refuses_a_descriptor_outside_the_artifact_root(self) -> None:
        result = self.runtime.install_dependencies(
            InstallPythonDependencies(
                self.environment.environment, "/etc/requirements.txt", "requirements", "pip"
            )
        )

        assert isinstance(result, Err), result
        self.assertEqual(result.diagnostics[0].code, PYTHON_RUNTIME_REFUSED)
        self.assertEqual(self.runner.calls, [])

    def test_it_refuses_a_locked_project_rather_than_quietly_ignoring_the_lock(self) -> None:
        result = self.runtime.install_dependencies(
            InstallPythonDependencies(
                self.environment.environment,
                self.environment.payload_path("pyproject.toml"),
                "locked-project",
                "uv",
            )
        )

        assert isinstance(result, Err), result
        self.assertEqual(result.diagnostics[0].code, PYTHON_RUNTIME_UNSUPPORTED)
        self.assertEqual(self.runner.calls, [])

    def test_the_argv_it_builds_names_the_artifact_interpreter_not_the_ambient_one(self) -> None:
        self.runtime.install_dependencies(
            InstallPythonDependencies(
                self.environment.environment,
                self.environment.payload_path("requirements.txt"),
                "requirements",
                "pip",
            )
        )

        argv = self.runner.calls[0]
        self.assertEqual(argv[0], f"{self.environment.environment}/bin/python")
        self.assertEqual(argv[1:4], ("-m", "pip", "install"))
        self.assertIn(self.environment.payload_path("requirements.txt"), argv)


class RealEnvironmentTest(unittest.TestCase):
    """The interpreters against real `venv`, real `pip` and, when present, real `uv`."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "mcp" / "probe"
        (self.root / "payload").mkdir(parents=True)
        self.environment = ArtifactEnvironment("probe", str(self.root))
        self.runtime = LocalPythonRuntime(self.environment, timeout_seconds=300.0, offline=True)
        self.wheel = _build_wheel(Path(self.directory.name))
        self.system_prefix = sys.prefix
        self.system_path = tuple(sys.path)

    def _requirements(self, name: str = "requirements.txt") -> str:
        descriptor = self.root / "payload" / name
        descriptor.write_text(f"{self.wheel}\n", encoding="utf-8")
        return str(descriptor)

    def _create(self) -> None:
        created = self.runtime.create_environment(
            CreatePythonEnvironment("probe", self.environment.environment, sys.executable)
        )
        assert isinstance(created, Ok), created
        self.assertEqual(created.value.interpreter, self.environment.interpreter)
        self.assertTrue(Path(self.environment.interpreter).exists())

    def _sees(self, interpreter: str) -> bool:
        probe = subprocess.run(
            (
                interpreter,
                "-c",
                f"import importlib.util,sys;"
                f"sys.exit(0 if importlib.util.find_spec('{PACKAGE}') else 1)",
            ),
            capture_output=True,
            timeout=60.0,
            check=False,
        )
        return probe.returncode == 0

    def test_a_created_environment_is_the_artifact_s_own_and_not_the_system_one(self) -> None:
        self._create()

        reported = subprocess.run(
            (self.environment.interpreter, "-c", "import sys,json;print(json.dumps(sys.prefix))"),
            capture_output=True,
            text=True,
            timeout=60.0,
            check=True,
        )

        self.assertEqual(json.loads(reported.stdout), self.environment.environment)
        self.assertNotEqual(json.loads(reported.stdout), self.system_prefix)
        self.assertEqual(sys.prefix, self.system_prefix)
        self.assertEqual(tuple(sys.path), self.system_path)

    def test_pip_installs_into_the_artifact_environment_and_nowhere_else(self) -> None:
        self._create()
        self.assertFalse(self._sees(self.environment.interpreter))
        self.assertIsNone(importlib.util.find_spec(PACKAGE))

        installed = self.runtime.install_dependencies(
            InstallPythonDependencies(
                self.environment.environment, self._requirements(), "requirements", "pip"
            )
        )

        assert isinstance(installed, Ok), installed
        self.assertTrue(self._sees(self.environment.interpreter))
        # The system interpreter never gained it, in this process or in a fresh one.
        self.assertIsNone(importlib.util.find_spec(PACKAGE))
        self.assertFalse(self._sees(sys.executable))

    @unittest.skipUnless(shutil.which("uv"), "uv is not installed here")
    def test_uv_installs_into_the_same_artifact_environment(self) -> None:
        self._create()

        installed = self.runtime.install_dependencies(
            InstallPythonDependencies(
                self.environment.environment, self._requirements(), "requirements", "uv"
            )
        )

        assert isinstance(installed, Ok), installed
        self.assertTrue(self._sees(self.environment.interpreter))
        self.assertFalse(self._sees(sys.executable))

    def test_two_artifacts_get_two_environments_that_cannot_see_each_other(self) -> None:
        self._create()
        installed = self.runtime.install_dependencies(
            InstallPythonDependencies(
                self.environment.environment, self._requirements(), "requirements", "pip"
            )
        )
        assert isinstance(installed, Ok), installed

        other_root = Path(self.directory.name) / "mcp" / "other"
        (other_root / "payload").mkdir(parents=True)
        other = ArtifactEnvironment("other", str(other_root))
        other_runtime = LocalPythonRuntime(other, timeout_seconds=300.0, offline=True)
        created = other_runtime.create_environment(
            CreatePythonEnvironment("other", other.environment, sys.executable)
        )
        assert isinstance(created, Ok), created

        self.assertTrue(self._sees(self.environment.interpreter))
        self.assertFalse(self._sees(other.interpreter))

    def test_a_failing_install_reports_the_failure_instead_of_claiming_success(self) -> None:
        self._create()
        descriptor = self.root / "payload" / "requirements.txt"
        descriptor.write_text("aart-package-that-does-not-exist==9.9.9\n", encoding="utf-8")

        result = self.runtime.install_dependencies(
            InstallPythonDependencies(
                self.environment.environment, str(descriptor), "requirements", "pip"
            )
        )

        assert isinstance(result, Err), result
        self.assertIn("dependency installation failed", result.diagnostics[0].message)

    def test_the_observed_capabilities_match_what_this_machine_can_really_run(self) -> None:
        self._create()

        capabilities = observe_python_installers(interpreter=self.environment.interpreter)

        names = {item.name for item in capabilities}
        for item in capabilities:
            self.assertIs(item.kind, RemediationCapabilityKind.PYTHON_INSTALLER)
        self.assertIn("pip", names)  # `venv` provides it, which is why the environment is created.
        self.assertEqual("uv" in names, shutil.which("uv") is not None)

    def test_planning_and_execution_agree_on_every_path(self) -> None:
        facts = EnvironmentFacts("darwin", (), observe_python_installers())
        selected = select_python_installer(
            RequirementsFile("requirements.txt"), facts, EffectivePolicy()
        )
        assert isinstance(selected, Ok), selected

        planned = plan_python_environment(
            self.environment,
            RequirementsFile("requirements.txt"),
            selected.value,
            sys.executable,
        )
        assert isinstance(planned, Ok), planned
        create, install = planned.value
        self._requirements()

        created = self.runtime.create_environment(create)
        assert isinstance(created, Ok), created
        installed = self.runtime.install_dependencies(install)

        assert isinstance(installed, Ok), installed
        self.assertTrue(self._sees(self.environment.interpreter))
        self.assertEqual(selected.value, PythonInstaller.PIP)

    def test_a_pyproject_plan_points_the_installer_at_the_project_directory(self) -> None:
        planned = plan_python_environment(
            self.environment, PyProjectSpec("pyproject.toml"), PythonInstaller.PIP, sys.executable
        )

        assert isinstance(planned, Ok), planned
        _, install = planned.value
        self.assertEqual(install.descriptor_kind, "pyproject")
        self.assertEqual(install.descriptor, f"{self.environment.payload}/pyproject.toml")


if __name__ == "__main__":
    unittest.main()
