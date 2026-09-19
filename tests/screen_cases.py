"""Recorded populated states for CP-23 task 14's complete frame matrix.

The matrix deliberately lives outside the assertions.  Adding a screen to either catalog changes
the expected set even if nobody remembers to add a test method, while each exceptional workflow
state below names the fixture that can actually populate it.  The ordinary cases start from the
same Dashboard-derived sources used by the key-walk tests; screens a key walk cannot finish
without an imperative action are seeded with the action's reviewed/result projection.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from agent_artifacts.application.candidate_validation import validate_candidate
from agent_artifacts.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiState,
    InstallationConfigDraft,
    InstallationConfigField,
)
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
    project_dashboard,
)
from agent_artifacts.application.maintainer_views import (
    MaintainerScreen,
    MaintainerViews,
    project_maintainer_candidate_lifecycle,
    project_maintainer_candidates,
    project_maintainer_dashboard,
    project_maintainer_provenance,
    project_maintainer_version_conflict,
    project_registry_workspace,
)
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.tui_consumer import CanonicalScreenSource, ConsumerScreens, _reload
from tests import (
    action_prompt_layout_test,
    consumer_install_flow_shell_test,
    consumer_marketplace_shell_test,
    maintainer_bulk_promotion_test,
    maintainer_candidate_lifecycle_test,
    maintainer_candidate_shell_test,
    maintainer_collection_candidate_test,
    maintainer_promotion_shell_execution_test,
    maintainer_promotion_test,
    maintainer_registry_view_test,
    maintainer_validation_views_test,
    maintainer_version_conflict_test,
)
from tests.configuration_edit_test import (
    INPUT,
    ConfigurationReviewNamesTheChangeTest,
    _editing,
    _key,
    _source_and_state,
)
from tests.consumer_shell_test import screens as activity_screens
from tests.install_time_config_form_test import InstallTimeConfigFormRenderingTest
from tests.install_time_config_form_test import _state as install_form_state
from tests.screen_skeleton_test import _registry

ApplicationScreen = ConsumerScreen | MaintainerScreen

# Deliberately explicit.  Do not derive this from the enums: a newly declared screen must fail the
# matrix until somebody records the state that proves what it draws and what its keys do.
RECORDED_SCREENS: tuple[ApplicationScreen, ...] = (
    ConsumerScreen.DASHBOARD,
    ConsumerScreen.MARKETPLACE,
    ConsumerScreen.ARTIFACT_DETAILS,
    ConsumerScreen.COLLECTION_PREVIEW,
    ConsumerScreen.COLLECTION_CUSTOMIZE,
    ConsumerScreen.REVIEW_SELECTION,
    ConsumerScreen.AUTOMATIC_INSPECTION,
    ConsumerScreen.REQUIRED_INPUTS,
    ConsumerScreen.REMEDIATION,
    ConsumerScreen.READY,
    ConsumerScreen.INSTALLING,
    ConsumerScreen.SUCCESS,
    ConsumerScreen.INSTALLED,
    ConsumerScreen.INSTALLED_ARTIFACT_DETAILS,
    ConsumerScreen.INSTALLED_COLLECTION_DETAILS,
    ConsumerScreen.UPDATES,
    ConsumerScreen.UPDATE_INPUTS,
    ConsumerScreen.UPDATING,
    ConsumerScreen.UNINSTALL_REVIEW,
    ConsumerScreen.UNINSTALLING,
    ConsumerScreen.VERIFY_REPAIR,
    ConsumerScreen.REGISTRIES,
    ConsumerScreen.REGISTRY_ADD,
    ConsumerScreen.REGISTRY_REVIEW,
    ConsumerScreen.REGISTRY_SYNC,
    ConsumerScreen.REGISTRY_REMOVE,
    ConsumerScreen.CREDENTIALS,
    ConsumerScreen.USER_INPUT_DETAILS,
    ConsumerScreen.CONFIGURATION_TARGETS,
    ConsumerScreen.CONFIGURATION_VALUE,
    ConsumerScreen.CONFIGURATION_REVIEW,
    ConsumerScreen.CREDENTIAL_DETAILS,
    ConsumerScreen.CREDENTIAL_ACTION,
    ConsumerScreen.CREDENTIAL_REVIEW,
    ConsumerScreen.ACTIVITY,
    ConsumerScreen.ACTIVITY_DETAILS,
    ConsumerScreen.RECEIPT_DETAILS,
    ConsumerScreen.SETTINGS,
    ConsumerScreen.DOCTOR,
    MaintainerScreen.DASHBOARD,
    MaintainerScreen.SOURCES,
    MaintainerScreen.SOURCE_ADD,
    MaintainerScreen.SOURCE_ADD_REVIEW,
    MaintainerScreen.SOURCE_DETAILS,
    MaintainerScreen.SOURCE_SYNC,
    MaintainerScreen.SOURCE_SYNC_RESULT,
    MaintainerScreen.CANDIDATES,
    MaintainerScreen.CANDIDATE_DETAILS,
    MaintainerScreen.CANDIDATE_DIFF,
    MaintainerScreen.VALIDATION,
    MaintainerScreen.VALIDATION_DETAILS,
    MaintainerScreen.POLICY_REVIEW,
    MaintainerScreen.PROMOTION_REVIEW,
    MaintainerScreen.PROMOTION_MODE,
    MaintainerScreen.REGISTRY_DIFF,
    MaintainerScreen.REGISTRY_VALIDATION,
    MaintainerScreen.REGISTRY_COMMIT,
    MaintainerScreen.REGISTRY,
    MaintainerScreen.REGISTRY_INIT,
    MaintainerScreen.REGISTRY_INIT_REVIEW,
    MaintainerScreen.REPOSITORY_SCAN,
    MaintainerScreen.SCAN_RESULT,
    MaintainerScreen.ADOPTION_REVIEW,
    MaintainerScreen.ADOPTED_ARTIFACTS,
    MaintainerScreen.UPSTREAM_CHECK,
    MaintainerScreen.REGISTRY_REBUILD,
    MaintainerScreen.REGISTRY_REBUILD_REVIEW,
    MaintainerScreen.REGISTRY_PUSH,
    MaintainerScreen.BULK_PROMOTION,
    MaintainerScreen.CANDIDATE_LIFECYCLE,
    MaintainerScreen.PROVENANCE,
    MaintainerScreen.VERSION_CONFLICT,
    MaintainerScreen.COLLECTION_CANDIDATES,
    MaintainerScreen.COLLECTION_VALIDATION,
    MaintainerScreen.CANDIDATE_FILTERS,
)


@dataclass(frozen=True, slots=True)
class ScreenCase:
    """One source and immutable UI state whose frame is part of the recorded matrix."""

    label: str
    source: CanonicalScreenSource
    state: ConsumerUiState

    @property
    def screen(self) -> ApplicationScreen:
        return self.state.session.screen


def _consumer_cases() -> dict[ConsumerScreen, ScreenCase]:
    cases = {}
    for screen in (item for item in RECORDED_SCREENS if isinstance(item, ConsumerScreen)):
        source, state = consumer_install_flow_shell_test.at(screen)
        cases[screen] = ScreenCase(f"{screen.value}:dashboard-route", source, state)

    marketplace_source = CanonicalScreenSource(consumer_marketplace_shell_test.screens())
    artifact = marketplace_source.screens.marketplace[0].key
    collection = marketplace_source.screens.collections[0]
    marketplace_states = {
        ConsumerScreen.MARKETPLACE: ConsumerUiState(
            ConsumerSession(ConsumerScreen.MARKETPLACE), selection=(artifact,)
        ),
        ConsumerScreen.ARTIFACT_DETAILS: ConsumerUiState(
            ConsumerSession(ConsumerScreen.ARTIFACT_DETAILS), focus=artifact
        ),
        ConsumerScreen.COLLECTION_PREVIEW: ConsumerUiState(
            ConsumerSession(ConsumerScreen.COLLECTION_PREVIEW),
            focus=collection.key,
            selection=collection.members,
        ),
        ConsumerScreen.COLLECTION_CUSTOMIZE: ConsumerUiState(
            ConsumerSession(ConsumerScreen.COLLECTION_CUSTOMIZE),
            focus=collection.key,
            selection=collection.members[:1],
        ),
    }
    for screen, state in marketplace_states.items():
        cases[screen] = ScreenCase(
            f"{screen.value}:populated-marketplace",
            marketplace_source,
            _reload(marketplace_source, state, entering=True),
        )

    registry_source = CanonicalScreenSource(
        replace(consumer_install_flow_shell_test.screens(), registries=(_registry("company"),))
    )
    for screen, action in (
        (ConsumerScreen.REGISTRY_SYNC, ConsumerActionKind.REGISTRY_SYNC),
        (ConsumerScreen.REGISTRY_REMOVE, ConsumerActionKind.REGISTRY_REMOVE),
    ):
        state = ConsumerUiState(
            ConsumerSession(screen, review_digest="sha256:" + "d" * 64),
            focus="company",
            action=action,
        )
        cases[screen] = ScreenCase(
            f"{screen.value}:reviewed-company",
            registry_source,
            _reload(registry_source, state, entering=True),
        )

    configuration_source, details = _source_and_state()
    targets, _ = _key(configuration_source, details, "enter")
    value = _editing(configuration_source, details)
    cases[ConsumerScreen.CONFIGURATION_TARGETS] = ScreenCase(
        "22b:installed-harnesses", configuration_source, targets
    )
    cases[ConsumerScreen.CONFIGURATION_VALUE] = ScreenCase(
        "22c:prefilled-value", configuration_source, value
    )
    review_source, review = ConfigurationReviewNamesTheChangeTest()._review()
    cases[ConsumerScreen.CONFIGURATION_REVIEW] = ScreenCase(
        "22d:reviewed-change", review_source, review
    )

    activity_source = CanonicalScreenSource(activity_screens())
    activity = _reload(
        activity_source,
        ConsumerUiState(ConsumerSession(ConsumerScreen.ACTIVITY)),
        entering=True,
    )
    activity_focus = activity.current_row
    for screen in (ConsumerScreen.ACTIVITY_DETAILS, ConsumerScreen.RECEIPT_DETAILS):
        state = ConsumerUiState(ConsumerSession(screen), focus=activity_focus)
        cases[screen] = ScreenCase(
            f"{screen.value}:recorded-operation",
            activity_source,
            _reload(activity_source, state, entering=True),
        )
    return cases


def _maintainer_cases() -> dict[MaintainerScreen, ScreenCase]:
    views = maintainer_candidate_shell_test._views()
    source = maintainer_candidate_shell_test._shell(views)
    assert views.candidates
    focus = views.candidates[0].id
    settings = ConsumerSettings().with_maintainer_mode(True)
    cases = {}
    for screen in (item for item in RECORDED_SCREENS if isinstance(item, MaintainerScreen)):
        state = ConsumerUiState(ConsumerSession(screen), settings=settings, focus=focus)
        cases[screen] = ScreenCase(
            f"{screen.value}:candidate-source",
            source,
            _reload(source, state, entering=True),
        )

    sync_source = CanonicalScreenSource(
        replace(
            source.screens,
            source_sync_result=(
                action_prompt_layout_test.MaintainerReviewsSeparateTheirPromptTest()._sync_result()
            ),
        )
    )
    sync_state = ConsumerUiState(
        ConsumerSession(MaintainerScreen.SOURCE_SYNC_RESULT),
        settings=settings,
        focus="company",
    )
    cases[MaintainerScreen.SOURCE_SYNC_RESULT] = ScreenCase(
        "34:completed-source-sync",
        sync_source,
        _reload(sync_source, sync_state, entering=True),
    )

    lifecycle_scan = maintainer_candidate_lifecycle_test._changed_scan()
    lifecycle_bundle = lifecycle_scan.active[0]
    lifecycle_source_view = maintainer_candidate_shell_test._projected_source(
        "authors", lifecycle_scan
    )
    lifecycle = project_maintainer_candidate_lifecycle(
        lifecycle_bundle,
        validate_candidate(lifecycle_bundle, policy=EffectivePolicy()),
        history=lifecycle_scan.history,
        versions=(),
        audits=(),
    )
    lifecycle_views = MaintainerViews(
        project_maintainer_dashboard((lifecycle_source_view,)),
        (lifecycle_source_view,),
        project_maintainer_candidates((lifecycle_scan,)),
        lifecycles=(lifecycle,),
        provenances=(project_maintainer_provenance(lifecycle_bundle),),
    )
    lifecycle_source = CanonicalScreenSource(
        ConsumerScreens(project_dashboard((), registry_count=0), maintainer=lifecycle_views)
    )
    for screen in (MaintainerScreen.CANDIDATE_LIFECYCLE, MaintainerScreen.PROVENANCE):
        state = ConsumerUiState(
            ConsumerSession(screen),
            settings=settings,
            focus=lifecycle_bundle.candidate.id.value,
        )
        cases[screen] = ScreenCase(
            f"{screen.value}:durable-candidate-evidence",
            lifecycle_source,
            _reload(lifecycle_source, state, entering=True),
        )

    conflict_scan, published = maintainer_version_conflict_test._conflict()
    conflict_bundle = conflict_scan.active[0]
    conflict = project_maintainer_version_conflict(conflict_bundle, (published,))
    assert conflict is not None
    conflict_source_view = maintainer_candidate_shell_test._projected_source(
        "authors", conflict_scan
    )
    conflict_views = MaintainerViews(
        project_maintainer_dashboard((conflict_source_view,)),
        (conflict_source_view,),
        project_maintainer_candidates((conflict_scan,)),
        provenances=(project_maintainer_provenance(conflict_bundle),),
        version_conflicts=(conflict,),
    )
    conflict_source = CanonicalScreenSource(
        ConsumerScreens(project_dashboard((), registry_count=0), maintainer=conflict_views)
    )
    conflict_state = ConsumerUiState(
        ConsumerSession(MaintainerScreen.VERSION_CONFLICT),
        settings=settings,
        focus=conflict_bundle.candidate.id.value,
    )
    cases[MaintainerScreen.VERSION_CONFLICT] = ScreenCase(
        "50:published-version-conflict",
        conflict_source,
        _reload(conflict_source, conflict_state, entering=True),
    )

    collection = maintainer_collection_candidate_test.MaintainerCollectionCandidateRouteTest()
    collection.setUp()
    for screen in (
        MaintainerScreen.COLLECTION_CANDIDATES,
        MaintainerScreen.COLLECTION_VALIDATION,
    ):
        state = ConsumerUiState(
            ConsumerSession(screen),
            settings=settings,
            focus=collection.candidate.id.value,
        )
        cases[screen] = ScreenCase(
            f"{screen.value}:versioned-collection",
            collection.source,
            _reload(collection.source, state, entering=True),
        )

    registry = maintainer_registry_view_test.MaintainerRegistryShellTest()
    registry.setUp()
    registry_state = ConsumerUiState(
        ConsumerSession(MaintainerScreen.REGISTRY), settings=settings, focus="company"
    )
    cases[MaintainerScreen.REGISTRY] = ScreenCase(
        "46:approved-registry",
        registry.source,
        _reload(registry.source, registry_state, entering=True),
    )

    validation_views = maintainer_validation_views_test._views(
        EffectivePolicy(required_checks=frozenset({"live-acceptance"}))
    )
    validation_source = maintainer_validation_views_test._shell(validation_views)
    assert validation_views.candidates
    validation_focus = validation_views.candidates[0].id
    for screen in (
        MaintainerScreen.VALIDATION,
        MaintainerScreen.VALIDATION_DETAILS,
        MaintainerScreen.POLICY_REVIEW,
    ):
        state = ConsumerUiState(ConsumerSession(screen), settings=settings, focus=validation_focus)
        cases[screen] = ScreenCase(
            f"{screen.value}:validation-run",
            validation_source,
            _reload(validation_source, state, entering=True),
        )

    promotion = maintainer_promotion_test.PromotionShellTest()
    promotion.setUp()
    for screen in (
        MaintainerScreen.PROMOTION_REVIEW,
        MaintainerScreen.PROMOTION_MODE,
        MaintainerScreen.REGISTRY_DIFF,
    ):
        state = ConsumerUiState(
            ConsumerSession(screen), settings=settings, focus=promotion.candidate
        )
        cases[screen] = ScreenCase(
            f"{screen.value}:promotion",
            promotion.source,
            _reload(promotion.source, state, entering=True),
        )

    execution = maintainer_promotion_shell_execution_test.PromotionShellExecutionTest()
    execution.setUp()
    for screen in (MaintainerScreen.REGISTRY_VALIDATION, MaintainerScreen.REGISTRY_COMMIT):
        state = ConsumerUiState(ConsumerSession(screen), settings=settings, focus="a" * 64)
        cases[screen] = ScreenCase(
            f"{screen.value}:promotion-transaction",
            execution.source,
            _reload(execution.source, state, entering=True),
        )

    # Screen 46j only exists over a workspace that may actually be pushed: a checkout whose
    # approved content is committed, whose review digest is known and which has no blocker. On a
    # branch subscribers read it offers the branch field, which is the state worth recording --
    # the empty-row form is what the other `46j` cases in `conditional_cases` are for.
    assert registry.source._screens.maintainer is not None
    push_source = CanonicalScreenSource(
        ConsumerScreens(
            project_dashboard((), registry_count=0),
            maintainer=replace(
                registry.source._screens.maintainer,
                registry_workspace=project_registry_workspace(
                    "manual-registry",
                    commit="eed6c4f",
                    origin="https://git.example.test/acme/registry.git",
                    branch="main",
                    root="/lab/registry",
                    revision="a" * 40,
                    content_digest="sha256:" + "b" * 64,
                    publication_review_digest="sha256:" + "c" * 64,
                    push_blockers=(),
                ),
            ),
        )
    )
    push_state = ConsumerUiState(
        ConsumerSession(MaintainerScreen.REGISTRY_PUSH), settings=settings, focus="company"
    )
    cases[MaintainerScreen.REGISTRY_PUSH] = ScreenCase(
        "46j:pushable-workspace",
        push_source,
        _reload(push_source, push_state, entering=True),
    )

    bulk = maintainer_bulk_promotion_test.BulkPromotionShellTest()
    bulk.setUp()
    cases[MaintainerScreen.BULK_PROMOTION] = ScreenCase(
        "47:selectable-promotion", bulk.source, bulk._state()
    )
    return cases


def screen_cases() -> tuple[ScreenCase, ...]:
    """Exactly one primary populated/fallback case for every declared application screen."""

    cases: dict[ApplicationScreen, ScreenCase] = {}
    cases.update(_consumer_cases())
    cases.update(_maintainer_cases())
    return tuple(cases[screen] for screen in RECORDED_SCREENS)


def conditional_cases() -> tuple[ScreenCase, ...]:
    """States that share a screen but exercise modal, filter, failure and form conditions."""

    source = CanonicalScreenSource(activity_screens())
    installed = _reload(
        source, ConsumerUiState(ConsumerSession(ConsumerScreen.INSTALLED)), entering=True
    )
    searching = replace(installed, searching=True, search="jira")
    filtered = _reload(source, replace(installed, search="jira"))
    help_visible = replace(installed, help_visible=True)
    quit_pending = replace(installed, selection=(installed.rows[0],), quit_pending=True)

    configuration_source, details = _source_and_state()
    editing = _editing(configuration_source, details)
    accepted = replace(
        editing,
        configuration_draft=InstallationConfigDraft(
            (InstallationConfigField(INPUT.value, "matrix-team"),)
        ).accept(INPUT.value),
    )
    install_form_source = InstallTimeConfigFormRenderingTest()._source()
    install_form = replace(
        install_form_state(), rows=install_form_source.rows(install_form_state())
    )
    refused_source = CanonicalScreenSource(
        replace(
            consumer_install_flow_shell_test.screens(),
            notice=("The reviewed request is stale; nothing was changed.",),
        )
    )
    refused = _reload(
        refused_source,
        ConsumerUiState(ConsumerSession(ConsumerScreen.REVIEW_SELECTION)),
        entering=True,
    )
    failed_source = CanonicalScreenSource(
        replace(
            consumer_install_flow_shell_test.screens(),
            notice=("The repair stopped before any change was recorded.",),
        )
    )
    failed = _reload(
        failed_source,
        ConsumerUiState(
            ConsumerSession(ConsumerScreen.VERIFY_REPAIR),
            failed_action=ConsumerActionKind.VERIFY_REPAIR,
        ),
        entering=True,
    )
    return (
        ScreenCase("12:searching", source, searching),
        ScreenCase("12:filtered", source, filtered),
        ScreenCase("12:help", source, help_visible),
        ScreenCase("12:quit-pending", source, quit_pending),
        ScreenCase("07:active-config-form", install_form_source, install_form),
        ScreenCase("22c:accepted-form", configuration_source, accepted),
        ScreenCase("05:refused-review", refused_source, refused),
        ScreenCase("20:failed-action", failed_source, failed),
    )
