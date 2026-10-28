"""What a contract change and a removal are allowed to do to a credential somebody else still uses.

Product Specification 165.19 makes three statements about a version update that alters an input
contract. AART asks only for the *newly* required value rather than re-collecting what it already
has; an authentication-model change is explicit rather than silent; and -- the one this file is
named for -- *old credentials remain if still referenced by other installed artifacts* (INV-232).

That last statement is a negative about a second artifact, which is why no existing test holds it:
every credential test in this repository has exactly one installation in scope, and a claim about
what happens to B when A changes cannot be measured with only an A.

A removal is the other half. Every installation has its own credential items (D-334), so an
uninstall deletes the removed installations' items and cannot reach anybody else's (§208, which
amends INV-185). The command-line claims run through `aart-cli consume uninstall` with a store
standing in for the Keychain, because `commands/marketplace.py` wires the real one on darwin. The
dependant arithmetic is measured where a file-backed provider can stand in.
"""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from aart_cli.application.consumer_session import assemble_consumer_machine
from aart_cli.application.installation_inputs import (
    InstallationInputUse,
    OwnedInputSource,
    compose_installation_inputs,
)
from aart_cli.domain.effects import DeleteCredential
from aart_cli.domain.harness import Scope
from aart_cli.domain.inputs import (
    EnvironmentBinding,
    InputGuidance,
    PersistedConfigValue,
    SecretInput,
    SecretProviderReference,
)
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.receipts import InstalledRecord
from aart_cli.domain.result import Ok
from aart_cli.domain.selection import OwnershipKind, OwnershipReason
from aart_cli.io.configured_installation_action import InstallationHost
from aart_cli.io.configured_uninstall_action import prepare_configured_uninstall
from aart_cli.io.credential_entry import EntryOutcome
from tests.configured_install_command_e2e_test import COORDINATE, _environment
from tests.consumer_session_test import OTHER as SECOND_REFERENCE
from tests.consumer_session_test import TODAY, coordinate, inspection, observed, receipt
from tests.consumer_session_test import TOKEN as SHARED_REFERENCE
from tests.credential_length_e2e_test import AUTHORED as CREDENTIALED
from tests.credential_length_e2e_test import GITHUB as CREDENTIALED_ARTIFACT
from tests.credential_length_e2e_test import _CuttingStore, _OtherWay, _run
from tests.credential_length_e2e_test import _install as _install_with_store
from tests.installation_inputs_test import (
    KEYCHAIN,
    ORG,
    TOKEN,
    _config,
    _owner,
    _secret,
)


def _deletions(prepared) -> list[DeleteCredential]:
    """The credential deletions one prepared removal would carry out."""

    return [effect for effect in prepared.proposal.effects if isinstance(effect, DeleteCredential)]


class RemovalDeletesCredentialsTest(unittest.TestCase):
    """An uninstall takes the removed installations' own credential items with it (§208).

    Each installation has its own items (D-334), so nothing another installation uses is at risk;
    INV-232 holds because no item is shared, not because removals keep them.
    """

    def _installed(self, env) -> None:
        code, payload = env.run("consume", "install", COORDINATE, "--profile", "claude", "--yes")
        self.assertEqual(code, 0, payload)

    def test_the_removal_review_says_which_credentials_go(self) -> None:
        """The reviewed payload says it rather than leaving it to be assumed either way."""

        with _environment() as env:
            self._installed(env)

            code, payload = env.run("consume", "uninstall", COORDINATE, "--profile", "claude")

            self.assertEqual(code, 0, payload)
            self.assertFalse(payload["finalized"])
            # The fixture Skill declares no inputs, so it has nothing to delete, and says so.
            self.assertEqual(payload["review"]["credentials"], {"deleted": []})

    def test_the_human_rendering_says_it_too(self) -> None:
        """The JSON is not what a person reads, and the two renderings can drift apart."""

        with _environment() as env:
            self._installed(env)

            code, text = env.run_text("consume", "uninstall", COORDINATE, "--profile", "claude")

            self.assertEqual(code, 0, text)
            self.assertIn("Credentials deleted with their installations: none.", text)

    def test_consume_uninstall_deletes_the_credential_it_reviewed(self) -> None:
        """Through the public verb, over a store standing in for the Keychain."""

        store = _CuttingStore(cut=1_000)
        entry = _OtherWay(store, EntryOutcome.UNAVAILABLE)
        with _environment(authored=CREDENTIALED) as env:
            _install_with_store(env, store, entry)
            self.assertEqual(len(store.stored), 1, "the install stored no credential")
            named = ("consume", "uninstall", CREDENTIALED_ARTIFACT, "--profile", "claude")

            code, out, _ = _run(env, store, entry, *named)
            payload = json.loads(out)
            self.assertEqual(code, 0, out)
            self.assertEqual(len(store.stored), 1, "reviewing a removal deleted the credential")
            deleted = payload["review"]["credentials"]["deleted"]
            self.assertEqual(len(deleted), 1)
            self.assertTrue(deleted[0].startswith(CREDENTIALED_ARTIFACT), deleted)
            self.assertTrue(deleted[0].endswith(": github-token"), deleted)
            code, text, _ = _run(env, store, entry, *named, as_json=False)
            self.assertIn("Credentials deleted with their installations:\n  - ", text)

            code, out, _ = _run(
                env, store, entry, *named, "--yes", "--expect", payload["review_digest"]
            )

        self.assertEqual(code, 0, out)
        self.assertEqual(store.stored, {})

    def test_a_credential_already_gone_is_not_said_to_be_deleted(self) -> None:
        """The review lists what the removal will do, not every reference the receipt names."""

        store = _CuttingStore(cut=1_000)
        entry = _OtherWay(store, EntryOutcome.UNAVAILABLE)
        with _environment(authored=CREDENTIALED) as env:
            _install_with_store(env, store, entry)
            store.stored.clear()

            code, out, _ = _run(
                env,
                store,
                entry,
                "consume",
                "uninstall",
                CREDENTIALED_ARTIFACT,
                "--profile",
                "claude",
            )

        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["review"]["credentials"], {"deleted": []})

    def test_a_removed_installation_plans_deleting_each_of_its_credentials(self) -> None:
        record = InstalledRecord(coordinate("github"), receipt("github"), ())
        with tempfile.TemporaryDirectory() as raw:
            host = self._host(pathlib.Path(raw).resolve())

            prepared = prepare_configured_uninstall((record,), host=host, policy=EffectivePolicy())

            self.assertIsInstance(prepared, Ok, getattr(prepared, "diagnostics", ()))
            assert isinstance(prepared, Ok)
            self.assertEqual(
                [effect.reference for effect in _deletions(prepared.value)],
                [str(reference) for reference in record.receipt.credentials],
            )
            self.assertTrue(record.receipt.credentials, "the receipt holds no credential to delete")

    def test_an_installation_that_stays_keeps_its_credentials(self) -> None:
        """A Collection giving up its claim on a member something else still owns removes nothing.

        Paired with the record that goes, so the absence is evidence: the same record, owned once
        more, plans the deletion the moment its last owner lets go.
        """

        direct = OwnershipReason(OwnershipKind.DIRECT, "company/mcp/github@1.6.0")
        kit = OwnershipReason(OwnershipKind.COLLECTION, "public/collection/data-scientist@1.0.0")
        kept = InstalledRecord(coordinate("github"), receipt("github"), (direct, kit))
        alone = InstalledRecord(coordinate("github"), receipt("github"), (kit,))
        with tempfile.TemporaryDirectory() as raw:
            host = self._host(pathlib.Path(raw).resolve())

            narrowed = prepare_configured_uninstall(
                (kept,), host=host, policy=EffectivePolicy(), release=(kit,)
            )
            removed = prepare_configured_uninstall(
                (alone,), host=host, policy=EffectivePolicy(), release=(kit,)
            )

            self.assertIsInstance(narrowed, Ok, getattr(narrowed, "diagnostics", ()))
            self.assertIsInstance(removed, Ok, getattr(removed, "diagnostics", ()))
            assert isinstance(narrowed, Ok) and isinstance(removed, Ok)
            self.assertFalse(_deletions(narrowed.value))
            self.assertTrue(_deletions(removed.value))

    @staticmethod
    def _host(root: pathlib.Path) -> InstallationHost:
        for name in ("data", "project", "home"):
            (root / name).mkdir()
        return InstallationHost(
            str(root / "data"),
            str(root / "project"),
            str(root / "home"),
            Scope.PROJECT,
            ("tabnine",),
        )


class SharedCredentialOwnershipTest(unittest.TestCase):
    """INV-232's arithmetic: who still needs this credential once one artifact stops needing it."""

    def test_two_installations_binding_one_reference_are_both_its_dependants(self) -> None:
        machine = assemble_consumer_machine(
            (inspection(), inspection("jira")),
            credentials=(observed(SHARED_REFERENCE),),
            today=TODAY,
        )

        record = next(item for item in machine.credentials if item.input == "github-token")
        self.assertEqual(record.dependants, ("public/mcp/github@1.6.0", "public/mcp/jira@1.6.0"))

    def test_removing_one_of_them_leaves_the_credential_owned_by_the_other(self) -> None:
        """The whole of INV-232 in one comparison: the same credential, one fewer installation.

        Asserted as a *change* rather than as a final state, because "still referenced" is a claim
        about what the removal did not do, and a snapshot of the machine afterwards cannot tell a
        credential that survived from one that was never at risk.
        """

        before = assemble_consumer_machine(
            (inspection(), inspection("jira")),
            credentials=(observed(SHARED_REFERENCE),),
            today=TODAY,
        )
        after = assemble_consumer_machine(
            (inspection("jira"),), credentials=(observed(SHARED_REFERENCE),), today=TODAY
        )

        kept = next(item for item in after.credentials if item.input == "github-token")
        self.assertEqual(len(before.credentials), len(after.credentials))
        self.assertEqual(kept.dependants, ("public/mcp/jira@1.6.0",))
        self.assertEqual(
            kept.health,
            next(item for item in before.credentials if item.input == "github-token").health,
        )

    def test_a_credential_no_installation_names_is_not_thereby_deleted(self) -> None:
        """The end of the same sequence: nothing left references it, and it is still there.

        AART reports that it is owed nothing and offers the removal; it does not take it. The
        distinction is the whole reason `dependants` exists rather than a reference count that
        collects at zero.
        """

        machine = assemble_consumer_machine(
            (inspection(),),
            credentials=(observed(SHARED_REFERENCE), observed(SECOND_REFERENCE)),
            today=TODAY,
        )

        orphan = next(item for item in machine.credentials if item.input == "jira-token")
        self.assertEqual(orphan.dependants, ())
        self.assertIn("delete", orphan.actions)


class ContractMigrationAsksOnlyForWhatIsNewTest(unittest.TestCase):
    """165.19's first two statements, about the version update that changes what an artifact needs.

    Both are read here off `compose_installation_inputs`, which is what decides the form an operator
    is shown. The install command publishes the result as its `unanswered` list, so the seam and the
    verb agree by construction rather than by a second implementation.
    """

    def test_a_value_already_held_is_not_asked_for_again(self) -> None:
        """ "If AART cannot safely map an old config field to a new one, it asks only for the newly
        required value." The premise of that sentence is that the fields it *can* map stay mapped.
        """

        owner = _owner("github")
        upgraded = compose_installation_inputs(
            (
                InstallationInputUse(owner, _config()),
                InstallationInputUse(owner, _secret()),
            ),
            (OwnedInputSource(owner, PersistedConfigValue(ORG, "platform-team")),),
            EffectivePolicy(),
        )

        self.assertIsInstance(upgraded, Ok, getattr(upgraded, "diagnostics", ()))
        assert isinstance(upgraded, Ok)
        self.assertFalse(upgraded.value.ready)
        self.assertEqual([field.input.id for field in upgraded.value.unanswered], [TOKEN])

    def test_a_contract_change_does_not_touch_the_other_installation(self) -> None:
        """ "A contract change must not touch credentials owned by any other installation."

        The artifact that moved to a client secret asks for one. The artifact still on the old
        token keeps the binding and the item it already had, and neither is offered the other's --
        which is the separation §169.4-6 makes the rule and D-353 makes the key. What this replaces
        refused the pair outright, because one field served both owners and could hold only one of
        their two contracts.
        """

        old = _secret()
        new = SecretInput(
            TOKEN,
            EnvironmentBinding("GITHUB_CLIENT_SECRET"),
            guidance=InputGuidance("GitHub client secret", format_hint="opaque secret"),
        )
        moved = _owner("github")
        unchanged = _owner("issues")

        composed = compose_installation_inputs(
            (
                InstallationInputUse(moved, new),
                InstallationInputUse(unchanged, old),
            ),
            (OwnedInputSource(unchanged, SecretProviderReference(TOKEN, KEYCHAIN)),),
            EffectivePolicy(),
        )

        self.assertIsInstance(composed, Ok, getattr(composed, "diagnostics", ()))
        assert isinstance(composed, Ok)
        self.assertEqual(
            (SecretProviderReference(TOKEN, KEYCHAIN),), composed.value.sources_for(unchanged)
        )
        self.assertEqual((), composed.value.sources_for(moved))
        self.assertEqual(
            [(field.owner, field.input.binding.variable) for field in composed.value.unanswered],
            [(moved, "GITHUB_CLIENT_SECRET")],
        )


if __name__ == "__main__":  # pragma: no cover - unittest entry point
    unittest.main()
