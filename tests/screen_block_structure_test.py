"""`QA-087`: every view fills the same blocks, and actions never share one with view status.

The operator's words are the specification: *"nigdy akcja i menu do wyboru nie powinno byc w jednym
bloku z statusem widoku"*, and *"kazdy widok powinien miec ta strukture … bo teraz co widok jest
inaczej mam wrazenie"*. A reader scanning for something to press should not have to read prose to
find it, and prose standing between two rows reads like a row.

`Frame` gives the blocks somewhere to be said (`D-243`). What is held here is the other half: that
each screen puts the right thing in each of them. `MIXED_SCREENS` is the shrinking list of screens
that still do not, so the exceptions are named in one place rather than discovered one manual run at
a time -- *"zeby nie bylo zbyt wielu wyjatkow od reguly"*.
"""

from __future__ import annotations

from dataclasses import replace
from unittest import TestCase

from agent_artifacts.application.consumer_ui import ConsumerUiState
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
    PresentationProfile,
    project_dashboard,
)
from agent_artifacts.application.maintainer_views import (
    MaintainerRegistryView,
    MaintainerScreen,
    MaintainerViews,
    MaintainerWorkingTreeState,
    MaintainerWorkingTreeView,
    project_maintainer_candidates,
    project_maintainer_dashboard,
)
from agent_artifacts.tui_consumer import (
    CanonicalScreenSource,
    ConsumerScreens,
    frame,
    render_doctor,
)
from agent_artifacts.tui_layout import SECTION_RULE
from agent_artifacts.tui_maintainer import maintainer_registry_rows, maintainer_registry_status
from tests.consumer_shell_test import screens
from tests.screen_skeleton_test import _registry

#: Screens whose body still answers prose and rows together. Every entry is work, not a decision;
#: `CP-22` empties this set. Nothing may be added to it.
MIXED_SCREENS: frozenset[ConsumerScreen | MaintainerScreen] = frozenset()


def _maintainer_registry() -> MaintainerRegistryView:
    """One subscribed snapshot, valid and observed, with nothing promoted through it yet."""

    return MaintainerRegistryView(
        "company",
        True,
        "a" * 40,
        "sha256:" + "b" * 64,
        2,
        (),
        MaintainerWorkingTreeView(MaintainerWorkingTreeState.MATCHES_SNAPSHOT, "c" * 40),
        (),
    )


def _blocks(lines: tuple[str, ...]) -> list[tuple[str, ...]]:
    """The rendered frame back as the blocks it was composed from."""

    blocks: list[tuple[str, ...]] = []
    current: list[str] = []
    for line in lines:
        if line == SECTION_RULE:
            blocks.append(tuple(current))
            current = []
            continue
        current.append(line)
    blocks.append(tuple(current))
    return [tuple(block) for block in (tuple(b) for b in blocks)]


def _spoken(block: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(line for line in block if line.strip())


class DashboardBlockTest(TestCase):
    """The Dashboard the operator drew, read off the real composition."""

    def _frame(self, *, first_run: bool, verbose: bool = False) -> tuple[str, ...]:
        source = CanonicalScreenSource(
            ConsumerScreens(project_dashboard((), registry_count=0)) if first_run else screens()
        )
        profile = PresentationProfile.VERBOSE if verbose else PresentationProfile.FAST
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.DASHBOARD, profile=profile),
            settings=ConsumerSettings(profile=profile),
            workspace="/lab/consumer-project",
        )
        state = replace(state, rows=source.rows(state), cursor=0)
        return frame(source, state)

    def test_the_actions_block_holds_the_navigation_rows_and_nothing_else(self) -> None:
        blocks = _blocks(self._frame(first_run=True))

        self.assertEqual(
            _spoken(blocks[1]),
            (
                "> Marketplace",
                "  Installed",
                "  Updates",
                "  Registries",
                "  Credentials",
                "  Activity",
                "  Doctor",
                "  Settings",
            ),
        )

    def test_the_first_run_guidance_is_the_state_of_the_view_not_a_row(self) -> None:
        """It was drawn above the menu, inside the menu's own block."""

        blocks = _blocks(self._frame(first_run=True))
        guidance = next(
            block for block in blocks if any("Welcome to AART" in line for line in block)
        )

        self.assertNotIn(guidance, blocks[:2])
        self.assertIn("SETUP REQUIRED", guidance)
        self.assertNotIn("> Marketplace", guidance)

    def test_the_counts_are_the_state_of_the_view_on_a_machine_past_its_first_run(self) -> None:
        blocks = _blocks(self._frame(first_run=False))

        self.assertEqual(_spoken(blocks[1])[0], "> Marketplace")
        self.assertTrue(any("installed" in line for line in blocks[-3]))

    def test_the_block_order_is_rows_then_cursor_description_then_view_status(self) -> None:
        blocks = _blocks(self._frame(first_run=True, verbose=True))

        self.assertEqual(_spoken(blocks[1])[0], "> Marketplace")
        self.assertEqual(
            _spoken(blocks[2]),
            ("Browse and install approved tools from configured registries.",),
        )
        self.assertIn("Welcome to AART — this looks like your first run.", blocks[3])

    def test_no_block_announces_itself_now_that_it_holds_only_actions(self) -> None:
        """`Navigation:` labelled a block whose contents are the navigation."""

        self.assertNotIn("Navigation:", self._frame(first_run=True))


class MaintainerDashboardBlockTest(TestCase):
    def _frame(self) -> tuple[str, ...]:
        views = MaintainerViews(
            project_maintainer_dashboard(()), (), project_maintainer_candidates(()), ()
        )
        source = CanonicalScreenSource(
            ConsumerScreens(project_dashboard((), registry_count=0), maintainer=views)
        )
        state = ConsumerUiState(
            ConsumerSession(MaintainerScreen.DASHBOARD),
            settings=ConsumerSettings().with_maintainer_mode(True),
            workspace="/lab/registry",
        )
        state = replace(state, rows=source.rows(state), cursor=0)
        return frame(source, state)

    def test_the_actions_block_holds_the_navigation_rows_and_nothing_else(self) -> None:
        blocks = _blocks(self._frame())

        self.assertTrue(_spoken(blocks[1]))
        for line in _spoken(blocks[1]):
            self.assertTrue(line.startswith(("> ", "  ")), line)

    def test_the_maintainer_overview_is_the_state_of_the_view(self) -> None:
        blocks = _blocks(self._frame())
        overview = _spoken(blocks[2])

        self.assertEqual(overview[0], "Maintainer overview")
        self.assertFalse([line for line in overview if line.startswith("> ")])

    def test_an_unavailable_composition_is_state_rather_than_something_to_put_a_cursor_on(
        self,
    ) -> None:
        source = CanonicalScreenSource(screens())
        state = ConsumerUiState(
            ConsumerSession(MaintainerScreen.DASHBOARD),
            settings=ConsumerSettings().with_maintainer_mode(True),
        )

        self.assertEqual(source.actions(state), ())
        self.assertEqual(source.status(state), ("Maintainer state is not available yet.",))

    def test_no_block_announces_itself(self) -> None:
        self.assertNotIn("Maintainer navigation:", self._frame())


class RegistriesBlockTest(TestCase):
    """Screen 21, which is the one the operator drew."""

    def _frame(self, *, connected: bool) -> tuple[str, ...]:
        source = CanonicalScreenSource(
            ConsumerScreens(
                project_dashboard((), registry_count=2 if connected else 0),
                registries=(_registry("company"), _registry("team")) if connected else (),
            )
        )
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.REGISTRIES),
            settings=ConsumerSettings(),
            workspace="/lab/consumer-project",
        )
        state = replace(state, rows=source.rows(state), cursor=0)
        return frame(source, state)

    def test_the_actions_block_holds_the_add_row_and_nothing_else(self) -> None:
        blocks = _blocks(self._frame(connected=False))

        self.assertEqual(_spoken(blocks[1]), ("> [ Add Registry ]",))

    def test_what_a_registry_is_and_what_this_machine_has_are_the_state_of_the_view(self) -> None:
        blocks = _blocks(self._frame(connected=False))

        self.assertEqual(
            _spoken(blocks[2]),
            (
                "Connect an approved Git registry by URL. Local authoring Sources belong in "
                "Maintainer Mode.",
                "No sources are configured.",
                "Marketplace needs an approved registry before it can offer tools.",
                "Choose Add Registry above to connect the first one.",
            ),
        )

    def test_a_connected_registry_is_a_row_and_keeps_the_add_row_above_it(self) -> None:
        blocks = _blocks(self._frame(connected=True))
        rows = _spoken(blocks[1])

        self.assertEqual(rows[0], "> [ Add Registry ]")
        self.assertTrue([line for line in rows if "company" in line])
        self.assertFalse([line for line in rows if line.startswith("Connect an approved")])

    def test_the_empty_state_guidance_is_gone_once_something_is_connected(self) -> None:
        blocks = _blocks(self._frame(connected=True))

        self.assertNotIn("No sources are configured.", _spoken(blocks[2]))
        self.assertEqual(
            _spoken(blocks[2])[0],
            "Connect an approved Git registry by URL. Local authoring Sources belong in "
            "Maintainer Mode.",
        )


class SettingsBlockTest(TestCase):
    """Screen 27: four toggles under their group headings, and what the last one implies."""

    def _frame(self, *, maintainer: bool) -> tuple[str, ...]:
        source = CanonicalScreenSource(ConsumerScreens(project_dashboard((), registry_count=0)))
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.SETTINGS),
            settings=ConsumerSettings().with_maintainer_mode(maintainer),
            workspace="/lab",
        )
        state = replace(state, rows=source.rows(state), cursor=0)
        return frame(source, state)

    def test_the_actions_block_holds_the_toggles_and_the_headings_that_group_them(self) -> None:
        """A group heading is how the rows are organised, not prose about them."""

        blocks = _blocks(self._frame(maintainer=True))

        self.assertEqual(
            _spoken(blocks[1]),
            (
                "Experience",
                "> Detail level: Fast",
                "Installation",
                "  Default scope: Project",
                "Updates",
                "  Show available updates: on",
                "Advanced",
                "  Maintainer Mode: on",
            ),
        )

    def test_what_the_maintainer_toggle_implies_is_the_state_of_the_view(self) -> None:
        on = _blocks(self._frame(maintainer=True))
        off = _blocks(self._frame(maintainer=False))

        self.assertEqual(_spoken(on[2]), ("Maintainer screens are reachable from the Dashboard.",))
        self.assertEqual(
            _spoken(off[2]),
            ("Maintainer Mode off hides Sources, Candidates, Promotion and Publish.",),
        )


class DoctorBlockTest(TestCase):
    """Screen 29: what is installed and how it is, then how the whole machine is."""

    def _frame(self, *, verbose: bool = False) -> tuple[str, ...]:
        profile = PresentationProfile.VERBOSE if verbose else PresentationProfile.FAST
        source = CanonicalScreenSource(screens())
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.DOCTOR, profile=profile),
            settings=ConsumerSettings(profile=profile),
            workspace="/lab",
        )
        state = replace(state, rows=source.rows(state), cursor=0)
        return frame(source, state)

    def test_the_actions_block_holds_the_artifacts_and_what_drifted_on_them(self) -> None:
        blocks = _blocks(self._frame())

        self.assertEqual(
            _spoken(blocks[1]),
            (
                "✓ public/mcp/github@1.6.0",
                "⚠ public/mcp/jira@2.2.0",
                "  launcher: missing",
            ),
        )

    def test_the_counts_and_what_repair_would_do_are_the_state_of_the_view(self) -> None:
        blocks = _blocks(self._frame())

        self.assertEqual(
            _spoken(blocks[2]),
            (
                "1 ready",
                "1 needs attention",
                "Actions: repair issues using minimal reconciliation plans.",
            ),
        )

    def test_verbose_adds_to_the_state_of_the_view_not_to_the_rows(self) -> None:
        blocks = _blocks(self._frame(verbose=True))

        self.assertEqual(_spoken(blocks[1])[-1], "  launcher: missing")
        self.assertEqual(
            _spoken(blocks[2])[-2:], ("Independently repairable:", "  - public/mcp/jira@2.2.0")
        )

    def test_the_screen_does_not_name_itself_again_under_the_trail(self) -> None:
        """`QA-077`: the trail already says where this is; a second title is noise."""

        lines = self._frame()

        self.assertEqual(lines[0], "AART / Doctor")
        self.assertNotIn("AART / Check system", lines)

    def test_the_command_line_still_gets_the_whole_report(self) -> None:
        """`render_doctor` is the CLI's output too, and a report is read top to bottom."""

        rendered = render_doctor(screens().doctor, PresentationProfile.FAST)

        self.assertEqual(rendered[0], "AART / Check system")
        self.assertIn("✓ public/mcp/github@1.6.0", rendered)
        self.assertIn("1 needs attention", rendered)


class RegistryMaintainerBlockTest(TestCase):
    """Screen 46, which has two subjects and rows for only one of them."""

    def _frame(self) -> tuple[str, ...]:
        source = CanonicalScreenSource(screens())
        state = ConsumerUiState(
            ConsumerSession(MaintainerScreen.REGISTRY),
            settings=ConsumerSettings().with_maintainer_mode(True),
            workspace="/lab",
        )
        state = replace(state, rows=source.rows(state), cursor=0)
        return frame(source, state)

    def test_nothing_subscribed_means_no_rows_block_at_all(self) -> None:
        """A heading over nothing is the empty section `QA-065` reported."""

        blocks = _blocks(self._frame())

        # trail, view status, the `working at` caption, the keys -- no block of rows.
        self.assertEqual(len(blocks), 4)
        self.assertEqual(
            _spoken(blocks[1]),
            (
                "Connected Registry snapshots",
                "These approved snapshots determine what Marketplace can offer.",
                "No Registry is subscribed in this project yet.",
                "A Registry created here becomes connectable once it is published to its "
                "branch and subscribed to.",
                "Local Registry workspace",
                "Current project contains a Registry. Rebuild updates its generated files.",
            ),
        )

    def test_a_subscribed_snapshot_is_a_row_under_the_heading_that_introduces_it(self) -> None:
        rows = maintainer_registry_rows((_maintainer_registry(),), PresentationProfile.FAST)

        self.assertEqual(rows[0], "Connected Registry snapshots")
        self.assertTrue([line for line in rows if "company" in line])

    def test_the_local_workspace_is_state_whether_or_not_anything_is_subscribed(self) -> None:
        for views in ((), (_maintainer_registry(),)):
            with self.subTest(subscribed=bool(views)):
                status = maintainer_registry_status(views)

                self.assertIn("Local Registry workspace", status)
                self.assertIn(
                    "These approved snapshots determine what Marketplace can offer.", status
                )
                self.assertFalse([line for line in status if "company" in line])


class AddRegistryFormBlockTest(TestCase):
    """Screen 22, the first form. The operator settled it: everything explanatory below the rule.

    *"Wszystko pod pola"* -- so a form is not an exception, and `Frame` gains no block above the
    rows. The introduction and the reassurance about what is not being changed only read, and they
    read below what they are about. What a key press does is not one of them: `QA-088` sends that
    to the legend, which is the block that exists to answer it.
    """

    def _frame(self) -> tuple[str, ...]:
        source = CanonicalScreenSource(ConsumerScreens(project_dashboard((), registry_count=0)))
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.REGISTRY_ADD),
            settings=ConsumerSettings(),
            workspace="/lab",
        )
        state = replace(state, rows=source.rows(state), cursor=0)
        return frame(source, state)

    def test_the_actions_block_holds_the_fields_and_nothing_else(self) -> None:
        blocks = _blocks(self._frame())

        self.assertEqual(
            _spoken(blocks[1]),
            (
                "> Alias: <type a short name>",
                "  Registry URL: <type an HTTPS or SSH Git URL>",
                "  Branch or tag: <repository default>",
                "  Make default registry: yes",
                "  Continue: Validate and review",
            ),
        )

    def test_the_introduction_reads_below_the_fields(self) -> None:
        blocks = _blocks(self._frame())

        self.assertEqual(
            _spoken(blocks[2]),
            (
                "Connect an approved registry. AART validates a fresh snapshot before saving it.",
                "Local folders are authoring Sources, not Marketplace registries.",
                "This adds another registry. Nothing already connected is changed.",
            ),
        )

    def test_the_screen_says_nothing_about_the_keyboard(self) -> None:
        """`QA-088`: the four keys this form accepts are advertised, not described."""

        rendered = self._frame()

        self.assertNotIn(
            "Type to edit; Backspace removes; Space toggles default; Enter advances.", rendered
        )
        self.assertIn(
            "[Type] Edit   [Backspace] Delete   [Space] Make default   [Enter] Next / continue",
            rendered,
        )


class MaintainerFormBlockTest(TestCase):
    """Screens 31, 46a, 46c and 46h: the four forms that followed screen 22.

    Each had the same fault and takes the same shape the operator settled -- fields alone above the
    rule, everything that only reads below it, the key prompt last with a blank above it.
    """

    def _frame(self, screen: MaintainerScreen) -> tuple[str, ...]:
        source = CanonicalScreenSource(screens())
        state = ConsumerUiState(
            ConsumerSession(screen),
            settings=ConsumerSettings().with_maintainer_mode(True),
            workspace="/lab",
        )
        state = replace(state, rows=source.rows(state), cursor=0)
        return frame(source, state)

    def test_each_form_holds_only_its_fields_where_the_cursor_moves(self) -> None:
        for screen in (
            MaintainerScreen.SOURCE_ADD,
            MaintainerScreen.REGISTRY_INIT,
            MaintainerScreen.REPOSITORY_SCAN,
            MaintainerScreen.REGISTRY_REBUILD,
        ):
            with self.subTest(screen=screen):
                actions = _spoken(_blocks(self._frame(screen))[1])

                self.assertTrue(actions)
                for line in actions:
                    self.assertTrue(
                        line.startswith(("> ", "  ")),
                        f"{screen.value}: not a row -- {line!r}",
                    )

    def test_each_form_says_what_it_does_below_the_rule(self) -> None:
        opening = {
            MaintainerScreen.SOURCE_ADD: "Subscribe to an authoring repository.",
            MaintainerScreen.REGISTRY_INIT: "Create the registry this project publishes.",
            MaintainerScreen.REPOSITORY_SCAN: "Look at one repository for explicit",
            MaintainerScreen.REGISTRY_REBUILD: "Re-run this registry's generated files.",
        }
        for screen, starts in opening.items():
            with self.subTest(screen=screen):
                status = _spoken(_blocks(self._frame(screen))[2])

                self.assertTrue(status[0].startswith(starts), status[:1])

    def test_no_form_spells_out_in_prose_what_the_legend_already_advertises(self) -> None:
        """`QA-088`: a key the screen accepts is a key in the footer, not a sentence above it.

        *"duzo z tego powinno byc w klawiszach u dolu a nie w informacji"* -- and the one the
        operator named twice, *"Enter reviews the run under the cursor"*, said nothing the footer's
        `[Enter] Review run` was not already saying two lines below it.
        """

        for screen in (
            MaintainerScreen.SOURCE_ADD,
            MaintainerScreen.REGISTRY_INIT,
            MaintainerScreen.REPOSITORY_SCAN,
            MaintainerScreen.REGISTRY_REBUILD,
        ):
            with self.subTest(screen=screen):
                for line in _spoken(_blocks(self._frame(screen))[2]):
                    self.assertNotRegex(
                        line,
                        r"\b(Type to edit|Backspace|Enter (advances|reviews)|Space (toggles|switches))\b",
                        f"{screen.value}: the footer already says this -- {line!r}",
                    )

    def test_the_boundary_a_run_holds_is_still_stated_where_the_run_is_chosen(self) -> None:
        """`161.7`/`164.7`: the sentence moved block, and must not have been lost with the move."""

        for screen in (MaintainerScreen.REGISTRY_INIT, MaintainerScreen.REGISTRY_REBUILD):
            with self.subTest(screen=screen):
                status = _spoken(_blocks(self._frame(screen))[2])

                self.assertTrue(
                    any("Nothing is pushed and nothing is merged" in line for line in status),
                    status,
                )


class RebuildRegistryRowsTest(TestCase):
    """Screen 46h: a row is a choice, and what the choice is for is the cursor description.

    `QA-089`. Each row read `Lock only: pin everything the registry references` -- the choice and
    its explanation glued into one line, so the five things a reader is choosing between could not
    be scanned as five things. The operator drew it apart: bare labels above the rule, the purpose
    of the one under the cursor in the block `[v]` opens. *"z czego to wyjasnienie powinno
    oczywiscie byc collapsed albo uncollapsed jak sie klika v"*.
    """

    def _frame(self, *, verbose: bool, cursor: int = 1) -> tuple[str, ...]:
        source = CanonicalScreenSource(screens())
        state = ConsumerUiState(
            ConsumerSession(
                MaintainerScreen.REGISTRY_REBUILD,
                profile=PresentationProfile.VERBOSE if verbose else PresentationProfile.FAST,
            ),
            settings=ConsumerSettings().with_maintainer_mode(True),
            workspace="/lab",
        )
        state = replace(state, rows=source.rows(state), cursor=cursor)
        return frame(source, state)

    def test_a_row_is_the_choice_without_the_explanation(self) -> None:
        rows = _spoken(_blocks(self._frame(verbose=False))[1])

        self.assertEqual(
            rows,
            (
                "  Everything, in order: lock, build, validate, audit",
                "> Lock only",
                "  Build only",
                "  Validate only",
                "  Audit only",
            ),
        )

    def test_verbose_says_what_the_stage_under_the_cursor_is_for(self) -> None:
        described = _spoken(_blocks(self._frame(verbose=True))[2])

        self.assertEqual(described, ("pin everything the registry references",))

    def test_the_explanation_follows_the_cursor(self) -> None:
        described = _spoken(_blocks(self._frame(verbose=True, cursor=4))[2])

        self.assertEqual(described, ("report the registry's security evidence",))

    def test_fast_is_the_same_screen_without_it(self) -> None:
        """`QA-070`: the description is a mode, not a fixture, and `[v]` is the key that owns it."""

        for purpose in ("pin everything", "report the registry's"):
            self.assertNotIn(purpose, "\n".join(self._frame(verbose=False)))

    def test_the_whole_sequence_row_describes_itself_and_needs_no_second_line(self) -> None:
        """Its label already names the four stages in order; a description would repeat them.

        Saying nothing costs the block rather than drawing an empty one, which is the `QA-065`
        fault the skeleton already refuses: the frame here is one block shorter than the one a
        stage row draws, and the block after the rows is the view status.
        """

        everything = _blocks(self._frame(verbose=True, cursor=0))
        stage = _blocks(self._frame(verbose=True, cursor=1))

        self.assertEqual(len(everything), len(stage) - 1)
        self.assertTrue(_spoken(everything[2])[0].startswith("Re-run this registry's"))


class EveryScreenBlockTest(TestCase):
    """The enforcement: a migrated screen's actions block holds only what the cursor acts on."""

    def setUp(self) -> None:
        self.source = CanonicalScreenSource(screens())

    def test_a_migrated_screen_puts_no_prose_where_the_cursor_rows_go(self) -> None:
        for screen in (*ConsumerScreen, *MaintainerScreen):
            if screen in MIXED_SCREENS:
                continue
            state = ConsumerUiState(
                ConsumerSession(screen),
                settings=ConsumerSettings().with_maintainer_mode(True),
            )
            state = replace(state, rows=self.source.rows(state), cursor=0)
            if not state.rows:
                continue
            with self.subTest(screen=screen):
                for line in _spoken(self.source.actions(state)):
                    self.assertFalse(
                        line.endswith(".") and not line.startswith(("> ", "  ")),
                        f"{screen.value}: prose in the actions block -- {line!r}",
                    )

    def test_no_screen_is_exempt_from_the_structure_any_more(self) -> None:
        """The list is empty, and the sweep above now speaks for every screen there is.

        It stays here rather than being deleted with the last entry: an empty set that something
        asserts on is the only thing standing between a future exception and nobody noticing.
        """

        self.assertEqual(MIXED_SCREENS, frozenset())
