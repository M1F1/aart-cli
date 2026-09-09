from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

from agent_artifacts.application.consumer_views import project_install_plan
from agent_artifacts.tui_consumer import render_install_plan, render_ready

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "agent_artifacts"

# Where a plan is decided.  Presentation must be unknown here, because a layer that can read the
# preference is a layer that can act on it, and INV-158 is about exactly that reachability.
DECIDING_LAYERS = ("domain", "security", "configuration", "installation", "application")

# The one module in those layers that may name the profile: it declares the type.  Declaring the
# vocabulary of a presentation choice is not the same as consulting one.
DECLARES_THE_TYPE = "application/consumer_views.py"

PRESENTATION_WORDS = ("PresentationProfile", "fast", "verbose", "FAST", "VERBOSE")


def _deciding_modules() -> list[Path]:
    modules: list[Path] = []
    for layer in DECIDING_LAYERS:
        modules.extend(sorted((PACKAGE / layer).rglob("*.py")))
    return [p for p in modules if p.relative_to(PACKAGE).as_posix() != DECLARES_THE_TYPE]


def _presentation_mentions(path: Path) -> list[str]:
    """Identifiers and string literals, so neither an import nor a bare `"verbose"` slips past."""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in PRESENTATION_WORDS:
            found.add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in PRESENTATION_WORDS:
            found.add(node.attr)
        elif isinstance(node, ast.alias) and node.name in PRESENTATION_WORDS:
            found.add(node.name)
        elif isinstance(node, ast.Constant) and node.value in PRESENTATION_WORDS:
            found.add(str(node.value))
    return sorted(found)


class PresentationCannotReachTheDecisionTest(unittest.TestCase):
    """INV-149, INV-152 and INV-158, stated as reachability rather than as behaviour.

    The behavioural half is already held: `consumer_properties_test.py` proves over generated
    plans that switching the profile changes neither the selection, the review digest nor the
    machine payload.  What nothing held is the structural half -- that the preference is not *there*
    to be consulted.  A policy path that started branching on Fast would satisfy every existing
    property test for as long as the two branches happened to agree.
    """

    def test_no_deciding_module_knows_what_a_presentation_profile_is(self) -> None:
        offenders = {
            path.relative_to(PACKAGE).as_posix(): found
            for path in _deciding_modules()
            if (found := _presentation_mentions(path))
        }

        self.assertEqual(
            offenders,
            {},
            "planning, policy and security decide the same way for both profiles because they "
            "cannot tell which one is running.",
        )

    def test_the_plan_is_built_before_the_profile_is_known(self) -> None:
        """The signatures say it: projection takes a plan, rendering takes a plan and a profile."""

        projection = inspect.signature(project_install_plan).parameters
        self.assertNotIn("profile", projection)
        self.assertNotIn("presentation", projection)

        for renderer in (render_install_plan, render_ready):
            with self.subTest(renderer=renderer.__name__):
                self.assertIn("profile", inspect.signature(renderer).parameters)


class TheseGuardsAreNotVacuousTest(unittest.TestCase):
    def test_the_layers_being_swept_are_the_layers_that_decide(self) -> None:
        swept = {path.relative_to(PACKAGE).as_posix() for path in _deciding_modules()}

        self.assertGreater(len(swept), 40)
        for planner in (
            "application/installation_planning.py",
            "application/reconciliation.py",
            "domain/policies.py",
        ):
            with self.subTest(module=planner):
                self.assertIn(planner, swept)
        self.assertNotIn(DECLARES_THE_TYPE, swept)

    def test_the_detector_detects(self) -> None:
        """The word really is findable where it legitimately appears."""

        self.assertTrue(_presentation_mentions(PACKAGE / "tui_consumer.py"))
        self.assertTrue(_presentation_mentions(PACKAGE / DECLARES_THE_TYPE))


if __name__ == "__main__":
    unittest.main()
