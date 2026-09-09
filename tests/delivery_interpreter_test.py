"""Carrying out a delivery: putting an artifact where a harness reads it, and taking it back.

This is the one interpreter that writes outside AART's own tree, so it is the one that cannot
prove ownership structurally the way `FileEffectInterpreter` does. It proves it the way
`HarnessEffectInterpreter` does instead: it is given the deliveries it may make, and an effect it
was not given is refused rather than carried out. D-072 -- supporting an effect means being allowed
to carry it out, not recognizing its type -- is what keeps two artifacts delivering to the same
harness from being carried out by each other's interpreter.
"""

from __future__ import annotations

import os
import pathlib
import tempfile
import unittest

from agent_artifacts.domain.effects import DeliverArtifact, DeliveryKind, WithdrawArtifact
from agent_artifacts.domain.identifiers import ObjectDigest
from agent_artifacts.domain.receipts import ArtifactDelivery
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.execution import DeliveryEffectInterpreter


def _digest(character: str = "b") -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


class _Delivers:
    """One artifact's payload, and the harness directory it is delivered into."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = pathlib.Path(self.temporary.name)
        self.root = self.base / "runtimes" / "skill" / "code-review"
        self.source = self.root / "payload" / "skill"
        self.source.mkdir(parents=True)
        (self.source / "SKILL.md").write_text("# review\n", encoding="utf-8")
        (self.source / "reference.md").write_text("detail\n", encoding="utf-8")
        self.destination = self.base / "project" / ".claude" / "skills" / "code-review"

    def _interpreter(
        self, *, artifact: str = "skill/code-review", harness: str = "claude"
    ) -> DeliveryEffectInterpreter:
        return DeliveryEffectInterpreter(
            artifact,
            (
                ArtifactDelivery(
                    harness,
                    str(self.source),
                    str(self.destination),
                    DeliveryKind.TREE,
                    _digest(),
                ),
            ),
        )

    def _deliver(
        self, *, artifact: str = "skill/code-review", harness: str = "claude"
    ) -> DeliverArtifact:
        return DeliverArtifact(
            harness, artifact, str(self.source), str(self.destination), DeliveryKind.TREE
        )


class DeliveryInterpreterTest(_Delivers, unittest.TestCase):
    def test_a_tree_delivery_puts_the_payload_where_the_harness_reads(self) -> None:
        result = self._interpreter().apply(self._deliver())
        self.assertIsInstance(result, Ok)
        self.assertEqual("# review\n", (self.destination / "SKILL.md").read_text(encoding="utf-8"))

    def test_a_file_delivery_writes_one_file_and_makes_the_directory_it_needs(self) -> None:
        source = self.root / "payload" / "guideline.md"
        source.write_text("guide\n", encoding="utf-8")
        destination = self.base / "project" / ".claude" / "guidelines" / "review.md"
        delivery = ArtifactDelivery(
            "claude", str(source), str(destination), DeliveryKind.FILE, _digest()
        )
        interpreter = DeliveryEffectInterpreter("guideline/review", (delivery,))
        result = interpreter.apply(
            DeliverArtifact(
                "claude", "guideline/review", str(source), str(destination), DeliveryKind.FILE
            )
        )
        self.assertIsInstance(result, Ok)
        self.assertEqual("guide\n", destination.read_text(encoding="utf-8"))

    def test_delivering_again_leaves_no_file_the_new_payload_dropped(self) -> None:
        interpreter = self._interpreter()
        self.assertIsInstance(interpreter.apply(self._deliver()), Ok)
        (self.source / "reference.md").unlink()
        self.assertIsInstance(interpreter.apply(self._deliver()), Ok)
        self.assertFalse((self.destination / "reference.md").exists())
        self.assertTrue((self.destination / "SKILL.md").exists())

    def test_a_delivery_from_a_source_that_is_not_there_fails_and_places_nothing(self) -> None:
        import shutil

        shutil.rmtree(self.source)
        result = self._interpreter().apply(self._deliver())
        self.assertIsInstance(result, Err)
        self.assertFalse(self.destination.exists())

    def test_withdrawing_takes_back_what_was_delivered(self) -> None:
        interpreter = self._interpreter()
        self.assertIsInstance(interpreter.apply(self._deliver()), Ok)
        self.destination.chmod(0o500)
        self.assertEqual(0, os.stat(self.destination).st_mode & 0o200)
        withdraw = WithdrawArtifact(
            "claude", "skill/code-review", str(self.destination), DeliveryKind.TREE
        )
        self.assertIsInstance(interpreter.apply(withdraw), Ok)
        self.assertFalse(self.destination.exists())

    def test_withdrawing_something_already_gone_is_not_a_failure(self) -> None:
        withdraw = WithdrawArtifact(
            "claude", "skill/code-review", str(self.destination), DeliveryKind.TREE
        )
        self.assertIsInstance(self._interpreter().apply(withdraw), Ok)

    def test_withdrawing_leaves_the_directory_the_harness_owns_standing(self) -> None:
        interpreter = self._interpreter()
        self.assertIsInstance(interpreter.apply(self._deliver()), Ok)
        neighbour = self.destination.parent / "someone-elses-skill"
        neighbour.mkdir()
        withdraw = WithdrawArtifact(
            "claude", "skill/code-review", str(self.destination), DeliveryKind.TREE
        )
        self.assertIsInstance(interpreter.apply(withdraw), Ok)
        self.assertTrue(neighbour.is_dir())

    def test_withdrawing_a_symlink_removes_only_the_link(self) -> None:
        target = self.base / "somebody-elses-skill"
        target.mkdir()
        (target / "SKILL.md").write_text("still theirs\n", encoding="utf-8")
        self.destination.parent.mkdir(parents=True)
        self.destination.symlink_to(target, target_is_directory=True)
        withdraw = WithdrawArtifact(
            "claude", "skill/code-review", str(self.destination), DeliveryKind.TREE
        )

        self.assertIsInstance(self._interpreter().apply(withdraw), Ok)

        self.assertFalse(self.destination.exists())
        self.assertEqual("still theirs\n", (target / "SKILL.md").read_text(encoding="utf-8"))


class DeliveryDispatchTest(_Delivers, unittest.TestCase):
    def test_another_artifacts_delivery_is_not_this_interpreters_to_make(self) -> None:
        interpreter = self._interpreter(artifact="skill/code-review")
        self.assertFalse(interpreter.supports(self._deliver(artifact="skill/other")))

    def test_another_harnesss_delivery_is_not_this_interpreters_to_make(self) -> None:
        self.assertFalse(self._interpreter().supports(self._deliver(harness="codex")))

    def test_a_delivery_it_holds_is_supported(self) -> None:
        self.assertTrue(self._interpreter().supports(self._deliver()))

    def test_a_delivery_to_a_destination_it_was_not_given_is_not_supported(self) -> None:
        elsewhere = DeliverArtifact(
            "claude",
            "skill/code-review",
            str(self.source),
            str(self.base / "project" / ".claude" / "skills" / "elsewhere"),
            DeliveryKind.TREE,
        )
        self.assertFalse(self._interpreter().supports(elsewhere))

    def test_applying_a_delivery_it_was_not_given_is_refused_rather_than_carried_out(self) -> None:
        interpreter = self._interpreter(artifact="skill/code-review")
        result = interpreter.apply(self._deliver(artifact="skill/other"))
        self.assertIsInstance(result, Err)
        self.assertFalse(self.destination.exists())

    def test_a_harness_effect_is_not_a_delivery(self) -> None:
        from agent_artifacts.domain.effects import ConfigureHarness

        effect = ConfigureHarness("claude", "skill/code-review", str(self.base / "settings.json"))
        self.assertFalse(self._interpreter().supports(effect))
        self.assertIsInstance(self._interpreter().apply(effect), Err)

    def test_an_interpreter_needs_at_least_one_delivery_to_be_for(self) -> None:
        with self.assertRaises(ValueError):
            DeliveryEffectInterpreter("skill/code-review", ())

    def test_an_interpreter_needs_a_named_artifact(self) -> None:
        with self.assertRaises(ValueError):
            DeliveryEffectInterpreter(
                " ",
                (
                    ArtifactDelivery(
                        "claude",
                        str(self.source),
                        str(self.destination),
                        DeliveryKind.TREE,
                        _digest(),
                    ),
                ),
            )


class DeliveryPermissionTest(_Delivers, unittest.TestCase):
    def test_a_delivered_tree_is_readable_by_the_harness_and_not_by_anyone_else(self) -> None:
        self.assertIsInstance(self._interpreter().apply(self._deliver()), Ok)
        mode = os.stat(self.destination / "SKILL.md").st_mode & 0o077
        self.assertEqual(0, mode)


if __name__ == "__main__":
    unittest.main()
