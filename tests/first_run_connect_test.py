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

from hypothesis import given, settings
from hypothesis import strategies as st

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
        FirstRunOptions((), (), True) if first_run else None,
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


def _git_refuses(message: str):
    def refuse(_: Request) -> Err:
        return Err((Diagnostic(DiagnosticCode("source-git-failed"), Severity.ERROR, message),))

    return refuse


_FETCH = "Git command failed for git -C mirror.git fetch --force --prune --tags origin: "
_SIGNED_OUT = (
    "fatal: unable to get password from user",
    "fatal: could not read Username for 'https://example.invalid': terminal prompts disabled",
    "remote: Invalid username or password.\nfatal: Authentication failed for 'x'",
    "fatal: unable to access 'x': The requested URL returned error: 401",
    "fatal: unable to access 'x': The requested URL returned error: 403",
)


class TheWarningSaysWhichRegistryAndHowToReachIt(unittest.TestCase):
    """B-268, D-515: the warning names the Registry, and a missing sign-in says how to sign in.

    The error Git gives names the mirror's remote, `origin`, never the URL, so without this a person
    could not tell which Registry failed. And `credential.interactive=never` means a host Git holds
    no credential for fails the same way every time: the one useful thing to say is how to give Git
    one.
    """

    def _report(self, add, url: str = URL) -> FirstRunSeedReport:
        return connect_baked_default_registry(
            REQUEST,
            load=lambda _: _runtime(_loaded(first_run=True)),
            add=add,
            read_baked=lambda: Ok(SeededRegistry(SourceAlias("company"), url)),
        )

    def _said(self, add, url: str = URL) -> str:
        (diagnostic,) = self._report(add, url).diagnostics
        return "\n".join((diagnostic.message, *diagnostic.remediation))

    def test_it_names_the_alias_and_url_with_a_check_and_the_command_to_add_it(self) -> None:
        for add in (_refuses, _git_refuses(_FETCH + _SIGNED_OUT[0])):
            with self.subTest(add=add):
                (diagnostic,) = self._report(add).diagnostics
                self.assertIn(f"company ({URL})", diagnostic.message)
                self.assertIn(
                    f"Check that Git can read it:\n"
                    f"    git -c credential.interactive=never ls-remote {URL} HEAD",
                    diagnostic.remediation,
                )
                self.assertIn(
                    "Or connect it yourself:\n    aart-cli consume registry add --alias company "
                    f"--kind git --location {URL} --default",
                    diagnostic.remediation,
                )

    def test_a_missing_sign_in_says_how_to_give_git_one_for_that_host(self) -> None:
        for failure in _SIGNED_OUT:
            with self.subTest(failure):
                said = self._said(_git_refuses(_FETCH + failure))
                self.assertIn("Git has no credential for example.invalid", said)
                self.assertIn("gh auth login --hostname example.invalid", said)
                self.assertIn("gh auth setup-git --hostname example.invalid", said)

    def test_any_other_refusal_never_suggests_signing_in(self) -> None:
        for add in (
            _refuses,
            _git_refuses(_FETCH + "fatal: unable to access 'x': Could not resolve host"),
            _git_refuses(_FETCH + "fatal: repository 'x' not found"),
        ):
            with self.subTest(add=add):
                self.assertNotIn("gh auth", self._said(add))

    def test_a_refused_ssh_key_is_not_answered_with_an_https_sign_in(self) -> None:
        said = self._said(
            _git_refuses(_FETCH + "git@example.invalid: Permission denied (publickey)."),
            "ssh://git@example.invalid/team/registry.git",
        )
        self.assertNotIn("gh auth", said)
        self.assertIn("Git has no SSH key example.invalid accepts", said)

    def test_signing_in_is_offered_only_for_https_since_only_https_uses_it(self) -> None:
        said = self._said(
            _git_refuses(_FETCH + _SIGNED_OUT[2]), "ssh://git@example.invalid/team/registry.git"
        )
        self.assertNotIn("gh auth", said)

    @settings(max_examples=60, deadline=None)
    @given(
        alias=st.from_regex(r"[a-z][a-z0-9-]{0,20}", fullmatch=True),
        host=st.from_regex(r"[a-z][a-z0-9-]{0,15}(\.[a-z]{2,6}){1,2}", fullmatch=True),
        failure=st.sampled_from(_SIGNED_OUT),
    )
    def test_every_registry_is_named_and_signed_in_to_by_its_own_host(
        self, alias: str, host: str, failure: str
    ) -> None:
        url = f"https://{host}/team/registry.git"
        report = connect_baked_default_registry(
            REQUEST,
            load=lambda _: _runtime(_loaded(first_run=True)),
            add=_git_refuses(_FETCH + failure),
            read_baked=lambda: Ok(SeededRegistry(SourceAlias(alias), url)),
        )
        (diagnostic,) = report.diagnostics
        self.assertIn(f"{alias} ({url})", diagnostic.message)
        said = "\n".join(diagnostic.remediation)
        self.assertIn(f"    gh auth login --hostname {host}\n", said)
        self.assertIn(f"    gh auth setup-git --hostname {host}\n", said + "\n")
        self.assertIn(f"--alias {alias} --kind git --location {url} --default\n", said + "\n")


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


class TheFlagFormSeedsAConsumerToo(unittest.TestCase):
    """B-168: a first run that is a `consume` command connects the baked Registry as well.

    Only `consume`, because that is the family that reads Registries; a maintainer works in a
    checkout and an author in a workspace, and neither should reach the network for a Registry it
    never asked for. `consume registry add` is the person choosing a Registry, and `--offline`
    forbids the fetch a connection needs, so neither seeds.
    """

    def _main(self, *argv: str) -> tuple[list[Request], list[str], str, str]:
        from io import StringIO

        from aart_cli import cli

        seeded: list[Request] = []
        dispatched: list[str] = []

        def record(request: Request, **_: object) -> FirstRunSeedReport:
            seeded.append(request)
            return FirstRunSeedReport(None, ("Connected company (" + URL + ").",), ())

        def handler(request: Request) -> int:
            dispatched.append("seeded" if seeded else "unseeded")
            return 0

        out, err = StringIO(), StringIO()
        with (
            mock.patch.object(first_run, "connect_baked_default_registry", record),
            mock.patch.dict(cli.DISPATCH, {name: handler for name in cli.DISPATCH}),
            mock.patch("sys.stdout", out),
            mock.patch("sys.stderr", err),
        ):
            cli.main(list(argv))
        return seeded, dispatched, out.getvalue(), err.getvalue()

    def test_a_consume_command_seeds_before_it_runs(self) -> None:
        seeded, dispatched, _, _ = self._main("consume", "list", "--json")
        self.assertEqual(len(seeded), 1)
        self.assertEqual(dispatched, ["seeded"])

    def test_what_was_connected_goes_to_stderr_so_json_stays_clean(self) -> None:
        _, _, out, err = self._main("consume", "list", "--json")
        self.assertNotIn(URL, out)
        self.assertIn(URL, err)

    def test_adding_a_registry_is_a_choice_and_seeds_nothing(self) -> None:
        seeded, dispatched, _, _ = self._main(
            "consume", "registry", "add", "--alias", "mine", "--kind", "git", "--location", URL
        )
        self.assertEqual((seeded, dispatched), ([], ["unseeded"]))

    def test_offline_forbids_the_fetch_and_seeds_nothing(self) -> None:
        seeded, _, _, _ = self._main("consume", "install", "x", "--offline", "--yes")
        self.assertEqual(seeded, [])

    def test_a_maintainer_command_seeds_nothing(self) -> None:
        seeded, _, _, _ = self._main("maintain", "registry", "validate")
        self.assertEqual(seeded, [])

    def test_a_defect_in_seeding_never_stops_the_command(self) -> None:
        from aart_cli import cli

        def explode(*_: object, **__: object):
            raise RuntimeError("something nobody predicted")

        with (
            mock.patch.object(first_run, "connect_baked_default_registry", explode),
            mock.patch.dict(cli.DISPATCH, {name: (lambda _: 0) for name in cli.DISPATCH}),
        ):
            self.assertEqual(cli.main(["consume", "list"]), 0)


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
