"""The ignore file `registry init` writes leaves every vendored payload whole.

The entries are the root's own clutter: harness directories somebody ran in the checkout, caches,
build output. A payload is vendored as reviewed, and a plugin or a Skill can carry exactly those
names inside it -- an OpenCode plugin ships `.opencode/plugins/<name>.js`. Measured on 2026-10-15:
an unanchored `.opencode/` made git drop the plugin module from `artifacts/`, and the published
Registry then failed its own content digest at `source add`. Asked of git itself, because what
matters is what `git add -A` keeps, not what the patterns look like.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

# B-186: `registry_commands` imported first enters the application/registry cycle half-built, so
# `application` is loaded before it. Breaking that cycle deletes this line.
import aart_cli.application  # noqa: F401  # isort: skip
from aart_cli.registry_commands.templates import REGISTRY_GITIGNORE

_PATTERNS = tuple(
    line.strip().strip("/")
    for line in REGISTRY_GITIGNORE.decode().splitlines()
    if line.strip() and not line.startswith("#")
)
_PAYLOAD = "artifacts/plugin/superpowers/7.0.0/payload"


def _ignored(root: Path, *paths: str) -> set[str]:
    completed = subprocess.run(
        ["git", "check-ignore", "--no-index", *paths],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return set(completed.stdout.split())


@unittest.skipUnless(shutil.which("git"), "git is required to ask what git keeps")
class TheIgnoreFileLeavesPayloadsWholeTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        (self.root / ".gitignore").write_bytes(REGISTRY_GITIGNORE)

    def test_nothing_inside_a_payload_is_ignored(self) -> None:
        inside = [f"{_PAYLOAD}/{pattern}/file" for pattern in _PATTERNS]

        self.assertEqual(set(), _ignored(self.root, *inside))

    def test_the_root_clutter_is_still_ignored(self) -> None:
        at_root = [f"{pattern}/file" for pattern in _PATTERNS]

        self.assertEqual(set(at_root), _ignored(self.root, *at_root))


if __name__ == "__main__":
    unittest.main()
