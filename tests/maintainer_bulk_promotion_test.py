"""CP-14 step 5: screen 47, bulk promotion.

Bulk promotion is one registry transaction, not a loop over single promotions: that is what makes
the diff, the validation and the commit one coherent boundary rather than several that can each
half-succeed.  A transaction has exactly one target registry, so what a Maintainer may select
together is bounded by the registry the Candidates were scanned for, and screen 47 says so before a
selection can be made rather than refusing it afterwards.
"""

from __future__ import annotations

import builtins
import json
import unittest

from agent_artifacts.application.candidate_validation import validate_candidate
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
from agent_artifacts.application.maintainer_sync import ApprovedRegistryState
from agent_artifacts.application.maintainer_views import (
    MaintainerBulkPromotionView,
    MaintainerScreen,
    MaintainerViews,
    project_maintainer_bulk_promotion,
    project_maintainer_candidates,
    project_maintainer_dashboard,
    project_maintainer_source,
    project_maintainer_validation,
)
from agent_artifacts.configuration.model import SourceKind
from agent_artifacts.domain.candidates import CandidateState
from agent_artifacts.domain.identifiers import ObjectDigest, SourceAlias
from agent_artifacts.domain.policies import EffectivePolicy
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

#: A secret bound to argv compiles and then fails the secret-metadata check, which is what makes it
#: the fixture for "the run refused this Candidate" rather than "the compiler did".
_ARGV_SECRET = {
    "id": "github-token",
    "kind": "secret",
    "inject": {"type": "cli-argument", "argument": "--github-token"},
    "help": {
        "label": "GitHub token",
        "format_hint": "provider-issued token",
        "obtain_from": {"label": "GitHub Settings", "url": "https://github.example/settings"},
    },
}


def _entry(path: str, content: str) -> SnapshotEntry:
    parsed = parse_relative_path(path)
    assert isinstance(parsed, Ok)
    return SnapshotEntry(parsed.value, SnapshotEntryKind.FILE, content.encode())


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _manifest(name: str, *, inputs: list[dict[str, object]] | None = None) -> dict[str, object]:
    manifest: dict[str, object] = {
        "schema": "aart.dev/mcp/v1",
        "artifact": {"name": name, "kind": "mcp", "version": "1.0.0"},
        "payload": {"include": ["server.py"]},
        "transport": {"type": "stdio"},
        "runtime": {"type": "python", "version": ">=3.11"},
        "launch": {"type": "python", "entrypoint": "server.py"},
    }
    if inputs is not None:
        manifest["inputs"] = inputs
    return manifest


def _scan(names, *, registry: str = "company", flawed: frozenset[str] = frozenset()):
    entries: list[SnapshotEntry] = []
    for name in names:
        manifest = _manifest(name, inputs=[_ARGV_SECRET] if name in flawed else None)
        entries.append(_entry(f"{name}/aart.json", json.dumps(manifest, sort_keys=True)))
        entries.append(_entry(f"{name}/server.py", "print('x')\n"))
    compiled = compile_author_snapshot(
        SourceSnapshot(SnapshotOrigin.IMMUTABLE_GIT, tuple(entries)),
        source_alias=SourceAlias("authors"),
        source="https://git.example/authors.git",
        revision="a" * 40,
    )
    assert isinstance(compiled, Ok), compiled
    scanned = reconcile_source_scan(
        SourceAlias("authors"),
        "a" * 40,
        compiled.value,
        previous=(),
        approved=(),
        target_registry=SourceAlias(registry),
    )
    assert isinstance(scanned, Ok), scanned
    return scanned.value


def _runs(scan, policy: EffectivePolicy):
    return tuple((bundle, validate_candidate(bundle, policy=policy)) for bundle in scan.active)


def _approved(alias: str = "company") -> ApprovedRegistryState:
    return ApprovedRegistryState(SourceAlias(alias), "f" * 40, _digest("e"), ())


class BulkPromotionProjectionTest(unittest.TestCase):
    def test_screen_47_offers_every_promotable_candidate_of_one_registry(self) -> None:
        policy = EffectivePolicy()
        scan = _scan(("github-mcp", "jira-mcp"))

        view = project_maintainer_bulk_promotion(
            SourceAlias("company"), _runs(scan, policy), _approved()
        )

        self.assertIsInstance(view, MaintainerBulkPromotionView)
        self.assertEqual(view.target_registry, "company")
        self.assertEqual(
            tuple(item.artifact for item in view.candidates),
            ("mcp/github-mcp", "mcp/jira-mcp"),
        )
        self.assertTrue(all(item.state is CandidateState.READY for item in view.candidates))

    def test_a_candidate_its_run_refused_is_excluded_by_name_and_reason(self) -> None:
        policy = EffectivePolicy()
        scan = _scan(("github-mcp", "jira-mcp"), flawed=frozenset({"jira-mcp"}))

        view = project_maintainer_bulk_promotion(
            SourceAlias("company"), _runs(scan, policy), _approved()
        )

        self.assertEqual(len(view.candidates), 1)
        self.assertEqual(len(view.excluded), 1)
        self.assertTrue(view.excluded[0].reason)
        self.assertNotIn(
            view.excluded[0].candidate_id,
            tuple(item.candidate_id for item in view.candidates),
        )

    def test_a_registry_with_no_approved_state_offers_nothing_and_says_why(self) -> None:
        policy = EffectivePolicy()
        scan = _scan(("github-mcp",))

        view = project_maintainer_bulk_promotion(SourceAlias("company"), _runs(scan, policy), None)

        self.assertEqual(view.candidates, ())
        self.assertTrue(view.refusals)

    def test_candidates_scanned_for_another_registry_are_not_offered_here(self) -> None:
        """One transaction has one registry, so mixing them cannot be a selection to make."""

        policy = EffectivePolicy()
        runs = _runs(_scan(("github-mcp",)), policy) + _runs(
            _scan(("jira-mcp",), registry="partners"), policy
        )

        view = project_maintainer_bulk_promotion(SourceAlias("company"), runs, _approved())

        self.assertEqual(tuple(item.artifact for item in view.candidates), ("mcp/github-mcp",))


def _views(policy: EffectivePolicy, scan) -> MaintainerViews:
    configured = configured_source("authors", SourceKind.SOURCE_GIT)
    health = source_state(
        configured, "author-source", display_order=0, resolved_revision=scan.revision
    ).health
    sources = (project_maintainer_source(configured, health, scan),)
    return MaintainerViews(
        project_maintainer_dashboard(sources),
        sources,
        project_maintainer_candidates((scan,)),
        tuple(project_maintainer_validation(bundle, policy=policy) for bundle in scan.active),
        bulk_promotions=(
            project_maintainer_bulk_promotion(
                SourceAlias("company"), _runs(scan, policy), _approved()
            ),
        ),
    )


def _on(screen: MaintainerScreen) -> ConsumerUiState:
    return ConsumerUiState(
        ConsumerSession(screen),
        settings=ConsumerSettings().with_maintainer_mode(True),
    )


class BulkPromotionShellTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = EffectivePolicy()
        self.scan = _scan(("github-mcp", "jira-mcp"))
        self.views = _views(self.policy, self.scan)
        self.source = CanonicalScreenSource(
            ConsumerScreens(project_dashboard((), registry_count=0), maintainer=self.views)
        )

    def _state(self) -> ConsumerUiState:
        return _reload(self.source, _on(MaintainerScreen.BULK_PROMOTION), entering=True)

    def test_screen_47_rows_are_the_promotable_candidate_ids(self) -> None:
        state = self._state()

        assert self.views.bulk_promotions is not None
        self.assertEqual(
            state.rows,
            tuple(item.candidate_id for item in self.views.bulk_promotions[0].candidates),
        )

    def test_space_selects_a_candidate_on_screen_47(self) -> None:
        state = self._state()

        event = key_event(" ", state, cursor=state.current_row)
        assert event is not None
        selected, _commands = reduce_consumer_ui(state, event)

        self.assertEqual(selected.selection, (state.current_row,))

    def test_the_drawn_screen_marks_what_is_selected_and_counts_it(self) -> None:
        state = self._state()
        selected, _commands = reduce_consumer_ui(
            state, ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_SELECTION, key=state.rows[0])
        )

        drawn = "\n".join(frame(self.source, selected))

        self.assertIn("[x]", drawn)
        self.assertIn("1 selected", drawn)

    def test_an_excluded_candidate_is_named_on_screen_rather_than_silently_absent(self) -> None:
        scan = _scan(("github-mcp", "jira-mcp"), flawed=frozenset({"jira-mcp"}))
        source = CanonicalScreenSource(
            ConsumerScreens(
                project_dashboard((), registry_count=0),
                maintainer=_views(self.policy, scan),
            )
        )

        drawn = "\n".join(
            frame(source, _reload(source, _on(MaintainerScreen.BULK_PROMOTION), entering=True))
        )

        self.assertIn("Not promotable", drawn)
        self.assertIn("jira-mcp", drawn)

    def test_drawing_screen_47_opens_no_file(self) -> None:
        opened: list[object] = []
        real_open = builtins.open

        def _watched(*args: object, **kwargs: object):
            opened.append(args[0] if args else None)
            return real_open(*args, **kwargs)  # type: ignore[arg-type]

        builtins.open = _watched  # type: ignore[assignment]
        try:
            frame(self.source, self._state())
        finally:
            builtins.open = real_open  # type: ignore[assignment]

        self.assertEqual(opened, [])


if __name__ == "__main__":
    unittest.main()
