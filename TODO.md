# TODO

> [!WARNING]
> Historical record of the completed `M1F1/agent-artifacts` 1.0 program, kept as evidence. It is
> preserved below and its GitHub issues are not this repository's. The first section of this file
> is now the current manual-acceptance list for `aart-cli`; it is a test/fix queue, **not** product
> authority.
> Current authority is [`docs/product-specification/PRODUCT_SPECIFICATION.md`](docs/product-specification/PRODUCT_SPECIFICATION.md),
> and the active work is tracked in [`docs/refactor/NEXT.md`](docs/refactor/NEXT.md).

## Current `aart-cli` manual-acceptance TODO

This is the single list for problems found while walking the real Registry → Marketplace →
Install → Update → Repair → Uninstall scenario. New findings go into **Open** immediately. A fix
moves to **Fixed — awaiting manual retest** and is checked only after the operator reproduces the
original steps and confirms the result.

The repeatable procedure and stage checkpoints are in
[`docs/testing/END_TO_END_ACCEPTANCE.md`](docs/testing/END_TO_END_ACCEPTANCE.md).

Each new entry records:

- the screen or public command;
- exact reproduction steps;
- expected and observed behavior;
- severity (`blocking`, `high`, `medium`, or `low`);
- whether it blocks the current end-to-end stage;
- the fixing commit once accepted.

### Open

- [ ] **QA-027 — A finished sequence has no way out but pressing Esc repeatedly.**
      Stage: after any completed Maintainer action
      Surface: Source Sync Result (34), and every result screen with no forward route
      Severity: high
      Blocks current stage: no
      Reproduction: Sources → `s` → review → Enter → Source Sync Result. Now try to add or sync
      another Source
      Expected: Enter on a result screen returns to the list the sequence started from — Sources
      for a Source action, Registry for a registry action — so the next one can begin
      Observed: Enter does nothing; the only way back is Esc, Esc, Esc through the history
      Operator's words: "jak przechodzę przez dodanie source to nie wiem jak się mam cofnąć do
      ekranu głównego... na koniec journey w danej sekwencji Enter powinien wracać do pierwszego
      ekranu danej sekcji, np. jak dodaję source i wszystko poszło dobrze, to kolejny Enter cofa
      mnie do pierwszego ekranu Source, żeby dodać kolejne"
      Note: screen 45 already does exactly this (`Enter` after the receipt goes to screen 46).
      The rule exists; it is applied to one screen instead of all of them.

- [ ] **QA-028 — Add Source opens holding the previous Source's answers.**
      Stage: adding a second authoring Source
      Surface: Add Source (31a); the same shape applies to Add Registry (21a) and Initialize
      Registry (46a)
      Severity: medium
      Blocks current stage: no
      Reproduction: add one Source, then press `a` on screen 31 again
      Expected: an empty form, so it is obvious a **new** subscription is being created
      Observed: every field still holds the previous Source's values, and nothing on screen says
      whether confirming edits the old subscription or creates another one
      Operator's words: "jak próbuję dodać nowe source to mam wartości z poprzedniego, co jest
      nieintuicyjne, bo nie wiem czy właśnie usuwam to stare i zamieniam na nowe wartości, czy
      dodaję całkowicie nowe source"
      Note: the draft is carried in `ConsumerUiState` and never reset on entry. `QA-018` requires
      a **refused** form to keep what was typed, so the reset belongs on entering the form, not on
      leaving it.

- [ ] **QA-029 — Screens are a wall of text; the action prompt is not separated from the body.**
      Stage: every review screen
      Surface: Source Sync (33), Source Sync Result (34), and reviews generally
      Severity: medium
      Blocks current stage: no
      Reproduction: open Sources → `s` and read screen 33 top to bottom
      Expected: the facts, then a blank line, then the one line that says what a key press will
      do — so `Press Enter to synchronize.` is findable without reading the whole screen
      Observed: eight dense lines with no vertical grouping, `Press Enter to synchronize.` being
      the ninth in the same block
      Operator's words: "`Press Enter to synchronize.` powinno być oddzielone, żeby było widoczne";
      "nie podoba mi się, że jest tak wiele tekstu w opisach, to się wszystko gubi i jest
      nieczytelne, powinno być więcej pustych linii pomiędzy wierszami tekstu"
      Note: related to `B-048` (refusal lines are not wrapped). This is the positive half — the
      screens need a stated layout rule, not one more line each.

- [ ] **QA-030 — The Candidates list does not hold its columns.**
      Stage: reviewing Candidates after a sync
      Surface: Candidates (35); check the other tabular lists for the same defect
      Severity: medium
      Blocks current stage: no
      Reproduction: sync two Sources so the list holds both `mcp/aart-e2e-mcp` and
      `skill/verification-before-completion`, then open screen 35
      Expected: `STATUS`, `ARTIFACT`, `VERSION`, `SOURCE` stay aligned; a name too long for its
      column is truncated, and the row under the cursor is shown in full below the list
      Observed: the header is aligned but a long artifact name pushes `VERSION` and `SOURCE` out
      of their columns, so the rows no longer line up with the header
      Operator's words: "powinno wszystko być w kolumnach, a nie taki przepchany tekst; powinno
      najwyżej ucinać nazwy, ale jak się najedzie kursorem, to pod spodem jest całość"
      Evidence:
      ```
      STATUS               ARTIFACT                 VERSION       SOURCE
      > New                mcp/aart-e2e-mcp         1.0.0         aart-test-mcp
        New                skill/verification-before-completion 1.0.0         superpowers-test
      ```

- [ ] **QA-031 — Promotion baseline refusal does not explain the unpublished Registry change.**
      Stage: promoting the second Candidate during the real Registry walkthrough
      Surface: Registry Diff (43)
      Severity: high
      Blocks current stage: yes, until the preceding Registry commit is published and synchronized
      Reproduction: promote `skill/verification-before-completion@1.0.0` into the local Registry,
      leave that commit on `qa/publish-v1` without publishing it, then review promotion of
      `mcp/aart-e2e-mcp@1.0.0` against the Registry still synchronized from remote `main`
      Expected: the safety refusal remains, but it identifies the local unpublished Registry
      change and explains the sequence in product terms: publish/review the prior change, update
      the checkout, synchronize the Registry, then review this promotion again
      Observed: screen 43 first shows a complete five-path transaction, then says only `registry
      workspace does not match the synchronized approved baseline` and `synchronize or restore the
      registry checkout`. It does not say what differs or that the preceding promotion is the
      difference, so the operator cannot tell whether to publish, discard, rebuild or synchronize
      Evidence: the lab checkout is clean at local `cc7c01d` on `qa/publish-v1`, containing the
      Skill promotion; `origin/main` and the synchronized Registry are still at `027ba7f`. The
      refusal is therefore correct, but its diagnosis and TUI recovery are not actionable.
      Note: do not weaken the baseline equality check. The future increment must first distinguish
      an unpublished local promotion, a stale checkout, the wrong workspace root and unrelated
      drift; no `aart ...` command text may enter the TUI.

- [ ] **QA-032 — A Registry produced by TUI promotion fails its generated GitHub Actions.**
      Stage: publishing the first promoted artifact through Registry PR #1
      Surface: generated `.github/workflows/aart-registry.yml`
      Severity: blocking
      Blocks current stage: yes, unless the known false-negative checks are consciously bypassed
      Reproduction: promote `skill/verification-before-completion@1.0.0` through the TUI, push the
      resulting clean commit and open a PR; observe both `registry-quality (minimum)` and
      `registry-quality (latest)`
      Expected: the generated CI validates the same versioned approved-Registry representation the
      canonical TUI promotion writes, and a public consumer would accept
      Observed: both jobs run the legacy workspace commands. `registry validate` reports a missing
      unversioned `artifact.json` plus stale `aart.lock.json`/`aart.index.json`; `registry lock`,
      `build`, `audit` and `test` fail for the same representation mismatch
      Evidence: public `source add --kind registry-git` over remote branch `qa/publish-v1` accepts
      exact commit `cc7c01d` as healthy, while generated run `34341007222` fails. This is B-057's
      remaining command disagreement reaching the real publication gate, so it is critical now.
      Note: the fix belongs in the generated workflow/template and its public validation command,
      not in weakening promoted-Registry validation or teaching promotion to write a second legacy
      representation.

- [ ] **QA-033 — A refused run remains on a stale confirmation screen.**
      Stage: Registry maintenance after a canonical promotion
      Surface: Review Rebuild (46i) after execution has already stopped
      Severity: high
      Blocks current stage: no; pressing Esc twice still reaches Registry Maintainer
      Reproduction: Registry Maintainer → `b` → choose the whole rebuild → Enter to review → Enter
      to run; let `lock` refuse because the canonical promoted Registry has no legacy
      `artifact.json`
      Expected: the screen clearly becomes a finished/refused result, removes the confirmation
      prompt and offers one honest route back to Registry Maintainer or to prepare a fresh retry
      Observed: the body says the run stopped, but the title remains `Review Rebuild`, the header
      still says `press Enter to start it`, and the footer still advertises `Enter Confirm`. The
      action adapter has already cleared its pending run, so another Enter can only answer
      `nothing was prepared for this action; review it again`.
      Note: QA-032 explains this particular lock refusal, but the stale terminal state is a
      separate reducer/result-screen defect and must hold for every failed action.

### Fixed — awaiting manual retest

- [ ] **QA-026 — The footer does not name the keys the current screen actually has.**
      Stage: every screen; found while walking Maintainer Mode
      Surface: shell chrome, every screen
      Severity: high
      Blocks current stage: no, but it makes every other finding harder to report
      Reproduction: open any screen with its own actions — 21 (`a`, `s`), 31 (`a`, `s`), 46
      (`n`, `b`, `s`, `u`), 35 (`f`, `c`), 37 (`f`) — and read the footer
      Expected: the footer lists the keys usable **here**, view-specific ones first, then the
      global movement/back/help/quit set
      Observed: the footer was one fixed legend. A screen's own keys lived in a body line the
      screen happened to draw, or nowhere at all.
      Fix: yes — contextual letter bindings now carry their displayed meaning beside the event
      they produce, and both `key_event` and the footer read that one table. Structural keys derive
      from the reducer's searchable/selectable/form/review sets. Local actions are drawn first,
      global movement/back/help/quit second; a screen no longer advertises Space when it cannot
      select anything. Screen 46's duplicate body-level `Actions:` header is gone (D-202).

- [ ] **QA-025 — Re-running a registry's generated files had no home in the TUI.**
      Stage: after promoting, adopting or editing anything in the registry checkout
      Surface: Registry (screen 46)
      Severity: high
      Blocks current stage: yes, for a TUI-only walkthrough
      Reproduction: promote a Candidate through the TUI, then try to lock, build, validate and
      audit the registry without leaving the shell
      Expected: the run the maintainer needs after every change is on the screen that owns the
      registry
      Observed: nothing offered it. The procedure was four `aart_maintainer registry ...` commands
      typed by hand, in an order and with flags (`--strict --frozen`) no screen ever named
      Evidence: `B-090` had already established that ordering is the knowledge a screen must hold;
      this is the same defect one step further along the maintainer's day (`B-099`)
      Fix: yes — screen 46 gained `b Rebuild generated files`. Screen 46h offers the whole
      sequence and each stage on its own, 46i reviews the named stages, and the run goes through
      the same authority `init` uses. `init` is not offered: a registry is created once (`D-200`).
- [ ] **QA-024 — Two review screens could not be confirmed, and no review drew its plan.**
      Stage: adding a Source and initializing a registry from the TUI
      Surface: Add Source review (31b), Initialize Registry review (46b)
      Severity: blocking
      Blocks current stage: yes
      Reproduction: fill in Add Source or Initialize Registry, continue to the review, press Enter
      Expected: the review shows the plan, and Enter runs it
      Observed: the review showed its prompt with nothing under it, and Enter did nothing at all —
      the flows could be typed and reviewed but never confirmed
      Evidence: `key_event`'s confirmation list never named those two screens, and `_ANSWERABLE`
      hand-listed five review screens while deriving the request screens, so any review or result
      screen off that list drew no notice
      Fix: yes — both screens confirm, and the notice set is now derived from both action tables
      instead of hand-listed. Found by walking the keys in a headless shell rather than by another
      adapter test, which is also how the wrong row reached the first rebuild request (`D-201`).
- [ ] **QA-022 — The TUI could not install any MCP artifact once Codex was measured.**
      Stage: installing the MCP from Marketplace in the persistent shell
      Surface: Marketplace → Install (screens 05–10)
      Severity: blocking
      Blocks current stage: yes
      Reproduction: select any `mcp` offer in the TUI on a machine whose measured harness set
      includes Codex, and open the install review
      Expected: the plan registers the server with the harnesses that can host one at this scope
      Observed: the whole placement was refused with `no measured MCP target for harness 'codex'
      at project scope`, so no MCP artifact could be installed for Claude or Tabnine either
      Evidence: the shell's profiles are the union of every measured table (`D-193`), and Codex
      registers servers only at user scope (`D-196`); `placement_for` refused a profile it could
      not place, which is correct for `--profile` and wrong for a set nobody asked for
      Fix: yes — `placement_for` now takes `profiles_requested`, the shell passes `False`, and a
      measured harness that cannot host this kind at this scope is left out of that artifact's
      plan instead of refusing it. A harness no table names is still refused by name, and a
      Selection every profile left out is still refused (D-198, 13 tests).
- [ ] **QA-023 — Settings offers an installation scope the TUI then ignores.**
      Stage: installing at user scope from the shell
      Surface: Settings (screen 28) → Marketplace → Install
      Severity: high
      Blocks current stage: yes, for user-mode acceptance
      Reproduction: set `Default scope: User` on screen 28, then install any artifact
      Expected: the artifact lands under the user's home
      Observed: it landed in the project; the preference was persisted, redrawn and never read
      Evidence: composition built the installation host with `Scope.PROJECT` hard-coded
      Fix: yes — the host's scope is derived from the stored preference at the point of use, so it
      applies in the session that changed it; each review records the host it was prepared against
      and its confirmation acts on that one; the maintainer registry root no longer follows the
      installation scope (D-199, 1 end-to-end test through the real shell).

- [ ] **QA-011 — Canonical installation cannot target OpenCode.**
      Stage: installing the Skill and MCP into the locally installed OpenCode 1.18.29
      Surface: Marketplace/TUI and `marketplace install --profile opencode`
      Severity: high
      Blocks current stage: yes, for OpenCode acceptance; no, for Claude/Tabnine
      Reproduction: select an artifact declaring OpenCode compatibility or request profile
      `opencode` explicitly
      Expected: reviewed effects use OpenCode's measured Skill, AGENTS.md and MCP configuration
      contracts
      Observed: TUI targets only Claude/Tabnine; the CLI refuses every canonical target as
      unmeasured and writes nothing
      Evidence: OpenCode 1.18.29 is installed locally; all `domain/harness.py` target lookups for
      OpenCode refuse, while the dormant `profiles/builtin.py` values are not canonical authority
      Fix: yes — Skills, instructions and MCP are measured and installable at both scopes
      (`.opencode/skills/<name>`, `.config/opencode/skills/<name>`, `AGENTS.md`,
      `.config/opencode/AGENTS.md`, the `mcp` key of `opencode.json` and
      `.config/opencode/opencode.json`), and OpenCode is selectable in the TUI through the union
      harness set (D-194, 9 tests, two of which run the installed OpenCode). MCP needed a new
      `McpEntryShape` because a local server here is `{"type": "local", "command": [...]}` rather
      than a command string beside `args`. Guidelines and hooks stay refused by name because that
      build documents no guidelines directory and its event model was not measured.
      Verified end to end (D-197): an authored server compiled, published, planned, installed and
      then started from the vector that landed in `opencode.json`, and `marketplace install
      --profile opencode --yes` landing a Skill in `.opencode/skills/<name>`. That verification
      found and fixed a reader defect that made every OpenCode MCP install end partially-applied.
- [ ] **QA-012 — Canonical installation cannot target Codex.**
      Stage: installing the Skill and MCP into the locally installed Codex CLI 0.152.0
      Surface: Marketplace/TUI and `marketplace install --profile codex`
      Severity: high
      Blocks current stage: yes, for Codex acceptance; no, for Claude/Tabnine
      Reproduction: select an artifact declaring Codex compatibility or request profile `codex`
      explicitly
      Expected: reviewed effects use Codex's measured Skill roots, layered `AGENTS.md` and
      native `mcp_servers` configuration contracts
      Observed: TUI targets only Claude/Tabnine; the CLI has no canonical Codex target and refuses
      the requested placement without writing
      Evidence: Codex CLI 0.152.0 is installed locally; Codex is absent from every canonical target
      table and from the dormant built-in profile registry
      Fix: partial — Skills and instructions are measured and installable at both scopes
      (`.codex/skills/<name>`, `AGENTS.md`, `.codex/AGENTS.md`), and harness selection now derives
      from every measured table rather than from `MCP_TARGETS` alone, so Codex is selectable
      (D-193, 10 tests, two of which run the installed Codex). The expectation above named
      `.agents/skills`; measurement found that is the cross-vendor interop root Codex also migrates
      other agents from, and `.codex/skills` is its own. MCP stays refused by name because Codex
      writes its own MCP configuration now (D-196, B-096 closed): `codex mcp add`/`remove`/`list
      --json` were measured leaving an operator's comments, unrelated keys and other servers
      byte-identical, so the user-scope target delegates to them and a missing Codex is named
      rather than reported as registered. Verified end to end: Codex lists the server the install
      registered and the launcher it was handed starts the author's server. User scope only —
      `codex mcp add` offers no project flag, so project scope is still refused by name. Hooks are
      measured and still refused (B-097): `codex
      features list` reports them stable and enabled, but they are configured through a path in
      `config.toml`, project-local hooks are disabled until the operator trusts the project, and
      every new or changed hook is held for interactive review — a file AART wrote would not run.

- [ ] **QA-021 — Registry cannot one-off scan YAML manifests and vendor selected artifacts.**
      Stage: optional artifact-scoped onboarding from an external repository
      Surface: Maintainer → Registry
      Severity: high
      Blocks current monitored-Source stage: no; this is a second required onboarding model
      Reproduction: provide the Superpowers URL/ref without adding it as a configured Source, then
      try to discover its `aart.yaml` files and select one Skill for Registry ownership
      Expected: `Scan Repository` finds only explicit YAML/JSON manifests, presents selectable
      artifacts, and vendors only each selected manifest's `payload.include` files with pinned
      provenance; the repository is not saved as a Source
      Observed: `registry scan` reads YAML but only prints a local-checkout result, `discover` looks
      for conventional shapes, and `vendor` ignores YAML and requires repeated metadata flags
      Evidence: no public command or TUI action composes author-manifest discovery with selected
      vendoring; existing commands each stop at a different boundary
      Fix: complete — `io/registry_adoption.py` composes scan → selection → atomic vendored
      adoption with pinned provenance and saves no Source (D-187, 14 tests). Maintainer Registry
      exposes that flow as `s` Scan Repository: form 46c, selectable result 46d and exact local
      adoption review 46e (D-188, 8 tests). Adopted packages retain the moving branch/tag as
      immutable namespaced provenance (D-189). The read-only check distinguishes unchanged,
      changed, missing, unreachable and invalid manifests, and prepares a new immutable version
      only after an upstream version bump (D-190, 8 tests), reached as `u` Check upstream on
      screens 46f/46g (D-191). `aart registry adopt` and `aart registry check-upstream` are the
      machine-complete CLI projection: scan/review/apply phases, `--expect` verified whenever
      given, sorted listings (D-192, 8 tests).

- [ ] **QA-016 — A new Registry cannot be initialized through Maintainer TUI.** Screen 46 now
      offers `n` Initialize Registry with its own id/name/reporting/commit form (46a) and an exact
      review (46b) that names all five stages. One confirmation runs init → lock → build → validate
      → audit, fail-fast, through the same curation service and planning gates the CLI drives, and
      draws stage by stage what each did. The local commit is opt-in and part of the review digest;
      nothing is ever pushed or merged. B-090/D-186.
- [ ] **QA-015 — Audit of a valid empty Registry reports non-actionable warnings as problems.** The
      provenance-coverage and installation-risk findings are now `info` notes when the registry
      holds neither an external reference nor an owned package, and warnings again as soon as
      either exists. `registry init` also stopped warning that the usage-reporting templates were
      inert, because D-180 no longer writes them. B-089/D-181.
- [ ] **QA-014 — Successful `registry init --yes` output is overwhelming and repetitive.** The
      outcome no longer repeats the warnings its review just stated, drops the `observed:` line
      when it equals the headline's own count, and the follow-up commands are the AART pipeline
      without the `git diff` line that re-listed every reviewed path. `--json` still carries review
      and outcome in full. B-088/D-182.
- [ ] **QA-019 — Git Source rejects a symlink without naming what is unsafe or how to proceed.**
      The refusal is unchanged and still fail-closed; it now names the entry kind it observed —
      symbolic link, submodule, unsupported Git mode, unsafe path or excessive depth — and carries
      remediation for each. The link target is never printed. A submodule is also no longer
      reported as a malformed listing. B-093/D-183.
- [ ] **QA-018 — A refused Registry connection leaves the user stranded on Review Registry.** A
      declined preparation now returns to the screen the action was asked from — for Add Registry
      the form, with the typed values intact — and clears the pending action, so a later Enter
      cannot reach a confirmation. The refusal is drawn on that screen, because `_ANSWERABLE` now
      derives the request origins from `_ACTION_REVIEW`. B-092/D-184.
- [ ] **QA-017 — TUI exposes raw CLI remediation commands after adding a Registry.** `Diagnostic`
      gained `interactive`, the same next step written for somebody already inside the application;
      `_refusal` renders that, or the remediation steps that name no command. The duplicate alias,
      duplicate origin, changed-identity and unsynchronized-source refusals all carry prose. A
      sweep over every screen asserts no frame draws an `aart <verb>` command, and a Hypothesis
      property holds the universal half. CLI and JSON keep their exact remediation. B-091/D-185.
- [ ] **QA-010 — Consumer TUI cannot synchronize a configured Registry.** Screen 21 now routes `s`
      to its own Refresh Registry action with a review (21c) that names the ref to be fetched,
      states that a refresh is not an artifact update, and warns that a failed fetch keeps the
      snapshot already held. Execution goes through `sync_configured_sources`, the same transaction
      as `aart source sync`. B-084/D-179.
- [ ] **QA-013 — `registry init` generates unused usage-reporting automation by default.** The
      usage-reporting Issue Form and its two workflows are now generated only when
      `--usage-reporting-repository` names a destination, and the generated README describes the
      registry that was actually created. B-087/D-180.
- [ ] **QA-020 — A YAML authoring repository cannot enter the monitored Source → Candidate flow.**
      Authoring-Source admission is now manifest discovery rather than native-package validation:
      `source add --kind source-git` admits a repository that declares at least one explicit
      `aart.yaml`/`aart.json`, keeps the native-package rule for a tree that declares
      `aart-source.json`, and still refuses a tree that declares neither. Transport, identity,
      symlink, special-file and last-known-good boundaries are unchanged. An authoring Source
      contributes no Marketplace offers and cannot empty the consumer's Marketplace. B-094/D-176.
- [ ] **QA-009 — Maintainer TUI cannot add an authoring Source.** Screen 31 now offers `a` Add
      Source with its own alias/kind/location/ref form (31a), an exact Review (31b) and confirmed
      execution through the canonical source-add transaction. It accepts only `source-git` and
      `source-local`; `registry-git` stays screen 21a's. B-083/D-177.
- [ ] **QA-001 — The TUI does not advertise its navigation keys.** The permanent footer now names
      arrows, Enter, Space, Esc, help and quit, and remains pinned below long content. B-077/D-168.
- [ ] **QA-002 — Esc returns to the previous screen noticeably slowly.** The curses escape-prefix
      delay is now bounded at 50 ms. B-078/D-169.
- [ ] **QA-003 — Dashboard destinations do not explain what they mean.** Moving the cursor now
      shows a short description of the highlighted destination. B-079/D-170.
- [ ] **QA-004 — An empty first run does not explain AART or what to do next.** A first-run panel
      now appears above navigation and points to Registry onboarding. B-080/D-170.
- [ ] **QA-005 — Old user subscriptions look like built-in registries.** The two persisted August
      subscriptions and their managed snapshots were removed through `aart source remove`; a fresh
      public list is empty. B-081.
- [ ] **QA-006 — Registry cannot be added from the TUI.** Screen 21 now provides Add Registry with
      alias, credential-free Git URL, branch/tag, default choice, exact Review and confirmed
      connection through the canonical source-add transaction. B-082/D-171.
- [ ] **QA-007 — The permanent legend omits Space.** It now states `Space select/toggle`.
- [ ] **QA-008 — First-run setup guidance is visually buried below navigation.** It now appears
      first as a distinct `SETUP REQUIRED` callout above the menu.

### Confirmed

Move an entry here only after manual retest, preserving its checkbox, result date and fixing commit.

---

Backup implementation tracker for that program. Its GitHub issues were the source of truth for
discussion and status *there*; in this repository they are neither, and nothing here should be
kept aligned with them.

## Post-1.0.0 follow-ups

Execution order, acceptance criteria, and handoff steps live in
[`docs/plan/PLAN-post-v1-catalog-boundary.md`](docs/plan/PLAN-post-v1-catalog-boundary.md).

- [ ] Create/link a new post-1.0 GitHub issue for CB01 before its review PR. Issue #27 is the
      completed historical 1.0 program, not the source of truth for this follow-up.
- [ ] Expose the full canonical non-interactive lifecycle for agents: qualified marketplace
      install, update, uninstall, and setup. `aart source add/list` and `aart marketplace list`
      bootstrap and inspect the marketplace, while retained `list/install/update/setup --source`
      commands are explicit 0.1 compatibility adapters.
- [ ] Add a configuration-scoped lock and expected-digest compare-and-swap write path for source
      additions and source-selection changes. A fresh re-read after sync is not enough to prevent
      a concurrent configuration writer from being lost.
- [ ] Update the registry-owned `agent-artifacts` and `author-aart-installer` skills in a separate
      `M1F1/agent-artifacts-registry` PR: rewrite the stale embedded-catalog instructions, bump
      both artifact versions to `2.0.0`, remove invalid legacy provenance, and regenerate lock and
      index through registry gates. The same PR must teach `author-aart-installer` the only
      supported recipe revision — `schema_version`/`protocol_version` both `2`, the required
      package-root `SETUP.md` written before the recipe, and the
      `# AART manual setup: see ../SETUP.md` header on any custom entrypoint. Worked packages to
      copy from: `tests/fixtures/setup-routes/`.
- [ ] Define a new versioned release contract before the next AART release. Preserve the immutable
      `v1.0.0` schema-freeze/release evidence rather than rewriting it for post-release changes.

## [#27 — AART 1.0: federated artifact compiler and optional registries](https://github.com/M1F1/agent-artifacts/issues/27)

Product requirements:
[`docs/product/PRD-aart-1.0.md`](docs/product/PRD-aart-1.0.md). Technical contract:
[`docs/design/SPEC-aart-1.0.md`](docs/design/SPEC-aart-1.0.md). Task sequencing and quality gates:
[`PLAN.md`](PLAN.md). Durable execution state: [`PROGRESS.md`](PROGRESS.md).

### Architecture and release

- [x] Separate the AART compiler/tool repository from operational artifact registries.
- [x] Define a federated marketplace with zero or more direct sources/registries and an optional
      default registry.
- [x] Define native references, materialized foreign imports, and direct source subscriptions.
- [x] Treat importers as deterministic Maintainer-time migration/curation tools, never consumer
      runtime conversion.
- [x] Write the AART 1.0 PRD and technical specification.
- [x] Start implementation versions at `1.0.0a1`; do not tag `1.0.0` before the release gates pass.
- [x] Freeze the 1.0 schemas, publish compatibility/migration/release evidence, and finalize stable
      `1.0.0` only through the fail-closed REL01 checklist.

### Protocol and compiler

- [x] Implement strict JSON schemas for native sources, artifacts, provenance, and collections.
- [x] Implement strict registry, native entry, committed lock, and compiled index schemas.
- [x] Implement strict JSON schemas and canonical writers for user configuration and organization
      policy.
- [x] Implement the strict canonical installation manifest v2 schema and migration evidence model,
      documented in
      [`docs/state/installation-state-v2.md`](docs/state/installation-state-v2.md).
- [x] Implement strict schema-v1 structured command outcomes and shared terminal summaries.
- [x] Implement SemVer bounds, protocol/capability negotiation, and canonical JSON/tree digests.
- [x] Implement qualified marketplace resolution and ambiguity diagnostics without silent source
      shadowing.
- [x] Resolve user selections as source-qualified marketplace coordinates at CLI/TUI application
      boundaries; ambiguous unqualified identities fail closed.
- [x] Implement deterministic registry-input hashing, graph validation, index generation, and
      frozen registry lock resolution.
- [x] Implement typed deterministic compiler phases, accumulated diagnostics, immutable candidate
      planning, injected effect ports, and publication gating.
- [x] Supply the concrete source/compatibility/effects graph compiler on the phase framework.
- [x] Implement the closed built-in importer registry plus deterministic legacy-catalog conversion,
      provenance, loss/ambiguity checks, and stale-output validation.
- [x] Implement promotion of native direct sources into registries and locked importer reruns.
- [x] Add registry quality gates for format, validate, lock, build, audit, diff, and compatibility
      tests, documented in
      [`docs/registry/maintainer-commands-v1.md`](docs/registry/maintainer-commands-v1.md).

### Federated sources and managed store

- [x] Add user configuration for zero or more local/Git source and registry aliases, with at most
      one optional default registry.
- [x] Add organization policy for recommended/required sources, allowed Git hosts/prefixes, setup
      capabilities, minimum user-scope trust, custom setup, and reporting destinations.
- [x] Extend policy and marketplace consumption with exact company-reviewed source identity and
      effective trust evidence.
- [x] Enforce operation-specific scope/trust/setup gates in the installation and setup tasks.
- [x] Implement Git mirrors, immutable validated snapshots, atomic current pointers, health/doctor,
      concurrency control, and offline last-known-good behavior.
- [x] Implement the content-addressed artifact object store with digest verification, safe GC, and
      install/setup references.
- [x] Merge configured sources deterministically without silent shadowing and display effective
      source/trust for every artifact.

### Consumer and TUI migration

- [x] Add a source-aware canonical Copy prepare/review/finalize boundary over qualified marketplace
      items and verified immutable CAS objects, documented in
      [`canonical-copy-v1.md`](docs/installation/canonical-copy-v1.md).
- [x] Apply canonical file, tree, managed-block, and JSON merge effects transactionally; pin
      manifest-v2 evidence and a durable installed-object reference with structured no-op,
      conflict, failure, and rollback outcomes.
- [x] Add durable managed file/tree Symlinks to exact immutable CAS payloads, mixed copied merges,
      explicit atomic retarget/reference replacement, link-state evidence, and opt-in verified
      `mutable-local` developer links, documented in
      [`canonical-symlink-v1.md`](docs/installation/canonical-symlink-v1.md).
- [x] Resolve Install/Update from qualified source subscriptions and immutable objects.
- [x] Keep Copy as default and make managed Symlink target immutable store content; sync alone must
      not retarget installed artifacts.
- [x] Add canonical local status, fetch-free check, recorded-subscription update, explicit upstream
      prune, proven-effect uninstall, per-selection outcomes, scope isolation, and CAS-reference
      release, documented in
      [`canonical-lifecycle-v1.md`](docs/installation/canonical-lifecycle-v1.md).
- [x] Migrate project/user manifests, scope/profile compatibility, managed merges, uninstall proof,
      setup state, and structured outcomes to manifest v2.
- [x] Add the Sources/health stage to the persistent TUI while preserving Backspace state, basket,
      Review/Finalize, descriptions, modes, scopes, and explicit outcomes, documented in
      [`source-management-v1.md`](docs/tui/source-management-v1.md).
- [x] Migrate the User TUI to qualified federated marketplace rows, canonical multi-item
      Review/Finalize requests, verified registry security evidence, persistent cart navigation,
      and explicit no-op/partial/offline/setup outcomes, documented in
      [`consumer-marketplace-v1.md`](docs/tui/consumer-marketplace-v1.md).
- [x] Migrate canonical Maintainer TUI actions to digest-bound local-checkout plans for registry
      init/scaffold, native promotion/update, controlled foreign conversion, lock/build,
      validate/audit/diff, and explicit outcomes; retain the legacy catalog workflow without
      automatic commit/push or consumer-store writes, documented in
      [`maintainer-curation-v1.md`](docs/tui/maintainer-curation-v1.md).
- [x] Bind reviewed macOS setup recipes to source trust and artifact/recipe/plan digests, retain the
      exact CAS object, execute custom code from a verified private copy, and preserve separate
      payload/setup outcomes, documented in
      [`canonical-setup-v1.md`](docs/installation/canonical-setup-v1.md).
- [x] Keep reporting disabled without an explicit destination; route configured reports only to
      the policy-approved registry service; preview exact redacted events; isolate provider
      failures; and supply bounded registry validation/aggregation/dashboard templates, documented
      in [`usage-reporting-v1.md`](docs/reporting/usage-reporting-v1.md).

### Installation-risk assessment

- [x] Add a zero-runtime-dependency baseline that reports deterministic object/rules-digest-bound
      installation-risk evidence, explicit coverage and remediation, documented in
      [`baseline-v1.md`](docs/security/baseline-v1.md), without certifying an artifact.
- [x] Add a versioned out-of-process JSON protocol for independently installed analyzers; never
      auto-install them or import them into the AART process.
- [x] Add optional adapters/suites for applicable open-source analyzers while preserving the
      stdlib-only AART runtime.
- [x] Add digest-bound evidence indexes, freshness handling, deterministic bundle aggregation,
      and policy gates based on worst/unknown status rather than average alone, documented in
      [`attestations-v1.md`](docs/security/attestations-v1.md). Cryptographic signing remains a
      separately versioned future protocol.
- [x] Show provider, rules version, evidence age, coverage, risk range, and remediation details in
      CLI/TUI marketplace, review, maintainer, and outcome views.
- [x] Test malicious provider output, timeout, crash, stale/mismatched evidence, partial bundle
      coverage, offline behavior, and policy enforcement.

### Repositories, migration, and verification

- [x] Create the public `M1F1/agent-artifacts-registry` reference marketplace during SEP01, only
      after the deterministic export and public-content preflight pass.
- [x] Provide a confidential-content-free `aart registry init` bootstrap and minimum/latest CI
      template for a company registry.
- [x] Provide deterministic, reviewable conversion of the current top-level 0.1.x catalog into a
      canonical native source.
- [x] Promote the converted top-level 0.1.x catalog into the canonical registry layout during the
      reviewed SEP01 migration.
- [x] Add reviewed dry-run/apply/backup/rollback migration primitives for existing 0.1.x
      installation state; MIG01 supplies the final public compatibility orchestration.
- [x] Test direct-source-only, multi-registry, company-plus-team, native-reference, foreign-import,
      collision, trust, offline, concurrency, Copy/Symlink, setup, and reporting fixtures.
- [x] Test local editable and local-wheel installation without an embedded operational registry or
      checkout-relative runtime data.
- [x] Prove deleting/recreating the Python environment does not break managed artifact symlinks.
- [x] Run registry CI with the minimum supported and latest compatible AART versions.

## Completed 0.1.x TUI and installation UX

## [#15 — TUI: add User/Maintainer entry paths and maintainer workflows](https://github.com/M1F1/agent-artifacts/issues/15)

- [x] Make User/Maintainer selection the first screen in both curses and text TUI modes.
- [x] Explain each path in one line:
  - User installs, updates, and removes artifacts from subscribed/recorded catalog sources.
  - Maintainer can do the same and also curate the catalog and its upstreams.
- [x] Keep the existing profile-aware install/update/uninstall flow in User mode.
- [x] Record enough source/subscription identity for updates without asking for the repository
      again.
- [x] Add guided Maintainer workflows for:
  - adding one upstream from a GitHub URL;
  - scanning a repository/path and selecting detected artifacts to import;
  - optionally adding imported artifacts to a bundle;
  - checking all or selected tracked upstreams;
  - previewing and applying upstream updates;
  - validating the catalog before and after mutations;
  - showing artifact counts, tracked/untracked state, validation failures, and upstreams needing
    attention.
- [x] Make the active catalog checkout/source explicit and reject ambiguous catalog mutations.
- [x] End maintainer mutations with next steps such as reviewing the diff and running validation;
      never commit automatically.
- [x] Reuse Request objects and existing command/core logic instead of duplicating it in the TUI.
- [x] Cover role selection, clean quit, invalid catalog context, and upstream workflows in tests.
- [x] Document the distinction between reviewed consumer updates and maintainer catalog updates.

## [#16 — TUI: show a one-line description for every installable artifact](https://github.com/M1F1/agent-artifacts/issues/16)

- [x] Add a normalized description field to Artifact and populate it in every catalog parser.
- [x] Read descriptions from:
  - Markdown frontmatter for skills, guidelines, and memory;
  - JSON descriptors for MCP servers and hooks;
  - the existing bundle description field.
- [x] Require a non-empty, single-line, user-facing description during catalog validation.
- [x] Add concise, value-oriented descriptions to every shipped artifact and fixture.
- [x] Show descriptions for artifact and bundle rows in both TUI frontends.
- [x] Keep each selector row to one visual line, truncate with an ellipsis on narrow terminals,
      and provide a way to view the full text.
- [x] Expose the same description in human and JSON list output.
- [x] Retain descriptions after compatibility filtering and in update/uninstall views when source
      metadata is available.
- [x] Test all artifact types, bundles, invalid descriptions, narrow terminals, and JSON output.
- [x] Document description authoring conventions for catalog maintainers.

## [#17 — TUI: provide explicit outcome summaries for every action](https://github.com/M1F1/agent-artifacts/issues/17)

- [x] Introduce a shared structured action-result/summary contract; do not parse command stdout in
      the TUI.
- [x] Always leave a visible final summary after curses exits and in the text fallback.
- [x] Report, at minimum:
  - install: installed/reinstalled, copied, symlinked, skipped, and failed targets;
  - update: selected, changed, already current, skipped, conflicted, and failed targets;
  - uninstall: removed, already absent/not matched, preserved user content, and failures;
  - maintainer actions: scanned/imported/checked/updated upstream counts;
  - cancellation or empty selection: explicitly state that no changes were made.
- [x] Make a successful no-op explicit, for example: “Updated 0 artifacts; all 5 selected
      artifacts are already up to date.”
- [x] Distinguish an empty selection from an already-up-to-date selection.
- [x] Preserve appropriate non-zero exit codes for conflicts, partial failures, and errors.
- [x] Keep warnings and recovery instructions visible alongside the summary.
- [x] Provide equivalent counts and item lists in human and JSON output.
- [x] Test successful, no-op, empty, conflict, partial-success, and failure paths in both TUI modes.

## [#18 — TUI: let users choose copy or symlink install mode](https://github.com/M1F1/agent-artifacts/issues/18)

- [x] Add an Install-only mode screen to curses and text TUI:
  - Copy (recommended): install an independent snapshot;
  - Symlink: live-link supported directory artifacts to a local catalog.
- [x] Keep Copy as the default.
- [x] Pass the choice through Request.install_mode/the existing CLI link behavior.
- [x] Explain that Symlink is local-source-only and currently applies to linkable skills/hooks;
      merged and file artifacts still use copy semantics.
- [x] Reject remote-only symlink sources before mutation and explain how to select a local source.
- [x] Disable/hide individual non-linkable rows with a reason instead of failing late.
- [x] Disclose mixed bundle behavior before confirmation, including linked/copied counts.
- [x] Show source, destination scope/path, harness, and mode on the confirmation screen.
- [x] Report the actual mode used for each artifact in the completion summary.
- [x] Preserve recorded modes during update and remove only managed links during uninstall.
- [x] Test default Copy, Symlink, navigation, source validation, non-linkable artifacts, mixed
      bundles, manifest metadata, update, and uninstall.

## [#19 — Support project-scoped and user-global installs per harness](https://github.com/M1F1/agent-artifacts/issues/19)

- [x] Add a core/CLI scope option such as `--scope project|user`; keep Project as the default.
- [x] Let the TUI select scope before loading install/status/update/uninstall choices.
- [x] Explain the choices:
  - Project configures only the current repository;
  - User configures the selected harness for the current user.
- [x] Model explicit project and user destinations per harness and artifact type; do not derive
      global paths by blindly prepending the home directory.
- [x] Verify supported user-global paths against current official harness documentation.
- [x] Explicitly mark unsupported harness/type/scope combinations and explain them in the TUI.
- [x] Keep separate project and user manifests/state so update and uninstall never cross scopes.
- [x] Store resolved destinations, harness, source/subscription, install mode, and managed effects,
      but never secrets.
- [x] Reject ambiguous combinations such as `--scope user` with `--project` before mutation.
- [x] Show resolved absolute destinations and ask for confirmation before user-global writes.
- [x] Prevent multi-harness operations from overwriting another harness's state.
- [x] Test with a temporary fake home/state directory; never touch real global harness config.
- [x] Preserve existing project behavior when scope is omitted.
- [x] Document project/user precedence and scoped install/update/uninstall examples.

## [#20 — Support queued per-artifact interactive setup installers on macOS](https://github.com/M1F1/agent-artifacts/issues/20)

- [x] Define and validate a reviewed, per-artifact macOS setup convention, for example an
      `install.sh` plus metadata for OS support, purpose, and credential/help URLs.
- [x] Only run scripts shipped with the reviewed artifact source; never auto-run a script directly
      from an unreviewed network response.
- [x] After core artifact installation, queue setup-capable selected artifacts and run their
      installers sequentially in the foreground.
- [x] Allow each installer to:
  - explain the configuration it will perform;
  - show a direct credential/help URL and wait for the user;
  - read secrets without echoing them;
  - store secrets in macOS Keychain;
  - create only explicit, managed, idempotent configuration/snippets;
  - verify setup and return a meaningful exit status.
- [x] Account for subprocess limitations: scripts cannot export variables into the parent TUI;
      use a durable Keychain plus managed shell/harness lookup and explain restart requirements.
- [x] On failure/cancellation, preserve earlier successes, mark setup incomplete, and continue to
      the next installer unless the user stops the queue.
- [x] Distinguish “installed and configured” from “artifact installed, setup incomplete.”
- [x] List every incomplete installer with a safe retry command and offer a preselected TUI retry.
- [x] Add a first-class CLI setup/retry runner using the same validation and state tracking.
- [x] Never put credentials in argv, manifests, logs, stdout, or JSON output.
- [x] Before execution, show artifact name, reviewed source identity, script path, and requested
      effects, then require explicit consent.
- [x] Use a controlled working directory, documented minimal environment, and safely quoted paths.
- [x] Record only non-secret status, installer version/hash, timestamps, and exit status.
- [x] On non-macOS systems, do not execute the installer and show a clear unsupported message.
- [x] Test with fake installers and a fake Keychain command: success, hidden input, failure,
      cancellation, continue/stop, idempotent retry, and secret redaction.
- [x] Add a representative MCP setup fixture or reviewed example (Atlassian preferred).
- [x] Document the trust model, authoring contract, retry flow, and the role of SETUP.md as
      optional reference rather than the primary guided setup path.

## [#21 — TUI: add onboarding, progress stepper, back navigation, and persistent selections](https://github.com/M1F1/agent-artifacts/issues/21)

- [x] Start text and curses sessions with a concise controls/onboarding screen.
- [x] Derive an accessible, non-color-only progress stepper from the applicable User or Maintainer
      stage graph and keep it usable in narrow terminals.
- [x] Model navigation, confirmations, basket values, notices, and curses cursor/scroll positions
      in one immutable `WizardSession` shared by both frontends.
- [x] Support one-stage Back on every applicable screen (`KEY_BACKSPACE`, `127`, and `8` in
      curses; `b`/`back` in text) without dispatching or losing valid selections.
- [x] Preserve the artifact/bundle/upstream basket across Review/Edit and selectively remove only
      choices invalidated by earlier edits, with a visible reason.
- [x] Show complete Review facts from issues #15–#20, including descriptions, source, scope,
      destinations, projected install modes, warnings, structured outcomes, and setup queue.
- [x] Make Finalize the sole consumer/upstream apply boundary; keep curses teardown before command
      dispatch and setup execution.
- [x] Preserve Maintainer validation/dry-run preview while moving catalog apply behind Finalize.
- [x] Confirm quit when the basket is non-empty and explicitly report that cancellation made no
      changes.
- [x] Cover pure transitions/rendering, text and curses adapters, Maintainer flows, real lifecycle
      E2E, and all repository quality gates.
- [x] Document onboarding, navigation, basket persistence, Review, and Finalize behavior.
