from __future__ import annotations

import unittest

from agent_artifacts.configuration.model import (
    ConfiguredSource,
    SourceKind,
    SyncMode,
    SyncSettings,
    UserConfiguration,
)
from agent_artifacts.configuration.policy import (
    RuntimeOverrides,
    apply_configuration,
    apply_configuration_for_source_management,
    redact_text,
)
from agent_artifacts.configuration.schema import (
    parse_organization_policy,
    parse_user_configuration,
)
from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.result import Err, Ok
from tests.credential_fixtures import assignment, credential_url


def _config(document: str):
    result = parse_user_configuration(document)
    assert isinstance(result, Ok)
    return result.value


def _policy(document: str):
    result = parse_organization_policy(document)
    assert isinstance(result, Ok)
    return result.value


class ConfigurationPolicyTest(unittest.TestCase):
    def test_runtime_precedence_applies_before_policy_locked_values(self) -> None:
        user = _config(
            """{
              "schema_version":1,
              "sources":[{"alias":"company","kind":"registry-git","url":"https://github.company.example/agents/registry.git","ref":"main","enabled":true}],
              "sync":{"mode":"auto","max_age_seconds":900}
            }"""
        )
        policy = _policy(
            """{
              "schema_version":1,
              "allowed_git_hosts":["github.company.example"],
              "allowed_repository_prefixes":["agents/"]
            }"""
        )

        result = apply_configuration(
            user,
            RuntimeOverrides(
                default_registry=SourceAlias("company"),
                sync_mode=SyncMode.MANUAL,
                max_age_seconds=10,
            ),
            policy,
        )

        self.assertIsInstance(result, Ok)
        assert isinstance(result, Ok)
        self.assertEqual(str(result.value.configuration.default_registry), "company")
        self.assertIs(result.value.configuration.sync.mode, SyncMode.MANUAL)
        self.assertEqual(result.value.configuration.sync.max_age_seconds, 10)
        self.assertEqual(result.value.locked_fields, ())

    def test_policy_checks_direct_sources_hosts_prefixes_and_required_aliases(self) -> None:
        direct = _config(
            """{
              "schema_version":1,
              "sources":[{"alias":"team","kind":"source-git","url":"https://github.com/team/repo.git","ref":"main","enabled":true}]
            }"""
        )
        registry = _config(
            """{
              "schema_version":1,
              "sources":[{"alias":"company","kind":"registry-git","url":"https://github.company.example/other/registry.git","ref":"main","enabled":true}]
            }"""
        )
        cases = (
            (direct, _policy('{"schema_version":1,"allow_direct_sources":false}')),
            (
                direct,
                _policy('{"schema_version":1,"allowed_git_hosts":["github.company.example"]}'),
            ),
            (registry, _policy('{"schema_version":1,"allowed_repository_prefixes":["agents/"]}')),
            (registry, _policy('{"schema_version":1,"required_sources":["missing"]}')),
        )

        for config, policy in cases:
            with self.subTest(config=config, policy=policy):
                result = apply_configuration(config, RuntimeOverrides(), policy)
                self.assertIsInstance(result, Err)
                assert isinstance(result, Err)
                self.assertTrue(
                    all(item.code.value == "source-policy-denied" for item in result.diagnostics)
                )

    def test_source_management_can_stage_required_sources_without_authorizing_content(self) -> None:
        company_only = _config(
            """{
              "schema_version":1,
              "sources":[{"alias":"company","kind":"registry-git","url":"https://git.company.example/agents/company.git","ref":"main","enabled":true}],
              "default_registry":"company"
            }"""
        )
        policy = _policy(
            """{
              "schema_version":1,
              "required_sources":["company","team"],
              "allowed_git_hosts":["git.company.example"],
              "allowed_repository_prefixes":["agents/"]
            }"""
        )

        content = apply_configuration(company_only, RuntimeOverrides(), policy)
        management = apply_configuration_for_source_management(company_only, policy)

        self.assertIsInstance(content, Err)
        self.assertIsInstance(management, Ok)
        assert isinstance(content, Err)
        self.assertEqual(content.diagnostics[0].code.value, "source-policy-denied")

        forbidden_direct = _config(
            """{
              "schema_version":1,
              "sources":[{"alias":"external","kind":"source-git","url":"https://git.company.example/agents/external.git","ref":"main","enabled":true}]
            }"""
        )
        direct_denied = apply_configuration_for_source_management(
            forbidden_direct,
            _policy('{"schema_version":1,"allow_direct_sources":false}'),
        )
        self.assertIsInstance(direct_denied, Err)

    def test_diagnostics_are_redacted(self) -> None:
        self.assertEqual(
            redact_text(
                "failed "
                + credential_url(
                    "example.test",
                    "/repo?token=abc " + assignment("password", "hunter2"),
                    held="token",
                )
            ),
            "failed https://[redacted]@example.test/repo?token=[redacted] password=[redacted]",
        )

    def test_runtime_values_and_direct_domain_inputs_are_validated_before_effects(self) -> None:
        base = _config(
            """{
              "schema_version":1,
              "sources":[{"alias":"company","kind":"registry-git","url":"https://example.test/team/registry.git","ref":"main","enabled":true}]
            }"""
        )
        invalid_runtime = (
            RuntimeOverrides(max_age_seconds=-1),
            RuntimeOverrides(default_registry=SourceAlias("missing")),
        )
        for overrides in invalid_runtime:
            with self.subTest(overrides=overrides):
                self.assertIsInstance(
                    apply_configuration(base, overrides, _policy('{"schema_version":1}')),
                    Err,
                )

        malformed_git = ConfiguredSource(
            SourceAlias("malformed"), SourceKind.SOURCE_GIT, "not-a-url", "main", True
        )
        local = ConfiguredSource(
            SourceAlias("local"), SourceKind.SOURCE_LOCAL, "/work/source", None, True
        )
        direct = UserConfiguration(1, (malformed_git, local), None, SyncSettings())
        denied = apply_configuration(
            direct,
            RuntimeOverrides(),
            _policy('{"schema_version":1,"allow_direct_sources":false}'),
        )
        self.assertIsInstance(denied, Err)
        assert isinstance(denied, Err)
        self.assertGreaterEqual(len(denied.diagnostics), 3)

    def test_allowed_constraints_succeed(self) -> None:
        configuration = _config(
            """{
              "schema_version":1,
              "sources":[{"alias":"private","kind":"registry-git","url":"https://git.company.test/team/registry.git","ref":"main","enabled":true}]
            }"""
        )
        policy = _policy(
            """{
              "schema_version":1,
              "allowed_git_hosts":["git.company.test"],
              "allowed_repository_prefixes":["team/"]
            }"""
        )

        self.assertIsInstance(
            apply_configuration(configuration, RuntimeOverrides(), policy),
            Ok,
        )


if __name__ == "__main__":
    unittest.main()
