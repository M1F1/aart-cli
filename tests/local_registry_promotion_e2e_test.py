"""D-388: a Candidate is promoted into a local Registry checkout from the Maintainer screens.

The operator could not update a Registry connected as `registry-local`: Source Sync found the
bumped version and every review screen drew, and then Registry Diff refused with "target registry
company is not configured and enabled", because promotion looked for its target among `registry-git`
subscriptions only (B-180). The CLI route (`registry scan` / `registry promote`) already worked, so
this walks the TUI one on a real machine: a Registry initialized and published with Git, connected by
its local path, an authoring Source beside it with a version bump, and the screens from Source Sync
to the commit.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aart_cli import cli, tui
from aart_cli.application.consumer_ui import ConsumerUiState, SourceDraft, opening_state
from aart_cli.application.consumer_views import ConsumerSession
from aart_cli.application.maintainer_views import MaintainerScreen
from aart_cli.domain.result import Ok
from tests.consumer_shell_test import DOWN, ENTER, ESCAPE, FakeTerminal

TODAY = dt.date(2026, 10, 15)

_SOURCE = (
    "--source-alias",
    "authors",
    "--source-url",
    "https://git.example.test/authors.git",
    "--target-registry",
    "company",
)


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", "-C", str(root), *arguments), check=True, capture_output=True, text=True
    ).stdout.strip()


def _manifest(version: str) -> str:
    return json.dumps(
        {
            "schema": "aart-cli.dev/mcp/v1",
            "artifact": {"name": "github-mcp", "kind": "mcp", "version": version},
            "payload": {"include": ["server.py"]},
            "transport": {"type": "stdio"},
            "runtime": {"type": "python", "version": ">=3.11"},
            "launch": {"type": "python", "entrypoint": "server.py"},
        }
    )


def _cli(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = cli.main(list(argv))
    return code, out.getvalue()


class _Terminal(FakeTerminal):
    """Answers the quit prompt a pending selection asks on the way out."""

    def __init__(self, *codes: int) -> None:
        super().__init__(*codes)
        self._codes.append(ord("y"))


class LocalRegistryPromotionTest(unittest.TestCase):
    @contextlib.contextmanager
    def _machine(self, *, default: bool = True):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            home, author, registry, project = (
                root / name for name in ("home", "author", "reg", "proj")
            )
            for path in (home, author / "gh", registry, project):
                path.mkdir(parents=True)
            environment = {
                "AART_CLI_HOME": str(home / ".aart-cli"),
                "HOME": str(home),
                "GIT_AUTHOR_NAME": "AART Test",
                "GIT_AUTHOR_EMAIL": "aart@example.invalid",
                "GIT_COMMITTER_NAME": "AART Test",
                "GIT_COMMITTER_EMAIL": "aart@example.invalid",
                "XDG_CONFIG_HOME": str(home / ".config"),
                "XDG_DATA_HOME": str(home / ".local" / "share"),
                "XDG_STATE_HOME": str(home / ".local" / "state"),
                "XDG_CACHE_HOME": str(home / ".cache"),
            }
            with mock.patch.dict(os.environ, environment, clear=False):
                _git(author, "init", "-q", "-b", "main")
                (author / "gh" / "aart-cli.json").write_text(_manifest("1.0.0"), encoding="utf-8")
                (author / "gh" / "server.py").write_text("print('v1')\n", encoding="utf-8")
                _git(author, "add", "-A")
                _git(author, "commit", "-qm", "v1")

                _git(registry, "init", "-q", "-b", "main")
                common = ("--source", str(registry), "--checkout", str(author), *_SOURCE)
                steps = (
                    (
                        "registry",
                        "init",
                        "--source",
                        str(registry),
                        "--source-id",
                        "company",
                        "--display-name",
                        "Company",
                        "--yes",
                    ),
                )
                for step in steps:
                    code, said = _cli(*step)
                    self.assertEqual(code, 0, said)
                _git(registry, "add", "-A")
                _git(registry, "commit", "-qm", "init")
                code, scan = _cli("registry", "scan", *common, "--json")
                self.assertEqual(code, 0, scan)
                candidate = json.loads(scan)["candidates"][0]["candidate_id"]
                for step in (
                    ("registry", "promote", *common, "--candidate", candidate, "--yes"),
                    ("registry", "publish", "--source", str(registry), "--yes"),
                    (
                        "source",
                        "add",
                        "--alias",
                        "company",
                        "--kind",
                        "registry-local",
                        "--location",
                        str(registry),
                        "--ref",
                        "main",
                        "--default" if default else "--no-default",
                    ),
                    (
                        "source",
                        "add",
                        "--alias",
                        "authors",
                        "--kind",
                        "source-local",
                        "--location",
                        str(author),
                    ),
                ):
                    code, said = _cli(*step)
                    self.assertEqual(code, 0, said)

                (author / "gh" / "aart-cli.json").write_text(_manifest("1.1.0"), encoding="utf-8")
                _git(author, "commit", "-qam", "v1.1")
                yield home, registry, author

    def _shell(
        self, home: Path, registry: Path, *codes: int, draft: SourceDraft | None = None
    ) -> _Terminal:
        composed = tui._canonical_consumer_actions(
            project=str(registry), user_home=str(home), today=TODAY
        )
        assert isinstance(composed, Ok), composed
        handler = composed.value
        terminal = _Terminal(*codes)
        state = opening_state(handler.settings)
        if draft is not None:
            # The Add Source form, filled in, with the cursor on its submit row.
            state = ConsumerUiState(
                ConsumerSession(MaintainerScreen.SOURCE_ADD),
                settings=handler.settings,
                source_draft=draft,
                rows=("alias", "kind", "location", "ref", "connect"),
                cursor=4,
            )
        tui.run_consumer_shell(
            handler.source(),
            terminal,
            state=state,
            action_handler=handler,
            settings_writer=handler.save_settings,
        )
        return terminal

    def test_a_bumped_version_is_promoted_and_committed_into_the_local_registry(self) -> None:
        with self._machine() as (home, registry, _author):
            before = _git(registry, "rev-parse", "HEAD")
            # Settings → Registry Maintainer Mode on.
            self._shell(home, registry, *(DOWN,) * 7, ENTER, *(DOWN,) * 4, ENTER, ESCAPE)
            # Registry Maintainer Dashboard → Sources → the authoring Source → Source Sync, confirmed.
            synced = self._shell(home, registry, *(DOWN,) * 8, ENTER, ENTER, ord("s"), ENTER)
            self.assertTrue(synced.screen_containing("/ Source Sync Result"), synced.last)
            # Candidates → the bumped Candidate → its review walk, through to the commit.
            walked = self._shell(
                home,
                registry,
                *(DOWN,) * 8,
                ENTER,
                DOWN,
                ENTER,
                ENTER,
                ord("d"),
                *(ENTER,) * 9,
            )

            drawn = "\n".join("\n".join(frame) for frame in walked.frames)
            self.assertNotIn("is not configured and enabled", drawn)
            self.assertNotEqual(_git(registry, "rev-parse", "HEAD"), before, walked.last)
            self.assertTrue(
                (registry / "registry" / "versions" / "mcp" / "github-mcp" / "1.1.0.json").is_file()
            )
            self.assertEqual(_git(registry, "status", "--porcelain=v1"), "")

    def test_source_sync_targets_the_only_registry_when_none_is_the_default(self) -> None:
        # D-390: disconnecting the default Registry left the other one connected but no default,
        # and Source Sync refused with no way to name one. One enabled Registry is unambiguous.
        with self._machine(default=False) as (home, registry, _author):
            self._shell(home, registry, *(DOWN,) * 7, ENTER, *(DOWN,) * 4, ENTER, ESCAPE)
            synced = self._shell(home, registry, *(DOWN,) * 8, ENTER, ENTER, ord("s"), ENTER)

            drawn = "\n".join("\n".join(frame) for frame in synced.frames)
            self.assertNotIn("explicit default target registry", drawn)
            self.assertTrue(synced.screen_containing("/ Source Sync Result"), synced.last)
            before = _git(registry, "rev-parse", "HEAD")
            walked = self._shell(
                home, registry, *(DOWN,) * 8, ENTER, DOWN, ENTER, ENTER, ord("d"), *(ENTER,) * 9
            )
            self.assertNotEqual(_git(registry, "rev-parse", "HEAD"), before, walked.last)

    def test_a_source_is_removed_from_maintainer_sources_and_added_again(self) -> None:
        # D-391: a Source entered wrong had no way out of the TUI; `aart-cli source remove` did.
        with self._machine() as (home, registry, author):
            self._shell(home, registry, *(DOWN,) * 7, ENTER, *(DOWN,) * 4, ENTER, ESCAPE)
            synced = self._shell(home, registry, *(DOWN,) * 8, ENTER, ENTER, ord("s"), ENTER)
            self.assertTrue(synced.screen_containing("/ Source Sync Result"), synced.last)

            removed = self._shell(home, registry, *(DOWN,) * 8, ENTER, ENTER, ord("d"), ENTER)
            review = removed.screen_containing("remove Source review")
            self.assertIn("[d] Remove", removed.screen_containing("/ Sources"))
            self.assertIn("Source: authors", review)
            self.assertIn("its Candidates", review)
            code, listed = _cli("source", "list")
            self.assertEqual(code, 0, listed)
            self.assertNotIn("authors", listed)
            self.assertIn("company", listed)

            added = self._shell(
                home,
                registry,
                ENTER,
                ENTER,
                draft=SourceDraft("authors", "source-local", str(author), ""),
            )
            self.assertTrue(added.screen_containing("source authors added"), added.last)
            before = _git(registry, "rev-parse", "HEAD")
            self._shell(home, registry, *(DOWN,) * 8, ENTER, ENTER, ord("s"), ENTER)
            walked = self._shell(
                home, registry, *(DOWN,) * 8, ENTER, DOWN, ENTER, ENTER, ord("d"), *(ENTER,) * 9
            )
            self.assertNotEqual(_git(registry, "rev-parse", "HEAD"), before, walked.last)


if __name__ == "__main__":  # pragma: no cover - unittest entry point
    unittest.main()
