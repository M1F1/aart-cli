"""CP-42: one artifact in one harness for the user and for two projects is three installations.

The owner's report, twice over. Opening Installed crashed with `ValueError` in `ConsumerUiEvent`,
because the same MCP installed in opencode at project and at user scope drew two identical rows.
And User Variables And Credentials drew those installations as one entry, holding every file and
every credential of all of them, so nobody could tell which value or which missing credential
belonged where. Both came from one key: `coordinate#harness` left out the scope and the root that
§169.3 makes part of installation identity (D-479).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

from aart_cli.application.consumer_session import InstalledInspection, assemble_consumer_machine
from aart_cli.application.consumer_ui import ConsumerUiState
from aart_cli.application.consumer_views import ConsumerScreen, ConsumerSession
from aart_cli.domain.credentials import CredentialReference
from aart_cli.domain.harness import Scope
from aart_cli.domain.identifiers import ArtifactIdentity, InputId, SourceAlias
from aart_cli.domain.installation_owner import (
    InstallationOwner,
    credential_address,
    describe_installation,
    installation_key,
)
from aart_cli.domain.receipts import InstalledRecord
from aart_cli.tui_consumer import (
    CanonicalScreenSource,
    _reload,
    frame,
    render_user_inputs_area,
    screens_from,
)
from tests.consumer_session_test import coordinate as coordinate_of
from tests.consumer_session_test import current, desired, observed, receipt

TODAY = dt.date(2026, 10, 23)
COORDINATE = "public/mcp/github@1.6.0"
TOKEN_INPUT = InputId("github-token")


def _owner(scope: Scope, root: str) -> InstallationOwner:
    return InstallationOwner(
        SourceAlias("public"), ArtifactIdentity("mcp", "github"), scope, root, "opencode"
    )


#: The owner's machine: one MCP in opencode, for the user and in two projects.
OWNERS = (
    _owner(Scope.USER, "/home/dev"),
    _owner(Scope.PROJECT, "/home/dev/code/alpha"),
    _owner(Scope.PROJECT, "/home/dev/code/beta"),
)


def _reference(owner: InstallationOwner) -> CredentialReference:
    return CredentialReference(TOKEN_INPUT, credential_address(owner, TOKEN_INPUT))


def _inspection(owner: InstallationOwner) -> InstalledInspection:
    record = dataclasses.replace(receipt("github", (_reference(owner),)), owner=owner)
    return InstalledInspection(
        InstalledRecord(coordinate_of("github"), record), desired("github"), current("github")
    )


def _screens():
    machine = assemble_consumer_machine(
        tuple(_inspection(owner) for owner in OWNERS),
        credentials=tuple(observed(_reference(owner)) for owner in OWNERS),
        today=TODAY,
    )
    return screens_from(machine)


def _entered(screen: ConsumerScreen) -> tuple[CanonicalScreenSource, ConsumerUiState]:
    source = CanonicalScreenSource(_screens())
    state = _reload(source, ConsumerUiState(ConsumerSession(screen)), entering=True)
    return source, state


class TheKeyCarriesTheWholeInstallationIdentity(unittest.TestCase):
    def test_scope_and_root_separate_installations_of_one_harness(self) -> None:
        keys = {installation_key(COORDINATE, owner) for owner in OWNERS}

        self.assertEqual(len(keys), 3)

    def test_the_installed_row_is_the_key_its_record_is_addressed_by(self) -> None:
        """A row spelled one way and a lookup another way address nothing."""

        machine = assemble_consumer_machine(
            tuple(_inspection(owner) for owner in OWNERS), today=TODAY
        )

        self.assertEqual(
            [item.row for item in machine.installed],
            [installation_key(COORDINATE, owner) for owner in OWNERS],
        )


class APersonReadsWhichInstallationItIs(unittest.TestCase):
    def test_a_key_reads_as_artifact_harness_and_where(self) -> None:
        described = [describe_installation(installation_key(COORDINATE, o)) for o in OWNERS]

        self.assertEqual(
            described,
            [
                f"{COORDINATE} · opencode · user",
                f"{COORDINATE} · opencode · project alpha",
                f"{COORDINATE} · opencode · project beta",
            ],
        )

    def test_a_record_naming_no_owner_reads_as_its_coordinate(self) -> None:
        self.assertEqual(describe_installation(COORDINATE), COORDINATE)

    @given(
        parts=st.lists(
            st.text(alphabet="ab#· -_", min_size=1).filter(lambda part: part not in {".", ".."}),
            min_size=1,
            max_size=4,
        )
    )
    @settings(max_examples=200)
    def test_whatever_the_root_holds_the_key_splits_back_into_its_parts(
        self, parts: list[str]
    ) -> None:
        owner = dataclasses.replace(OWNERS[1], root="/" + "/".join(parts))
        key = installation_key(COORDINATE, owner)

        self.assertEqual(key.split("#", 3), [COORDINATE, "opencode", "project", owner.root])


class InstalledOpensWithAllThree(unittest.TestCase):
    def test_entering_installed_draws_three_rows_rather_than_failing(self) -> None:
        source, state = _entered(ConsumerScreen.INSTALLED)

        self.assertEqual(len(state.rows), 3)
        self.assertEqual(len(set(state.rows)), 3)
        self.assertTrue(frame(source, state))


class UserVariablesAndCredentialsHasOneEntryPerInstallation(unittest.TestCase):
    def test_each_installation_is_its_own_entry(self) -> None:
        _source, state = _entered(ConsumerScreen.CREDENTIALS)

        self.assertEqual(state.rows, tuple(sorted(installation_key(COORDINATE, o) for o in OWNERS)))

    def test_each_entry_says_which_installation_it_is_and_holds_only_its_own_credential(
        self,
    ) -> None:
        screens = _screens()
        rows = tuple(installation_key(COORDINATE, owner) for owner in OWNERS)

        drawn = render_user_inputs_area(screens, rows, rows[0])

        headings = [line for line in drawn if line.startswith(("> ", "  ")) and "·" in line]
        self.assertEqual(
            headings,
            [
                f"> {COORDINATE} · opencode · user",
                f"  {COORDINATE} · opencode · project alpha",
                f"  {COORDINATE} · opencode · project beta",
            ],
        )
        self.assertEqual(
            [line for line in drawn if "Credentials:" in line],
            ["    Credentials: ✓ github-token  Ready  Used by 1"] * 3,
        )

    def test_an_entry_opened_names_its_installation(self) -> None:
        source, state = _entered(ConsumerScreen.CREDENTIALS)
        beta = installation_key(COORDINATE, OWNERS[2])
        opened = _reload(
            source,
            dataclasses.replace(
                state,
                session=ConsumerSession(ConsumerScreen.USER_INPUT_DETAILS),
                user_inputs_artifact=beta,
            ),
            entering=True,
        )

        self.assertIn(f"{COORDINATE} · opencode · project beta", "\n".join(frame(source, opened)))


if __name__ == "__main__":
    unittest.main()
