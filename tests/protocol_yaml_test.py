"""Finite, dependency-free YAML grammar used only for AART author manifests."""

from __future__ import annotations

import unittest

from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.protocol.json import JsonArray, JsonObject
from agent_artifacts.protocol.yaml import parse_yaml


class ProtocolYamlTest(unittest.TestCase):
    def test_block_mappings_sequences_comments_and_scalar_types(self) -> None:
        parsed = parse_yaml(
            """name: artifact # comment
enabled: true
attempts: 3
unset: null
paths:
  - src/**
  - "**/__pycache__/**"
quoted: 'single '' quote'
"""
        )

        self.assertIsInstance(parsed, Ok)
        assert isinstance(parsed, Ok) and isinstance(parsed.value, JsonObject)
        fields = dict(parsed.value.entries)
        self.assertEqual(fields["name"], "artifact")
        self.assertEqual(fields["enabled"], True)
        self.assertEqual(fields["attempts"], 3)
        self.assertIsNone(fields["unset"])
        self.assertEqual(fields["quoted"], "single ' quote")
        self.assertEqual(fields["paths"], JsonArray(("src/**", "**/__pycache__/**")))

    def test_sequence_mappings_support_declarative_input_shapes(self) -> None:
        parsed = parse_yaml(
            """inputs:
  - id: github-token
    kind: secret
    required: true
    inject:
      type: environment
      name: GITHUB_TOKEN
"""
        )

        self.assertIsInstance(parsed, Ok)
        assert isinstance(parsed, Ok) and isinstance(parsed.value, JsonObject)
        inputs = parsed.value.get("inputs")
        self.assertIsInstance(inputs, JsonArray)
        assert isinstance(inputs, JsonArray) and isinstance(inputs.items[0], JsonObject)
        self.assertEqual(inputs.items[0].get("id"), "github-token")
        inject = inputs.items[0].get("inject")
        self.assertIsInstance(inject, JsonObject)
        assert isinstance(inject, JsonObject)
        self.assertEqual(inject.get("name"), "GITHUB_TOKEN")

    def test_unquoted_url_is_a_scalar_not_a_mapping(self) -> None:
        parsed = parse_yaml("urls:\n  - https://example.invalid/help\n")

        self.assertIsInstance(parsed, Ok)
        assert isinstance(parsed, Ok) and isinstance(parsed.value, JsonObject)
        self.assertEqual(parsed.value.get("urls"), JsonArray(("https://example.invalid/help",)))

    def test_duplicate_keys_and_unsafe_yaml_features_are_rejected(self) -> None:
        invalid_documents = (
            "name: one\nname: two\n",
            "value: &anchor data\n",
            "value: *anchor\n",
            "value: !custom data\n",
            "value: [one, two]\n",
            "value: |\n  block\n",
            "---\nname: artifact\n",
        )
        for document in invalid_documents:
            with self.subTest(document=document):
                parsed = parse_yaml(document)
                self.assertIsInstance(parsed, Err)
                assert isinstance(parsed, Err)
                self.assertEqual(parsed.diagnostics[0].code.value, "author-manifest-invalid")

    def test_malformed_encoding_indentation_and_strings_are_diagnostics(self) -> None:
        invalid_documents: tuple[bytes | str, ...] = (
            b"name: \xff",
            " name: artifact\n",
            "name:\n   nested: value\n",
            "name:\n",
            'name: "unterminated\n',
            "items:\n  -\n",
            "items:\n  - id: one\n      kind: config\n",
            "",
        )
        for document in invalid_documents:
            with self.subTest(document=document):
                self.assertIsInstance(parse_yaml(document), Err)


if __name__ == "__main__":
    unittest.main()
