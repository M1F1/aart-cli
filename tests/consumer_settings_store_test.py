"""Screen 28's preferences are kept, read back strictly, and say nothing about the machine.

A Settings screen whose choices die with the terminal is not a Settings screen, and Maintainer
Mode has to survive a restart to be an opt-in at all -- it is the boundary deciding whether
Sources, Candidates, Promotion and Publish are reachable (Product Specification 161.10).

Reading is strict on purpose. Repairing an unreadable preference into a default would have the
frontend decide a detail level, a default scope, or a mode boundary on somebody's behalf, and do
it silently.
"""

from __future__ import annotations

import json
import pathlib
import stat
import tempfile
import unittest

from agent_artifacts.application.consumer_views import (
    CONSUMER_SETTINGS_INVALID,
    SETTING_ROWS,
    ConsumerSettings,
    PresentationProfile,
    settings_from_data,
    settings_to_data,
)
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.consumer_settings import (
    consumer_settings_path,
    read_consumer_settings,
    write_consumer_settings,
)


class ConsumerSettingsValueTest(unittest.TestCase):
    def test_every_accepted_control_is_binary_and_toggles_only_itself(self) -> None:
        for row in SETTING_ROWS:
            with self.subTest(row=row):
                once = ConsumerSettings().toggled(row)
                twice = once.toggled(row)

                self.assertNotEqual(once, ConsumerSettings())
                self.assertEqual(twice, ConsumerSettings())
                changed = [
                    key
                    for key, value in settings_to_data(once).items()
                    if value != settings_to_data(ConsumerSettings())[key]
                ]
                self.assertEqual(len(changed), 1, changed)

    def test_a_setting_nothing_names_is_refused_rather_than_ignored(self) -> None:
        with self.assertRaises(ValueError):
            ConsumerSettings().toggled("dark-mode")

    def test_preferences_round_trip_through_plain_data(self) -> None:
        chosen = ConsumerSettings().toggled("detail-level").toggled("maintainer-mode")

        read = settings_from_data(settings_to_data(chosen))

        self.assertIsInstance(read, Ok)
        self.assertEqual(read.value, chosen)

    def test_stored_preferences_name_no_artifact_registry_or_credential(self) -> None:
        """These are preferences. What somebody installed is not recorded here."""

        data = settings_to_data(ConsumerSettings().toggled("maintainer-mode"))

        self.assertEqual(
            sorted(data), ["default_scope", "detail_level", "maintainer_mode", "show_updates"]
        )

    def test_a_value_this_cannot_mean_is_refused_not_repaired(self) -> None:
        for payload in (
            {"detail_level": "sideways"},
            {"default_scope": "machine"},
            {"show_updates": "yes"},
            {"maintainer_mode": 1},
            {"maintainer_mode": False, "beta_features": True},
            ["fast"],
        ):
            with self.subTest(payload=payload):
                read = settings_from_data(payload)

                self.assertIsInstance(read, Err)
                self.assertEqual(read.diagnostics[0].code, CONSUMER_SETTINGS_INVALID)


class ConsumerSettingsStoreTest(unittest.TestCase):
    def test_never_having_chosen_a_preference_is_not_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            read = read_consumer_settings(root)

            self.assertIsInstance(read, Ok)
            self.assertEqual(read.value, ConsumerSettings())

    def test_a_choice_is_readable_by_whatever_opens_next(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            chosen = ConsumerSettings().toggled("maintainer-mode").toggled("default-scope")

            written = write_consumer_settings(chosen, data_root=root)
            read = read_consumer_settings(root)

            self.assertIsInstance(written, Ok)
            self.assertIsInstance(read, Ok)
            self.assertEqual(read.value, chosen)
            self.assertEqual(read.value.default_scope, "user")

    def test_the_file_is_the_consumers_own_and_nobody_elses(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            write_consumer_settings(ConsumerSettings(), data_root=root)

            path = pathlib.Path(consumer_settings_path(root))
            mode = stat.S_IMODE(path.stat().st_mode)

            self.assertEqual(mode, 0o600, oct(mode))

    def test_a_later_choice_replaces_the_earlier_one_rather_than_accumulating(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            write_consumer_settings(ConsumerSettings().toggled("detail-level"), data_root=root)
            write_consumer_settings(ConsumerSettings(), data_root=root)

            read = read_consumer_settings(root)

            self.assertIsInstance(read, Ok)
            self.assertIs(read.value.profile, PresentationProfile.FAST)
            stored = json.loads(pathlib.Path(consumer_settings_path(root)).read_text())
            self.assertEqual(stored["detail_level"], "fast")

    def test_a_file_that_is_not_readable_json_refuses_rather_than_opening_on_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = pathlib.Path(consumer_settings_path(root))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{ not json")

            read = read_consumer_settings(root)

            self.assertIsInstance(read, Err)
            self.assertEqual(read.diagnostics[0].code, CONSUMER_SETTINGS_INVALID)


if __name__ == "__main__":
    unittest.main()
