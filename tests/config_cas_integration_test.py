"""The reviewed source-management write refuses a concurrent change end to end (CFG02).

`config_cas_write_test` covers the writer in isolation. These tests prove the CLI actually routes
through it — a correct writer that nothing calls would fix nothing.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
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
from aart_cli.configuration.paths import (
    Platform,
    config_lock_directory,
    resolve_config_paths,
)
from aart_cli.configuration.schema import parse_user_configuration, user_configuration_bytes
from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Ok

_FIXTURE = Path(__file__).parent / "fixtures" / "protocol" / "native-source-v1"


class _Environment:
    def __init__(self, root: Path) -> None:
        self.home = root / "home"
        self.home.mkdir()
        self.environ = {
            "HOME": str(self.home),
            "AART_CLI_HOME": str(self.home / ".aart-cli"),
        }
        platform = Platform.DARWIN if os.sys.platform == "darwin" else Platform.LINUX
        self.paths = resolve_config_paths(
            platform,
            home=str(self.home),
            application_home=self.environ["AART_CLI_HOME"],
        )
        self.config_path = Path(self.paths.user_config_file)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

    def write_configuration(self, *sources: ConfiguredSource) -> None:
        self.config_path.write_bytes(
            user_configuration_bytes(UserConfiguration(1, sources, None, SyncSettings()))
        )

    def add_source(self, alias: str):
        stdout = io.StringIO()
        with (
            mock.patch.dict(os.environ, self.environ, clear=False),
            contextlib.redirect_stdout(stdout),
        ):
            code = cli.main(
                [
                    "source",
                    "add",
                    "--alias",
                    alias,
                    "--kind",
                    "source-local",
                    "--location",
                    str(_FIXTURE.resolve()),
                    "--json",
                ]
            )
        raw = stdout.getvalue()
        return code, (json.loads(raw) if raw.strip() else None)


@contextlib.contextmanager
def _environment():
    with tempfile.TemporaryDirectory() as raw:
        yield _Environment(Path(raw).resolve())


class SourceAddConfigCasTest(unittest.TestCase):
    def test_adding_a_source_to_a_fresh_home_succeeds(self) -> None:
        with _environment() as env:
            code, payload = env.add_source("reference")

            self.assertEqual(code, 0, payload)
            parsed = parse_user_configuration(env.config_path.read_bytes())
            assert isinstance(parsed, Ok), parsed
            self.assertEqual(
                tuple(source.alias.value for source in parsed.value.sources), ("reference",)
            )

    def test_a_writer_landing_during_the_sync_is_not_overwritten(self) -> None:
        """The precise race CB01 could not close.

        A competing writer is injected *during* the source synchronization — after this command has
        read and reviewed the configuration, and after its post-sync revalidation would ordinarily
        run. The reviewed write must lose rather than silently discard the other writer's work.
        """

        with _environment() as env:
            competitor = ConfiguredSource(
                SourceAlias("written-by-someone-else"),
                SourceKind.SOURCE_LOCAL,
                str(_FIXTURE.resolve()),
                None,
                True,
            )
            real_sync = None

            def racing_sync(source, *, data_root):
                # Land the competing write while this command believes it holds a reviewed state.
                env.write_configuration(competitor)
                return real_sync(source, data_root=data_root)

            from aart_cli.commands import source as source_command

            real_sync = source_command.sync_configured_source
            with mock.patch.object(source_command, "sync_configured_source", racing_sync):
                code, payload = env.add_source("reference")

            self.assertEqual(code, 1, payload)
            # The competitor's configuration survives untouched.
            parsed = parse_user_configuration(env.config_path.read_bytes())
            assert isinstance(parsed, Ok), parsed
            self.assertEqual(
                tuple(source.alias.value for source in parsed.value.sources),
                ("written-by-someone-else",),
            )

    def test_a_held_configuration_lock_blocks_the_write_without_corrupting_state(self) -> None:
        with _environment() as env:
            os.makedirs(config_lock_directory(env.paths), exist_ok=True)

            # Shorten the wait: this asserts the outcome of losing the lock, not how long a real
            # CLI is willing to wait for a competing writer.
            with mock.patch("aart_cli.io.config_cas.DEFAULT_LOCK_TIMEOUT_SECONDS", 0.05):
                code, payload = env.add_source("reference")

            self.assertEqual(code, 1, payload)
            self.assertFalse(env.config_path.exists(), "no configuration is written while locked")

    def test_the_configuration_lock_is_not_left_behind_after_a_successful_add(self) -> None:
        with _environment() as env:
            code, payload = env.add_source("reference")

            self.assertEqual(code, 0, payload)
            self.assertFalse(Path(config_lock_directory(env.paths)).exists())


if __name__ == "__main__":  # pragma: no cover - unittest entry point
    unittest.main()
