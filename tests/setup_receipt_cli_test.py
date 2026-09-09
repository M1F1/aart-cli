"""RR-5: the three receipt verbs are reachable from the shipped front end, on real records.

Carried from the removed `tests/tui_receipt_test.py`, which made the same claims against the
retired wizard skins.  What is asserted is front-end reachability rather than receipt logic --
`show` writes exactly what the renderer produces, `verify` asks the filesystem instead of
trusting the record, `undo` reviews before it changes anything, and an unknown coordinate is a
refusal with remediation rather than a traceback.  The rendering and rollback decisions
themselves stay characterized in `setup_receipt_show_test.py`, `setup_verify_test.py` and
`setup_undo_test.py`; this file only proves an operator can reach them.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import tempfile
import unittest
from dataclasses import replace
from unittest import mock

from agent_artifacts import cli
from agent_artifacts.configuration.model import (
    ReportingSettings,
    SyncSettings,
    UserConfiguration,
)
from agent_artifacts.configuration.paths import Platform, resolve_config_paths
from agent_artifacts.configuration.schema import user_configuration_bytes
from agent_artifacts.domain.effects import DeliveryKind
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    ObjectDigest,
    SourceAlias,
)
from agent_artifacts.domain.receipts import ArtifactDelivery, PlacedArtifactReceipt
from agent_artifacts.domain.result import Ok
from agent_artifacts.install_state.paths import install_state_paths
from agent_artifacts.io.receipt_store import LocalReceiptStore
from agent_artifacts.model import SetupState, SetupStateRecord
from agent_artifacts.setup import dump_setup_state
from agent_artifacts.setup_receipt import ReceiptLocation, setup_state_file
from agent_artifacts.setup_render import receipt_payload, render_receipt_payload

SETUP_REF = "setup-" + "e" * 20
COORDINATE = "registry-a/mcp/github-docker"
MANAGED_BLOCK = (
    "# >>> aart setup: aart-github >>>\nexport AART=1\n# <<< aart setup: aart-github <<<"
)


def _installation() -> dict:
    return {
        "coordinate": COORDINATE,
        "artifact": {
            "type": "mcp",
            "name": "github-docker",
            "version": "1.0.0",
            "manifest_digest": f"sha256:{'a' * 64}",
            "object_digest": f"sha256:{'b' * 64}",
            "payload_digest": f"sha256:{'c' * 64}",
        },
        "profile": "claude",
        "profile_version": 1,
        "scope": "project",
        "requested_mode": "copy",
        "source": {
            "alias": "registry-a",
            "kind": "registry-git",
            "origin": "github.com/example/registry",
            "declared_id": "la-registry-a",
            "resolved_commit": "0" * 40,
            "subscription_ref": "main",
        },
        "effects": [
            {
                "kind": "write-file",
                "destination": ".mcp.json",
                "actual_mode": "copy",
                "created_destination": True,
                "overwrote": False,
                "installed_digest": f"sha256:{'d' * 64}",
                "source_path": "payload/x.json",
            }
        ],
        "setup_state_ref": SETUP_REF,
    }


def _record(block_path: str) -> SetupStateRecord:
    """One step only, and a file one -- so `verify` asks the filesystem and nothing else.

    A docker or Keychain claim would make this test depend on a daemon and a login session;
    `file.managed-block@1` is verified by reading a file, which a temporary directory provides.
    """

    return SetupStateRecord(
        artifact_type="mcp",
        artifact_name="github-docker",
        profile="claude",
        scope="project",
        status="configured",
        detail="Setup completed",
        source_label="registry-a (unverified)",
        installer_path="setup/installer.json",
        installer_hash="1" * 64,
        plan_hash="2" * 64,
        started_at="2026-08-15T09:00:00Z",
        finished_at="2026-08-15T09:00:42Z",
        exit_status=0,
        retry_command=f"aart marketplace setup {COORDINATE}@1.0.0 --yes",
        rollback_command=f"aart marketplace receipt undo {COORDINATE}",
        receipt=(
            {
                "step_id": "shell-block",
                "module": "file.managed-block@1",
                "path": block_path,
                "marker": "aart-github",
                "changed": True,
                "file_existed": False,
                "mode": 0o644,
                "prior_block": None,
                "installed_block": MANAGED_BLOCK,
                "disposition": "created",
            },
        ),
        object_digest=f"sha256:{'4' * 64}",
        recipe_digest=f"sha256:{'5' * 64}",
        trust="unverified",
        trust_evidence_digest=f"sha256:{'7' * 64}",
        policy_digest=f"sha256:{'8' * 64}",
        capability_plan_digest=f"sha256:{'9' * 64}",
        canonical_review_digest=f"sha256:{'6' * 64}",
        setup_state_ref=SETUP_REF,
    )


class ReceiptCommandTests(unittest.TestCase):
    """One installed, setup-bearing artifact on disk, read through the shipped command."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name).resolve()
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
        config = pathlib.Path(self.paths.user_config_file)
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_bytes(
            user_configuration_bytes(
                UserConfiguration(1, (), None, SyncSettings(), ReportingSettings())
            )
        )

        self.block = self.project / ".zshrc"
        self.block.write_text(MANAGED_BLOCK + "\n", encoding="utf-8")
        self.record = _record(str(self.block))

        manifest = pathlib.Path(
            install_state_paths(
                "project",
                project_root=str(self.project),
                user_home=str(self.home),
                data_root=self.paths.data_root,
            ).destination_path
        )
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps({"schema_version": 2, "installations": [_installation()]}),
            encoding="utf-8",
        )

        self.state_path = pathlib.Path(setup_state_file(self.paths.data_root, SETUP_REF))
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            dump_setup_state(SetupState((self.record,))) + "\n", encoding="utf-8"
        )

        self.location = ReceiptLocation(
            coordinate=COORDINATE,
            profile="claude",
            scope="project",
            setup_state_ref=SETUP_REF,
            state_path=str(self.state_path),
        )

    def _run(self, *argv: str) -> tuple[int, str]:
        output = io.StringIO()
        with (
            mock.patch.dict(os.environ, self.xdg, clear=False),
            contextlib.redirect_stdout(output),
            mock.patch("os.getcwd", return_value=str(self.project)),
        ):
            code = cli.main([*argv, "--project", str(self.project)])
        return code, output.getvalue()

    def test_show_writes_exactly_what_the_flag_mode_renderer_writes(self) -> None:
        code, text = self._run("marketplace", "receipt", "show", COORDINATE)

        self.assertEqual(code, 0, text)
        expected = render_receipt_payload(receipt_payload(self.record, location=self.location))
        written = text.splitlines()
        self.assertEqual(written[-len(expected) :], list(expected))

    def test_verify_asks_the_filesystem_and_reports_the_block_as_still_true(self) -> None:
        code, text = self._run("marketplace", "receipt", "verify", COORDINATE)

        self.assertEqual(code, 0, text)
        self.assertIn("Verification", text)
        self.assertIn("the managed block is present and unchanged", text)
        self.assertIn("false=0", text)

    def test_verify_sees_an_edited_block_as_false(self) -> None:
        self.block.write_text("# somebody edited this\n", encoding="utf-8")

        code, text = self._run("marketplace", "receipt", "verify", COORDINATE)

        self.assertIn("false=1", text)
        self.assertIn("block-present", text)
        # A false claim is a finding, and a finding must not report success to CI.
        self.assertNotEqual(code, 0, text)

    def test_an_unknown_coordinate_is_refused_with_remediation_not_a_traceback(self) -> None:
        code, text = self._run("marketplace", "receipt", "show", "mcp/never-installed")

        self.assertNotEqual(code, 0, text)
        self.assertIn("no installation of mcp/never-installed", text)
        self.assertIn("remediation:", text)

    def test_undo_reviews_first_and_changes_nothing_without_yes(self) -> None:
        before = self.state_path.read_bytes(), self.block.read_bytes()

        code, text = self._run("marketplace", "receipt", "undo", COORDINATE)

        self.assertEqual(code, 0, text)
        self.assertEqual((self.state_path.read_bytes(), self.block.read_bytes()), before)
        self.assertIn("re-run with --yes to apply this exact undo", text)

    def test_undo_applied_reverses_the_effect_and_rewrites_the_record(self) -> None:
        code, text = self._run("marketplace", "receipt", "undo", COORDINATE, "--yes")

        self.assertEqual(code, 0, text)
        self.assertFalse(self.block.exists(), "the file this run created is removed")
        self.assertIn("Undo outcome: skipped", text)
        self.assertIn("skipped", self.state_path.read_text(encoding="utf-8"))

    def test_an_unsupported_action_is_refused_by_the_parser_not_by_doing_nothing(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            with contextlib.redirect_stderr(io.StringIO()):
                self._run("marketplace", "receipt", "explode", COORDINATE)

        self.assertNotEqual(raised.exception.code, 0)


class CanonicalReceiptCommandTests(ReceiptCommandTests):
    """B-046: the same three verbs, over a setup run a *configured* install recorded.

    The canonical route writes no install-state manifest (D-128). What says an artifact is
    installed there is the receipt in `LocalReceiptStore`, and what says setup ran for it is that
    receipt's `setup_state_ref`. Every assertion is inherited: an operator asking about a
    configured installation must get the same answers, from the same commands, as one asking
    about a legacy installation -- otherwise a setup run that happened is one the machine cannot
    show, verify or undo.
    """

    def setUp(self) -> None:
        super().setUp()
        # The legacy manifest this artifact was found through is gone: what remains is exactly
        # what a configured install leaves behind.
        pathlib.Path(
            install_state_paths(
                "project",
                project_root=str(self.project),
                user_home=str(self.home),
                data_root=self.paths.data_root,
            ).destination_path
        ).unlink()

        root = str(self.project / "runtimes" / "github-docker")
        recorded = LocalReceiptStore(
            os.path.join(self.paths.data_root, "state")
        ).record_installation(
            ArtifactCoordinate(
                SourceAlias("registry-a"), ArtifactIdentity("mcp", "github-docker"), "1.0.0"
            ),
            PlacedArtifactReceipt(
                "mcp/github-docker",
                root,
                ObjectDigest("sha256", "c" * 64),
                (
                    ArtifactDelivery(
                        "claude",
                        f"{root}/payload",
                        str(self.project / ".mcp.json"),
                        DeliveryKind.FILE,
                        ObjectDigest("sha256", "d" * 64),
                    ),
                ),
                object_digest=ObjectDigest("sha256", "b" * 64),
                setup_state_ref=SETUP_REF,
            ),
        )
        self.assertIsInstance(recorded, Ok, getattr(recorded, "diagnostics", ()))
        # The one difference from the legacy route, and it is the canonical store being more
        # precise rather than different: a receipt is filed under the exact version installed,
        # while the manifest records a coordinate with the version left off. `show` prints what
        # the store holds.
        self.location = replace(self.location, coordinate=f"{COORDINATE}@1.0.0")


class CanonicalReceiptAbsenceTests(CanonicalReceiptCommandTests):
    """The three absences stay three sentences when the pointer comes off a receipt.

    `locate_setup_record` was written so that "never installed", "installed with no run recorded"
    and "points at a record that is gone" cannot be confused with each other, because an operator
    holding the wrong one of those has no idea what to do next. The receipt-backed locator has to
    keep that apart, and one of the three is now reachable in a way it was not before: a machine
    with configured installations and no install-state manifest at all.
    """

    def _forget_setup_pointer(self) -> None:
        store = LocalReceiptStore(os.path.join(self.paths.data_root, "state"))
        coordinate = ArtifactCoordinate(
            SourceAlias("registry-a"), ArtifactIdentity("mcp", "github-docker"), "1.0.0"
        )
        record = store.record(coordinate)
        self.assertIsInstance(record, Ok, getattr(record, "diagnostics", ()))
        assert isinstance(record, Ok)
        rewritten = store.record_installation(
            coordinate, replace(record.value.receipt, setup_state_ref=None)
        )
        self.assertIsInstance(rewritten, Ok, getattr(rewritten, "diagnostics", ()))

    def test_a_configured_installation_with_no_recorded_run_says_exactly_that(self) -> None:
        self._forget_setup_pointer()

        code, text = self._run("marketplace", "receipt", "show", COORDINATE)

        self.assertNotEqual(code, 0, text)
        self.assertIn("is installed and no setup run has been recorded for it", text)
        # Not the manifest's sentence: there is no manifest, and its absence says nothing about
        # an artifact the configured store knows perfectly well is installed.
        self.assertNotIn("this scope has no installation state", text)

    def test_a_pointer_whose_record_is_gone_is_its_own_refusal(self) -> None:
        self.state_path.unlink()

        code, text = self._run("marketplace", "receipt", "show", COORDINATE)

        self.assertNotEqual(code, 0, text)
        self.assertIn("points at setup record", text)
        self.assertIn("not present under the data root", text)

    def test_an_unknown_coordinate_on_a_configured_machine_names_the_coordinate(self) -> None:
        """The regression B-046 leaves behind if only the happy path is wired.

        With no install-state manifest the old reader answered every question with "this scope has
        no installation state", which on a machine whose installations are all configured is both
        false and useless -- it points the operator at a file that is never going to exist.
        """

        code, text = self._run("marketplace", "receipt", "show", "mcp/never-installed")

        self.assertNotEqual(code, 0, text)
        self.assertIn("no installation of mcp/never-installed in project scope", text)
        self.assertIn("aart marketplace status", text)

    def test_a_record_belonging_to_the_other_scope_is_refused_not_silently_shown(self) -> None:
        """The receipt store partitions nothing by scope, so only the record knows.

        Rebinding the answer to whatever the record says would mean `--scope project` printing a
        user-scope installation, which reads exactly like a correct answer to a question nobody
        asked.
        """

        self.state_path.write_text(
            dump_setup_state(SetupState((replace(self.record, scope="user"),))) + "\n",
            encoding="utf-8",
        )

        code, text = self._run("marketplace", "receipt", "show", COORDINATE)

        self.assertNotEqual(code, 0, text)
        self.assertIn("belongs to user scope, not project", text)
        self.assertIn("--scope user", text)

    def test_a_profile_the_receipt_never_served_matches_nothing(self) -> None:
        code, text = self._run("marketplace", "receipt", "show", COORDINATE, "--profile", "codex")

        self.assertNotEqual(code, 0, text)
        self.assertIn("no installation of", text)

    def test_the_profile_shown_is_the_one_the_record_says_setup_ran_for(self) -> None:
        """A receipt can serve several harnesses; setup ran once, for one of them.

        The second harness sorts *before* the one setup ran for, so a reader that answered with
        whichever profile the receipt happens to name first would print `aider` here. Only the
        record knows, and it is read before the answer is composed.
        """

        store = LocalReceiptStore(os.path.join(self.paths.data_root, "state"))
        coordinate = ArtifactCoordinate(
            SourceAlias("registry-a"), ArtifactIdentity("mcp", "github-docker"), "1.0.0"
        )
        held = store.record(coordinate)
        assert isinstance(held, Ok), held
        receipt = held.value.receipt
        second = replace(
            receipt.deliveries[0],
            harness="aider",
            destination=str(self.project / ".aider" / "mcp.json"),
        )
        rewritten = store.record_installation(
            coordinate, replace(receipt, deliveries=(*receipt.deliveries, second))
        )
        self.assertIsInstance(rewritten, Ok, getattr(rewritten, "diagnostics", ()))

        code, text = self._run("marketplace", "receipt", "show", COORDINATE)

        self.assertEqual(code, 0, text)
        self.assertIn(f"mcp/github-docker@{self.record.profile} (project)", text)
        self.assertNotIn("@aider", text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
