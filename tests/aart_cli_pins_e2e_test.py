"""CP-47: the pin and `.aart-cli-source` are read from a real synced Registry snapshot (§211).

The Registry here is published into the real source store, so what is read is what a sync left:
the current pointer, the snapshot it names, and the two files at its root. The CLI then says so on
stderr for a `consume` command, and `aart-cli upgrade --how` prints how to install it.
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

from aart_cli import cli
from aart_cli.application.aart_cli_update import Installer, RunningAartCli
from aart_cli.configuration.model import UserConfiguration
from aart_cli.configuration.policy import EffectiveConfiguration, OrganizationPolicy
from aart_cli.configuration.schema import parse_user_configuration
from aart_cli.domain.identifiers import SourceId
from aart_cli.domain.result import Ok
from aart_cli.io import aart_cli_pins
from aart_cli.io.aart_cli_pins import read_aart_cli_update, read_registry_pins
from aart_cli.io.source_store import publish_source_snapshot
from aart_cli.protocol.native_tree import SnapshotEntry, SnapshotEntryKind
from aart_cli.protocol.paths import SafeRelativePath
from aart_cli.protocol.semver import parse_semver
from aart_cli.sources.model import (
    SourcePublishCommand,
    ValidatedSourceCandidate,
    make_source_candidate,
    source_instance_id,
    source_store_paths,
)
from tests.configured_install_command_e2e_test import _environment
from tests.configured_installation_draft_e2e_test import _published_registry
from tests.consumer_application_e2e_test import _actions
from tests.placed_installation_e2e_test import AUTHORED_SKILL

NEXUS = "https://nexus.example.test/repository/pypi/simple"
SOURCE = f"AART_CLI_PIP_INDEX_URL={NEXUS}\nAART_CLI_PACKAGE=aart-cli=={{version}}\n"


def _publish(env, files: dict[str, bytes]) -> None:
    """Publish the environment's Registry again with `files` at its root, as a sync would."""

    snapshot = _published_registry(AUTHORED_SKILL)
    extra = tuple(
        SnapshotEntry(SafeRelativePath((name,)), SnapshotEntryKind.FILE, content)
        for name, content in files.items()
    )
    candidate = make_source_candidate(
        source_instance_id(env.source),
        env.source.alias,
        "b" * 40,
        replace(snapshot, entries=snapshot.entries + extra),
    )
    assert isinstance(candidate, Ok), candidate
    published = publish_source_snapshot(
        SourcePublishCommand(
            source_store_paths(env.paths.data_root, source_instance_id(env.source)),
            ValidatedSourceCandidate(candidate.value, SourceId("company-registry")),
            91,
        )
    )
    assert isinstance(published, Ok), published


def _effective(env) -> EffectiveConfiguration:
    parsed = parse_user_configuration(pathlib.Path(env.paths.user_config_file).read_bytes())
    assert isinstance(parsed, Ok), parsed
    assert isinstance(parsed.value, UserConfiguration)
    return EffectiveConfiguration(parsed.value, OrganizationPolicy(1), ())


def _running(version: str = "0.20.0") -> RunningAartCli:
    parsed = parse_semver(version)
    assert isinstance(parsed, Ok)
    return RunningAartCli(parsed.value, "/usr/bin/python3", Installer.PIPX)


def _cli(env, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with (
        mock.patch.dict(os.environ, env.xdg, clear=False),
        mock.patch.object(aart_cli_pins, "running_aart_cli", return_value=_running()),
        contextlib.redirect_stdout(out),
        contextlib.redirect_stderr(err),
        mock.patch("os.getcwd", return_value=str(env.project)),
    ):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class ReadFromTheSnapshotTest(unittest.TestCase):
    def test_the_pin_and_the_source_are_read_from_the_current_snapshot(self) -> None:
        with _environment() as env:
            _publish(env, {".aart-cli-version": b"0.21.0\n", ".aart-cli-source": SOURCE.encode()})

            pins = read_registry_pins(_effective(env), data_root=env.paths.data_root)
            update = read_aart_cli_update(
                _effective(env), data_root=env.paths.data_root, running=_running()
            )

            self.assertEqual(
                [(pin.alias, pin.pin, pin.source) for pin in pins],
                [("company", "0.21.0\n", SOURCE.encode())],
            )
            assert update is not None
            self.assertEqual((update.available, update.registry), ("0.21.0", "company"))
            self.assertEqual(
                update.steps[0].commands,
                (f"pipx install --force --index-url {NEXUS} aart-cli==0.21.0",),
            )

    def test_a_registry_without_a_pin_announces_nothing(self) -> None:
        with _environment() as env:
            self.assertEqual(read_registry_pins(_effective(env), data_root=env.paths.data_root), ())
            self.assertIsNone(
                read_aart_cli_update(
                    _effective(env), data_root=env.paths.data_root, running=_running()
                )
            )

    def test_a_defect_in_finding_out_is_nothing(self) -> None:
        with _environment() as env:
            _publish(env, {".aart-cli-version": b"0.21.0\n"})
            with mock.patch.object(
                aart_cli_pins, "read_registry_pins", side_effect=OSError("disk")
            ):
                self.assertIsNone(
                    read_aart_cli_update(
                        _effective(env), data_root=env.paths.data_root, running=_running()
                    )
                )


class TheTerminalShowsItTest(unittest.TestCase):
    def test_the_production_composition_carries_it_to_home(self) -> None:
        with _environment() as env:
            _publish(env, {".aart-cli-version": b"99.0.0\n", ".aart-cli-source": SOURCE.encode()})

            with mock.patch.object(aart_cli_pins, "running_aart_cli", return_value=_running()):
                screens = _actions(env).source().screens

            assert screens.aart_cli_update is not None
            self.assertEqual(screens.aart_cli_update.available, "99.0.0")
            self.assertEqual(screens.dashboard.aart_cli_available, "99.0.0")


class RunningAartCliTest(unittest.TestCase):
    def test_the_environment_s_own_file_names_the_installer(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            installed = root / "site-packages/aart_cli/io/aart_cli_pins.py"
            installed.parent.mkdir(parents=True)
            installed.touch()
            for mark, expected in (
                ("pipx_metadata.json", Installer.PIPX),
                ("uv-receipt.toml", Installer.UV),
            ):
                with self.subTest(mark=mark):
                    environment = root / mark.split(".")[0]
                    environment.mkdir()
                    (environment / mark).write_text("{}")
                    running = aart_cli_pins.running_aart_cli(
                        prefix=str(environment), module=str(installed)
                    )
                    self.assertIs(running.installer, expected)

    def test_a_checkout_is_an_editable_install(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            checkout = pathlib.Path(raw).resolve()
            module = checkout / "aart_cli/io/aart_cli_pins.py"
            module.parent.mkdir(parents=True)
            module.touch()
            (checkout / ".git").mkdir()
            (checkout / "pyproject.toml").touch()

            running = aart_cli_pins.running_aart_cli(prefix=raw, module=str(module))

            self.assertEqual(
                (running.installer, running.checkout), (Installer.EDITABLE, str(checkout))
            )


class TheCliSaysItTest(unittest.TestCase):
    def test_a_consume_command_says_it_on_stderr_and_leaves_json_alone(self) -> None:
        with _environment() as env:
            _publish(env, {".aart-cli-version": b"0.21.0\n"})

            code, out, err = _cli(env, "consume", "list", "--json")

            self.assertEqual(code, 0, err)
            json.loads(out)
            self.assertIn(
                "aart-cli 0.21.0 is available (Registry company runs it; this is 0.20.0). "
                "Run `aart-cli upgrade --how` to see how to install it.",
                err,
            )

    def test_nothing_is_said_when_no_pin_is_newer(self) -> None:
        with _environment() as env:
            _publish(env, {".aart-cli-version": b"0.20.0\n"})

            _, _, err = _cli(env, "consume", "list", "--json")

            self.assertNotIn("is available", err)

    def test_upgrade_how_prints_the_route_and_installs_nothing(self) -> None:
        with _environment() as env:
            _publish(env, {".aart-cli-version": b"0.21.0\n", ".aart-cli-source": SOURCE.encode()})
            ran = mock.Mock()

            with mock.patch("subprocess.run", ran):
                code, out, _ = _cli(env, "upgrade", "--how")

            self.assertEqual(code, 0)
            ran.assert_not_called()
            self.assertIn(
                "aart-cli 0.21.0 is available: Registry company runs it, and this is 0.20.0.", out
            )
            self.assertIn(f"  pipx install --force --index-url {NEXUS} aart-cli==0.21.0", out)

    def test_upgrade_how_says_when_nothing_is_newer(self) -> None:
        with _environment() as env:
            code, out, _ = _cli(env, "upgrade", "--how")

            self.assertEqual(code, 0)
            self.assertIn("No connected Registry runs an aart-cli newer than 0.20.0.", out)


if __name__ == "__main__":
    unittest.main()
