"""§176, INV-275: Default never silently differs from Settings.

Choosing Default checks every Settings value -- each harness, the scope and the Python installer --
against what the preparation measured for the selection. Either every value applies to every
selected artifact, or each one that does not is listed once, with its reason.
"""

from __future__ import annotations

import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.consumer_views import (
    INSTALL_PATH_CUSTOM,
    INSTALL_PATH_DEFAULT,
    DefaultPathMismatch,
    HarnessTargetView,
    PythonInstallerChoiceView,
    default_path_mismatches,
    install_path_label,
    pair_from_key,
    pair_key,
    render_default_path_mismatches,
)

SKILL = "company/skill/review@1.0.0"
MCP = "company/mcp/github@1.6.0"


def _targets(**hosted: tuple[str, ...]) -> tuple[HarnessTargetView, ...]:
    return tuple(HarnessTargetView(harness, artifacts) for harness, artifacts in hosted.items())


class DefaultPathMismatchTest(unittest.TestCase):
    def test_settings_that_fit_every_artifact_report_nothing(self) -> None:
        targets = _targets(claude=(SKILL, MCP), opencode=(SKILL, MCP))

        found = default_path_mismatches(
            targets,
            detected=("claude", "opencode"),
            harnesses=("claude", "opencode"),
            scope_offers=((pair_key(SKILL, "claude"), ("project", "user")),),
            scope="project",
            installer=PythonInstallerChoiceView(("pip", "uv"), "uv"),
            python_installer="uv",
        )

        self.assertEqual(found, ())

    def test_a_settings_harness_that_cannot_host_an_artifact_is_named_for_it(self) -> None:
        targets = _targets(claude=(SKILL, MCP), codex=(MCP,))

        found = default_path_mismatches(
            targets, detected=("claude", "codex"), harnesses=("claude", "codex")
        )

        self.assertEqual(found, (DefaultPathMismatch(SKILL, "harness", "codex", "can't host it"),))

    def test_a_settings_harness_that_hosts_nothing_is_named_for_every_artifact(self) -> None:
        # Measurement leaves a harness that hosts nothing out of the targets altogether.
        targets = _targets(claude=(SKILL, MCP))

        found = default_path_mismatches(targets, detected=("claude", "codex"), harnesses=("codex",))

        self.assertEqual(
            found,
            (
                DefaultPathMismatch(SKILL, "harness", "codex", "can't host it"),
                DefaultPathMismatch(MCP, "harness", "codex", "can't host it"),
            ),
        )

    def test_a_settings_harness_not_detected_is_one_line_for_the_selection(self) -> None:
        targets = _targets(claude=(SKILL, MCP))

        found = default_path_mismatches(
            targets, detected=("claude",), harnesses=("claude", "tabnine")
        )

        self.assertEqual(
            found,
            (DefaultPathMismatch("", "harness", "tabnine", "not detected on this machine"),),
        )

    def test_no_settings_harness_means_every_detected_one_and_nothing_to_report(self) -> None:
        targets = _targets(claude=(SKILL,), codex=(MCP,))

        self.assertEqual(
            default_path_mismatches(targets, detected=("claude", "codex"), harnesses=()), ()
        )

    def test_a_scope_the_artifact_does_not_offer_is_named_once_for_it(self) -> None:
        targets = _targets(claude=(SKILL, MCP), opencode=(MCP,))

        found = default_path_mismatches(
            targets,
            detected=("claude", "opencode"),
            harnesses=(),
            scope_offers=(
                (pair_key(SKILL, "claude"), ("project", "user")),
                (pair_key(MCP, "claude"), ("user",)),
                (pair_key(MCP, "opencode"), ("user",)),
            ),
            scope="project",
        )

        self.assertEqual(
            found, (DefaultPathMismatch(MCP, "scope", "project", "only user is offered"),)
        )

    def test_a_python_installer_this_selection_cannot_use_is_one_line(self) -> None:
        found = default_path_mismatches(
            _targets(claude=(MCP,)),
            detected=("claude",),
            harnesses=(),
            installer=PythonInstallerChoiceView(("pip",), "pip"),
            python_installer="uv",
        )

        self.assertEqual(
            found,
            (
                DefaultPathMismatch(
                    "", "Python installer", "uv", "only pip can install this selection here"
                ),
            ),
        )

    def test_a_selection_without_python_dependencies_has_no_installer_to_check(self) -> None:
        found = default_path_mismatches(
            _targets(claude=(SKILL,)), detected=("claude",), harnesses=(), python_installer="uv"
        )

        self.assertEqual(found, ())


class DefaultPathMismatchRenderTest(unittest.TestCase):
    def test_the_block_names_artifact_value_and_reason_and_points_to_custom(self) -> None:
        lines = render_default_path_mismatches(
            (
                DefaultPathMismatch(SKILL, "harness", "codex", "can't host it"),
                DefaultPathMismatch("", "harness", "tabnine", "not detected on this machine"),
            )
        )

        self.assertEqual(
            lines,
            (
                "Default can't install with your Settings:",
                f"  {SKILL} -- harness codex: can't host it",
                "  The whole selection -- harness tabnine: not detected on this machine",
                "Choose Custom to pick harnesses, scope and installer for these.",
            ),
        )

    def test_nothing_to_report_draws_nothing(self) -> None:
        self.assertEqual(render_default_path_mismatches(()), ())

    def test_default_says_it_is_unavailable_only_while_something_does_not_fit(self) -> None:
        self.assertEqual(install_path_label(INSTALL_PATH_DEFAULT, blocked=False), "Default")
        self.assertEqual(
            install_path_label(INSTALL_PATH_DEFAULT, blocked=True),
            "Default (not available with these Settings)",
        )
        self.assertEqual(install_path_label(INSTALL_PATH_CUSTOM, blocked=True), "Custom")


_HARNESS = st.sampled_from(("claude", "codex", "opencode", "tabnine"))
_ARTIFACT = st.sampled_from((SKILL, MCP, "company/mcp/jira@2.2.0"))
_SCOPES = st.sampled_from((("project",), ("user",), ("project", "user")))
_INSTALLERS = st.sampled_from((("pip",), ("uv",), ("pip", "uv")))


@st.composite
def _situations(draw):
    hosted = draw(st.dictionaries(_HARNESS, st.sets(_ARTIFACT, min_size=1), max_size=4))
    targets = tuple(
        HarnessTargetView(harness, tuple(sorted(artifacts)))
        for harness, artifacts in hosted.items()
    )
    detected = tuple(sorted(set(hosted) | set(draw(st.sets(_HARNESS)))))
    harnesses = tuple(draw(st.lists(_HARNESS, unique=True, max_size=4)))
    pairs = [
        pair_key(artifact, item.harness)
        for item in targets
        if not harnesses or item.harness in harnesses
        for artifact in item.artifacts
    ]
    scope_offers = tuple((pair, draw(_SCOPES)) for pair in pairs)
    offered = draw(st.none() | _INSTALLERS)
    installer = None if offered is None else PythonInstallerChoiceView(offered, offered[0])
    return (
        targets,
        detected,
        harnesses,
        scope_offers,
        draw(st.sampled_from(("project", "user"))),
        installer,
        draw(st.sampled_from(("pip", "uv"))),
    )


class DefaultNeverSilentlyDiffersPropertyTest(unittest.TestCase):
    @given(_situations())
    def test_nothing_is_reported_exactly_when_every_settings_value_applies(self, situation) -> None:
        targets, detected, harnesses, scope_offers, scope, installer, python_installer = situation
        hosts = {item.harness: item.artifacts for item in targets}
        artifacts = {artifact for item in targets for artifact in item.artifacts}

        found = default_path_mismatches(
            targets,
            detected=detected,
            harnesses=harnesses,
            scope_offers=scope_offers,
            scope=scope,
            installer=installer,
            python_installer=python_installer,
        )

        applies = (
            all(harness in detected for harness in harnesses)
            and all(
                artifact in hosts.get(harness, ())
                for harness in harnesses
                if harness in detected
                for artifact in artifacts
            )
            and all(scope in offered for _, offered in scope_offers)
            and (installer is None or python_installer in installer.offered)
        )
        self.assertEqual(found == (), applies, found)
        self.assertEqual(len(set(found)), len(found), "a mismatch is listed more than once")

    @given(_situations())
    def test_every_reported_mismatch_is_a_real_one(self, situation) -> None:
        targets, detected, harnesses, scope_offers, scope, installer, python_installer = situation
        hosts = {item.harness: item.artifacts for item in targets}
        offers: dict[str, set[str]] = {}
        for pair, offered in scope_offers:
            parsed = pair_from_key(pair)
            assert parsed is not None
            offers.setdefault(parsed[0], set()).update(() if scope in offered else ("missing",))

        found = default_path_mismatches(
            targets,
            detected=detected,
            harnesses=harnesses,
            scope_offers=scope_offers,
            scope=scope,
            installer=installer,
            python_installer=python_installer,
        )

        for item in found:
            if item.setting == "harness" and not item.artifact:
                self.assertNotIn(item.value, detected)
            elif item.setting == "harness":
                self.assertIn(item.value, harnesses)
                self.assertNotIn(item.artifact, hosts.get(item.value, ()))
            elif item.setting == "scope":
                self.assertEqual(item.value, scope)
                self.assertIn("missing", offers.get(item.artifact, set()))
            else:
                self.assertEqual(item.setting, "Python installer")
                assert installer is not None
                self.assertNotIn(item.value, installer.offered)


if __name__ == "__main__":
    unittest.main()
