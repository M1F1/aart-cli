"""B-095: the one-off repository adoption contract is machine-complete on the public CLI.

The command is a skin over ``registry_adoption``: tests substitute only transport, then use a real
Git repository and Registry checkout. Review must write nothing, finalization must use the reviewed
plan, and upstream movement must add a version rather than rewrite one.
"""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from dataclasses import replace
from unittest import mock

from agent_artifacts import cli
from agent_artifacts.domain.result import Ok
from agent_artifacts.sources.git import acquire_git_snapshot
from tests.registry_repository_scan_test import OTHER_MANIFEST, _git, _Lab


class RegistryAdoptionCliTest(_Lab):
    coordinate = "skill/brainstorming@2.1.0"

    def _run(self, *arguments: str) -> tuple[int, dict[str, object]]:
        output = io.StringIO()

        def local_transport(request):
            self.assertFalse(request.allow_local_transport)
            return acquire_git_snapshot(
                replace(
                    request,
                    location=self.author.path.as_uri(),
                    allow_local_transport=True,
                )
            )

        with (
            mock.patch(
                "agent_artifacts.curation.runtime.acquire_git_snapshot",
                side_effect=local_transport,
            ),
            contextlib.redirect_stdout(output),
        ):
            code = cli.main([*arguments, "--json"])
        return code, json.loads(output.getvalue())

    def _adopt(self) -> dict[str, object]:
        code, payload = self._run(
            "registry",
            "adopt",
            "--source",
            str(self.registry),
            "--url",
            self.url,
            "--ref",
            "main",
            "--artifact",
            self.coordinate,
            "--yes",
        )
        self.assertEqual(code, 0, payload)
        return payload

    def test_scan_json_names_every_manifest_and_writes_nothing(self) -> None:
        before = _git(self.registry, "status", "--porcelain=v1", "--untracked-files=all")

        code, payload = self._run(
            "registry",
            "adopt",
            "--source",
            str(self.registry),
            "--url",
            self.url,
            "--ref",
            "main",
        )

        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["operation"], "registry.adopt")
        self.assertEqual(payload["phase"], "scan")
        self.assertFalse(payload["applied"])
        self.assertEqual(payload["resolved_commit"], self.author.head)
        self.assertEqual(
            [item["coordinate"] for item in payload["artifacts"]],
            ["skill/brainstorming@2.1.0", "skill/verification-before-completion@1.0.0"],
        )
        self.assertEqual(
            _git(self.registry, "status", "--porcelain=v1", "--untracked-files=all"), before
        )

    def test_selected_artifact_is_reviewed_before_any_write(self) -> None:
        before = _git(self.registry, "status", "--porcelain=v1", "--untracked-files=all")

        code, payload = self._run(
            "registry",
            "adopt",
            "--source",
            str(self.registry),
            "--url",
            self.url,
            "--ref",
            "main",
            "--artifact",
            self.coordinate,
        )

        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["phase"], "review")
        self.assertFalse(payload["applied"])
        self.assertEqual(payload["selected"], [self.coordinate])
        self.assertTrue(payload["review_digest"].startswith("sha256:"))
        self.assertTrue(payload["changes"])
        self.assertEqual(
            _git(self.registry, "status", "--porcelain=v1", "--untracked-files=all"), before
        )

    def test_yes_applies_only_the_selected_declared_payload_and_saves_no_source(self) -> None:
        payload = self._adopt()

        self.assertEqual(payload["phase"], "adopted-local")
        self.assertTrue(payload["applied"])
        package = self.registry / "artifacts" / "skill" / "brainstorming" / "2.1.0"
        self.assertTrue((package / "payload" / "SKILL.md").is_file())
        self.assertFalse((package / "payload" / "NOTES.md").exists())
        self.assertFalse((self.registry / "aart.config.json").exists())

    def test_check_json_reports_unchanged_without_writing(self) -> None:
        self._adopt()
        before = _git(self.registry, "status", "--porcelain=v1", "--untracked-files=all")

        code, payload = self._run(
            "registry",
            "check-upstream",
            "--source",
            str(self.registry),
            self.coordinate,
        )

        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["operation"], "registry.check-upstream")
        self.assertEqual(payload["disposition"], "unchanged")
        self.assertFalse(payload["applied"])
        self.assertIsNone(payload["proposal"])
        self.assertEqual(
            _git(self.registry, "status", "--porcelain=v1", "--untracked-files=all"), before
        )

    def test_changed_new_version_is_reviewed_then_added_without_rewriting_the_old_one(self) -> None:
        self._adopt()
        old = self.registry / "artifacts" / "skill" / "brainstorming" / "2.1.0"
        old_bytes = (old / "payload" / "SKILL.md").read_bytes()
        manifest = self.author.path / "skills" / "brainstorming" / "aart.yaml"
        manifest.write_text(OTHER_MANIFEST.replace("2.1.0", "2.2.0"), encoding="utf-8")
        (manifest.parent / "SKILL.md").write_text("# brainstorming 2.2\n", encoding="utf-8")
        _git(self.author.path, "add", "-A")
        _git(self.author.path, "commit", "-m", "release brainstorming 2.2")

        code, review = self._run(
            "registry",
            "check-upstream",
            "--source",
            str(self.registry),
            self.coordinate,
        )

        self.assertEqual(code, 0, review)
        self.assertEqual(review["disposition"], "changed")
        self.assertFalse(review["applied"])
        self.assertEqual(review["proposal"]["selected"], ["skill/brainstorming@2.2.0"])
        self.assertTrue(review["proposal"]["review_digest"].startswith("sha256:"))
        self.assertFalse((old.parent / "2.2.0").exists())

        code, applied = self._run(
            "registry",
            "check-upstream",
            "--source",
            str(self.registry),
            self.coordinate,
            "--yes",
            "--expect",
            review["proposal"]["review_digest"],
        )

        self.assertEqual(code, 0, applied)
        self.assertTrue(applied["applied"])
        self.assertEqual((old / "payload" / "SKILL.md").read_bytes(), old_bytes)
        self.assertTrue((old.parent / "2.2.0" / "payload" / "SKILL.md").is_file())

    def test_the_scan_listing_is_ordered_by_coordinate_whatever_the_compiler_returns(self) -> None:
        """A machine-readable listing that reorders itself between runs is not machine-readable.

        The compiler's own order is an implementation detail of how a snapshot was walked, so the
        command sorts. Reversing what the scan hands over proves the sort is the command's and not
        an accident of this repository's layout.
        """

        from agent_artifacts.commands import registry as registry_command

        real = registry_command.scan_repository

        def reversed_scan(**keywords):
            scanned = real(**keywords)
            return Ok(replace(scanned.value, artifacts=tuple(reversed(scanned.value.artifacts))))

        with mock.patch.object(registry_command, "scan_repository", side_effect=reversed_scan):
            code, payload = self._run(
                "registry",
                "adopt",
                "--source",
                str(self.registry),
                "--url",
                self.url,
                "--ref",
                "main",
            )

        self.assertEqual(code, 0, payload)
        self.assertEqual(
            [item["coordinate"] for item in payload["artifacts"]],
            ["skill/brainstorming@2.1.0", "skill/verification-before-completion@1.0.0"],
        )

    def test_a_stale_expect_refuses_the_adoption_and_writes_nothing(self) -> None:
        """`--expect` binds a finalization to the review that produced it, or there is no point to
        it: the repository can move between the two invocations."""

        before = _git(self.registry, "status", "--porcelain=v1", "--untracked-files=all")

        code, payload = self._run(
            "registry",
            "adopt",
            "--source",
            str(self.registry),
            "--url",
            self.url,
            "--ref",
            "main",
            "--artifact",
            self.coordinate,
            "--yes",
            "--expect",
            "sha256:" + "0" * 64,
        )

        self.assertNotEqual(code, 0)
        self.assertFalse(payload["ok"])
        self.assertFalse(
            (self.registry / "artifacts" / "skill" / "brainstorming" / "2.1.0").exists()
        )
        self.assertEqual(
            _git(self.registry, "status", "--porcelain=v1", "--untracked-files=all"), before
        )

    def test_a_stale_expect_refuses_the_upstream_finalization(self) -> None:
        self._adopt()
        manifest = self.author.path / "skills" / "brainstorming" / "aart.yaml"
        manifest.write_text(OTHER_MANIFEST.replace("2.1.0", "2.2.0"), encoding="utf-8")
        (manifest.parent / "SKILL.md").write_text("# brainstorming 2.2\n", encoding="utf-8")
        _git(self.author.path, "add", "-A")
        _git(self.author.path, "commit", "-m", "release brainstorming 2.2")

        code, payload = self._run(
            "registry",
            "check-upstream",
            "--source",
            str(self.registry),
            self.coordinate,
            "--yes",
            "--expect",
            "sha256:" + "0" * 64,
        )

        self.assertNotEqual(code, 0)
        self.assertFalse(payload["ok"])
        self.assertFalse(
            (self.registry / "artifacts" / "skill" / "brainstorming" / "2.2.0").exists()
        )


if __name__ == "__main__":
    unittest.main()
