"""§197, INV-298: an artifact points to its own documentation, and every explanation of it does too.

The owner asked for one optional manifest field, `artifact.documentation`, for what a summary and an
input's `help` have no room for: a longer manual, how to obtain a credential, how to configure the
artifact. It is approved with the package, and shown whole wherever the artifact or one of its
inputs is explained: Marketplace's More info, screen 07, the lent terminal, Credentials and
variables, and the CLI's listing, review, refusal and result. No surface ever shows a link the
artifact did not declare, and none shows a link that could carry a credential.
"""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import datetime as dt
import io
import json
import os
import re
import unittest
from unittest import mock

from hypothesis import given
from hypothesis import strategies as st

from aart_cli import cli, tui
from aart_cli.application.consumer_ui import InstallationConfigDraft, InstallationConfigField
from aart_cli.application.consumer_views import PresentationProfile, project_required_inputs
from aart_cli.application.credential_guidance import (
    credential_guidance_lines,
    gather_credential_guidance,
)
from aart_cli.domain.inputs import (
    ConfigInput,
    EnvironmentBinding,
    InputGuidance,
    InputId,
    ObtainFrom,
    SecretInput,
    documentation_url,
    documented,
)
from aart_cli.domain.install_description import InstallDescription
from aart_cli.domain.result import Err, Ok
from aart_cli.protocol.authoring import describe_installation
from aart_cli.protocol.json import canonical_json_bytes
from aart_cli.protocol.native_schema import artifact_manifest_to_json, parse_artifact_manifest
from aart_cli.tui_consumer import (
    MarketplaceEntry,
    artifact_user_inputs_status,
    configuration_value_status,
    render_installation_config_form,
    render_required_inputs,
    render_user_inputs_area,
)
from aart_cli.tui_layout import CONTENT_MEASURE
from aart_cli.tui_marketplace_detail import artifact_disclosure
from tests.artifact_installation_e2e_test import MANIFEST, SERVER_SOURCE
from tests.authoring_inputs_test import _parsed
from tests.credential_fixtures import access_token, assignment, credential_url
from tests.credential_guidance_test import _Journal, _Resolving
from tests.marketplace_cursor_description_test import _distinct
from tests.native_protocol_schema_test import _artifact_document

DOCS = "https://wiki.example.com/display/PLATFORM/GitHub+MCP?pageId=4711#credentials"

_LABEL = st.from_regex(r"[a-z][a-z0-9-]{0,12}", fullmatch=True)
_SEGMENT = st.from_regex(r"[A-Za-z0-9._~+-]{1,12}", fullmatch=True)
#: Plain documentation links of every shape a wiki gives: a host, a port, a path, a page id in the
#: query and a section in the fragment.
_LINKS = st.builds(
    lambda scheme, labels, port, path, page, section: (
        f"{scheme}://{'.'.join(labels)}{port}/{'/'.join(path)}{page}{section}"
    ),
    st.sampled_from(("https", "http")),
    st.lists(_LABEL, min_size=2, max_size=4),
    st.sampled_from(("", ":8443")),
    st.lists(_SEGMENT, max_size=8),
    st.sampled_from(("", "?pageId=4711", "?view=full&lang=en")),
    st.sampled_from(("", "#setup", "#obtaining-a-token")),
)


def _mcp(name: str = "github", documentation: str | None = DOCS) -> tuple[tuple[str, str], ...]:
    """An MCP server declaring a credential and a configuration value, documented or not."""

    manifest = copy.deepcopy(MANIFEST)
    manifest["artifact"] = dict(manifest["artifact"], name=name)
    # No default, so the configuration value is unanswered too and the CLI has to explain it.
    for item in manifest["inputs"]:
        item.pop("default", None)
    if documentation is not None:
        manifest["artifact"]["documentation"] = documentation
    return (
        (f"{name}/aart-cli.json", json.dumps(manifest)),
        (f"{name}/server.py", SERVER_SOURCE),
        (f"{name}/requirements.txt", "# no third-party packages\n"),
    )


class TheLinkRuleTest(unittest.TestCase):
    @given(_LINKS)
    def test_every_plain_documentation_link_is_accepted_as_written(self, link: str) -> None:
        self.assertEqual(documentation_url(link), link)

    @given(
        _LINKS,
        st.sampled_from(
            (
                lambda link: link.replace("://", "://user@", 1),
                lambda link: link.replace("http", "ftp", 1),
                lambda link: link + " more",
                lambda link: link + "\x1b[2J",
                lambda link: link + "‮",
                lambda link: link + "\n",
                lambda link: " " + link,
                lambda link: link.partition("://")[2],
                lambda link: f"{link}{'&' if '?' in link else '?'}{assignment('token', 'abc123')}",
                lambda link: f"{link}/{access_token()}",
                lambda link: credential_url("wiki.example.com", "/page"),
            )
        ),
    )
    def test_a_link_that_is_not_plain_or_could_carry_a_credential_is_refused(
        self, link: str, spoil
    ) -> None:
        with self.assertRaises(ValueError):
            documentation_url(spoil(link))

    def test_a_link_longer_than_any_url_a_terminal_takes_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            documentation_url("https://wiki.example.com/" + "a" * 2048)


class TheManifestDeclaresItTest(unittest.TestCase):
    def test_the_author_manifest_reads_it_and_an_absent_one_is_none(self) -> None:
        documented_ = _parsed(artifact={"name": "github-mcp", "kind": "mcp", "documentation": DOCS})
        plain = _parsed()

        self.assertIsInstance(documented_, Ok, documented_)
        self.assertEqual(documented_.value.documentation, DOCS)
        self.assertIsNone(plain.value.documentation)

    def test_an_unsafe_author_link_is_refused_naming_the_field(self) -> None:
        for link in (credential_url("wiki.example.com"), "javascript:alert(1)", 7):
            with self.subTest(link=link):
                parsed = _parsed(
                    artifact={"name": "github-mcp", "kind": "mcp", "documentation": link}
                )

                self.assertIsInstance(parsed, Err)
                self.assertIn("artifact.documentation", parsed.diagnostics[0].message)

    @given(_LINKS)
    def test_the_approved_manifest_carries_it_through_a_round_trip(self, link: str) -> None:
        document = _artifact_document("skill", "aart-cli-skill-v1", documentation=link)

        parsed = parse_artifact_manifest(json.dumps(document))

        self.assertIsInstance(parsed, Ok, parsed)
        self.assertEqual(parsed.value.documentation, link)
        again = parse_artifact_manifest(
            canonical_json_bytes(artifact_manifest_to_json(parsed.value))
        )
        self.assertEqual(again.value, parsed.value)

    def test_an_undocumented_manifest_serializes_exactly_as_before(self) -> None:
        """No key, so every artifact already approved keeps its manifest digest."""

        parsed = parse_artifact_manifest(
            json.dumps(_artifact_document("skill", "aart-cli-skill-v1"))
        )

        self.assertNotIn(
            b"documentation", canonical_json_bytes(artifact_manifest_to_json(parsed.value))
        )

    def test_an_unsafe_approved_link_is_refused_on_reading(self) -> None:
        document = _artifact_document(
            "skill", "aart-cli-skill-v1", documentation=credential_url("wiki.example.com")
        )

        self.assertIsInstance(parse_artifact_manifest(json.dumps(document)), Err)


class EveryInputCarriesItTest(unittest.TestCase):
    def test_each_declared_input_is_explained_with_its_artifacts_link(self) -> None:
        parsed = _parsed(artifact={"name": "github-mcp", "kind": "mcp", "documentation": DOCS})

        described = describe_installation(parsed.value)

        self.assertEqual(described.documentation, DOCS)
        self.assertTrue(described.inputs)
        for item in described.inputs:
            self.assertEqual(item.guidance.documentation, DOCS)

    @given(st.booleans(), st.one_of(st.none(), _LINKS))
    def test_documenting_changes_nothing_but_the_link(self, guided: bool, link) -> None:
        guidance = InputGuidance("GitHub token", "Reads repositories.") if guided else None
        item = SecretInput(
            InputId("github-token"), EnvironmentBinding("GITHUB_TOKEN"), guidance=guidance
        )

        result = documented(item, link)

        if link is None:
            self.assertIs(result, item)
            return
        self.assertEqual(result.guidance.documentation, link)
        self.assertEqual(
            dataclasses.replace(result.guidance, documentation=None),
            guidance or InputGuidance("github-token"),
        )
        self.assertEqual(
            (result.id, result.binding, result.required), (item.id, item.binding, item.required)
        )

    def test_an_install_description_refuses_an_unsafe_link(self) -> None:
        with self.assertRaises(ValueError):
            InstallDescription(documentation=credential_url("wiki.example.com"))


def _secret(link: str | None, obtain: ObtainFrom | None = None) -> SecretInput:
    return documented(
        SecretInput(
            InputId("github-token"),
            EnvironmentBinding("GITHUB_TOKEN"),
            guidance=InputGuidance("GitHub token", obtain_from=obtain),
        ),
        link,
    )


def _config(link: str | None) -> ConfigInput:
    return documented(
        ConfigInput(
            InputId("github-org"),
            EnvironmentBinding("GITHUB_ORG"),
            guidance=InputGuidance("GitHub organisation", example="acme"),
        ),
        link,
    )


class TheWordsTest(unittest.TestCase):
    def test_a_credential_names_its_documentation_after_how_to_get_it(self) -> None:
        guided = gather_credential_guidance(
            "github-token",
            (("company/mcp/github@1.5.0", _secret(DOCS, ObtainFrom("Create a token")).guidance),),
        )

        lines = credential_guidance_lines(guided)

        self.assertIn("  Get it: Create a token", lines)
        self.assertEqual(lines[-1], f"  Documentation: {DOCS}")

    def test_a_credential_that_does_not_say_where_to_get_it_points_to_the_documentation(
        self,
    ) -> None:
        lines = credential_guidance_lines(
            gather_credential_guidance(
                "github-token", (("company/mcp/github@1.5.0", _secret(DOCS).guidance),)
            )
        )

        self.assertIn("  Where to get it is not stated here; see the documentation.", lines)
        self.assertNotIn("maintainer", "\n".join(lines))

    def test_an_undocumented_credential_keeps_the_honest_fallback(self) -> None:
        lines = credential_guidance_lines(
            gather_credential_guidance(
                "github-token", (("company/mcp/github@1.5.0", _secret(None).guidance),)
            )
        )

        self.assertNotIn("Documentation", "\n".join(lines))
        self.assertIn("ask the maintainer of company/mcp/github@1.5.0", "\n".join(lines))

    def test_owners_with_different_documentation_each_keep_their_own(self) -> None:
        other = "https://wiki.example.com/other"
        groups = gather_credential_guidance(
            "github-token",
            (
                ("company/mcp/alpha@1.0.0", _secret(DOCS).guidance),
                ("company/mcp/beta@1.0.0", _secret(other).guidance),
            ),
        )

        self.assertEqual([group.documentation for group in groups], [DOCS, other])

    def test_screen_07_shows_it_beside_a_configuration_value_and_a_credential(self) -> None:
        views = project_required_inputs((_secret(DOCS), _config(DOCS)))

        drawn = render_required_inputs(views, PresentationProfile.LESS_INFO)

        self.assertEqual([view.documentation for view in views], [DOCS, DOCS])
        self.assertEqual(drawn.count(f"  Documentation: {DOCS}"), 2)

    def test_the_configuration_form_names_it_once_per_installation(self) -> None:
        second = documented(
            ConfigInput(InputId("github-team"), EnvironmentBinding("GITHUB_TEAM"), required=False),
            DOCS,
        )
        views = project_required_inputs((_config(DOCS), second), owner="claude/project:github")
        draft = InstallationConfigDraft(
            tuple(
                InstallationConfigField(view.id, owner=view.owner, required=view.required)
                for view in views
            )
        )

        drawn = render_installation_config_form(views, draft, "")

        self.assertEqual(sum(DOCS in line for line in drawn), 1)

    def test_an_undocumented_input_draws_no_link(self) -> None:
        views = project_required_inputs((_secret(None), _config(None)))

        self.assertNotIn(
            "Documentation", "\n".join(render_required_inputs(views, PresentationProfile.MORE_INFO))
        )


class MarketplaceShowsItWholeTest(unittest.TestCase):
    @given(st.integers(min_value=0, max_value=3 * CONTENT_MEASURE))
    def test_more_info_shows_the_link_on_one_line_however_long(self, extra: int) -> None:
        link = "https://wiki.example.com/" + "a" * extra
        row = dataclasses.replace(_distinct().marketplace[0].row, documentation=link)

        drawn = artifact_disclosure(row)

        self.assertEqual([line for line in drawn if link in line], [f"  Documentation  {link}"])
        description = next(index for index, line in enumerate(drawn) if "Description" in line)
        self.assertGreater(drawn.index(f"  Documentation  {link}"), description)
        self.assertTrue(all(len(line) < CONTENT_MEASURE for line in drawn if link not in line))

    def test_an_offer_without_one_says_nothing_about_documentation(self) -> None:
        row = _distinct().marketplace[0].row

        self.assertNotIn("Documentation", "\n".join(artifact_disclosure(row)))

    def test_a_row_refuses_an_unsafe_link(self) -> None:
        with self.assertRaises(ValueError):
            dataclasses.replace(
                _distinct().marketplace[0].row, documentation=credential_url("wiki.example.com")
            )


class CredentialsAndVariablesShowItTest(unittest.TestCase):
    def _screens(self, link: str):
        screens = _distinct()
        row = dataclasses.replace(screens.marketplace[0].row, documentation=link)
        return dataclasses.replace(
            screens, marketplace=(MarketplaceEntry(row), *screens.marketplace[1:])
        ), row

    def test_an_installation_finds_the_link_its_exact_offer_carries(self) -> None:
        screens, row = self._screens(DOCS)
        installation = f"{row.key}#claude#project#/work/app"

        self.assertEqual(screens.documentation_for(installation), DOCS)
        self.assertEqual(screens.documentation_for(row.key), DOCS)
        other = row.key.replace(f"@{row.version}", "@99.0.0")
        self.assertEqual(screens.documentation_for(f"{other}#claude#project#/work/app"), "")

    def test_the_list_names_it_once_under_the_installation_whose_offer_carries_it(self) -> None:
        screens, row = self._screens(DOCS)
        documented = f"{row.key}#claude#project#/work/app"
        withdrawn = documented.replace(f"@{row.version}", "@99.0.0")

        drawn = render_user_inputs_area(screens, (documented, withdrawn), documented)

        groups = "\n".join(drawn).split("\n\n")
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0].count(f"    Documentation: {DOCS}"), 1)
        self.assertNotIn("Documentation", groups[1])

    def test_the_artifact_and_value_views_name_it(self) -> None:
        installation = "company/mcp/github@1.5.0#claude#project#/work/app"

        status = artifact_user_inputs_status(installation, (), (), DOCS)
        value = configuration_value_status(installation, "github-org", ("claude",), (), DOCS)

        self.assertIn(f"Documentation: {DOCS}", status)
        self.assertIn(f"Documentation: {DOCS}", value)
        self.assertNotIn(
            "Documentation", "\n".join(artifact_user_inputs_status(installation, (), ()))
        )


def _reader(*lines: str):
    pending = list(lines)

    def read(_prompt: str = "") -> str:
        if not pending:
            raise EOFError
        return pending.pop(0)

    return read


def _no_keychain():
    """A recording provider in place of the Keychain: no test ever reaches the real one."""

    stack = contextlib.ExitStack()
    for target in ("aart_cli.commands.marketplace", "aart_cli.tui"):
        stack.enter_context(
            mock.patch(f"{target}.MacOsKeychainProvider", lambda: _Resolving(_Journal()))
        )
    return stack


def _listed(env, *flags: str) -> tuple[int, str]:
    """`consume list`, which reads every connected Registry and so takes no `--project`."""

    output = io.StringIO()
    with (
        mock.patch.dict(os.environ, env.xdg, clear=False),
        contextlib.redirect_stdout(output),
        mock.patch("os.getcwd", return_value=str(env.project)),
    ):
        code = cli.main(["consume", "list", *flags])
    return code, output.getvalue()


class FromTheManifestToEverySurfaceE2ETest(unittest.TestCase):
    """Real compile, scan, assess, promote and publish; each surface reads what was approved."""

    def test_marketplace_more_info_shows_the_approved_link(self) -> None:
        from tests.configured_install_command_e2e_test import _environment

        with _environment(authored=_mcp()) as env, _no_keychain():
            with mock.patch.dict(os.environ, env.xdg, clear=False):
                composed = tui._canonical_consumer_actions(
                    project=str(env.project), user_home=str(env.home), today=dt.date(2026, 9, 1)
                )
                self.assertIsInstance(composed, Ok, composed)
                written: list[str] = []
                tui.run_consumer_text(composed.value, read=_reader("", "v"), write=written.append)

        shown = "\n".join(written).rpartition("AART / Marketplace")[2]
        self.assertIn(f"  Documentation  {DOCS}\n", shown)

    def test_the_cli_lists_refuses_reviews_and_installs_with_the_link(self) -> None:
        from tests.configured_install_command_e2e_test import _environment

        coordinate = "company/mcp/github"
        with _environment(authored=_mcp()) as env, _no_keychain():
            listed_code, listed_json = _listed(env, "--json")
            listed_text_code, listed_text = _listed(env)
            refused_code, refused = env.run_text(
                "consume", "install", coordinate, "--profile", "claude"
            )
            refused_json_code, refused_json = env.run(
                "consume", "install", coordinate, "--profile", "claude"
            )
            review_code, review = env.run_text(
                "consume", "install", coordinate, "--profile", "claude", "--set-later"
            )
            done_code, done = env.run(
                "consume", "install", coordinate, "--profile", "claude", "--set-later", "--yes"
            )

        self.assertEqual(listed_code, 0, listed_json)
        self.assertEqual(
            [item["documentation"] for item in json.loads(listed_json)["artifacts"]], [DOCS]
        )
        self.assertEqual(listed_text_code, 0, listed_text)
        self.assertIn(f"documentation={DOCS}", listed_text)
        self.assertNotEqual(refused_code, 0)
        self.assertRegex(
            refused, rf"(?m)^  - github-org \(config\)\n    Documentation: {re.escape(DOCS)}$"
        )
        self.assertRegex(refused, rf"(?m)^      Documentation: {re.escape(DOCS)}$")
        self.assertNotEqual(refused_json_code, 0)
        by_kind = {item["kind"]: item for item in refused_json["inputs"]}
        self.assertEqual(by_kind["config"]["documentation"], DOCS)
        self.assertEqual(by_kind["credential"]["guidance"][0]["documentation"], DOCS)
        self.assertEqual(review_code, 0, review)
        self.assertRegex(
            review, rf"Documentation:\n  company/mcp/github@1\.5\.0: {re.escape(DOCS)}\n"
        )
        self.assertEqual(done_code, 0, done)
        self.assertEqual(
            done["documentation"], [{"artifact": "company/mcp/github@1.5.0", "url": DOCS}]
        )

    def test_an_undocumented_artifact_shows_no_link_anywhere(self) -> None:
        from tests.configured_install_command_e2e_test import _environment

        coordinate = "company/mcp/github"
        with _environment(authored=_mcp(documentation=None)) as env, _no_keychain():
            _, listed = _listed(env)
            _, refused = env.run_text("consume", "install", coordinate, "--profile", "claude")
            _, done = env.run(
                "consume", "install", coordinate, "--profile", "claude", "--set-later", "--yes"
            )

        self.assertNotIn("documentation", listed.lower())
        self.assertNotIn("Documentation", refused)
        self.assertNotIn("documentation", done)


if __name__ == "__main__":
    unittest.main()
