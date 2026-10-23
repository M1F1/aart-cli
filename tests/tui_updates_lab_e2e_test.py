"""CP-41, end to end: a maintainer publishes, and the consumer's TUI says so when it opens.

The owner's report: a Collection approved in the Registry did not appear in the TUI until `s` was
pressed on Registries, nothing said a sync was due, and Updates never listed anything. This drives
that scenario over the manual-test lab's real Git remotes: the consumer installs from the Registry,
the maintainer then publishes a newer version and a new Collection to the remote, and the consumer
application is composed the way `aart-cli` composes it on launch.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

#: Composes the consumer application as `tui.run` does, and reports what its screens would show.
_PROBE = textwrap.dedent(
    """
    import json, os, sys
    from datetime import date
    from aart_cli.application.consumer_ui import ConsumerUiState
    from aart_cli.application.consumer_views import ConsumerScreen, ConsumerSession
    from aart_cli.tui import _canonical_consumer_actions

    said = []
    composed = _canonical_consumer_actions(
        project=os.getcwd(),
        user_home=os.environ["HOME"],
        today=date.today(),
        observe=said.append if sys.argv[1] == "observe" else None,
    )
    screens = composed.value.source().screens
    print(json.dumps({
        "said": said,
        "updates": [[item.row, item.available] for item in screens.updatable],
        "update_count": screens.dashboard.update_count,
        "collections": [str(item.collection.coordinate) for item in screens.collections],
        "registries": [[item.alias, item.health] for item in screens.registries],
    }))
    """
)


class AMaintainersPublicationReachesTheConsumersTui(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from scripts.manual_test import publish_collection, publish_version, setup_lab

        temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        cls.root = pathlib.Path(temporary.name) / "manual-lab"
        lab = setup_lab(cls.root)
        cls._consume(
            "registry", "add", "--alias", "lab", "--kind", "git",
            "--location", "https://manual.aart.test/registry.git", "--ref", lab.branch,
        )  # fmt: skip
        cls._consume("install", "lab/skill/manual-check@1.0.0", "--profile", "claude", "--yes")
        cls.published = publish_version(cls.root)
        publish_collection(cls.root)

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

    def _probe(self, mode: str) -> dict:
        from scripts.manual_test import CHECKOUT, shell_environment

        env, project = shell_environment(self.root, "consumer")
        env["PYTHONPATH"] = str(CHECKOUT)
        ran = subprocess.run(
            (sys.executable, "-c", _PROBE, mode),
            cwd=project,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(ran.stdout)

    def test_the_lab_publishes_the_next_version(self) -> None:
        self.assertEqual(self.published, "1.0.1")

    def test_launching_shows_the_update_and_the_new_collection(self) -> None:
        seen = self._probe("observe")

        self.assertEqual(seen["registries"], [["lab", "healthy"]])
        self.assertEqual(len(seen["said"]), 1)
        self.assertIn("lab", seen["said"][0])
        ((row, available),) = seen["updates"]
        self.assertTrue(row.startswith("lab/skill/manual-check@1.0.0#claude#project#"), row)
        self.assertEqual(available, self.published)
        self.assertEqual(seen["update_count"], 1)
        self.assertIn("lab/collection/lab-starter@1.0.0", seen["collections"])


if __name__ == "__main__":
    unittest.main()
