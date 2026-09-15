from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"

# INV-114 says acceptance must *primarily* depend on public contracts, so the answer is not zero --
# it is a list short enough to read, with a reason beside each entry.
#
# * `tui_consumer._reload` -- the persistent TUI has one reducer and no public re-entry point; a
#   session test that cannot re-enter the loop cannot assert what the second screen shows.
# * `commands.doctor._configuration_*` / `._credential_*` -- these project the configuration and
#   credential halves of one report. The command prints them together, so a test going through the
#   command can only assert on merged output; these two claims are about each half separately.
KNOWN_PRIVATE_REACH = {
    "artifact_installation_e2e_test.py": ("agent_artifacts.tui_consumer._reload",),
    "consumer_session_e2e_test.py": ("agent_artifacts.tui_consumer._reload",),
    "doctor_configuration_credentials_e2e_test.py": (
        "agent_artifacts.commands.doctor._configuration_data",
        "agent_artifacts.commands.doctor._configuration_lines",
        "agent_artifacts.commands.doctor._credential_data",
        "agent_artifacts.commands.doctor._credential_lines",
    ),
}


def _private_reach(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("agent_artifacts")
        ):
            found.update(
                f"{node.module}.{alias.name}" for alias in node.names if alias.name.startswith("_")
            )
        elif isinstance(node, ast.Import):
            found.update(
                alias.name
                for alias in node.names
                if alias.name.startswith("agent_artifacts") and "._" in alias.name
            )
    return tuple(sorted(found))


class AcceptanceDependsOnPublicContractsTest(unittest.TestCase):
    """INV-114. An acceptance test that imports a private name is pinned to implementation
    structure: it keeps passing through a refactor that breaks every user, and it fails on a
    rename that breaks nobody. Neither is what acceptance is for.

    Stated as an exact map rather than a count, so both directions are drift -- a new test reaching
    inside, and an entry that stopped being needed and should have been deleted.
    """

    def test_only_the_listed_acceptance_tests_reach_into_private_structure(self) -> None:
        actual = {
            path.name: reach
            for path in sorted(TESTS.glob("*e2e_test.py"))
            if (reach := _private_reach(path))
        }

        self.assertEqual(actual, KNOWN_PRIVATE_REACH)

    def test_the_public_majority_is_real(self) -> None:
        acceptance = list(TESTS.glob("*e2e_test.py"))

        self.assertGreater(len(acceptance), 40)
        # "Primarily public" is the invariant's own word; hold it as a ratio, not a vibe.
        self.assertLess(len(KNOWN_PRIVATE_REACH) * 10, len(acceptance))

    def test_this_guard_is_not_vacuous(self) -> None:
        self.assertTrue(KNOWN_PRIVATE_REACH)
        self.assertEqual(
            _private_reach(TESTS / "consumer_session_e2e_test.py"),
            ("agent_artifacts.tui_consumer._reload",),
        )


if __name__ == "__main__":
    unittest.main()
