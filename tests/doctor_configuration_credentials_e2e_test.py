"""End to end: the two ways a machine quietly ignores what an operator configured.

CP-16 step 4c. Both halves of this file are about the same failure: something is set, something
else overrides or ignores it, and no surface says so.

A **disabled source** is skipped by every other part of the global report on purpose -- step 2's
offline readiness iterates enabled sources only -- so an operator wondering why an artifact is not
offered has nothing telling them the source is switched off rather than broken.

A **policy-locked field** is stronger. `_locked_override_diagnostics` refuses a *runtime* override
of one, so a `--reporting-mode` flag is answered. But a value written in the user's own
configuration file is replaced by the organization's in silence, and `EffectiveConfiguration`
carries `locked_fields` for exactly this purpose while being read by nothing in the package.

**Credentials** are the third: `project_credential_record` exists and `application/consumer_session`
is its only caller.

Two claims are measured at the seam rather than through the verb, and the reasons are concrete
rather than convenient -- the same split CP-15 step 8 recorded for the same kind of reason:

- The **populated credential list**. Recording a credential reference on an installation requires
  running a setup recipe that declares a secret input and supplying its value, and
  `commands/marketplace.py` wires a real `MacOsKeychainProvider` on darwin, so that test would
  write into the developer's own Keychain. Reading is safe and the empty case runs through the
  verb; the populated shape is projected here.
- The **policy-locked field**. `resolve_config_paths` puts the policy at
  `/Library/Application Support/agent-artifacts/policy.json` on darwin and no CLI flag overrides
  it, so no test can install one without writing to a root-owned system path.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import unittest

from agent_artifacts.application.consumer_session import credential_dependants
from agent_artifacts.application.consumer_views import (
    CredentialRecordView,
    project_credential_record,
)
from agent_artifacts.commands.doctor import (
    _configuration_data,
    _configuration_lines,
    _credential_data,
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
from agent_artifacts.configuration.schema import (
    parse_user_configuration,
    user_configuration_bytes,
)
from agent_artifacts.domain.credentials import CredentialObservation, CredentialState
from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.result import Ok
from tests.configured_install_command_e2e_test import _environment
from tests.consumer_session_test import OTHER, TOKEN, inspection, observed

_DISABLED = ConfiguredSource(
    SourceAlias("retired"), SourceKind.SOURCE_LOCAL, "/tmp/retired-source", None, False
)


def _with_disabled_source(env) -> None:
    """Add one configured-but-disabled source to the machine's real user configuration.

    Read back through the package's own parser rather than by hand: the file's spelling of a
    source is the schema's business, and a fixture that reimplements it tests the fixture.
    """

    path = pathlib.Path(env.paths.user_config_file)
    existing = parse_user_configuration(path.read_bytes())
    assert isinstance(existing, Ok), existing
    path.write_bytes(
        user_configuration_bytes(
            dataclasses.replace(existing.value, sources=(*existing.value.sources, _DISABLED))
        )
    )


class DoctorConfigurationE2ETest(unittest.TestCase):
    def test_a_source_that_is_configured_but_disabled_is_reported(self) -> None:
        with _environment() as env:
            _with_disabled_source(env)

            code, payload = env.run("doctor")

            self.assertEqual(code, 0, payload)
            self.assertEqual(
                payload["configuration"]["disabled_sources"],
                [{"alias": "retired", "kind": "source-local", "location": "/tmp/retired-source"}],
            )
            # The point of reporting it: nothing else in the report mentions it at all.
            offline = payload["offline_readiness"]
            self.assertNotIn("retired", json.dumps(offline))

    def test_an_enabled_source_is_not_reported_as_disabled(self) -> None:
        """The baseline that stops the assertion above from passing for the wrong reason."""

        with _environment() as env:
            code, payload = env.run("doctor")

            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["configuration"]["disabled_sources"], [])
            self.assertEqual(payload["configuration"]["policy_locked_fields"], [])

    def test_the_human_report_says_a_disabled_source_is_why_nothing_offers_it(self) -> None:
        with _environment() as env:
            _with_disabled_source(env)

            code, output = env.run_text("doctor")

            self.assertEqual(code, 0, output)
            self.assertIn(
                "Configuration:\n  source retired is configured but disabled, so nothing offers it",
                output,
            )

    def test_a_machine_where_no_installation_references_a_credential_says_so(self) -> None:
        with _environment() as env:
            code, payload = env.run("doctor")
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["credentials"], [])

            code, output = env.run_text("doctor")

            self.assertEqual(code, 0, output)
            self.assertIn("Credentials: no installed artifact references one.", output.splitlines())


class CredentialDiagnosticProjectionTest(unittest.TestCase):
    """The populated shape, at the seam, because the verb's route writes to a real Keychain."""

    def _record(
        self,
        state: CredentialState = CredentialState.PRESENT,
        *,
        names: tuple[str, ...] = ("github",),
    ) -> CredentialRecordView:
        installed = tuple(inspection(name, credentials=(TOKEN,)) for name in names)
        watched = observed(TOKEN, state)
        return project_credential_record(
            watched, dependants=credential_dependants(watched, installed)
        )

    def test_the_observation_type_has_no_field_that_could_carry_material(self) -> None:
        """The guarantee is structural, so the serializer cannot break it by forgetting.

        `CredentialObservation`'s docstring says it "deliberately has no value field". Asserting
        that here means a future field named `value` or `secret` fails this test rather than
        silently reaching the report.
        """

        names = {field.name for field in dataclasses.fields(CredentialObservation)}
        self.assertEqual(names, {"reference", "provider_state", "state", "detail"})

    def test_a_credential_reports_its_health_and_who_depends_on_it(self) -> None:
        """Every published field, because a field nothing reads is a contract nobody is keeping."""

        self.assertEqual(
            _credential_data(self._record()),
            {
                "reference": "github-token@macos-keychain:github.com/work",
                "input": "github-token",
                "provider": "macos-keychain",
                "service": "github.com",
                "account": "work",
                "provider_state": "available",
                "health": "present",
                "detail": "reference resolves",
                "dependants": ["public/mcp/github@1.6.0"],
                # Retained rather than deletable, which is CP-15 step 8's INV-231 made visible.
                "actions": ["verify", "replace"],
            },
        )

    def test_a_credential_nothing_depends_on_may_be_deleted(self) -> None:
        """The pair: the absent dependant list is evidence because the present one sits beside it."""

        unused = observed(OTHER)
        record = _credential_data(
            project_credential_record(
                unused, dependants=credential_dependants(unused, (inspection("github"),))
            )
        )

        self.assertEqual(record["dependants"], [])
        self.assertEqual(record["actions"], ["verify", "replace", "delete"])
        # And the operator is told so in words, because "deletable" is the whole point of the case.
        self.assertEqual(
            _credential_lines((project_credential_record(unused),))[1],
            "  jira-token@macos-keychain:jira.acme/work is present"
            " (no installed artifact needs it)",
        )

    def test_the_human_line_names_every_dependant_and_never_the_material(self) -> None:
        """Two dependants, so the separator between them is part of what is asserted."""

        lines = _credential_lines((self._record(names=("github", "gitlab")),))

        self.assertEqual(
            lines,
            (
                "Credentials:",
                "  github-token@macos-keychain:github.com/work is present"
                " (needed by public/mcp/github@1.6.0, public/mcp/gitlab@1.6.0)",
            ),
        )
        self.assertNotIn("value", "\n".join(lines))


class PolicyLockedFieldProjectionTest(unittest.TestCase):
    """At the seam because the policy file is a root-owned system path on darwin."""

    def _effective(self, locked: tuple[str, ...]) -> EffectiveConfiguration:
        return EffectiveConfiguration(
            UserConfiguration(1, (), None, SyncSettings(), ReportingSettings()),
            OrganizationPolicy(1),
            locked,
        )

    def test_a_locked_field_is_reported_so_the_users_own_value_is_not_a_mystery(self) -> None:
        """Two locked fields, so the operator is told about both and not only the first."""

        effective = self._effective(("reporting.destination", "reporting.mode"))

        self.assertEqual(
            _configuration_data(effective)["policy_locked_fields"],
            ["reporting.destination", "reporting.mode"],
        )
        self.assertEqual(
            _configuration_lines(effective),
            (
                "Configuration:",
                "  set by organization policy, so your own value is not in force:"
                " reporting.destination, reporting.mode",
            ),
        )

    def test_an_unlocked_configuration_says_nothing_is_locked(self) -> None:
        effective = self._effective(())

        self.assertEqual(_configuration_data(effective)["policy_locked_fields"], [])
        self.assertEqual(
            _configuration_lines(effective),
            ("Configuration: every configured source is enabled and no field is policy-locked.",),
        )


if __name__ == "__main__":
    unittest.main()
