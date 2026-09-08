"""B-095/QA-021: adopting artifacts from a repository that is not a configured Source.

Besides the monitored Source → Candidate → promotion flow, a maintainer needs an artifact-scoped
adoption path: point at a credential-free Git URL once, see exactly what its authors declared,
choose some of it, and let the registry own immutable copies of only those files. The repository is
never saved as a Source, so nothing about this claims continuous monitoring (INV-199, INV-200).

Three boundaries are the slice rather than incidental to it. Discovery is explicit: only committed
`aart.yaml`/`aart.json` manifests are read, never an inferred conventional shape (INV-201). What is
copied is only what each selected manifest declares in `payload.include` — a repository's other
files are not adopted by being nearby. And the copies carry their origin: the upstream URL, the
resolved commit, the manifest path and its input digest travel into the registry as provenance, so
a later explicit upstream check has something recorded to compare against.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from agent_artifacts.application.maintainer import CandidateBundle
from agent_artifacts.domain.candidates import (
    CandidateFinding,
    FindingSeverity,
    assess_candidate,
)
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.registry_adoption import (
    apply_adoption,
    prepare_adoption,
    scan_repository,
)
from agent_artifacts.io.registry_bootstrap import bootstrap_registry_workspace
from agent_artifacts.sources.git import acquire_git_snapshot
from agent_artifacts.sources.model import GitSnapshotRequest

SKILL_MANIFEST = """schema: aart.dev/skill/v1
artifact:
  name: verification-before-completion
  kind: skill
  version: 1.0.0
payload:
  include:
    - SKILL.md
compatibility:
  harnesses:
    - claude
"""

OTHER_MANIFEST = """schema: aart.dev/skill/v1
artifact:
  name: brainstorming
  kind: skill
  version: 2.1.0
payload:
  include:
    - SKILL.md
compatibility:
  harnesses:
    - claude
"""


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=True,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _initialize(root: Path) -> None:
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "AART Test")


class _Author:
    """A real authoring repository: two declared skills, and files nobody declared."""

    def __init__(self, root: Path) -> None:
        self.path = root / "superpowers"
        first = self.path / "skills" / "verification-before-completion"
        second = self.path / "skills" / "brainstorming"
        for directory, manifest in ((first, SKILL_MANIFEST), (second, OTHER_MANIFEST)):
            directory.mkdir(parents=True)
            (directory / "aart.yaml").write_text(manifest, encoding="utf-8")
            (directory / "SKILL.md").write_text(f"# {directory.name}\n", encoding="utf-8")
            # Present, committed, and declared by nobody: adoption must not copy it.
            (directory / "NOTES.md").write_text("internal working notes\n", encoding="utf-8")
        (self.path / "README.md").write_text("# Superpowers\n", encoding="utf-8")
        _initialize(self.path)
        _git(self.path, "add", "-A")
        _git(self.path, "commit", "-m", "author two skills")
        self.head = _git(self.path, "rev-parse", "HEAD")


class _Lab(unittest.TestCase):
    """One authoring repository and one initialized registry, both real checkouts."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="aart-adoption-")).resolve()
        self.addCleanup(lambda: subprocess.run(("rm", "-rf", str(self.root)), check=False))
        self.author = _Author(self.root)
        #: Other repositories a test wants the acquirer to reach, by the URL it names them with.
        self._elsewhere: dict[str, str] = {}
        self.registry = self.root / "registry"
        self.registry.mkdir()
        _initialize(self.registry)
        bootstrapped = bootstrap_registry_workspace(
            root=str(self.registry),
            registry_id="acme-registry",
            display_name="ACME Registry",
        )
        assert isinstance(bootstrapped, Ok) and bootstrapped.value.passed, bootstrapped
        # The URL the maintainer types is a real remote one; only the transport this test can
        # actually reach is substituted, inside the acquirer.
        self.url = "https://git.example/superpowers.git"

    def _acquire(self, url: str, ref: str):
        """The public acquirer, with local transport allowed for this test only.

        The production path never asks for it; `_assert_remote_request` fails the test if the code
        under test ever weakens the transport request it makes.
        """

        from agent_artifacts.curation.runtime import default_native_acquirer

        def local(request: GitSnapshotRequest):
            self.assertFalse(
                request.allow_local_transport,
                "the scan weakened its own transport request",
            )
            local_url = (
                self.author.path.as_uri()
                if request.location == self.url
                else self._elsewhere[request.location]
            )
            return acquire_git_snapshot(
                replace(request, location=local_url, allow_local_transport=True)
            )

        with mock.patch("agent_artifacts.curation.runtime.acquire_git_snapshot", side_effect=local):
            return default_native_acquirer(url, ref)

    def _scan(self):
        return scan_repository(
            url=self.url, ref="main", registry_root=str(self.registry), acquire=self._acquire
        )


class RepositoryScanTest(_Lab):
    def test_a_scan_finds_exactly_the_declared_manifests_and_pins_the_commit(self) -> None:
        scanned = self._scan()

        self.assertIsInstance(scanned, Ok, scanned)
        assert isinstance(scanned, Ok)
        scan = scanned.value
        self.assertEqual(scan.commit, self.author.head)
        self.assertEqual(scan.url, self.url)
        self.assertEqual(scan.manifest_count, 2)
        self.assertEqual(
            sorted(item.coordinate for item in scan.artifacts),
            ["skill/brainstorming@2.1.0", "skill/verification-before-completion@1.0.0"],
        )

    def test_a_scan_names_only_the_files_each_manifest_declared(self) -> None:
        scanned = self._scan()

        assert isinstance(scanned, Ok)
        chosen = next(item for item in scanned.value.artifacts if item.name == "brainstorming")
        self.assertEqual(chosen.payload_paths, ("payload/SKILL.md",))
        self.assertEqual(chosen.manifest_path, "skills/brainstorming/aart.yaml")
        self.assertTrue(chosen.input_digest.startswith("sha256:"))

    def test_a_scan_saves_no_source_and_writes_nothing(self) -> None:
        """`B-095`: the repository is looked at, not subscribed to (INV-199)."""

        before = _git(self.registry, "status", "--porcelain=v1", "--untracked-files=all")

        scanned = self._scan()

        assert isinstance(scanned, Ok)
        self.assertEqual(
            _git(self.registry, "status", "--porcelain=v1", "--untracked-files=all"), before
        )
        self.assertFalse(os.path.exists(self.registry / "aart.config.json"))

    def test_a_repository_declaring_nothing_is_refused_by_name(self) -> None:
        plain = self.root / "plain"
        plain.mkdir()
        (plain / "README.md").write_text("# nothing declared\n", encoding="utf-8")
        _initialize(plain)
        _git(plain, "add", "-A")
        _git(plain, "commit", "-m", "no manifests")

        self._elsewhere["https://git.example/plain.git"] = plain.as_uri()

        refused = scan_repository(
            url="https://git.example/plain.git",
            ref="main",
            registry_root=str(self.registry),
            acquire=self._acquire,
        )

        self.assertIsInstance(refused, Err)
        assert isinstance(refused, Err)
        self.assertIn("aart.yaml", "\n".join(item.message for item in refused.diagnostics))


class SelectiveAdoptionTest(_Lab):
    def _package(self, kind: str, name: str, version: str) -> Path:
        return self.registry / "artifacts" / kind / name / version

    def test_only_the_selected_artifact_becomes_registry_content(self) -> None:
        scanned = self._scan()
        assert isinstance(scanned, Ok)

        prepared = prepare_adoption(
            scanned.value, ("skill/brainstorming@2.1.0",), registry_root=str(self.registry)
        )
        self.assertIsInstance(prepared, Ok, prepared)
        assert isinstance(prepared, Ok)
        applied = apply_adoption(
            prepared.value, prepared.value.review_digest, registry_root=str(self.registry)
        )

        self.assertIsInstance(applied, Ok, applied)
        adopted = self._package("skill", "brainstorming", "2.1.0")
        self.assertTrue((adopted / "artifact.json").is_file())
        self.assertFalse(
            self._package("skill", "verification-before-completion", "1.0.0").exists(),
            "an unselected artifact was adopted",
        )

    def test_only_the_declared_payload_files_are_copied(self) -> None:
        scanned = self._scan()
        assert isinstance(scanned, Ok)
        prepared = prepare_adoption(
            scanned.value, ("skill/brainstorming@2.1.0",), registry_root=str(self.registry)
        )
        assert isinstance(prepared, Ok), prepared
        apply_adoption(
            prepared.value, prepared.value.review_digest, registry_root=str(self.registry)
        )

        adopted = self._package("skill", "brainstorming", "2.1.0")
        copied = sorted(
            str(path.relative_to(adopted)) for path in adopted.rglob("*") if path.is_file()
        )

        self.assertIn("payload/SKILL.md", copied)
        # NOTES.md sits beside the manifest and is committed upstream; nothing declared it.
        self.assertNotIn("payload/NOTES.md", copied)
        self.assertNotIn("payload/aart.yaml", copied)

    def test_the_adopted_copy_records_where_it_came_from(self) -> None:
        scanned = self._scan()
        assert isinstance(scanned, Ok)
        prepared = prepare_adoption(
            scanned.value, ("skill/brainstorming@2.1.0",), registry_root=str(self.registry)
        )
        assert isinstance(prepared, Ok), prepared
        apply_adoption(
            prepared.value, prepared.value.review_digest, registry_root=str(self.registry)
        )

        adopted = self._package("skill", "brainstorming", "2.1.0")
        provenance = json.loads((adopted / "provenance.json").read_text(encoding="utf-8"))
        origin = provenance["origin"]

        # The key names are the native provenance contract's, not this flow's invention: an
        # adopted copy is provenance-shaped exactly like every other package in the registry.
        self.assertEqual(origin["url"], self.url)
        self.assertEqual(origin["resolved_commit"], self.author.head)
        self.assertEqual(origin["path"], "skills/brainstorming/aart.yaml")
        self.assertTrue(origin["input_digest"].startswith("sha256:"))
        self.assertEqual(
            provenance["aart.repository-adoption"],
            {"ref": "main"},
            "an explicit upstream check needs the moving ref, not only this pinned commit",
        )

    def test_the_review_names_every_chosen_coordinate_and_the_resolved_commit(self) -> None:
        scanned = self._scan()
        assert isinstance(scanned, Ok)

        prepared = prepare_adoption(
            scanned.value,
            ("skill/brainstorming@2.1.0", "skill/verification-before-completion@1.0.0"),
            registry_root=str(self.registry),
        )

        assert isinstance(prepared, Ok), prepared
        self.assertEqual(
            prepared.value.selected,
            ("skill/brainstorming@2.1.0", "skill/verification-before-completion@1.0.0"),
        )
        self.assertEqual(prepared.value.commit, self.author.head)
        self.assertTrue(prepared.value.review_digest.startswith("sha256:"))
        self.assertTrue(
            any(
                path.startswith("artifacts/skill/brainstorming/")
                for path in prepared.value.changed_paths
            )
        )

    def test_nothing_is_written_by_preparing_alone(self) -> None:
        scanned = self._scan()
        assert isinstance(scanned, Ok)
        before = _git(self.registry, "status", "--porcelain=v1", "--untracked-files=all")

        prepared = prepare_adoption(
            scanned.value, ("skill/brainstorming@2.1.0",), registry_root=str(self.registry)
        )

        assert isinstance(prepared, Ok), prepared
        self.assertEqual(
            _git(self.registry, "status", "--porcelain=v1", "--untracked-files=all"), before
        )

    def test_a_coordinate_the_scan_never_found_is_refused(self) -> None:
        scanned = self._scan()
        assert isinstance(scanned, Ok)

        refused = prepare_adoption(
            scanned.value, ("skill/not-there@1.0.0",), registry_root=str(self.registry)
        )

        self.assertIsInstance(refused, Err)

    def test_a_confirmation_naming_another_plan_is_refused(self) -> None:
        scanned = self._scan()
        assert isinstance(scanned, Ok)
        prepared = prepare_adoption(
            scanned.value, ("skill/brainstorming@2.1.0",), registry_root=str(self.registry)
        )
        assert isinstance(prepared, Ok), prepared

        refused = apply_adoption(
            prepared.value, "sha256:" + "0" * 64, registry_root=str(self.registry)
        )

        self.assertIsInstance(refused, Err)
        self.assertFalse(self._package("skill", "brainstorming", "2.1.0").exists())

    def test_adopting_the_same_version_twice_is_refused_as_immutable(self) -> None:
        scanned = self._scan()
        assert isinstance(scanned, Ok)
        first = prepare_adoption(
            scanned.value, ("skill/brainstorming@2.1.0",), registry_root=str(self.registry)
        )
        assert isinstance(first, Ok), first
        applied = apply_adoption(
            first.value, first.value.review_digest, registry_root=str(self.registry)
        )
        assert isinstance(applied, Ok), applied

        again = self._scan()
        assert isinstance(again, Ok)
        repeated = prepare_adoption(
            again.value, ("skill/brainstorming@2.1.0",), registry_root=str(self.registry)
        )

        self.assertIsInstance(repeated, Err, repeated)

    def test_the_scan_alias_never_becomes_registry_identity(self) -> None:
        """`INV-199`: the ephemeral name a scan compiles under is not what the registry publishes.

        Compiling an artifact needs a Source name and this repository is not a Source, so the scan
        invents `scan-<slug>` in memory. That name is a mechanism, not an identity: what the
        registry owns is published under the registry's own alias, and the only thing recorded
        about the repository is its URL and commit, as provenance.
        """

        scanned = self._scan()
        assert isinstance(scanned, Ok)
        self.assertEqual(scanned.value.registry_alias, "acme-registry")
        prepared = prepare_adoption(
            scanned.value, ("skill/brainstorming@2.1.0",), registry_root=str(self.registry)
        )
        assert isinstance(prepared, Ok), prepared
        applied = apply_adoption(
            prepared.value, prepared.value.review_digest, registry_root=str(self.registry)
        )
        assert isinstance(applied, Ok), applied

        written = [
            path
            for path in self.registry.rglob("*")
            if path.is_file() and ".git/" not in str(path.relative_to(self.registry))
        ]
        for path in written:
            self.assertNotIn(
                "scan-superpowers",
                path.read_text(encoding="utf-8", errors="replace"),
                f"{path.relative_to(self.registry)} published the scan's throwaway alias",
            )

    def test_an_artifact_that_did_not_validate_is_refused_by_name(self) -> None:
        """Only a Candidate validation cleared may be adopted. A scan screen shows the state; this
        holds that the state is enforced rather than displayed."""

        scanned = self._scan()
        assert isinstance(scanned, Ok)
        scan = scanned.value
        failed = CandidateFinding("payload-boundary", FindingSeverity.ERROR, "payload escapes")
        broken = tuple(
            CandidateBundle(assess_candidate(bundle.candidate, findings=(failed,)), bundle.artifact)
            if bundle.candidate.artifact.coordinate.artifact.name == "brainstorming"
            else bundle
            for bundle in scan.bundles
        )

        refused = prepare_adoption(
            replace(scan, bundles=broken),
            ("skill/brainstorming@2.1.0",),
            registry_root=str(self.registry),
        )

        self.assertIsInstance(refused, Err, refused)
        assert isinstance(refused, Err)
        self.assertIn(
            "skill/brainstorming@2.1.0", "\n".join(item.message for item in refused.diagnostics)
        )
        self.assertFalse(self._package("skill", "brainstorming", "2.1.0").exists())


if __name__ == "__main__":
    unittest.main()
