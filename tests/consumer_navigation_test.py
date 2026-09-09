from __future__ import annotations

import unittest

from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
    InstalledArtifactView,
    LifecycleDriftView,
    PresentationProfile,
    navigation_targets,
    project_dashboard,
    project_doctor,
    project_registries,
)
from agent_artifacts.application.intents import InstalledHealth
from agent_artifacts.configuration.model import SourceKind
from agent_artifacts.domain.result import Ok
from agent_artifacts.marketplace.catalog import build_marketplace
from agent_artifacts.tui_consumer import (
    render_dashboard,
    render_doctor,
    render_registry,
    render_settings,
)
from tests.marketplace_fixtures import (
    artifact,
    configured_source,
    effective_configuration,
    graph,
    source_state,
)


def _catalog():
    company = configured_source("company", SourceKind.REGISTRY_GIT)
    team = configured_source("team", SourceKind.SOURCE_GIT)
    built = build_marketplace(
        graph(
            (company, "company-registry", (artifact("company-registry", "review"),)),
            (
                team,
                "team-source",
                (
                    artifact("team-source", "github", kind="mcp"),
                    artifact("team-source", "jira", kind="mcp"),
                ),
            ),
        ),
        effective_configuration((company, team), default_registry="company"),
        (
            source_state(company, "company-registry", display_order=0),
            source_state(team, "team-source", display_order=1),
        ),
    )
    assert isinstance(built, Ok), built
    return built.value


def _installed(name: str, health: InstalledHealth) -> InstalledArtifactView:
    drift = (
        ()
        if health in {InstalledHealth.READY, InstalledHealth.UPDATE}
        else (LifecycleDriftView("launcher", "divergent", True),)
    )
    actions = ("details", "verify", "repair", "uninstall") if drift else ("details", "verify")
    return InstalledArtifactView(
        f"company/mcp/{name}@1.0.0",
        health.value,
        (),
        drift,
        actions,
    )


class ConsumerNavigationTest(unittest.TestCase):
    def test_dashboard_navigation_matches_the_accepted_consumer_roots(self) -> None:
        targets = navigation_targets(ConsumerScreen.DASHBOARD)

        self.assertEqual(
            targets,
            (
                ConsumerScreen.MARKETPLACE,
                ConsumerScreen.INSTALLED,
                ConsumerScreen.UPDATES,
                ConsumerScreen.REGISTRIES,
                ConsumerScreen.CREDENTIALS,
                ConsumerScreen.ACTIVITY,
                ConsumerScreen.DOCTOR,
                ConsumerScreen.SETTINGS,
            ),
        )

    def test_navigation_and_profile_switch_are_pure_and_back_restores_position(self) -> None:
        session = ConsumerSession(ConsumerScreen.DASHBOARD)

        marketplace = session.navigate(ConsumerScreen.MARKETPLACE)
        detail = marketplace.navigate(ConsumerScreen.ARTIFACT_DETAILS)
        verbose = detail.switch_profile(PresentationProfile.VERBOSE)

        self.assertEqual(session.screen, ConsumerScreen.DASHBOARD)
        self.assertEqual(verbose.back().screen, ConsumerScreen.MARKETPLACE)
        self.assertEqual(verbose.back().profile, PresentationProfile.VERBOSE)
        self.assertEqual(verbose.history, (ConsumerScreen.DASHBOARD, ConsumerScreen.MARKETPLACE))


class ConsumerOverviewTest(unittest.TestCase):
    def test_dashboard_and_doctor_are_health_oriented(self) -> None:
        artifacts = (
            _installed("github", InstalledHealth.READY),
            _installed("jira", InstalledHealth.BROKEN),
            _installed("database", InstalledHealth.UPDATE),
        )

        dashboard = project_dashboard(artifacts, registry_count=2, recent_activity=("Installed x",))
        doctor = project_doctor(artifacts)

        self.assertEqual(dashboard.installed_count, 3)
        self.assertEqual(dashboard.update_count, 1)
        self.assertEqual(dashboard.attention_count, 1)
        self.assertEqual(doctor.ready_count, 2)
        self.assertEqual(doctor.attention_count, 1)
        self.assertEqual(doctor.issues, ("company/mcp/jira@1.0.0",))
        self.assertIn("repair-issues", doctor.actions)
        self.assertIn("3 installed", "\n".join(render_dashboard(dashboard)))
        rendered_doctor = "\n".join(render_doctor(doctor, PresentationProfile.FAST))
        self.assertIn("company/mcp/jira@1.0.0", rendered_doctor)
        self.assertNotIn("reinstall", rendered_doctor.lower())

    def test_registries_offer_sync_but_never_artifact_update(self) -> None:
        """And an authoring Source offers neither, because it has no availability to refresh."""

        registries = {item.alias: item for item in project_registries(_catalog())}

        self.assertEqual(sorted(registries), ["company", "team"])
        self.assertEqual(sum(item.artifact_count for item in registries.values()), 3)
        self.assertEqual(registries["company"].actions, ("details", "sync"))
        self.assertEqual(registries["team"].actions, ("details",))
        rendered = "\n".join(
            line
            for registry in registries.values()
            for line in render_registry(registry, PresentationProfile.FAST)
        )
        self.assertIn("2 artifacts", rendered)
        self.assertNotIn("Actions: update", rendered)
        self.assertIn("does not update installed artifacts", rendered)
        self.assertIn("An authoring Source, not a registry.", rendered)

    def test_settings_default_to_fast_and_hide_maintainer_navigation(self) -> None:
        settings = ConsumerSettings()
        enabled = settings.with_maintainer_mode(True)

        self.assertEqual(settings.profile, PresentationProfile.FAST)
        self.assertFalse(settings.maintainer_mode)
        self.assertTrue(enabled.maintainer_mode)
        self.assertFalse(settings.maintainer_mode)
        rendered = "\n".join(render_settings(settings))
        self.assertIn("Fast", rendered)
        self.assertIn("Maintainer Mode: off", rendered)


if __name__ == "__main__":
    unittest.main()
