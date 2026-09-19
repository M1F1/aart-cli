from __future__ import annotations

import json
import unittest

from aart_cli.domain.result import Err, Ok
from aart_cli.protocol.registry_schema import (
    parse_registry_manifest,
)


def _document(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _digest(character: str) -> str:
    return f"sha256:{character * 64}"


def _registry_manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "protocol_version": 1,
        "registry_id": "company-agent-artifacts",
        "display_name": "Company Agent Artifacts",
        "requires_aart": {"min_inclusive": "1.0.0", "max_exclusive": "2.0.0"},
        "required_capabilities": ["lockfile-v1", "registry-entry-v1"],
        "default_channel": "main",
        "services": {
            "usage_reporting": {
                "kind": "github-issues",
                "repository": "agents/company-agent-artifacts-registry",
            }
        },
    }


def _entry() -> dict[str, object]:
    return {
        "schema_version": 1,
        "type": "mcp",
        "name": "atlassian",
        "source": {
            "kind": "git",
            "url": "git@github.company.example:platform/atlassian-agent-tools.git",
            "ref": "main",
            "path": "artifacts/mcp/atlassian",
        },
        "review": {"status": "approved", "policy": "company-artifact-review-v1"},
    }


def _locked_entry() -> dict[str, object]:
    return {
        "origin_url": "git@github.company.example:platform/atlassian-agent-tools.git",
        "requested_ref": "main",
        "resolved_commit": "a" * 40,
        "path": "artifacts/mcp/atlassian",
        "manifest_digest": _digest("1"),
        "payload_digest": _digest("2"),
        "object_digest": _digest("3"),
        "artifact_version": "2.1.0",
        "review": {"status": "approved", "policy": "company-artifact-review-v1"},
        "provenance_digest": _digest("4"),
    }


class RegistryProtocolSchemaTest(unittest.TestCase):
    def test_registry_manifest_parses_advertised_service_without_enabling_it(self) -> None:
        result = parse_registry_manifest(_document(_registry_manifest()))

        self.assertIsInstance(result, Ok)
        assert isinstance(result, Ok)
        self.assertEqual(str(result.value.registry_id), "company-agent-artifacts")
        self.assertEqual(result.value.default_channel, "main")
        self.assertEqual(result.value.services[0].name, "usage_reporting")
        self.assertEqual(result.value.services[0].kind, "github-issues")
        self.assertEqual(
            result.value.services[0].repository,
            "agents/company-agent-artifacts-registry",
        )

    def test_registry_manifest_rejects_trust_reporting_enablement_and_credentials(self) -> None:
        cases = []
        trust = _registry_manifest()
        trust["trust"] = "trusted"
        cases.append(trust)
        enabled = _registry_manifest()
        assert isinstance(enabled["services"], dict)
        enabled["services"]["usage_reporting"]["enabled"] = True  # type: ignore[index]
        cases.append(enabled)
        credential = _registry_manifest()
        assert isinstance(credential["services"], dict)
        credential["services"]["usage_reporting"]["repository"] = (  # type: ignore[index]
            "https://token@example.test/org/repo"
        )
        cases.append(credential)

        for value in cases:
            with self.subTest(value=value):
                result = parse_registry_manifest(_document(value))
                self.assertIsInstance(result, Err)


if __name__ == "__main__":
    unittest.main()
