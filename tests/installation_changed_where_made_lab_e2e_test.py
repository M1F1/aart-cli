"""CP-42, end to end: a change reaches the installation it was asked for, and only that one.

Found by walking the manual lab. One Skill was installed in Claude for this project, for the user,
and in a second project, and then a newer version was published. On Updates, the row for this
project's installation was updated into Claude, OpenCode and Tabnine: the update offered every
harness the machine has rather than the one the installation is. The user's row answered "nothing
canonical is installed here" with a raw key, because a lifecycle action read only the installations
of the scope Settings prefer. The second project's row answered the same, rather than saying where
to open aart-cli to change it. And once a user installation could be reached from a project, its
removal was planned at the project's scope, so the user's OpenCode entry would have been left
behind (§169.3, D-479).

This drives the application `aart-cli` launches, in its text terminal, over the lab's real Git
remotes, and reads what the machine holds afterwards.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

#: Composes the consumer application as `tui.run` does and walks it through `steps`: a string is a
#: key, and `{"row": pattern}` moves down until the cursor line matches. It prints everything drawn
#: and, from a fresh composition, every installation the machine holds.
_PROBE = textwrap.dedent(
    """
    import json, os, re, sys
    from datetime import date
    from aart_cli.tui import _canonical_consumer_actions, run_consumer_text

    def compose():
        return _canonical_consumer_actions(
            project=os.getcwd(), user_home=os.environ["HOME"], today=date.today(),
            observe=lambda line: None,
        ).value

    steps = json.loads(sys.argv[1])
    drawn = []

    def read(prompt=""):
        while steps and isinstance(steps[0], dict):
            cursor = [line for line in drawn if line.startswith("> ") and "AART" not in line][-1]
            if not re.search(steps[0]["row"], cursor):
                if len(drawn) > 4000:
                    raise EOFError
                return "down"
            steps.pop(0)
        if steps:
            return steps.pop(0)
        raise EOFError

    run_consumer_text(compose(), read=read, write=drawn.append)
    installed = compose().source().screens.installed
    print(json.dumps({
        "drawn": "\\n".join(drawn),
        "installed": sorted([item.coordinate, item.harness, item.scope, item.root]
                            for item in installed),
    }))
    """
)

UPDATES = ("down", "down", "enter")
INSTALLED = ("down", "enter")


class _Lab(unittest.TestCase):
    """One manual lab with `INSTALLS` made from its consumer project, each a `consume` argv."""

    INSTALLS: tuple[tuple[str, ...], ...] = ()

    @classmethod
    def setUpClass(cls) -> None:
        from scripts.manual_test import setup_lab, shell_environment

        temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        cls.root = pathlib.Path(temporary.name).resolve() / "manual-lab"
        lab = setup_lab(cls.root)
        env, project = shell_environment(cls.root, "consumer")
        cls.project = project
        cls.home = pathlib.Path(env["HOME"])
        cls.second = cls.root / "second-project"
        cls.second.mkdir()
        cls._consume(
            "registry", "add", "--alias", "lab", "--kind", "git",
            "--location", "https://manual.aart.test/registry.git", "--ref", lab.branch,
        )  # fmt: skip
        for argv in cls.INSTALLS:
            cls._consume(*(item.format(second=cls.second) for item in argv))

    @classmethod
    def _consume(cls, *argv: str) -> None:
        from scripts.manual_test import shell_environment

        env, project = shell_environment(cls.root, "consumer")
        subprocess.run(
            (sys.executable, "-m", "aart_cli.cli", "consume", *argv),
            cwd=project,
            env=env,
            check=True,
            capture_output=True,
        )

    def _walk(self, *steps: str | dict[str, str]) -> dict:
        """Open aart-cli in this lab's project and take `steps` (see `_PROBE`)."""

        from scripts.manual_test import CHECKOUT, shell_environment

        env, project = shell_environment(self.root, "consumer")
        env["PYTHONPATH"] = str(CHECKOUT)
        ran = subprocess.run(
            (
                sys.executable,
                "-c",
                _PROBE,
                json.dumps(steps),
            ),
            cwd=project,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(ran.stdout)


_SKILL = ("install", "lab/skill/manual-check@1.0.0", "--profile", "claude", "--yes")


class AnUpdateChangesTheInstallationItWasAskedFor(_Lab):
    INSTALLS = (_SKILL, (*_SKILL, "--scope", "user"), (*_SKILL, "--project", "{second}"))

    @classmethod
    def setUpClass(cls) -> None:
        from scripts.manual_test import publish_version

        super().setUpClass()
        publish_version(cls.root)

    def _update(self, row: str) -> dict:
        return self._walk(*UPDATES, {"row": row}, "space", "i", "enter")

    def _skills(self, root: pathlib.Path) -> list[str]:
        return sorted(
            str(path.relative_to(root))
            for path in root.rglob("SKILL.md")
            if ".aart-cli" not in path.parts
        )

    def test_this_projects_row_is_updated_in_its_own_harness_alone(self) -> None:
        before = self._skills(self.project)

        seen = self._update(r"project\s+consumer-proj")

        self.assertIn(
            ["lab/skill/manual-check@1.0.1", "claude", "project", str(self.project)],
            seen["installed"],
            seen["drawn"][-3000:],
        )
        self.assertEqual(
            [item for item in seen["installed"] if item[1] != "claude"], [], seen["installed"]
        )
        self.assertEqual(self._skills(self.project), before)

    def test_the_users_row_is_updated_from_a_project(self) -> None:
        before = self._skills(self.home)

        seen = self._update(r"\buser\s")

        self.assertNotIn("nothing canonical is installed here", seen["drawn"])
        self.assertIn(
            ["lab/skill/manual-check@1.0.1", "claude", "user", str(self.home)],
            seen["installed"],
            seen["drawn"][-3000:],
        )
        self.assertEqual(
            [item for item in seen["installed"] if item[1] != "claude"], [], seen["installed"]
        )
        self.assertEqual(self._skills(self.home), before)

    def test_another_projects_row_says_where_to_change_it_and_changes_nothing(self) -> None:
        files = sorted(str(path) for path in self.second.rglob("*"))

        seen = self._update(r"second-project")

        self.assertIn(
            "installed in another project: lab/skill/manual-check@1.0.0 · claude · project "
            "second-project",
            seen["drawn"],
        )
        self.assertIn(f"open aart-cli in {self.second}", seen["drawn"])
        self.assertNotIn("nothing canonical is installed here", seen["drawn"])
        self.assertIn(
            ["lab/skill/manual-check@1.0.0", "claude", "project", str(self.second)],
            seen["installed"],
        )
        self.assertEqual(sorted(str(path) for path in self.second.rglob("*")), files)


_MCP = ("install", "lab/mcp/dummy-mcp@1.0.0", "--profile", "opencode", "--set-later", "--yes")


def _entries(path: pathlib.Path) -> list[str]:
    """The MCP servers one OpenCode configuration file registers."""

    if not path.exists():
        return []
    return sorted(json.loads(path.read_text(encoding="utf-8")).get("mcp", {}))


@unittest.skipUnless(sys.platform == "darwin", "the MCP's credential needs the Keychain")
class AUsersInstallationIsRemovedFromAProjectWhereItLives(_Lab):
    INSTALLS = ((*_MCP, "--scope", "user"),)

    def test_its_harness_entry_goes_with_it(self) -> None:
        user_config = self.home / ".config/opencode/opencode.json"
        self.assertEqual(len(_entries(user_config)), 1, user_config)

        seen = self._walk(*INSTALLED, {"row": r"dummy-mcp.*\buser\b"}, "u", "enter")

        self.assertIn("harness:opencode", seen["drawn"])
        self.assertEqual(seen["installed"], [], seen["drawn"][-3000:])
        self.assertEqual(_entries(user_config), [])
        self.assertEqual(_entries(self.project / "opencode.json"), [])


@unittest.skipUnless(sys.platform == "darwin", "the MCP's credential needs the Keychain")
class UserAndProjectRowsAreChangedOneScopeAtATime(_Lab):
    INSTALLS = (_MCP, (*_MCP, "--scope", "user"))

    def test_ticking_both_is_refused_and_removes_nothing(self) -> None:
        seen = self._walk(
            *INSTALLED,
            {"row": r"dummy-mcp.*\bproject\b"},
            "space",
            {"row": r"dummy-mcp.*\buser\b"},
            "space",
            "u",
        )

        self.assertIn(
            "user and project installations are changed one scope at a time", seen["drawn"]
        )
        self.assertEqual(len(seen["installed"]), 2, seen["drawn"][-3000:])
        self.assertEqual(len(_entries(self.home / ".config/opencode/opencode.json")), 1)
        self.assertEqual(len(_entries(self.project / "opencode.json")), 1)


if __name__ == "__main__":
    unittest.main()
