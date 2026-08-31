"""Reading a whole machine back off a disk, the way a public entry point has to.

Every consumer screen is a projection of a `ConsumerMachine`, and until now the only thing that
built one was a test: each of them read the receipts, inspected the installation, paired the two
and assembled the result by hand. A public entry point cannot do that, so `run()` had nothing to
open and `run_consumer` had no caller.

What the reader cannot do is guess. An installation whose environment is gone has to read as
broken, and the only honest way to know which environment that was is for the receipt to say --
which is why a receipt now records the interpreter its environment was built from.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import unittest

from agent_artifacts.application.consumer_session import ConsumerMachine
from agent_artifacts.domain.identifiers import ObjectDigest
from agent_artifacts.domain.receipts import (
    InstallationReceipt,
    installation_receipt_from_data,
    installation_receipt_to_data,
)
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.consumer_machine import read_consumer_machine
from agent_artifacts.io.receipt_store import LocalReceiptStore
from tests.repair_e2e_test import COORDINATE, InstalledFixture

TODAY = dt.date(2026, 8, 31)


class RememberedEnvironmentTest(unittest.TestCase):
    """A receipt records what its environment was built from, so nothing later has to guess."""

    def receipt(self, **overrides: object) -> InstallationReceipt:
        fields: dict[str, object] = {
            "artifact": "public/mcp/github@1.5.0",
            "root": "/home/agent/aart/github",
            "launcher": "/home/agent/aart/github/launch",
            "launcher_digest": ObjectDigest("sha256", "a" * 64),
            "interpreter": "/home/agent/aart/github/env/bin/python",
            "base_interpreter": "/usr/bin/python3",
        }
        fields.update(overrides)
        return InstallationReceipt(**fields)  # type: ignore[arg-type]

    def test_a_receipt_survives_the_round_trip_carrying_it(self) -> None:
        written = installation_receipt_to_data(self.receipt())
        read = installation_receipt_from_data(json.loads(json.dumps(written)))

        self.assertIsInstance(read, Ok, getattr(read, "diagnostics", ()))
        self.assertEqual(read.value.base_interpreter, "/usr/bin/python3")
        self.assertEqual(read.value, self.receipt())

    def test_a_receipt_written_before_this_field_existed_still_reads(self) -> None:
        """Absent is a fact: nothing recorded it, so nothing may claim to know it."""

        written = dict(installation_receipt_to_data(self.receipt()))
        written.pop("base_interpreter")

        read = installation_receipt_from_data(written)

        self.assertIsInstance(read, Ok, getattr(read, "diagnostics", ()))
        self.assertIsNone(read.value.base_interpreter)

    def test_a_base_interpreter_that_is_not_a_path_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.receipt(base_interpreter="python3\n")


class MachineFromDiskTest(InstalledFixture):
    """What a second process, holding nothing in memory, can say about this machine."""

    def setUp(self) -> None:
        super().setUp()
        self.state_root = str(self.scope / "state")
        store = LocalReceiptStore(self.state_root)
        recorded = store.record_installation(COORDINATE, self.receipt)
        self.assertIsInstance(recorded, Ok, getattr(recorded, "diagnostics", ()))

    def read(self):
        return read_consumer_machine(
            state_root=self.state_root,
            harness_root=str(self.scope),
            today=TODAY,
        )

    def test_a_machine_read_from_disk_counts_what_is_really_installed(self) -> None:
        read = self.read()

        self.assertIsInstance(read, Ok, getattr(read, "diagnostics", ()))
        self.assertIsInstance(read.value, ConsumerMachine)
        self.assertEqual([item.coordinate for item in read.value.installed], [str(COORDINATE)])
        self.assertEqual(read.value.installed[0].health, "attention")

    def test_an_installation_whose_environment_is_gone_reads_as_broken(self) -> None:
        """The reason the receipt remembers its base interpreter, stated as a failure."""

        os.remove(self.receipt.interpreter)

        machine = self.read().value

        self.assertEqual(machine.installed[0].health, "broken")

    def test_a_launcher_broken_after_the_install_reads_as_broken(self) -> None:
        pathlib.Path(self.receipt.launcher).write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")

        machine = self.read().value

        self.assertEqual(machine.installed[0].health, "broken")

    def test_a_credential_no_provider_here_can_see_is_unknown_rather_than_absent(self) -> None:
        """Nothing was asked, so nothing may be reported as missing."""

        machine = self.read().value

        self.assertEqual(
            [item.health for item in machine.credentials],
            ["unknown"] * len(machine.credentials),
        )

    def test_a_record_that_cannot_be_read_is_reported_rather_than_skipped(self) -> None:
        """D-045: a skipped receipt reads as an installation that never happened."""

        store = LocalReceiptStore(self.state_root)
        path = pathlib.Path(store.path_for(COORDINATE))
        path.write_text("{not json", encoding="utf-8")

        self.assertIsInstance(self.read(), Err)

    def test_an_empty_machine_is_a_machine_rather_than_a_failure(self) -> None:
        read = read_consumer_machine(
            state_root=str(self.scope / "empty"),
            harness_root=str(self.scope),
            today=TODAY,
        )

        self.assertIsInstance(read, Ok, getattr(read, "diagnostics", ()))
        self.assertEqual(read.value.installed, ())


if __name__ == "__main__":
    unittest.main()
