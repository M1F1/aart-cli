"""CP-21 step 7: an empty block says what it is empty of, and a refusal names its steps in order.

`QA-075` and `QA-060` are the same complaint from two screens. A maintainer who has just finished
initializing a Registry is told `No Registry is connected.` on one screen and `configure an enabled
default registry` on the next -- both true, both unreadable, because neither says that the Registry
they just made is not yet a *subscribed* one and what turns it into one.
"""

from __future__ import annotations

from unittest import TestCase

from agent_artifacts.configuration.model import (
    ConfiguredSource,
    OrganizationPolicy,
    ReportingSettings,
    SourceKind,
    SyncSettings,
    UserConfiguration,
)
from agent_artifacts.configuration.policy import EffectiveConfiguration
from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.result import Err
from agent_artifacts.io.maintainer_sync import prepare_configured_source_sync
from agent_artifacts.tui_layout import separate
from agent_artifacts.tui_maintainer import (
    maintainer_registry_descriptor,
    maintainer_registry_status,
)


class EmptyConnectedRegistriesTest(TestCase):
    """`QA-075`: after a successful initialization the block read as a failure."""

    def _lines(self, *, workspace: bool) -> tuple[str, ...]:
        """Everything screen 46 says with nothing subscribed: the `[v]` block and the status."""

        return separate(
            maintainer_registry_descriptor((), registry_workspace_present=workspace),
            maintainer_registry_status((), registry_workspace_present=workspace),
        )

    def test_the_empty_block_says_what_it_is_empty_of(self) -> None:
        text = "\n".join(self._lines(workspace=True))

        self.assertNotIn("No Registry is connected.", text)
        self.assertIn("subscribed", text)

    def test_it_names_publishing_and_subscribing_as_the_next_step(self) -> None:
        text = "\n".join(self._lines(workspace=True))

        self.assertIn("published", text)
        self.assertIn("subscrib", text)

    def test_a_project_that_is_not_a_registry_is_not_told_to_publish_one(self) -> None:
        """Nothing was created here, so the next step is creating it, not publishing it."""

        lines = self._lines(workspace=False)

        self.assertIn("Current project is not a Registry. Initialize creates one here.", lines)

    def test_the_block_still_says_what_the_snapshots_are_for(self) -> None:
        lines = self._lines(workspace=True)

        self.assertEqual(lines[0], "Connected Registry snapshots")
        self.assertIn("These approved snapshots determine what Marketplace can offer.", lines)


class SourceSyncWithoutADefaultRegistryTest(TestCase):
    """`QA-060`: the refusal named a fix without saying the maintainer already has the thing."""

    def _refusal(self) -> tuple[str, ...]:
        """One configured authoring Source and no default registry: the operator's own state."""

        source = ConfiguredSource(
            SourceAlias("authors"), SourceKind.SOURCE_LOCAL, "/work/authors", None, True
        )
        effective = EffectiveConfiguration(
            UserConfiguration(1, (source,), None, SyncSettings(), ReportingSettings()),
            OrganizationPolicy(1),
            (),
        )
        refused = prepare_configured_source_sync(
            effective, SourceAlias("authors"), data_root="/tmp/does-not-matter"
        )

        self.assertIsInstance(refused, Err)
        assert isinstance(refused, Err)
        return tuple(
            line
            for diagnostic in refused.diagnostics
            for line in (diagnostic.message, *diagnostic.remediation)
        )

    def _advice(self) -> tuple[str, ...]:
        """The headline says what is missing; the advice says what to do, and in what order.

        `Diagnostic` sorts its remediation into a set, so the steps that must happen in order
        are one remedy rather than several (`D-238`).
        """

        message, *advice = self._refusal()
        self.assertIn("default target registry", message)
        return tuple(advice)

    def test_the_refusal_names_the_two_steps_in_the_order_they_must_happen(self) -> None:
        text = "\n".join(self._advice())

        publish = text.index("publish")
        default = text.index("default")

        self.assertLess(publish, default, text)

    def test_it_says_a_registry_made_here_is_not_yet_subscribable(self) -> None:
        text = "\n".join(self._refusal())

        self.assertIn("subscrib", text)
