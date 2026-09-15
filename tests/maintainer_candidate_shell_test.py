"""CP-14 screens 35-37 are reachable, typed-filtered and semantic-first in the shared shell.

Screens 35, 36 and 37 already had projections and renderers.  What they did not have was a way in:
the shared screen source listed no Candidate rows, opened no Candidate detail and drew no diff, so
the three screens existed without being reachable.  These tests pin the way in, and pin it to the
stable Candidate ID rather than to an artifact name that two Sources may both claim.
"""

from __future__ import annotations

import dataclasses
import json
import unittest

from agent_artifacts.application.consumer_ui import (
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_event,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import (
    ConsumerSession,
    ConsumerSettings,
    project_dashboard,
)
from agent_artifacts.application.maintainer import reconcile_source_scan
from agent_artifacts.application.maintainer_views import (
    MaintainerCandidateFilter,
    MaintainerScreen,
    MaintainerViews,
    filter_maintainer_candidates,
    project_maintainer_candidates,
    project_maintainer_dashboard,
    project_maintainer_source,
)
from agent_artifacts.configuration.model import SourceKind
from agent_artifacts.domain.candidates import CandidateState
from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.result import Ok
from agent_artifacts.protocol.authoring import compile_author_snapshot
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
)
from agent_artifacts.protocol.paths import parse_relative_path
from agent_artifacts.tui_consumer import CanonicalScreenSource, ConsumerScreens, _reload, frame
from tests.marketplace_fixtures import configured_source, source_state


def _entry(path: str, content: str) -> SnapshotEntry:
    parsed = parse_relative_path(path)
    assert isinstance(parsed, Ok)
    return SnapshotEntry(parsed.value, SnapshotEntryKind.FILE, content.encode())


def _compiled(*, alias: str, revision: str, version: str, server: str):
    """One compiled `github-mcp` manifest, deliberately named the same in every Source."""

    manifest = {
        "schema": "aart.dev/mcp/v1",
        "artifact": {"name": "github-mcp", "kind": "mcp", "version": version},
        "payload": {"include": ["server.py"]},
        "transport": {"type": "stdio"},
        "runtime": {"type": "python", "version": ">=3.11"},
        "launch": {"type": "python", "entrypoint": "server.py"},
    }
    compiled = compile_author_snapshot(
        SourceSnapshot(
            SnapshotOrigin.IMMUTABLE_GIT,
            (
                _entry("github/aart.json", json.dumps(manifest, sort_keys=True)),
                _entry("github/server.py", server),
            ),
        ),
        source_alias=SourceAlias(alias),
        source=f"https://git.example/{alias}.git",
        revision=revision,
    )
    assert isinstance(compiled, Ok), compiled
    return compiled.value


def _scan(*, alias: str, revision: str, version: str, server: str, previous=()):
    scanned = reconcile_source_scan(
        SourceAlias(alias),
        revision,
        _compiled(alias=alias, revision=revision, version=version, server=server),
        previous=previous,
        approved=(),
        target_registry=SourceAlias("company"),
    )
    assert isinstance(scanned, Ok), scanned
    return scanned.value


def _changed_scan(alias: str):
    """A Source scanned twice, so its active Candidate has a prior Candidate to diff against."""

    first = _scan(alias=alias, revision="a" * 40, version="1.0.0", server="print('old')\n")
    return _scan(
        alias=alias,
        revision="b" * 40,
        version="1.1.0",
        server="print('new')\n",
        previous=first.history,
    )


def _projected_source(alias: str, scan):
    configured = configured_source(alias, SourceKind.SOURCE_GIT)
    health = source_state(
        configured,
        f"{alias}-source",
        display_order=0,
        resolved_revision=scan.revision,
    ).health
    return project_maintainer_source(configured, health, scan)


def _views() -> MaintainerViews:
    """Two authoring Sources that both publish an artifact called `github-mcp`."""

    scans = (
        _changed_scan("authors"),
        _scan(alias="vendors", revision="c" * 40, version="2.0.0", server="print('vendor')\n"),
    )
    sources = tuple(
        _projected_source(alias, scan)
        for alias, scan in zip(("authors", "vendors"), scans, strict=True)
    )
    return MaintainerViews(
        project_maintainer_dashboard(sources),
        sources,
        project_maintainer_candidates(scans),
    )


def _shell(views: MaintainerViews) -> CanonicalScreenSource:
    return CanonicalScreenSource(
        ConsumerScreens(project_dashboard((), registry_count=0), maintainer=views)
    )


def _on(screen: MaintainerScreen, *, focus: str = "") -> ConsumerUiState:
    return ConsumerUiState(
        ConsumerSession(screen),
        settings=ConsumerSettings().with_maintainer_mode(True),
        focus=focus,
    )


class MaintainerCandidateFilterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.candidates = _views().candidates or ()

    def test_an_empty_filter_keeps_every_active_candidate(self) -> None:
        self.assertEqual(
            filter_maintainer_candidates(self.candidates, MaintainerCandidateFilter()),
            self.candidates,
        )

    def test_a_filter_is_typed_state_and_refuses_renderer_strings(self) -> None:
        with self.assertRaises(ValueError):
            MaintainerCandidateFilter(states=("changed",))
        with self.assertRaises(ValueError):
            MaintainerCandidateFilter(sources=("",))
        with self.assertRaises(ValueError):
            MaintainerCandidateFilter(query="a\nb")

        accepted = MaintainerCandidateFilter(states=(CandidateState.CHANGED,))
        self.assertEqual(accepted.states, (CandidateState.CHANGED,))

    def test_a_filter_narrows_by_state_source_and_query(self) -> None:
        by_source = filter_maintainer_candidates(
            self.candidates, MaintainerCandidateFilter(sources=("vendors",))
        )
        by_state = filter_maintainer_candidates(
            self.candidates, MaintainerCandidateFilter(states=(CandidateState.CHANGED,))
        )
        by_query = filter_maintainer_candidates(
            self.candidates, MaintainerCandidateFilter(query="2.0.0")
        )

        self.assertEqual([item.source_alias for item in by_source], ["vendors"])
        self.assertEqual([item.state for item in by_state], [CandidateState.CHANGED])
        self.assertEqual([item.version for item in by_query], ["2.0.0"])
        self.assertEqual(
            filter_maintainer_candidates(
                self.candidates,
                MaintainerCandidateFilter(sources=("vendors",), query="1.1.0"),
            ),
            (),
        )

    def test_toggling_a_state_or_source_returns_new_typed_filter_state(self) -> None:
        filtered = MaintainerCandidateFilter().toggled_state(CandidateState.READY)
        self.assertEqual(filtered.states, (CandidateState.READY,))
        self.assertEqual(filtered.toggled_state(CandidateState.READY).states, ())
        self.assertEqual(filtered.toggled_source("authors").sources, ("authors",))


class MaintainerCandidateShellTest(unittest.TestCase):
    def setUp(self) -> None:
        self.views = _views()
        self.source = _shell(self.views)
        self.candidates = self.views.candidates or ()
        self.by_alias = {item.source_alias: item for item in self.candidates}

    def test_candidate_rows_are_stable_ids_not_artifact_names(self) -> None:
        state = _reload(self.source, _on(MaintainerScreen.CANDIDATES), entering=True)

        self.assertEqual(len(state.rows), 2)
        self.assertEqual(set(state.rows), {item.id for item in self.candidates})
        for row in state.rows:
            self.assertRegex(row, r"^[0-9a-f]{64}$")
        self.assertEqual({item.artifact for item in self.candidates}, {"mcp/github-mcp"})

    def test_screen_35_rows_honour_the_typed_filter(self) -> None:
        filtered = dataclasses.replace(
            _on(MaintainerScreen.CANDIDATES),
            candidate_filter=MaintainerCandidateFilter(sources=("vendors",)),
        )

        state = _reload(self.source, filtered, entering=True)

        self.assertEqual(state.rows, (self.by_alias["vendors"].id,))

    def test_enter_opens_the_candidate_under_the_cursor_by_id(self) -> None:
        listed = _reload(self.source, _on(MaintainerScreen.CANDIDATES), entering=True)
        for index, row in enumerate(listed.rows):
            with self.subTest(row=row):
                cursored = dataclasses.replace(listed, cursor=index)
                self.assertIs(self.source.detail(cursored), MaintainerScreen.CANDIDATE_DETAILS)

    def test_duplicate_artifact_names_across_sources_do_not_collide(self) -> None:
        vendors = self.by_alias["vendors"]
        authors = self.by_alias["authors"]

        drawn = "\n".join(
            frame(
                self.source,
                _reload(
                    self.source,
                    _on(MaintainerScreen.CANDIDATE_DETAILS, focus=vendors.id),
                    entering=True,
                ),
            )
        )

        self.assertNotEqual(vendors.id, authors.id)
        self.assertIn("vendors", drawn)
        self.assertIn("2.0.0", drawn)
        self.assertNotIn("1.1.0", drawn)

    def test_an_unavailable_composition_is_not_an_empty_candidate_list(self) -> None:
        unavailable = CanonicalScreenSource(
            ConsumerScreens(project_dashboard((), registry_count=0))
        )

        drawn = "\n".join(
            frame(
                unavailable,
                _reload(unavailable, _on(MaintainerScreen.CANDIDATES), entering=True),
            )
        )

        self.assertIn("Maintainer state is not available yet.", drawn)
        self.assertNotIn("No active Candidates have been discovered.", drawn)

    def test_an_unknown_candidate_focus_refuses_instead_of_raising(self) -> None:
        drawn = "\n".join(
            frame(
                self.source,
                _reload(
                    self.source,
                    _on(MaintainerScreen.CANDIDATE_DETAILS, focus="f" * 64),
                    entering=True,
                ),
            )
        )

        self.assertIn("not available", drawn)

    def test_d_opens_the_semantic_diff_from_the_candidate_detail(self) -> None:
        detail = _on(MaintainerScreen.CANDIDATE_DETAILS, focus=self.by_alias["authors"].id)

        self.assertEqual(
            key_event("d", detail, detail=self.source.detail(detail)),
            ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=MaintainerScreen.CANDIDATE_DIFF),
        )
        self.assertIsNone(key_event("d", _on(MaintainerScreen.SOURCES)))

    def test_f_opens_filters_on_the_list_and_means_nothing_on_the_diff(self) -> None:
        # CP-23 task 03: the raw file diff is the Verbose projection of screen 37, so `f` no longer
        # has a meaning there; on screen 35 it still opens the Candidate filters (164.10).
        self.assertIsNone(key_event("f", _on(MaintainerScreen.SOURCES)))
        opened_filters = key_event("f", _on(MaintainerScreen.CANDIDATES))
        assert opened_filters is not None
        self.assertIs(opened_filters.screen, MaintainerScreen.CANDIDATE_FILTERS)
        diff = _on(MaintainerScreen.CANDIDATE_DIFF, focus=self.by_alias["authors"].id)
        self.assertIsNone(key_event("f", diff))

    def test_back_from_each_candidate_side_view_keeps_the_candidate_on_details(self) -> None:
        candidate = self.by_alias["authors"].id
        for side_view in (
            MaintainerScreen.CANDIDATE_LIFECYCLE,
            MaintainerScreen.PROVENANCE,
            MaintainerScreen.VERSION_CONFLICT,
        ):
            with self.subTest(side_view=side_view):
                state = dataclasses.replace(
                    _on(side_view, focus=candidate),
                    session=ConsumerSession(
                        side_view,
                        history=(
                            MaintainerScreen.CANDIDATES,
                            MaintainerScreen.CANDIDATE_DETAILS,
                        ),
                    ),
                )

                returned, _ = reduce_consumer_ui(state, ConsumerUiEvent(ConsumerUiEventKind.BACK))
                drawn = "\n".join(frame(self.source, returned))

                self.assertIs(returned.session.screen, MaintainerScreen.CANDIDATE_DETAILS)
                self.assertEqual(returned.focus, candidate)
                self.assertNotIn("That Candidate is not available.", drawn)

    def test_the_reported_candidate_lifecycle_round_trip_keeps_its_candidate(self) -> None:
        listed = _reload(self.source, _on(MaintainerScreen.CANDIDATES), entering=True)
        candidate = listed.current_row

        detail_event = key_event("enter", listed, detail=self.source.detail(listed))
        assert detail_event is not None
        detail, _ = reduce_consumer_ui(listed, detail_event)
        detail = _reload(self.source, detail, entering=True)
        lifecycle_event = key_event("r", detail, detail=self.source.detail(detail))
        assert lifecycle_event is not None
        lifecycle, _ = reduce_consumer_ui(detail, lifecycle_event)
        returned, _ = reduce_consumer_ui(lifecycle, ConsumerUiEvent(ConsumerUiEventKind.BACK))

        self.assertIs(returned.session.screen, MaintainerScreen.CANDIDATE_DETAILS)
        self.assertEqual(returned.focus, candidate)
        self.assertNotIn("That Candidate is not available.", frame(self.source, returned))

    def test_back_through_nested_candidate_inspection_keeps_its_subject(self) -> None:
        candidate = self.by_alias["authors"].id
        for side_view, owner in (
            (MaintainerScreen.PROVENANCE, MaintainerScreen.CANDIDATE_LIFECYCLE),
            (MaintainerScreen.VERSION_CONFLICT, MaintainerScreen.PROVENANCE),
        ):
            with self.subTest(side_view=side_view, owner=owner):
                state = dataclasses.replace(
                    _on(side_view, focus=candidate),
                    session=ConsumerSession(
                        side_view,
                        history=(MaintainerScreen.CANDIDATE_DETAILS, owner),
                    ),
                )

                returned, _ = reduce_consumer_ui(state, ConsumerUiEvent(ConsumerUiEventKind.BACK))

                self.assertIs(returned.session.screen, owner)
                self.assertEqual(returned.focus, candidate)

    def test_drawing_the_three_screens_reads_nothing_from_the_machine(self) -> None:
        """Screens 35-37 draw the scans composition already read; drawing rescans nothing."""

        focus = self.by_alias["authors"].id
        states = tuple(
            _reload(self.source, _on(screen, focus=focus), entering=True)
            for screen in (
                MaintainerScreen.CANDIDATES,
                MaintainerScreen.CANDIDATE_DETAILS,
                MaintainerScreen.CANDIDATE_DIFF,
            )
        )
        opened: list[str] = []
        real_open = open

        def _record(file, *args, **kwargs):  # type: ignore[no-untyped-def]
            opened.append(str(file))
            return real_open(file, *args, **kwargs)

        import builtins

        builtins.open = _record  # noqa: A001 - narrow, restored immediately below
        try:
            drawn = tuple("\n".join(frame(self.source, state)) for state in states)
        finally:
            builtins.open = real_open

        self.assertEqual(opened, [])
        self.assertTrue(all(text for text in drawn))
        self.assertIs(self.source.screens.maintainer, self.views)


if __name__ == "__main__":
    unittest.main()
