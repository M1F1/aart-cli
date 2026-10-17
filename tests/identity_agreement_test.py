"""The consumer refuses a registry whose two identity documents disagree.

A registry whose `aart-cli-registry.json` and `aart-cli-source.json` declare different identities is
refused by `registry validate --strict --frozen` — the publisher's own gate — and must be refused by
every consumer path too, because it is the value the entire subscription model pins.

This applies the one-way adaptation rule: a consumer does not soften a rule the
publisher's tooling already enforces. The agreement is checked at acquisition, whenever a
snapshot carries both documents: on `consume registry sync` for a Registry, and on `maintain
upstream add` for an Upstream repository that carries a Registry marker it should not.
"""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from tests.marketplace_lifecycle_e2e_test import _COORDINATE, _FIXTURE, _environment
from tests.reference_registry import commit
from tests.source_project_isolation_test import _source
from tests.source_sync_command_e2e_test import _environment_over_a_writable_source

_DECLARED = "reference-native-source"
_DISAGREEING = "some-other-identity"


def _registry_document(registry_id: str) -> str:
    """A valid `aart-cli-registry.json` at one chosen identity.

    It must actually parse: the agreement check has nothing to compare against a malformed registry
    marker, so a document short of the schema's required fields would make these tests pass for the
    wrong reason.
    """

    return json.dumps(
        {
            "schema_version": 1,
            "protocol_version": 1,
            "registry_id": registry_id,
            "display_name": "Reference Registry",
            "requires_aart": {"min_inclusive": "1.0.0", "max_exclusive": "3.0.0"},
            "required_capabilities": ["artifact-manifest-v1"],
            "default_channel": "main",
            "services": {},
        },
        indent=2,
    )


class IdentityAgreementTest(unittest.TestCase):
    def _source_copy(self, root: Path, name: str) -> Path:
        copy = root / name
        shutil.copytree(_FIXTURE, copy)
        return copy

    def _upstream_add(self, env, location: Path):
        return _source(
            env,
            "maintain",
            "upstream",
            "add",
            "--alias",
            "mirror",
            "--kind",
            "local",
            "--location",
            str(location),
        )

    def test_an_upstream_publishing_only_aart_source_json_is_unaffected(self) -> None:
        """The check must not turn every ordinary native Upstream repository into a registry."""

        with _environment() as env:
            mirror = self._source_copy(env.root, "plain-mirror")
            self.assertFalse((mirror / "aart-cli-registry.json").exists())

            code, payload = self._upstream_add(env, mirror)

            self.assertEqual(code, 0, payload)

    def test_agreeing_identity_documents_are_accepted(self) -> None:
        """The reference Registry carries both documents, and they agree."""

        with _environment() as env:
            markers = [
                json.loads((env.source_location / name).read_text(encoding="utf-8"))
                for name in ("aart-cli-registry.json", "aart-cli-source.json")
            ]
            self.assertEqual(markers[0]["registry_id"], markers[1]["source_id"])

            code, payload = env.run(
                "consume", "install", _COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, payload)

    def test_registry_sync_refuses_disagreeing_identity_documents(self) -> None:
        with _environment_over_a_writable_source() as (env, location):
            # Synchronized once while the documents agreed, so the refusal below is the sync
            # itself and not a first-acquisition failure.
            marker = location / "aart-cli-registry.json"
            document = json.loads(marker.read_text(encoding="utf-8"))
            document["registry_id"] = _DISAGREEING
            marker.write_text(json.dumps(document), encoding="utf-8")
            commit(location)

            code, payload = _source(env, "consume", "registry", "sync", "--alias", "reference")

            self.assertEqual(code, 1, payload)
            self.assertFalse(payload["registries"][0]["ok"], payload)
            diagnostic = self._only_diagnostic(payload["registries"][0])
            self.assertEqual(diagnostic["code"], "source-invalid")
            self.assertIn("aart-cli-registry.json", diagnostic["message"])
            self.assertIn("aart-cli-source.json", diagnostic["message"])
            self.assertIn(_DECLARED, diagnostic["message"])
            self.assertIn(_DISAGREEING, diagnostic["message"])
            self.assertTrue(diagnostic["remediation"], diagnostic)

    def test_upstream_add_refuses_disagreeing_identity_documents(self) -> None:
        with _environment() as env:
            mirror = self._source_copy(env.root, "disagreeing-mirror")
            (mirror / "aart-cli-registry.json").write_text(
                _registry_document(_DISAGREEING), encoding="utf-8"
            )

            code, payload = _source(
                env,
                "maintain",
                "upstream",
                "add",
                "--alias",
                "mirror",
                "--kind",
                "local",
                "--location",
                str(mirror),
            )

            self.assertEqual(code, 1, payload)
            diagnostic = self._only_diagnostic(payload)
            self.assertEqual(diagnostic["code"], "source-invalid")
            self.assertIn(_DISAGREEING, diagnostic["message"])
            # A refused subscription is not a subscription: nothing may be left configured.
            _, listed = _source(env, "maintain", "upstream", "list")
            self.assertNotIn("mirror", [item["alias"] for item in listed["upstreams"]])

    def test_rs08_a_registry_marker_that_does_not_parse_is_refused(self) -> None:
        """The skipped check, taken as its own decision.

        A source shaped like a registry whose `aart-cli-registry.json` is broken must not be admitted in
        silence — it is the one file that declares the identity the whole subscription model pins.
        A marker that is present must parse; there is no third state where it is ignored.
        """

        with _environment() as env:
            mirror = self._source_copy(env.root, "broken-marker-mirror")
            (mirror / "aart-cli-registry.json").write_text(
                json.dumps({"schema_version": 1, "registry_id": _DECLARED}), encoding="utf-8"
            )

            code, payload = _source(
                env,
                "maintain",
                "upstream",
                "add",
                "--alias",
                "mirror",
                "--kind",
                "local",
                "--location",
                str(mirror),
            )

            self.assertEqual(code, 1, payload)
            diagnostic = self._only_diagnostic(payload)
            self.assertEqual(diagnostic["code"], "source-invalid")
            self.assertIn("aart-cli-registry.json", diagnostic["message"])
            self.assertIn("does not parse", diagnostic["message"])
            self.assertTrue(diagnostic["remediation"], diagnostic)
            _, listed = _source(env, "maintain", "upstream", "list")
            self.assertNotIn("mirror", [item["alias"] for item in listed["upstreams"]])

    def test_rs08_a_marker_that_is_not_json_at_all_is_refused(self) -> None:
        with _environment() as env:
            mirror = self._source_copy(env.root, "not-json-mirror")
            (mirror / "aart-cli-registry.json").write_text(
                "this is not a registry", encoding="utf-8"
            )

            code, payload = _source(
                env,
                "maintain",
                "upstream",
                "add",
                "--alias",
                "mirror",
                "--kind",
                "local",
                "--location",
                str(mirror),
            )

            self.assertEqual(code, 1, payload)
            self.assertIn("does not parse", self._only_diagnostic(payload)["message"])

    def test_rs08_a_marker_broken_after_subscription_is_refused_by_sync(self) -> None:
        """The subscription is re-validated on every sync, so the gap closes on both paths."""

        with _environment_over_a_writable_source() as (env, location):
            (location / "aart-cli-registry.json").write_text("{", encoding="utf-8")
            commit(location)

            code, payload = _source(env, "consume", "registry", "sync", "--alias", "reference")

            self.assertEqual(code, 1, payload)
            self.assertFalse(payload["registries"][0]["ok"], payload)
            diagnostic = self._only_diagnostic(payload["registries"][0])
            self.assertEqual(diagnostic["code"], "protocol-json-invalid")
            self.assertEqual(diagnostic["location"]["path"], "aart-cli-registry.json")
            self.assertIn("last synchronized snapshot", diagnostic["remediation"][0])

    def _only_diagnostic(self, payload) -> dict:
        diagnostics = payload["diagnostics"]
        self.assertEqual(len(diagnostics), 1, payload)
        return diagnostics[0]


if __name__ == "__main__":
    unittest.main()
