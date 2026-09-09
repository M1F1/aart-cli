"""CP-14 step 5: screen 46, the Registry Maintainer View.

A Maintainer looking at a registry is asking four questions at once: is it valid, what is in it,
does my local checkout still match it, and what was promoted into it recently.  All four are
answered from durable evidence the registry itself wrote -- version records and the promotion audit
records that approved them -- rather than from anything restated elsewhere, and all four are
composed once outside drawing.

Recency is derivable without a clock: every promotion audit names the registry snapshot before and
after its own transaction, so the transactions form a chain and the current snapshot is its head.
"""

from __future__ import annotations

import builtins
import json
import unittest

from agent_artifacts.application.candidate_validation import validate_candidate
from agent_artifacts.application.consumer_ui import ConsumerUiState
from agent_artifacts.application.consumer_views import (
    ConsumerSession,
    ConsumerSettings,
    project_dashboard,
)
from agent_artifacts.application.maintainer import reconcile_source_scan
from agent_artifacts.application.maintainer_promotion import (
    plan_candidate_promotion,
    prepare_candidate_promotion,
)
from agent_artifacts.application.maintainer_sync import ApprovedRegistryState
from agent_artifacts.application.maintainer_views import (
    MaintainerRegistryView,
    MaintainerScreen,
    MaintainerViews,
    MaintainerWorkingTreeState,
    project_maintainer_dashboard,
    project_maintainer_registry,
    project_maintainer_source,
)
from agent_artifacts.application.promotion import registry_state_digest
from agent_artifacts.configuration.model import SourceKind
from agent_artifacts.domain.artifacts import ArtifactKind
from agent_artifacts.domain.identifiers import ObjectDigest, SourceAlias
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.registry import PromotionMode
from agent_artifacts.domain.result import Ok
from agent_artifacts.protocol.authoring import compile_author_snapshot
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
)
from agent_artifacts.protocol.paths import parse_relative_path
from agent_artifacts.sources.model import source_snapshot_digest
from agent_artifacts.tui_consumer import CanonicalScreenSource, ConsumerScreens, _reload, frame
from tests.marketplace_fixtures import configured_source, source_state


def _entry(path: str, content: str) -> SnapshotEntry:
    parsed = parse_relative_path(path)
    assert isinstance(parsed, Ok)
    return SnapshotEntry(parsed.value, SnapshotEntryKind.FILE, content.encode())


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _bundle(*, name: str = "github-mcp", kind: str = "mcp", version: str = "1.0.0"):
    manifest: dict[str, object] = {
        "schema": f"aart.dev/{kind}/v1",
        "artifact": {"name": name, "kind": kind, "version": version},
        "payload": {"include": ["server.py"]},
        "transport": {"type": "stdio"},
        "runtime": {"type": "python", "version": ">=3.11"},
        "launch": {"type": "python", "entrypoint": "server.py"},
    }
    compiled = compile_author_snapshot(
        SourceSnapshot(
            SnapshotOrigin.IMMUTABLE_GIT,
            (
                _entry(f"{name}/aart.json", json.dumps(manifest, sort_keys=True)),
                _entry(f"{name}/server.py", "print('x')\n"),
            ),
        ),
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
        target_registry=SourceAlias("company"),
    )
    assert isinstance(scanned, Ok), scanned
    return scanned.value.active[0]


def _promote(bundle, registry: SourceSnapshot, approved: ApprovedRegistryState):
    """Plan one promotion and return the registry snapshot it would leave behind."""

    policy = EffectivePolicy()
    prepared = prepare_candidate_promotion(
        bundle,
        validate_candidate(bundle, policy=policy),
        policy,
        approved,
        mode=PromotionMode.VENDORED,
    )
    assert isinstance(prepared, Ok), prepared
    plan = plan_candidate_promotion(prepared.value, registry)
    assert isinstance(plan, Ok), plan
    written = {str(item.path): item for item in plan.value.changes}
    kept = tuple(item for item in registry.entries if str(item.path) not in written)
    promoted = SourceSnapshot(
        SnapshotOrigin.LOCAL,
        kept
        + tuple(
            SnapshotEntry(
                item.path, SnapshotEntryKind.FILE, item.content, executable=item.executable
            )
            for item in plan.value.changes
        ),
    )
    # The approved snapshot digest is the whole synchronized tree, which is also what D-103
    # requires a checkout to match before anything may be promoted from it.
    snapshot_digest = source_snapshot_digest(promoted)
    assert isinstance(snapshot_digest, Ok), snapshot_digest
    state = ApprovedRegistryState(
        SourceAlias("company"),
        "f" * 40,
        snapshot_digest.value,
        plan.value.versions,
    )
    return promoted, state, plan.value


class MaintainerRegistryViewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.empty_registry = SourceSnapshot(SnapshotOrigin.LOCAL, ())
        self.empty_state = ApprovedRegistryState(SourceAlias("company"), "f" * 40, _digest("e"), ())
        self.registry, self.state, self.plan = _promote(
            _bundle(), self.empty_registry, self.empty_state
        )

    def test_a_registry_reports_its_alias_revision_and_snapshot(self) -> None:
        view = project_maintainer_registry(
            SourceAlias("company"), self.state, self.registry, self.registry
        )

        self.assertIsInstance(view, MaintainerRegistryView)
        self.assertEqual(view.alias, "company")
        self.assertEqual(view.revision, "f" * 40)
        self.assertEqual(view.snapshot, str(self.state.snapshot_digest))
        self.assertEqual(view.version_count, 1)

    def test_artifact_counts_are_grouped_by_kind(self) -> None:
        view = project_maintainer_registry(
            SourceAlias("company"), self.state, self.registry, self.registry
        )

        self.assertEqual(view.artifact_counts, ((ArtifactKind.MCP, 1),))

    def test_a_registry_whose_versions_all_carry_audits_is_valid(self) -> None:
        view = project_maintainer_registry(
            SourceAlias("company"), self.state, self.registry, self.registry
        )

        self.assertTrue(view.valid)
        self.assertEqual(view.diagnostics, ())

    def test_a_version_with_no_promotion_audit_is_not_valid(self) -> None:
        """A published version nobody approved is exactly what registry validity must catch."""

        stripped = SourceSnapshot(
            self.registry.origin,
            tuple(
                item
                for item in self.registry.entries
                if not str(item.path).startswith("registry/promotions/")
            ),
        )

        view = project_maintainer_registry(SourceAlias("company"), self.state, stripped, stripped)

        self.assertFalse(view.valid)
        self.assertTrue(any("approval" in line for line in view.diagnostics), view.diagnostics)

    def test_a_matching_checkout_is_reported_as_matching_the_approved_snapshot(self) -> None:
        view = project_maintainer_registry(
            SourceAlias("company"), self.state, self.registry, self.registry
        )

        self.assertIs(view.working_tree.state, MaintainerWorkingTreeState.MATCHES_SNAPSHOT)
        self.assertEqual(view.working_tree.digest, str(self.state.snapshot_digest))

    def test_a_checkout_holding_different_published_content_is_reported_as_diverged(self) -> None:
        edited = SourceSnapshot(
            self.registry.origin,
            self.registry.entries + (_entry("artifacts/stray.txt", "local edit\n"),),
        )

        view = project_maintainer_registry(
            SourceAlias("company"), self.state, self.registry, edited
        )

        self.assertIs(view.working_tree.state, MaintainerWorkingTreeState.DIVERGED)
        observed = source_snapshot_digest(edited)
        assert isinstance(observed, Ok)
        self.assertEqual(view.working_tree.digest, str(observed.value))

    def test_an_unread_checkout_is_reported_as_unobserved_rather_than_clean(self) -> None:
        view = project_maintainer_registry(SourceAlias("company"), self.state, self.registry, None)

        self.assertIs(view.working_tree.state, MaintainerWorkingTreeState.UNOBSERVED)
        self.assertIsNone(view.working_tree.digest)

    def test_recent_transactions_are_ordered_newest_first_by_the_snapshot_chain(self) -> None:
        """No promotion record carries a clock, but each one names the snapshot it started from."""

        later = _bundle(name="jira-mcp")
        second, state, _plan = _promote(later, self.registry, self.state)

        view = project_maintainer_registry(SourceAlias("company"), state, second, second)

        # An audit names the *registry state* digest its transaction produced, which covers
        # published content only, while the approved snapshot digest covers the whole tree.
        first_state = registry_state_digest(self.registry)
        second_state = registry_state_digest(second)
        assert isinstance(first_state, Ok) and isinstance(second_state, Ok)
        self.assertEqual(len(view.transactions), 2)
        self.assertEqual(view.transactions[0].snapshot_after, str(second_state.value))
        self.assertEqual(view.transactions[0].snapshot_before, str(first_state.value))
        self.assertEqual(view.transactions[0].candidate_ids, (later.candidate.id.value,))
        self.assertEqual(view.transactions[1].snapshot_after, str(first_state.value))

    def test_one_bulk_transaction_lists_every_candidate_it_promoted(self) -> None:
        view = project_maintainer_registry(
            SourceAlias("company"), self.state, self.registry, self.registry
        )

        self.assertEqual(len(view.transactions), 1)
        self.assertEqual(
            view.transactions[0].candidate_ids,
            tuple(sorted(item.candidate_id.value for item in self.plan.audits)),
        )

    def test_a_registry_with_no_synchronized_state_is_a_stated_refusal(self) -> None:
        view = project_maintainer_registry(SourceAlias("company"), None, None, None)

        self.assertFalse(view.valid)
        self.assertIsNone(view.snapshot)
        self.assertEqual(view.version_count, 0)
        self.assertEqual(view.transactions, ())
        self.assertTrue(view.diagnostics)

    def test_a_registry_view_holds_no_secret_material(self) -> None:
        view = project_maintainer_registry(
            SourceAlias("company"), self.state, self.registry, self.registry
        )

        rendered = repr(view)
        self.assertNotIn("BEGIN", rendered)
        self.assertNotIn("token", rendered.lower().replace("github-token-free", ""))


class MaintainerRegistryShellTest(unittest.TestCase):
    """Screen 46 in the production shared shell: what it lists, and what it must not reach for."""

    def setUp(self) -> None:
        empty_state = ApprovedRegistryState(SourceAlias("company"), "f" * 40, _digest("e"), ())
        registry, state, _plan = _promote(
            _bundle(), SourceSnapshot(SnapshotOrigin.LOCAL, ()), empty_state
        )
        self.view = project_maintainer_registry(SourceAlias("company"), state, registry, registry)
        configured = configured_source("authors", SourceKind.SOURCE_GIT)
        scan = reconcile_source_scan(
            SourceAlias("authors"),
            "a" * 40,
            (),
            previous=(),
            approved=(),
            target_registry=SourceAlias("company"),
        )
        assert isinstance(scan, Ok), scan
        health = source_state(
            configured, "author-source", display_order=0, resolved_revision="a" * 40
        ).health
        sources = (project_maintainer_source(configured, health, scan.value),)
        self.views = MaintainerViews(
            project_maintainer_dashboard(sources),
            sources,
            registries=(self.view,),
        )
        self.source = CanonicalScreenSource(
            ConsumerScreens(project_dashboard((), registry_count=0), maintainer=self.views)
        )

    def _drawn(self) -> str:
        state = ConsumerUiState(
            ConsumerSession(MaintainerScreen.REGISTRY),
            settings=ConsumerSettings().with_maintainer_mode(True),
        )
        return "\n".join(frame(self.source, _reload(self.source, state, entering=True)))

    def test_screen_46_draws_the_composed_registry(self) -> None:
        drawn = self._drawn()

        self.assertIn("company", drawn)
        self.assertIn("Approved versions: 1", drawn)
        self.assertIn("matches the approved snapshot", drawn)
        self.assertIn("Recent promotions", drawn)

    def test_an_installation_with_no_composed_registry_refuses_instead_of_raising(self) -> None:
        source = CanonicalScreenSource(
            ConsumerScreens(
                project_dashboard((), registry_count=0),
                maintainer=MaintainerViews(self.views.dashboard, self.views.sources),
            )
        )
        state = ConsumerUiState(
            ConsumerSession(MaintainerScreen.REGISTRY),
            settings=ConsumerSettings().with_maintainer_mode(True),
        )

        drawn = "\n".join(frame(source, _reload(source, state, entering=True)))

        self.assertIn("No registry is configured.", drawn)

    def test_drawing_screen_46_opens_no_file(self) -> None:
        """Registry validity read while drawing could contradict the promotion that produced it."""

        opened: list[object] = []
        real_open = builtins.open

        def _watched(*args: object, **kwargs: object):
            opened.append(args[0] if args else None)
            return real_open(*args, **kwargs)  # type: ignore[arg-type]

        builtins.open = _watched  # type: ignore[assignment]
        try:
            self._drawn()
        finally:
            builtins.open = real_open  # type: ignore[assignment]

        self.assertEqual(opened, [])


if __name__ == "__main__":
    unittest.main()
