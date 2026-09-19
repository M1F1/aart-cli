"""CP-23 task 13: what a credential is and how to get one reaches the moment it is asked for.

An author already declares a secret's human name, purpose, where to obtain it and its format in the
native manifest's `help` (§154, INV-168). All of that survived compilation and promotion, but
installation said only `GitHub token` / `Enter securely during installation` on screen 07 and
nothing at all when the terminal was lent to the provider: the operator met a bare
`password data for new item:` with no idea what to type (`nowe bledy`, QA-081).

These tests hold the whole route, and the words at both ends:

- screen 07 names each credential, what it is for, which artifact needs it, where and how to get
  it, and its format, in Fast;
- the provider's prompt is preceded, on the lent terminal, by the same guidance;
- the CLI's refusal for an unanswered credential carries it too;
- an artifact that says nothing gets an honest fallback (ask its maintainer), never an invented
  link. A manually issued credential can say how to get it without a URL;
- two artifacts sharing a credential keep their owners, and differing help is shown per owner
  instead of refusing the install;
- guidance holding terminal-control characters or an unsafe URL never reaches a terminal.

Every provider here is a recording fake. Nothing reads or writes a real Keychain, and no value is
ever typed.
"""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import io
import json
import os
import unittest
from unittest import mock

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.candidate_validation import (
    ValidationCheck,
    validate_candidate,
)
from aart_cli.application.consumer_views import (
    ConsumerScreen,
    PresentationProfile,
    project_required_inputs,
)
from aart_cli.application.credential_guidance import (
    credential_guidance_lines,
    credential_prompt_briefing,
    gather_credential_guidance,
)
from aart_cli.application.installation_inputs import (
    INPUT_DECLARATION_CONFLICT,
    InstallationInputUse,
    compose_installation_inputs,
)
from aart_cli.domain.credentials import (
    CredentialProviderRef,
    CredentialReference,
    CredentialState,
)
from aart_cli.domain.effects import ReplaceCredential, StoreCredential
from aart_cli.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    InputId,
    SourceAlias,
)
from aart_cli.domain.inputs import (
    BindingExposure,
    EnvironmentBinding,
    InputGuidance,
    ObtainFrom,
    SecretInput,
)
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.result import Err, Ok
from aart_cli.io.consumer_actions import LocalConsumerActions
from aart_cli.io.execution import CredentialEffectInterpreter
from aart_cli.tui import _CursesHandover
from aart_cli.tui_consumer import render_required_inputs
from tests.artifact_installation_e2e_test import MANIFEST, SERVER_SOURCE
from tests.candidate_validation_test import _bundle
from tests.configured_install_command_e2e_test import _environment
from tests.configured_installation_draft_e2e_test import _published_registries
from tests.consumer_application_e2e_test import _actions, _at, _drive
from tests.consumer_shell_test import DOWN, ENTER, SPACE
from tests.credential_action_rows_test import _Provider
from tests.credential_fixtures import credential_url

TOKEN_HELP = {
    "label": "GitHub token",
    "description": "Lets the server read the repositories you choose.",
    "format_hint": "fine-grained personal access token",
    "validation_hint": "Grant read-only access to Contents and Metadata.",
    "obtain_from": {
        "label": "Create a token in GitHub settings",
        "url": "https://github.com/settings/tokens",
    },
}
MANUAL_HELP = {
    "label": "Service token",
    "description": "Authenticates the server to the internal API.",
    "obtain_from": {"label": "Ask the platform team in #platform-access for a service token"},
}
PROVIDER = "macos-keychain"


def _manifest(name: str, help_: dict | None) -> str:
    manifest = copy.deepcopy(MANIFEST)
    manifest["artifact"] = dict(manifest["artifact"], name=name)
    token = {key: value for key, value in manifest["inputs"][0].items() if key != "help"}
    if help_ is not None:
        token["help"] = help_
    manifest["inputs"] = [token]
    return json.dumps(manifest)


def _authored(name: str, help_: dict | None):
    """One author tree: an MCP server declaring a single secret with `help_` as its help."""

    return (
        (f"{name}/aart.json", _manifest(name, help_)),
        (f"{name}/server.py", SERVER_SOURCE),
        (f"{name}/requirements.txt", "# no third-party packages\n"),
    )


def _guidance(help_: dict) -> InputGuidance:
    obtain = help_.get("obtain_from")
    return InputGuidance(
        help_["label"],
        help_.get("description", ""),
        format_hint=help_.get("format_hint"),
        obtain_from=None if obtain is None else ObtainFrom(obtain["label"], obtain.get("url")),
        validation_hint=help_.get("validation_hint", ""),
    )


def _secret(help_: dict | None) -> SecretInput:
    return SecretInput(
        InputId("github-token"),
        EnvironmentBinding("GITHUB_TOKEN"),
        guidance=None if help_ is None else _guidance(help_),
    )


class _Journal:
    """What reached the lent terminal, and in what order relative to the prompt."""

    def __init__(self) -> None:
        self.entries: list[object] = []

    def handover(self, briefing: tuple[str, ...] = ()):
        @contextlib.contextmanager
        def _held():
            self.entries.append(("briefed", briefing))
            try:
                yield
            finally:
                self.entries.append("restored")

        return _held()

    @property
    def briefings(self) -> list[tuple[str, ...]]:
        return [item[1] for item in self.entries if isinstance(item, tuple)]


class _Resolving(_Provider):
    """The task 12 recording provider, plus the launcher argv a plan needs. It reads nothing."""

    def resolution_argv(self, reference):
        return ("/usr/bin/false", str(reference))

    @staticmethod
    def store_exposure(*, interactive: bool) -> BindingExposure:
        return BindingExposure.PRIVATE


# -- the words ---------------------------------------------------------------------------------


class TheGuidanceWordsTest(unittest.TestCase):
    def test_a_guided_credential_says_what_it_is_for_who_needs_it_and_how_to_get_it(self) -> None:
        groups = gather_credential_guidance(
            "github-token", (("company/mcp/github@1.5.0", _guidance(TOKEN_HELP)),)
        )

        lines = credential_guidance_lines(groups)

        self.assertEqual(
            lines,
            (
                "GitHub token — needed by company/mcp/github@1.5.0",
                "  Lets the server read the repositories you choose.",
                "  Get it: Create a token in GitHub settings → https://github.com/settings/tokens",
                "  Format: fine-grained personal access token",
                "  Grant read-only access to Contents and Metadata.",
            ),
        )

    def test_a_manually_issued_credential_is_explained_without_a_link(self) -> None:
        groups = gather_credential_guidance(
            "github-token", (("company/mcp/internal@1.0.0", _guidance(MANUAL_HELP)),)
        )

        lines = credential_guidance_lines(groups)

        self.assertIn(
            "  Get it: Ask the platform team in #platform-access for a service token", lines
        )
        self.assertNotIn("→", "\n".join(lines))
        self.assertNotIn("http", "\n".join(lines))

    def test_an_artifact_that_says_nothing_sends_the_person_to_its_maintainer(self) -> None:
        for help_ in (None, {"label": "GitHub token"}):
            with self.subTest(help=help_):
                groups = gather_credential_guidance(
                    "github-token",
                    (
                        (
                            "company/mcp/github@1.5.0",
                            None if help_ is None else _guidance(help_),
                        ),
                    ),
                )

                drawn = "\n".join(credential_guidance_lines(groups))

                self.assertIn(
                    "Where to get it is not stated; ask the maintainer of "
                    "company/mcp/github@1.5.0.",
                    drawn,
                )
                self.assertNotIn("http", drawn)
                self.assertNotIn("Get it:", drawn)

    def test_owners_that_agree_share_one_explanation(self) -> None:
        guidance = _guidance(TOKEN_HELP)

        groups = gather_credential_guidance(
            "github-token",
            (("company/mcp/b@1.0.0", guidance), ("company/mcp/a@1.0.0", guidance)),
        )

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].owners, ("company/mcp/a@1.0.0", "company/mcp/b@1.0.0"))
        self.assertEqual(
            credential_guidance_lines(groups)[0],
            "GitHub token — needed by company/mcp/a@1.0.0, company/mcp/b@1.0.0",
        )

    def test_owners_that_disagree_each_keep_their_own_instructions(self) -> None:
        groups = gather_credential_guidance(
            "github-token",
            (
                ("company/mcp/a@1.0.0", _guidance(TOKEN_HELP)),
                ("company/mcp/b@1.0.0", _guidance(MANUAL_HELP)),
            ),
        )

        lines = credential_guidance_lines(groups)

        self.assertEqual(
            [group.owners for group in groups], [("company/mcp/a@1.0.0",), ("company/mcp/b@1.0.0",)]
        )
        a = lines.index("GitHub token — needed by company/mcp/a@1.0.0")
        b = lines.index("Service token — needed by company/mcp/b@1.0.0")
        self.assertIn("https://github.com/settings/tokens", "\n".join(lines[a:b]))
        self.assertIn("#platform-access", "\n".join(lines[b:]))

    @given(
        owners=st.lists(
            st.sampled_from(("company/mcp/a@1.0.0", "company/mcp/b@1.0.0", "company/mcp/c@2.0.0")),
            min_size=1,
            max_size=6,
        ),
        helps=st.lists(st.sampled_from((0, 1, 2)), min_size=6, max_size=6),
    )
    def test_no_owner_is_ever_lost_or_repeated(self, owners: list[str], helps: list[int]) -> None:
        choices = (_guidance(TOKEN_HELP), _guidance(MANUAL_HELP), None)
        declared = tuple((owner, choices[helps[index]]) for index, owner in enumerate(owners))

        groups = gather_credential_guidance("github-token", declared)

        named = [owner for group in groups for owner in group.owners]
        self.assertEqual(sorted(set(named)), sorted(named))
        self.assertEqual(set(named), set(owners))

    def test_the_prompt_briefing_says_who_asks_and_that_aart_never_sees_it(self) -> None:
        groups = gather_credential_guidance(
            "github-token", (("company/mcp/github@1.5.0", _guidance(TOKEN_HELP)),)
        )

        stored = credential_prompt_briefing(groups, provider=PROVIDER)
        replaced = credential_prompt_briefing(groups, provider=PROVIDER, replacing=True)

        self.assertEqual(stored[0], "AART needs a credential to continue.")
        self.assertEqual(stored[1:-1], credential_guidance_lines(groups))
        self.assertEqual(
            stored[-1],
            "macos-keychain asks for it next. Type it there; AART never sees or keeps it.",
        )
        self.assertEqual(replaced[0], "AART is replacing a credential.")
        self.assertEqual(
            replaced[-1],
            "macos-keychain asks for the new value next. Type it there; AART never sees or keeps it.",
        )

    def test_screen_07_shows_the_guidance_in_fast_and_the_reference_only_in_verbose(self) -> None:
        views = project_required_inputs(
            (_secret(TOKEN_HELP),),
            declared_by=(("company/mcp/github@1.5.0", _secret(TOKEN_HELP)),),
        )

        fast = render_required_inputs(views, PresentationProfile.FAST)
        verbose = render_required_inputs(views, PresentationProfile.VERBOSE)

        for line in credential_guidance_lines(views[0].guidance):
            self.assertIn(line, fast)
        self.assertIn("  Required", fast)
        self.assertNotIn("Provider reference", "\n".join(fast))
        self.assertIn("  Provider reference: not configured", verbose)

    def test_a_projection_with_no_owners_still_explains_the_credential(self) -> None:
        views = project_required_inputs((_secret(TOKEN_HELP),))

        drawn = render_required_inputs(views, PresentationProfile.FAST)

        self.assertIn("GitHub token", drawn)
        self.assertIn("  Lets the server read the repositories you choose.", drawn)


# -- what may reach a terminal -------------------------------------------------------------------

_UNSAFE = ("\x1b[2J", "\x07", "\x08", "\x9b31m", "‮", "\x00")


class UnsafeGuidanceIsRefusedTest(unittest.TestCase):
    @given(
        field=st.sampled_from(
            ("label", "description", "format_hint", "validation_hint", "obtain_label")
        ),
        unsafe=st.one_of(
            st.sampled_from(_UNSAFE),
            st.characters(categories=("Cc", "Cf")).filter(lambda c: c not in "\r\n"),
        ),
    )
    def test_terminal_control_characters_never_become_guidance(
        self, field: str, unsafe: str
    ) -> None:
        values = {
            "label": "GitHub token",
            "description": "Lets the server read.",
            "format_hint": "token",
            "validation_hint": "Read only.",
            "obtain_label": "GitHub settings",
        }
        values[field] = values[field][:3] + unsafe + values[field][3:]

        with self.assertRaises(ValueError):
            InputGuidance(
                values["label"],
                values["description"],
                format_hint=values["format_hint"],
                obtain_from=ObtainFrom(values["obtain_label"], "https://github.com/settings"),
                validation_hint=values["validation_hint"],
            )

    def test_an_unsafe_acquisition_link_is_refused(self) -> None:
        for url in (
            "javascript:alert(1)",
            "file:///etc/passwd",
            credential_url("github.com", "/settings", user="user", held="pass"),
            "https://github.com/\x1b]8;;https://evil.example\x07",
            "ftp://github.com/tokens",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                ObtainFrom("GitHub settings", url)

    def test_the_author_parser_refuses_them_before_compilation(self) -> None:
        from tests.authoring_inputs_test import TOKEN, _parsed

        for broken in (
            dict(TOKEN, help=dict(TOKEN["help"], description="Read \x1b[2J access.")),
            dict(TOKEN, help=dict(TOKEN["help"], obtain_from={"label": "x", "url": "file:///x"})),
        ):
            with self.subTest(help=broken["help"]):
                self.assertIsInstance(_parsed(inputs=[broken]), Err)

    def test_a_link_is_optional_for_manual_issuance_but_the_instruction_is_not(self) -> None:
        from tests.authoring_inputs_test import TOKEN, _parsed

        manual = _parsed(inputs=[dict(TOKEN, help=MANUAL_HELP)])
        empty = _parsed(inputs=[dict(TOKEN, help=dict(MANUAL_HELP, obtain_from={}))])

        self.assertIsInstance(manual, Ok, getattr(manual, "diagnostics", ()))
        obtain = manual.value.inputs[0].guidance.obtain_from
        self.assertEqual(obtain.url, None)
        self.assertIsInstance(empty, Err)


class AuthorValidationTest(unittest.TestCase):
    def _warnings(self, help_: dict | None) -> tuple[str, ...]:
        token = {"id": "github-token", "kind": "secret", "inject": MANIFEST["inputs"][0]["inject"]}
        if help_ is not None:
            token["help"] = help_
        result = validate_candidate(_bundle(inputs=[token]), policy=EffectivePolicy()).result(
            ValidationCheck.SECRET_METADATA
        )
        return tuple(item.message for item in result.details)

    def test_missing_acquisition_guidance_tells_the_author_what_to_add(self) -> None:
        for help_ in (None, {"label": "GitHub token"}):
            with self.subTest(help=help_):
                self.assertEqual(
                    self._warnings(help_),
                    (
                        "secret input github-token says nothing about where its value is "
                        "obtained; add help.obtain_from with a label, and a url when there is one",
                    ),
                )

    def test_a_manual_instruction_is_acquisition_guidance(self) -> None:
        self.assertEqual(self._warnings(MANUAL_HELP), ())
        self.assertEqual(self._warnings(TOKEN_HELP), ())


# -- the lent terminal ---------------------------------------------------------------------------


def _reference(name: str = "github-token") -> CredentialReference:
    return CredentialReference(InputId(name), CredentialProviderRef(PROVIDER, "aart", name))


class ThePromptIsBriefedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.journal = _Journal()
        self.provider = _Resolving(self.journal)
        self.groups = gather_credential_guidance(
            "github-token", (("company/mcp/github@1.5.0", _guidance(TOKEN_HELP)),)
        )

    def _interpreter(self, guidance=None) -> CredentialEffectInterpreter:
        reference = _reference()
        return CredentialEffectInterpreter(
            self.provider,
            (reference,),
            interactive_store=True,
            terminal_handover=self.journal.handover,
            guidance={str(reference): self.groups} if guidance is None else guidance,
        )

    def test_the_guidance_is_on_the_terminal_before_the_provider_asks(self) -> None:
        applied = self._interpreter().apply(StoreCredential(str(_reference()), PROVIDER))

        self.assertIsInstance(applied, Ok, getattr(applied, "diagnostics", ()))
        self.assertEqual(
            self.journal.entries,
            [
                ("briefed", credential_prompt_briefing(self.groups, provider=PROVIDER)),
                "prompted",
                "restored",
            ],
        )

    def test_a_replacement_is_briefed_as_a_replacement(self) -> None:
        self._interpreter().apply(ReplaceCredential(str(_reference()), PROVIDER))

        self.assertEqual(
            self.journal.briefings,
            [credential_prompt_briefing(self.groups, provider=PROVIDER, replacing=True)],
        )

    def test_a_reference_nobody_described_still_says_who_asks(self) -> None:
        self._interpreter(guidance={}).apply(StoreCredential(str(_reference()), PROVIDER))

        (briefing,) = self.journal.briefings
        self.assertEqual(
            briefing,
            credential_prompt_briefing(
                gather_credential_guidance("github-token", ()), provider=PROVIDER
            ),
        )
        self.assertIn("Where to get it is not stated", "\n".join(briefing))

    def test_verifying_or_removing_briefs_nobody(self) -> None:
        from aart_cli.domain.effects import DeleteCredential, VerifyCredential

        interpreter = self._interpreter()
        interpreter.apply(VerifyCredential(str(_reference()), PROVIDER))
        interpreter.apply(DeleteCredential(str(_reference()), PROVIDER))

        self.assertEqual(self.journal.briefings, [])


class _Curses:
    def __init__(self, journal: list) -> None:
        self._journal = journal

    def def_prog_mode(self):
        self._journal.append("saved")

    def endwin(self):
        self._journal.append("ended")

    def reset_prog_mode(self):
        self._journal.append("reset")


class _Screen:
    def __init__(self, journal: list) -> None:
        self._journal = journal

    def clear(self):
        self._journal.append("cleared")

    def refresh(self):
        self._journal.append("refreshed")


class CursesHandoverBriefingTest(unittest.TestCase):
    def _lend(self, briefing: tuple[str, ...], *, columns: int = 80) -> tuple[list, str]:
        journal: list = []
        stream = io.StringIO()
        loan = _CursesHandover(stream=stream, columns=lambda: columns)
        loan.bind(_Screen(journal))
        with mock.patch.dict("sys.modules", {"curses": _Curses(journal)}):
            with loan(briefing):
                journal.append(("prompt sees", stream.getvalue()))
        return journal, stream.getvalue()

    def test_the_briefing_is_written_after_the_screen_is_released_and_before_the_prompt(
        self,
    ) -> None:
        briefing = credential_prompt_briefing(
            gather_credential_guidance(
                "github-token", (("company/mcp/github@1.5.0", _guidance(TOKEN_HELP)),)
            ),
            provider=PROVIDER,
        )

        journal, written = self._lend(briefing, columns=200)

        self.assertEqual(journal[:2], ["saved", "ended"])
        self.assertEqual(journal[2], ("prompt sees", written))
        for line in briefing:
            self.assertIn(line, written)

    def test_a_narrow_terminal_wraps_the_words_but_never_breaks_the_link(self) -> None:
        briefing = credential_prompt_briefing(
            gather_credential_guidance(
                "github-token", (("company/mcp/github@1.5.0", _guidance(TOKEN_HELP)),)
            ),
            provider=PROVIDER,
        )

        _, written = self._lend(briefing, columns=30)

        # The link is longer than the terminal is wide, so only refusing to break it keeps it whole.
        self.assertGreater(len("https://github.com/settings/tokens"), 30)
        self.assertIn("https://github.com/settings/tokens", written.split())
        for line in written.splitlines():
            if "https://" not in line:
                self.assertLessEqual(len(line), 30, line)

    def test_an_unbound_loan_still_tells_the_person_what_to_type(self) -> None:
        stream = io.StringIO()
        loan = _CursesHandover(stream=stream, columns=lambda: 80)

        with loan(("AART needs a credential to continue.",)):
            pass

        self.assertEqual(stream.getvalue(), "AART needs a credential to continue.\n")


def _owner(name: str) -> ArtifactCoordinate:
    return ArtifactCoordinate(SourceAlias("company"), ArtifactIdentity("mcp", name), "1.0.0")


class SharedDeclarationsTest(unittest.TestCase):
    def _compose(self, first: SecretInput, second: SecretInput):
        return compose_installation_inputs(
            (
                InstallationInputUse(_owner("a"), first),
                InstallationInputUse(_owner("b"), second),
            ),
            (),
            EffectivePolicy(),
        )

    def test_differing_help_is_not_a_conflict_and_each_owner_keeps_theirs(self) -> None:
        composed = self._compose(_secret(TOKEN_HELP), _secret(MANUAL_HELP))

        self.assertIsInstance(composed, Ok, getattr(composed, "diagnostics", ()))
        (view,) = composed.value.views()
        self.assertEqual(
            [group.owners for group in view.guidance],
            [("company/mcp/a@1.0.0",), ("company/mcp/b@1.0.0",)],
        )

    def test_a_different_delivery_is_still_a_conflict(self) -> None:
        other = dataclasses.replace(_secret(TOKEN_HELP), binding=EnvironmentBinding("GH_TOKEN"))

        composed = self._compose(_secret(TOKEN_HELP), other)

        self.assertIsInstance(composed, Err)
        self.assertEqual(composed.diagnostics[0].code, INPUT_DECLARATION_CONFLICT)


# -- Source to Registry to installation ------------------------------------------------------


def _install(*trees, present: CredentialState = CredentialState.ABSENT, keys=None):
    """Install through the shell from a registry that approved each author tree in turn."""

    journal = _Journal()
    provider = _Resolving(journal)
    provider.present = present
    with (
        mock.patch(
            "tests.configured_install_command_e2e_test._published_registry",
            lambda _authored, **kwargs: _published_registries(*trees, **kwargs),
        ),
        _environment() as env,
    ):
        with mock.patch.dict(os.environ, env.xdg, clear=False):
            base = _actions(env)
            actions = LocalConsumerActions(
                dataclasses.replace(base._context, credential_providers=(provider,)),
                terminal_handover=journal.handover,
            )
        _, terminal, _ = _drive(
            env,
            _at(ConsumerScreen.MARKETPLACE),
            *(keys or (SPACE, ord("i"), SPACE, ENTER, ENTER, ENTER, ENTER)),
            actions=actions,
        )
    return terminal, journal, provider


def _screen_07(terminal) -> str:
    return next(
        "\n".join(frame)
        for frame in terminal.frames
        if any("A few things are needed before installation" in line for line in frame)
    )


class SourceToPromptE2ETest(unittest.TestCase):
    """Real compile, scan, assess, promote and publish; the installation reads what was approved."""

    def test_authored_guidance_is_on_screen_07_and_on_the_terminal_before_the_prompt(
        self,
    ) -> None:
        terminal, journal, provider = _install(_authored("github", TOKEN_HELP))

        drawn = _screen_07(terminal)
        expected = gather_credential_guidance(
            "github-token", (("company/mcp/github@1.5.0", _guidance(TOKEN_HELP)),)
        )
        for line in credential_guidance_lines(expected):
            self.assertIn(line, drawn)
        briefed = next(i for i, item in enumerate(journal.entries) if isinstance(item, tuple))
        self.assertEqual(journal.entries[briefed + 1 : briefed + 3], ["prompted", "restored"])
        self.assertEqual(
            journal.briefings, [credential_prompt_briefing(expected, provider=PROVIDER)]
        )
        self.assertEqual(provider.stored, [(None, False)])
        self.assertTrue(terminal.screen_containing("✓ credential:github-token"))

    def test_an_unguided_artifact_falls_back_honestly_on_both(self) -> None:
        terminal, journal, _ = _install(_authored("github", None))

        fallback = "Where to get it is not stated; ask the maintainer of company/mcp/github@1.5.0."
        self.assertIn(fallback, _screen_07(terminal))
        self.assertIn("  " + fallback, journal.briefings[0])
        self.assertNotIn("http", "\n".join(journal.briefings[0]))

    def test_a_credential_already_stored_is_not_asked_for_again(self) -> None:
        terminal, journal, provider = _install(
            _authored("github", TOKEN_HELP), present=CredentialState.PRESENT
        )

        self.assertEqual(journal.briefings, [])
        self.assertEqual(provider.stored, [])

    def test_two_artifacts_sharing_a_credential_are_asked_once_with_both_owners(self) -> None:
        terminal, journal, provider = _install(
            _authored("alpha", TOKEN_HELP),
            _authored("beta", MANUAL_HELP),
            keys=(SPACE, DOWN, SPACE, ord("i"), SPACE, ENTER, ENTER, ENTER, ENTER),
        )

        drawn = _screen_07(terminal)
        self.assertIn("GitHub token — needed by company/mcp/alpha@1.5.0", drawn)
        self.assertIn("Service token — needed by company/mcp/beta@1.5.0", drawn)
        self.assertEqual(provider.stored, [(None, False)])
        (briefing,) = journal.briefings
        self.assertIn("GitHub token — needed by company/mcp/alpha@1.5.0", briefing)
        self.assertIn("Service token — needed by company/mcp/beta@1.5.0", briefing)

    def test_no_frame_or_briefing_holds_anything_credential_shaped(self) -> None:
        from aart_cli.redaction import contains_credential_shape

        terminal, journal, _ = _install(_authored("github", TOKEN_HELP))

        for frame in terminal.frames:
            self.assertFalse(contains_credential_shape("\n".join(frame)))
        for briefing in journal.briefings:
            self.assertFalse(contains_credential_shape("\n".join(briefing)))


class CommandLineGuidanceE2ETest(unittest.TestCase):
    def test_an_unanswered_credential_is_explained_by_the_cli_too(self) -> None:
        journal = _Journal()
        with (
            _environment(authored=_authored("github", TOKEN_HELP)) as env,
            mock.patch(
                "aart_cli.commands.marketplace.MacOsKeychainProvider",
                lambda: _Resolving(journal),
            ),
        ):
            text_code, text = env.run_text(
                "marketplace", "install", "company/mcp/github", "--profile", "claude"
            )
            json_code, payload = env.run(
                "marketplace", "install", "company/mcp/github", "--profile", "claude"
            )

        expected = gather_credential_guidance(
            "github-token", (("company/mcp/github@1.5.0", _guidance(TOKEN_HELP)),)
        )
        self.assertNotEqual(text_code, 0)
        for line in credential_guidance_lines(expected):
            self.assertIn(line, text)
        self.assertNotEqual(json_code, 0)
        self.assertEqual(
            payload["inputs"][0]["guidance"],
            [
                {
                    "owners": ["company/mcp/github@1.5.0"],
                    "label": "GitHub token",
                    "description": "Lets the server read the repositories you choose.",
                    "obtain_from": {
                        "label": "Create a token in GitHub settings",
                        "url": "https://github.com/settings/tokens",
                    },
                    "format_hint": "fine-grained personal access token",
                    "validation_hint": "Grant read-only access to Contents and Metadata.",
                }
            ],
        )
        self.assertNotIn("prompted", journal.entries)


if __name__ == "__main__":
    unittest.main()
