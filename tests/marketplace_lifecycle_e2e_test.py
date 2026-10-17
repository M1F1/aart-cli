"""End-to-end canonical lifecycle over a real temporary home, project, and source (LIFE02).

Nothing here is mocked below the CLI entry point: a real local source is synchronized into a real
managed snapshot, and the commands write into real project/user trees.  These tests exist to prove
that the JSON contract an agent depends on matches what actually lands on disk.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from aart_cli import cli
from aart_cli.configuration.model import (
    ConfiguredSource,
    SourceKind,
    SyncSettings,
    UserConfiguration,
)
from aart_cli.configuration.paths import Platform, resolve_config_paths
from aart_cli.configuration.schema import user_configuration_bytes
from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Ok
from tests.configured_installation_draft_e2e_test import AuthoredSetup
from tests.reference_registry import (
    BRANCH,
    ESSENTIALS,
    commit,
    memory,
    reference_snapshot,
    skill,
    write_reference_registry,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "protocol" / "native-source-v1"
_COORDINATE = "reference/skill/code-review"
_COLLECTION = "reference/collection/essentials"
#: Where a Registry installation of the Skill lands for Claude in a project.
_PLACED = Path(".claude/skills/code-review-reference-project")


def _unwrap(result):
    assert isinstance(result, Ok), result
    return result.value


class _Environment:
    """A real, isolated home/project/XDG environment with one synchronized local source."""

    def __init__(self, root: Path, source_location: Path | None = None) -> None:
        # A consumer reads only Registries (INV-269), so the reference content is published as an
        # approved Registry in a Git checkout of this environment's own. ``source_location`` names
        # a checkout a test prepared itself; either way it is writable, and a test that changes
        # what the Registry publishes edits it and calls :meth:`publish`.
        self.source_location = (
            source_location or write_reference_registry(root / "registry")
        ).resolve()
        self.root = root
        self.home = root / "home"
        self.project = root / "project"
        self.home.mkdir()
        self.project.mkdir()
        # ``HOME`` is what the command boundary expands; the XDG values only matter on Linux, so
        # both must point at this temporary home for the test to be hermetic on either platform.
        self.xdg = {
            "HOME": str(self.home),
            "AART_CLI_HOME": str(self.home / ".aart-cli"),
        }
        platform = Platform.DARWIN if os.sys.platform == "darwin" else Platform.LINUX
        self.paths = resolve_config_paths(
            platform,
            home=str(self.home),
            application_home=self.xdg["AART_CLI_HOME"],
        )
        self.source = ConfiguredSource(
            SourceAlias("reference"),
            SourceKind.REGISTRY_LOCAL,
            str(self.source_location),
            BRANCH,
            True,
        )
        config_path = Path(self.paths.user_config_file)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_bytes(
            user_configuration_bytes(UserConfiguration(1, (self.source,), None, SyncSettings()))
        )
        self._synchronize()

    def publish(self, message: str = "publish") -> str:
        """Commit what the checkout holds and synchronize it, as a Maintainer's release would."""

        revision = commit(self.source_location, message)
        self._synchronize()
        return revision

    def _synchronize(self) -> None:
        # The consumer's own refresh: the Registry is validated as a Registry, not as a source.
        stdout = io.StringIO()
        with mock.patch.dict(os.environ, self.xdg, clear=False), contextlib.redirect_stdout(stdout):
            code = cli.main(["consume", "registry", "sync", "--alias", "reference", "--json"])
        assert code == 0, stdout.getvalue()

    def run(self, *argv: str):
        """Invoke the real CLI and return ``(exit_code, parsed_json)``.

        ``--project`` is omitted for user-scope runs: the CLI rejects that combination on purpose,
        because user targets are resolved from the home directory rather than a project.
        """

        scoped_to_user = "user" in argv
        arguments = [*argv, "--json"]
        if not scoped_to_user:
            arguments = [*argv, "--project", str(self.project), "--json"]
        stdout = io.StringIO()
        with (
            mock.patch.dict(os.environ, self.xdg, clear=False),
            contextlib.redirect_stdout(stdout),
            mock.patch("os.getcwd", return_value=str(self.project)),
        ):
            code = cli.main(arguments)
        raw = stdout.getvalue()
        return code, (json.loads(raw) if raw.strip() else None)

    def run_text(self, *argv: str) -> tuple[int, str]:
        """Invoke the real CLI without ``--json`` and return ``(exit_code, stdout)``.

        The same command, asked for the other rendering.  Tests that compare the two need a way to
        ask for the human one; everything else about the invocation is identical on purpose, so a
        difference between them is a difference in rendering rather than in setup.
        """

        scoped_to_user = "user" in argv
        arguments = list(argv) if scoped_to_user else [*argv, "--project", str(self.project)]
        stdout = io.StringIO()
        with (
            mock.patch.dict(os.environ, self.xdg, clear=False),
            contextlib.redirect_stdout(stdout),
            mock.patch("os.getcwd", return_value=str(self.project)),
        ):
            code = cli.main(arguments)
        return code, stdout.getvalue()


@contextlib.contextmanager
def _environment(source_location: Path | None = None):
    with tempfile.TemporaryDirectory() as raw:
        yield _Environment(Path(raw).resolve(), source_location)


#: The file the declared setup writes, and nothing else does.
_CONFIGURED = ".code-review.toml"

#: One managed block in one project file: the smallest setup that is unmistakably observable. It
#: needs no tool, no secret and no network, so nothing about the environment can explain the file
#: being absent except that the recipe did not run.
_RECIPE = {
    "schema_version": 2,
    "protocol_version": 2,
    "artifact": "skill/code-review",
    "purpose": "Write the configuration file the Skill reads.",
    "platforms": ["darwin"],
    "help_urls": [{"label": "Setup help", "url": "https://example.test/code-review/setup"}],
    "required_tools": [],
    "capabilities": ["filesystem"],
    "inputs": [],
    "steps": [
        {
            "id": "config",
            "use": "file.managed-block@1",
            "with": {"file": _CONFIGURED, "content": "enabled = true"},
        }
    ],
}


@contextlib.contextmanager
def _environment_with_setup(setup: AuthoredSetup):
    """The reference Registry with its Skill packaged to declare `setup`.

    The declaration enters where a packager puts it -- a `setup` reference on `artifact.json`, the
    recipe beside the payload and the package root `SETUP.md` the manual route requires -- and the
    Registry is promoted, committed and synchronized as it stands rather than patched afterwards.
    """

    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw).resolve()
        location = write_reference_registry(
            root / "registry",
            reference_snapshot(
                skill(platforms=("darwin", "linux")), memory(), ESSENTIALS, setup=setup
            ),
        )
        machine = root / "machine"
        machine.mkdir()
        yield _Environment(machine, location)


def _environment_declaring_setup():
    return _environment_with_setup(
        AuthoredSetup(_RECIPE, "Write `enabled = true` into .code-review.toml yourself.\n")
    )


class LifecycleCopyE2ETest(unittest.TestCase):
    def test_collection_install_materializes_every_expanded_member(self) -> None:
        with _environment() as env:
            code, payload = env.run(
                "consume", "install", _COLLECTION, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["finalized"])
            installed = env.project / _PLACED / "SKILL.md"
            self.assertTrue(installed.is_file(), sorted(map(str, env.project.rglob("*"))))

    def test_review_only_install_writes_nothing_to_the_project(self) -> None:
        with _environment() as env:
            code, payload = env.run("consume", "install", _COORDINATE, "--profile", "claude")

            self.assertEqual(code, 0, payload)
            self.assertFalse(payload["finalized"])
            self.assertTrue(payload["review"]["items"])
            self.assertEqual(list(env.project.iterdir()), [])

    def test_copy_install_materializes_the_payload_and_is_idempotent(self) -> None:
        with _environment() as env:
            code, payload = env.run(
                "consume", "install", _COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["finalized"])
            self.assertEqual(payload["session_status"], "succeeded")
            installed = env.project / _PLACED / "SKILL.md"
            self.assertTrue(installed.is_file(), sorted(map(str, env.project.rglob("*"))))
            self.assertFalse(installed.is_symlink())

            repeat_code, repeat = env.run(
                "consume", "install", _COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(repeat_code, 0, repeat)
            self.assertEqual([item["status"] for item in repeat["items"]], ["current"])
            self.assertEqual(repeat["receipt"]["artifacts"][0]["steps"], [])

    def test_user_scope_install_stays_out_of_the_project_tree(self) -> None:
        with _environment() as env:
            code, payload = env.run(
                "consume",
                "install",
                _COORDINATE,
                "--profile",
                "claude",
                "--scope",
                "user",
                "--yes",
            )

            self.assertEqual(code, 0, payload)
            self.assertFalse((env.project / _PLACED).exists())
            self.assertTrue(any(env.home.rglob("SKILL.md")), sorted(map(str, env.home.rglob("*"))))


class LifecycleUpdateStatusUninstallE2ETest(unittest.TestCase):
    def test_update_on_a_current_installation_is_a_no_op(self) -> None:
        with _environment() as env:
            env.run("consume", "install", _COORDINATE, "--profile", "claude", "--yes")

            code, payload = env.run(
                "consume", "update", _COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, payload)
            self.assertEqual([item["status"] for item in payload["items"]], ["current"])
            self.assertEqual(payload["receipt"]["artifacts"][0]["steps"], [])

    def test_status_reports_the_installed_artifact_without_changing_it(self) -> None:
        with _environment() as env:
            env.run("consume", "install", _COORDINATE, "--profile", "claude", "--yes")
            installed = env.project / _PLACED / "SKILL.md"
            before = installed.read_bytes()

            code, payload = env.run("consume", "status", "--profile", "claude")

            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["operation"], "marketplace.status")
            self.assertEqual(installed.read_bytes(), before)

    def test_forced_reinstall_upserts_the_record_instead_of_duplicating_it(self) -> None:
        # ``--force`` authorizes overwriting an already-installed artifact.  The record it leaves
        # must still be one record: a duplicate would make later status and uninstall ambiguous.
        with _environment() as env:
            env.run("consume", "install", _COORDINATE, "--profile", "claude", "--yes")

            code, payload = env.run(
                "consume", "install", _COORDINATE, "--profile", "claude", "--force", "--yes"
            )

            self.assertEqual(code, 0, payload)
            status_code, status = env.run("consume", "status", "--profile", "claude")
            self.assertEqual(status_code, 0, status)
            self.assertEqual([item["key"] for item in status["items"]], [f"{_COORDINATE}@1.0.0"])

    def test_a_bare_update_selects_every_installation_in_the_scope(self) -> None:
        # ``update`` without coordinates is the routine operator action.  It must reconcile the
        # whole recorded scope, not silently do nothing because no coordinate was named.
        with _environment() as env:
            env.run("consume", "install", _COORDINATE, "--profile", "claude", "--yes")

            code, payload = env.run("consume", "update", "--profile", "claude", "--yes")

            self.assertEqual(code, 0, payload)
            self.assertEqual(len(payload["items"]), 1, payload)
            self.assertEqual(payload["items"][0]["status"], "current")

    def test_review_and_json_are_observations_that_change_no_effect(self) -> None:
        # ``--json`` selects a rendering.  An agent reading the plan must be able to trust that
        # asking for it never installs anything the human-readable path would not have.
        with _environment() as env:
            code, payload = env.run("consume", "install", _COORDINATE, "--profile", "claude")

            self.assertEqual(code, 0, payload)
            self.assertFalse(payload["finalized"])
            self.assertEqual(list(env.project.iterdir()), [], "review must not touch the project")

    def test_two_reviews_seconds_apart_produce_one_digest_to_authorize(self) -> None:
        # The review digest is consent a human carries to a later ``--yes``.  This runs the real CLI
        # twice across a real second boundary: the workspace is untouched between them, so the
        # digest must not move.
        with _environment() as env:
            _, first = env.run("consume", "install", _COORDINATE, "--profile", "claude")
            time.sleep(1.2)
            _, second = env.run("consume", "install", _COORDINATE, "--profile", "claude")

            self.assertEqual(first["review_digest"], second["review_digest"])
            self.assertEqual(first["review"], second["review"])

    def test_expect_carries_one_reviewed_decision_across_two_commands(self) -> None:
        # The workflow the review text prescribes: read the digest from a review, then finalize that
        # exact plan in a second command.  A digest that no longer describes the plan must refuse.
        with _environment() as env:
            _, review = env.run("consume", "install", _COORDINATE, "--profile", "claude")
            reviewed = review["review_digest"]

            stale = "sha256:" + "0" * 64
            code, refused = env.run(
                "consume",
                "install",
                _COORDINATE,
                "--profile",
                "claude",
                "--yes",
                "--expect",
                stale,
            )

            self.assertEqual(code, 1)
            self.assertFalse(refused["ok"])
            self.assertFalse(refused["finalized"])
            self.assertEqual(refused["expected_review_digest"], stale)
            self.assertEqual(refused["review_digest"], reviewed)
            self.assertEqual(
                refused["diagnostics"][0]["code"],
                "consumer-review-mismatch",
            )
            self.assertIn("review", refused, "a refusal must show the plan that would have run")
            self.assertEqual(list(env.project.iterdir()), [], "a refusal writes nothing")

            code, applied = env.run(
                "consume",
                "install",
                _COORDINATE,
                "--profile",
                "claude",
                "--yes",
                "--expect",
                reviewed,
            )

            self.assertEqual(code, 0, applied)
            self.assertTrue(applied["finalized"])
            self.assertTrue((env.project / _PLACED).exists())

    def test_yes_without_expect_keeps_its_meaning(self) -> None:
        with _environment() as env:
            code, applied = env.run(
                "consume", "install", _COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, applied)
            self.assertTrue(applied["finalized"])

    def test_uninstall_removes_the_installed_payload(self) -> None:
        with _environment() as env:
            env.run("consume", "install", _COORDINATE, "--profile", "claude", "--yes")
            installed = env.project / _PLACED
            self.assertTrue(installed.exists())

            code, payload = env.run(
                "consume", "uninstall", _COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, payload)
            self.assertFalse(installed.exists(), sorted(map(str, env.project.rglob("*"))))


class LifecycleDiagnosticsE2ETest(unittest.TestCase):
    def test_an_unknown_coordinate_reports_a_structured_not_found_diagnostic(self) -> None:
        with _environment() as env:
            code, payload = env.run(
                "consume", "install", "reference/skill/absent", "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 1)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["diagnostics"][0]["code"], "artifact-not-found")

    def test_an_unknown_profile_is_rejected_before_anything_is_written(self) -> None:
        with _environment() as env:
            code, payload = env.run("consume", "install", _COORDINATE, "--profile", "nope", "--yes")

            self.assertEqual(code, 1)
            self.assertFalse(payload["ok"])
            self.assertEqual(list(env.project.iterdir()), [])

    def test_a_profile_outside_the_declared_compatibility_is_refused(self) -> None:
        # The fixture declares ``claude``/``tabnine``.  A known-but-undeclared profile must be
        # refused with the allowed set named, so the operator can pick a profile that works
        # instead of guessing why an install produced nothing.
        with _environment() as env:
            code, payload = env.run(
                "consume", "install", _COORDINATE, "--profile", "opencode", "--yes"
            )

            self.assertEqual(code, 1)
            diagnostic = payload["diagnostics"][0]
            self.assertEqual(diagnostic["code"], "artifact-placement-unavailable")
            self.assertIn("supported profiles: claude, tabnine", diagnostic["message"])
            self.assertEqual(list(env.project.iterdir()), [])

    def test_an_unreadable_install_state_is_a_typed_refusal_not_a_crash(self) -> None:
        # Reading damaged state must fail closed with a diagnostic rather than tracebacking or,
        # worse, treating the project as if nothing were installed and reinstalling over it.
        with _environment() as env:
            env.run("consume", "install", _COORDINATE, "--profile", "claude", "--yes")
            (state,) = (Path(env.paths.data_root) / "state" / "installations").iterdir()
            state.write_text("{ this is not valid json ]", encoding="utf-8")

            code, payload = env.run("consume", "status", "--profile", "claude")

            self.assertNotEqual(code, 0)
            self.assertFalse(payload["ok"])
            self.assertTrue(payload["diagnostics"])

    def test_a_malformed_coordinate_reports_the_accepted_grammar(self) -> None:
        with _environment() as env:
            code, payload = env.run(
                "consume", "install", "code-review", "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 1)
            self.assertIn("<source>/<kind>/<name>", payload["diagnostics"][0]["message"])

    def test_setup_on_an_artifact_that_declares_none_says_so_and_changes_nothing(self) -> None:
        with _environment() as env:
            env.run("consume", "install", _COORDINATE, "--profile", "claude", "--yes")
            before = sorted(map(str, env.project.rglob("*")))

            code, payload = env.run("consume", "setup", _COORDINATE, "--profile", "claude", "--yes")

            self.assertEqual(code, 1, payload)
            self.assertEqual(
                payload["diagnostics"][0]["message"],
                "selected configured installations declare no setup",
            )
            self.assertEqual(sorted(map(str, env.project.rglob("*"))), before)

    def test_offline_install_from_the_published_snapshot_succeeds(self) -> None:
        with _environment() as env:
            code, payload = env.run(
                "consume", "install", _COORDINATE, "--profile", "claude", "--offline", "--yes"
            )

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["finalized"])
            self.assertTrue((env.project / _PLACED / "SKILL.md").is_file())


@unittest.skipUnless(
    os.sys.platform == "darwin",
    "the setup engine accepts only darwin recipes (setup.py:562), so applying one elsewhere is "
    "refused for the platform before any of these boundaries is reached",
)
class DeclaredSetupE2ETest(unittest.TestCase):
    """The route on which declared setup runs, end to end, from the CLI, over a local Registry.

    A consumer installs only from a Registry (INV-269), and what a Registry publishes is reviewed,
    so no source-trust gate stands in front of the recipe: the gate that remains is the effects
    themselves. An install reviews the plan and applies none of it, `setup` without
    `--approve-setup-effects` does the same, and only the approval writes the file.
    """

    #: Install first. Setup configures what is installed, so there is nothing to configure before.
    def _installed(self, env) -> dict:
        code, payload = env.run("consume", "install", _COORDINATE, "--profile", "claude", "--yes")
        self.assertEqual(code, 0, payload)
        self.assertFalse((env.project / _CONFIGURED).exists())
        return payload

    def _reviewed_and_not_applied(self, env, setup: dict) -> None:
        self.assertEqual(setup["planning_failures"], [])
        planned = setup["planned"]
        self.assertEqual([item["trust"] for item in planned], ["registry-reviewed"])
        self.assertEqual([item["recipe"] for item in planned], ["setup/installer.json"])
        self.assertEqual(
            [effect["target"] for effect in planned[0]["effects"]],
            [str(env.project / _CONFIGURED)],
        )
        self.assertEqual([effect["capability"] for effect in planned[0]["effects"]], ["filesystem"])
        self.assertEqual([item["status"] for item in setup["items"]], ["cancelled"])
        self.assertEqual(setup["configured"], 0)
        self.assertFalse((env.project / _CONFIGURED).exists())

    def test_install_names_the_setup_it_did_not_run_instead_of_staying_silent(self) -> None:
        with _environment_declaring_setup() as env:
            payload = self._installed(env)

            self._reviewed_and_not_applied(env, payload["setup"])
            self.assertEqual(
                [item["retry"] for item in payload["setup"]["items"]],
                [
                    f"aart-cli consume setup {_COORDINATE} --profile claude --scope project "
                    "--yes --approve-setup-effects"
                ],
            )

    def test_a_reviewed_plan_applies_nothing_until_its_effects_are_approved(self) -> None:
        """`--yes` confirms the run; it does not consent to the effects the plan names."""

        with _environment_declaring_setup() as env:
            self._installed(env)

            code, payload = env.run("consume", "setup", _COORDINATE, "--profile", "claude", "--yes")

            self.assertNotEqual(code, 0)
            self._reviewed_and_not_applied(env, payload["setup"])

    def test_an_approved_setup_writes_the_block_it_reviewed(self) -> None:
        with _environment_declaring_setup() as env:
            self._installed(env)

            code, payload = env.run(
                "consume",
                "setup",
                _COORDINATE,
                "--profile",
                "claude",
                "--yes",
                "--approve-setup-effects",
            )

            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["setup"]["configured"], 1)
            self.assertEqual(payload["setup"]["incomplete"], 0)
            self.assertEqual([item["status"] for item in payload["setup"]["items"]], ["configured"])
            # The managed block, delimited so a later run owns exactly what it wrote and nothing a
            # person added around it.
            written = (env.project / _CONFIGURED).read_text(encoding="utf-8")
            self.assertIn("enabled = true", written)
            self.assertIn("aart setup: skill/code-review@claude:config", written)


if __name__ == "__main__":  # pragma: no cover - unittest entry point
    unittest.main()
