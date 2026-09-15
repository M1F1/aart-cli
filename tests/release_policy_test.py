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

from scripts import release_artifact

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
# Release Please's generic updater pattern: the first match on a marked line is replaced whole,
# including whatever it takes for a pre-release or build suffix.
_ENGINE_VERSION = re.compile(r"\d+\.\d+\.\d+(?P<rest>-[\w.]+|\+[-\w.]+)?")
# The places the README would quote this package's release: a tag, a wheel, an index pin.
_README_RELEASE = re.compile(r"(?:aart_cli-|aart-cli==|@v|--tag v|tag -f v|origin v)\d+\.\d+\.\d+")
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

    def test_every_line_the_engine_rewrites_holds_exactly_one_version_it_can_rewrite(self) -> None:
        """INV-101: a line the engine rewrites wrongly is worse than a line it never touches.

        The generic updater replaces only the *first* version on a marked line, and its pattern
        reads anything after a hyphen as a pre-release. The first release PR showed both: a table
        row quoting three versions had one rewritten, and `aart_cli-0.0.1-py3-none-any.whl` became
        `aart_cli-0.1.0-none-any.whl`. So a marked line may hold one version, bare.
        """

        marker = "x-release-please-version"
        config = _config()
        packages = config.get("packages")
        assert isinstance(packages, dict)
        root_package = packages["."]
        assert isinstance(root_package, dict)
        generic = [
            entry if isinstance(entry, str) else str(entry["path"])
            for entry in root_package.get("extra-files", ())
            if isinstance(entry, str) or entry.get("type", "generic") == "generic"
        ]
        self.assertGreater(len(generic), 0)
        for relative in generic:
            text = (ROOT / relative).read_text(encoding="utf-8")
            marked = [line for line in text.split("\n") if marker in line]
            self.assertGreater(len(marked), 0, f"{relative} is listed but carries no marker")
            for line in marked:
                with self.subTest(file=relative, line=line[:60]):
                    found = list(_ENGINE_VERSION.finditer(line))
                    self.assertEqual(len(found), 1, "the engine rewrites only the first version")
                    self.assertIsNone(
                        found[0].group("rest"), "the engine reads this as a pre-release"
                    )

    def test_the_readme_writes_the_release_as_a_placeholder(self) -> None:
        """INV-101: the README shows the shape of a command; the exact one is on the release.

        `scripts/install_commands.py` prints the exact commands and the release body carries them,
        so a version written into the README is a copy with nothing to gain from it.
        """

        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertEqual(_README_RELEASE.findall(text), [])
        self.assertIn("X.Y.Z", text)

    def test_the_tag_the_engine_creates_is_one_the_release_run_accepts(self) -> None:
        """INV-099: the release tag is the released identity, so both ends must spell it alike.

        Release Please names a tag `<component>-v<version>` unless told otherwise, and the
        component defaults to `package-name`, which is why this repository sets neither. `release.yml` and `release_artifact.py` accept only
        `vX.Y.Z`, so an engine left on its default would publish a GitHub Release whose wheel is
        never built. The tag is derived here the way the engine derives it.
        """

        config = _config()
        packages = config.get("packages")
        assert isinstance(packages, dict)
        root_package = packages["."]
        assert isinstance(root_package, dict)
        component = root_package.get("component", root_package.get("package-name", ""))
        include_component = root_package.get(
            "include-component-in-tag", config.get("include-component-in-tag", True)
        )
        include_v = root_package.get("include-v-in-tag", config.get("include-v-in-tag", True))
        separator = root_package.get("tag-separator", config.get("tag-separator", "-"))
        version = _released_version()
        tag = f"{'v' if include_v else ''}{version}"
        if include_component and component:
            tag = f"{component}{separator}{tag}"

        self.assertEqual(release_artifact.released_version(tag), version)

    def test_a_merged_release_pr_is_one_the_engine_will_release(self) -> None:
        """INV-099: a release PR that merges without becoming a release is a release that never was.

        With one pull request for the whole manifest, the release branch is
        `release-please--branches--main` and names no component. After the merge, Release Please
        (17.3.0, `BaseStrategy.buildRelease`) compares that empty component with its own
        `component || package-name`. When they differ it logs "PR component: undefined does not
        match configured component" and creates no tag, no GitHub Release and no wheel. That
        happened to 0.1.0 while `package-name` was `aart-cli`.
        """

        config = _config()
        packages = config.get("packages")
        assert isinstance(packages, dict)
        root_package = packages["."]
        assert isinstance(root_package, dict)
        separate = root_package.get(
            "separate-pull-requests", config.get("separate-pull-requests", False)
        )
        if separate:
            self.skipTest("a separate release PR's branch carries its component")
        configured = root_package.get("component") or root_package.get("package-name") or ""
        self.assertEqual(configured, "", "the release branch names no component to match this")

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
