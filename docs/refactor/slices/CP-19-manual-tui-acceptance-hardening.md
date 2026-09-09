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
8. **Batch verification — TODO.** Each implementation increment gets a real RED/mutation and focused
   suites. Only after the operator hands the batch back run full `make quality` and
   `make integration`, then return the fixed items for manual retest.

## Current manual checkpoint

The Registry checkout `/Users/mifi/code/aart-e2e-work/aart-test-registry` is clean at `cc7c01d` on
`qa/publish-v1`. That commit promotes `skill/verification-before-completion@1.0.0`. There is no
remote PR yet; `origin/main` is `027ba7f`, the same revision the configured Registry source last
synchronized. Reviewing `mcp/aart-e2e-mcp@1.0.0` therefore correctly refuses the unequal baseline.

To resume discovery, publish the existing branch through Git review/merge, update the local `main`,
restart the TUI, synchronize `aart-test-registry` from screen 21 and retry the MCP Candidate. Do not
reset or discard `cc7c01d`; it is the first promotion under test.

## Evidence and gates

QA-026 was RED against the fixed footer. A semantic mutation routing advertised `b Rebuild` to the
initialization screen was killed by the headless shell walk. The focused 238-test interaction and
boundary set, changed-module `mypy`, `ruff check`, `ruff format --check` and `make docs-check` were
green. Full repository gates are intentionally deferred until step 8 at the operator's request.

## Do not undo

- Do not weaken the exact synchronized-baseline comparison to pass QA-031.
- Do not put `aart ...` commands into TUI frames.
- Do not reset a refused form on leave; reset a fresh form on entry.
- Keep `key_event` as the only key interpreter and keep application code free of IO.
- Never commit the embedded `superpowers-aart-test/` lab repository.

## Exact next implementation action

None during the current discovery pass. CP-19 step 2 is the operator's active manual walkthrough.
When implementation resumes, begin with QA-027 unless the operator explicitly prioritizes blocking
QA-031.
