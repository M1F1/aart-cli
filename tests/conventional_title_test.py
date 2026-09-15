"""INV-090, INV-092, INV-093: the squash commit is the release engine's input, so it is checked.

Under a squash-merge workflow the pull request's title becomes the one commit on `main`, and that
commit is what decides whether the next release is a patch, a minor or a major.  A title the
engine cannot classify is not a style problem: it is a change that silently classifies as nothing
and is left out of the release it belongs in.

The types it accepts are read out of `release-please-config.json` rather than listed here.  One
file says what a type means and which types exist; a gate with its own list would be a second
policy, and the two would drift.
"""

from __future__ import annotations

import json
import pathlib
import unittest

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from scripts import conventional_title

ROOT = pathlib.Path(__file__).resolve().parents[1]
MUTATION_SETTINGS = settings(suppress_health_check=(HealthCheck.differing_executors,))


class AcceptedTitleTest(unittest.TestCase):
    def test_the_three_shapes_the_specification_names(self) -> None:
        for title, kind, breaking in (
            ("fix(tui): preserve selected artifact after refresh", "fix", False),
            ("feat(mcp): add isolated Python runtime", "feat", False),
            ("feat(registry)!: replace legacy source schema", "feat", True),
        ):
            with self.subTest(title=title):
                parsed = conventional_title.parse(title)
                self.assertIsNotNone(parsed)
                assert parsed is not None
                self.assertEqual(parsed.type, kind)
                self.assertIs(parsed.breaking, breaking)

    def test_a_scope_is_optional(self) -> None:
        parsed = conventional_title.parse("docs: reconcile the release model")
        assert parsed is not None
        self.assertEqual(parsed.type, "docs")
        self.assertIsNone(parsed.scope)

    def test_the_semver_step_is_the_committed_mapping(self) -> None:
        """INV-082: `fix -> PATCH`, `feat -> MINOR`, a break -> `MAJOR`."""

        self.assertEqual(conventional_title.semver_step("fix: a"), "patch")
        self.assertEqual(conventional_title.semver_step("feat: a"), "minor")
        self.assertEqual(conventional_title.semver_step("feat!: a"), "major")
        self.assertEqual(conventional_title.semver_step("fix(x)!: a"), "major")
        self.assertEqual(conventional_title.semver_step("chore: a"), "none")


class RefusedTitleTest(unittest.TestCase):
    def test_a_title_the_engine_cannot_classify_is_refused(self) -> None:
        for title in (
            "preserve selected artifact after refresh",
            "Fix(tui): capitalised type",
            "fix (tui): space before the scope",
            "fix(tui) : space before the colon",
            "fix:",
            "fix: ",
            "fix(): an empty scope",
            "wibble: a type nothing declares",
            "",
        ):
            with self.subTest(title=title):
                self.assertIsNone(conventional_title.parse(title))

    def test_the_accepted_types_are_the_ones_the_release_config_declares(self) -> None:
        config = json.loads((ROOT / "release-please-config.json").read_text(encoding="utf-8"))
        declared = {str(section["type"]) for section in config["changelog-sections"]}
        self.assertEqual(set(conventional_title.ACCEPTED_TYPES), declared)
        self.assertGreater(len(declared), 3, "a policy this small is not a policy")

    @MUTATION_SETTINGS
    @given(st.text(max_size=40))
    def test_nothing_is_ever_classified_by_a_type_it_does_not_carry(self, raw: str) -> None:
        parsed = conventional_title.parse(raw)
        if parsed is None:
            return
        self.assertTrue(raw.startswith(parsed.type))
        self.assertIn(parsed.type, conventional_title.ACCEPTED_TYPES)

    @MUTATION_SETTINGS
    @given(
        st.sampled_from(sorted(conventional_title.ACCEPTED_TYPES)),
        st.sampled_from(("", "(tui)", "(registry)", "(a-b)")),
        st.booleans(),
        st.text(
            alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=1, max_size=20
        ),
    )
    def test_every_title_the_grammar_can_build_is_a_title_it_accepts(
        self, kind: str, scope: str, breaking: bool, description: str
    ) -> None:
        title = f"{kind}{scope}{'!' if breaking else ''}: {description}"
        parsed = conventional_title.parse(title)
        self.assertIsNotNone(parsed, title)
        assert parsed is not None
        self.assertEqual(parsed.type, kind)
        self.assertIs(parsed.breaking, breaking)
        self.assertEqual(parsed.scope, scope[1:-1] if scope else None)


class TheGateTest(unittest.TestCase):
    def test_a_good_title_exits_zero_and_says_what_it_will_do(self) -> None:
        self.assertEqual(conventional_title.main(("feat(tui): add a screen",)), 0)

    def test_a_bad_title_exits_nonzero(self) -> None:
        self.assertEqual(conventional_title.main(("add a screen",)), 1)


if __name__ == "__main__":
    unittest.main()
