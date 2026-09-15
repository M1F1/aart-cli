"""Wave-0 smoke tests: the still-shipped legacy contracts import and are immutable.

Run: ``python -m unittest discover -s tests -p "*_test.py"``
"""

import dataclasses
import unittest

from agent_artifacts import model
from agent_artifacts.model import (
    Artifact,
    ManifestEntry,
    MergeJson,
    Resolved,
    WriteFile,
    source_label,
)


class ContractTests(unittest.TestCase):
    def test_records_are_frozen(self):
        art = Artifact(type="skill", name="code-review", root="skills/code-review")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            art.name = "other"  # type: ignore[misc]

    def test_action_algebra_present(self):
        plan: model.Plan = (
            WriteFile(path="a.txt", content=b"x"),
            MergeJson(
                file=".mcp.json", json_path="mcpServers", mode="key", value={}, identity=("name",)
            ),
        )
        self.assertEqual(len(plan), 2)

    def test_source_label(self):
        self.assertEqual(source_label(Resolved(kind="main", sha="abc123")), "main:abc123")

    def test_manifest_entry_defaults(self):
        e = ManifestEntry(artifact="postgres", type="mcp", profile="claude", source="main:abc")
        self.assertEqual(e.files, {})
        self.assertIsNone(e.merge)


if __name__ == "__main__":
    unittest.main()
