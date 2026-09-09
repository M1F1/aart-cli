"""INV-081 to INV-105: the release engine's policy is committed, and it is the only engine.

Every claim here is about *reviewable state in the repository*, because that is what the
invariants are about.  INV-086 says the mapping from a reviewed change to a SemVer step must be
committed configuration rather than mutable GitHub Settings; INV-085 and INV-100 say one engine
decides the version and nothing else maintains a copy of it; INV-094 and INV-105 say the release
boundary is a pull request a human merges, and that auto-merge is a policy somebody turns on
rather than a side effect of automating the arithmetic.

None of that is a runtime behaviour, so none of it can be proven by running the tool.  What can be
proven is that the files which decide it say what they must say -- and, for the version, that no
second file quotes the release without the engine writing it.
"""

from __future__ import annotations

import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = ROOT / "release-please-config.json"
MANIFEST = ROOT / ".release-please-manifest.json"

# A version *declaration*: a name whose meaning is "the version", assigned a dotted literal.
# `_COMPILER_VERSION` in the authoring compiler and `DEFAULT_VERSION` in the vendor scanner match
# the shape and are not this package's release, so the value has to match the released version for
# a line to count.  That is the point: this finds the places that quote *this release*.
_ASSIGNED = re.compile(
    r'(?m)^\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*"(?P<value>\d+\.\d+\.\d+[^"]*)"'
)
_SEMVER_LITERAL = re.compile(
    r"(?m)^\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*SemVer\("
    r"(?P<major>\d+),\s*(?P<minor>\d+),\s*(?P<patch>\d+)\s*\)"
)


def _released_version() -> str:
    return str(json.loads(MANIFEST.read_text(encoding="utf-8"))["."])


def _config() -> dict[str, object]:
    loaded = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _scanned_files() -> tuple[pathlib.Path, ...]:
    """Everywhere a version can be declared: the build metadata, the package, the tooling."""

    return (
        ROOT / "pyproject.toml",
        *sorted((ROOT / "agent_artifacts").rglob("*.py")),
        *sorted((ROOT / "scripts").glob("*.py")),
    )


def declarations_of(version: str) -> tuple[str, ...]:
    """Every file that writes this release's version down, relative to the repository root."""

    found: list[str] = []
    for path in _scanned_files():
        text = path.read_text(encoding="utf-8")
        quoted = any(
            "version" in match.group("name").lower() and match.group("value") == version
            for match in _ASSIGNED.finditer(text)
        )
        built = any(
            "version" in match.group("name").lower()
            and f"{match.group('major')}.{match.group('minor')}.{match.group('patch')}" == version
            for match in _SEMVER_LITERAL.finditer(text)
        )
        if quoted or built:
            found.append(str(path.relative_to(ROOT)))
    return tuple(found)


def _written_by_the_engine() -> frozenset[str]:
    """The files the release engine rewrites: its own release-type target, plus `extra-files`."""

    config = _config()
    packages = config.get("packages")
    assert isinstance(packages, dict)
    root_package = packages["."]
    assert isinstance(root_package, dict)
    # `release-type: python` writes the project version in `pyproject.toml`; everything else is
    # named, so the policy can be read rather than remembered.
    written = {"pyproject.toml"}
    for entry in root_package.get("extra-files", ()):
        written.add(entry if isinstance(entry, str) else str(entry["path"]))
    return frozenset(written)


class CommittedReleasePolicyTest(unittest.TestCase):
    def test_the_semver_mapping_is_committed_configuration(self) -> None:
        """INV-082, INV-086, INV-087, INV-104.

        `fix -> PATCH`, `feat -> MINOR`, `!` -> `MAJOR` is the project's semantics, and a fork
        that changes runners, images and mirrors must not change it.  Release Please's own default
        for a `0.x` version is *not* that mapping -- it downgrades a break to a minor and a
        feature to a patch -- so leaving the defaults implicit would have meant the file said one
        thing and the engine did another.  Both switches are therefore written down.
        """

        config = _config()
        self.assertEqual(config.get("release-type"), "python")
        self.assertIs(config.get("bump-minor-pre-major"), False)
        self.assertIs(config.get("bump-patch-for-minor-pre-major"), False)
        sections = config.get("changelog-sections")
        assert isinstance(sections, list)
        visible = {str(section["type"]) for section in sections if not section.get("hidden", False)}
        self.assertIn("feat", visible)
        self.assertIn("fix", visible)

    def test_the_engine_writes_every_file_that_quotes_the_release(self) -> None:
        """INV-083, INV-085, INV-100, INV-101.

        Not "the copies agree" -- that test is the thing the invariant forbids.  The claim is that
        no copy is *maintained*: every file naming this release is one the engine rewrites.
        """

        declared = _written_by_the_engine()
        for relative in declarations_of(_released_version()):
            with self.subTest(file=relative):
                self.assertIn(
                    relative,
                    declared,
                    f"{relative} names the release, and release-please-config.json does not "
                    "list it -- so somebody has to remember to edit it",
                )

    def test_the_scan_above_finds_the_places_that_do_quote_it(self) -> None:
        """D-149: an absence proven by a sweep that sweeps nothing is not proven."""

        found = declarations_of(_released_version())
        self.assertIn("pyproject.toml", found)
        self.assertIn("agent_artifacts/__init__.py", found)

    def test_every_prose_mention_of_the_release_is_on_a_line_the_engine_rewrites(self) -> None:
        """INV-101: a README that quotes a version is a version somebody has to remember.

        The install table names an exact wheel and an exact tag, which is the whole reason it is
        useful, so the answer is not to delete the version -- it is to make the engine write it.
        The generic updater rewrites annotated lines only, so an *un*annotated mention is a copy
        that will go stale, and that is what this refuses.
        """

        marker = "x-release-please-version"
        version = _released_version()
        for relative in ("README.md",):
            text = (ROOT / relative).read_text(encoding="utf-8")
            mentions = [line for line in text.split("\n") if version in line]
            self.assertGreater(len(mentions), 0, f"{relative} no longer names the release at all")
            for line in mentions:
                with self.subTest(file=relative, line=line[:60]):
                    self.assertIn(marker, line)

    def test_the_manifest_and_the_package_agree_because_one_engine_wrote_both(self) -> None:
        """INV-099: the manifest is the engine's record of the released identity."""

        version = _released_version()
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(f'version = "{version}"', pyproject)

    def test_the_release_boundary_is_a_pull_request_a_human_merges(self) -> None:
        """INV-094, INV-105.

        Automating the arithmetic must not automate the decision.  Auto-merge is allowed as an
        explicit policy; what is forbidden is it arriving as a side effect, so the absence is
        asserted over the workflow that would be where it appeared.
        """

        workflow = (ROOT / ".github/workflows/release-please.yml").read_text(encoding="utf-8")
        self.assertNotIn("--auto", workflow)
        self.assertNotIn("enable-pull-request-automerge", workflow)
        self.assertNotIn("automerge", workflow)

    def test_no_second_engine_decides_a_version(self) -> None:
        """INV-091, INV-100, INV-101.

        The manual cut -- a version typed into a button, a version written into files by a script,
        a changelog edited by hand -- is not deprecated here, it is gone.  A retired path that is
        still runnable is still a second engine.
        """

        for retired in (
            ".github/workflows/cut-release.yml",
            ".github/actions/cut-release/action.yml",
            "scripts/cut_release.py",
            "scripts/prepare_release.py",
            "scripts/changelog.py",
            "scripts/bump_version.py",
            "scripts/version.py",
        ):
            with self.subTest(path=retired):
                self.assertFalse(
                    (ROOT / retired).exists(),
                    f"{retired} still exists, and it decides or writes a version",
                )

    def test_release_tooling_stays_out_of_the_runtime_graph(self) -> None:
        """INV-088: the release engine is a GitHub Action, not a dependency."""

        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        runtime = pyproject.split("dependencies = []", 1)
        self.assertEqual(len(runtime), 2, "the zero-dependency declaration moved")
        self.assertNotIn("release-please", pyproject)
        self.assertNotIn("commitizen", pyproject)
        self.assertNotIn("semantic-release", pyproject)


if __name__ == "__main__":
    unittest.main()
