"""CP-23 task 16.3: installed configuration and credentials share one grouped area."""

from __future__ import annotations

import datetime as dt
import pathlib
import tempfile
import unittest
from dataclasses import replace

from agent_artifacts.application.consumer_session import assemble_consumer_machine
from agent_artifacts.application.consumer_ui import (
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import (
    ConfigurationFileView,
    ConsumerScreen,
    ConsumerSession,
)
from agent_artifacts.domain.configuration_files import ConfigurationFileRecord
from agent_artifacts.domain.result import Ok
from agent_artifacts.io.consumer_machine import read_configuration_files
from agent_artifacts.protocol.hashing import sha256_bytes
from agent_artifacts.tui_consumer import CanonicalScreenSource, _reload, frame, screens_from
from tests.consumer_session_test import TOKEN, inspection, observed


class ConfigurationFileReadingTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name).resolve()
        original = inspection().record
        self.record = replace(
            original,
            receipt=replace(
                original.receipt,
                root=str(self.root),
                launcher=str(self.root / "launch.sh"),
                interpreter=str(self.root / "runtime/.venv/bin/python"),
                registrations=(),
            ),
        )

    def _record(self, harness: str, content: bytes) -> ConfigurationFileRecord:
        path = self.root / "config" / f"{harness}.conf"
        return ConfigurationFileRecord(harness, str(path), sha256_bytes(content))

    def test_matching_changed_and_missing_files_are_read_without_guessing(self) -> None:
        original = b"github-org=acme\n"
        changed = b"github-org=other-team\n"
        claude = self._record("claude", original)
        tabnine = self._record("tabnine", original)
        opencode = self._record("opencode", original)
        pathlib.Path(claude.path).parent.mkdir(parents=True)
        pathlib.Path(claude.path).write_bytes(original)
        pathlib.Path(tabnine.path).write_bytes(changed)
        installed = replace(
            self.record,
            receipt=replace(
                self.record.receipt,
                configuration_files=(claude, tabnine, opencode),
            ),
        )

        views = read_configuration_files((installed,))

        self.assertIsInstance(views, Ok, getattr(views, "diagnostics", ()))
        assert isinstance(views, Ok)
        by_harness = {item.harness: item for item in views.value}
        self.assertEqual(by_harness["claude"].state, "matched")
        self.assertEqual(by_harness["claude"].values, (("github-org", "acme"),))
        self.assertEqual(by_harness["tabnine"].state, "changed-outside-aart")
        self.assertEqual(by_harness["tabnine"].values, (("github-org", "other-team"),))
        self.assertEqual(by_harness["opencode"].state, "missing")
        self.assertEqual(by_harness["opencode"].values, ())

    def test_invalid_file_is_unknown_and_never_projects_its_raw_text(self) -> None:
        content = b"not a configuration file\n"
        record = self._record("claude", content)
        pathlib.Path(record.path).parent.mkdir(parents=True)
        pathlib.Path(record.path).write_bytes(content)
        installed = replace(
            self.record,
            receipt=replace(self.record.receipt, configuration_files=(record,)),
        )

        views = read_configuration_files((installed,))

        self.assertIsInstance(views, Ok)
        assert isinstance(views, Ok)
        self.assertEqual(views.value[0].state, "unreadable")
        self.assertEqual(views.value[0].values, ())
        self.assertNotIn("not a configuration file", repr(views.value[0]))


class UserInputsAreaProjectionTest(unittest.TestCase):
    def _source(self) -> tuple[CanonicalScreenSource, str]:
        coordinate = str(inspection().record.coordinate)
        configuration = (
            ConfigurationFileView(
                coordinate,
                "claude",
                "/opt/agents/mcp/github/config/claude.conf",
                "matched",
                (("github-org", "acme"),),
                "",
            ),
        )
        machine = assemble_consumer_machine(
            (inspection(),),
            credentials=(observed(TOKEN),),
            configurations=configuration,
            today=dt.date(2026, 9, 14),
        )
        return CanonicalScreenSource(screens_from(machine)), coordinate

    def test_area_rows_are_artifacts_and_details_keep_two_distinct_sections(self) -> None:
        source, coordinate = self._source()
        state = ConsumerUiState(ConsumerSession(ConsumerScreen.CREDENTIALS))
        state = _reload(source, state, entering=True)

        self.assertEqual(state.rows, (coordinate,))
        area = "\n".join(frame(source, state))
        self.assertIn("User Variables And Credentials", area)
        self.assertIn(coordinate, area)

        event = ConsumerUiEvent(
            ConsumerUiEventKind.NAVIGATE,
            screen=ConsumerScreen.USER_INPUT_DETAILS,
        )
        details, _ = reduce_consumer_ui(state, event)
        details = _reload(source, details, entering=True)
        drawn = "\n".join(frame(source, details))

        self.assertIn("\nConfiguration\n", drawn)
        self.assertIn("claude", drawn)
        self.assertIn("github-org", drawn)
        self.assertIn("claude: acme", drawn)
        self.assertIn("\nCredentials\n", drawn)
        self.assertIn("github-token", drawn)
        self.assertIn("Configured securely", drawn)
        self.assertNotIn("credential value", drawn.lower())

    def test_an_artifact_with_only_a_provider_reference_is_still_grouped(self) -> None:
        coordinate = str(inspection().record.coordinate)
        machine = assemble_consumer_machine(
            (inspection(),),
            credentials=(observed(TOKEN),),
            today=dt.date(2026, 9, 14),
        )
        source = CanonicalScreenSource(screens_from(machine))
        state = _reload(
            source,
            ConsumerUiState(ConsumerSession(ConsumerScreen.CREDENTIALS)),
            entering=True,
        )

        self.assertEqual(state.rows, (coordinate,))
        self.assertIn("github-token", "\n".join(frame(source, state)))


if __name__ == "__main__":
    unittest.main()
