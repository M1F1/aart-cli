"""§173.6: Installed, Doctor and uninstall show an installed Collection as one row, members under it.

The Registry approved two artifacts and a Collection naming both. Installed draws the Collection,
then its member installations under it. Doctor does the same, and a member that drifted is named
on the Collection's line (INV-186). Uninstalling the Collection, from the TUI or with
`marketplace uninstall`, removes every member installation it owns in one review. A member that is
also installed directly stays, and only the Collection's claim on it is given up (INV-215).
"""

from __future__ import annotations

import contextlib
import os
import unittest
from unittest import mock

from aart_cli.application.consumer_ui import ConsumerUiState
from aart_cli.application.consumer_views import ConsumerScreen, ConsumerSession, offer_cells
from aart_cli.domain.installation_owner import compose_installation_key
from aart_cli.domain.result import Ok
from aart_cli.domain.selection import OwnershipKind
from aart_cli.io.receipt_store import LocalReceiptStore
from aart_cli.tui_consumer import run_consumer_shell
from tests.collection_install_tui_e2e_test import STARTER, _with_starter
from tests.configured_install_command_e2e_test import _environment
from tests.consumer_application_e2e_test import _actions, _Terminal
from tests.consumer_shell_test import ENTER

DUMMY = "company/mcp/dummy@1.0.0"
REVIEW = "company/skill/code-review@1.2.0"


@contextlib.contextmanager
def _starter_registry():
    with (
        mock.patch("tests.configured_install_command_e2e_test._published_registry", _with_starter),
        _environment() as env,
    ):
        yield env


def _install(env, coordinate: str, *harnesses: str) -> None:
    profiles = (item for harness in harnesses for item in ("--profile", harness))
    code, payload = env.run("consume", "install", coordinate, *profiles, "--yes")
    assert code == 0, payload


def _skill(env, harness: str = "claude"):
    return env.project / f".{harness}/skills/code-review-company-project/SKILL.md"


def _records(env) -> dict[str, tuple[OwnershipKind, ...]]:
    stored = LocalReceiptStore(str(env.paths.data_root) + "/state").installations()
    assert isinstance(stored, Ok), getattr(stored, "diagnostics", ())
    return {
        f"{item.receipt.owner.artifact}#{item.receipt.owner.harness}": tuple(
            reason.kind for reason in item.ownership
        )
        for item in stored.value
    }


def _walk(env, screen: ConsumerScreen, *codes: int):
    handler = _actions(env)
    terminal = _Terminal(*codes)
    with mock.patch.dict(os.environ, env.xdg, clear=False):
        source = handler.source()
        empty = ConsumerUiState(ConsumerSession(screen))
        state = ConsumerUiState(ConsumerSession(screen), rows=source.rows(empty))
        finished = run_consumer_shell(source, terminal, state=state, action_handler=handler)
    return finished, terminal


class InstalledCollectionTest(unittest.TestCase):
    def test_installed_draws_the_collection_then_its_members_under_it(self) -> None:
        with _starter_registry() as env:
            _install(env, STARTER, "claude", "opencode")

            finished, terminal = _walk(env, ConsumerScreen.INSTALLED)

        self.assertEqual(
            finished.rows,
            (
                STARTER,
                *(
                    compose_installation_key(coordinate, harness, "project", str(env.project))
                    for coordinate in (DUMMY, REVIEW)
                    for harness in ("claude", "opencode")
                ),
            ),
        )
        lines = terminal.last.splitlines()
        # §199: the row names the artifact as `name@version`; the Type and Harness columns say the rest.
        starter, dummy = offer_cells(STARTER)[0], offer_cells(DUMMY)[0]
        (collection,) = (line for line in lines if starter in line)
        (member,) = (line for line in lines if dummy in line and "claude" in line)
        self.assertIn("Collection", collection)
        self.assertGreater(
            member.index(dummy), collection.index(starter), "a member is not drawn under it"
        )

    def test_doctor_draws_the_collection_and_names_the_member_that_needs_attention(self) -> None:
        with _starter_registry() as env:
            _install(env, STARTER, "claude")
            _skill(env).parent.chmod(0o755)
            _skill(env).unlink()

            _, terminal = _walk(env, ConsumerScreen.DOCTOR)
            code, text = env.run_text("doctor")

        for drawn in (terminal.last, text):
            with self.subTest(drawn=drawn[:40]):
                lines = drawn.splitlines()
                (collection,) = (line for line in lines if STARTER in line)
                self.assertIn(f"{REVIEW} · claude · project project", collection)
                (member,) = (
                    line for line in lines if f"{DUMMY} · claude" in line and STARTER not in line
                )
                self.assertGreater(member.index(DUMMY), collection.index(STARTER))
        self.assertEqual(code, 1)


class CollectionUninstallTest(unittest.TestCase):
    def test_u_on_the_collection_removes_every_member_installation_in_one_review(self) -> None:
        with _starter_registry() as env:
            _install(env, STARTER, "claude", "opencode")

            finished, terminal = _walk(env, ConsumerScreen.INSTALLED, ord("u"), ENTER)

            review = terminal.screen_containing("/ Uninstall Review")
            records = _records(env)
            delivered = [_skill(env, harness).exists() for harness in ("claude", "opencode")]

        self.assertIn("for 4 artifacts", review)
        for harness in ("claude", "opencode"):
            self.assertIn(f"delivery:{harness}", review)
            self.assertIn(f"harness:{harness}", review)
        self.assertEqual(finished.session.screen, ConsumerScreen.ACTIVITY_DETAILS, terminal.last)
        self.assertEqual(records, {})
        self.assertEqual(delivered, [False, False])

    def test_a_member_also_installed_directly_stays_with_only_its_own_claim(self) -> None:
        with _starter_registry() as env:
            _install(env, DUMMY, "claude")
            _install(env, STARTER, "claude")
            self.assertEqual(
                set(_records(env)[f"{DUMMY.split('@')[0]}#claude".replace("company/", "")]),
                {OwnershipKind.DIRECT, OwnershipKind.COLLECTION},
            )

            finished, terminal = _walk(env, ConsumerScreen.INSTALLED, ord("u"), ENTER)
            records = _records(env)

        self.assertEqual(finished.session.screen, ConsumerScreen.ACTIVITY_DETAILS, terminal.last)
        self.assertEqual(records, {"mcp/dummy#claude": (OwnershipKind.DIRECT,)})

    def test_marketplace_uninstall_takes_a_collection_coordinate(self) -> None:
        with _starter_registry() as env:
            _install(env, DUMMY, "claude")
            _install(env, STARTER, "claude")

            reviewed, review = env.run("consume", "uninstall", STARTER, "--profile", "claude")
            code, payload = env.run("consume", "uninstall", STARTER, "--profile", "claude", "--yes")
            records = _records(env)
            delivered = _skill(env).exists()

        self.assertEqual(reviewed, 0, review)
        self.assertFalse(review["finalized"])
        self.assertEqual(code, 0, payload)
        self.assertEqual(records, {"mcp/dummy#claude": (OwnershipKind.DIRECT,)})
        self.assertFalse(delivered)

    def test_a_collection_is_not_uninstalled_together_with_artifacts(self) -> None:
        with _starter_registry() as env:
            _install(env, STARTER, "claude")

            code, payload = env.run("consume", "uninstall", STARTER, DUMMY, "--profile", "claude")
            records = _records(env)

        self.assertNotEqual(code, 0, payload)
        self.assertIn("Collection", str(payload))
        self.assertEqual(len(records), 2)


if __name__ == "__main__":
    unittest.main()
