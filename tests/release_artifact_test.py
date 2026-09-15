"""INV-089, INV-097, INV-098, INV-099: the release run's subject is the artifact it publishes.

What the tag pipeline used to prove was that a version typed into a script matched a version
written into three files matched the tag somebody pushed.  None of that is a property of the
thing being shipped, and all of it was provable from the source tree alone -- which the pull
request had already proven.

These are the claims a pull request could not have made, because the wheel did not exist yet:
the archive's own metadata names the released identity, it declares no runtime dependency, and
the command inside it runs and agrees about what version it is.
"""

from __future__ import annotations

import pathlib
import tempfile
import unittest
import zipfile

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from scripts import release_artifact

# mutmut invokes the same pure property from a fresh executor for every mutant.  Hypothesis warns
# about that shape because stateful tests can become non-reproducible across executors; these
# properties carry no state, so the warning does not describe a possible failure here.
MUTATION_SETTINGS = settings(suppress_health_check=(HealthCheck.differing_executors,))


def _wheel(
    directory: pathlib.Path,
    *,
    version: str = "1.4.0",
    name: str = "aart-cli",
    filename: str | None = None,
    requires: tuple[str, ...] = (),
) -> pathlib.Path:
    path = directory / (filename or f"aart_cli-{version}-py3-none-any.whl")
    metadata = [
        "Metadata-Version: 2.3",
        f"Name: {name}",
        f"Version: {version}",
        *(f"Requires-Dist: {requirement}" for requirement in requires),
        "",
        "The package.",
    ]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"aart_cli-{version}.dist-info/METADATA", "\n".join(metadata) + "\n")
        archive.writestr("agent_artifacts/__init__.py", "")
    return path


def _diagnostic(
    diagnostics: tuple[release_artifact.ArtifactDiagnostic, ...], code: str
) -> release_artifact.ArtifactDiagnostic:
    found = [item for item in diagnostics if item.code == code]
    assert len(found) == 1
    item = found[0]
    assert item.check == "artifact"
    assert item.message
    return item


class ReleasedIdentityTest(unittest.TestCase):
    def test_a_wheel_whose_metadata_names_the_tag_passes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            wheel = _wheel(pathlib.Path(raw), version="1.4.0")
            self.assertEqual(release_artifact.verify_artifact(wheel, "v1.4.0"), ())

    def test_a_wheel_built_from_a_different_version_is_refused(self) -> None:
        """INV-099: the tag is the released identity; packaging consumes it, never invents one."""

        with tempfile.TemporaryDirectory() as raw:
            wheel = _wheel(pathlib.Path(raw), version="1.4.0")
            diagnostic = _diagnostic(
                release_artifact.verify_artifact(wheel, "v1.5.0"),
                "artifact-version-mismatch",
            )
            self.assertIn("v1.5.0", diagnostic.message)
            self.assertIn("1.4.0", diagnostic.message)

    def test_a_wheel_that_declares_a_runtime_dependency_is_refused(self) -> None:
        """Zero runtime dependencies is an architectural promise the *artifact* has to keep."""

        with tempfile.TemporaryDirectory() as raw:
            wheel = _wheel(pathlib.Path(raw), requires=("requests>=2", "rich>=13"))
            diagnostic = _diagnostic(
                release_artifact.verify_artifact(wheel, "v1.4.0"),
                "artifact-runtime-dependency",
            )
            self.assertEqual(diagnostic.message, "the wheel requires: requests>=2, rich>=13")

    def test_a_wheel_for_another_project_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            wheel = _wheel(pathlib.Path(raw), name="aart-cli-fork")
            diagnostic = _diagnostic(
                release_artifact.verify_artifact(wheel, "v1.4.0"),
                "artifact-name-unexpected",
            )
            self.assertIn("aart-cli-fork", diagnostic.message)

    def test_a_filename_that_disagrees_with_the_metadata_is_refused(self) -> None:
        """The two are written by different parts of the build, so they can disagree."""

        with tempfile.TemporaryDirectory() as raw:
            wheel = _wheel(
                pathlib.Path(raw), version="1.4.0", filename="aart_cli-1.4.1-py3-none-any.whl"
            )
            diagnostic = _diagnostic(
                release_artifact.verify_artifact(wheel, "v1.4.0"),
                "artifact-filename-mismatch",
            )
            self.assertIn(wheel.name, diagnostic.message)
            self.assertIn("v1.4.0", diagnostic.message)

    def test_an_archive_with_no_metadata_is_refused_rather_than_read_as_empty(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "aart_cli-1.4.0-py3-none-any.whl"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("agent_artifacts/__init__.py", "")
            diagnostic = _diagnostic(
                release_artifact.verify_artifact(path, "v1.4.0"),
                "artifact-metadata-unreadable",
            )
            self.assertIn("METADATA", diagnostic.message)


class TheOneWheelTest(unittest.TestCase):
    def test_the_one_wheel_is_the_one_returned(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            wheel = _wheel(pathlib.Path(raw), version="1.4.0")
            self.assertEqual(release_artifact.wheel_in(pathlib.Path(raw)), wheel)

    def test_the_directory_must_hold_exactly_one_wheel(self) -> None:
        """Two wheels means the run built the artifact twice, and the checks pick one at random."""

        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            _wheel(directory, version="1.4.0")
            _wheel(directory, version="1.4.1")
            with self.assertRaises(release_artifact.ArtifactError) as caught:
                release_artifact.wheel_in(directory)
            self.assertEqual(
                str(caught.exception),
                "expected exactly one wheel in "
                f"{directory}, found: aart_cli-1.4.0-py3-none-any.whl, "
                "aart_cli-1.4.1-py3-none-any.whl",
            )

    def test_no_wheel_is_a_refusal_not_a_pass(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(release_artifact.ArtifactError, "no wheel was built"):
                release_artifact.wheel_in(pathlib.Path(raw))


class ReleasedTagTest(unittest.TestCase):
    def test_a_tag_that_is_not_a_release_tag_is_refused(self) -> None:
        for tag in ("1.4.0", "v1.4", "vlatest", "v1.4.0-rc1", ""):
            with self.subTest(tag=tag):
                with self.assertRaisesRegex(release_artifact.ArtifactError, "expected vX.Y.Z"):
                    release_artifact.released_version(tag)

    def test_the_release_tag_carries_the_version_and_nothing_else(self) -> None:
        self.assertEqual(release_artifact.released_version("v12.0.7"), "12.0.7")

    @MUTATION_SETTINGS
    @given(
        st.integers(min_value=0, max_value=10**6),
        st.integers(min_value=0, max_value=10**6),
        st.integers(min_value=0, max_value=10**6),
    )
    def test_every_release_tag_gives_back_exactly_the_version_it_carries(
        self, major: int, minor: int, patch: int
    ) -> None:
        """The claim is universal, so it is stated over generated tags rather than over one.

        The version the artifact is checked against is read off the tag and nothing else, so a
        parse that drops, pads or reorders a component would ship a wheel checked against the
        wrong identity while every example anybody thought to write still passed.
        """

        version = f"{major}.{minor}.{patch}"
        self.assertEqual(release_artifact.released_version(f"v{version}"), version)

    @MUTATION_SETTINGS
    @given(st.text(max_size=24))
    def test_no_text_that_is_not_a_release_tag_is_ever_read_as_one(self, raw: str) -> None:
        try:
            version = release_artifact.released_version(raw)
        except release_artifact.ArtifactError:
            return
        self.assertEqual(raw, f"v{version}")


class CleanEnvironmentSmokeTest(unittest.TestCase):
    """The command inside the wheel runs, and agrees about which version it is.

    Driven through an injected runner rather than a real install: what is being tested here is
    that a disagreeing or failing command is *noticed*.  That the real install works is what the
    release run itself proves, on the artifact it is about to publish.
    """

    def test_a_command_that_reports_the_released_version_passes(self) -> None:
        calls: list[tuple[str, ...]] = []

        def runner(command: tuple[str, ...]) -> tuple[int, str]:
            calls.append(command)
            if "--version" in command:
                return (0, "aart-cli 1.4.0\n")
            return (0, "usage: aart [-h] ...\n")

        self.assertEqual(release_artifact.smoke("1.4.0", runner=runner), ())
        self.assertEqual(calls, [("aart", "--version"), ("aart", "--help")])

    def test_a_command_that_reports_another_version_is_refused(self) -> None:
        def runner(command: tuple[str, ...]) -> tuple[int, str]:
            return (0, "aart-cli 9.9.9\n" if "--version" in command else "usage: aart\n")

        diagnostic = _diagnostic(
            release_artifact.smoke("1.4.0", runner=runner), "artifact-smoke-version"
        )
        self.assertIn("aart-cli 9.9.9", diagnostic.message)
        self.assertIn("1.4.0", diagnostic.message)

    def test_a_command_that_fails_is_refused(self) -> None:
        def runner(command: tuple[str, ...]) -> tuple[int, str]:
            return (0, "aart-cli 1.4.0\n") if "--version" in command else (2, "boom")

        diagnostic = _diagnostic(
            release_artifact.smoke("1.4.0", runner=runner), "artifact-smoke-failed"
        )
        self.assertIn("--help", diagnostic.message)
        self.assertIn("boom", diagnostic.message)

    def test_a_version_command_that_fails_is_refused_with_its_answer(self) -> None:
        def runner(command: tuple[str, ...]) -> tuple[int, str]:
            return (2, "version boom") if "--version" in command else (0, "usage: aart\n")

        diagnostic = _diagnostic(
            release_artifact.smoke("1.4.0", runner=runner), "artifact-smoke-failed"
        )
        self.assertIn("--version", diagnostic.message)
        self.assertIn("version boom", diagnostic.message)


if __name__ == "__main__":
    unittest.main()
