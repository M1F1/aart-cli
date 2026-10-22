"""§189, INV-290, D-471: a project locked with uv installs exactly its lock.

An Enterprise agent found that an artifact declaring `type: uv` validated and was then refused at
install ("installing a locked project with uv is not supported yet"), so the only way to ship it
was to drop the lock and let every install resolve different versions. The lock is now honoured:
`uv sync --frozen` installs what `uv.lock` pins, into the artifact's own environment.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aart_cli.domain.effects import CreatePythonEnvironment, InstallPythonDependencies
from aart_cli.domain.python_runtime import ArtifactEnvironment, PyProjectSpec
from aart_cli.domain.result import Err, Ok
from aart_cli.io.python_runtime import (
    PYTHON_RUNTIME_UNSUPPORTED,
    LocalPythonRuntime,
    ProcessOutcome,
)
from tests.python_environment_integration_test import PACKAGE, VERSION, _build_wheel


class _RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], dict[str, str]]] = []

    def __call__(self, argv, *, timeout, environment=None) -> ProcessOutcome:
        self.calls.append((argv, dict(environment or {})))
        return ProcessOutcome(0)


def _locked(environment: ArtifactEnvironment, installer: str = "uv") -> InstallPythonDependencies:
    return InstallPythonDependencies(
        environment.environment,
        environment.payload_path("server/pyproject.toml"),
        "locked-project",
        installer,
    )


class LockedProjectArgvTest(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = ArtifactEnvironment("github", "/opt/aart/mcp/github")
        self.runner = _RecordingRunner()

    def test_uv_syncs_the_frozen_lock_into_the_artifact_environment(self) -> None:
        for offline in (False, True):
            with self.subTest(offline=offline):
                self.runner.calls.clear()
                runtime = LocalPythonRuntime(
                    self.environment, run=self.runner, offline=offline, uv_executable="/bin/uv"
                )

                installed = runtime.install_dependencies(_locked(self.environment))

                assert isinstance(installed, Ok), installed
                ((argv, environment),) = self.runner.calls
                self.assertEqual(argv[:2], ("/bin/uv", "sync"))
                for flag in ("--frozen", "--no-dev", "--no-editable", "--no-python-downloads"):
                    self.assertIn(flag, argv)
                self.assertEqual(argv.count("--offline"), int(offline))
                self.assertEqual(
                    argv[argv.index("--project") + 1], self.environment.payload_path("server")
                )
                self.assertEqual(argv[argv.index("--python") + 1], self.environment.interpreter)
                # Without this uv makes `.venv` inside the payload and installs there.
                self.assertEqual(
                    environment, {"UV_PROJECT_ENVIRONMENT": self.environment.environment}
                )

    def test_a_lock_another_backend_cannot_read_is_refused_and_nothing_runs(self) -> None:
        runtime = LocalPythonRuntime(self.environment, run=self.runner)

        refused = runtime.install_dependencies(_locked(self.environment, "pip"))

        assert isinstance(refused, Err), refused
        self.assertEqual(refused.diagnostics[0].code, PYTHON_RUNTIME_UNSUPPORTED)
        self.assertEqual(self.runner.calls, [])


class LockPlacementTest(unittest.TestCase):
    def test_a_uv_lock_sits_beside_its_project_as_uv_lock(self) -> None:
        self.assertEqual(
            PyProjectSpec("server/pyproject.toml", "server/uv.lock", "uv").lock, "server/uv.lock"
        )
        for lock in ("locks/uv.lock", "server/requirements.lock", "uv.lock"):
            with self.subTest(lock=lock), self.assertRaisesRegex(ValueError, "beside"):
                PyProjectSpec("server/pyproject.toml", lock, "uv")


@unittest.skipUnless(shutil.which("uv"), "uv is not installed here")
class RealUvSyncTest(unittest.TestCase):
    """Real `uv lock` and `uv sync`, offline, against a wheel this test builds."""

    def test_the_locked_dependency_lands_in_the_artifact_environment_only(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            wheel = _build_wheel(directory)
            root = directory / "mcp" / "probe"
            project = root / "payload"
            project.mkdir(parents=True)
            (project / "pyproject.toml").write_text(
                "[project]\n"
                'name = "probe-server"\n'
                'version = "0.1.0"\n'
                f'requires-python = ">={sys.version_info.major}.{sys.version_info.minor}"\n'
                f'dependencies = ["{PACKAGE} @ {wheel.as_uri()}"]\n'
                "\n[tool.uv]\n"
                "package = false\n",
                encoding="utf-8",
            )
            subprocess.run(
                ("uv", "lock", "--offline", "--project", str(project)),
                check=True,
                capture_output=True,
                timeout=120,
                env={**os.environ, "UV_NO_CONFIG": "1"},
            )
            lock = (project / "uv.lock").read_bytes()
            environment = ArtifactEnvironment("probe", str(root))
            runtime = LocalPythonRuntime(environment, timeout_seconds=300.0, offline=True)
            created = runtime.create_environment(
                CreatePythonEnvironment("probe", environment.environment, sys.executable)
            )
            assert isinstance(created, Ok), created

            installed = runtime.install_dependencies(
                InstallPythonDependencies(
                    environment.environment,
                    environment.payload_path("pyproject.toml"),
                    "locked-project",
                    "uv",
                )
            )

            assert isinstance(installed, Ok), installed
            probe = subprocess.run(
                (
                    environment.interpreter,
                    "-c",
                    f"import importlib.metadata as m;print(m.version('{PACKAGE}'))",
                ),
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(probe.stdout.strip(), VERSION, probe.stderr)
            self.assertFalse((project / ".venv").exists())
            self.assertEqual((project / "uv.lock").read_bytes(), lock)


if __name__ == "__main__":
    unittest.main()
