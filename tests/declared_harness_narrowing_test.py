"""`QA-078`: what a Skill declares it supports and what it is installed into are one answer.

The operator read `profile 'codex' is not supported; supported profiles: claude` on Artifact
Details and then `✓ delivery:codex` on Success, for the same Skill in the same install. Both
screens were internally consistent and consistent with different sources: `evaluate_compatibility`
reads the manifest, and the placement read the request alone (`D-231`).

The rule this file holds is the one `D-231` settled. An empty or absent `compatibility.harnesses`
means *unconstrained* -- the schema parses both as `()`, so they cannot mean different things, and
an author who wrote nothing did not say "nowhere". A non-empty declaration narrows, and it narrows
through the existing asymmetry rather than a second one: a harness the machine merely measured is
left out, a harness somebody typed is still refused by name.
"""

from __future__ import annotations

import dataclasses
import unittest

from agent_artifacts.domain.harness import Scope
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.artifact_placement import PLACEMENT_UNAVAILABLE, placement_for
from tests.measured_host_profiles_test import _PlacementFixture


def _renamed(artifact, name: str):
    """The same stored package, resolved under somebody else's name."""

    coordinate = artifact.version.coordinate
    identity = dataclasses.replace(coordinate.artifact, name=name)
    return dataclasses.replace(
        artifact,
        version=dataclasses.replace(
            artifact.version, coordinate=dataclasses.replace(coordinate, artifact=identity)
        ),
    )


#: Declares one harness. Three of the machine's four are outside it.
DECLARED_SKILL = {
    "schema": "aart.dev/skill/v1",
    "artifact": {"name": "manual-check", "kind": "skill", "version": "1.0.0"},
    "payload": {"include": ["SKILL.md"]},
    "compatibility": {"harnesses": ["claude"]},
}

#: Declares nothing at all, like `company/mcp/notes@1.0.0` in the fixture registry.
UNDECLARED_SKILL = {
    "schema": "aart.dev/skill/v1",
    "artifact": {"name": "open-check", "kind": "skill", "version": "1.0.0"},
    "payload": {"include": ["SKILL.md"]},
}

#: Declares the empty list, which the schema cannot tell apart from the one above.
EMPTY_SKILL = {
    "schema": "aart.dev/skill/v1",
    "artifact": {"name": "empty-check", "kind": "skill", "version": "1.0.0"},
    "payload": {"include": ["SKILL.md"]},
    "compatibility": {"harnesses": []},
}

_FILES = (("SKILL.md", "# review\n"),)


class DeclaredHarnessesNarrowTheMachineSetTest(_PlacementFixture):
    """The machine has four harnesses; the Skill says one."""

    manifest = DECLARED_SKILL
    files = _FILES

    def _harnesses(self, placed) -> list[str]:
        return sorted(item.harness for item in placed.value.deliveries)

    def test_a_declared_harness_set_narrows_what_the_machine_offers(self) -> None:
        placed = self._place(scope=Scope.USER, harness_root=self.home, profiles_requested=False)

        self.assertIsInstance(placed, Ok, getattr(placed, "diagnostics", ()))
        self.assertEqual(["claude"], self._harnesses(placed))

    def test_the_install_agrees_with_what_artifact_details_said(self) -> None:
        """The whole finding in one assertion: no harness is delivered that the screen refused."""

        placed = self._place(scope=Scope.USER, harness_root=self.home, profiles_requested=False)

        assert isinstance(placed, Ok)
        declared = set(DECLARED_SKILL["compatibility"]["harnesses"])  # type: ignore[index]
        self.assertTrue(
            set(self._harnesses(placed)) <= declared,
            f"delivered to {self._harnesses(placed)}, declared {sorted(declared)}",
        )

    def test_a_harness_the_operator_typed_is_still_refused_by_name(self) -> None:
        """Narrowing is for the capability set. A request is a request, and gets an answer."""

        placed = self._place(scope=Scope.USER, harness_root=self.home, profiles=("claude", "codex"))

        self.assertIsInstance(placed, Err)
        assert isinstance(placed, Err)
        self.assertIs(placed.diagnostics[0].code, PLACEMENT_UNAVAILABLE)
        self.assertIn("codex", placed.diagnostics[0].message)
        # Naming the refused harness is half the answer; the other half is the set they can pick
        # instead, which is what Artifact Details already showed them. A refusal that says only
        # "no" sends the reader back to the manifest to find out what "yes" would have been.
        self.assertIn("claude", placed.diagnostics[0].message)
        self.assertIn(
            "install it for a harness this artifact declares support for",
            placed.diagnostics[0].remediation,
        )

    def test_a_declaration_that_leaves_nothing_is_refused_rather_than_silently_empty(self) -> None:
        """The other branch: nobody typed anything, and the machine measured nothing declared.

        The capability set is narrowed rather than refused harness by harness, so narrowing it to
        empty is the one place the shell has to speak. Installing into no harness at all and
        reporting success is the `QA-078` lie again, one level down.
        """

        placed = self._place(
            scope=Scope.USER,
            harness_root=self.home,
            profiles=("codex",),
            profiles_requested=False,
        )

        self.assertIsInstance(placed, Err)
        assert isinstance(placed, Err)
        self.assertIs(placed.diagnostics[0].code, PLACEMENT_UNAVAILABLE)
        message = placed.diagnostics[0].message
        self.assertIn("claude", message)
        self.assertIn("this machine measured none of them", message)
        self.assertIn(
            "install it on a machine with one of those harnesses",
            placed.diagnostics[0].remediation,
        )

    def test_the_declaration_read_is_the_one_belonging_to_this_coordinate(self) -> None:
        """Narrowing reads a package out of the store, so it has to check whose package it is.

        Every assertion above would still pass if the stored object held a different artifact's
        manifest: the harness set would simply be somebody else's. The identity check is what
        makes "what the artifact declares" mean this artifact.
        """

        artifact = _renamed(self.artifact, "borrowed-check")

        placed = placement_for(
            artifact,
            scope=Scope.USER,
            profiles=("claude",),
            project_root=self.project,
            data_root=self.data,
            harness_root=self.home,
            store=self.store,
        )

        self.assertIsInstance(placed, Err)
        assert isinstance(placed, Err)
        self.assertIn("does not match", placed.diagnostics[0].message)


class AnAbsentDeclarationIsUnconstrainedTest(_PlacementFixture):
    """An author who wrote nothing did not say "nowhere"."""

    manifest = UNDECLARED_SKILL
    files = _FILES

    def test_every_measured_harness_that_can_read_it_still_gets_it(self) -> None:
        placed = self._place(scope=Scope.USER, harness_root=self.home, profiles_requested=False)

        self.assertIsInstance(placed, Ok, getattr(placed, "diagnostics", ()))
        self.assertEqual(
            ["claude", "codex", "opencode"],
            sorted(item.harness for item in placed.value.deliveries),
        )


class AnEmptyDeclarationMeansTheSameAsAnAbsentOneTest(_PlacementFixture):
    """`allow_empty=True` parses both as `()`, so they cannot be given different meanings."""

    manifest = EMPTY_SKILL
    files = _FILES

    def test_it_is_unconstrained_exactly_like_an_absent_block(self) -> None:
        placed = self._place(scope=Scope.USER, harness_root=self.home, profiles_requested=False)

        self.assertIsInstance(placed, Ok, getattr(placed, "diagnostics", ()))
        self.assertEqual(
            ["claude", "codex", "opencode"],
            sorted(item.harness for item in placed.value.deliveries),
        )


if __name__ == "__main__":
    unittest.main()
