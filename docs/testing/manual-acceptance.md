# Manual acceptance

This is the one list of problems found while an operator walks AART by hand: Registry →
Marketplace → Install → Update → Repair → Uninstall. It is a test and fix queue, not product
authority — the [Product Specification](../product-specification/PRODUCT_SPECIFICATION.md) is.

The walks themselves are [`TUI_MANUAL_WALKTHROUGH.md`](TUI_MANUAL_WALKTHROUGH.md) for the terminal
application and [`END_TO_END_ACCEPTANCE.md`](END_TO_END_ACCEPTANCE.md) for the command line.

## How an entry moves

1. A new finding goes into **Open** immediately.
2. A fix moves it to **Fixed — awaiting retest**, with the fix and its evidence.
3. It is checked and moved to **Confirmed** only after the operator repeats the original steps and
   confirms the result, with the date and the fixing commit.

Each entry records:

- the screen or public command;
- exact reproduction steps;
- expected and observed behaviour;
- severity (`blocking`, `high`, `medium`, or `low`);
- whether it blocks the current end-to-end stage;
- the fixing commit once accepted.

## Open

- [ ] **CP-23 owner acceptance walk.** Tasks 01–16 of
      [`CP-23`](../refactor/slices/CP-23-actionable-tui-workflows.md) are implemented and their
      gates are recorded; the walkthrough's *CP-23 acceptance* checklist has not been walked by the
      owner yet.

## Fixed — awaiting retest

- [ ] **QA-001 — The TUI does not advertise its navigation keys.** The permanent footer now names
      arrows, Enter, Space, Esc, help and quit, and remains pinned below long content. B-077/D-168.

- [ ] **QA-002 — Esc returns to the previous screen noticeably slowly.** The curses escape-prefix
      delay is now bounded at 50 ms. B-078/D-169.

- [ ] **QA-003 — Dashboard destinations do not explain what they mean.** Moving the cursor now
      shows a short description of the highlighted destination. B-079/D-170.

- [ ] **QA-004 — An empty first run does not explain AART or what to do next.** A first-run panel
      now appears above navigation and points to Registry onboarding. B-080/D-170.

- [ ] **QA-005 — Old user subscriptions look like built-in registries.** The two persisted August
      subscriptions and their managed snapshots were removed through `aart-cli source remove`; a fresh
      public list is empty. B-081.

- [ ] **QA-006 — Registry cannot be added from the TUI.** Screen 21 now provides Add Registry with
      alias, credential-free Git URL, branch/tag, default choice, exact Review and confirmed
      connection through the canonical source-add transaction. B-082/D-171.

- [ ] **QA-007 — The permanent legend omits Space.** It now states `Space select/toggle`.

- [ ] **QA-008 — First-run setup guidance is visually buried below navigation.** It now appears
      first as a distinct `SETUP REQUIRED` callout above the menu.

- [ ] **QA-009 — Maintainer TUI cannot add an authoring Source.** Screen 31 now offers `a` Add
      Source with its own alias/kind/location/ref form (31a), an exact Review (31b) and confirmed
      execution through the canonical source-add transaction. It accepts only `source-git` and
      `source-local`; `registry-git` stays screen 21a's. B-083/D-177.

- [ ] **QA-010 — Consumer TUI cannot synchronize a configured Registry.** Screen 21 now routes `s`
      to its own Refresh Registry action with a review (21c) that names the ref to be fetched,
      states that a refresh is not an artifact update, and warns that a failed fetch keeps the
      snapshot already held. Execution goes through `sync_configured_sources`, the same transaction
      as `aart-cli source sync`. B-084/D-179.

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

- [ ] **QA-013 — `registry init` carries no withdrawn usage-reporting automation.** The obsolete
      Issue Form, validation workflow and dashboard/Pages workflow are not generated, advertised,
      or offered by the command. CP-25.06/D-292.

- [ ] **QA-014 — Successful `registry init --yes` output is overwhelming and repetitive.** The
      outcome no longer repeats the warnings its review just stated, drops the `observed:` line
      when it equals the headline's own count, and the follow-up commands are the AART pipeline
      without the `git diff` line that re-listed every reviewed path. `--json` still carries review
      and outcome in full. B-088/D-182.

- [ ] **QA-015 — Audit of a valid empty Registry reports non-actionable warnings as problems.** The
      provenance-coverage and installation-risk findings are now `info` notes when the registry
      holds neither an external reference nor an owned package, and warnings again as soon as
      either exists. B-089/D-181.

- [ ] **QA-016 — A new Registry cannot be initialized through Maintainer TUI.** Screen 46 now
      offers `n` Initialize Registry with its own id/name/commit form (46a) and an exact
      review (46b) that names all five stages. One confirmation runs init → lock → build → validate
      → audit, fail-fast, through the same curation service and planning gates the CLI drives, and
      draws stage by stage what each did. The local commit is opt-in and part of the review digest;
      nothing is ever pushed or merged. B-090/D-186.

- [ ] **QA-017 — TUI exposes raw CLI remediation commands after adding a Registry.** `Diagnostic`
      gained `interactive`, the same next step written for somebody already inside the application;
      `_refusal` renders that, or the remediation steps that name no command. The duplicate alias,
      duplicate origin, changed-identity and unsynchronized-source refusals all carry prose. A
      sweep over every screen asserts no frame draws an `aart <verb>` command, and a Hypothesis
      property holds the universal half. CLI and JSON keep their exact remediation. B-091/D-185.

- [ ] **QA-018 — A refused Registry connection leaves the user stranded on Review Registry.** A
      declined preparation now returns to the screen the action was asked from — for Add Registry
      the form, with the typed values intact — and clears the pending action, so a later Enter
      cannot reach a confirmation. The refusal is drawn on that screen, because `_ANSWERABLE` now
      derives the request origins from `_ACTION_REVIEW`. B-092/D-184.

- [ ] **QA-019 — Git Source rejects a symlink without naming what is unsafe or how to proceed.**
      The refusal is unchanged and still fail-closed; it now names the entry kind it observed —
      symbolic link, submodule, unsupported Git mode, unsafe path or excessive depth — and carries
      remediation for each. The link target is never printed. A submodule is also no longer
      reported as a malformed listing. B-093/D-183.

- [ ] **QA-020 — A YAML authoring repository cannot enter the monitored Source → Candidate flow.**
      Authoring-Source admission is now manifest discovery rather than native-package validation:
      `source add --kind source-git` admits a repository that declares at least one explicit
      `aart-cli.yaml`/`aart-cli.json`, keeps the native-package rule for a tree that declares
      `aart-cli-source.json`, and still refuses a tree that declares neither. Transport, identity,
      symlink, special-file and last-known-good boundaries are unchanged. An authoring Source
      contributes no Marketplace offers and cannot empty the consumer's Marketplace. B-094/D-176.

- [ ] **QA-021 — Registry cannot one-off scan YAML manifests and vendor selected artifacts.**
      Stage: optional artifact-scoped onboarding from an external repository
      Surface: Maintainer → Registry
      Severity: high
      Blocks current monitored-Source stage: no; this is a second required onboarding model
      Reproduction: provide the Superpowers URL/ref without adding it as a configured Source, then
      try to discover its `aart-cli.yaml` files and select one Skill for Registry ownership
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
      screens 46f/46g (D-191). `aart-cli registry adopt` and `aart-cli registry check-upstream` are the
      machine-complete CLI projection: scan/review/apply phases, `--expect` verified whenever
      given, sorted listings (D-192, 8 tests).

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

- [ ] **QA-025 — Re-running a registry's generated files exists in the TUI but rejects its output.**
      Stage: after promoting, adopting or editing anything in the registry checkout
      Surface: Registry Maintainer → Rebuild (46h/46i)
      Severity: blocking
      Blocks current stage: yes; skip Rebuild during discovery
      Reproduction: promote a Candidate through the TUI, then choose `b`, `Everything, in order`,
      Enter to review and Enter to run
      Expected: the canonical `lock → build → validate → audit` maintenance sequence accepts the
      same versioned Registry representation the TUI promotion writes
      Observed: `lock` immediately refuses because legacy `artifact.json` is missing, so no later
      stage runs. The action has a TUI home, but the underlying authority is incompatible with the
      Registry it is supposed to maintain.
      Retest outcome: FAILED on the real promoted Registry. The earlier focused fixture proved the
      route and ordering but never supplied canonical promotion output. Reopened under B-099 and
      joined to QA-032/B-057 in CP-19 step 9.
      Fix: Rebuild's port is `refresh_registry_workspace`, which runs the same four verbs through
      the same curation authority the CLI uses, so the representation dispatch of `QA-032` repairs
      it at the same seam rather than in a second place (`D-208`).
      Evidence: `test_screen_46_rebuilds_the_registry_a_promotion_left_behind` calls that port over
      a really promoted checkout and holds that all four stages pass in canonical order.
      Retest: promote a Candidate through the TUI, then `b` → `Everything, in order` → Enter →
      Enter, and confirm the run completes.

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
      Additional manual evidence: completing the Candidate promotion sequence also leaves the
      operator backing through every intermediate screen to reach Candidates. The owning-list
      return must cover completed Candidate workflows, not only Source Sync.
      Fix: Source Sync Result binds Enter to Sources — the list that journey started from — and
      the route is declared in the navigation map, because a key that navigates somewhere the map
      does not allow is a key that does nothing. Registry Maintainer gains `c Candidates`, so the
      screen a finished promotion lands on is one key from the next promotion instead of an Esc
      for every screen just walked. Screen 45's own Enter still goes on to Registry, which is the
      precedent this generalizes rather than replaces (`D-210`).
      Evidence: `tests/terminal_result_return_test.py` holds the key, the declared route, the
      footer label, the move it really makes, both halves of the finding, and that a review still
      waiting for its confirmation is not treated as a result.
      Retest: Sources → `s` → review → Enter → Source Sync Result → Enter should land on Sources;
      after a promotion, `c` from Registry Maintainer should reach Candidates.

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
      Fix: `_navigate` empties the draft the entered form owns, and only that one, so opening Add
      Source does not discard a half-typed Add Registry. It is read on forward navigation only,
      which is exactly what separates opening a new form from returning to a refused one —
      `_declined_preparation` goes back through the session history and never reaches this
      (`D-211`). Add Registry and Add Source also state, in words, that they add another one and
      change nothing already connected, which is the question the operator actually asked.
      Evidence: `tests/form_draft_lifecycle_test.py` holds the empty form, the other drafts left
      alone, the refused form still holding everything typed (`QA-018`/`D-184`), Esc back onto a
      form keeping it, and the new sentence on both add forms.
      Retest: add one Source, press `a` on screen 31 again, and confirm the form is empty; then
      let a preparation refuse and confirm the typed values are still there.

- [ ] **QA-032 — A Registry produced by TUI promotion fails its generated GitHub Actions.**
      Stage: publishing the first promoted artifact through Registry PR #1
      Surface: generated `.github/workflows/aart-cli-registry.yml`
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
      Fix: the six generated verbs now dispatch on the representation they are given instead of
      assuming the authoring workspace (`D-208`). `is_promoted_registry` recognizes the approved
      shape by `registry/versions/`; `validate` drops the compiled-lock requirement for it because
      its version records already carry those digests; `build` rebuilds exactly the two derived
      catalogs; `lock` becomes a read-only prepared curation, because approved versions are pinned
      by their own records; and `publish` chains the same build, validate and audit without a lock
      half. The generated workflow and its verbs are unchanged, so registries already scaffolded
      keep working.
      Evidence: `tests/promoted_registry_maintenance_e2e_test.py` builds the workspace through the
      public `registry init` → `registry scan` → `registry promote --yes` chain and runs the six
      verbs the generated workflow runs, in its order. It also holds that maintenance never writes
      `aart.lock.json` or `aart.index.json` (`B-057`: one representation, not both), that `build`
      restores a damaged catalog, and that a damaged version record is still refused.
      Retest: promote through the TUI, push the resulting commit and open the Registry PR; both
      `registry-quality` jobs must pass over the promoted representation.

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
      Fix: a refused run now says so. `_failed` emits `ACTION_FAILED` instead of an empty
      `ACTION_RECORDED`, which the reducer could only read as no transition at all; the reducer
      clears the plan and records `failed_action`, so the review it was confirmed from becomes that
      attempt's terminal result without moving off the refusal (`D-209`). The footer offers
      `Enter Back to list` instead of `Enter Confirm`, Enter navigates to the screen that owns the
      run, and the heading says the run did not happen. Leaving the screen ends the terminal state,
      so the next review is a review again.
      Evidence: `tests/failed_action_terminal_state_test.py` holds all of it across four confirmed
      action kinds, not Registry rebuild alone, plus the frame the operator actually read and the
      `QA-024` claim that an unconfirmed review still asks for its confirmation.
      Retest: run a Registry action that refuses, and confirm the screen becomes a result with one
      route back and no confirmation prompt.

- [ ] **QA-034 — A Git-merged promotion never becomes visible in Marketplace.**
      Stage: first clean Consumer after Registry PR #1 was merged and synchronized
      Surface: Marketplace in TUI and `marketplace list --json`
      Severity: blocking
      Blocks current stage: yes; install/update/repair acceptance cannot start
      Reproduction: merge the TUI promotion commit into the configured Registry's `main`, connect
      a clean consumer to that branch, then open Marketplace
      Expected: merging into the configured approved branch is the publication boundary, so the
      promoted artifact becomes an approved Marketplace offer
      Observed: Source health is `healthy` at merged commit `f37d182`, and the synchronized tree
      contains the version, manifest and payload, but Marketplace returns `artifacts: []`. The
      durable record still says `publication: promoted-local`; the consumer admits only
      `PublicationStage.PUBLISHED`, and no public Git publication path changes that field.
      Evidence: even the first merged Skill is absent, independently of the not-yet-published MCP
      and adopted Skill. CP-17's Git-backed fixture called `publish_registry_version` internally
      before materializing its repository, so it never exercised this missing public transition.
      Fix: publication is now read where INV-242 puts it — presence on the branch the consumer
      configured — instead of waiting for a durable field no public workflow writes.
      `load_published_registry_versions` applies the transition once, at the four consumer read
      seams (offers, selection, installation re-read, offline readiness); the maintainer's own
      workspace, source validation and promotion planning keep the record as written (`D-207`).
      Evidence: `tests/git_publication_transition_e2e_test.py` promotes with the real transaction,
      commits the second promotion to a review branch, merges it with `git merge --no-ff`,
      synchronizes and reads Marketplace and an install receipt. It was RED at
      `[] != ['company/skill/code-review@1.2.0']`, the exact symptom reported here.
      Retest: connect the clean Consumer to the merged Registry `main`, `source sync`, open
      Marketplace, and confirm the promoted Skill is offered and installable.

- [ ] **QA-039 — Vendored and Referenced promotion modes are unexplained.**
      Stage: choosing how a Candidate enters a Registry
      Surface: Promotion Mode and Promotion Review
      Severity: high
      Blocks current stage: no, but the choice changes what the Registry owns and can install
      Expected: concise definitions and consequences for both modes, the currently selected mode,
      and a key label that says what `m` changes
      Observed: the screen named `vendored` or `referenced` without explaining ownership, payload
      availability or the upstream relationship, and labelled `m` only as `Mode`.
      Fix: `D-217`. The domain now owns the consequences of both promotion modes. Promotion Review
      projects both choices, marks the active one, labels Vendored as the enterprise default and
      explains Registry ownership, install availability and upstream dependence before confirmation.
      The footer names `m` as `Toggle mode`.
      Evidence: projection and renderer tests were RED on the missing choices and explanation. A
      semantic mutation removing Vendored's enterprise-default fact turns the exact explanation
      test red; the focused 1513-test family is green.
      Retest: open a Candidate promotion review, read both complete choices, press `m`, and confirm
      that only the selected marker changes while both consequence explanations remain visible.

- [ ] **QA-043 — Registries exposes authoring Sources as actionable rows and leaks an internal error.**
      Stage: browsing consumer Registry connections
      Surface: Registries (21)
      Severity: high
      Blocks current stage: no
      Reproduction: configure one `registry-git` plus authoring Sources, then open Registries
      Expected: the Registry screen contains Registry connections only; authoring Sources remain on
      Maintainer Sources and cannot advertise a Registry-only detail action here
      Observed: authoring Sources appeared as connected rows with `Actions: details`, but Enter could
      not open them and exposed `no connected registry here is 21-registries`.
      Fix: `D-218`. The screen-21 projection now admits only `registry-git` connections. Its sync
      request always targets the visible Registry row rather than stale navigation focus; Source
      records remain available through their own Maintainer surface.
      Evidence: an authoring Source placed before a Registry cannot hide the later Registry, and a
      Hypothesis property holds the sync target for every single-line stale focus. Mutating the
      filter from `continue` to `break`, or removing Registry Sync from the row-owned actions, turns
      the corresponding test red. The focused 1513-test family is green.
      Retest: configure Registry and authoring Source entries, open Registries, and confirm only the
      Registry connection appears and `s` refreshes the visibly focused Registry.

- [ ] **QA-044 — Registry Maintainer contradicts the connected Registry with local-project state.**
      Surface: Registry Maintainer. Severity: high. The frame can show a valid connected Registry
      and then say there is no Registry to rebuild because it silently switches subjects to the
      current project; its remediation also leaks the internal name `Screen 46`. Expected: label
      connected Registry snapshots and the local Registry workspace separately, name the current
      project explicitly, and offer `Initialize Registry` without any internal screen identifier.
      CP-20 step 2 owns the fix and manual retest.
      Fix: connected snapshots and the local Registry workspace now have separate labelled blocks;
      an absent local marker names the current project and offers Initialize Registry in product
      language. Evidence: `tests/cp20_tui_clarity_test.py`, `tests/maintainer_registry_view_test.py`.

- [ ] **QA-045 — Doctor exposes an internal screen identifier as the repair subject.**
      Surface: Doctor/Automatic Inspection. Severity: high. `nothing canonical is installed here
      as 29-doctor` is implementation-state leakage, not a diagnosis. Expected: repair/reload uses
      the visibly focused installed coordinate and never renders a route identifier. CP-20 step 2.
      Fix: Doctor repair is row-owned and refuses when no visible repairable issue is focused.
      Evidence: `tests/cp20_tui_clarity_test.py`, `tests/consumer_navigation_test.py`.

- [ ] **QA-046 — Automatic Inspection presents inconclusive harness observations as a failed quiz.**
      Surface: Fast installation workflow. Severity: high. A page showing `0 of 4` and four
      `unknown` harness requirements asks for no decision and reads like failure immediately before
      a successful install. Expected: inspection still builds the immutable plan, but Fast mode
      advances directly to the first genuinely required input/remediation decision or Ready.
      CP-20 step 2.
      Fix: inspection still contributes to the immutable plan, while Fast mode advances directly
      to Required Inputs, Remediation or Ready. Evidence: `tests/consumer_install_flow_shell_test.py`.

- [ ] **QA-047 — Success requires backing out of a completed installation wizard.**
      Surface: installation Success. Severity: high. Expected: Enter on Done completes the wizard
      and returns directly to Marketplace; View installed and View receipt remain explicit choices.
      CP-20 step 2.
      Fix: Success binds Enter/Done to Marketplace without changing its explicit detail routes.
      Evidence: `tests/consumer_navigation_test.py`, `tests/consumer_application_e2e_test.py`.

- [ ] **QA-048 — Section rules and Settings groups run together vertically.**
      Surface: shared section layout and Settings. Severity: medium. Expected: one blank line on
      both sides of section text, one blank between Settings groups, and one blank before the
      Maintainer Mode explanatory sentence. CP-20 step 2.
      Fix: the shared section primitive owns blank lines on both sides, and Settings renders its
      groups as separate blocks. Evidence: `tests/tui_layout_test.py`, `tests/consumer_views_test.py`.

- [ ] **QA-049 — The manual MCP cannot exercise credential input and management.**
      Surface: disposable manual acceptance fixture. Severity: high. Expected: the fixture
      publishes an installable dummy MCP with a declared safe test credential, drives the required
      input/credential views, and never commits or prints the supplied value. CP-20 step 4.
      Fix: the disposable Registry publishes `dummy-mcp@1.0.0` with required `dummy-token`; only a
      provider reference is planned and the server reports presence, never content. Evidence:
      `tests/manual_test_lab_test.py`, `tests/configured_installation_action_e2e_test.py`.

- [ ] **QA-050 — A connected Registry cannot be disconnected from Marketplace in the TUI.**
      Surface: Registries. Severity: high. Expected: the focused Registry has a reviewed Disconnect
      action that removes its connection and AART-managed snapshot, clears it as default if needed,
      and leaves installed artifacts and receipts untouched. CP-20 step 3.
      Fix: `d` opens an exact origin/ref review and confirmation rechecks the source identity before
      removing configuration and its managed snapshot. Evidence: `tests/consumer_registry_disconnect_test.py`.

- [ ] **QA-051 — Manual acceptance inherits repositories and app state from earlier runs.**
      Surface: manual-test setup. Severity: blocking for reproducible acceptance. Expected: one
      command builds a fresh lab with new clones, isolated HOME/XDG, a unique `manual/<run-id>`
      branch in every repository and all prerequisites; one reset command deletes only that
      marker-owned local lab. GitHub-specific passes use the same unique branch namespace in
      dedicated test repositories and never reset/force-push shared branches; remote cleanup is a
      separate exact reviewed action. CP-20 step 5.
      Fix: `make manual-test-setup` creates three fresh working repositories and local bare remotes
      under isolated homes; `make manual-test-reset` deletes only the exact marker-owned root.
      Evidence: `tests/manual_test_lab_test.py` and a real setup/reset smoke.

- [ ] **QA-052 — AART has no safe command-line factory reset.**
      Surface: CLI administration. Severity: high. Expected: a CLI-only reset lists exact AART-owned
      configuration/data/cache targets, requires two deliberate confirmations, refuses unsafe
      targets, restores the app to no connections/settings, and leaves projects, harness files,
      other applications' credentials and unrelated files untouched. CP-20 step 6.
      Fix: CLI-only `aart-cli reset` lists the exact plan/digest, requires `RESET AART` and
      `DELETE AART STATE`, and refuses unsafe/symlinked targets before deleting anything.
      Evidence: `tests/factory_reset_test.py` including Hypothesis target properties.

- [ ] **QA-053 — No screen says which directory the session was launched from.**
      Surface: every canonical shell frame. Severity: medium. Reproduction: launch `aart` from any
      directory and read any screen. Observed: nothing on the frame names the directory, so an
      install or a Registry edit gives no way to tell whether it is about to land in a manual-test
      lab or in the real project. Expected: the frame names the launch directory as persistent
      chrome, on every screen. Blocks the end-to-end stage: no.
      Fix: the composition boundary resolves the launch directory once, the state carries it, and
      the frame prints `Working in <path>` directly under the heading; home is written `~` and an
      over-long path drops leading segments so the directory's own name always survives.
      Evidence: `tests/workspace_context_line_test.py`, including a Hypothesis property that a
      shown path is bounded and keeps its final segment.

- [ ] **QA-054 — The manual acceptance procedure tests the CLI, not the TUI.**
      Surface: `docs/testing/END_TO_END_ACCEPTANCE.md` and the manual lab. Severity: medium.
      Observed: stages 1-3 are entirely CLI and GitHub setup, stage 4 adds author Sources through
      the CLI although adding a Source is itself a Maintainer screen, and the CP-20 head advertising
      `make manual-test-setup` was never reconciled with a body that still exports
      `$AART_CLI_MAINTAINER_HOME`. The default lab also publishes both fixtures, so the whole Maintainer
      run — Initialize Registry, Add Source, Sync, Candidates, validation, promotion, commit — is
      already done by the setup script and an operator walking those screens re-reads a result
      instead of producing one. Expected: a TUI-first walkthrough over a Registry that starts empty.
      Blocks the end-to-end stage: no.
      Fix: `make manual-test-setup-empty` builds the lab with the author sources published and the
      Registry repository empty, and `docs/testing/TUI_MANUAL_WALKTHROUGH.md` walks both roles
      through the screens, naming the one `git push` the TUI deliberately does not do (161.7).
      Evidence: `tests/manual_test_lab_test.py`, plus a driven text-TUI run reaching
      `[n] Initialize` on the empty Registry.

- [ ] **QA-056 — A promotion cannot be completed from the CLI without fabricating its evidence.**
      Surface: `aart-cli registry promote`. Severity: medium. **Unconfirmed — verify during the CLI
      run.** Observed in code: `registry promote` requires `--validation-report DIGEST` and
      `--policy-result DIGEST`, and no CLI command emits either; `validation_report_digest` is
      derived in the application layer and displayed only by the Maintainer screens. An operator
      following a CLI-only route therefore either reads the digests off the TUI, which makes the
      route not CLI-only, or invents them, which defeats the evidence the flags exist to carry.
      Expected: either a command that emits the validation/policy evidence for scanned Candidates,
      or an explicit statement that Candidate promotion is a TUI-only transaction. Blocks the
      end-to-end stage: no. Workaround in use: `registry vendor`, which needs no external evidence.
      Confirm at: `docs/testing/END_TO_END_ACCEPTANCE.md` step 3.

- [ ] **QA-057 — The CLI route had no way into the lab's environment.**
      Surface: manual acceptance tooling. Severity: low. Observed: `manual_test.py open` starts the
      TUI, and the CLI procedure told the operator to paste four environment variables in front of
      every command — unreadable, and a mistyped HOME runs a manual test against real state.
      Expected: one entry point that puts a shell inside the lab.
      Fix: `make manual-test-shell-maintainer` / `make manual-test-shell-consumer` open an
      interactive shell with the lab's isolated HOME/XDG and the role's working directory.
      Evidence: `tests/manual_test_lab_test.py::...a_lab_shell_is_described_for_each_role...`.

## Confirmed

Move an entry here only after manual retest, preserving its checkbox, result date and fixing commit.
