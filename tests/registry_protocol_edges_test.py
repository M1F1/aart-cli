from __future__ import annotations

import json
import unittest
from typing import Callable

from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.protocol.registry_schema import (
    parse_registry_manifest,
)


def _digest(character: str) -> str:
    return f"sha256:{character * 64}"


def _manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "protocol_version": 1,
        "registry_id": "company-registry",
        "display_name": "Company Registry",
        "requires_aart": {"min_inclusive": "1.0.0", "max_exclusive": "2.0.0"},
        "required_capabilities": ["registry-entry-v1"],
        "default_channel": "main",
        "services": {
            "usage_reporting": {
                "kind": "github-issues",
                "repository": "agents/company-registry",
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
            "url": "https://github.example/platform/atlassian.git",
            "ref": "main",
            "path": "artifacts/mcp/atlassian",
        },
        "review": {"status": "approved", "policy": "review-v1"},
    }


def _locked() -> dict[str, object]:
    return {
        "origin_url": "https://github.example/platform/atlassian.git",
        "requested_ref": "main",
        "resolved_commit": "a" * 40,
        "path": "artifacts/mcp/atlassian",
        "manifest_digest": _digest("1"),
        "payload_digest": _digest("2"),
        "object_digest": _digest("3"),
        "artifact_version": "2.1.0",
        "review": {"status": "approved", "policy": "review-v1"},
        "provenance_digest": _digest("4"),
    }


def _lock() -> dict[str, object]:
    return {
        "schema_version": 1,
        "registry_inputs_digest": _digest("0"),
        "entries": {"mcp/atlassian": _locked()},
    }


def _index_artifact() -> dict[str, object]:
    return {
        "source_id": "company-registry",
        "type": "mcp",
        "name": "atlassian",
        "version": "2.1.0",
        "summary": "Connect reviewed Atlassian tools.",
        "manifest_digest": _digest("1"),
        "payload_digest": _digest("2"),
        "object_digest": _digest("3"),
        "compatibility": {
            "profiles": ["claude", "tabnine"],
            "platforms": ["darwin", "linux"],
        },
        "install": {
            "scopes": ["project", "user"],
            "modes": ["copy"],
            "effects": ["merge-json"],
        },
        "setup": {
            "recipe": "setup/installer.json",
            "platforms": ["darwin"],
            "capabilities": ["keychain-write-v1"],
        },
        "review": {"status": "approved", "policy": "review-v1"},
        "provenance": {
            "origin_url": "https://github.example/platform/atlassian.git",
            "resolved_commit": "a" * 40,
            "path": "artifacts/mcp/atlassian",
        },
        "collections": ["essentials"],
    }


def _collection(name: str = "essentials") -> dict[str, object]:
    return {
        "name": name,
        "summary": "Reviewed essentials.",
        "artifacts": [{"type": "mcp", "name": "atlassian"}],
        "collections": [],
    }


def _index() -> dict[str, object]:
    return {
        "schema_version": 1,
        "protocol_version": 1,
        "registry_id": "company-registry",
        "registry_inputs_digest": _digest("0"),
        "artifacts": [_index_artifact()],
        "collections": [_collection()],
        "services": {},
    }


def _encoded(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


Parser = Callable[[bytes | str], Result[object]]


class RegistryProtocolEdgesTest(unittest.TestCase):
    def assert_invalid(self, parser: Parser, value: object) -> None:
        self.assertIsInstance(parser(_encoded(value)), Err)

    def test_manifest_scalar_version_and_capability_edges_fail_closed(self) -> None:
        mutations: tuple[tuple[str, object], ...] = (
            ("schema_version", "1"),
            ("schema_version", 2),
            ("protocol_version", "1"),
            ("protocol_version", 2),
            ("registry_id", "Bad ID"),
            ("display_name", "two\nlines"),
            ("display_name", ""),
            ("requires_aart", []),
            ("required_capabilities", "registry-entry-v1"),
            ("required_capabilities", [1]),
            ("required_capabilities", ["Bad Capability"]),
            ("default_channel", "--unsafe"),
            ("default_channel", "feature//bad"),
            ("default_channel", "feature."),
            ("default_channel", "feature bad"),
            ("default_channel", "@"),
            ("default_channel", ".hidden/main"),
            ("default_channel", "release.lock"),
            ("services", []),
        )
        for field, replacement in mutations:
            with self.subTest(field=field, replacement=replacement):
                value = _manifest()
                value[field] = replacement
                self.assert_invalid(parse_registry_manifest, value)

        for bounds in (
            {"unknown": "1.0.0"},
            {"min_inclusive": 1},
            {"min_inclusive": "bad"},
            {"max_exclusive": 2},
            {"max_exclusive": "bad"},
            {"min_inclusive": "2.0.0", "max_exclusive": "1.0.0"},
        ):
            with self.subTest(bounds=bounds):
                value = _manifest()
                value["requires_aart"] = bounds
                self.assert_invalid(parse_registry_manifest, value)

    def test_manifest_service_shapes_fail_closed(self) -> None:
        services = (
            {"bad-name": {"kind": "github-issues", "repository": "org/repo"}},
            {"usage_reporting": "github-issues"},
            {"usage_reporting": {}},
            {"usage_reporting": {"kind": 1}},
            {"usage_reporting": {"kind": "Bad Kind"}},
            {"usage_reporting": {"kind": "github-issues", "repository": 1}},
            {
                "usage_reporting": {
                    "kind": "github-issues",
                    "repository": "https://example.test/org/repo",
                }
            },
            {"usage_reporting": {"kind": "custom", "repository": "org/repo", "enabled": True}},
        )
        for replacement in services:
            with self.subTest(replacement=replacement):
                value = _manifest()
                value["services"] = replacement
                self.assert_invalid(parse_registry_manifest, value)

    def test_service_kinds_have_no_provider_specific_repository_rule(self) -> None:
        value = _manifest()
        value["services"] = {"legacy_service": {"kind": "github-issues"}}

        self.assertIsInstance(parse_registry_manifest(_encoded(value)), Ok)


if __name__ == "__main__":
    unittest.main()
