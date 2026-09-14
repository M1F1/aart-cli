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

from agent_artifacts.application.consumer_ui import (
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    RegistryDraft,
    RegistryInitDraft,
    SourceDraft,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import (
    SETTING_PURPOSE,
    SETTING_ROWS,
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
from agent_artifacts.tui_layout import BULLET, SECTION_RULE
from agent_artifacts.tui_maintainer import (
    maintainer_registry_descriptor,
    maintainer_registry_rows,
    maintainer_registry_status,
)
from tests.consumer_shell_test import screens
from tests.frame_contract import frame_violations
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


def _statements(block: tuple[str, ...]) -> tuple[str, ...]:
    """A status block as what it says, with the list marking `QA-096` adds taken back off.

    A test about what a screen states should fail when the statement changes, not when the way a
    list of them is drawn does. That claim is held once, by `BulletedStatusTest`.
    """

    return tuple(
        line.removeprefix(BULLET).removeprefix(" " * len(BULLET)) for line in _spoken(block)
    )


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
                "  User Variables And Credentials",
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
        self.assertIn("SETUP REQUIRED", _statements(guidance))
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
        self.assertIn("Welcome to AART — this looks like your first run.", _statements(blocks[3]))

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
        """`QA-092`: the counts are the overview, so nothing has to say that they are one."""

        blocks = _blocks(self._frame())
        overview = _statements(blocks[2])

        self.assertEqual(overview[0], "Sources: 0")
        self.assertNotIn("Maintainer overview", overview)
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

    def _source_and_state(self, *, connected: bool):
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
        return source, replace(state, rows=source.rows(state), cursor=0)

    def _frame(self, *, connected: bool) -> tuple[str, ...]:
        return frame(*self._source_and_state(connected=connected))

    def test_the_actions_block_holds_the_add_row_and_nothing_else(self) -> None:
        blocks = _blocks(self._frame(connected=False))

        self.assertEqual(_spoken(blocks[1]), ("> Add Registry",))

    def test_what_a_registry_is_and_what_this_machine_has_are_the_state_of_the_view(self) -> None:
        blocks = _blocks(self._frame(connected=False))

        self.assertEqual(
            _statements(blocks[2]),
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

        self.assertEqual(rows[0], "> Add Registry")
        self.assertTrue([line for line in rows if "company" in line])
        self.assertFalse([line for line in rows if line.startswith("Connect an approved")])

    def test_a_registry_row_is_described_in_verbose_rather_than_drawn_as_more_rows(self) -> None:
        """CP-23 task 14: what a sync does is about the row, so it is the cursor's description."""

        source, state = self._source_and_state(connected=True)
        fast = replace(state, cursor=1)
        verbose, _ = reduce_consumer_ui(fast, ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_PROFILE))

        self.assertEqual(
            _spoken(source.actions(fast)),
            (
                "  Add Registry",
                "> company — connected",
                "    2 artifacts",
                "  team — connected",
                "    2 artifacts",
            ),
        )
        self.assertEqual(source.actions(verbose), source.actions(fast))
        self.assertIn(
            "Sync refreshes Marketplace availability; it does not update installed artifacts.",
            _spoken(_blocks(frame(source, verbose))[2]),
        )
        for drawn in (fast, verbose):
            self.assertEqual(frame_violations(source, drawn), ())

    def test_the_empty_state_guidance_is_gone_once_something_is_connected(self) -> None:
        blocks = _blocks(self._frame(connected=True))

        self.assertNotIn("No sources are configured.", _statements(blocks[2]))
        self.assertEqual(
            _statements(blocks[2])[0],
            "Connect an approved Git registry by URL. Local authoring Sources belong in "
            "Maintainer Mode.",
        )


class SettingsBlockTest(TestCase):
    """Screen 27: four toggles under their group headings, and what the last one implies."""

    def _frame(
        self, *, maintainer: bool = True, verbose: bool = False, cursor: int = 0
    ) -> tuple[str, ...]:
        profile = PresentationProfile.VERBOSE if verbose else PresentationProfile.FAST
        source = CanonicalScreenSource(ConsumerScreens(project_dashboard((), registry_count=0)))
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.SETTINGS, profile=profile),
            settings=ConsumerSettings(profile=profile).with_maintainer_mode(maintainer),
            workspace="/lab",
        )
        state = replace(state, rows=source.rows(state), cursor=cursor)
        return frame(source, state)

    def test_every_setting_says_what_it_changes_under_the_key_that_opens_it(self) -> None:
        """`QA-097`: four rows that change behaviour and no row that said what it changed."""

        for cursor, row in enumerate(SETTING_ROWS):
            with self.subTest(row=row):
                described = _spoken(_blocks(self._frame(verbose=True, cursor=cursor))[2])

                self.assertEqual(described, (SETTING_PURPOSE[row],))

    def test_a_setting_keeps_its_explanation_collapsed_in_fast(self) -> None:
        """`QA-070`: `[v]` is what opens every explanation, and this is not an exception."""

        blocks = _blocks(self._frame(verbose=False))

        self.assertNotIn(SETTING_PURPOSE["detail-level"], _spoken(blocks[2]))

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

        self.assertEqual(
            _statements(on[2]), ("Maintainer screens are reachable from the Dashboard.",)
        )
        self.assertEqual(
            _statements(off[2]),
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

    def test_the_rows_are_the_issues_repair_acts_on_with_the_cursor_on_one(self) -> None:
        """CP-23 task 14: `r` repairs the row under the cursor, so the cursor has to be drawn."""

        blocks = _blocks(self._frame())

        self.assertEqual(
            _spoken(blocks[1]),
            ("> ⚠ public/mcp/jira@2.2.0", "    launcher: missing"),
        )

    def test_the_counts_the_healthy_artifacts_and_what_repair_does_are_the_view_state(self) -> None:
        blocks = _blocks(self._frame())

        self.assertEqual(
            _statements(blocks[2]),
            (
                "✓ public/mcp/github@1.6.0",
                "1 ready",
                "1 needs attention",
                "Actions: repair issues using minimal reconciliation plans.",
            ),
        )

    def test_verbose_adds_to_the_state_of_the_view_not_to_the_rows(self) -> None:
        blocks = _blocks(self._frame(verbose=True))

        self.assertEqual(_spoken(blocks[1])[-1], "    launcher: missing")
        self.assertEqual(
            _statements(blocks[2])[-2:], ("Independently repairable:", "  - public/mcp/jira@2.2.0")
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
                "- Current project contains a Registry. Rebuild updates its generated files.",
                "- No Registry is subscribed in this project yet.",
            ),
        )

    def test_a_subscribed_snapshot_is_a_row_and_nothing_introduces_it(self) -> None:
        """`QA-092`: a registry snapshot does not need a line above it saying so."""

        rows = maintainer_registry_rows((_maintainer_registry(),), PresentationProfile.FAST)

        self.assertNotIn("Connected Registry snapshots", rows)
        self.assertTrue(rows[0].startswith("company"))

    def test_the_local_workspace_is_state_whether_or_not_anything_is_subscribed(self) -> None:
        for views in ((), (_maintainer_registry(),)):
            with self.subTest(subscribed=bool(views)):
                status = maintainer_registry_status(views)

                self.assertIn(
                    "Current project contains a Registry. Rebuild updates its generated files.",
                    status,
                )
                self.assertFalse([line for line in status if "company" in line])

    def test_what_a_snapshot_is_for_is_an_explanation_rather_than_a_state(self) -> None:
        """`QA-095`: it never changes, so it collapses under `[v]` like every other one."""

        for views in ((), (_maintainer_registry(),)):
            with self.subTest(subscribed=bool(views)):
                sentence = "These approved snapshots determine what Marketplace can offer."

                self.assertNotIn(sentence, maintainer_registry_status(views))
                self.assertIn(sentence, maintainer_registry_descriptor(views))

    def test_the_project_is_told_it_is_not_a_registry_exactly_once(self) -> None:
        """`QA-094`: the status said it, and the refusal standing beside it said it again."""

        status = maintainer_registry_status((), registry_workspace_present=False)

        self.assertEqual(
            len([line for line in status if "not a Registry" in line]),
            1,
        )


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
            _statements(blocks[2]),
            (
                "Connect an approved registry. AART validates a fresh snapshot before saving it.",
                "Local folders are authoring Sources, not Marketplace registries.",
                "This adds another registry. Nothing already connected is changed.",
            ),
        )

    def test_the_screen_says_nothing_about_the_keyboard(self) -> None:
        """`QA-088`: the keys the field under the cursor takes are advertised, not described."""

        rendered = self._frame()

        self.assertNotIn(
            "Type to edit; Backspace removes; Space toggles default; Enter advances.", rendered
        )
        self.assertIn(
            "[Type] Edit   [Backspace] Delete   [Enter] Next",
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
                status = _statements(_blocks(self._frame(screen))[2])

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
        self.assertTrue(_statements(everything[2])[0].startswith("Re-run this registry's"))


class ReviewScreenBlockTest(TestCase):
    """`QA-090`: a confirmation screen has to say what it is confirming.

    Every review drew exactly one line -- *"Press Enter to connect this registry."* -- over a legend
    that already said `[Enter] Confirm`, so the screen between a filled-in form and an irreversible
    action said nothing at all about what was about to happen. `CP-22` step 14 places it: the
    decision is what the legend offers, and what the review is about is view status.
    """

    def _frame(self, screen, **changes) -> tuple[str, ...]:
        source = CanonicalScreenSource(screens())
        state = ConsumerUiState(
            ConsumerSession(screen),
            settings=ConsumerSettings().with_maintainer_mode(True),
            workspace="/lab",
            **changes,
        )
        state = replace(state, rows=source.rows(state), cursor=0)
        # A review has no rows, so every line it draws is a statement: read them as what they say
        # rather than as how `QA-096` marks them.
        return _statements(frame(source, state))

    def test_connecting_a_registry_says_which_one_and_from_where(self) -> None:
        rendered = self._frame(
            ConsumerScreen.REGISTRY_REVIEW,
            registry_draft=RegistryDraft(
                "company", "https://git.example.test/company/registry.git", "stable", True
            ),
        )

        self.assertIn(
            "Connect company from https://git.example.test/company/registry.git", rendered
        )
        self.assertIn("Branch or tag: stable", rendered)
        self.assertIn("It becomes the default registry.", rendered)

    def test_a_registry_that_is_not_made_default_says_so_rather_than_staying_silent(self) -> None:
        """Silence would read as "no opinion", and the form has a yes/no the reader chose."""

        rendered = self._frame(
            ConsumerScreen.REGISTRY_REVIEW,
            registry_draft=RegistryDraft(
                "company", "https://git.example.test/company/registry.git", "", False
            ),
        )

        self.assertIn("Branch or tag: repository default", rendered)
        self.assertIn("The default registry does not change.", rendered)

    def test_connecting_a_source_says_its_kind_and_location(self) -> None:
        rendered = self._frame(
            MaintainerScreen.SOURCE_ADD_REVIEW,
            source_draft=SourceDraft(
                "kit", "source-git", "https://git.example.test/kit.git", "main"
            ),
        )

        self.assertIn("Subscribe to kit at https://git.example.test/kit.git", rendered)
        self.assertIn("Branch or tag: main", rendered)

    def test_creating_a_registry_names_it_and_says_whether_a_commit_is_made(self) -> None:
        rendered = self._frame(
            MaintainerScreen.REGISTRY_INIT_REVIEW,
            registry_init_draft=RegistryInitDraft("acme-registry", "Acme", "", True),
        )

        self.assertIn("Create acme-registry, called Acme, in this project.", rendered)
        self.assertIn("The files are written and committed locally.", rendered)

    def test_a_review_offers_its_decision_in_the_legend_and_not_in_a_sentence(self) -> None:
        """`QA-088` again: the key is advertised, so describing it is saying the same thing twice."""

        for screen, changes in (
            (ConsumerScreen.REGISTRY_REVIEW, {}),
            (MaintainerScreen.SOURCE_ADD_REVIEW, {}),
            (MaintainerScreen.REGISTRY_INIT_REVIEW, {}),
            (MaintainerScreen.REGISTRY_REBUILD_REVIEW, {}),
        ):
            with self.subTest(screen=screen):
                rendered = self._frame(screen, **changes)

                for line in rendered:
                    self.assertNotRegex(line, r"^Press Enter to ")
                self.assertTrue(any("[Enter] " in line for line in rendered[-2:]))


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

    def test_a_screen_with_no_rows_draws_no_actions_block_at_all(self) -> None:
        """`QA-091`: the rule the row model already knows, instead of a list of screens.

        A result, a review and a refusal have nothing the cursor can move over, so everything they
        draw is the state of the view. Read off `rows` rather than off a set, because a set of
        named exceptions is what the operator asked us to stop maintaining -- *"zeby nie bylo zbyt
        wielu wyjatkow od reguly"*.
        """

        for screen in (*ConsumerScreen, *MaintainerScreen):
            state = ConsumerUiState(
                ConsumerSession(screen),
                settings=ConsumerSettings().with_maintainer_mode(True),
            )
            state = replace(state, rows=self.source.rows(state), cursor=0)
            if state.rows:
                continue
            with self.subTest(screen=screen):
                self.assertEqual(self.source.actions(state), ())

    def test_no_screen_is_exempt_from_the_structure_any_more(self) -> None:
        """The list is empty, and the sweep above now speaks for every screen there is.

        It stays here rather than being deleted with the last entry: an empty set that something
        asserts on is the only thing standing between a future exception and nobody noticing.
        """

        self.assertEqual(MIXED_SCREENS, frozenset())


class NoticeBlockTest(TestCase):
    """`QA-093`: what an action left behind is not one of the things it was left among."""

    #: What a refused rebuild actually leaves behind: two statements, separated the way
    #: `_refusal` separates a reason from its next step (`QA-096`).
    _NOTICE = (
        "The current project is not a Registry, so there is nothing here to rebuild.",
        "",
        "Choose Initialize Registry to create one in this project first.",
    )

    def _frame(self, screen: MaintainerScreen) -> tuple[str, ...]:
        views = MaintainerViews(
            project_maintainer_dashboard(()), (), project_maintainer_candidates(()), ()
        )
        source = CanonicalScreenSource(
            replace(
                ConsumerScreens(project_dashboard((), registry_count=0), maintainer=views),
                notice=self._NOTICE,
            )
        )
        state = ConsumerUiState(
            ConsumerSession(screen),
            settings=ConsumerSettings().with_maintainer_mode(True),
            workspace="/lab/registry",
        )
        state = replace(state, rows=source.rows(state), cursor=0)
        return frame(source, state)

    def test_a_notice_never_stands_among_the_rows_it_was_left_over(self) -> None:
        blocks = _blocks(self._frame(MaintainerScreen.REGISTRY_REBUILD))

        for line in _spoken(blocks[1]):
            self.assertTrue(line.startswith(("> ", "  ")), line)
        self.assertNotIn(self._NOTICE[0], _statements(blocks[1]))

    def test_the_notice_is_a_block_of_its_own(self) -> None:
        blocks = _blocks(self._frame(MaintainerScreen.REGISTRY_REBUILD))
        carrying = [block for block in blocks if self._NOTICE[0] in _statements(block)]

        self.assertEqual(len(carrying), 1)
        self.assertEqual(_statements(carrying[0]), _spoken(self._NOTICE))
        self.assertTrue(all(line.startswith(BULLET) for line in _spoken(carrying[0])))

    def test_the_notice_follows_the_view_status_and_precedes_the_caption(self) -> None:
        """§167 orders them: description, view status, notices, caption, keys (D-268)."""

        drawn = self._frame(MaintainerScreen.REGISTRY)
        blocks = _blocks(drawn)
        notice = next(
            index for index, block in enumerate(blocks) if self._NOTICE[0] in _statements(block)
        )
        status = next(
            index
            for index, block in enumerate(blocks)
            if index != notice and any(line.startswith(BULLET) for line in _spoken(block))
        )

        self.assertLess(status, notice)
        self.assertIn("working at /lab/registry", blocks[notice + 1])

    def test_a_screen_with_no_rows_gives_its_notice_the_same_block(self) -> None:
        """`QA-091` had folded it into view status, which is a different question again."""

        blocks = _blocks(self._frame(MaintainerScreen.REGISTRY))
        carrying = [block for block in blocks if self._NOTICE[0] in _statements(block)]

        self.assertEqual(len(carrying), 1)
        self.assertEqual(_statements(carrying[0]), _spoken(self._NOTICE))


class BulletedStatusTest(TestCase):
    """`QA-096`: every statement about a view is marked as one, on every screen.

    *"kazda linia statusu/informacji powinna byc oznaczona jako element listy"*, and *"zawsze,
    nawet pojedyncze"* -- so no screen has to decide whether it has enough to say to be a list.
    The claim lives here alone: every other test in this file reads statements through
    `_statements` and fails on what a screen says rather than on how the list is drawn.
    """

    def _status(self, frame_lines: tuple[str, ...]) -> tuple[str, ...]:
        blocks = _blocks(frame_lines)
        # The status block is the last one before the `working at` caption and the keys.
        return _spoken(blocks[-3])

    def test_a_lone_statement_is_still_marked(self) -> None:
        source = CanonicalScreenSource(screens())
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.SETTINGS),
            settings=ConsumerSettings().with_maintainer_mode(True),
            workspace="/lab",
        )
        state = replace(state, rows=source.rows(state), cursor=0)

        self.assertEqual(
            self._status(frame(source, state)),
            ("- Maintainer screens are reachable from the Dashboard.",),
        )

    def test_separate_facts_are_separate_items_with_a_blank_line_between_them(self) -> None:
        views = MaintainerViews(
            project_maintainer_dashboard(()), (), project_maintainer_candidates(()), ()
        )
        source = CanonicalScreenSource(
            ConsumerScreens(project_dashboard((), registry_count=0), maintainer=views)
        )
        state = ConsumerUiState(
            ConsumerSession(MaintainerScreen.DASHBOARD),
            settings=ConsumerSettings().with_maintainer_mode(True),
            workspace="/lab",
        )
        state = replace(state, rows=source.rows(state), cursor=0)
        blocks = _blocks(frame(source, state))

        self.assertEqual(
            blocks[2],
            (
                "",
                "- Sources: 0",
                "",
                "- Candidates: 0",
                "",
                "- Validation failures: 0",
                "",
                "- Ready for promotion: 0",
                "",
                "- Recent maintainer activity:",
                "    - none yet",
                "",
            ),
        )

    def test_no_screen_states_anything_without_marking_it(self) -> None:
        """Read off every screen the shell can reach, so a new one cannot quietly opt out."""

        source = CanonicalScreenSource(screens())
        for screen in (*ConsumerScreen, *MaintainerScreen):
            state = ConsumerUiState(
                ConsumerSession(screen),
                settings=ConsumerSettings().with_maintainer_mode(True),
                workspace="/lab",
            )
            state = replace(state, rows=source.rows(state), cursor=0)
            status = source.status(state)
            if not status:
                continue
            with self.subTest(screen=screen):
                drawn = self._status(frame(source, state))
                self.assertTrue(drawn)
                for line in drawn:
                    self.assertTrue(line.startswith((BULLET, "  ")), (screen, line))
