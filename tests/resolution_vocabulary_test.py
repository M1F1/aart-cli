"""A resolution failure names the layer that failed, not the artifact.

Four unrelated stressors -- an alias no Registry answers to, an Upstream repository named where a
Registry belongs, a Registry configured but never synchronized, and a name the Registry really does
not offer -- must not all report `artifact-not-found` about the one part of the request that was
never wrong. An operator sent to look for a correctly spelled name learns nothing.

Each case is driven through the real CLI, because the vocabulary is only worth anything if it
survives to the JSON an agent reads.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from aart_cli.configuration.model import (
    ConfiguredSource,
    SourceKind,
    SyncMode,
    SyncSettings,
    UserConfiguration,
)
from aart_cli.configuration.schema import user_configuration_bytes
from aart_cli.domain.identifiers import SourceAlias
from tests.marketplace_lifecycle_e2e_test import _environment
from tests.reference_registry import REFERENCE_CONTENT, reference_snapshot, write_reference_registry

_COLD = "mirror/skill/code-review"
_UPSTREAM = "drafts/skill/code-review"


def _configure_cold_registry_and_an_upstream(env) -> None:
    """Add a Registry that was never synchronized, and an Upstream repository, to the configuration.

    This is the state a machine is in after a configuration arrives ahead of its content -- a fresh
    checkout of someone's dotfiles, a restored home directory -- and it is exactly the state
    `registry add` cannot produce, because adding synchronizes.
    """

    mirror = write_reference_registry(
        env.root / "mirror-registry",
        # A distinct identity: two subscriptions to one Registry ID is a different refusal.
        reference_snapshot(*REFERENCE_CONTENT, declared_id="mirror-registry"),
    )
    cold = ConfiguredSource(
        SourceAlias("mirror"), SourceKind.REGISTRY_LOCAL, str(mirror), "main", True
    )
    upstream = ConfiguredSource(
        SourceAlias("drafts"), SourceKind.SOURCE_LOCAL, str(env.root / "drafts"), None, True
    )
    Path(env.paths.user_config_file).write_bytes(
        user_configuration_bytes(
            UserConfiguration(
                1, (env.source, cold, upstream), None, SyncSettings(mode=SyncMode.MANUAL)
            )
        )
    )


class ResolutionFailureVocabularyTest(unittest.TestCase):
    def _diagnostic(self, payload) -> dict:
        self.assertFalse(payload["ok"], payload)
        self.assertEqual(len(payload["diagnostics"]), 1, payload)
        return payload["diagnostics"][0]

    def test_an_unconfigured_alias_reports_the_registry_not_the_artifact(self) -> None:
        with _environment() as env:
            code, payload = env.run(
                "consume", "install", "ghost/skill/code-review", "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 1)
            diagnostic = self._diagnostic(payload)
            self.assertEqual(diagnostic["code"], "registry-unavailable")
            self.assertIn("ghost", diagnostic["message"])
            self.assertIn(
                "aart-cli consume registry add --alias ghost --kind git --location <url>",
                diagnostic["remediation"],
            )

    def test_an_upstream_alias_is_refused_as_an_upstream(self) -> None:
        """INV-269: the name is right, and it names something a consumer never installs from."""

        with _environment() as env:
            _configure_cold_registry_and_an_upstream(env)

            code, payload = env.run("consume", "install", _UPSTREAM, "--profile", "claude", "--yes")

            self.assertEqual(code, 1)
            diagnostic = self._diagnostic(payload)
            self.assertEqual(diagnostic["code"], "upstream-not-installable")
            self.assertIn("drafts is an Upstream repository, not a Registry", diagnostic["message"])
            self.assertIn("aart-cli maintain candidate list", diagnostic["remediation"][0])

    def test_a_configured_but_unsynchronized_registry_reports_the_missing_snapshot(self) -> None:
        with _environment() as env:
            _configure_cold_registry_and_an_upstream(env)

            code, payload = env.run("consume", "install", _COLD, "--profile", "claude", "--yes")

            self.assertEqual(code, 1)
            diagnostic = self._diagnostic(payload)
            self.assertEqual(diagnostic["code"], "registry-not-synchronized")
            self.assertEqual(
                diagnostic["remediation"], ["aart-cli consume registry sync --alias mirror"]
            )

    def test_artifact_not_found_survives_for_the_one_case_where_it_is_true(self) -> None:
        with _environment() as env:
            code, payload = env.run(
                "consume", "install", "reference/skill/absent", "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 1)
            diagnostic = self._diagnostic(payload)
            self.assertEqual(diagnostic["code"], "artifact-not-found")
            self.assertEqual(diagnostic["remediation"], ["aart-cli consume list"])

    def test_the_four_causes_do_not_share_one_code(self) -> None:
        """The residue was unrelated stressors collapsing onto one code; assert they separate."""

        with _environment() as env:
            _configure_cold_registry_and_an_upstream(env)
            codes = tuple(
                self._diagnostic(
                    env.run("consume", "install", coordinate, "--profile", "claude", "--yes")[1]
                )["code"]
                for coordinate in (
                    "ghost/skill/code-review",
                    _UPSTREAM,
                    _COLD,
                    "reference/skill/absent",
                )
            )

            self.assertEqual(
                codes,
                (
                    "registry-unavailable",
                    "upstream-not-installable",
                    "registry-not-synchronized",
                    "artifact-not-found",
                ),
            )


if __name__ == "__main__":
    unittest.main()
