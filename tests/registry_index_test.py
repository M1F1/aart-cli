from __future__ import annotations

import json
import unittest
from dataclasses import replace
from types import MappingProxyType

from agent_artifacts.domain.identifiers import ObjectDigest, SourceId
from agent_artifacts.domain.result import Ok
from agent_artifacts.model import SetupCapability, SetupInstaller, SetupStep
from agent_artifacts.protocol.native_models import CollectionManifest
from agent_artifacts.protocol.native_schema import (
    parse_artifact_manifest,
    parse_collection_manifest,
    parse_provenance,
)
from agent_artifacts.protocol.native_tree import NativeArtifactPackage
from agent_artifacts.protocol.registry_index import (
    index_artifact_from_package,
)
from agent_artifacts.protocol.registry_models import ReviewRecord
from agent_artifacts.protocol.registry_schema import (
    parse_registry_manifest,
)


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _manifest_json(name: str) -> str:
    return f"""{{
      "schema_version": 1,
      "type": "skill",
      "name": "{name}",
      "version": "1.2.0",
      "summary": "Use {name} during agent work.",
      "requires_aart": {{"min_inclusive": "1.1.0", "max_exclusive": "2.0.0"}},
      "payload": {{"root": "payload", "format": "aart-skill-v1"}},
      "compatibility": {{"profiles": ["tabnine", "claude"], "platforms": ["linux", "darwin"]}},
      "install": {{"scopes": ["user", "project"], "modes": ["symlink", "copy"], "effects": ["copy-tree"]}}
    }}"""


def _registry():
    result = parse_registry_manifest(
        """{
          "schema_version": 1,
          "protocol_version": 1,
          "registry_id": "company-registry",
          "display_name": "Company Registry",
          "requires_aart": {"min_inclusive": "1.0.0", "max_exclusive": "2.0.0"},
          "required_capabilities": ["registry-entry-v1"],
          "default_channel": "main",
          "services": {}
        }"""
    )
    assert isinstance(result, Ok)
    return result.value


def _package(
    name: str, *, requires: list[dict[str, object]] | None = None
) -> NativeArtifactPackage:
    document = json.loads(_manifest_json(name))
    if requires is not None:
        document["requires"] = requires
    manifest = parse_artifact_manifest(json.dumps(document))
    assert isinstance(manifest, Ok)
    return NativeArtifactPackage(manifest.value, None, _digest("1"), _digest("2"))


def _configured_package() -> NativeArtifactPackage:
    manifest = parse_artifact_manifest(
        """{
          "schema_version": 1,
          "type": "mcp",
          "name": "atlassian",
          "version": "2.1.0",
          "summary": "Connect reviewed Atlassian tools.",
          "payload": {"root": "payload", "format": "aart-mcp-v1"},
          "compatibility": {"profiles": ["claude"], "platforms": ["darwin"]},
          "install": {"scopes": ["user"], "modes": ["copy"], "effects": ["merge-json"]},
          "setup": {"recipe": "setup/installer.json", "platforms": ["darwin"]}
        }"""
    )
    provenance = parse_provenance(
        f"""{{
          "schema_version": 1,
          "origin": {{
            "kind": "git",
            "url": "https://github.example/platform/atlassian.git",
            "resolved_commit": "{"a" * 40}",
            "path": "artifacts/mcp/atlassian",
            "input_digest": "{_digest("4")}"
          }},
          "importer": {{
            "id": "native-importer",
            "version": "1.0.0",
            "options_digest": "{_digest("5")}"
          }},
          "warnings": []
        }}"""
    )
    assert isinstance(manifest, Ok)
    assert isinstance(provenance, Ok)
    return NativeArtifactPackage(manifest.value, provenance.value, _digest("1"), _digest("2"))


def _installer(
    capabilities: tuple[SetupCapability, ...],
    steps: tuple[SetupStep, ...] = (),
) -> SetupInstaller:
    """The compiled recipe reduced to the fields the index has to carry across."""

    return SetupInstaller(
        schema_version=2,
        protocol_version=2,
        artifact="atlassian",
        purpose="Connect reviewed Atlassian tools.",
        platforms=("darwin",),
        help_urls=(),
        required_tools=(),
        capabilities=capabilities,
        inputs=(),
        steps=steps,
        descriptor_path="setup/installer.json",
        descriptor_hash="b" * 64,
        manual_path="SETUP.md",
    )


def _collection(name: str, artifacts: list[str], collections: list[str]) -> CollectionManifest:
    selectors = ",".join(f'{{"type":"skill","name":"{artifact}"}}' for artifact in artifacts)
    nested = ",".join(f'"{collection}"' for collection in collections)
    result = parse_collection_manifest(
        f"""{{
          "schema_version": 1,
          "name": "{name}",
          "summary": "The {name} collection.",
          "artifacts": [{selectors}],
          "collections": [{nested}]
        }}"""
    )
    assert isinstance(result, Ok)
    return result.value


class RegistryIndexTest(unittest.TestCase):
    def test_registry_owned_package_becomes_index_record_without_duplicate_entry(self) -> None:
        record = index_artifact_from_package(
            _package("code-review"),
            source_id=SourceId("company-registry"),
            object_digest=_digest("3"),
            review=ReviewRecord("approved", "company-review-v1"),
        )

        self.assertEqual(str(record.identity), "skill/code-review")
        self.assertEqual(record.summary, "Use code-review during agent work.")
        self.assertEqual(str(record.requires_aart.min_inclusive), "1.1.0")
        self.assertEqual(str(record.requires_aart.max_exclusive), "2.0.0")
        self.assertEqual(record.collections, ())
        self.assertIsNone(record.provenance)

    def test_setup_and_provenance_are_summarized_without_content(self) -> None:
        record = index_artifact_from_package(
            _configured_package(),
            source_id=SourceId("company-registry"),
            object_digest=_digest("3"),
        )

        self.assertIsNotNone(record.setup)
        self.assertIsNotNone(record.provenance)
        assert record.setup is not None
        assert record.provenance is not None
        self.assertEqual(str(record.setup.recipe), "setup/installer.json")
        self.assertEqual(record.provenance.resolved_commit, "a" * 40)

    def test_setup_capabilities_are_published_from_the_compiled_recipe(self) -> None:
        # An empty published set would make the consumer-side capability gate inert, so every
        # artifact would look installable-and-runnable regardless of what its setup requires.
        # What is published is what the *steps* need, in the vocabulary a policy speaks — not the
        # author's declaration, which the consumer never recomputes and could not compare against.
        package = _configured_package()
        compiled = replace(
            package,
            setup_installer=_installer(
                ("docker", "keychain", "filesystem"),
                steps=(
                    SetupStep(
                        id="image",
                        use="docker.build@1",
                        config=MappingProxyType({"context": "payload"}),
                    ),
                    SetupStep(
                        id="token",
                        use="macos-keychain.store@1",
                        config=MappingProxyType(
                            {"input": "api_token", "service": "s", "account": "a"}
                        ),
                    ),
                ),
            ),
        )

        record = index_artifact_from_package(
            compiled,
            source_id=SourceId("company-registry"),
            object_digest=_digest("3"),
        )

        assert record.setup is not None
        self.assertEqual(
            tuple(str(item) for item in record.setup.capabilities),
            ("docker-build", "keychain", "network", "process"),
        )

    def test_a_recipe_that_declares_much_and_does_nothing_publishes_nothing(self) -> None:
        """The declaration is the author's; the evidence is the steps'."""

        compiled = replace(
            _configured_package(),
            setup_installer=_installer(("docker", "keychain", "process")),
        )

        record = index_artifact_from_package(
            compiled,
            source_id=SourceId("company-registry"),
            object_digest=_digest("3"),
        )

        assert record.setup is not None
        self.assertEqual(record.setup.capabilities, ())


if __name__ == "__main__":
    unittest.main()
