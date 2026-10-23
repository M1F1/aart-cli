"""CP-39: a fork may label its wheel's version, so its builds never share a filename with PyPI's.

An Enterprise fork bakes its own default Registry into the wheel, so its `aart_cli-X.Y.Z` holds other
bytes than the public one. Once the public release is also on PyPI, an index group that proxies PyPI
lists both under one filename, and `publish-index` rightly refuses the fork's. A PEP 440 local label
(`X.Y.Z+corp`) gives the fork's wheel its own filename. `aart-cli==X.Y.Z` still matches it, and pip
prefers it over the public `X.Y.Z`.

The label changes the distribution's version only. `aart_cli.__version__`, and so `aart-cli
--version`, stays the tag's version: the Registry CI compares that against `.aart-cli-version`, and
a label there would fail every Registry that pinned the release.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import re
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

from hypothesis import given
from hypothesis import strategies as st
from packaging.version import InvalidVersion, Version

from aart_cli.commands.upgrade import plan_upgrade
from aart_cli.domain.result import Ok
from scripts import release_artifact

ROOT = pathlib.Path(__file__).resolve().parent.parent
VARIABLE = "AART_CLI_LOCAL_VERSION_LABEL"
PYPROJECT = """[build-system]
requires = ["poetry-core==2.4.0"]

[project]
name = "aart-cli"
version = "1.4.0"
dependencies = []

[tool.poetry]
packages = [{ include = "aart_cli" }]
"""


def _load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_aart_test_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _inject():
    return _load("inject_local_version")


def _version(text: str) -> str:
    match = re.search(r'(?m)^version = "([^"]+)"$', text)
    assert match is not None
    return match.group(1)


SEGMENT = st.one_of(
    st.integers(min_value=0, max_value=10**6).map(str),
    st.from_regex(r"[a-z0-9]{0,4}[a-z][a-z0-9]{0,4}", fullmatch=True),
)
LABELS = st.lists(SEGMENT, min_size=1, max_size=3).map(".".join)


class UnsetLabelsNothing(unittest.TestCase):
    def test_an_unset_variable_leaves_the_file_byte_for_byte(self) -> None:
        self.assertEqual(_inject().render(PYPROJECT, ""), PYPROJECT)

    def test_the_committed_pyproject_is_unchanged_when_unset(self) -> None:
        committed = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertEqual(
            _inject().render(committed, _inject().label_from("  \n", VARIABLE)), committed
        )


class ALabelReachesTheDistributionVersion(unittest.TestCase):
    def test_the_project_version_gains_the_label(self) -> None:
        self.assertEqual(_version(_inject().render(PYPROJECT, "corp")), "1.4.0+corp")

    def test_nothing_but_the_project_version_moves(self) -> None:
        rendered = _inject().render(PYPROJECT, "corp")
        self.assertEqual(rendered.replace("1.4.0+corp", "1.4.0"), PYPROJECT)

    def test_stamping_twice_is_stamping_once(self) -> None:
        once = _inject().render(PYPROJECT, "corp")
        self.assertEqual(_inject().render(once, "corp"), once)

    def test_surrounding_whitespace_is_the_shell_s_and_is_dropped(self) -> None:
        self.assertEqual(_inject().label_from("  corp\n", VARIABLE), "corp")

    def test_the_package_s_own_version_is_left_alone(self) -> None:
        # `aart-cli --version` is what the Registry CI compares with `.aart-cli-version`.
        self.assertEqual(_inject().TARGET, ROOT / "pyproject.toml")

    @given(LABELS)
    def test_every_accepted_label_is_a_pep_440_local_version_of_the_tag(self, label: str) -> None:
        version = Version(
            _version(_inject().render(PYPROJECT, _inject().label_from(label, VARIABLE)))
        )
        self.assertEqual((version.public, version.local), ("1.4.0", label))

    @given(LABELS)
    def test_pip_prefers_the_labelled_build_of_the_pinned_version(self, label: str) -> None:
        from packaging.specifiers import SpecifierSet

        candidates = (Version("1.4.0"), Version(f"1.4.0+{label}"))
        self.assertEqual(max(SpecifierSet("==1.4.0").filter(candidates)), candidates[1])


class AMalformedLabelFailsTheBuild(unittest.TestCase):
    def test_labels_outside_the_grammar_are_refused(self) -> None:
        for raw in (
            "Corp",
            "co-rp",
            "co_rp",
            "+corp",
            "corp.",
            ".corp",
            "co rp",
            "corp..x",
            "00",
            "corp.01",
        ):
            with self.subTest(label=raw), self.assertRaises(SystemExit):
                _inject().label_from(raw, VARIABLE)

    @given(st.text(min_size=1, max_size=12))
    def test_whatever_is_accepted_is_a_valid_local_version(self, raw: str) -> None:
        try:
            label = _inject().label_from(raw, VARIABLE)
        except SystemExit:
            return
        if not label:
            return
        try:
            version = Version(f"1.4.0+{label}")
        except InvalidVersion:
            self.fail(f"{raw!r} was accepted but is not a PEP 440 local label")
        # Equal as written: PEP 440 normalising the label would rename the file.
        self.assertEqual(str(version), f"1.4.0+{label}")

    def test_a_refused_label_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = pathlib.Path(raw) / "pyproject.toml"
            target.write_text(PYPROJECT, encoding="utf-8")
            with self.assertRaises(SystemExit):
                _inject().write(target, "Not-A-Label")
            self.assertEqual(target.read_text(encoding="utf-8"), PYPROJECT)

    def test_a_file_with_no_project_version_is_refused(self) -> None:
        with self.assertRaises(SystemExit):
            _inject().render('[project]\nname = "aart-cli"\n', "corp")


def _wheel(directory: pathlib.Path, version: str) -> pathlib.Path:
    path = directory / f"aart_cli-{version}-py3-none-any.whl"
    metadata = ["Metadata-Version: 2.3", "Name: aart-cli", f"Version: {version}", ""]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"aart_cli-{version}.dist-info/METADATA", "\n".join(metadata) + "\n")
    return path


class TheReleaseChecksTheLabelledWheel(unittest.TestCase):
    def test_a_labelled_wheel_passes_when_the_release_was_labelled(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            wheel = _wheel(pathlib.Path(raw), "1.4.0+corp")
            self.assertEqual(release_artifact.verify_artifact(wheel, "v1.4.0", label="corp"), ())

    def test_an_unlabelled_wheel_is_refused_when_the_release_was_labelled(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            wheel = _wheel(pathlib.Path(raw), "1.4.0")
            codes = {
                item.code
                for item in release_artifact.verify_artifact(wheel, "v1.4.0", label="corp")
            }
        self.assertEqual(codes, {"artifact-filename-mismatch", "artifact-version-mismatch"})

    def test_a_labelled_wheel_is_refused_when_the_release_was_not(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            wheel = _wheel(pathlib.Path(raw), "1.4.0+corp")
            codes = {item.code for item in release_artifact.verify_artifact(wheel, "v1.4.0")}
        self.assertEqual(codes, {"artifact-filename-mismatch", "artifact-version-mismatch"})

    def test_the_installed_command_still_reports_the_tag_s_version(self) -> None:
        answers = {
            ("aart-cli", "--version"): (0, "aart-cli 1.4.0\n"),
            ("aart-cli", "--help"): (0, ""),
        }
        self.assertEqual(release_artifact.smoke("1.4.0", runner=answers.__getitem__), ())


class TheReceiptRecordsTheLabel(unittest.TestCase):
    def _field(self, value: str | None) -> object:
        release = _load("release")
        environment = dict(os.environ)
        environment.pop(VARIABLE, None)
        if value is not None:
            environment[VARIABLE] = value
        with mock.patch.dict(os.environ, environment, clear=True):
            return release.local_version_label_value()

    def test_an_unset_variable_records_nothing(self) -> None:
        self.assertIsNone(self._field(None))

    def test_the_label_the_build_used_is_recorded(self) -> None:
        self.assertEqual(self._field(" corp\n"), "corp")


class UpgradeTakesALabelledWheel(unittest.TestCase):
    def test_a_labelled_wheel_is_a_valid_local_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            wheel = pathlib.Path(raw, "aart_cli-1.4.0+corp-py3-none-any.whl")
            wheel.write_bytes(b"fixture")
            result = plan_upgrade(sys.executable, wheel=str(wheel), source_checkout=None)
        self.assertIsInstance(result, Ok)


if __name__ == "__main__":
    unittest.main()
