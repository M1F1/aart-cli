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
3. **Completed-sequence navigation (QA-027) — TODO.** Characterize every result screen with no
   forward decision. Enter returns to the owning list, beginning with Source Sync Result → Sources;
   confirmation screens must remain confirmations until their action has run.
4. **Form lifecycle (QA-028) — TODO.** Entering Add Registry, Add Source or Initialize Registry for
   a new action resets its draft. A preparation refusal stays on the form with the typed draft
   intact, preserving QA-018/D-184.
5. **Review layout (QA-029) — TODO.** State one layout rule for every review: facts, blank
   separation, decision/action prompt. Do not patch Source Sync alone; keep refusal wrapping B-048
   separate unless it becomes necessary to satisfy the rule.
6. **Stable tabular projections (QA-030) — TODO.** Bound each column, truncate only the list row and
   show the focused value in full below it. Survey the other Maintainer tables before choosing the
   shared projection boundary.
7. **Registry baseline diagnosis and recovery (QA-031/B-100) — TODO.** Preserve exact baseline
   equality. Characterize unpublished prior promotion, stale checkout, wrong workspace root and
   unrelated drift separately. The measured first case must explain the Git publication → local
   update → Registry synchronization sequence in product terms without embedding CLI commands.
8. **Git publication transition (QA-034/B-102) — TODO, CRITICAL.** Characterize the real sequence
   promotion → local commit → Git review/merge → configured Registry sync. Preserve
   `promoted-local` before publication, but make a version read from the configured published Git
   boundary available to Marketplace. No fixture may call `publish_registry_version` on behalf of
   a public flow; the test must prove the actual boundary performs the transition.
9. **Canonical Registry maintenance and CI (QA-025/QA-032/B-057/B-099) — TODO, CRITICAL.** Provide
   public read-only validation and appropriate deterministic maintenance for the checked-out
   versioned Registry representation. Make both TUI Rebuild and the generated workflow use the
   authority paired with promotion's output. Keep compatibility/audit coverage explicit. Do not
   make promotion emit the legacy authoring workspace as a second truth merely to satisfy old
   commands.
10. **Failed-action terminal state (QA-033/B-101) — TODO.** Once an attempted action refuses, replace
   its review/confirmation state with an explicit failed result. The pending plan is already gone,
   so the footer may not advertise confirmation; offer the owning list or a freshly prepared retry.
   Characterize this across action kinds rather than special-casing Registry rebuild.
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

The Marketplace-to-lifecycle half of discovery cannot continue honestly until step 8 closes
QA-034. The operator may keep collecting navigation and layout observations, but must not treat an
empty Marketplace as the expected result or synthesize an offer by editing Registry JSON. Do not
run Rebuild again until step 9 is implemented, and do not discard the local MCP promotion or
adoption transaction.

## Evidence and gates

QA-026 was RED against the fixed footer. A semantic mutation routing advertised `b Rebuild` to the
initialization screen was killed by the headless shell walk. The focused 238-test interaction and
boundary set, changed-module `mypy`, `ruff check`, `ruff format --check` and `make docs-check` were
green. Full repository gates are intentionally deferred until step 15 at the operator's request.

## Do not undo

- Do not weaken the exact synchronized-baseline comparison to pass QA-031.
- Do not put `aart ...` commands into TUI frames.
- Do not reset a refused form on leave; reset a fresh form on entry.
- Keep `key_event` as the only key interpreter and keep application code free of IO.
- Never commit the embedded `superpowers-aart-test/` lab repository.

## Exact next implementation action

The discovery pass is now blocked at Marketplace by QA-034. When Claude resumes implementation,
start with CP-19 step 8 and prove the defect over an actual Git merge/sync boundary. Do not use the
fixture shortcut that calls `publish_registry_version` before the repository exists. Then execute
step 9 so the same canonical representation passes local TUI maintenance and generated CI.
