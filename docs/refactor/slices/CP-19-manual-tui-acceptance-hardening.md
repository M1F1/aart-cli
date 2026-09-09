# CP-19 — Manual TUI acceptance hardening

Status: IN PROGRESS — paused for the operator's manual discovery run

## Goal

Turn the post-refactor manual walkthrough into explicit, independently executable work without
reopening the verified CP-13, CP-14 or CP-18 slices. Preserve every accepted safety boundary while
making the persistent TUI understandable and recoverable for an operator who does not know its
internal state model.

## Product Specification authority

- 161.1 and INV-187: accepted information hierarchy, safety and navigation semantics.
- 161.7 and INV-199: Registry, Source, Candidate and Marketplace remain distinct.
- 164.2 and INV-200/201: Source synchronization and explicit manifest discovery.
- 165.28 and INV-242: a local commit is not publication; Git review/merge remains external.
- D-185: interactive TUI guidance contains no CLI command text.

## Scope and ordered work

1. **Contextual footer (QA-026) — DONE.** Local bindings appear first, universal movement/back/help/
   quit second. Keyboard events and labels share one binding authority (D-202).
2. **Complete the real discovery run — IN PROGRESS.** Continue from the MCP promotion after the
   prior Skill promotion is merged, the local checkout observes it and the configured Registry is
   synchronized. Every new finding goes immediately to root `TODO.md` and receives a bounded CP-19
   step or a backlog item; it is not implemented during the discovery pass.
3. **Completed-sequence navigation (QA-027) — DONE.** Screen 34 binds `Enter → Sources`, with the
   matching edge declared in the navigation map, because `_navigate` refuses a target the map does
   not carry and a binding without it is a key that silently does nothing. Registry Maintainer
   binds `c Candidates`, so a finished promotion is one key from the next one; screen 45's own
   Enter still goes on to Registry, which is the precedent this generalizes (D-210). Confirmation
   screens stay confirmations: a review still holding its action is not treated as a result.
4. **Form lifecycle (QA-028) — DONE.** `_navigate` empties the draft the entered form owns, and only
   that one. It is forward navigation only, which is exactly what separates opening a new form from
   returning to a refused one: `_declined_preparation` and `_back` walk the session history and
   touch no draft, so `QA-018`/`D-184` holds unchanged. Both add forms also say in words that they
   add another one and change nothing already connected (D-211).
5. **Review layout (QA-029) — DONE.** The rule — facts, one blank line, the single line saying what
   a key press will do, nothing after it — is stated once in the pure layout kernel and applied at
   the seams every screen already passes through: `tui_layout.separate` joins blocks with exactly
   one blank and drops an empty one, `tui_layout.action_prompt` composes facts with the prompt, and
   `is_action_prompt` recognises the prompt from the line itself so `CanonicalScreenSource.lines`
   can lift whatever prompt a screen wrote and re-place it last, under the notice it is about. Four
   review prompts stopped saying "below" about a plan that is now above them. The two Source Sync
   screens were regrouped into what it is / where it stands / what it will do / the evidence. B-048
   (refusal wrapping) stays separate: wrapping is a width decision, this is an ordering one (D-212).
6. **Stable tabular projections (QA-030) — DONE.** The header is a row of the same grid rather than
   a hand-spaced string, and `tui_layout.columns` lays the header and every row out together, so a
   name wider than its column is cut there instead of pushing the columns after it right. The cursor
   mark is its own column. Cutting is honest because the row under the cursor is repeated in full in
   a `field_block` below the list — which is also where the verbose per-row detail line went, since
   a detail under every row was part of the reported density. Screen 47's selectable rows are the
   same table without a header and were moved onto the grid too; the other Maintainer lists are
   label/indent blocks, not tables, and putting them on a grid would be a redesign (D-213).
7. **Registry baseline diagnosis and recovery (QA-031/B-100) — TODO.** Preserve exact baseline
   equality. Characterize unpublished prior promotion, stale checkout, wrong workspace root and
   unrelated drift separately. The measured first case must explain the Git publication → local
   update → Registry synchronization sequence in product terms without embedding CLI commands.
8. **Git publication transition (QA-034/B-102) — DONE.** Publication is presence on the canonical
   consumer-visible branch (INV-242), so it is a property of the reading and not a field anything
   in the accepted workflow writes. `load_published_registry_versions` applies the transition once,
   at the consumer seams (`configured_offers`, `configured_selection`, `configured_installation`,
   `offline_readiness`); maintainer-side readers keep the record as written (D-207).
   `tests/git_publication_transition_e2e_test.py` drives the real sequence — promotion transaction,
   review branch, `git merge --no-ff`, public sync, Marketplace, install receipt — and asserts the
   merged records on disk still read `promoted-local`.
9. **Canonical Registry maintenance and CI (QA-025/QA-032/B-057/B-099) — DONE.** The six generated
   verbs dispatch on the representation they are handed instead of assuming the authoring workspace
   (D-208). `is_promoted_registry` recognizes the approved shape by `registry/versions/`; `validate`
   drops the compiled-lock requirement, because `validate_promoted_registry` is the stricter check;
   `build` derives exactly `registry/index.json` and `registry/snapshot.json`; `lock` is a read-only
   prepared curation; `publish` chains build, validate and audit with no lock half. Screen 46's
   Rebuild reaches the same authority through `refresh_registry_workspace`, so it is repaired at the
   same seam. Nothing writes a second legacy representation, and the generated workflow is unchanged
   so already-scaffolded registries keep working.
10. **Failed-action terminal state (QA-033/B-101) — DONE.** A confirmation that never happened and
   an attempt that is over arrived as the same event, so the reducer could only treat both as
   nothing. `ACTION_FAILED` separates them: `action` clears, `failed_action` records which run this
   screen is the end of, the footer offers `Enter Back to list`, Enter navigates through the same
   `_ACTION_RESULT` table a recorded run uses, and the review's prompt and heading say the run did
   not happen (D-209). The screen does not move, because the refusal is drawn here. Held across four
   confirmed action kinds, with `QA-024` preserved.
11. **Workflow progress and back context (QA-036/QA-037) — TODO.** Give every multi-step sequence a
   compact completed/current/upcoming trail derived from its real navigation graph. Back restores
   the same stable subject and read model; it may not return to a screen that says its Candidate is
   unavailable.
12. **Visual hierarchy and focus (QA-035/QA-038/QA-040/QA-041/QA-042) — TODO.** State one small
   layout vocabulary for section separators, bounded Registry rows, readable one-binding-per-line
   help, compact `[Key] Action` footer chrome and a cursor on every actionable row. Avoid a
   screen-by-screen pile of unrelated punctuation.
13. **Promotion mode explanation (QA-039) — TODO.** Explain Vendored and Referenced ownership,
   payload and upstream consequences before confirmation; label `m` as a toggle with the active
   value visible.
14. **Registry/Source row truth (QA-043) — TODO.** Decide the screen-21 representation from the
   Product Specification distinction: authoring Sources may not advertise a detail action whose
   route accepts only Registry connections, and no internal screen enum may enter user output.
15. **Batch verification — TODO.** Each implementation increment gets a real RED/mutation and focused
   suites. Only after the operator hands the batch back run full `make quality` and
   `make integration`, then return the fixed items for manual retest.

## Current manual checkpoint

The operator merged Registry PR #1 at `f37d182` and synchronized it despite the known QA-032 false
negative. The clean Consumer sees that Source as healthy, and its snapshot contains the promoted
Skill's version, manifest and payload, but Marketplace offers zero artifacts. The version remains
`promoted-local`; no public path applies the publication transition that CP-17 fixtures applied
internally. This is blocking QA-034.

Local Registry `main` now holds the second promotion at
`259af24`, one commit ahead of published `origin/main`, and the repository-adopted
`skill/commit-message-discipline@1.0.0` transaction is present as an uncommitted working-tree
change. The procedure's required Rebuild run exposed QA-033: after `lock` refused on the legacy
representation,
the TUI remained on Review Rebuild and continued to advertise confirmation for a cleared plan.
That run was the procedure's required QA-025 retest, not an operator detour: QA-025 is reopened
because its real canonical input fails even though its route and ordering passed focused tests.

Step 8 has since closed QA-034, so the Marketplace-to-lifecycle half of discovery can resume: a
merged promotion is offered and installable without anything editing Registry JSON. Step 9 has since
closed QA-025 and QA-032, so Rebuild and the Registry PR gate are retestable again. Do not discard
the local MCP promotion or adoption transaction.

## Evidence and gates

Step 8 was RED against the shipped behaviour with the reported symptom itself: Marketplace listed
`[]` where the merged branch's promotion belonged. Two targeted mutations were killed — removing the
transition from `load_published_registry_versions`, and leaving the installation re-read on the raw
loader so an install refuses the exact version Marketplace just offered. One older test asserted the
replaced belief and was rewritten rather than deleted: `configured_selection_resolution_e2e_test`
now holds that the configured branch publishes what it carries without rewriting it, plus a
separate claim that an artifact the branch does not carry is still not found.

Step 9 was RED through the public chain rather than a fixture: `registry init` → `registry scan` →
`registry promote --yes`, then the six verbs the generated workflow runs, in its order. Four
targeted mutations were killed — removing the promoted exemption from `validate`, disabling the
promoted `lock` so it falls back to the authoring lock, disabling the approved reader in
`registry_maintenance.planning`, and disabling the promoted `build` dispatch. Each turned the
acceptance tests red, including the screen-46 rebuild claim.

Step 10 was RED against the shipped reducer with the operator's own symptom: `Enter Confirm` still
advertised over a discarded plan, and `key_event` still returning `CONFIRM_ACTION`. The claims are
stated over four confirmed action kinds as subtests rather than over Registry rebuild alone, and the
frame test asserts what the operator actually read — heading, prompt and footer — with the refusal
still on screen, because losing the refusal would be the worse defect.

QA-026 was RED against the fixed footer. A semantic mutation routing advertised `b Rebuild` to the
initialization screen was killed by the headless shell walk. The focused 238-test interaction and
boundary set, changed-module `mypy`, `ruff check`, `ruff format --check` and `make docs-check` were
green. Full repository gates are intentionally deferred until step 15 at the operator's request.

Step 5 was RED as a rule rather than as a screen: a sweep over every Consumer and Maintainer
screen, run twice — once with no notice and once with one on it — plus the three maintainer reviews
the sweep cannot reach without their typed views, in every presentation profile. Six targeted
mutations were killed: dropping the blank in `action_prompt`, joining without a blank in `separate`,
keeping a block's trailing blank, restoring the old `(*body, "", *notice)` order in `lines`, and
un-grouping either Source Sync screen. The second of those initially survived, which is what the
grouping claim and the join property were added to hold — the prompt rule alone had said nothing
about the groups above it.

The step-5 sweep also caught a step-4 regression that step 4's own targeted set had missed:
`consumer_declined_preparation_test` planted a typed draft and *then* navigated into the form, so
`D-211` emptied it. The claim is intact and still holds — a decline keeps what was typed — but its
fixture now types on the form after opening it, which is what the shell actually does. The lesson is
recorded rather than the fix alone: a targeted set chosen per-module misses reducer fixtures living
under other names, so each remaining CP-19 step runs the whole `tui`/`consumer`/`maintainer`/
`source`/`registry`/`setup` file set, not only the files it edited.

Step 6 was RED on both screens with the operator's own two rows. Five targeted mutations were
killed: hand-spaced padding, a header outside the grid, no focused block, the first row expanded
instead of the focused one, and double-space concatenation on screen 47. The column claims the step
depends on are stated as a Hypothesis property over generated names rather than assumed from
`B-107`'s kernel, which the scoped advisory run still reports as largely unheld elsewhere.

## Do not undo

- Do not weaken the exact synchronized-baseline comparison to pass QA-031.
- Do not put `aart ...` commands into TUI frames.
- Do not reset a refused form on leave; reset a fresh form on entry.
- Do not put an action prompt anywhere but last, and do not reintroduce `(*body, "", *notice)`:
  the notice is what the reader is being asked about, so it belongs above the ask.
- Do not re-widen a column literal to make a name fit. A list with a header puts the header on the
  same grid as its rows, and a cut cell is repeated in full under the cursor.
- Keep `key_event` as the only key interpreter and keep application code free of IO.
- Never commit the embedded `superpowers-aart-test/` lab repository.
- Do not make promotion write the authoring workspace as a second representation, and do not
  weaken `validate_promoted_registry` to accept a registry missing its derived catalogs.

## Exact next implementation action

Execute step 7 (QA-031/B-100) next: an honest Registry baseline-refusal diagnosis and a recovery
path. Preserve the exact baseline equality — do not weaken the comparison to make the refusal go
away. Characterize unpublished prior promotion, stale checkout, wrong workspace root and unrelated
drift as separate measured cases, and explain the Git publication → local update → Registry
synchronization sequence in product terms, with no `aart ...` command text in any TUI frame. Then
steps 11–14. The operator has asked for targeted tests and quality gates only until the batch is
finished; run the whole `tui`/`consumer`/`maintainer`/`source`/`registry`/`setup`/`promotion`/
`candidate` test file set after each step, not only the files it edits, and step 15 runs the full
suites once the batch is handed back.
