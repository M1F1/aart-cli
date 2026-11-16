"""§216: doctor shows pip and uv as an install runs them, and a failed install names the cause.

The pure claims are universal -- every reported setting is one the person set and aart-cli drops,
every reported failure line is a line the installer printed -- so they are stated over generated
input. The interpreter claims use a recording runner: what matters is which commands run with
which interpreter, and that nothing reads the person's shell except for variable names.
"""

from __future__ import annotations

import os
import string
import unittest
from collections.abc import Mapping

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.consumer_views import (
    LifecycleStepOutcomeView,
    PresentationProfile,
    ReceiptArtifactView,
)
from aart_cli.application.python_installers import (
    IndexCheck,
    InstallerFailure,
    InstallerFailureKind,
    PythonInstallersReadiness,
    ignored_installer_settings,
    installer_failure,
    is_installer_setting,
    python_installer_lines,
    python_installers_to_data,
)
from aart_cli.domain.effects import InstallPythonDependencies
from aart_cli.domain.python_runtime import ArtifactEnvironment
from aart_cli.domain.result import Err
from aart_cli.io.python_installers import read_python_installers
from aart_cli.io.python_runtime import LocalPythonRuntime, ProcessOutcome, installer_environment
from aart_cli.redaction import redact_text
from aart_cli.tui_consumer import PYTHON_INSTALLER_HINT, _transaction_member
from tests.credential_fixtures import credential_url

# What pip prints when a TLS-intercepting proxy is not trusted: the cause in the retries, the
# consequence last. Reporting the last line is what sent people looking at the package.
PIP_CERTIFICATE_OUTPUT = """\
WARNING: Retrying (Retry(total=4, connect=None, read=None, redirect=None, status=None)) after \
connection broken by 'SSLError(SSLCertVerificationError(1, '[SSL: CERTIFICATE_VERIFY_FAILED] \
certificate verify failed: unable to get local issuer certificate (_ssl.c:1006)'))': /simple/mcp/
ERROR: Could not find a version that satisfies the requirement mcp<2.0.0,>=1.0.0 (from versions: none)
ERROR: No matching distribution found for mcp<2.0.0,>=1.0.0
"""
UV_CERTIFICATE_OUTPUT = """\
error: Request failed after 3 retries
  Caused by: Failed to fetch: `https://pypi.org/simple/mcp/`
  Caused by: error sending request for url (https://pypi.org/simple/mcp/)
  Caused by: invalid peer certificate: UnknownIssuer
"""

_names = st.text(alphabet=string.ascii_letters + string.digits + "_", min_size=1, max_size=24)
_lines = st.text(alphabet=string.ascii_letters + string.digits + " :'()[]_./-", max_size=60)


class IgnoredSettingsTest(unittest.TestCase):
    def test_the_settings_the_reported_case_relied_on_are_reported_and_others_are_not(
        self,
    ) -> None:
        shell = {
            "PIP_INDEX_URL": credential_url("mirror", "/simple", held="token"),
            "https_proxy": "http://proxy:3128",
            "REQUESTS_CA_BUNDLE": "/etc/ca.pem",
            "UV_NATIVE_TLS": "1",
            "HOME": "/home/dev",
            "EDITOR": "vi",
        }

        self.assertEqual(
            ignored_installer_settings(shell, installer_environment(shell)),
            ("PIP_INDEX_URL", "REQUESTS_CA_BUNDLE", "UV_NATIVE_TLS", "https_proxy"),
        )

    @given(st.sets(_names), st.sets(_names))
    def test_a_reported_setting_is_one_the_person_set_and_aart_cli_does_not_pass(
        self, present: set[str], passed: set[str]
    ) -> None:
        reported = ignored_installer_settings(present, passed)

        self.assertEqual(list(reported), sorted(set(reported)))
        for name in reported:
            self.assertIn(name, present)
            self.assertNotIn(name, passed)
            self.assertTrue(is_installer_setting(name))
        for name in present - passed:
            if is_installer_setting(name):
                self.assertIn(name, reported)

    @given(st.dictionaries(_names, st.text(max_size=20)))
    def test_pip_and_uv_get_a_fixed_few_variables_and_never_one_that_moves_an_install(
        self, shell: dict[str, str]
    ) -> None:
        moving = {"PIP_TARGET": "/", "PIP_PREFIX": "/usr", "PIP_USER": "1", "PIP_SRC": "/tmp"}
        environment = installer_environment({**shell, **moving, "XDG_CONFIG_HOME": "/cfg"})

        self.assertLessEqual(
            set(environment),
            {
                "HOME",
                "PATH",
                "SYSTEMROOT",
                "TMPDIR",
                "XDG_CONFIG_HOME",
                "LC_ALL",
                "PYTHONNOUSERSITE",
                "PIP_DISABLE_PIP_VERSION_CHECK",
            },
        )
        self.assertEqual(environment["XDG_CONFIG_HOME"], "/cfg")


class InstallerFailureTest(unittest.TestCase):
    def test_pip_names_the_certificate_not_the_missing_distribution(self) -> None:
        failure = installer_failure(PIP_CERTIFICATE_OUTPUT)

        self.assertIs(failure.kind, InstallerFailureKind.CERTIFICATE)
        self.assertIn("CERTIFICATE_VERIFY_FAILED", failure.line)

    def test_uv_names_the_certificate_under_caused_by(self) -> None:
        failure = installer_failure(UV_CERTIFICATE_OUTPUT)

        self.assertIs(failure.kind, InstallerFailureKind.CERTIFICATE)
        self.assertEqual(failure.line, "Caused by: invalid peer certificate: UnknownIssuer")

    def test_a_genuinely_missing_package_is_reported_as_missing(self) -> None:
        failure = installer_failure(
            "ERROR: Could not find a version that satisfies the requirement nope\n"
            "ERROR: No matching distribution found for nope\n"
        )

        self.assertIs(failure.kind, InstallerFailureKind.NOT_FOUND)

    def test_a_status_code_inside_a_version_is_not_an_access_failure(self) -> None:
        failure = installer_failure("Collecting thing==1.403.0\nERROR: build failed\n")

        self.assertIs(failure.kind, InstallerFailureKind.OTHER)
        self.assertEqual(failure.line, "ERROR: build failed")

    def test_credentials_in_the_line_are_redacted(self) -> None:
        failure = installer_failure(
            "ProxyError('Cannot connect to proxy', "
            + credential_url("proxy.corp:8080", user="alice", held="s3cret")
            + ")"
        )

        self.assertIs(failure.kind, InstallerFailureKind.PROXY)
        self.assertNotIn("s3cret", failure.line)

    @given(st.lists(_lines, max_size=12))
    def test_the_reported_line_is_always_one_the_installer_printed(self, lines: list[str]) -> None:
        failure = installer_failure("\n".join(lines))

        printed = {redact_text(line.strip()) for line in lines if line.strip()}
        if printed:
            self.assertIn(failure.line, printed)
        else:
            self.assertEqual(failure.line, "(no output)")

    @given(st.lists(_lines, max_size=6), st.lists(_lines, max_size=6))
    def test_a_cause_anywhere_wins_over_the_consequence_after_it(
        self, before: list[str], after: list[str]
    ) -> None:
        output = "\n".join(
            [
                *before,
                "Caused by: invalid peer certificate: UnknownIssuer",
                *after,
                "ERROR: No matching distribution found for mcp",
            ]
        )

        self.assertIs(installer_failure(output).kind, InstallerFailureKind.CERTIFICATE)


class _Runner:
    """Answers each probe by its first distinctive argument and records what ran."""

    def __init__(self, answers: Mapping[str, ProcessOutcome]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv, *, timeout, environment=None):  # noqa: ANN001
        self.calls.append(argv)
        for marker, outcome in self.answers.items():
            if marker in argv:
                return outcome
        return ProcessOutcome(0)


_HEALTHY = {
    "-c": ProcessOutcome(0, "pip\n24.2\n"),
    "config": ProcessOutcome(
        0,
        f"global.index-url='{credential_url('mirror.corp', '/simple', held='token')}'\n"
        ":env:.disable-pip-version-check='1'\n",
    ),
    "--version": ProcessOutcome(0, "uv 0.12.5 (Homebrew)\n"),
}


class ReadPythonInstallersTest(unittest.TestCase):
    def test_without_the_index_check_nothing_is_fetched_and_no_environment_is_built(self) -> None:
        runner = _Runner(_HEALTHY)

        readiness = read_python_installers(
            interpreter="/opt/python",
            environ={"PIP_INDEX_URL": credential_url("mirror", "/simple", held="token")},
            run=runner,
            locate=lambda name: "/usr/bin/uv",
        )

        self.assertEqual(readiness.environment_pip, "24.2")
        self.assertEqual(readiness.uv, "0.12.5")
        self.assertEqual(readiness.ignored_settings, ("PIP_INDEX_URL",))
        self.assertEqual(
            readiness.pip_configuration,
            ("global.index-url='https://[redacted]@mirror.corp/simple'",),
        )
        self.assertIsNone(readiness.pip_index)
        self.assertFalse(any("venv" in argv or "index" in argv for argv in runner.calls))
        self.assertTrue(all(argv[0] in {"/opt/python", "uv"} for argv in runner.calls))
        self.assertNotIn("token", str(python_installers_to_data(readiness)))

    def test_the_index_check_runs_the_pip_of_a_fresh_environment_from_the_same_interpreter(
        self,
    ) -> None:
        runner = _Runner(_HEALTHY)

        readiness = read_python_installers(
            interpreter="/opt/python",
            environ={},
            check_index=True,
            run=runner,
            locate=lambda name: "/usr/bin/uv",
        )

        created = next(argv for argv in runner.calls if "venv" in argv)
        self.assertEqual(created[:3], ("/opt/python", "-m", "venv"))
        environment = created[3]
        pip = next(argv for argv in runner.calls if "index" in argv)
        self.assertEqual(pip[0], f"{environment}/bin/python")
        uv = next(argv for argv in runner.calls if "--dry-run" in argv)
        self.assertIn(f"{environment}/bin/python", uv)
        self.assertEqual(readiness.pip_index, IndexCheck(True))
        self.assertEqual(readiness.uv_index, IndexCheck(True))
        self.assertFalse(os.path.exists(environment), "the throwaway environment is removed")

    def test_a_failing_index_is_attention_and_carries_the_cause(self) -> None:
        runner = _Runner({**_HEALTHY, "index": ProcessOutcome(1, "", PIP_CERTIFICATE_OUTPUT)})

        readiness = read_python_installers(
            interpreter="/opt/python",
            environ={},
            check_index=True,
            run=runner,
            locate=lambda name: None,
        )

        assert readiness.pip_index is not None and readiness.pip_index.failure is not None
        self.assertIs(readiness.pip_index.failure.kind, InstallerFailureKind.CERTIFICATE)
        self.assertIsNone(readiness.uv)
        self.assertIsNone(readiness.uv_index)
        self.assertTrue(readiness.needs_attention)
        text = "\n".join(python_installer_lines(readiness))
        self.assertIn("CERTIFICATE_VERIFY_FAILED", text)
        self.assertIn("cert = <path>", text)

    def test_an_interpreter_whose_new_environments_get_no_pip_needs_attention(self) -> None:
        runner = _Runner({**_HEALTHY, "-c": ProcessOutcome(0, "pip\n")})

        readiness = read_python_installers(
            interpreter="/opt/python", environ={}, run=runner, locate=lambda name: None
        )

        self.assertIsNone(readiness.environment_pip)
        self.assertTrue(readiness.needs_attention)

    def test_a_healthy_machine_without_the_check_needs_no_attention(self) -> None:
        readiness = read_python_installers(
            interpreter="/opt/python", environ={}, run=_Runner(_HEALTHY), locate=lambda name: None
        )

        self.assertFalse(readiness.needs_attention)
        self.assertIn("aart-cli doctor --check-index", "\n".join(python_installer_lines(readiness)))


class ReadinessInvariantsTest(unittest.TestCase):
    def test_an_index_check_fails_exactly_when_it_carries_a_failure(self) -> None:
        failure = InstallerFailure(InstallerFailureKind.NETWORK, "Connection refused")
        with self.assertRaises(ValueError):
            IndexCheck(True, failure)
        with self.assertRaises(ValueError):
            IndexCheck(False)

    def test_only_installer_settings_can_be_reported_as_ignored(self) -> None:
        with self.assertRaises(ValueError):
            PythonInstallersReadiness(
                "/opt/python", True, "24.2", None, ignored_settings=("AWS_KEY",)
            )


class InstallFailureReasonTest(unittest.TestCase):
    def test_a_failed_dependency_install_names_the_cause_not_the_last_line(self) -> None:
        environment = ArtifactEnvironment("airflow", "/home/dev/.aart/mcp/airflow")
        runtime = LocalPythonRuntime(
            environment,
            run=lambda argv, *, timeout, environment=None: ProcessOutcome(
                1, "", PIP_CERTIFICATE_OUTPUT
            ),
        )

        result = runtime.install_dependencies(
            InstallPythonDependencies(
                environment.environment,
                environment.payload_path("requirements.txt"),
                "requirements",
                "pip",
            )
        )

        assert isinstance(result, Err), result
        self.assertIn("CERTIFICATE_VERIFY_FAILED", result.diagnostics[0].message)


class InstallFailureHintTest(unittest.TestCase):
    def _member(self, component: str) -> ReceiptArtifactView:
        return ReceiptArtifactView(
            "company/mcp/airflow",
            "failed",
            steps=(
                LifecycleStepOutcomeView("payload", "write", "applied", ""),
                LifecycleStepOutcomeView(component, "install", "failed", "pip failed"),
            ),
        )

    def test_a_failed_pip_step_points_at_doctor_in_the_ordinary_view(self) -> None:
        lines = _transaction_member(
            self._member("runtime-dependencies"), PresentationProfile.LESS_INFO
        )

        self.assertIn(f"    {PYTHON_INSTALLER_HINT}", lines)

    def test_a_failure_pip_did_not_cause_does_not_point_at_pip(self) -> None:
        lines = _transaction_member(self._member("configuration"), PresentationProfile.LESS_INFO)

        self.assertNotIn(f"    {PYTHON_INSTALLER_HINT}", lines)


if __name__ == "__main__":
    unittest.main()
