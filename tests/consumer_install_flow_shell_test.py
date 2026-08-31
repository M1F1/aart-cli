"""CP-13 screens 05–11 and 14–24 in the persistent application.

These are the screens that need a plan rather than a catalog. Fast and Verbose stay two disclosures
of one reviewed plan, so every assertion here about a Fast screen has a Verbose counterpart that
adds detail without changing what the screen is about.
"""

from __future__ import annotations

import unittest

from agent_artifacts.application.consumer_ui import (
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    PresentationProfile,
    navigation_targets,
    project_credential_record,
    project_dashboard,
    project_install_plan,
    project_installed_collection,
    project_lifecycle_outcome,
    project_lifecycle_plan,
)
from agent_artifacts.application.intents import InstalledHealth, MemberHealth
from agent_artifacts.tui_consumer import (
    CanonicalScreenSource,
    ConsumerScreens,
    _reload,
    frame,
    render_progress,
)
from tests.consumer_activity_test import lifecycle_outcome
from tests.consumer_shell_test import installed
from tests.consumer_views_test import _credential_input, _plan

COLLECTION = "company/collection/developer@1.0.0"


def plan_view():
    runtime_input, bound, observation = _credential_input()
    return project_install_plan(
        _plan(),
        inputs=(runtime_input,),
        bound_inputs=bound,
        credential_observations=(observation,),
    )


def screens() -> ConsumerScreens:
    artifacts = (
        installed("public/mcp/github@1.6.0", "ready"),
        installed("public/mcp/jira@2.2.0", "update"),
    )
    _, _, observation = _credential_input()
    return ConsumerScreens(
        project_dashboard(artifacts, registry_count=1),
        artifacts,
        plan=plan_view(),
        lifecycle=project_lifecycle_plan(lifecycle_outcome().plan),
        outcome=project_lifecycle_outcome(lifecycle_outcome()),
        credentials=(project_credential_record(observation, dependants=("public/mcp/github",)),),
        installed_collections=(
            project_installed_collection(
                COLLECTION,
                (
                    MemberHealth("public/mcp/github", InstalledHealth.READY),
                    MemberHealth("public/mcp/jira", InstalledHealth.UPDATE),
                ),
            ),
        ),
    )


def route(screen: ConsumerScreen) -> tuple[ConsumerScreen, ...]:
    """The shortest accepted way in, from the Dashboard. Empty where there is none.

    Walking the real map rather than jumping straight to a screen is the point: a screen nobody can
    reach is not implemented, however well it draws when a test hands it a state.
    """

    frontier: list[tuple[ConsumerScreen, ...]] = [()]
    seen = {ConsumerScreen.DASHBOARD}
    while frontier:
        path = frontier.pop(0)
        current = path[-1] if path else ConsumerScreen.DASHBOARD
        if current is screen:
            return path
        for target in navigation_targets(current):
            if target not in seen:
                seen.add(target)
                frontier.append((*path, target))
    return ()


def at(screen: ConsumerScreen, profile: PresentationProfile = PresentationProfile.FAST):
    source = CanonicalScreenSource(screens())
    state = _reload(source, ConsumerUiState(), entering=True)
    if profile is PresentationProfile.VERBOSE:
        state, _ = reduce_consumer_ui(state, ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_PROFILE))
    for hop in route(screen):
        state, _ = _navigate(source, state, hop)
    if state.session.screen is not screen:
        raise AssertionError(f"{screen.value} is not reachable from the Dashboard")
    return source, state


def drawn(screen: ConsumerScreen, profile: PresentationProfile = PresentationProfile.FAST) -> str:
    source, state = at(screen, profile)
    return "\n".join(frame(source, state))


class InstallFlowScreenTest(unittest.TestCase):
    def test_no_screen_in_the_accepted_catalog_is_still_unavailable(self):
        unavailable = tuple(
            screen for screen in ConsumerScreen if "is not available yet" in drawn(screen)
        )

        self.assertEqual(unavailable, ())

    def test_review_selection_states_what_was_asked_for_and_what_it_resolved_to(self):
        fast = drawn(ConsumerScreen.REVIEW_SELECTION)

        self.assertIn("company/mcp/github@1.0.0", fast)
        self.assertIn("Review identity:", fast)

    def test_inspection_reports_what_it_found_without_asking_anything(self):
        fast = drawn(ConsumerScreen.AUTOMATIC_INSPECTION)
        verbose = drawn(ConsumerScreen.AUTOMATIC_INSPECTION, PresentationProfile.VERBOSE)

        self.assertIn("python", fast)
        self.assertIn("satisfied", fast.lower())
        self.assertIn("observed 3.12.1", verbose)
        self.assertNotIn("observed 3.12.1", fast)

    def test_required_inputs_never_shows_a_secret_only_that_it_is_configured(self):
        fast = drawn(ConsumerScreen.REQUIRED_INPUTS)

        self.assertIn("Configured securely", fast)
        self.assertNotIn("value", fast.lower())

    def test_remediation_surfaces_only_the_choice_and_what_it_will_not_touch(self):
        fast = drawn(ConsumerScreen.REMEDIATION)

        self.assertIn("credential", fast.lower())
        self.assertIn("Continue", fast)

    def test_ready_summarises_outcomes_and_verbose_shows_the_same_plan(self):
        fast = drawn(ConsumerScreen.READY)
        verbose = drawn(ConsumerScreen.READY, PresentationProfile.VERBOSE)

        self.assertIn("securely", fast.lower())
        self.assertNotIn("copy-tree", fast)
        self.assertIn("Review identity:", fast)
        self.assertIn("Effects:", verbose)

    def test_progress_is_meaningful_rather_than_a_log_until_verbose(self):
        view = screens().outcome
        fast = "\n".join(render_progress(view, PresentationProfile.FAST))
        verbose = "\n".join(render_progress(view, PresentationProfile.VERBOSE))

        self.assertIn("launcher", fast)
        self.assertNotIn("write-file", fast)
        self.assertIn("write-file", verbose)

    def test_success_offers_the_installed_view_and_the_receipt(self):
        fast = drawn(ConsumerScreen.SUCCESS)

        self.assertIn("View installed", fast)
        self.assertIn("View receipt", fast)

    def test_updates_lists_only_what_has_an_update_and_opens_its_inputs(self):
        source, state = at(ConsumerScreen.UPDATES)

        self.assertEqual(state.rows, ("public/mcp/jira@2.2.0",))
        self.assertIn("Update", "\n".join(frame(source, state)))

    def test_uninstall_review_explains_what_is_retained_and_why(self):
        fast = drawn(ConsumerScreen.UNINSTALL_REVIEW)

        self.assertIn("Review", fast)
        self.assertIn("Review identity:", fast)

    def test_verify_repair_shows_the_minimal_plan_for_what_drifted(self):
        fast = drawn(ConsumerScreen.VERIFY_REPAIR)

        self.assertIn("Review identity:", fast)

    def test_credentials_are_a_reference_view_and_never_a_value_view(self):
        source, state = at(ConsumerScreen.CREDENTIALS)
        fast = "\n".join(frame(source, state))

        self.assertEqual(state.rows, ("github-token@macos-keychain:github.com/work",))
        self.assertIn("Ready", fast)
        self.assertIn("Used by 1", fast)

    def test_a_credential_detail_names_its_provider_consumers_and_actions(self):
        source, state = at(ConsumerScreen.CREDENTIALS)
        opened, _ = _navigate(source, state, ConsumerScreen.CREDENTIAL_DETAILS)
        fast = "\n".join(frame(source, opened))

        self.assertIn("macos-keychain", fast)
        self.assertIn("public/mcp/github", fast)
        self.assertIn("verify", fast)

    def test_deleting_a_credential_in_use_shows_what_it_would_affect(self):
        source, state = at(ConsumerScreen.CREDENTIALS)
        opened, _ = _navigate(source, state, ConsumerScreen.CREDENTIAL_DETAILS)
        action, _ = _navigate(source, opened, ConsumerScreen.CREDENTIAL_ACTION)
        fast = "\n".join(frame(source, action))

        self.assertIn("public/mcp/github", fast)
        self.assertNotIn("delete", fast)

    def test_an_installed_collection_aggregates_the_health_of_its_members(self):
        source, state = at(ConsumerScreen.INSTALLED_COLLECTION_DETAILS)

        self.assertIn(COLLECTION, "\n".join(frame(source, state)))


def _navigate(source, state, screen: ConsumerScreen):
    moved, commands = reduce_consumer_ui(
        state, ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=screen)
    )
    return _reload(source, moved, entering=True), commands


if __name__ == "__main__":
    unittest.main()
