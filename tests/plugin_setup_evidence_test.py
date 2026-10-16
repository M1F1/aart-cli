"""A plugin's settings entry is the effect its setup evidence proves."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from aart_cli.consumer.configured_setup import _effect_proofs
from aart_cli.domain.harness import Scope
from aart_cli.domain.hooks import PluginEntry
from aart_cli.domain.receipts import ArtifactSettingsEntry, PlacedArtifactReceipt
from aart_cli.protocol.hashing import sha256_bytes

COORDINATE = "company/plugin/superpowers"
TREE = ".opencode/aart-cli/plugin/company/superpowers"
REFERENCE = f"./{TREE}/payload/.opencode/plugins/superpowers.js"


class APluginIsSetupEvidenceTest(unittest.TestCase):
    """Setup completion reads an installation's effects; a plugin's only one is its entry.

    Measured live on 2026-10-15: with deliveries and merges the only effects read, a plugin
    install reported `setup completion is unavailable`, because its receipt proved nothing.
    """

    def test_the_entry_is_proved_as_one_member_of_the_list(self) -> None:
        receipt = PlacedArtifactReceipt(
            COORDINATE,
            f"/p/{TREE}",
            sha256_bytes(b"payload"),
            settings=(
                ArtifactSettingsEntry(
                    "opencode", "/p/opencode.json", "plugin", PluginEntry(REFERENCE)
                ),
            ),
        )
        host = SimpleNamespace(scope=Scope.PROJECT, project_root="/p")

        (proof,) = _effect_proofs(receipt, profile="opencode", host=host)  # type: ignore[arg-type]

        self.assertEqual(
            ("merge-json", "opencode.json", "plugin", "list"),
            (proof.kind, proof.destination, proof.json_path, proof.merge_mode),
        )
        self.assertEqual((), _effect_proofs(receipt, profile="claude", host=host))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
