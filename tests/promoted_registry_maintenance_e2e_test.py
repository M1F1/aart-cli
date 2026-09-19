"""CP-19 step 9: the registry promotion writes is the registry maintenance has to accept.

`registry init` generates a workflow that gates every pull request with `format`, `validate`,
`lock`, `build`, `audit` and `test`, and screen 46's Rebuild runs four of the same verbs locally.
A promotion writes the approved versioned representation the Product Specification names -- the one
a public consumer acquires and validates -- so the first real promoted artifact failed both gates
with a refusal naming `artifact.json` at the *unversioned* path of the older authoring workspace
(`QA-025`, `QA-032`, `B-057`).

Nothing here is a fixture's idea of a registry: the workspace is built by the public `registry init`
→ `registry scan` → `registry promote` chain, which is the same transaction the TUI applies.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from aart_cli import cli
from aart_cli.domain.result import Ok
from aart_cli.io.registry_bootstrap import refresh_registry_workspace
from aart_cli.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
)
from aart_cli.protocol.paths import parse_relative_path
from aart_cli.registry_maintenance.promoted import (
    is_promoted_registry,
    legacy_registry_paths,
)
from tests.maintainer_scan_cli_test import _author_checkout, _git

_EVIDENCE = ("--validation-report", "sha256:" + "7" * 64, "--policy-result", "sha256:" + "8" * 64)

#: What `.github/workflows/aart-registry.yml` runs on every pull request, in its order.
GENERATED_GATE: tuple[tuple[str, ...], ...] = (
    ("format", "--check"),
    ("validate",),
    ("build", "--check"),
    ("audit",),
    ("test", "--compatibility", "latest"),
)


def _cli(*argv: str) -> tuple[int, str]:
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = cli.main(list(argv))
    except SystemExit as exit_request:
        return int(exit_request.code or 0), output.getvalue()
    return code, output.getvalue()


def _shape(*paths: str) -> SourceSnapshot:
    entries = []
    for path in paths:
        parsed = parse_relative_path(path)
        assert isinstance(parsed, Ok)
        entries.append(SnapshotEntry(parsed.value, SnapshotEntryKind.FILE, b"{}"))
    return SourceSnapshot(SnapshotOrigin.LOCAL, tuple(entries))


class RegistryShapeTest(unittest.TestCase):
    def test_every_retired_path_kind_is_identified_without_matching_versioned_packages(
        self,
    ) -> None:
        retired = (
            "aart.lock.json",
            "aart.index.json",
            "entries/skill/example.json",
            "artifacts/skill/example/artifact.json",
            "artifacts/skill/example/provenance.json",
        )
        for path in retired:
            with self.subTest(path=path):
                self.assertEqual(legacy_registry_paths(_shape(path)), (path,))

        canonical = _shape(
            "artifacts/skill/example/1.0.0/artifact.json",
            "artifacts/skill/example/1.0.0/provenance.json",
        )
        self.assertEqual(legacy_registry_paths(canonical), ())

    def test_empty_canonical_old_and_mixed_registry_shapes_are_distinct(self) -> None:
        roots = ("aart-registry.json", "aart-source.json")
        self.assertTrue(is_promoted_registry(_shape(*roots)))
        self.assertFalse(is_promoted_registry(_shape(*roots, "aart.lock.json")))
        self.assertTrue(
            is_promoted_registry(
                _shape(
                    *roots,
                    "aart.lock.json",
                    "registry/versions/skill/example/1.0.0.json",
                )
            )
        )


class PromotedRegistryMaintenanceE2ETest(unittest.TestCase):
    @contextlib.contextmanager
    def _empty_registry(self):
        """An initialized canonical Registry before its first approved version."""

        with tempfile.TemporaryDirectory() as raw:
            checkout = Path(raw).resolve() / "registry"
            checkout.mkdir()
            _git(checkout, "init", "-q")
            _git(checkout, "config", "user.name", "AART Test")
            _git(checkout, "config", "user.email", "aart@example.invalid")
            code, text = _cli(
                "registry",
                "init",
                "--source",
                str(checkout),
                "--source-id",
                "company-registry",
                "--display-name",
                "Company Registry",
                "--yes",
            )
            self.assertEqual(code, 0, text)
            yield checkout

    @contextlib.contextmanager
    def _promoted_registry(self):
        """An initialized registry checkout holding exactly one real local promotion."""

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            author = root / "author"
            checkout = root / "registry"
            author.mkdir()
            checkout.mkdir()
            _author_checkout(author)
            _git(checkout, "init", "-q")
            _git(checkout, "config", "user.name", "AART Test")
            _git(checkout, "config", "user.email", "aart@example.invalid")

            code, text = _cli(
                "registry",
                "init",
                "--source",
                str(checkout),
                "--source-id",
                "company-registry",
                "--display-name",
                "Company Registry",
                "--yes",
            )
            self.assertEqual(code, 0, text)
            common = (
                "--source",
                str(checkout),
                "--checkout",
                str(author),
                "--source-alias",
                "authors",
                "--source-url",
                "https://git.example/authors.git",
                "--target-registry",
                "company",
            )
            code, text = _cli("registry", "scan", *common, "--json")
            self.assertEqual(code, 0, text)
            candidate = json.loads(text)["candidates"][0]["candidate_id"]
            code, text = _cli(
                "registry",
                "promote",
                *common,
                "--candidate",
                candidate,
                *_EVIDENCE,
                "--yes",
                "--json",
            )
            self.assertEqual(code, 0, text)
            yield checkout

    def test_the_generated_gate_accepts_the_registry_promotion_wrote(self) -> None:
        with self._promoted_registry() as checkout:
            failed = []
            for verb, *arguments in GENERATED_GATE:
                code, text = _cli("registry", verb, "--source", str(checkout), *arguments)
                if code != 0:
                    failed.append(f"{verb}: {text.strip().splitlines()[:3]}")

            self.assertEqual(failed, [])

    def test_empty_registry_maintenance_never_creates_the_older_representation(self) -> None:
        """CP-26.03: init already chose the canonical shape, before the first promotion."""

        with self._empty_registry() as checkout:
            for verb in ("lock", "build", "format"):
                code, text = _cli("registry", verb, "--source", str(checkout), "--yes")
                self.assertEqual(code, 0, text)

            for verb in ("validate", "audit"):
                code, text = _cli("registry", verb, "--source", str(checkout))
                self.assertEqual(code, 0, text)

            code, text = _cli("registry", "publish", "--source", str(checkout), "--yes")
            self.assertEqual(code, 0, text)

            self.assertFalse((checkout / "aart.lock.json").exists())
            self.assertFalse((checkout / "aart.index.json").exists())
            self.assertTrue((checkout / "registry/index.json").is_file())
            self.assertTrue((checkout / "registry/snapshot.json").is_file())

    def test_maintenance_does_not_write_the_older_workspace_representation(self) -> None:
        """`B-057` stays closed by one representation, not by producing both of them."""

        with self._promoted_registry() as checkout:
            for verb in ("lock", "build"):
                code, text = _cli("registry", verb, "--source", str(checkout), "--yes")
                self.assertEqual(code, 0, text)

            self.assertFalse((checkout / "aart.lock.json").exists())
            self.assertFalse((checkout / "aart.index.json").exists())
            self.assertTrue((checkout / "registry/index.json").exists())

    def test_a_rebuild_restores_a_catalog_somebody_damaged(self) -> None:
        """What `build` means for this representation: the derived catalogs, and nothing else."""

        with self._promoted_registry() as checkout:
            catalog = checkout / "registry/index.json"
            approved = catalog.read_bytes()
            catalog.write_bytes(b'{"schema": "aart.dev/registry-index/v1"}')

            code, text = _cli("registry", "build", "--source", str(checkout), "--check")

            self.assertNotEqual(code, 0, text)

            code, text = _cli("registry", "build", "--source", str(checkout), "--yes")

            self.assertEqual(code, 0, text)
            self.assertEqual(catalog.read_bytes(), approved)

    def test_publish_gates_the_approved_representation_without_locking_it(self) -> None:
        """Publish chains build, validate and audit; canonical packages need no legacy lock."""

        with self._promoted_registry() as checkout:
            code, text = _cli("registry", "publish", "--source", str(checkout), "--yes")

            self.assertEqual(code, 0, text)
            self.assertFalse((checkout / "aart.lock.json").exists())
            self.assertFalse((checkout / "aart.index.json").exists())

    def test_screen_46_rebuilds_the_registry_a_promotion_left_behind(self) -> None:
        """`QA-025`: the TUI's Rebuild is this port, and it ran the authoring workspace's reader."""

        with self._promoted_registry() as checkout:
            report = refresh_registry_workspace(root=str(checkout))

            self.assertIsInstance(report, Ok, report)
            self.assertEqual(
                [(stage.name, stage.passed) for stage in report.value.stages],
                [("lock", True), ("build", True), ("validate", True), ("audit", True)],
            )

    def test_publish_refuses_a_checkout_carrying_both_representations(self) -> None:
        """B-142: publish refuses mixed representation before any gate can mislead."""

        with self._promoted_registry() as checkout:
            (checkout / "aart.lock.json").write_text("{}\n", encoding="utf-8")
            (checkout / "aart.index.json").write_text("{}\n", encoding="utf-8")

            code, text = _cli("registry", "publish", "--source", str(checkout), "--yes")

            self.assertNotEqual(code, 0, text)
            self.assertNotIn("publish gate failed", text)
            self.assertIn("aart.lock.json", text)
            self.assertIn("aart.index.json", text)

    def test_a_damaged_version_record_is_still_refused(self) -> None:
        """The dispatch may not become a way past the validator it dispatches to."""

        with self._promoted_registry() as checkout:
            record = checkout / "registry/versions/mcp/github-mcp/1.0.0.json"
            content = json.loads(record.read_text(encoding="utf-8"))
            content["payload_digest"] = "sha256:" + "0" * 64
            record.write_text(json.dumps(content), encoding="utf-8")

            code, text = _cli(
                "registry", "validate", "--source", str(checkout), "--strict", "--frozen"
            )

            self.assertNotEqual(code, 0, text)


if __name__ == "__main__":
    unittest.main()
