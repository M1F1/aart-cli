"""CP-25.14: Installed Artifact Details names where AART actually put things (issue #17).

The view reported health, ownership and drift and never answered the first question somebody opens
it with: where is it. Every path here is a recorded or measured fact -- read off the receipt that
was written when the effects ran, and joined to the component observation that measured it -- never
reconstructed from an assumed harness layout, because an assumed path is a claim about somebody
else's disk.

A path whose component is absent or divergent is still named, with what was measured about it. The
alternative is a view that goes quiet exactly when it is most needed.
"""

from __future__ import annotations

import pathlib
import unittest

from aart_cli.application.consumer_views import (
    ConsumerScreen,
    PresentationProfile,
    project_installed_artifact,
)
from aart_cli.domain.effects import CopyTree
from aart_cli.domain.harness import Scope, mcp_target
from aart_cli.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    ObjectDigest,
    SourceAlias,
)
from aart_cli.domain.receipts import (
    ArtifactDelivery,
    DeliveryKind,
    InstallationReceipt,
    McpRegistration,
    PlacedArtifactReceipt,
)
from aart_cli.domain.reconciliation import (
    Component,
    ComponentId,
    ComponentState,
    CurrentState,
    DesiredComponent,
    DesiredState,
    ObservedComponent,
)
from aart_cli.tui_consumer import render_installed_artifact
from tests.configured_install_command_e2e_test import _environment
from tests.consumer_application_e2e_test import (
    _INSTALL,
    OFFERED,
    _actions,
    _at,
    _drive,
)
from tests.credential_fixtures import access_token

DIGEST = ObjectDigest("sha256", "a" * 64)
ROOT = "/home/dev/.local/share/aart/artifacts/skill/code-review"
MCP_ROOT = "/home/dev/.local/share/aart/artifacts/mcp/github"
PROJECT_DELIVERY = "/work/checkout/.claude/skills/code-review/SKILL.md"
USER_DELIVERY = "/home/dev/.claude/skills/code-review/SKILL.md"
COORDINATE = ArtifactCoordinate(
    SourceAlias("company"), ArtifactIdentity("skill", "code-review"), "1.2.0"
)
SECRET = access_token()
EFFECT = CopyTree(f"{ROOT}/payload", f"{ROOT}/payload")


def _delivery(harness: str, destination: str) -> ArtifactDelivery:
    return ArtifactDelivery(
        harness, f"{ROOT}/payload/SKILL.md", destination, DeliveryKind.FILE, DIGEST
    )


def _placed(*deliveries: ArtifactDelivery) -> PlacedArtifactReceipt:
    return PlacedArtifactReceipt("skill/code-review", ROOT, DIGEST, deliveries)


def _installation(*harnesses: tuple[str, Scope]) -> InstallationReceipt:
    return InstallationReceipt(
        "mcp/github",
        MCP_ROOT,
        f"{MCP_ROOT}/launch.sh",
        DIGEST,
        f"{MCP_ROOT}/runtime/.venv/bin/python",
        registrations=tuple(
            McpRegistration(mcp_target(harness, scope), "github", f"{MCP_ROOT}/launch.sh")
            for harness, scope in harnesses
        ),
    )


def _projected(receipt, *observed: tuple[ComponentId, ComponentState]):
    desired = DesiredState(
        COORDINATE, tuple(DesiredComponent(identifier, (EFFECT,)) for identifier, _ in observed)
    )
    current = CurrentState(
        COORDINATE, tuple(ObservedComponent(identifier, state) for identifier, state in observed)
    )
    return project_installed_artifact(desired, current, receipt=receipt)


def _drawn(receipt, *observed, profile=PresentationProfile.FAST) -> str:
    return "\n".join(render_installed_artifact(_projected(receipt, *observed), profile))


_MATCHED_SKILL = (
    (ComponentId(Component.PAYLOAD), ComponentState.MATCHED),
    (ComponentId(Component.DELIVERY, "claude"), ComponentState.MATCHED),
)


class ThePathsAreRecordedFactsTest(unittest.TestCase):
    def test_the_payload_root_and_the_harness_destination_are_both_named(self) -> None:
        drawn = _drawn(_placed(_delivery("claude", USER_DELIVERY)), *_MATCHED_SKILL)

        self.assertIn("Installation", drawn)
        self.assertIn(ROOT, drawn)
        self.assertIn(USER_DELIVERY, drawn)

    def test_one_payload_read_by_several_harnesses_names_each_destination(self) -> None:
        receipt = _placed(
            _delivery("claude", USER_DELIVERY),
            _delivery("opencode", "/home/dev/.opencode/skills/code-review/SKILL.md"),
        )

        drawn = _drawn(
            receipt,
            (ComponentId(Component.PAYLOAD), ComponentState.MATCHED),
            (ComponentId(Component.DELIVERY, "claude"), ComponentState.MATCHED),
            (ComponentId(Component.DELIVERY, "opencode"), ComponentState.MATCHED),
        )

        self.assertIn(USER_DELIVERY, drawn)
        self.assertIn("/home/dev/.opencode/skills/code-review/SKILL.md", drawn)
        self.assertIn("claude", drawn)
        self.assertIn("opencode", drawn)

    def test_an_installation_with_no_receipt_claims_no_location(self) -> None:
        """Nothing recorded it, so the view says nothing rather than guessing a layout."""

        view = _projected(None, *_MATCHED_SKILL)

        self.assertEqual(view.installation, ())
        self.assertNotIn("Installation", "\n".join(render_installed_artifact(view, FAST)))


class AMissingPathIsStillNamedTest(unittest.TestCase):
    def test_an_absent_delivery_is_named_with_what_was_measured_about_it(self) -> None:
        drawn = _drawn(
            _placed(_delivery("claude", USER_DELIVERY)),
            (ComponentId(Component.PAYLOAD), ComponentState.MATCHED),
            (ComponentId(Component.DELIVERY, "claude"), ComponentState.ABSENT),
        )

        self.assertIn(USER_DELIVERY, drawn)
        self.assertIn("absent", drawn)

    def test_a_divergent_path_is_not_reported_as_installed_there(self) -> None:
        drawn = _drawn(
            _placed(_delivery("claude", USER_DELIVERY)),
            (ComponentId(Component.PAYLOAD), ComponentState.MATCHED),
            (ComponentId(Component.DELIVERY, "claude"), ComponentState.DIVERGENT),
        )

        self.assertIn("divergent", drawn)

    def test_a_healthy_payload_the_comparison_dropped_is_named_and_left_unobserved(self) -> None:
        """`installed_state._reported` drops an undamaged payload nobody desired, so a reopened
        session's current state can legitimately carry a delivery and no payload at all. The path
        is still the artifact's and is still named; the state says only that nothing looked."""

        drawn = _drawn(
            _placed(_delivery("claude", USER_DELIVERY)),
            (ComponentId(Component.DELIVERY, "claude"), ComponentState.MATCHED),
        )

        self.assertIn(f"payload: {ROOT} — unobserved", drawn)
        self.assertIn("matched", drawn)

    def test_a_recorded_path_nothing_observed_says_so_rather_than_matched(self) -> None:
        """An unmeasured component is honestly unmeasured; `matched` would be a verification."""

        view = _projected(_placed(_delivery("claude", USER_DELIVERY)))
        states = {item.role: item.state for item in view.installation}

        self.assertEqual(states["delivery"], "unobserved")
        self.assertEqual(states["payload"], "unobserved")


class TheScopeIsReportedWhenItWasRecordedTest(unittest.TestCase):
    def test_a_project_registration_reports_project_scope(self) -> None:
        view = _projected(
            _installation(("claude", Scope.PROJECT)),
            (ComponentId(Component.PAYLOAD), ComponentState.MATCHED),
        )

        self.assertEqual(view.scope, "project")

    def test_a_user_registration_reports_user_scope(self) -> None:
        view = _projected(
            _installation(("claude", Scope.USER)),
            (ComponentId(Component.PAYLOAD), ComponentState.MATCHED),
        )

        self.assertEqual(view.scope, "user")

    def test_a_receipt_that_records_no_scope_claims_none(self) -> None:
        """A delivery records a harness and a path, never a scope. Inferring one from the path
        would be exactly the guessed layout this task forbids."""

        view = _projected(_placed(_delivery("claude", USER_DELIVERY)), *_MATCHED_SKILL)

        self.assertEqual(view.scope, "")

    def test_registrations_disagreeing_about_scope_are_not_flattened_into_one(self) -> None:
        view = _projected(
            _installation(("claude", Scope.PROJECT), ("opencode", Scope.USER)),
            (ComponentId(Component.PAYLOAD), ComponentState.MATCHED),
        )

        self.assertEqual(view.scope, "")


class VerboseAddsEveryOwnedComponentTest(unittest.TestCase):
    def test_fast_names_the_payload_and_the_harness_locations_only(self) -> None:
        drawn = _drawn(
            _installation(("claude", Scope.PROJECT)),
            (ComponentId(Component.PAYLOAD), ComponentState.MATCHED),
        )

        self.assertIn(MCP_ROOT, drawn)
        self.assertNotIn("runtime/.venv/bin/python", drawn)

    def test_verbose_adds_the_launcher_and_the_interpreter_with_their_roles(self) -> None:
        drawn = _drawn(
            _installation(("claude", Scope.PROJECT)),
            (ComponentId(Component.PAYLOAD), ComponentState.MATCHED),
            profile=PresentationProfile.VERBOSE,
        )

        self.assertIn(f"{MCP_ROOT}/launch.sh", drawn)
        self.assertIn(f"{MCP_ROOT}/runtime/.venv/bin/python", drawn)
        self.assertIn("launcher", drawn)
        self.assertIn("interpreter", drawn)


class NothingUnownedIsAttributedTest(unittest.TestCase):
    def test_only_paths_the_receipt_records_appear(self) -> None:
        """A harness's own settings file is not this artifact's, and is never listed as one."""

        view = _projected(_placed(_delivery("claude", USER_DELIVERY)), *_MATCHED_SKILL)

        self.assertEqual(
            sorted(item.path for item in view.installation), sorted([ROOT, USER_DELIVERY])
        )

    def test_no_file_content_configuration_value_or_credential_reaches_the_view(self) -> None:
        drawn = _drawn(_placed(_delivery("claude", USER_DELIVERY)), *_MATCHED_SKILL)

        self.assertNotIn(SECRET, drawn)
        self.assertNotIn(DIGEST.value, drawn)


class ThePathsSurviveTheSessionThatWroteThemTest(unittest.TestCase):
    """The whole point, through the production composition and a real disk.

    Every test above hands the projection a receipt it was given. This one installs through the
    public TUI, throws that composition away, opens Installed Artifact Details in a fresh one, and
    checks the drawn paths against the filesystem. A path that is only correct while the plan that
    made it is still in memory answers nobody: the reader opens this view days later.
    """

    def test_a_reopened_session_draws_paths_that_are_really_there(self) -> None:
        with _environment() as env:
            _drive(env, _at(ConsumerScreen.MARKETPLACE), *_INSTALL)

            _, terminal, _ = _drive(
                env,
                _at(ConsumerScreen.INSTALLED_ARTIFACT_DETAILS, focus=OFFERED),
                actions=_actions(env),
            )
            drawn = terminal.screen_containing("Installation")
            self.assertIsNotNone(drawn, "the reopened details screen named no installation at all")
            named = [
                line.split(": ", 1)[1].split(" (")[0].split(" — ")[0].strip()
                for line in (drawn or "").splitlines()
                if line.strip().startswith("- ") and ": /" in line
            ]

            self.assertTrue(named, "the Installation section listed no paths")
            self.assertIn(str(env.project / ".claude/skills/code-review"), named)
            for path in named:
                self.assertTrue(
                    pathlib.Path(path).exists(), f"the view named {path}, which is not there"
                )

    def test_nothing_the_installation_does_not_own_is_named(self) -> None:
        """The harness's own directory is where the delivery lives; it is not this artifact's."""

        with _environment() as env:
            _drive(env, _at(ConsumerScreen.MARKETPLACE), *_INSTALL)

            _, terminal, _ = _drive(
                env,
                _at(ConsumerScreen.INSTALLED_ARTIFACT_DETAILS, focus=OFFERED),
                actions=_actions(env),
            )
            drawn = terminal.screen_containing("Installation") or ""

            self.assertNotIn(f"- payload: {env.project / '.claude'}", drawn)
            self.assertNotIn(str(env.home / ".claude/settings.json"), drawn)


FAST = PresentationProfile.FAST


if __name__ == "__main__":
    unittest.main()
