"""The manual acceptance ecosystem is fresh, isolated and marker-bounded (QA-049/QA-051)."""

from __future__ import annotations

import json
import pathlib
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest


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


if __name__ == "__main__":
    unittest.main()
