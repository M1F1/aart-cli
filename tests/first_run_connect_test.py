"""CP-27 task 3: the first run's seeding transaction, and what it refuses to do.

The seams are injected, so these hold the transaction's own rules rather than a machine's: that it
runs `source add`'s path instead of a second one, that a refusal anywhere leaves nothing behind and
is a warning, and that a configuration which will not load is left for the run to report properly
rather than seeded over.
"""

from __future__ import annotations

import os
import unittest
from tempfile import TemporaryDirectory
from unittest import mock

from aart_cli.application.configuration import FirstRunOptions, LoadedConfiguration
from aart_cli.commands import first_run
from aart_cli.commands._configured_runtime import ConfiguredRuntime
from aart_cli.commands.first_run import (
    FirstRunSeedReport,
    connect_baked_default_registry,
)
from aart_cli.commands.source import AddedConfiguredSource
from aart_cli.configuration.model import (
    ConfiguredSource,
    OrganizationPolicy,
    SourceKind,
    SyncSettings,
    UserConfiguration,
    default_user_configuration,
)
from aart_cli.configuration.policy import EffectiveConfiguration
from aart_cli.configuration.seed import SeededRegistry
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Err, Ok
from aart_cli.model import Request

URL = "https://example.invalid/team/registry.git"
SEEDED = Ok(SeededRegistry(SourceAlias("company"), URL))
REQUEST = Request(command="tui", user_home="/tmp/does-not-matter")


def _loaded(*, first_run: bool, sources: tuple[ConfiguredSource, ...] = ()) -> LoadedConfiguration:
    configuration = (
        default_user_configuration()
        if not sources
        else UserConfiguration(1, sources, None, SyncSettings())
    )
    return LoadedConfiguration(
        configuration,
        EffectiveConfiguration(configuration, OrganizationPolicy(1), ()),
        FirstRunOptions((), (), True, True) if first_run else None,
        None,
        (),
    )


def _runtime(loaded: LoadedConfiguration):
    return Ok(ConfiguredRuntime(None, None, loaded))  # type: ignore[arg-type]


def _added(request: Request) -> Ok:
    source = ConfiguredSource(
        SourceAlias(request.source_alias or ""),
        SourceKind(request.source_kind or "registry-git"),
        request.source_location or "",
        request.ref,
        True,
    )
    # The sync outcome is the add transaction's own business; nothing here reads it.
    return Ok(AddedConfiguredSource(source, source.alias, None, True))  # type: ignore[arg-type]


def _refuses(_: Request) -> Err:
    return Err(
        (
            Diagnostic(
                DiagnosticCode("source-policy-denied"),
                Severity.ERROR,
                "organization policy does not allow that host",
            ),
        )
    )


class ItRunsTheOrdinaryAddTransaction(unittest.TestCase):
    def test_the_request_it_builds_is_the_one_source_add_would_receive(self) -> None:
        seen: list[Request] = []

        def record(request: Request):
            seen.append(request)
            return _added(request)

        connect_baked_default_registry(
            REQUEST,
            load=lambda _: _runtime(_loaded(first_run=True)),
            add=record,
            read_baked=lambda: SEEDED,
        )
        self.assertEqual(len(seen), 1)
        built = seen[0]
        self.assertEqual(
            (
                built.command,
                built.source_action,
                built.source_alias,
                built.source_kind,
                built.source_location,
                built.ref,
                built.source_make_default,
            ),
            ("source", "add", "company", "registry-git", URL, "main", True),
        )

    def test_it_carries_the_caller_s_home_rather_than_resolving_its_own(self) -> None:
        seen: list[Request] = []
        connect_baked_default_registry(
            Request(command="tui", user_home="/somewhere/else"),
            load=lambda _: _runtime(_loaded(first_run=True)),
            add=lambda request: (seen.append(request), _added(request))[1],
            read_baked=lambda: SEEDED,
        )
        self.assertEqual(seen[0].user_home, "/somewhere/else")

    def test_a_connected_registry_is_reported_with_what_to_say(self) -> None:
        report = connect_baked_default_registry(
            REQUEST,
            load=lambda _: _runtime(_loaded(first_run=True)),
            add=_added,
            read_baked=lambda: SEEDED,
        )
        assert report.connected is not None
        self.assertEqual(report.connected.source.alias, SourceAlias("company"))
        self.assertIn(URL, "\n".join(report.lines))
        self.assertEqual(report.diagnostics, ())


class ItDoesNothingWhenItShouldNot(unittest.TestCase):
    def _never(self, _: Request):
        raise AssertionError("the add transaction must not run")

    def test_a_later_run_adds_nothing(self) -> None:
        report = connect_baked_default_registry(
            REQUEST,
            load=lambda _: _runtime(_loaded(first_run=False)),
            add=self._never,
            read_baked=lambda: SEEDED,
        )
        self.assertEqual((report.connected, report.lines, report.diagnostics), (None, (), ()))

    def test_a_build_that_baked_nothing_adds_nothing(self) -> None:
        report = connect_baked_default_registry(
            REQUEST,
            load=lambda _: _runtime(_loaded(first_run=True)),
            add=self._never,
            read_baked=lambda: Ok(None),
        )
        self.assertEqual((report.connected, report.diagnostics), (None, ()))

    def test_a_configuration_that_will_not_load_is_left_alone_and_silent(self) -> None:
        # The run is about to report that properly. A warning from here would be a second, worse
        # account of the same thing.
        report = connect_baked_default_registry(
            REQUEST,
            load=lambda _: Err(
                (Diagnostic(DiagnosticCode("config-invalid"), Severity.ERROR, "unreadable"),)
            ),
            add=self._never,
            read_baked=lambda: SEEDED,
        )
        self.assertEqual((report.connected, report.lines, report.diagnostics), (None, (), ()))


class ARefusalIsAWarning(unittest.TestCase):
    def _report(self):
        return connect_baked_default_registry(
            REQUEST,
            load=lambda _: _runtime(_loaded(first_run=True)),
            add=_refuses,
            read_baked=lambda: SEEDED,
        )

    def test_nothing_is_reported_as_connected(self) -> None:
        self.assertIsNone(self._report().connected)

    def test_the_run_is_not_failed(self) -> None:
        self.assertEqual(
            [diagnostic.severity for diagnostic in self._report().diagnostics],
            [Severity.WARNING],
        )

    def test_the_reason_the_transaction_gave_is_carried_forward(self) -> None:
        self.assertIn(
            "organization policy does not allow that host",
            self._report().diagnostics[0].message,
        )

    def test_it_says_what_to_do_instead(self) -> None:
        self.assertIn("Add Registry", " ".join(self._report().diagnostics[0].remediation))


class TheTerminalStartupSeedsBeforeItComposes(unittest.TestCase):
    """The wiring, held where it matters: before composition, and never fatal.

    Composing first would read a configuration the seed is about to change, so the application
    would open on the state the run was meant to leave behind.
    """

    def test_the_startup_helper_asks_for_the_home_it_was_given(self) -> None:
        from aart_cli import tui

        seen: list[Request] = []

        def record(request: Request, **_: object):
            seen.append(request)
            return FirstRunSeedReport(None, (), ())

        with mock.patch.object(first_run, "connect_baked_default_registry", record):
            tui._seed_first_run("/a/home")
        self.assertEqual((seen[0].command, seen[0].user_home), ("tui", "/a/home"))

    def test_a_defect_in_seeding_never_stops_the_terminal_starting(self) -> None:
        from aart_cli import tui

        def explode(*_: object, **__: object):
            raise RuntimeError("something nobody predicted")

        with mock.patch.object(first_run, "connect_baked_default_registry", explode):
            report = tui._seed_first_run("/a/home")
        self.assertEqual((report.connected, report.lines, report.diagnostics), (None, (), ()))

    def test_what_was_connected_is_said_out_loud(self) -> None:
        from aart_cli import tui

        said: list[str] = []
        with mock.patch("builtins.print", lambda *parts: said.append(" ".join(map(str, parts)))):
            tui._announce(FirstRunSeedReport(None, ("Connected company (" + URL + ").",), ()))
        self.assertIn(URL, "\n".join(said))

    def test_a_warning_is_said_with_what_to_do_about_it(self) -> None:
        from aart_cli import tui

        said: list[str] = []
        report = FirstRunSeedReport(
            None,
            (),
            (
                Diagnostic(
                    DiagnosticCode("default-registry-unusable"),
                    Severity.WARNING,
                    "cannot be used",
                    remediation=("open Registries and choose Add Registry",),
                ),
            ),
        )
        with mock.patch("builtins.print", lambda *parts: said.append(" ".join(map(str, parts)))):
            tui._announce(report)
        joined = "\n".join(said)
        self.assertIn("warning: cannot be used", joined)
        self.assertIn("open Registries and choose Add Registry", joined)


class ARegistryThatCannotBeReachedLeavesNothingBehind(unittest.TestCase):
    """The claim end to end, on a real home, with a real clone that really fails.

    Port 1 on the loopback interface refuses immediately, so this is a genuine acquisition failure
    rather than a stubbed one, and it costs a fraction of a second. What must survive it is the
    absence of a configuration: a `config.json` naming a Registry this machine could not read would
    leave the person worse off than the untouched first run they started with.
    """

    URL = "https://127.0.0.1:1/team/registry.git"

    def test_the_run_is_warned_and_nothing_is_written(self) -> None:
        seeded = Ok(SeededRegistry(SourceAlias("company"), self.URL))
        with TemporaryDirectory() as home:
            report = connect_baked_default_registry(
                Request(command="tui", user_home=home), read_baked=lambda: seeded
            )
            self.assertIsNone(report.connected)
            self.assertEqual(
                [diagnostic.severity for diagnostic in report.diagnostics], [Severity.WARNING]
            )
            self.assertFalse(
                os.path.exists(os.path.join(home, ".aart-cli", "config.json")),
                "a Registry that could not be read must not reach the configuration",
            )

    def test_the_warning_says_which_registry_the_build_named(self) -> None:
        seeded = Ok(SeededRegistry(SourceAlias("company"), self.URL))
        with TemporaryDirectory() as home:
            report = connect_baked_default_registry(
                Request(command="tui", user_home=home), read_baked=lambda: seeded
            )
        self.assertIn("default Registry", report.diagnostics[0].message)


if __name__ == "__main__":
    unittest.main()
