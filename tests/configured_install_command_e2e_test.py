"""The public install command reaches the configured canonical action for approved registries.

Direct/local sources deliberately remain on the characterized legacy path while the strangler
moves one source kind at a time.  A RegistryGit coordinate, however, has an approved version and an
object identity the legacy catalogue cannot supply, so its public review and completion must come
from the same configured action already proven below the command boundary.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from agent_artifacts import cli
from agent_artifacts.configuration.model import (
    ReportingSettings,
    SourceKind,
    SyncSettings,
    UserConfiguration,
)
from agent_artifacts.configuration.paths import Platform, resolve_config_paths
from agent_artifacts.configuration.schema import user_configuration_bytes
from agent_artifacts.domain.identifiers import SourceId
from agent_artifacts.domain.registry import PromotionMode
from agent_artifacts.domain.result import Ok
from agent_artifacts.io.source_store import publish_source_snapshot
from agent_artifacts.sources.model import (
    SourcePublishCommand,
    ValidatedSourceCandidate,
    make_source_candidate,
    source_instance_id,
    source_store_paths,
)
from tests.configured_installation_draft_e2e_test import AuthoredSetup, _published_registry
from tests.marketplace_fixtures import configured_source
from tests.placed_installation_e2e_test import AUTHORED_SKILL, SKILL_BODY

COORDINATE = "company/skill/code-review"


class _Environment:
    def __init__(
        self,
        root: pathlib.Path,
        *,
        authored: tuple[tuple[str, str] | tuple[str, str, bool], ...] = AUTHORED_SKILL,
        setup: AuthoredSetup | None = None,
        promotion_mode: PromotionMode = PromotionMode.VENDORED,
    ) -> None:
        self.setup = setup
        self.promotion_mode = promotion_mode
        self.root = root
        self.home = root / "home"
        self.project = root / "project"
        self.home.mkdir()
        self.project.mkdir()
        self.xdg = {
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_DATA_HOME": str(self.home / ".local/share"),
            "XDG_CACHE_HOME": str(self.home / ".cache"),
        }
        platform = Platform.DARWIN if os.sys.platform == "darwin" else Platform.LINUX
        self.paths = resolve_config_paths(
            platform,
            home=str(self.home),
            xdg_config_home=self.xdg["XDG_CONFIG_HOME"],
            xdg_data_home=self.xdg["XDG_DATA_HOME"],
            xdg_cache_home=self.xdg["XDG_CACHE_HOME"],
        )
        self.source = configured_source("company", SourceKind.REGISTRY_GIT)
        configuration = UserConfiguration(
            1,
            (self.source,),
            self.source.alias,
            SyncSettings(),
            ReportingSettings(),
        )
        config_path = pathlib.Path(self.paths.user_config_file)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_bytes(user_configuration_bytes(configuration))

        self.publish(authored)

    def publish(self, authored: tuple[tuple[str, str] | tuple[str, str, bool], ...]) -> None:
        """Make `authored` the approved snapshot this machine's configured registry offers.

        Publishing again is how a source that has since synchronized is modelled. It replaces what
        the registry approves without touching anything installed, which is the precondition
        INV-188 describes: learning about a newer version is not itself an update.
        """

        candidate = make_source_candidate(
            source_instance_id(self.source),
            self.source.alias,
            "a" * 40,
            _published_registry(authored, setup=self.setup, mode=self.promotion_mode),
        )
        assert isinstance(candidate, Ok), candidate
        published = publish_source_snapshot(
            SourcePublishCommand(
                source_store_paths(self.paths.data_root, source_instance_id(self.source)),
                ValidatedSourceCandidate(candidate.value, SourceId("company-registry")),
                90,
            )
        )
        assert isinstance(published, Ok), published

    def disable_source(self) -> None:
        """Remove the registry subscription, leaving what it delivered installed."""

        configuration = UserConfiguration(1, (), None, SyncSettings(), ReportingSettings())
        pathlib.Path(self.paths.user_config_file).write_bytes(
            user_configuration_bytes(configuration)
        )

    def run(self, *argv: str) -> tuple[int, dict]:
        output = io.StringIO()
        with (
            mock.patch.dict(os.environ, self.xdg, clear=False),
            contextlib.redirect_stdout(output),
            mock.patch("os.getcwd", return_value=str(self.project)),
        ):
            code = cli.main([*argv, "--project", str(self.project), "--json"])
        payload = json.loads(output.getvalue())
        return code, payload

    def run_text(self, *argv: str) -> tuple[int, str]:
        output = io.StringIO()
        with (
            mock.patch.dict(os.environ, self.xdg, clear=False),
            contextlib.redirect_stdout(output),
            mock.patch("os.getcwd", return_value=str(self.project)),
        ):
            code = cli.main([*argv, "--project", str(self.project)])
        return code, output.getvalue()


@contextlib.contextmanager
def _environment(
    *,
    authored: tuple[tuple[str, str] | tuple[str, str, bool], ...] = AUTHORED_SKILL,
    setup: AuthoredSetup | None = None,
    promotion_mode: PromotionMode = PromotionMode.VENDORED,
):
    with tempfile.TemporaryDirectory() as raw:
        yield _Environment(
            pathlib.Path(raw).resolve(),
            authored=authored,
            setup=setup,
            promotion_mode=promotion_mode,
        )


class ConfiguredInstallCommandTest(unittest.TestCase):
    def test_review_projects_the_canonical_plan_and_writes_no_target_path(self) -> None:
        with _environment() as env:
            code, payload = env.run("marketplace", "install", COORDINATE, "--profile", "claude")

            self.assertEqual(code, 0, payload)
            self.assertFalse(payload["finalized"])
            self.assertEqual(payload["review_digest"], payload["review"]["review_digest"])
            self.assertEqual(payload["review"]["selection_mode"], "artifacts")
            self.assertTrue(payload["review"]["effects"])
            self.assertEqual(
                payload["review"]["items"][0]["key"], "company/skill/code-review@1.2.0"
            )
            text_code, text = env.run_text(
                "marketplace", "install", COORDINATE, "--profile", "claude"
            )
            self.assertEqual(text_code, 0, text)
            self.assertIn(payload["review_digest"], text)
            self.assertEqual(list(env.project.iterdir()), [])

    def test_a_stale_review_is_reported_with_the_current_canonical_plan_and_writes_nothing(
        self,
    ) -> None:
        with _environment() as env:
            code, payload = env.run(
                "marketplace",
                "install",
                COORDINATE,
                "--profile",
                "claude",
                "--expect",
                "sha256:" + "0" * 64,
                "--yes",
            )

            self.assertNotEqual(code, 0)
            self.assertFalse(payload["ok"])
            self.assertFalse(payload["finalized"])
            self.assertEqual(payload["review_digest"], payload["review"]["review_digest"])
            self.assertEqual(payload["review"]["selection_mode"], "artifacts")
            self.assertEqual(list(env.project.iterdir()), [])

    def test_an_explicit_symlink_mode_is_refused_instead_of_silently_copied(self) -> None:
        with _environment() as env:
            code, payload = env.run(
                "marketplace",
                "install",
                COORDINATE,
                "--profile",
                "claude",
                "--mode",
                "symlink",
            )

            self.assertNotEqual(code, 0)
            self.assertFalse(payload["ok"])
            self.assertIn("copy mode only", payload["diagnostics"][0]["message"])
            self.assertEqual(list(env.project.iterdir()), [])

    def test_confirmed_review_installs_and_records_without_the_legacy_manifest(self) -> None:
        with _environment() as env:
            _, review = env.run("marketplace", "install", COORDINATE, "--profile", "claude")

            code, payload = env.run(
                "marketplace",
                "install",
                COORDINATE,
                "--profile",
                "claude",
                "--expect",
                review["review_digest"],
                "--yes",
            )

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["finalized"])
            self.assertEqual(payload["review_digest"], review["review_digest"])
            self.assertEqual(payload["receipt"]["review_digest"], review["review_digest"])
            self.assertEqual(
                (env.project / ".claude/skills/code-review/SKILL.md").read_text(encoding="utf-8"),
                SKILL_BODY,
            )
            self.assertFalse(
                (env.project / ".agent-artifacts/manifest.json").exists(),
                "the registry route fell back to the legacy install-state writer",
            )
            state = pathlib.Path(env.paths.data_root) / "state"
            self.assertTrue(
                any((state / "installations").glob("*.json")),
                "the canonical installation was not recorded",
            )
            self.assertTrue(
                any((state / "activity").glob("*.json")),
                "the canonical action was not recorded",
            )

    def test_a_later_public_status_reads_the_canonical_installation_from_disk(self) -> None:
        with _environment() as env:
            installed, _ = env.run(
                "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
            )
            self.assertEqual(installed, 0)

            code, payload = env.run("marketplace", "status", "--profile", "claude")

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["finalized"])
            self.assertEqual(payload["operation"], "marketplace.status")
            self.assertEqual(len(payload["items"]), 1)
            self.assertEqual(payload["items"][0]["key"], "company/skill/code-review@1.2.0")
            self.assertEqual(payload["items"][0]["status"], "current")

    def test_public_status_is_empty_before_any_canonical_install(self) -> None:
        with _environment() as env:
            code, payload = env.run("marketplace", "status", "--profile", "claude")

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["items"], [])

    def test_public_status_measures_delivery_drift_instead_of_trusting_the_receipt(self) -> None:
        with _environment() as env:
            installed, _ = env.run(
                "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
            )
            self.assertEqual(installed, 0)
            delivered = env.project / ".claude/skills/code-review/SKILL.md"
            delivered.chmod(0o600)
            delivered.write_text("# changed after installation\n", encoding="utf-8")

            code, payload = env.run("marketplace", "status", "--profile", "claude")

            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["items"][0]["status"], "current")
            self.assertEqual(payload["items"][0]["health"], "attention")
            self.assertEqual(payload["items"][0]["detail"], "health: attention")

    def test_public_status_reports_only_the_requested_installation_scope(self) -> None:
        with _environment() as env:
            installed, _ = env.run(
                "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
            )
            self.assertEqual(installed, 0)

            user_code, user_payload = env.run(
                "marketplace", "status", "--profile", "claude", "--scope", "user"
            )
            project_code, project_payload = env.run("marketplace", "status", "--profile", "claude")

            self.assertEqual(user_code, 0, user_payload)
            self.assertEqual(user_payload["items"], [])
            self.assertEqual(project_code, 0, project_payload)
            self.assertEqual(len(project_payload["items"]), 1)


if __name__ == "__main__":
    unittest.main()
