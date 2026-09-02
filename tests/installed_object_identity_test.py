"""A canonical receipt names the immutable object its installation came from.

An artifact is installed *from* something: one content-addressed package in the object store,
resolved from the approved registry and materialized once. The receipt records what the effects
left behind -- the delivered tree, its digest, the harness that reads it -- and the root the payload
was copied out of, but not which object that root is. So the durable record cannot answer "which
package is this", and everything that has to go back to the exact installed bytes has to guess.

Post-install setup is where that first bites. `setup_engine/application.py::_prepare_setup_object`
loads the package by object digest and compiles it to find the declared recipe; the legacy
install-state record carries that digest in `ArtifactEvidence` and the canonical receipt does not,
which is one half of why the configured seam runs no setup (B-044, D-120). Repair is the same
question asked later: reconciling against the payload digest alone cannot tell a package apart from
a different package that happens to deliver identical bytes.

The digest is available where the record is written -- `PlannedPlacement.artifact.version` is the
`RegistryArtifactVersion` the Selection resolved, and it carries `object_digest` -- so recording it
is a matter of writing down what the installation already knew, not of deriving anything new.
"""

from __future__ import annotations

import json
import pathlib
import unittest

from agent_artifacts.domain.identifiers import ArtifactCoordinate, ArtifactIdentity, SourceAlias
from agent_artifacts.domain.result import Ok
from agent_artifacts.io.receipt_store import LocalReceiptStore
from tests.configured_install_command_e2e_test import _environment
from tests.configured_installation_draft_e2e_test import AuthoredSetup
from tests.configured_setup_gap_test import AUTHORED, COORDINATE, RECIPE

_INSTALLED = ArtifactCoordinate(
    SourceAlias("company"), ArtifactIdentity("skill", "code-review"), "1.2.0"
)


class InstalledObjectIdentityTest(unittest.TestCase):
    def _installed(self, env):
        code, payload = env.run(
            "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
        )
        self.assertEqual(code, 0, payload)
        store = LocalReceiptStore(str(pathlib.Path(env.paths.data_root) / "state"))
        record = store.record(_INSTALLED)
        self.assertIsInstance(record, Ok, getattr(record, "diagnostics", ()))
        assert isinstance(record, Ok)
        return record.value

    def test_the_receipt_names_the_object_the_installation_was_resolved_to(self) -> None:
        with _environment(authored=AUTHORED, setup=AuthoredSetup(RECIPE)) as env:
            record = self._installed(env)

            self.assertIsNotNone(
                record.receipt.object_digest,
                "the receipt cannot say which package this installation came from",
            )

    def test_the_named_object_is_the_one_that_is_in_the_store(self) -> None:
        """And it resolves, rather than merely being present.

        A digest nothing in the store answers to would be worse than none at all: it reads as an
        identity and behaves as a dangling pointer. So what is asserted is that the object exists
        under that digest and is the package that was installed -- the one whose manifest declares
        the setup this Skill needs, which is the use the digest is being recorded for.
        """

        with _environment(authored=AUTHORED, setup=AuthoredSetup(RECIPE)) as env:
            record = self._installed(env)

            digest = record.receipt.object_digest
            assert digest is not None
            algorithm, value = str(digest).split(":", 1)
            root = pathlib.Path(env.paths.data_root) / "objects" / algorithm / value[:2] / value[2:]
            manifest = json.loads((root / "artifact.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["name"], "code-review")
            self.assertEqual(
                manifest["setup"], {"recipe": "setup/installer.json", "platforms": ["darwin"]}
            )


if __name__ == "__main__":
    unittest.main()
