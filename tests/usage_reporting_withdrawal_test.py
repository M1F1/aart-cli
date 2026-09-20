"""CP-25.04-05: withdraw usage reporting without rejecting old configuration files."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from aart_cli.configuration import schema
from aart_cli.domain.result import Err, Ok


def _line(source: str, needle: str) -> int:
    for number, text in enumerate(source.splitlines(), start=1):
        if needle in text:
            return number
    return 0


class TheOfferIsGoneTest(unittest.TestCase):
    def test_the_usage_reporting_package_is_gone(self) -> None:
        package = Path(__file__).parents[1] / "aart_cli" / "reporting"
        self.assertFalse(package.exists())

    def test_the_marketplace_command_names_no_usage_report(self) -> None:
        import inspect

        from aart_cli.commands import marketplace

        source = inspect.getsource(marketplace)
        for gone in ("_CliReporting", "_read_reporting_consent", "usage report", "UsageReport"):
            with self.subTest(symbol=gone):
                self.assertFalse(
                    gone in source,
                    f"marketplace.py still names {gone!r} on line {_line(source, gone)}",
                )


class OldConfigurationsStillLoadTest(unittest.TestCase):
    """The withdrawal must not make AART refuse settings it previously wrote itself."""

    def test_a_configuration_written_before_the_withdrawal_still_loads(self) -> None:
        for block in ('{"mode": "prompt"}', '{"mode": "disabled"}'):
            with self.subTest(reporting=block):
                raw = json.dumps(json.loads('{"schema_version": 1, "reporting": ' + block + "}"))
                self.assertIsInstance(schema.parse_user_configuration(raw), Ok)

    def test_an_organization_policy_written_before_the_withdrawal_still_loads(self) -> None:
        raw = '{"schema_version": 1, "reporting": {"mode": "disabled"}}'
        self.assertIsInstance(schema.parse_organization_policy(raw), Ok)

    def test_the_block_is_read_to_nothing_rather_than_to_a_setting(self) -> None:
        parsed = schema.parse_user_configuration(
            '{"schema_version": 1, "reporting": {"mode": "prompt"}}'
        )
        assert isinstance(parsed, Ok), parsed
        self.assertFalse(hasattr(parsed.value, "reporting"))

    def test_a_field_that_was_never_accepted_is_still_refused(self) -> None:
        self.assertIsInstance(
            schema.parse_user_configuration('{"schema_version": 1, "nonsense": {}}'), Err
        )


class ConfigurationsStopGrowingTheBlockTest(unittest.TestCase):
    def test_a_freshly_written_configuration_carries_no_reporting_block(self) -> None:
        parsed = schema.parse_user_configuration('{"schema_version": 1}')
        assert isinstance(parsed, Ok), parsed

        written = schema.user_configuration_bytes(parsed.value)
        self.assertNotIn(
            "reporting", written if isinstance(written, str) else written.decode("utf-8")
        )


if __name__ == "__main__":
    unittest.main()
