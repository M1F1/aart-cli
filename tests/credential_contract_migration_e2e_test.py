"""What a contract change and a removal are allowed to do to a credential somebody else still uses.

Product Specification 165.19 makes three statements about a version update that alters an input
contract. AART asks only for the *newly* required value rather than re-collecting what it already
has; an authentication-model change is explicit rather than silent; and -- the one this file is
named for -- *old credentials remain if still referenced by other installed artifacts* (INV-232).

That last statement is a negative about a second artifact, which is why no existing test holds it:
every credential test in this repository has exactly one installation in scope, and a claim about
what happens to B when A changes cannot be measured with only an A.

Two of the claims here run through the public verb and two run at the seam, and the split is not a
convenience. `commands/marketplace.py` wires a real `MacOsKeychainProvider` on darwin, so a
command-line test that actually stored a credential would write into the developer's own Keychain.
The retention statement needs no credential to exist -- the removal review makes it either way --
so it is driven through `aart marketplace uninstall`. The dependant arithmetic does need one, so it
is measured where a file-backed provider can stand in, the same route every existing credential
test takes.
"""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from agent_artifacts.application.consumer_session import assemble_consumer_machine
from agent_artifacts.application.installation_inputs import (
    INPUT_DECLARATION_CONFLICT,
    InstallationInputUse,
    compose_installation_inputs,
)
from agent_artifacts.domain.effects import DeleteCredential
from agent_artifacts.domain.harness import Scope
from agent_artifacts.domain.inputs import (
    EnvironmentBinding,
    InputGuidance,
    PersistedConfigValue,
    SecretInput,
    SecretProviderReference,
)
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.receipts import InstalledRecord
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.configured_installation_action import InstallationHost
from agent_artifacts.io.configured_uninstall_action import prepare_configured_uninstall
from tests.configured_install_command_e2e_test import COORDINATE, _environment
from tests.consumer_session_test import OTHER as SECOND_REFERENCE
from tests.consumer_session_test import TODAY, coordinate, inspection, observed, receipt
from tests.consumer_session_test import TOKEN as SHARED_REFERENCE
from tests.installation_inputs_test import KEYCHAIN, ORG, TOKEN, _config, _coordinate, _secret


def _deletions(prepared) -> list[DeleteCredential]:
    """The credential deletions one prepared removal would carry out."""

    return [effect for effect in prepared.proposal.effects if isinstance(effect, DeleteCredential)]


class RemovalRetainsCredentialsTest(unittest.TestCase):
    """`aart marketplace uninstall` over a real machine, through the public verb."""

    def _installed(self, env) -> None:
        code, payload = env.run(
            "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
        )
        self.assertEqual(code, 0, payload)

    def test_the_removal_review_says_credentials_are_retained(self) -> None:
        """165.19 read from the other end: a removal is not a credential revocation.

        The reviewed payload has to say so rather than merely not mention it. A reader deciding
        whether to keep a token they also use elsewhere gets no help from silence, and the natural
        assumption about an uninstall is the wrong one.
        """

        with _environment() as env:
            self._installed(env)

            code, payload = env.run("marketplace", "uninstall", COORDINATE, "--profile", "claude")

            self.assertEqual(code, 0, payload)
            self.assertFalse(payload["finalized"])
            self.assertEqual(payload["review"]["credentials"], "retained")

    def test_the_human_rendering_says_it_too(self) -> None:
        """The JSON is not what a person reads, and the two renderings can drift apart."""

        with _environment() as env:
            self._installed(env)

            code, text = env.run_text("marketplace", "uninstall", COORDINATE, "--profile", "claude")

            self.assertEqual(code, 0, text)
            self.assertIn("Credentials: retained.", text)

    def test_the_call_the_command_makes_plans_no_credential_deletion(self) -> None:
        """The statement and the plan have to agree, measured where a credential actually exists.

        This is the seam rather than the command, and deliberately: the fixture registry's Skill
        declares no inputs, so asserting "no credential was deleted" through the CLI asserts an
        absence in a scenario where nothing could have been present. The first draft of this test
        did exactly that and stayed green with credential deletion switched on by default.

        So the record here carries a credential reference, and the two calls differ in one keyword.
        The first is the call `commands/marketplace.py` makes -- it passes no `delete_credentials`
        at all -- and the second is what the same function does when asked. The pair is the point:
        the absence in the first is only evidence because the second shows it was reachable.
        """

        record = InstalledRecord(coordinate("github"), receipt("github"), ())
        with tempfile.TemporaryDirectory() as raw:
            host = self._host(pathlib.Path(raw).resolve())

            kept = prepare_configured_uninstall((record,), host=host, policy=EffectivePolicy())
            asked = prepare_configured_uninstall(
                (record,), host=host, policy=EffectivePolicy(), delete_credentials=True
            )

            self.assertIsInstance(kept, Ok, getattr(kept, "diagnostics", ()))
            self.assertIsInstance(asked, Ok, getattr(asked, "diagnostics", ()))
            assert isinstance(kept, Ok) and isinstance(asked, Ok)
            self.assertTrue(_deletions(asked.value), "the deletion was never reachable")
            self.assertFalse(_deletions(kept.value))

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

        upgraded = compose_installation_inputs(
            (
                InstallationInputUse(_coordinate("github"), _config()),
                InstallationInputUse(_coordinate("github"), _secret()),
            ),
            (PersistedConfigValue(ORG, "platform-team"),),
            EffectivePolicy(),
        )

        self.assertIsInstance(upgraded, Ok, getattr(upgraded, "diagnostics", ()))
        assert isinstance(upgraded, Ok)
        self.assertFalse(upgraded.value.ready)
        self.assertEqual([field.input.id for field in upgraded.value.unanswered], [TOKEN])

    def test_an_authentication_model_change_is_refused_rather_than_resolved_quietly(self) -> None:
        """An artifact that redeclares an input another installation still binds differently.

        165.19 requires the change to be explicit. The refusal names both owners, which is what
        makes it explicit rather than merely loud: an operator has to know which other artifact is
        holding the old contract before they can decide anything.
        """

        old = _secret()
        new = SecretInput(
            TOKEN,
            EnvironmentBinding("GITHUB_CLIENT_SECRET"),
            guidance=InputGuidance("GitHub client secret", format_hint="opaque secret"),
        )

        composed = compose_installation_inputs(
            (
                InstallationInputUse(_coordinate("github"), new),
                InstallationInputUse(_coordinate("issues"), old),
            ),
            (SecretProviderReference(TOKEN, KEYCHAIN),),
            EffectivePolicy(),
        )

        self.assertIsInstance(composed, Err)
        assert isinstance(composed, Err)
        self.assertEqual(composed.diagnostics[0].code, INPUT_DECLARATION_CONFLICT)
        message = composed.diagnostics[0].message
        self.assertIn("company/mcp/github@1.0.0", message)
        self.assertIn("company/mcp/issues@1.0.0", message)


if __name__ == "__main__":  # pragma: no cover - unittest entry point
    unittest.main()
