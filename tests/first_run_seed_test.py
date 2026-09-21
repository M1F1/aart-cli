"""CP-27 task 3: a first run with nothing configured connects the Registry the build carried.

The decision is pure and lives here, away from the filesystem, because every one of its rules is a
rule about *when not to act*. It seeds only when there is nothing configured, so an upgrade cannot
overrule a choice a person made. It never fails: a value that cannot be used leaves the run exactly
where it is today, at `SETUP REQUIRED`, because a baked convenience that can stop the tool starting
is no longer a convenience. And it says the alias and the URL out loud, since the person did not
choose either and nothing else in the run will ever be able to tell them where it came from.
"""

from __future__ import annotations

import unittest

from aart_cli.application.configuration import FirstRunOptions, LoadedConfiguration
from aart_cli.application.first_run_seed import SEED_REF, plan_first_run_seed
from aart_cli.configuration.model import (
    ConfiguredSource,
    OrganizationPolicy,
    SourceKind,
    SyncSettings,
    UserConfiguration,
    default_user_configuration,
)
from aart_cli.configuration.policy import EffectiveConfiguration
from aart_cli.configuration.seed import SeededRegistry
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Err, Ok

URL = "https://example.invalid/team/registry.git"
SEEDED = Ok(SeededRegistry(SourceAlias("company"), URL))


def _loaded(*, first_run: bool, sources: tuple[ConfiguredSource, ...] = ()) -> LoadedConfiguration:
    configuration = (
        default_user_configuration()
        if not sources
        else UserConfiguration(1, sources, None, SyncSettings())
    )
    return LoadedConfiguration(
        configuration,
        EffectiveConfiguration(configuration, OrganizationPolicy(1), ()),
        FirstRunOptions((), (), True, True) if first_run else None,
        None,
        (),
    )


def _existing() -> ConfiguredSource:
    return ConfiguredSource(
        SourceAlias("mine"), SourceKind.REGISTRY_LOCAL, "/srv/registry", "main", True
    )


class SeedsOnlyWhenNothingIsConfigured(unittest.TestCase):
    def test_a_first_run_with_nothing_configured_is_seeded(self) -> None:
        outcome = plan_first_run_seed(_loaded(first_run=True), SEEDED)
        assert outcome.seed is not None
        self.assertEqual(outcome.seed.source.alias, SourceAlias("company"))

    def test_a_later_run_is_never_seeded(self) -> None:
        self.assertIsNone(plan_first_run_seed(_loaded(first_run=False), SEEDED).seed)

    def test_a_configuration_that_already_names_a_source_is_never_seeded(self) -> None:
        # Including a local Registry: connecting one is a choice, and an upgrade does not get to
        # add to it.
        loaded = _loaded(first_run=True, sources=(_existing(),))
        self.assertIsNone(plan_first_run_seed(loaded, SEEDED).seed)

    def test_a_build_that_baked_nothing_seeds_nothing_and_says_nothing(self) -> None:
        outcome = plan_first_run_seed(_loaded(first_run=True), Ok(None))
        self.assertEqual((outcome.seed, outcome.diagnostics), (None, ()))


class WhatIsSeeded(unittest.TestCase):
    def _seed(self):
        seed = plan_first_run_seed(_loaded(first_run=True), SEEDED).seed
        assert seed is not None
        return seed

    def test_the_seeded_source_is_a_git_registry_at_the_baked_url(self) -> None:
        self.assertEqual(
            self._seed().source,
            ConfiguredSource(SourceAlias("company"), SourceKind.REGISTRY_GIT, URL, SEED_REF, True),
        )

    def test_it_is_tracked_at_the_ref_configuration_already_defaults_to(self) -> None:
        self.assertEqual(SEED_REF, "main")

    def test_it_becomes_the_default_registry(self) -> None:
        self.assertTrue(self._seed().make_default)

    def test_the_announcement_names_the_alias_and_the_url(self) -> None:
        said = "\n".join(self._seed().announcement)
        self.assertIn("company", said)
        self.assertIn(URL, said)


class AnUnusableValueIsNotFatal(unittest.TestCase):
    """Somebody edited the module in an installed wheel, or a build predates a stricter rule."""

    def _refused(self, message: str = "baked default registry alias is invalid"):
        refused = Err(
            (Diagnostic(DiagnosticCode("default-registry-invalid"), Severity.ERROR, message),)
        )
        return plan_first_run_seed(_loaded(first_run=True), refused)

    def test_nothing_is_seeded(self) -> None:
        self.assertIsNone(self._refused().seed)

    def test_it_is_a_warning_rather_than_an_error(self) -> None:
        self.assertEqual(
            [diagnostic.severity for diagnostic in self._refused().diagnostics],
            [Severity.WARNING],
        )

    def test_the_reason_survives_into_what_the_run_can_say(self) -> None:
        said = " ".join(
            diagnostic.message for diagnostic in self._refused("the URL is unreachable").diagnostics
        )
        self.assertIn("the URL is unreachable", said)

    def test_one_warning_carries_every_reason_the_refusal_gave(self) -> None:
        # `Err` cannot be empty, so there is always something to say; several reasons stay in one
        # warning rather than becoming a wall of them on a screen meant to be reassuring.
        refused = Err(
            (
                Diagnostic(DiagnosticCode("x"), Severity.ERROR, "first reason"),
                Diagnostic(DiagnosticCode("x"), Severity.ERROR, "second reason"),
            )
        )
        outcome = plan_first_run_seed(_loaded(first_run=True), refused)
        self.assertEqual(len(outcome.diagnostics), 1)
        self.assertIn("first reason; second reason", outcome.diagnostics[0].message)


if __name__ == "__main__":
    unittest.main()
