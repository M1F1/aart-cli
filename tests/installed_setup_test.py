"""What an installed object says about its own setup, and what this reader refuses to guess.

The value is a reading of a package manifest, so the questions worth pinning are the ones where a
reader could plausibly invent an answer: a package that declares no setup, a declaration whose
manual document is not in the object, and a receipt that cannot say which object it came from.
"""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from agent_artifacts.application.installed_setup import (
    DeclaredArtifactSetup,
    declared_artifact_setup,
    declared_setup_to_data,
)
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    ObjectDigest,
    SourceAlias,
)
from agent_artifacts.domain.receipts import (
    ArtifactDelivery,
    DeliveryKind,
    PlacedArtifactReceipt,
)
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.domain.serialization import canonical_json_bytes
from agent_artifacts.io.installed_setup import read_declared_setup
from agent_artifacts.io.receipt_store import LocalReceiptStore
from agent_artifacts.protocol.native_schema import parse_artifact_manifest

COORDINATE = ArtifactCoordinate(
    SourceAlias("company"), ArtifactIdentity("skill", "code-review"), "1.2.0"
)
DIGEST = ObjectDigest("sha256", "a" * 64)

#: The manifest a compiled Skill package carries, as `compile_native_package` writes it.
_MANIFEST: dict = {
    "schema_version": 1,
    "type": "skill",
    "name": "code-review",
    "version": "1.2.0",
    "summary": "Code review",
    "payload": {"format": "aart-skill-v1", "root": "payload"},
    "compatibility": {"platforms": ["darwin", "linux"], "profiles": ["claude"]},
    "install": {"effects": ["copy-tree"], "modes": ["copy"], "scopes": ["project", "user"]},
}


def _manifest(**overrides):
    parsed = parse_artifact_manifest(canonical_json_bytes({**_MANIFEST, **overrides}))
    assert isinstance(parsed, Ok), getattr(parsed, "diagnostics", ())
    return parsed.value


class DeclaredArtifactSetupTest(unittest.TestCase):
    def test_a_package_that_declares_no_setup_declares_nothing(self) -> None:
        found = declared_artifact_setup(
            COORDINATE, DIGEST, _manifest(), package_paths=frozenset({"artifact.json"})
        )

        self.assertIsNone(found)

    def test_a_declaration_names_its_recipe_platforms_and_manual(self) -> None:
        found = declared_artifact_setup(
            COORDINATE,
            DIGEST,
            _manifest(setup={"recipe": "setup/installer.json", "platforms": ["darwin"]}),
            package_paths=frozenset({"artifact.json", "setup/installer.json", "SETUP.md"}),
        )

        self.assertEqual(
            found,
            DeclaredArtifactSetup(
                COORDINATE, DIGEST, "setup/installer.json", ("darwin",), "SETUP.md"
            ),
        )

    def test_a_manual_this_object_does_not_carry_is_named_as_absent(self) -> None:
        """Not asserted from the declaration.

        `compile_native_package` requires a package-root `SETUP.md` beside a setup declaration, so
        a promoted artifact has one -- but this reader parses a manifest rather than compiling, and
        reporting a document it did not see would send somebody who cannot run the recipe to a file
        that is not there.
        """

        found = declared_artifact_setup(
            COORDINATE,
            DIGEST,
            _manifest(setup={"recipe": "setup/installer.json", "platforms": ["darwin"]}),
            package_paths=frozenset({"artifact.json", "setup/installer.json"}),
        )

        assert found is not None
        self.assertIsNone(found.manual)

    def test_a_declaration_with_no_platform_is_refused_rather_than_reported_as_universal(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            DeclaredArtifactSetup(COORDINATE, DIGEST, "setup/installer.json", ())

    def test_a_declaration_that_names_no_version_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            DeclaredArtifactSetup(
                ArtifactCoordinate(SourceAlias("company"), ArtifactIdentity("skill", "x")),
                DIGEST,
                "setup/installer.json",
                ("darwin",),
            )

    def test_the_payload_shape_names_the_coordinate_the_way_everything_else_does(self) -> None:
        data = declared_setup_to_data(
            DeclaredArtifactSetup(
                COORDINATE, DIGEST, "setup/installer.json", ("darwin",), "SETUP.md"
            )
        )

        self.assertEqual(
            data,
            {
                "coordinate": "company/skill/code-review@1.2.0",
                "object_digest": f"sha256:{'a' * 64}",
                "recipe": "setup/installer.json",
                "platforms": ["darwin"],
                "manual": "SETUP.md",
            },
        )


_ROOT = "/var/lib/aart/runtimes/company/skill/code-review"


def _receipt(**overrides) -> PlacedArtifactReceipt:
    fields: dict = {
        "artifact": "skill/code-review",
        "root": _ROOT,
        "payload_digest": ObjectDigest("sha256", "b" * 64),
        "deliveries": (
            ArtifactDelivery(
                "claude",
                f"{_ROOT}/payload/skill",
                "/work/project/.claude/skills/code-review",
                DeliveryKind.TREE,
                ObjectDigest("sha256", "c" * 64),
            ),
        ),
    }
    fields.update(overrides)
    return PlacedArtifactReceipt(**fields)


class InstalledSetupReadTest(unittest.TestCase):
    """Reading the declaration off the durable record, and the two ways that can come up empty."""

    def test_a_receipt_that_cannot_say_which_object_it_came_from_declares_nothing(self) -> None:
        """Silence, not a guess.

        A receipt written before installations recorded their object (D-122) does not know which
        package it came from. Reporting "no setup declared" for it would be an answer this reader
        did not obtain, and looking for a package on this machine that resembles the coordinate
        would be worse -- an artifact's setup would then be read off bytes nobody installed.
        """

        with tempfile.TemporaryDirectory() as root:
            state = str(pathlib.Path(root) / "state")
            written = LocalReceiptStore(state).record_installation(COORDINATE, _receipt())
            self.assertIsInstance(written, Ok, getattr(written, "diagnostics", ()))

            declared = read_declared_setup((COORDINATE,), state_root=state, data_root=root)

            self.assertEqual(declared, Ok(()))

    def test_an_object_the_receipt_names_and_the_store_lacks_is_refused(self) -> None:
        """The dangling identity the optional field was shaped to avoid, if it ever happened.

        Reporting "nothing to configure" here would turn a broken object store into a clean bill of
        health for every artifact in it.
        """

        with tempfile.TemporaryDirectory() as root:
            state = str(pathlib.Path(root) / "state")
            written = LocalReceiptStore(state).record_installation(
                COORDINATE, _receipt(object_digest=DIGEST)
            )
            self.assertIsInstance(written, Ok, getattr(written, "diagnostics", ()))

            declared = read_declared_setup((COORDINATE,), state_root=state, data_root=root)

            self.assertIsInstance(declared, Err)
            self.assertIn("is not in the store", declared.diagnostics[0].message)

    def test_an_artifact_with_no_record_at_all_is_reported_rather_than_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            declared = read_declared_setup(
                (COORDINATE,), state_root=str(pathlib.Path(root) / "state"), data_root=root
            )

            self.assertIsInstance(declared, Err)


if __name__ == "__main__":
    unittest.main()
