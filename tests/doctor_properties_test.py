"""CP-16 step 5 — what the Doctor report holds for every input, not just the worked examples.

Each step of this slice proved its claim on a scenario an operator could actually produce, and
then a scoped mutation run found the gaps those scenarios could not reach: a fixture with one
working copy cannot tell `continue` from `break`, and a fixture with one dependant cannot see the
separator between two. Those are the same shape of blind spot, and both are cases where the claim
was universal all along while the evidence was a single example.

These are the universal halves, stated over generated input.
"""

from __future__ import annotations

import unittest

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_artifacts.application.consumer_views import project_credential_record
from agent_artifacts.application.orphaned_runs import (
    OrphanedRun,
    OrphanedRuns,
    orphaned_run_lines,
)
from agent_artifacts.commands.doctor import (
    _configuration_data,
    _configuration_lines,
    _credential_lines,
)
from agent_artifacts.configuration.model import (
    ConfiguredSource,
    OrganizationPolicy,
    ReportingSettings,
    SourceKind,
    SyncSettings,
    UserConfiguration,
)
from agent_artifacts.configuration.policy import EffectiveConfiguration
from agent_artifacts.domain.credentials import (
    CredentialObservation,
    CredentialProviderRef,
    CredentialReference,
    CredentialState,
    ProviderState,
)
from agent_artifacts.domain.identifiers import InputId, SourceAlias

# `differing_executors` is suppressed for one reason: `scripts/mutants.py` re-runs the same test
# method object from a fresh runner per mutant, which is what the check detects. These properties
# are pure functions of generated input and hold no state between executions, so the condition the
# check exists to catch cannot arise here. It does not fire under `make quality`.
SETTINGS = settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=(HealthCheck.too_slow, HealthCheck.differing_executors),
)

_ALIAS = st.from_regex(r"\A[a-z][a-z0-9-]{0,10}\Z")
_LOCKABLE = st.sampled_from(("reporting.destination", "reporting.mode", "sync.mode"))
_COORDINATE = st.from_regex(r"\A[a-z]{1,6}/[a-z]{1,6}/[a-z]{1,8}@[0-9]\.[0-9]\.[0-9]\Z")


@st.composite
def _effective(draw: st.DrawFn) -> EffectiveConfiguration:
    aliases = draw(st.lists(_ALIAS, max_size=6, unique=True))
    sources = tuple(
        ConfiguredSource(
            SourceAlias(alias),
            SourceKind.SOURCE_LOCAL,
            f"/srv/{alias}",
            None,
            draw(st.booleans()),
        )
        for alias in aliases
    )
    locked = tuple(sorted(draw(st.sets(_LOCKABLE, max_size=3))))
    return EffectiveConfiguration(
        UserConfiguration(1, sources, None, SyncSettings(), ReportingSettings()),
        OrganizationPolicy(1),
        locked,
    )


def _observation() -> CredentialObservation:
    return CredentialObservation(
        CredentialReference(
            InputId("github-token"), CredentialProviderRef("macos-keychain", "github.com", "work")
        ),
        ProviderState.AVAILABLE,
        CredentialState.PRESENT,
        "reference resolves",
    )


class ConfigurationDiagnosticProperties(unittest.TestCase):
    @SETTINGS
    @given(_effective())
    def test_the_report_names_every_disabled_source_and_no_enabled_one(
        self, effective: EffectiveConfiguration
    ) -> None:
        """Whatever the mix, the section is exactly the complement of what is enabled."""

        data = _configuration_data(effective)
        reported = data["disabled_sources"]
        assert isinstance(reported, list)

        self.assertEqual(
            {item["alias"] for item in reported},
            {
                source.alias.value
                for source in effective.configuration.sources
                if not source.enabled
            },
        )
        self.assertEqual(data["policy_locked_fields"], list(effective.locked_fields))

    @SETTINGS
    @given(_effective())
    def test_the_all_clear_line_appears_exactly_when_there_is_nothing_to_report(
        self, effective: EffectiveConfiguration
    ) -> None:
        """An operator may read the one-line answer as "nothing", so it must mean nothing."""

        lines = _configuration_lines(effective)
        disabled = [item for item in effective.configuration.sources if not item.enabled]
        quiet = not disabled and not effective.locked_fields

        self.assertEqual(len(lines) == 1, quiet)
        if quiet:
            self.assertIn("no field is policy-locked", lines[0])

    @SETTINGS
    @given(_effective())
    def test_nothing_configured_is_dropped_from_the_rendering(
        self, effective: EffectiveConfiguration
    ) -> None:
        """The example test had one disabled source and one locked field; this has any number."""

        rendered = "\n".join(_configuration_lines(effective))

        for source in effective.configuration.sources:
            if not source.enabled:
                self.assertIn(source.alias.value, rendered)
        for field in effective.locked_fields:
            self.assertIn(field, rendered)


class CredentialDiagnosticProperties(unittest.TestCase):
    @SETTINGS
    @given(st.lists(_COORDINATE, max_size=5, unique=True))
    def test_a_credential_is_deletable_exactly_when_nothing_depends_on_it(
        self, dependants: list[str]
    ) -> None:
        """CP-15's retention claim (INV-231) as a rule rather than as two examples."""

        record = project_credential_record(_observation(), dependants=tuple(dependants))

        self.assertEqual("delete" in record.actions, not dependants)
        self.assertEqual(record.dependants, tuple(sorted(set(dependants))))

    @SETTINGS
    @given(st.lists(_COORDINATE, min_size=1, max_size=5, unique=True))
    def test_no_dependant_is_ever_dropped_from_the_human_line(self, dependants: list[str]) -> None:
        """An operator deciding whether to replace a credential needs all of who it would affect."""

        record = project_credential_record(_observation(), dependants=tuple(dependants))
        rendered = "\n".join(_credential_lines((record,)))

        for item in dependants:
            self.assertIn(item, rendered)


class OrphanedRunProperties(unittest.TestCase):
    @SETTINGS
    @given(
        st.lists(
            st.tuples(st.from_regex(r"\A[a-z0-9]{1,12}\Z"), st.from_regex(r"\A[0-9a-f]{16}\Z")),
            max_size=6,
            unique_by=lambda item: item[0],
        )
    )
    def test_every_working_copy_found_is_named_and_counted_in_agreement(
        self, entries: list[tuple[str, str]]
    ) -> None:
        """The count in the summary line and the paths beneath it are one observation."""

        observed = OrphanedRuns(
            tuple(OrphanedRun(f"/runs/{name}", prefix) for name, prefix in entries)
        )
        lines = orphaned_run_lines(observed)
        rendered = "\n".join(lines)

        self.assertEqual(observed.runs, tuple(sorted(observed.runs, key=lambda i: i.path)))
        for name, _ in entries:
            self.assertIn(f"/runs/{name}", rendered)
        if entries:
            self.assertIn(f"{len(entries)} working cop", lines[0])
            self.assertIn("copy" if len(entries) == 1 else "copies", lines[0])
        else:
            self.assertEqual(lines, ("Interrupted runs: no working copy was left behind.",))


if __name__ == "__main__":
    unittest.main()
