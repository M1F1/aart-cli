"""§217: which packages an MCP's environment must hold, and how their absence is judged.

The parser's claims are universal -- every plainly named requirement is found, nothing it cannot
read is reported as complete -- so they are stated over generated requirements files. The judging
claims are the four answers the observation can give.
"""

from __future__ import annotations

import os
import pathlib
import string
import sys
import tempfile
import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.installation_verification import InstallationObservation
from aart_cli.application.installed_state import (
    current_state_from_observation,
    desired_state_from_receipt,
)
from aart_cli.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    ObjectDigest,
    SourceAlias,
)
from aart_cli.domain.python_runtime import (
    missing_distributions,
    normalize_distribution,
    requirements_distributions,
)
from aart_cli.domain.receipts import (
    InstallationReceipt,
    installation_receipt_from_data,
    installation_receipt_to_data,
)
from aart_cli.domain.reconciliation import Component, ComponentId, ComponentState, compare_states
from aart_cli.domain.result import Ok
from aart_cli.io.runtime_projection import observe_installation

ROOT = "/home/dev/.claude/aart-cli/mcp/company/github"
DESCRIPTOR = f"{ROOT}/payload/requirements.txt"
COORDINATE = ArtifactCoordinate(SourceAlias("company"), ArtifactIdentity("mcp", "github"), "1.5.0")

_letters = string.ascii_letters + string.digits
_names = st.builds(
    lambda head, body, tail: head + body + tail,
    st.sampled_from(_letters),
    st.text(alphabet=_letters + "-_.", max_size=10),
    st.sampled_from(_letters),
)
_specifiers = st.sampled_from(("", "==1.0", ">=1.0,<2.0", "~=1.4", " [extra]>=2", "!=3"))


def _receipt(dependencies: tuple[str, str, str] | None = (DESCRIPTOR, "requirements", "pip")):
    return InstallationReceipt(
        "github",
        ROOT,
        f"{ROOT}/bin/launch",
        ObjectDigest("sha256", "a" * 64),
        f"{ROOT}/runtime/.venv/bin/python",
        base_interpreter="/usr/bin/python3",
        dependencies=dependencies,
    )


class RequirementsParserTest(unittest.TestCase):
    @given(st.lists(st.tuples(_names, _specifiers), max_size=8))
    def test_every_plainly_named_requirement_is_found(self, requirements) -> None:
        text = "\n".join(f"{name}{specifier}" for name, specifier in requirements)

        self.assertEqual(
            requirements_distributions(text),
            tuple(sorted({normalize_distribution(name) for name, _ in requirements})),
        )

    @given(
        st.lists(st.tuples(_names, _specifiers), max_size=6),
        st.sampled_from(
            ("-r other.txt", "-e .", "--editable ./pkg", "./local-package", "https://x/p.whl")
        ),
    )
    def test_a_file_it_cannot_read_in_full_is_never_reported_as_complete(
        self, requirements, unreadable: str
    ) -> None:
        lines = [f"{name}{specifier}" for name, specifier in requirements]

        self.assertIsNone(requirements_distributions("\n".join([*lines, unreadable])))

    @given(st.text(max_size=200))
    def test_any_text_gives_names_or_none_and_never_raises(self, text: str) -> None:
        found = requirements_distributions(text)

        if found is not None:
            self.assertEqual(list(found), sorted(set(found)))
            self.assertTrue(all(name == normalize_distribution(name) for name in found))

    def test_options_markers_hashes_and_references_are_read_as_pip_reads_them(self) -> None:
        text = (
            "--no-index\n--find-links /wheels\n-i https://mirror/simple\n"
            "mcp>=1.0.0,<2.0.0\n"
            "pywin32 ; sys_platform == 'win32'\n"
            "httpx --hash=sha256:aa \\\n    --hash=sha256:bb\n"
            "Zope.Interface  # pinned elsewhere\n"
            "tool @ https://example.invalid/tool-1.0-py3-none-any.whl\n"
        )

        self.assertEqual(
            requirements_distributions(text), ("httpx", "mcp", "tool", "zope-interface")
        )

    @given(st.sets(_names), st.sets(_names))
    def test_missing_is_what_is_declared_and_not_held(self, declared, installed) -> None:
        missing = missing_distributions(declared, installed)

        held = {normalize_distribution(name) for name in installed}
        self.assertEqual(set(missing), {normalize_distribution(name) for name in declared} - held)


class ReceiptDependenciesTest(unittest.TestCase):
    def test_the_dependencies_survive_being_written_and_read_back(self) -> None:
        receipt = _receipt()

        read = installation_receipt_from_data(installation_receipt_to_data(receipt))

        self.assertEqual(read, Ok(receipt))

    def test_a_receipt_without_dependencies_is_written_as_before(self) -> None:
        self.assertNotIn("dependencies", installation_receipt_to_data(_receipt(None)))

    def test_a_descriptor_outside_the_installation_is_refused(self) -> None:
        for descriptor in ("/etc/requirements.txt", f"{ROOT}/../other/requirements.txt"):
            with self.subTest(descriptor=descriptor), self.assertRaises(ValueError):
                _receipt((descriptor, "requirements", "pip"))


class DependenciesJudgedTest(unittest.TestCase):
    def _judged(self, observation: InstallationObservation):
        receipt = _receipt()
        desired = desired_state_from_receipt(
            COORDINATE,
            receipt,
            base_interpreter=receipt.base_interpreter,
            dependencies=receipt.dependencies,
        )
        current = current_state_from_observation(desired, receipt, observation)
        [state] = [
            item
            for item in current.components
            if item.id == ComponentId(Component.RUNTIME_DEPENDENCIES)
        ]
        drift = {item.component for item in compare_states(desired, current)}
        return state, ComponentId(Component.RUNTIME_DEPENDENCIES) in drift

    def test_a_missing_package_is_drift_a_repair_or_install_acts_on(self) -> None:
        state, drifted = self._judged(
            InstallationObservation(interpreter_present=True, missing_distributions=("mcp",))
        )

        self.assertIs(state.state, ComponentState.ABSENT)
        self.assertIn("mcp", state.detail)
        self.assertTrue(drifted)

    def test_every_package_present_is_matched(self) -> None:
        state, drifted = self._judged(
            InstallationObservation(interpreter_present=True, missing_distributions=())
        )

        self.assertIs(state.state, ComponentState.MATCHED)
        self.assertFalse(drifted)

    def test_an_unchecked_environment_says_it_was_not_checked(self) -> None:
        state, drifted = self._judged(InstallationObservation(interpreter_present=True))

        self.assertIs(state.state, ComponentState.MATCHED)
        self.assertIn("not checked", state.detail)
        self.assertFalse(drifted)

    def test_a_desired_state_from_a_receipt_with_dependencies_wants_them(self) -> None:
        receipt = _receipt()
        desired = desired_state_from_receipt(
            COORDINATE,
            receipt,
            base_interpreter=receipt.base_interpreter,
            dependencies=receipt.dependencies,
        )

        self.assertIn(
            ComponentId(Component.RUNTIME_DEPENDENCIES),
            {component.id for component in desired.components},
        )


class DistributionsObservedTest(unittest.TestCase):
    """What `observe_installation` reads from a real directory laid out as an environment."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name).resolve() / "github"
        environment = self.root / "runtime" / ".venv"
        self.site = environment / "lib" / "python3.11" / "site-packages"
        self.site.mkdir(parents=True)
        interpreter = environment / "bin" / "python"
        interpreter.parent.mkdir()
        interpreter.write_text("")
        os.chmod(interpreter, 0o755)
        (self.root / "payload").mkdir()

    def _holds(self, name: str) -> None:
        info = self.site / f"{name.replace('-', '_')}-1.0.dist-info"
        info.mkdir()
        (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: 1.0\n")

    def _missing(self, descriptor: str, text: str, kind: str):
        (self.root / "payload" / descriptor).write_text(text)
        receipt = InstallationReceipt(
            "github",
            str(self.root),
            f"{self.root}/bin/launch",
            ObjectDigest("sha256", "a" * 64),
            f"{self.root}/runtime/.venv/bin/python",
            base_interpreter="/usr/bin/python3",
            dependencies=(f"{self.root}/payload/{descriptor}", kind, "pip"),
        )
        return observe_installation(receipt).missing_distributions

    def test_a_requirements_file_is_compared_with_what_site_packages_holds(self) -> None:
        self._holds("Tiny_Dep")

        self.assertEqual(
            self._missing("requirements.txt", "tiny-dep==1.0\nmcp>=1\n", "requirements"),
            ("mcp",),
        )
        self._holds("mcp")
        self.assertEqual(
            self._missing("requirements.txt", "tiny-dep==1.0\nmcp>=1\n", "requirements"), ()
        )

    def test_a_requirements_file_it_cannot_read_in_full_is_not_checked(self) -> None:
        self.assertIsNone(self._missing("requirements.txt", "-r base.txt\n", "requirements"))

    @unittest.skipIf(sys.version_info < (3, 11), "Python 3.10 has no TOML reader")
    def test_a_pyproject_wants_its_project_and_its_dependencies(self) -> None:
        text = '[project]\nname = "github-mcp"\ndependencies = ["mcp>=1", "httpx"]\n'
        self._holds("mcp")

        self.assertEqual(
            self._missing("pyproject.toml", text, "pyproject"), ("github-mcp", "httpx")
        )

    @unittest.skipIf(sys.version_info < (3, 11), "Python 3.10 has no TOML reader")
    def test_a_pyproject_with_dynamic_dependencies_is_not_checked(self) -> None:
        text = '[project]\nname = "github-mcp"\ndynamic = ["dependencies"]\n'

        self.assertIsNone(self._missing("pyproject.toml", text, "pyproject"))

    def test_an_installation_without_a_recorded_descriptor_is_not_checked(self) -> None:
        receipt = _receipt(None)

        self.assertIsNone(observe_installation(receipt).missing_distributions)


if __name__ == "__main__":
    unittest.main()
