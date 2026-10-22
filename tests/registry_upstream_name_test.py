"""INV-279: a Registry artifact name belongs to the one upstream it was first taken from.

The owner adopted `skill/brainstorming` from one repository, then adopted a different
`skill/brainstorming` from another. The second silently became `1.0.1` of the first: the version
record is keyed by kind/name and input digest only, so nothing noticed that the two copies come from
different authors. These hold that the same upstream still gets its next version, and that another
upstream is refused by name, before anything is written.
"""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from dataclasses import replace
from datetime import date
from unittest import mock

from aart_cli import cli
from aart_cli.application.consumer_ui import (
    ADOPTION_NAME_ROW,
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    RepositoryScanDraft,
    key_bindings,
    key_event,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import ConsumerSession, ConsumerSettings
from aart_cli.application.maintainer_views import MaintainerScreen
from aart_cli.domain.result import Err, Ok
from aart_cli.io.git_acquisition import acquire_git_snapshot
from aart_cli.io.registry_adoption import (
    AdoptionUpstreamDisposition,
    apply_adoption,
    check_adopted_upstream,
    list_adopted_artifacts,
    prepare_adoption,
    scan_repository,
)
from aart_cli.tui_consumer import frame
from tests.registry_repository_scan_test import _Author, _git, _Lab

OFFICIAL = "https://git.example/official.git"


class _Upstreams(_Lab):
    """Two authoring repositories that both declare `skill/brainstorming`."""

    def _scan(self, url: str = ""):
        scanned = scan_repository(
            url=url or self.url, ref="main", registry_root=str(self.registry), acquire=self._acquire
        )
        assert isinstance(scanned, Ok), scanned
        return scanned.value

    def _adopt(self, url: str, renames: tuple[tuple[str, str], ...] = ()):
        scan = self._scan(url)
        chosen = tuple(item.coordinate for item in scan.artifacts if item.name == "brainstorming")
        return prepare_adoption(scan, chosen, registry_root=str(self.registry), renames=renames)

    def _applied(self, url: str, renames: tuple[tuple[str, str], ...] = ()) -> None:
        prepared = self._adopt(url, renames)
        assert isinstance(prepared, Ok), prepared
        applied = apply_adoption(
            prepared.value, prepared.value.review_digest, registry_root=str(self.registry)
        )
        assert isinstance(applied, Ok), applied

    def _official(self) -> None:
        other = _Author(self.root / "official")
        (other.path / "skills/brainstorming/SKILL.md").write_text("# official brainstorming\n")
        _git(other.path, "commit", "-am", "differ")
        self._elsewhere[OFFICIAL] = other.path.as_uri()

    def _adopted(self) -> tuple[tuple[str, str], ...]:
        listed = list_adopted_artifacts(registry_root=str(self.registry))
        assert isinstance(listed, Ok), listed
        return tuple((item.coordinate, item.url) for item in listed.value)


class UpstreamNameTest(_Upstreams):
    def test_the_same_upstream_still_gets_its_next_version(self) -> None:
        self._applied(self.url)
        (self.author.path / "skills/brainstorming/SKILL.md").write_text("# moved on\n")
        _git(self.author.path, "commit", "-am", "move")

        self._applied(self.url)

        self.assertEqual(
            self._adopted(),
            (
                ("skill/brainstorming@1.0.0", self.url),
                ("skill/brainstorming@1.0.1", self.url),
            ),
        )

    def test_another_upstream_for_a_taken_name_is_refused_by_name(self) -> None:
        self._applied(self.url)
        self._official()
        before = _git(self.registry, "status", "--porcelain")

        refused = self._adopt(OFFICIAL)

        self.assertIsInstance(refused, Err, refused)
        assert isinstance(refused, Err)
        message = " ".join(
            " ".join((item.message, *item.interactive)) for item in refused.diagnostics
        )
        self.assertIn("skill/brainstorming", message)
        self.assertIn(self.url, message)
        self.assertIn(OFFICIAL, message)
        self.assertIn("another name", message)
        self.assertEqual(_git(self.registry, "status", "--porcelain"), before)
        self.assertEqual(self._adopted(), (("skill/brainstorming@1.0.0", self.url),))

    def test_the_scan_names_the_upstream_that_holds_the_name(self) -> None:
        self._applied(self.url)
        self._official()

        held = {item.name: item.held_by for item in self._scan(OFFICIAL).artifacts}
        own = {item.name: item.held_by for item in self._scan(self.url).artifacts}

        self.assertEqual(held, {"brainstorming": (self.url,), "verification-before-completion": ()})
        self.assertEqual(set(own.values()), {()})

    def test_another_name_adopts_it_beside_the_first_as_its_own_artifact(self) -> None:
        self._applied(self.url)
        self._official()

        self._applied(OFFICIAL, (("skill/brainstorming", "brainstorming-official"),))

        self.assertEqual(
            self._adopted(),
            (
                ("skill/brainstorming-official@1.0.0", OFFICIAL),
                ("skill/brainstorming@1.0.0", self.url),
            ),
        )
        package = self.registry / "artifacts/skill/brainstorming-official/1.0.0/payload/SKILL.md"
        self.assertEqual(package.read_text(), "# official brainstorming\n")

    def test_a_renamed_artifact_is_checked_and_moves_on_under_its_registry_name(self) -> None:
        self._applied(self.url)
        self._official()
        self._applied(OFFICIAL, (("skill/brainstorming", "brainstorming-official"),))
        coordinate = "skill/brainstorming-official@1.0.0"

        def check():
            checked = check_adopted_upstream(
                coordinate, registry_root=str(self.registry), acquire=self._acquire
            )
            assert isinstance(checked, Ok), checked
            return checked.value

        self.assertIs(check().disposition, AdoptionUpstreamDisposition.UNCHANGED)
        official = self.root / "official" / "superpowers"
        (official / "skills/brainstorming/SKILL.md").write_text("# official, revised\n")
        _git(official, "commit", "-am", "revise")

        moved = check()

        self.assertIs(moved.disposition, AdoptionUpstreamDisposition.CHANGED)
        self.assertEqual(moved.observed_coordinate, "skill/brainstorming-official@1.0.1")
        assert moved.proposal is not None
        self.assertEqual(moved.proposal.selected, ("skill/brainstorming-official@1.0.1",))

    def test_a_new_name_is_refused_when_it_is_not_valid_or_names_nothing_selected(self) -> None:
        self._applied(self.url)
        self._official()

        for renames in (
            (("skill/brainstorming", "Not A Name"),),
            (("skill/verification-before-completion", "other"),),
            (("skill/brainstorming", "a"), ("skill/brainstorming", "b")),
        ):
            with self.subTest(renames=renames):
                self.assertIsInstance(self._adopt(OFFICIAL, renames), Err)

    def test_a_new_name_another_upstream_holds_is_refused_too(self) -> None:
        scan = self._scan()
        prepared = prepare_adoption(
            scan,
            tuple(item.coordinate for item in scan.artifacts),
            registry_root=str(self.registry),
        )
        assert isinstance(prepared, Ok), prepared
        applied = apply_adoption(
            prepared.value, prepared.value.review_digest, registry_root=str(self.registry)
        )
        assert isinstance(applied, Ok), applied
        self._official()

        refused = self._adopt(
            OFFICIAL, (("skill/brainstorming", "verification-before-completion"),)
        )

        self.assertIsInstance(refused, Err, refused)


class UpstreamNameCliTest(_Upstreams):
    """The same rule through `maintain upstream adopt`, with only the transport substituted."""

    def _cli(self, *arguments: str) -> tuple[int, dict]:
        output = io.StringIO()
        with (
            mock.patch(
                "aart_cli.commands.registry.scan_repository",
                side_effect=lambda **kwargs: scan_repository(**kwargs, acquire=self._acquire),
            ),
            contextlib.redirect_stdout(output),
        ):
            code = cli.main(
                [
                    "maintain",
                    "upstream",
                    "adopt",
                    "--source",
                    str(self.registry),
                    "--url",
                    OFFICIAL,
                    "--ref",
                    "main",
                    *arguments,
                    "--json",
                ]
            )
        return code, json.loads(output.getvalue())

    def test_the_command_names_the_holder_refuses_and_adopts_under_another_name(self) -> None:
        self._applied(self.url)
        self._official()

        code, scanned = self._cli()
        self.assertEqual(code, 0, scanned)
        held = {item["name"]: item["held_by"] for item in scanned["artifacts"]}
        self.assertEqual(held["brainstorming"], [self.url])

        chosen = ("--artifact", "skill/brainstorming@1.0.1")
        code, refused = self._cli(*chosen, "--yes")
        self.assertNotEqual(code, 0, refused)
        self.assertIn("--rename skill/brainstorming=", json.dumps(refused))

        code, adopted = self._cli(
            *chosen, "--rename", "skill/brainstorming=brainstorming-official", "--yes"
        )
        self.assertEqual(code, 0, adopted)
        self.assertEqual(adopted["selected"], ["skill/brainstorming-official@1.0.0"])

        code, malformed = self._cli(*chosen, "--rename", "brainstorming-official")
        self.assertNotEqual(code, 0, malformed)


class UpstreamNameTuiTest(_Upstreams):
    """Screen 46d: the held name is shown, another is typed under it, and Adopt carries it."""

    def _press(self, state: ConsumerUiState, key: str) -> tuple[ConsumerUiState, tuple]:
        event = key_event(key, state)
        assert event is not None, key
        return reduce_consumer_ui(state, event)

    def test_the_scan_screen_takes_another_name_and_adopts_under_it(self) -> None:
        from aart_cli import tui

        self._applied(self.url)
        self._official()
        home = self.root / "home"
        home.mkdir()

        def transport(request):
            return acquire_git_snapshot(
                replace(
                    request,
                    location=self._elsewhere.get(request.location, self.author.path.as_uri()),
                    allow_local_transport=True,
                )
            )

        with (
            mock.patch.dict("os.environ", {"AART_CLI_HOME": str(self.root / "state")}),
            mock.patch("aart_cli.io.curation_runtime.acquire_git_snapshot", side_effect=transport),
        ):
            composed = tui._canonical_consumer_actions(
                project=str(self.registry), user_home=str(home), today=date(2026, 10, 21)
            )
            assert isinstance(composed, Ok), composed
            actions = composed.value
            scanned = actions.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.PREPARE_ACTION,
                    action=ConsumerActionKind.REPOSITORY_SCAN,
                    repository_scan_draft=RepositoryScanDraft(OFFICIAL, "main"),
                )
            )
            source = scanned.source
            state = ConsumerUiState(
                ConsumerSession(MaintainerScreen.SCAN_RESULT),
                settings=ConsumerSettings().with_maintainer_mode(True),
            )
            state, _ = reduce_consumer_ui(
                state, ConsumerUiEvent(ConsumerUiEventKind.SET_ROWS, rows=source.rows(state))
            )
            held = "skill/brainstorming@1.0.1"
            self.assertEqual(
                state.rows,
                (
                    held,
                    f"{ADOPTION_NAME_ROW}{held}",
                    "skill/verification-before-completion@1.0.0",
                ),
            )
            drawn = "\n".join(frame(source, state))
            self.assertIn(f"this Registry took skill/brainstorming from {self.url}", drawn)
            self.assertIn("Registry name: (type another name to adopt it)", drawn)

            state, _ = self._press(state, "down")
            for key in "brainstorming-official":
                state, _ = self._press(state, key)
            self.assertEqual(state.adoption_names, ((held, "brainstorming-official"),))
            self.assertNotIn("a", {item.key for item in key_bindings(state)})
            self.assertIn("Registry name: brainstorming-official", "\n".join(frame(source, state)))

            state, _ = self._press(state, "up")
            state, _ = self._press(state, " ")
            state, commands = self._press(state, "a")
            (command,) = (item for item in commands if item.action is not None)
            self.assertEqual(command.adoption_names, ((held, "brainstorming-official"),))

            prepared = actions.handle(command)
            self.assertEqual(
                prepared.source.screens.adoption_review.selected,
                ("skill/brainstorming-official@1.0.0",),
            )
            actions.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.EXECUTE_ACTION,
                    action=ConsumerActionKind.REPOSITORY_ADOPT,
                    review_digest=prepared.event.review_digest,
                )
            )

        self.assertIn(("skill/brainstorming-official@1.0.0", OFFICIAL), self._adopted())


if __name__ == "__main__":
    unittest.main()
