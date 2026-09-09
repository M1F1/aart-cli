"""CP-14 screen 53 edits the one typed Candidate filter screen 35 already obeys.

The Product Specification says Candidate filters include status, kind, Source and target registry.
Two of those four had nowhere to live, and none of them had a way in: `MaintainerCandidateFilter`
was typed state nobody could edit, so screen 35 obeyed a filter that was always empty.  These tests
pin the missing facets, the projection that says which values exist and what each would leave, and
the route in and out through the shared shell.
"""

from __future__ import annotations

import builtins
import dataclasses
import json
import unittest

from agent_artifacts.application.consumer_ui import (
    ConsumerUiEventKind,
    ConsumerUiState,
    key_event,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import (
    ConsumerSession,
    ConsumerSettings,
    PresentationProfile,
    project_dashboard,
)
from agent_artifacts.application.maintainer import reconcile_source_scan
from agent_artifacts.application.maintainer_views import (
    MaintainerCandidateFilter,
    MaintainerCandidateFilterFacet,
    MaintainerScreen,
    MaintainerViews,
    filter_maintainer_candidates,
    parse_candidate_filter_row,
    project_maintainer_candidate_filters,
    project_maintainer_candidates,
    project_maintainer_dashboard,
    project_maintainer_source,
)
from agent_artifacts.configuration.model import SourceKind
from agent_artifacts.domain.artifacts import ArtifactKind
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
from agent_artifacts.tui_maintainer import render_maintainer_candidate_filters
from tests.marketplace_fixtures import configured_source, source_state


def _entry(path: str, content: str) -> SnapshotEntry:
    parsed = parse_relative_path(path)
    assert isinstance(parsed, Ok)
    return SnapshotEntry(parsed.value, SnapshotEntryKind.FILE, content.encode())


def _mcp(name: str, version: str) -> tuple[SnapshotEntry, ...]:
    manifest = {
        "schema": "aart.dev/mcp/v1",
        "artifact": {"name": name, "kind": "mcp", "version": version},
        "payload": {"include": ["server.py"]},
        "transport": {"type": "stdio"},
        "runtime": {"type": "python", "version": ">=3.11"},
        "launch": {"type": "python", "entrypoint": "server.py"},
    }
    return (
        _entry(f"{name}/aart.json", json.dumps(manifest, sort_keys=True)),
        _entry(f"{name}/server.py", "print('serve')\n"),
    )


def _skill(name: str, version: str) -> tuple[SnapshotEntry, ...]:
    manifest = {
        "schema": "aart.dev/skill/v1",
        "artifact": {"name": name, "kind": "skill", "version": version},
        "payload": {"include": ["SKILL.md"]},
        "compatibility": {"harnesses": ["claude"]},
    }
    return (
        _entry(f"{name}/aart.json", json.dumps(manifest, sort_keys=True)),
        _entry(f"{name}/SKILL.md", f"# {name}\n\nA body.\n"),
    )


#: A pinned revision per Source. Hex, because a Git revision is 40 hex characters and the compiler
#: is right to refuse anything else.
_REVISIONS = {"authors": "a" * 40, "vendors": "b" * 40}


def _scan(*, alias: str, registry: str, entries: tuple[SnapshotEntry, ...]):
    revision = _REVISIONS[alias]
    compiled = compile_author_snapshot(
        SourceSnapshot(SnapshotOrigin.IMMUTABLE_GIT, entries),
        source_alias=SourceAlias(alias),
        source=f"https://git.example/{alias}.git",
        revision=revision,
    )
    assert isinstance(compiled, Ok), compiled
    scanned = reconcile_source_scan(
        SourceAlias(alias),
        revision,
        compiled.value,
        previous=(),
        approved=(),
        target_registry=SourceAlias(registry),
    )
    assert isinstance(scanned, Ok), scanned
    return scanned.value


def _views() -> MaintainerViews:
    """Four Candidates spanning two Sources, two kinds and two target registries.

    Every facet the Product Specification names therefore has something to narrow, and no two
    facets narrow to the same set -- otherwise a filter that ignored one of them would still pass.
    """

    scans = (
        _scan(
            alias="authors",
            registry="company",
            entries=_mcp("github-mcp", "1.0.0") + _skill("code-review", "1.0.0"),
        ),
        _scan(
            alias="vendors",
            registry="partners",
            entries=_mcp("jira-mcp", "2.0.0") + _skill("triage", "2.0.0"),
        ),
    )
    sources = tuple(
        project_maintainer_source(
            configured_source(alias, SourceKind.SOURCE_GIT),
            source_state(
                configured_source(alias, SourceKind.SOURCE_GIT),
                f"{alias}-source",
                display_order=index,
                resolved_revision=scan.revision,
            ).health,
            scan,
        )
        for index, (alias, scan) in enumerate(zip(("authors", "vendors"), scans, strict=True))
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


def _on(screen: MaintainerScreen, **fields) -> ConsumerUiState:
    return ConsumerUiState(
        ConsumerSession(screen),
        settings=ConsumerSettings().with_maintainer_mode(True),
        **fields,
    )


class MaintainerCandidateFilterFacetTest(unittest.TestCase):
    """The two facets the Product Specification names that the filter could not hold."""

    def setUp(self) -> None:
        self.candidates = _views().candidates or ()

    def test_the_filter_narrows_by_artifact_kind(self) -> None:
        narrowed = filter_maintainer_candidates(
            self.candidates, MaintainerCandidateFilter(kinds=(ArtifactKind.SKILL,))
        )

        self.assertEqual(len(self.candidates), 4)
        self.assertEqual(
            sorted(item.artifact for item in narrowed), ["skill/code-review", "skill/triage"]
        )

    def test_the_filter_narrows_by_target_registry(self) -> None:
        narrowed = filter_maintainer_candidates(
            self.candidates, MaintainerCandidateFilter(registries=("partners",))
        )

        self.assertEqual({item.target_registry for item in narrowed}, {"partners"})
        self.assertEqual(len(narrowed), 2)

    def test_facets_intersect_rather_than_accumulate(self) -> None:
        """Two facets narrow to what satisfies both; each alone keeps twice as much."""

        both = filter_maintainer_candidates(
            self.candidates,
            MaintainerCandidateFilter(kinds=(ArtifactKind.MCP,), registries=("company",)),
        )

        self.assertEqual([item.artifact for item in both], ["mcp/github-mcp"])

    def test_a_kind_is_typed_and_a_renderer_string_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            MaintainerCandidateFilter(kinds=("skill",))
        with self.assertRaises(ValueError):
            MaintainerCandidateFilter(registries=("",))
        with self.assertRaises(ValueError):
            MaintainerCandidateFilter(kinds=(ArtifactKind.MCP, ArtifactKind.MCP))

    def test_a_status_row_toggles_into_the_typed_state_facet_it_already_had(self) -> None:
        """The two new facets join the two that existed; `toggled` routes all four the same way."""

        toggled = MaintainerCandidateFilter().toggled(
            MaintainerCandidateFilterFacet.STATUS, CandidateState.NEW.value
        )

        self.assertEqual(toggled.states, (CandidateState.NEW,))
        self.assertEqual(
            toggled.toggled(MaintainerCandidateFilterFacet.SOURCE, "authors").sources,
            ("authors",),
        )

    def test_toggling_a_kind_or_registry_returns_new_typed_filter_state(self) -> None:
        toggled = MaintainerCandidateFilter().toggled_kind(ArtifactKind.SKILL)

        self.assertEqual(toggled.kinds, (ArtifactKind.SKILL,))
        self.assertEqual(toggled.toggled_kind(ArtifactKind.SKILL).kinds, ())
        self.assertEqual(toggled.toggled_registry("company").registries, ("company",))
        self.assertEqual(
            toggled.toggled_registry("company").toggled_registry("company").registries, ()
        )


class MaintainerCandidateFilterProjectionTest(unittest.TestCase):
    """Screen 53 offers the values that exist and says what each one would leave."""

    def setUp(self) -> None:
        self.candidates = _views().candidates or ()

    def test_every_facet_offers_only_values_the_composed_candidates_have(self) -> None:
        view = project_maintainer_candidate_filters(self.candidates, MaintainerCandidateFilter())

        offered = {group.facet: [option.value for option in group.options] for group in view.groups}
        self.assertEqual(offered[MaintainerCandidateFilterFacet.KIND], ["mcp", "skill"])
        self.assertEqual(offered[MaintainerCandidateFilterFacet.SOURCE], ["authors", "vendors"])
        self.assertEqual(offered[MaintainerCandidateFilterFacet.REGISTRY], ["company", "partners"])
        self.assertEqual(offered[MaintainerCandidateFilterFacet.STATUS], ["new"])

    def test_each_option_states_what_it_would_leave_before_it_is_applied(self) -> None:
        """A filter that selects nothing is visible up front rather than after it empties 35."""

        view = project_maintainer_candidate_filters(
            self.candidates, MaintainerCandidateFilter(registries=("company",))
        )

        counts = {
            option.value: option.matching
            for group in view.groups
            if group.facet is MaintainerCandidateFilterFacet.KIND
            for option in group.options
        }
        self.assertEqual(counts, {"mcp": 1, "skill": 1})
        self.assertEqual(view.matching, 2)
        self.assertEqual(view.total, 4)

    def test_an_active_value_is_marked_active(self) -> None:
        view = project_maintainer_candidate_filters(
            self.candidates, MaintainerCandidateFilter(kinds=(ArtifactKind.SKILL,))
        )

        active = {
            option.value for group in view.groups for option in group.options if option.active
        }
        self.assertEqual(active, {"skill"})
        self.assertFalse(view.is_empty)

    def test_a_row_is_a_typed_pair_that_parses_back_rather_than_a_split_string(self) -> None:
        view = project_maintainer_candidate_filters(self.candidates, MaintainerCandidateFilter())

        rows = [option.row for group in view.groups for option in group.options]
        self.assertIn("kind:skill", rows)
        self.assertIn("registry:partners", rows)
        parsed = parse_candidate_filter_row("kind:skill")
        assert parsed is not None
        self.assertIs(parsed[0], MaintainerCandidateFilterFacet.KIND)
        self.assertEqual(parsed[1], "skill")
        self.assertIsNone(parse_candidate_filter_row("kind"))
        self.assertIsNone(parse_candidate_filter_row("nonsense:skill"))
        self.assertIsNone(parse_candidate_filter_row("kind:not-a-kind"))


class MaintainerCandidateFilterShellTest(unittest.TestCase):
    """The way in, the toggle, and the way back to a narrowed screen 35."""

    def setUp(self) -> None:
        self.views = _views()
        self.source = _shell(self.views)
        self.candidates = self.views.candidates or ()

    def test_f_opens_the_filters_from_the_candidate_list(self) -> None:
        event = key_event("f", _on(MaintainerScreen.CANDIDATES))

        assert event is not None
        self.assertIs(event.kind, ConsumerUiEventKind.NAVIGATE)
        self.assertIs(event.screen, MaintainerScreen.CANDIDATE_FILTERS)

    def test_f_does_not_open_filters_from_a_screen_that_has_none(self) -> None:
        """`f` is the raw-file-diff toggle on screen 37; one key, two screens, no collision."""

        event = key_event("f", _on(MaintainerScreen.SOURCES))

        self.assertIsNone(event)

    def test_screen_53_rows_are_the_offered_facet_values(self) -> None:
        state = _reload(self.source, _on(MaintainerScreen.CANDIDATE_FILTERS), entering=True)

        self.assertIn("kind:skill", state.rows)
        self.assertIn("source:vendors", state.rows)
        self.assertIn("registry:company", state.rows)
        self.assertEqual(len(set(state.rows)), len(state.rows))

    def test_space_on_a_row_toggles_that_facet_into_the_typed_filter(self) -> None:
        listed = _reload(self.source, _on(MaintainerScreen.CANDIDATE_FILTERS), entering=True)
        cursor = listed.rows.index("kind:skill")
        state = dataclasses.replace(listed, cursor=cursor)

        event = key_event(" ", state, cursor="kind:skill")
        assert event is not None
        self.assertIs(event.kind, ConsumerUiEventKind.TOGGLE_CANDIDATE_FILTER)
        toggled, _ = reduce_consumer_ui(state, event)

        self.assertEqual(toggled.candidate_filter.kinds, (ArtifactKind.SKILL,))
        # Ticking a filter row is not selecting an artifact: nothing may end up in `selection`,
        # which is what every action reads.
        self.assertEqual(toggled.selection, ())

    def test_toggling_twice_returns_to_the_unnarrowed_list(self) -> None:
        listed = _reload(self.source, _on(MaintainerScreen.CANDIDATE_FILTERS), entering=True)
        state = dataclasses.replace(listed, cursor=listed.rows.index("registry:partners"))

        once, _ = reduce_consumer_ui(
            state,
            key_event(" ", state, cursor="registry:partners"),  # type: ignore[arg-type]
        )
        twice, _ = reduce_consumer_ui(
            once,
            key_event(" ", once, cursor="registry:partners"),  # type: ignore[arg-type]
        )

        self.assertEqual(once.candidate_filter.registries, ("partners",))
        self.assertTrue(twice.candidate_filter.is_empty)

    def test_the_filter_edited_on_53_narrows_screen_35(self) -> None:
        narrowed = dataclasses.replace(
            _on(MaintainerScreen.CANDIDATES),
            candidate_filter=MaintainerCandidateFilter(kinds=(ArtifactKind.SKILL,)),
        )

        state = _reload(self.source, narrowed, entering=True)

        kept = {item.id for item in self.candidates if item.kind == "skill"}
        self.assertEqual(set(state.rows), kept)
        self.assertEqual(len(kept), 2)

    def test_the_body_names_the_facets_and_marks_what_is_active(self) -> None:
        state = dataclasses.replace(
            _on(MaintainerScreen.CANDIDATE_FILTERS),
            candidate_filter=MaintainerCandidateFilter(kinds=(ArtifactKind.SKILL,)),
        )

        drawn = "\n".join(frame(self.source, _reload(self.source, state, entering=True)))

        self.assertIn("AART / Candidate Filters", drawn)
        self.assertIn("Kind", drawn)
        self.assertIn("Target registry", drawn)
        self.assertIn("[x] skill", drawn)
        self.assertIn("[ ] mcp", drawn)

    def test_drawing_screen_53_opens_no_file(self) -> None:
        state = _reload(self.source, _on(MaintainerScreen.CANDIDATE_FILTERS), entering=True)
        original = builtins.open

        def refuse(*arguments, **keywords):
            raise AssertionError("drawing screen 53 opened a file")

        builtins.open = refuse  # type: ignore[assignment]
        try:
            frame(self.source, state)
        finally:
            builtins.open = original

    def test_an_unfiltered_screen_says_so_rather_than_drawing_an_empty_summary(self) -> None:
        view = project_maintainer_candidate_filters(self.candidates, MaintainerCandidateFilter())
        drawn = "\n".join(render_maintainer_candidate_filters(view, PresentationProfile.VERBOSE))

        self.assertIn("No filter is applied", drawn)
        self.assertIn("4 of 4", drawn)


if __name__ == "__main__":
    unittest.main()
