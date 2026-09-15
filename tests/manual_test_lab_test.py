"""The manual acceptance ecosystem is fresh, isolated and marker-bounded (QA-049/QA-051)."""

from __future__ import annotations

import json
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock


def _first_sync_states(
    env: dict[str, str], project: pathlib.Path, alias: str
) -> tuple[tuple[str, str, str], ...]:
    """One real maintainer Source Sync, reported as (coordinate, state, findings) per Candidate."""

    driver = textwrap.dedent(
        """
        import os, sys
        from pathlib import Path
        from agent_artifacts.configuration.model import OrganizationPolicy, SourceAlias
        from agent_artifacts.configuration.paths import Platform, resolve_config_paths
        from agent_artifacts.configuration.policy import RuntimeOverrides, apply_configuration
        from agent_artifacts.configuration.schema import parse_user_configuration
        from agent_artifacts.domain.result import Ok
        from agent_artifacts.io.maintainer_sync import (
            complete_configured_source_sync,
            prepare_configured_source_sync,
        )

        paths = resolve_config_paths(
            Platform.DARWIN if sys.platform == "darwin" else Platform.LINUX,
            home=os.environ["HOME"],
            xdg_config_home=os.environ.get("XDG_CONFIG_HOME"),
            xdg_data_home=os.environ.get("XDG_DATA_HOME"),
            xdg_cache_home=os.environ.get("XDG_CACHE_HOME"),
        )
        parsed = parse_user_configuration(Path(paths.user_config_file).read_bytes())
        effective = apply_configuration(parsed.value, RuntimeOverrides(), OrganizationPolicy(1))
        prepared = prepare_configured_source_sync(
            effective.value, SourceAlias(sys.argv[1]), data_root=paths.data_root, offline=False
        )
        if not isinstance(prepared, Ok):
            raise SystemExit("refused: " + prepared.diagnostics[0].message)
        done = complete_configured_source_sync(
            effective.value, prepared.value, reviewed_digest=prepared.value.review_digest
        )
        if not isinstance(done, Ok):
            raise SystemExit("failed: " + done.diagnostics[0].message)
        for bundle in done.value.scan.active:
            candidate = bundle.candidate
            print(
                candidate.artifact.coordinate.artifact,
                candidate.state.value,
                ",".join(item.code for item in candidate.findings),
                sep="|",
            )
        """
    )
    finished = subprocess.run(
        (sys.executable, "-c", driver, alias),
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
    )
    if finished.returncode != 0:
        raise AssertionError(finished.stdout + finished.stderr)
    return tuple(
        tuple(line.split("|", 2))  # type: ignore[misc]
        for line in finished.stdout.splitlines()
        if line
    )


class ManualTestLabTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name) / "manual-lab"

    def test_setup_builds_a_fresh_ecosystem_with_a_credential_mcp(self) -> None:
        from scripts.manual_test import setup_lab

        first = setup_lab(self.root)
        first_marker = json.loads((self.root / ".aart-manual-lab.json").read_text())
        second = setup_lab(self.root)
        second_marker = json.loads((self.root / ".aart-manual-lab.json").read_text())

        self.assertNotEqual(first.run_id, second.run_id)
        self.assertNotEqual(first_marker["run_id"], second_marker["run_id"])
        self.assertTrue(second.branch.startswith("manual/"))
        self.assertTrue((self.root / "consumer-project").is_dir())
        self.assertFalse((self.root / "consumer-home/.config/agent-artifacts/config.json").exists())
        manifest = json.loads((self.root / "repositories/mcp/dummy-mcp/aart.json").read_text())
        self.assertEqual(manifest["inputs"][0]["kind"], "secret")
        self.assertEqual(manifest["inputs"][0]["id"], "dummy-token")
        # CP-23 task 13: the lab credential demonstrates complete guidance, including how a
        # manually issued value is obtained without a link (D-263).
        guidance = manifest["inputs"][0]["help"]
        self.assertEqual(set(guidance), {"label", "description", "format_hint", "obtain_from"})
        self.assertNotIn("url", guidance["obtain_from"])
        self.assertIn("disposable", guidance["obtain_from"]["label"])
        self.assertEqual(
            manifest["compatibility"]["harnesses"],
            ["claude", "opencode", "tabnine"],
        )
        # CP-23 task 16: an ordinary value beside the credential, so the manual run can answer it
        # at install and edit it per harness under User variables and credentials (D-264–D-267).
        (config,) = [item for item in manifest["inputs"] if item["kind"] == "config"]
        self.assertEqual(config["id"], "dummy-user")
        self.assertEqual(config["inject"], {"type": "environment", "variable": "AART_DUMMY_USER"})
        self.assertIn(
            "AART_DUMMY_USER", (self.root / "repositories/mcp/dummy-mcp/server.py").read_text()
        )
        skill_manifest = json.loads(
            (self.root / "repositories/skill/manual-check/aart.json").read_text()
        )
        self.assertEqual(
            skill_manifest["compatibility"]["harnesses"],
            ["claude", "opencode", "tabnine"],
        )
        registry_files = tuple(
            (self.root / "repositories/registry/registry/versions").rglob("*.json")
        )
        self.assertTrue(registry_files)
        instructions = (self.root / "START_HERE.md").read_text()
        self.assertIn(second.branch, instructions)
        self.assertIn("dummy-token", instructions)
        self.assertNotIn("export HOME", instructions)

    def test_an_empty_registry_lab_leaves_the_whole_maintainer_run_to_the_operator(self) -> None:
        """`QA-054`: the maintainer walkthrough is only a test if the registry starts with nothing.

        The default lab publishes both fixtures so consumer testing is not blocked on publication.
        That is the opposite of what testing the Maintainer surface needs: every screen from
        Initialize Registry through promotion has already been passed by the setup script, so an
        operator walking the TUI is re-reading a result rather than producing one.
        """

        from scripts.manual_test import setup_lab

        lab = setup_lab(self.root, empty_registry=True)

        registry = self.root / "repositories/registry"
        # The author sources still exist: an author publishes independently of any registry, and
        # the maintainer run needs something to discover.
        self.assertTrue((self.root / "repositories/skill/manual-check/aart.json").is_file())
        self.assertTrue((self.root / "repositories/mcp/dummy-mcp/aart.json").is_file())
        # The registry does not. Not its manifest, not a promotion, not a published version.
        self.assertFalse((registry / "aart-registry.json").exists())
        self.assertEqual((), tuple((registry / "registry").rglob("*.json")))
        self.assertEqual((), tuple((registry / "artifacts").rglob("*.json")))
        # And no configured Source either: adding them is itself a Maintainer screen under test.
        self.assertFalse(
            (self.root / "maintainer-home/.config/agent-artifacts/config.json").exists()
        )
        instructions = (self.root / "START_HERE.md").read_text()
        self.assertIn(lab.branch, instructions)
        self.assertIn("Initialize Registry", instructions)
        # The operator reads these instructions before any document, and the fabricated origin is
        # the first thing that does not explain itself, so it is explained where it is met.
        self.assertIn("manual.aart.test", instructions)
        self.assertIn("insteadOf", instructions)
        self.assertIn("never resolves on", instructions)

    def test_the_default_lab_still_arrives_published(self) -> None:
        """The consumer-first route CP-20 built is unchanged by the maintainer-first one."""

        from scripts.manual_test import setup_lab

        setup_lab(self.root)

        self.assertTrue((self.root / "repositories/registry/aart-registry.json").is_file())
        self.assertTrue(
            tuple((self.root / "repositories/registry/registry/versions").rglob("*.json"))
        )

    def test_the_first_sync_of_an_untouched_lab_finds_the_registry_already_agrees(self) -> None:
        """`QA-061`: a fixture that vendored different bytes than it published makes AART lie.

        A promoted version records the `input_digest` of the exact manifest bytes and payload it
        vendored, and Source Sync recomputes that digest from the author repository.  When the lab
        wrote `json.dumps(manifest)` into the Registry and `json.dumps(manifest, indent=2)` into
        `skill.git`, the payload matched and the manifest did not, so the very first Sync of an
        untouched lab reported every artifact `invalid` with `registry-version-immutable` -- a real
        product refusal, fired by a fixture that disagreed with itself.  This drives the operator's
        own first Sync rather than comparing bytes, because the digest is what decides.
        """

        from scripts.manual_test import setup_lab, shell_environment

        lab = setup_lab(self.root)
        env, project = shell_environment(self.root, "maintainer")
        for alias, kind, url, default in (
            ("manual-registry", "registry-git", "registry.git", "--default"),
            ("manual-skill", "source-git", "skill.git", "--no-default"),
        ):
            added = subprocess.run(
                (
                    sys.executable,
                    "-m",
                    "agent_artifacts.cli",
                    "source",
                    "add",
                    "--alias",
                    alias,
                    "--kind",
                    kind,
                    "--location",
                    f"https://manual.aart.test/{url}",
                    "--ref",
                    lab.branch,
                    default,
                ),
                cwd=project,
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(added.returncode, 0, added.stderr)

        states = _first_sync_states(env, project, "manual-skill")

        self.assertTrue(states, "the first Sync produced no Candidate at all")
        for coordinate, state, findings in states:
            self.assertNotIn(
                "registry-version-immutable",
                findings,
                f"{coordinate}: the lab published bytes its own Source does not contain",
            )
            self.assertEqual(state, "promoted", f"{coordinate} was {state}")

    def test_a_lab_shell_is_described_for_each_role_without_touching_the_real_home(self) -> None:
        """`QA-057`: the CLI route needs the lab's environment without exporting it by hand.

        The TUI route has `open`; the CLI route had nothing, so its procedure told the operator to
        paste four environment variables in front of every command. That is both unreadable and the
        one thing the lab exists to avoid -- a mistyped HOME runs a manual test against real state.
        """

        from scripts.manual_test import setup_lab, shell_environment

        setup_lab(self.root, empty_registry=True)

        for role, project in (
            ("maintainer", "repositories/registry"),
            ("consumer", "consumer-project"),
        ):
            with self.subTest(role=role):
                env, cwd = shell_environment(self.root, role)

                # The lab resolves its own root, so a platform that reaches /tmp through a symlink
                # still gets one absolute answer rather than two spellings of it.
                resolved = self.root.resolve()
                home = str(resolved / f"{role}-home")
                self.assertEqual(home, env["HOME"])
                self.assertEqual(str(resolved / project), str(cwd))
                self.assertTrue(env["XDG_CONFIG_HOME"].startswith(home))
                self.assertTrue(env["XDG_DATA_HOME"].startswith(home))
                self.assertTrue(env["XDG_CACHE_HOME"].startswith(home))

    @unittest.skipUnless(sys.platform == "darwin", "the Keychain only exists on macOS")
    def test_each_lab_home_owns_a_keychain_so_no_reset_is_ever_offered(self) -> None:
        """`QA-084`: a manual test that makes macOS offer to reset a keychain is a hazard.

        `security` resolves the default keychain from `HOME`, and the lab home had a `.config` and
        a `.cache` and nothing else -- so the credential step found no keychain and macOS offered
        the one thing a manual test must never make reachable: `Reset To Defaults`.  The lab now
        creates its own keychain, points its own `HOME` at it, and leaves it unlocked, so the write
        lands there and the operator's real keychain is never a candidate.
        """

        from scripts.manual_test import setup_lab, shell_environment

        setup_lab(self.root, empty_registry=True)

        for role in ("maintainer", "consumer"):
            with self.subTest(role=role):
                env, _project = shell_environment(self.root, role)
                keychain = pathlib.Path(env["HOME"]) / "Library/Keychains/aart-manual.keychain-db"
                self.assertTrue(keychain.is_file(), "the lab home has no keychain of its own")

                resolved = subprocess.run(
                    ("/usr/bin/security", "default-keychain"),
                    env=env,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(resolved.returncode, 0, resolved.stderr)
                self.assertIn(str(keychain.resolve()), resolved.stdout)

                # The write the credential step makes, run here without a person: it has to reach
                # the lab's keychain rather than raise a dialog about a missing one.
                stored = subprocess.run(
                    (
                        "/usr/bin/security",
                        "add-generic-password",
                        "-a",
                        "aart",
                        "-s",
                        "qa-084-probe",
                        "-w",
                        "not-a-secret",
                    ),
                    env=env,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(stored.returncode, 0, stored.stderr)
                found = subprocess.run(
                    (
                        "/usr/bin/security",
                        "find-generic-password",
                        "-a",
                        "aart",
                        "-s",
                        "qa-084-probe",
                    ),
                    env=env,
                    capture_output=True,
                    text=True,
                )
                self.assertIn(str(keychain.resolve()), found.stdout)

    @unittest.skipUnless(sys.platform == "darwin", "the Keychain only exists on macOS")
    def test_the_lab_keychain_never_becomes_the_real_one(self) -> None:
        """The whole point is isolation: the lab's choice must not be visible outside the lab."""

        from scripts.manual_test import setup_lab

        before = subprocess.run(
            ("/usr/bin/security", "default-keychain"), capture_output=True, text=True
        ).stdout

        setup_lab(self.root, empty_registry=True)

        after = subprocess.run(
            ("/usr/bin/security", "default-keychain"), capture_output=True, text=True
        ).stdout
        self.assertEqual(before, after)
        self.assertNotIn("aart-manual", after)

    def test_a_lab_shell_refuses_a_role_the_lab_does_not_have(self) -> None:
        from scripts.manual_test import setup_lab, shell_environment

        setup_lab(self.root, empty_registry=True)

        with self.assertRaises(ValueError):
            shell_environment(self.root, "author")

    def test_reset_refuses_an_unmarked_directory_and_removes_a_marked_lab(self) -> None:
        from scripts.manual_test import reset_lab, setup_lab

        self.root.mkdir(parents=True)
        important = self.root / "not-aart.txt"
        important.write_text("keep\n")
        with self.assertRaises(ValueError):
            reset_lab(self.root)
        self.assertTrue(important.exists())

        important.unlink()
        self.root.rmdir()
        setup_lab(self.root)
        immutable = self.root / "consumer-home/.local/share/agent-artifacts/immutable.json"
        immutable.parent.mkdir(parents=True, exist_ok=True)
        immutable.write_text("owned\n")
        immutable.chmod(stat.S_IRUSR)
        reset_lab(self.root)
        self.assertFalse(self.root.exists())

    def test_reset_clears_a_payload_delivered_into_a_read_only_directory(self) -> None:
        """Setup failed on a real lab: a vendored payload directory is `r-x`, its files writable.

        Unlinking needs write permission on the directory holding the file, not on the file, so
        making the file writable -- all the old error handler did -- could never let it go.
        """

        from scripts.manual_test import reset_lab, setup_lab

        setup_lab(self.root)
        payload = self.root / "repositories/registry/.agent-artifacts/runtimes/lab/mcp/payload"
        payload.mkdir(parents=True)
        (payload / "server.py").write_text("owned\n")
        (payload / "mcp.json").write_text("{}\n")
        (payload / "mcp.json").chmod(stat.S_IRUSR)
        payload.chmod(stat.S_IRUSR | stat.S_IXUSR)
        self.addCleanup(lambda: payload.is_dir() and payload.chmod(stat.S_IRWXU))

        reset_lab(self.root)

        self.assertFalse(self.root.exists())

    def test_the_marker_is_the_last_thing_a_reset_removes(self) -> None:
        """The ordering that decides whether a failed reset is recoverable.

        A single `shutil.rmtree(root)` walks the whole tree in directory order, so it can unlink
        the marker and *then* fail on some later entry -- leaving a half-deleted lab that nothing
        owns. Reset refuses it, and setup refuses it too because setup resets first, so the
        operator's only way forward is an unguarded `rm -rf` on a path the tool has just told them
        not to trust.

        What makes that impossible is that the root is only ever swept once nothing but the marker
        is left in it, which is what this observes.
        """

        from scripts.manual_test import MARKER, reset_lab, setup_lab

        setup_lab(self.root)
        real = shutil.rmtree
        root = self.root.resolve()
        remaining: list[set[str]] = []

        def recording(target, **keywords):
            if pathlib.Path(target).resolve() == root:
                remaining.append({entry.name for entry in root.iterdir()})
            real(target, **keywords)

        with mock.patch("scripts.manual_test.shutil.rmtree", recording):
            reset_lab(self.root)

        self.assertFalse(root.exists())
        self.assertEqual([{MARKER}], remaining)

    def test_the_refusal_hands_back_a_recovery_that_actually_clears_the_lab(self) -> None:
        """`QA-085`: the way out of an unmarked lab has to be a way out that works.

        The operator hit a lab that had lost its marker and could neither reset it nor set up over
        it, because setup resets first. Refusing is right -- an unmarked directory is not this
        tool's to delete -- but a refusal with no way forward leaves an unguarded `rm -rf` on a
        path the tool has just said not to trust as the only move.

        So the refusal prints a command, and this runs it. It also runs the obvious command first,
        to show why the printed one says more than that: an installed payload is delivered
        read-only, directories included, so `rm -rf` alone stops at the first artifact root.
        """

        from scripts.manual_test import MARKER, reset_lab, setup_lab

        setup_lab(self.root)
        sealed = self.root / "consumer-home/.local/share/agent-artifacts/sealed"
        sealed.mkdir(parents=True, exist_ok=True)
        (sealed / "payload.json").write_text("owned\n")
        sealed.chmod(stat.S_IRUSR | stat.S_IXUSR)
        # Only so a failure partway through this test does not also break the tempdir's own
        # cleanup, which is exactly the trap the test is about.
        self.addCleanup(lambda: sealed.is_dir() and sealed.chmod(stat.S_IRWXU))
        (self.root / MARKER).unlink()

        with self.assertRaises(ValueError) as refusal:
            reset_lab(self.root)

        blunt = subprocess.run(
            ["rm", "-rf", str(self.root)], capture_output=True, text=True, check=False
        )
        self.assertNotEqual(blunt.returncode, 0, blunt.stderr)
        self.assertTrue(self.root.exists())

        recovery = str(refusal.exception).splitlines()[-1].strip()
        self.assertIn(str(self.root), recovery)
        carried = subprocess.run(recovery, shell=True, capture_output=True, text=True, check=False)

        self.assertEqual(carried.returncode, 0, carried.stderr)
        self.assertFalse(self.root.exists())


if __name__ == "__main__":
    unittest.main()
