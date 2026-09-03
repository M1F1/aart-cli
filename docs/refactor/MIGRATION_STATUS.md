# AART Refactor Migration Status

> Source of truth for **where implementation currently is**.
> Product truth lives only in the Product Specification.

## State model

`NOT STARTED → IN PROGRESS → IMPLEMENTED → VERIFIED → MIGRATED → LEGACY REMOVED`

`BLOCKED` may be used with explicit evidence and unblock condition.

| Slice | Status | Evidence | Legacy authority remaining |
|---|---|---|---|
| CP-00 Canonical planning baseline | VERIFIED | Bootstrap commit `5515e11`; docs/secret/validation gates pass | Historical docs remain non-authoritative reference |
| CP-01 Repository characterization | VERIFIED | 242-row traceability matrix; 32 boundary + 86 focused tests pass; 1,903-test baseline recorded | Current implementation remains behavior evidence |
| CP-02 Clean architecture seam | VERIFIED | Architecture boundary tests; frozen domain scan; format/lint/typecheck/validate/docs/secret gates green | Legacy orchestration remains outside the new seam for strangler migration |
| CP-03 Five core algebras | VERIFIED | Frozen five-algebra modules; Hypothesis monotonicity/determinism properties; full gates green | Legacy/subsystem models remain flow authority until later adapters migrate |
| CP-04 Authoring manifest/compiler | VERIFIED | Explicit JSON/YAML discovery; five-kind canonical compilation; input-digest properties; real-filesystem integration; 1,935 unit + 46 E2E tests, 83.45% coverage and all quality gates green | Existing native/source commands remain public-flow authority until CP-05 routes Source Sync through the compiler. Extended under CP-13: the manifest now also declares §91 runtime inputs and the §107/§108 dependency descriptor (D-054, D-055) |
| CP-05 Source/Candidate/Registry | VERIFIED | Frozen Candidate/registry lifecycle; digest-aware Source Scan; atomic versioned promotion and lifecycle plans; public scan/review/local-promote flow; 1,959 unit + 46 E2E tests, 83.23% coverage and all quality gates green | Older curation `promote-native`/vendor paths remain supported legacy authority until later registry migration/removal evidence |
| CP-06 Marketplace/Selection/Collections | VERIFIED | Published-only aggregation; frozen Selection/versioned Collections; ownership-preserving constraint/dependency resolution; 1,975 unit + 46 E2E tests and 83.22% coverage green | Existing consumer CLI/TUI projection remains on the characterized catalog resolver until CP-12/13 migration |
| CP-07 Inspection/Remediation/Policy/Plan | VERIFIED | Frozen secret-free `EnvironmentFacts`/`InstallPlan`; pure aggregate/assess/filter/plan pipeline; read-only local inspector adapter; capability∩policy∩risk remediation intersection, non-interactive fail-closed and deterministic review digest; 1,989 unit + 46 E2E tests, 83.17% coverage and all quality gates green | Legacy per-artifact `installation/*`, `setup_engine/*` and `consumer/runtime_requirements.py` planning remains public-flow authority until CP-10/12/13 route the canonical plan |
| CP-08 Inputs/Credentials | VERIFIED | Secret/config, binding and value-source kept on three separate axes; `SecretInput` has no value field and binds only to a provider reference; dependant-aware inspect/store/verify/replace/delete planning with policy as a required argument; `TransientSecret` confined to `io/` and unpicklable, uncopyable, single-use; `MacOsKeychainProvider` proven against `security` itself, replacement measured to need delete-then-add (D-017), 128-byte truncation measured in child processes; 2,034 unit + 46 E2E tests, 83.19% coverage and all ten quality gates green | Legacy `setup_runtime.py` Keychain authority and `setup_engine/*`/`configuration/*` input seam remain public-flow authority until CP-10 routes a real MCP installation through the provider port |
| CP-09 Python environments/dependencies | VERIFIED | Dependency specification and installer backend kept separate, with one lock-compatibility rule shared by spec and requirement; `ArtifactEnvironment` derives every path from the artifact root so an interpreter outside it cannot be supplied; installer chosen by compatible∩available∩permitted with preference selecting inside it; effects carry the base interpreter, descriptor kind and installer so they reach the review digest; interpreters refuse unowned paths before any process starts and refuse a locked project rather than installing loose versions; proven against real `venv`, pip and uv with a self-built wheel and no network; 2,066 unit + 46 E2E tests, 83.20% coverage and all ten quality gates green | Legacy `setup_runtime.py` environment authority remains public-flow authority until CP-10 routes a real MCP installation through the environment port |
| CP-10 MCP stdio vertical slice | VERIFIED | Declarative `LaunchContract` plus a POSIX quoter property-tested through a real `/bin/sh`; pure launcher generation where a secret becomes a provider command substitution resolved at launch and never a written value (D-022), a stdin binding is refused because the transport owns stdin (D-023) and a file binding is refused rather than written (D-024); the writer refuses paths outside the artifact and re-digests after writing; measured Tabnine/Claude MCP targets merged without disturbing neighbours or permissions (D-025, D-026); receipts fingerprint config rather than copying it (D-027) and verification names six drift findings, counting an unmeasurable launcher as drift (D-028); proven end to end against a real venv, a real generated launcher and a real stdio MCP server that reports `agent_artifacts` is not importable, with the macOS run resolving a 256-bit token from a real temporary Keychain; 2,126 unit + 55 E2E tests, 83.26% coverage and all ten quality gates green | Legacy `setup_render.py` launcher/settings rendering and the `setup.py`/`lifecycle` merge remain public-flow authority until CP-12 routes install, repair and uninstall through reconciliation over this projection |
| CP-11 Reconciliation engine | VERIFIED | Seven independently inspectable components ordered by dependency; `DesiredState` and `CurrentState` kept as separate types and a component nobody observed counted as drift rather than a match (D-029); a desired component says both how it is established and how it is corrected, so a missing credential is stored and a wrong one replaced (D-030); planning takes only the drifted components' effects, in dependency order rather than canonical review order (D-031), and fails rather than dropping a repair the policy forbids (D-032); components whose effects are not independently repairable escalate by name, giving the CP-07 capability metadata its first consumer; the CP-10 receipt/observation bridge is paired so describing less cannot invent drift (D-033); proven against a real installation where an edited launcher plans a launcher-only repair and a deleted harness entry a harness-only repair; 2,161 unit + 56 E2E tests, 83.33% coverage and all ten quality gates green | Legacy `setup_verify.py`, `setup_verify_probes.py` and `setup_undo.py` remain public-flow authority until CP-12 routes repair and uninstall through this engine |
| CP-12 Installed lifecycle | VERIFIED | All eight intents lower through one reconciliation planner; executor rechecks the reviewed plan under a per-scope lease, always re-inspects, reports partial/interrupted/unverified outcomes, restores failed updates only after reversible effects, respects Collection ownership and retains credentials by default; real MCP damage/repair/start and reverse-uninstall E2E; 2,196 unit + 65 E2E tests, 83.25% coverage and all ten quality gates green | Legacy `lifecycle/application.py`, `setup_verify.py` and `setup_undo.py` remain public-flow authority until CP-13 migrates the consumer TUI/commands to the canonical intents and executor |
| CP-13 Consumer TUI | VERIFIED (legacy removal deferred to CP-14) | Accepted screens 01–29 have canonical Fast/Verbose projections, a pure reducer/keymap and a persistent injected shell (D-039–D-049). Durable action/installation receipts, ownership and machine reload are verified across processes (D-044–D-051, D-064–D-066). Authored packages lower once through reviewed execution; configured approved Selection resolution, screen-07 input references, object-store placement, capability-bound interpreters and one prepare/complete adapter are verified for real MCP installation (D-052–D-076). B-033 is complete: kind-neutral placed receipts and delivery reconciliation now take a real authored Skill through promotion, configured review, installation, durable reload, drift detection and reverse uninstall without a launcher or environment (D-077–D-078). Public direct approved-registry `install`, `status`, `update` and `uninstall` all use the configured action (D-079-D-081, D-083). B-034 is complete: memory owns a delimited region of a file the user writes in, measured by digesting the region rather than the file (D-084), and a hook is delivered and merged at once, owning one entry of one list inside a settings file the harness and its user share (D-085) -- so every artifact kind the Product Specification defines now installs, measures, repairs and removes canonically. B-025 is complete: the default terminal route is the canonical consumer application. `run()` composes machine, offers, configuration and credential adapters once and calls `run_consumer` before any wizard composition; a repair is bounded by its receipt and fails closed on what the receipt cannot describe (D-086); a refusal is drawn under the screen it was asked from rather than raised (D-087); and the Marketplace is now the configured registries' approved published versions, with trust taken from the promotion record that approved each one (D-088, INV-026), so what is browsed is installable. Evidence is `tests/consumer_application_e2e_test.py`, which drives the real shell over the production handler through install, reinstall-converges, verify/repair after a deleted delivery, uninstall, and two refusals. B-037 was promoted from backlog to the critical path and fixed: `plan_bulk_promotion` rebound only the version records in its own transaction while the catalogs took the new content digest, so the second promotion into any registry made it unreadable to every consumer -- a live defect on `aart registry promote`, not a fixture problem. Every retained approved record is now rebound to the snapshot its own transaction produces, as metadata only, with the published package proven byte-identical (D-089). That unblocked D-088's last piece of evidence: a Marketplace row stands for the highest approved SemVer of an identity, and an older approved version is superseded rather than declined. Screen 28 is the last accepted screen to go live: four controls with a cursor, `v` and Detail level unified as one preference, and a durable `<data_root>/state/consumer-settings.json` read strictly rather than repaired -- an opt-in that had to be re-chosen every session was not an opt-in, and Maintainer Mode is the boundary CP-14's whole surface sits behind (D-090). CP-13's remaining legacy retirement is re-triaged as a CP-14 dependency rather than two open product questions: the Product Specification already settles both, and both answers land in CP-14 -- 145.1 makes a Collection versioned and CP-14 owns collection candidates (B-031); 1737 and INV-019-INV-026 put consumer installation over approved registry content and CP-14 owns Sources screens 31-34 (B-038, D-091). Full suite now 2,958 tests green in 179s, with lint, format-check, typecheck, docs-check and secret-shape-check green; coverage and the remaining gates deferred to the end of the CP-13 block. | Direct approved-registry `install`, `status`, `update`, `uninstall` and the default TTY are canonical for all five kinds; Collections and direct/local lifecycle commands still route to legacy authority, and no legacy implementation has been removed. `_run_curses` and the wizard composition are now unreachable from `run()` on a terminal but retain direct test callers (B-039). Collections still have no live versioned source (B-031); a deprecated registry version is declined rather than offered because the row cannot render the warning (B-036); native sources are listed but offer nothing, pending a product answer (B-038). |
| CP-14 Maintainer TUI | IN PROGRESS | Step 1 names screens 30–53 inside the shared mode-gated state machine (D-092, INV-193). Screens 30–32 bind configured authoring Sources, durable health and exact pinned Source Scans through strict Candidate history (D-093–D-095, INV-229/239). Screens 33–34 are now the production typed `SOURCE_SYNC` action: read-only digest-bound review; approved-registry and Source/history precondition checks; acquire/validate/publish, exact manifest compile/reconcile, atomic history write/readback under one Source lease; no registry mutation (D-096–D-097, INV-007/200/201). A real temporary installation syncs a local Source through the shared shell and proves the registry observation unchanged. Step 3 puts screens 35–37 in that same shell: the Candidate list is keyed by stable Candidate ID so two Sources publishing one artifact name cannot collide, narrowing is the typed `MaintainerCandidateFilter` rather than renderer string matching, screen 36 carries the full authoring detail with secret inputs valueless, and screen 37 is semantic diff first with the bounded redacted file diff behind an explicit `f` toggle that no navigation carries forward (D-098, INV-202). Drawing the three screens opens no file and rescans nothing; the shell draws the scans `read_maintainer_views` already read once, and corrupt history still refuses the whole observation. Codex's step-3 checkpoint left format-check, lint and typecheck red and all three were repaired rather than relaxed. Step 4's engine is landed ahead of its screens: `application/candidate_validation.py` makes validation an ordered pipeline of named checks with warnings, errors and a non-passing `not-run` kept distinct, refuses a warning or error carrying no actionable detail, and routes policy through the previously unread `EffectivePolicy.required_checks` so a required check that did not pass yields `APPROVAL_REQUIRED` rather than `WARNING` (D-099); which checks can actually fail was established by probing the compiler first, so the re-verification checks are tested against doctored canonical trees and the two that bite on clean artifacts -- a secret bound to argv, an executable payload file -- are tested directly. Step 4 is complete: screens 38-40 project one run per active Candidate, addressed by `"<candidate-id>:<check>"` row pairs that parse back to a typed value rather than being split inside a renderer, with the policy judgement composed into the run so screens 38 and 40 cannot disagree about the same Candidate (D-100). `read_maintainer_views` now takes the `EffectivePolicy` and validates every active Candidate once at composition time; drawing all three screens opens no file. `make quality` and `make integration` are both green after step 4: 3,052 unit tests, 209 E2E tests, 83.35% branch coverage. Step 5 now has screens 41–45 live. Screens 41–43 review, choose and plan without writing (D-101–D-102). Screen 44 projects pre-write validation of the promoted registry and its Candidate-policy evidence. Explicit confirmation on screen 45 rechecks the digest, exact Candidate, approved baseline and checkout; revalidates and replans; refuses movement; atomically applies the existing promotion plan; validates persisted versions and audit provenance; then creates one local Git commit containing only reviewed paths, with no push capability (D-103). Drawing screens 44–45 opens no file. A real temporary production installation walks screens 30 and 35–45, commits a promoted registry into a clean checkout with no remote, and validates the persisted readback. `make quality` is green with 3,098 tests and 83.28% branch coverage; format, lint, type, validation, packaging, docs and secret-shape gates pass. `make integration` is separately green with 210 E2E tests. Screen 46 now reads the registry back: validity is the named check that every approved version carries a promotion approval record, and recent promotions are ordered by walking the audit snapshot chain backwards from the approved snapshot rather than by any clock, because no promotion record carries one and stamping one at read time would make the order a property of when a Maintainer looked (D-104). Working-tree state is a separate observation of the D-103 project-root checkout, digested over the whole synchronized tree -- the same `source_snapshot_digest` D-103 requires a checkout to match before it may be promoted from -- while the audit chain head is read separately in the published-content `registry_state_digest` space the audits themselves name; the composition E2E caught the first attempt comparing the two spaces, which made a correct checkout read as diverged. After a local commit the checkout is legitimately ahead of the synchronized approved snapshot and the line says so rather than calling it an error, and a promotion now recomposes the Maintainer views the way a Source Sync already did, because the commit it just made moved the checkout. Enter on screen 45 confirms only while an action is pending and otherwise continues to screen 46. Drawing screen 46 opens no file. The E2E walk now runs from the consumer dashboard through diff, validation, promotion, the local commit and out to the registry view. `make quality` and `make integration` are both green: 3,167 tests. Screen 47's selection surface is live: what one registry's transaction may carry, with promotability read off the run screens 38–40 showed, Candidates of another registry not offered at all, and a refused Candidate named with its reason rather than silently absent; selection reuses the reducer's existing typed `selection` with `Space` (D-105). Screen 47's transaction is now live and is genuinely one transaction: `PreparedCandidatePromotionTransaction` carries a tuple of promotions rather than a single one, `plan_promotion_transaction` plans the whole set through the existing `plan_bulk_promotion`, and the single-Candidate path is the one-element case of it rather than a second path -- so there is one review flow and one chance for it to be right. Confirmation reads the approved baseline once and then rechecks every Candidate against it, because reading it per Candidate would let one transaction assemble members against two different registries. Screens 44 and 45 now carry a tuple of Candidates each with its own validation-report and effective-policy digests, and screen 45's commit subject names the artifact for one and the count for several. Screen 47's one forward route is screen 44, not screen 43, because a bulk selection has no single-Candidate diff to open, and the configured handler re-checks at action time that the confirmed selection is still a subset of what screen 47 composed (D-106). A real temporary production installation ticks two Candidates on screen 47 and proves they reach the checkout as exactly one commit, one registry snapshot and a clean working tree -- which a loop over single promotions could not produce. B-041 is complete and so is step 5: promotion audits now discriminate a 40-hex Git revision from a typed local snapshot SHA-256, canonical legacy Git records remain readable, and a local pin in that legacy field is refused (D-107). Direct tests prove local screen-43 planning and the audit shape; the production E2E takes a real filesystem Source through sync, validation, promotion, persisted registry validation and one clean local commit whose audit digest matches the durable Candidate-history pin. Mixed Git/local bulk planning remains one transaction and one registry snapshot, and D-089/B-037 rebinding is unchanged. Focused gates are green; full checkpoint results are in the active slice. Screen 53 completes the filter half of step 6: the Product Specification names four Candidate filter facets and the one typed filter now carries all four, with closed sets typed (`states`, `kinds`) and open sets as aliases (`sources`, `registries`) because that is what each facet is. Its rows are `"<facet>:<value>"` addresses parsed back by `parse_candidate_filter_row` and toggled through one entry point, not four; the offered values come from every composed Candidate rather than the narrowed list, since a row that vanished when ticked could never be unticked; and each option states what choosing it would leave, so a narrowing that selects nothing is legible before it empties screen 35 rather than after. `f` opens it from screen 35 and ticking a row puts nothing in `selection`, which is what every action reads. `f` now means the raw file diff on screen 37 and the filters on screen 35, each meaning what its own screen is about; the characterization test that pinned `f` as inert on screen 35 was corrected to the new behaviour rather than relaxed (D-111). Drawing screen 53 opens no file. `make quality` and `make integration` are both green. Screens 51-52 complete step 6. They already had projections, a renderer, validation against approved registry state and durable composition; what they lacked was a route, so every test entered by constructing a session already sitting on screen 51 -- the same gap screens 35-37 had in step 3. `c` on the Candidate list is the way in, because "Collections are candidates too" puts them on the Candidate surface and the accepted screen 30 panel describes no Collections entry to add one to (D-112). Writing the walk forced a real distinction into the open: the fixture first compiled through `compile_author_snapshot` and got no Collections at all, because that boundary returns artifacts only, while production Source Sync uses `compile_author_source`, which carries both kinds. A Collection authored beside an artifact in one tree is now compiled once, persisted once, reached with `c` and resolved on screen 52 to the exact version the registry approved, over one real installation. | Step 6 is complete. Step 7 is under way: its first removal deleted the legacy curses wizard shell `_run_curses`, the two setup shims it alone called and the seven tests that existed only to drive it, on evidence that already existed -- `run()` never reached it and ERR05 is pinned on the canonical `run()` (D-113). `run()`, `_run_text` and the whole text route stay, because no-TTY is a supported environment rather than a broken one, as do the wizard's curses primitives the surviving stages still compose. Step 7 is now done apart from a mechanical sweep: the whole wizard front-end is removed (D-115, D-116, D-117) and `tui.py` is 2,747 lines, down from 5,705. Its stated remainder -- `consumer/application.py`, `lifecycle/*`, `installation/*`, `setup_engine/*` -- was a wrong reading and is not removed: `commands/marketplace.py`, the public `aart marketplace install|update|uninstall|setup`, composes `ConsumerApplicationService` and runs the setup queue through it, and the canonical shell's own `tui_marketplace.py` takes `LifecycleItem` and `InstallMode` from that stack. B-039 is closed; B-038's remainder is restated as an `aart marketplace install` question. What step 7 actually leaves behind is **B-044 (critical)**: the canonical shell reaches none of that stack, so it performs no post-install setup and offers no usage report (D-118). |
| CP-15 Edge-case hardening | NOT STARTED | — | — |
| CP-16 Doctor/supportability | NOT STARTED | — | — |
| CP-17 Git-backed live acceptance | NOT STARTED | — | — |
| CP-18 Migration/release gate | NOT STARTED | — | — |

### CP-14 current increment (2026-09-02)

**The wizard front-end is gone, and the stack under it turns out not to be legacy.**
`_run_user_curses_wizard`, `_run_user_text_wizard`, `_prompt_curation_request`, the
`_curses_source_*` maintenance screens with `_selected_source_row`, `_offer_usage_report`,
`_run_canonical_setup_queue`, `_is_canonical_maintainer_workspace`, `_type_rank` and the 22 further
definitions the fixpoint sweep found once they were gone are deleted -- 1,515 lines. `tui.py` is
**2,747 lines**, down from 5,705 when step 7 began. `tests/tui_curation_test.py` and
`tests/reporting_tui_test.py` go with them, along with `SourceLifecycleCursesTests` and
`CursesWizardFlowTests`.

**The plan the last three increments carried was wrong, and the correction matters more than the
removal.** `MIGRATION_STATUS.md`, `NEXT.md` and the slice file all said the wizard stages were the
last thing holding `consumer/application.py`, `lifecycle/*` and `setup_engine/*`, and that those
followed. They do not. `commands/marketplace.py` -- the public `aart marketplace
install|update|uninstall|setup` -- composes `ConsumerApplicationService` directly and runs the setup
queue through it (`service.setup_queue`, `service.finalize_setup_queue`), and `tui_marketplace.py`,
which the canonical shell imports, takes `LifecycleItem` and `InstallMode` out of
`lifecycle/model.py` and `installation/model.py`. That stack is load-bearing for a public flow. Like
`installation/*` before it, it goes by symbol if at all, never by package, and nothing further was
removed for it (D-117).

Two of the removed tests held an assertion nothing else did, and the assertion moved to the
reachable surface rather than going with the test. **LAF-90**: `RS-02`'s loop covers every registry
action except `init`, because `init` is the one that owns `--minimum-version`/`--maximum-version`,
so an operator who supplies neither gets the parser's defaults and the wizard test was the only
thing checking they admit the running executable -- restated in `tests/registry_cli_test.py`,
verified red against a dead `1.0.0..2.0.0` window. **The usage-report offer**:
`_render_cli_reporting` in `commands/marketplace.py` had no test at all, and the wizard test was the
only thing pinning that consent defaults to no, that the exact payload is readable before anything
opens, and that a reporting failure leaves the marketplace outcome unchanged -- privacy boundaries,
so they are now `tests/reporting_cli_offer_test.py` (7 tests), verified red against a consent
default of yes, with two properties the CLI has and the wizard did not: the second prompt can still
stop a report the first accepted, and a non-interactive stdin is a refusal rather than an unanswered
prompt. The rest went against evidence that already existed -- the canonical planner's refusal of a
snapshot with no `aart-registry.json`, the Maintainer E2E's local-commit-never-pushed test (which
showed the "AART never commits or pushes" menu label was stale rather than carried), the `aart
source` surface, and the canonical shell's drawn refusal and discard-on-quit prompt.

**What the removal exposed is now the critical work: B-044.** `io/consumer_actions.py` performs no
setup and no reporting, so since D-115 put the canonical application on both terminal routes, an
artifact installed from the TUI that declares setup requirements lands unconfigured and no usage
report is offered -- while the Product Specification names interactive setup as work AART performs
and screens 09/11 summarize an install as "configured MCP servers, isolated environments ...
securely stored credentials". That is a mandatory invariant a shipped path no longer satisfies, so
it is promoted to the critical path rather than filed as backlog. `_canonical_setup_run` and
`_complete_canonical_consumer_action` are deliberately **retained** as the material to wire it back
(D-118): deleting them as orphans would have been the mechanical reading of D-091 and the wrong one,
since they are not legacy authority but the only implementation of a capability the replacement
lacks. `aart marketplace install` carries both and is unaffected.

One live output the removal falsified is fixed here: `InternalFailureContext.stage` was typed
`WizardStage` and set only by the wizard, so every canonical crash would have reported `stage:
onboarding`, naming a screen that no longer exists. It takes a `CanonicalBoundary` (`compose` /
`curses` / `text`) now, `run()` sets it, and an untyped defect from the composition -- which reads
local state and carries paths in its message -- is redacted through `internal_failure_lines` instead
of propagating (D-119). 571 lines of `tui.py` remain production-orphaned, held only by widget tests,
and are the next sweep minus the two helpers B-044 holds. `make quality` and `make integration` are
both green.

**The legacy text wizard shell is removed, and everything only it reached with it.** D-115 left
`_run_text` in exactly the position `_run_curses` was in before D-113: defined, exercised by tests,
reachable from nothing. It is gone, with `_runtime_source_stage_context`, `_dispatch_result` and the
26 further private definitions in `tui.py` that became unreferenced once it was -- 1,546 lines out of
`tui.py`, about 2,200 with the tests that existed only to drive it. The sweep was mechanical and
repeated to a fixpoint rather than hand-picked, because removing one orphan orphans its callees and a
list written by eye would have left a tail. Every removed test's capability was checked against a
public flow before it went rather than assumed: scaffolding against `aart registry scaffold`
(`registry_init_scaffold_test.py`, `registry_cli_integration_test.py`); source add/remove/sync/
resubscribe against the `aart source` command surface (`source_cli_command_test.py`, 23 tests pinning
the same review-then-finalize semantics); vendoring against the flags half of the parity it was
testing, with the assessment rendering pinned by `registry_vendor_assessment_test.py`; ERR04's
`install-state-legacy` against four other modules; ERR06 refusals and the setup queue against the
canonical shell's drawn notice. Two entry tests asserting "not the legacy wizard" were restated as
"and nothing else", since a comparison to something that no longer exists pins nothing, and the
module docstring that still opened "Two front-ends, one body" was rewritten (D-116). `tui.py` is
4,262 lines, down from 5,705. `lifecycle/*` and `setup_engine/*` are now reachable only through
`consumer/*`, and `curation/*` only through the public flag-mode commands.
`ConsumerApplicationService` survives because the curses wizard *stages* still compose it and 36
tests still cover them; those stages, then `consumer/application.py` with `lifecycle/*` and
`setup_engine/*` behind it, are what step 7 removes next. `make quality` and `make integration` are
both green, 3,173 tests.

**The text fallback is now the canonical application rather than a second product.** Surveying what
step 7 could remove next turned up the reason it could remove nothing: every remaining target --
`consumer/application.py`, `lifecycle/*`, `setup_engine/*`, and B-038's legacy direct-install from a
native Source -- is reachable only through `_run_text`, which is built on `ConsumerApplicationService`
and through it on that entire stack. The blocker was a missing replacement, not missing evidence,
and a no-TTY environment (CI, a pipe, a dumb terminal, SSH without a pty) was being handed a
different product from the one a terminal gets. ERR05 permits a text fallback for exactly one
condition -- the terminal cannot host curses -- and says nothing about the application changing; the
shell already takes its terminal as a port of two methods, so text is an adapter rather than a second
frontend. `_TextTerminal` draws with `write` and reads with `read`, naming the keys a line editor
cannot send (`up`, `down`, `enter`, `esc`, `back`, `space`), treating a single-character line as that
character and a blank line as Return, giving an unknown word no meaning at all, and answering `q`
then `y` on EOF so a pipe that ends mid-selection does not redraw the discard prompt forever.
`run()` now composes the application once for whichever terminal answers and hands the same
composition to `run_consumer` or `run_consumer_text`; its whole legacy tail -- source-stage
composition, consumer/reporting service factories, the `_run_text` call -- is gone (D-115). Evidence
is `tests/consumer_text_terminal_test.py`, including two walks over a real temporary installation:
reaching the dashboard through a pipe and opening the Marketplace the configured registry approved.
The ERR05 tests in `tests/tui_fallback_boundary_test.py` were retargeted at `run_consumer_text`
rather than duplicated, and the assertions that had become vacuous were restated rather than left
standing. `make quality` and `make integration` are both green. `_run_text` and the stack below it
now have no production caller -- the position `_run_curses` was in before D-113 -- so the removals
step 7 exists for are unblocked.

**Screen 21 now lists the configured sources, and a native one says why it offers nothing.**
B-038's remaining CP-14 dependency was one sentence of wording, and writing the test for it exposed
that screen 21 had nothing to say it about: nothing on the composition path ever projected the
configured sources, so `machine.registries` stayed the empty default and a machine with a configured
registry on disk opened on an empty screen 21 and a dashboard reading "0 registries" -- the same gap
screens 02-04a had before the Marketplace was composed, on the screen next to it.
`read_consumer_offers` already reads the configured catalog once and now also projects it through
`project_registries`, carrying the rows on `ConsumerOffers`; `screens_from` takes them and
`LocalConsumerActions.source()` passes them, keeping the read at composition where an effect
belongs. Which sources are configured is configuration rather than durable machine evidence, which
is why it arrives through the offers seam instead of being read a second time by the machine.
The B-038 half is INV-026: a Marketplace projects configured registries, so an enabled `SOURCE_GIT`
or `SOURCE_LOCAL` contributes health and offers nothing -- and a bare "0 artifacts" describes that
correct state as a fault while an advertised sync names an effect that source cannot have.
`RegistryView` gains a typed `is_registry` decided in the projection rather than by a renderer
splitting `kind` (D-100, D-111); a non-registry row reads "An authoring Source, not a registry" with
`actions` of `("details",)`, and the dashboard counts the registries among the configured sources
because "2 registries" over one registry and one authoring Source is a false count (D-114). Evidence
is `tests/consumer_registries_screen_test.py`, including the production composition
(`tui._canonical_consumer_actions` over a real temporary installation) putting the configured
registry on screen 21 rather than a `screens_from` call a test made. The characterization test that
pinned `("details", "sync")` on every row was corrected to state what each kind of row now offers
rather than relaxed. `make quality` and `make integration` are both green. B-038 is partly closed:
removing the legacy route's ability to install directly from a native Source remains.

**Step 7 began with its first removal: the legacy curses wizard shell is gone.** `_run_curses`
(754 lines), the two setup shims it alone called (`_legacy_setup_stage_failure`,
`_run_post_install_setup`) and the seven tests that existed only to drive it are removed. No new
test was written for the removal because B-039's evidence pre-existed on both halves: `run()` has
composed `_canonical_consumer_actions` and called `run_consumer` before any wizard composition since
B-025/D-087, so no terminal reached `_run_curses`; and ERR05 -- the one condition under which a text
fallback is legitimate -- is pinned on the canonical `run()` by `tests/tui_fallback_boundary_test.py`
(text starts exactly once when curses is unavailable, an internal defect never restarts at
onboarding, an unexpected terminal-probe error is not silently downgraded). Three duplicates of
those were written against the entry test and then reverted rather than left as second coverage of
one behaviour. The text route stays, because no-TTY is a supported environment rather than a broken
one, and so do the wizard's curses primitives, which the surviving stages still compose and 36 tests
still cover. `_dispatch_result` lost its last production caller here but stays until the command
dispatch path retires, because a live test still patches it to prove the canonical text route does
not dispatch legacy commands. The removal exposed one alias worth naming: a text test reached the
legacy `model.Err` through `tui.Err`, which existed only because `tui` happened to import it; it now
imports from `agent_artifacts.model` directly, assertion unchanged (D-113). `make quality` and
`make integration` are both green. B-039 is partly closed -- the shell is gone, the semantic paths
behind it (`consumer/application.py`, `lifecycle/application.py`, `installation/*`,
`setup_engine/*`) are not.

Screens 48–50 are now live. Candidate lifecycle joins exact retained history with matching
version/audit evidence and never infers promotion from Candidate state (D-108). Provenance
cross-checks compiler output against domain metadata and exposes typed Git/local pins, importer
identity/version and the complete payload path set (D-109). Immutable coordinate/version conflicts
show both digest sets when available, retain the durable refusal when registry evidence is
unavailable, and only prescribe a new version (D-110, INV-203/239). Focused tests, lint and
typecheck are green. Screens 51–53 are live as well (D-111, D-112), so step 6 is complete. The
table's CP-14 legacy-removal boundary otherwise remains in force: each remaining legacy route goes
only behind the public-flow evidence D-091 requires.

**B-044's fixture and characterization are landed; the item is wider than it was recorded.** A
setup-declaring artifact could not be produced by any existing harness, because the authoring format
has no setup section -- `setup` appears zero times in `protocol/authoring.py` -- so a declaration
genuinely enters at packaging rather than at authoring. `AuthoredSetup` and `_with_setup` in
`tests/configured_installation_draft_e2e_test.py` model exactly that: they write `artifact.json`'s
`setup` reference, `setup/installer.json` and `SETUP.md` into the *compiled* package, recompile it
with `compile_native_package` -- which is what proves the declaration valid rather than merely
well-formed -- and send the result through the whole real promotion transaction, so every digest is
derived. The fixture threads through `_promote_one`, `_published_registries`, `_published_registry`
and `_environment(authored=..., setup=...)`, leaving every existing caller unchanged.

`tests/configured_setup_gap_test.py` characterizes what the two front ends then do with it. Its
first test guards the other three by asserting the approved registry really does carry the
declaration and its recipe, so a fixture that silently stopped declaring setup could not leave the
defect tests passing. What they record corrects D-118: **`aart marketplace install` skips setup
too.** For an approved registry coordinate it reaches `_configured_lifecycle`, which calls
`complete_configured_installation` -- the same seam `io/consumer_actions.py::_execute_installation`
uses -- and reports `session_status: succeeded` with no `setup` key, no diagnostic, and the
configuration file the recipe declares unwritten. Setup runs only on the legacy path, which
`_configured_registry_selection` selects by returning `None` for a direct or local source. There is
no operator recovery either: `aart marketplace setup` afterwards refuses with `registry company has
invalid root manifests`, because it resolves through the legacy catalogue and a promoted registry
snapshot carries no root manifests. So B-044 is one fix at one shared seam rather than a TUI wiring
gap (D-120), and what still blocks the green is the installed-record question: the setup engine
resolves what to configure from the install-state manifest that `io/consumer_machine.py` treats as
the *legacy* store (D-069), while the configured seam writes receipts.

The working route has its evidence as well (D-121):
`marketplace_lifecycle_e2e_test.py::DeclaredSetupE2ETest` runs a declared setup end to end from the
CLI over the legacy native-local-source route and asserts each of its four gates — `install` names
the setup it did not run, an unreviewed source refuses without `--authorize-untrusted-source`, an
authorized plan applies nothing until its effects are separately approved, and both together write
the delimited managed block. It is `skipUnless(darwin)` because `setup.py:562` accepts only
`['darwin']` recipes. Applying the preserved B-044 draft's hardcoded `TrustClass.COMPANY_REVIEWED`
now fails two of those four, where before it passed all 3,216 tests.

**The canonical receipt now names its object (D-122).** This was B-044's blocking question and it
was decided by measurement, not preference: after a canonical `aart marketplace install`, the
receipt store held the coordinate, `payload_digest`, `root` and the deliveries and no object digest,
while the legacy install-state record's `ArtifactEvidence` carries one — and
`setup_engine/application.py::_prepare_setup_object` needs that digest to read the package at all,
because setup is declared on the package manifest. So the receipt was not missing a convenience; it
could not answer "which package is this", which repair needs as much as setup does. `object_digest`
is now on `PlacedArtifactReceipt` and `InstallationReceipt`, populated by the installation proposal
from the `RegistryArtifactVersion` the Selection already resolved. It is optional and older receipts
read back as unknown rather than defaulted, because an installation whose object nobody wrote down
is honestly unknown and a default would be a dangling identity on a real installation.
`tests/installed_object_identity_test.py` proves the recorded digest resolves to a real object in
the store whose manifest is the installed package's; each receipt shape carries a round-trip, an
older-document read and a malformed-digest refusal. The alternative — having the configured seam
also write the legacy install-state record — was rejected because it writes new records into the
store the strangler is retiring. Two things step (3) still has to answer: the engine's
`MarketplaceCatalog` cannot read a promoted registry snapshot and `RegistryArtifactVersion` carries
no `manifest_digest`, and `persist_setup` records that setup ran inside the legacy install-state
record, which the canonical route has no equivalent of.

**Both front ends now name the setup they do not run (D-123).** The configured seam reported a
finished install and said nothing about the setup it skipped, which is the worse of the two
failures the legacy route has: that route at least names it (D-121's first gate), so an operator
knows there is a step left, while silence tells somebody a Skill is configured when it is not.
`complete_configured_installation` now reads the objects it just recorded, carries what they
declare as `pending_setup`, and both `aart marketplace install` (an additive `pending_setup` key,
rendered) and the persistent shell (under screen 11's success) say it. This is the first use of the
receipt's object identity and it is not scaffolding: setup is declared on the package manifest
rather than on anything the plan carries, so the reading is the first half of the engine's own
`_prepare_setup_object` for the canonical route. The key is absent rather than empty when nothing
declares setup, and the reading is done from the durable record after completion rather than from
the plan, so it states something about the machine instead of repeating the action's intention. An
object a receipt names and the store cannot produce is an error rather than a quiet "nothing to
configure". Half of `tests/configured_setup_gap_test.py` inverted;
`tests/configured_setup_report_test.py` owns the assertions that moved, and what stays
characterized is that the work is still not performed.

**The engine's subject is now separate from its object (D-124).** B-044 read as "the engine cannot
be reached" rather than "the engine needs a second subject" because `_prepare_setup_object` did
both jobs in one function: every canonical fact was blocked behind a legacy install-state read and
a legacy catalogue resolution. It now takes a typed `_InstalledSubject` and validates the object
that subject names, with `_install_state_subject` building the legacy one. Nothing behaves
differently -- the 27 engine tests and the darwin end-to-end route are the characterization -- and
the canonical route has one seam to fill rather than a function to fork. Step 7i of the CP-14 slice
records what filling it needs: canonical marketplace evidence, a precondition that does not
re-resolve through the legacy catalogue, and a durable setup record the canonical route owns.

**The engine now takes a subject port rather than a marketplace catalogue (D-125).** Two of those
three are closed as a shape: `prepare_setup`, `prepare_setup_attempt`, `finalize_setup` and
`execute_setup_queue` take `(SetupRequest) -> Result[_InstalledSubject]`, `install_state_subject`
is the legacy implementation, and `_preconditions_current` re-asks that port instead of
re-resolving the catalogue and separately re-reading install state -- so what was two checks that
could drift is one. The subject carries the trust decision and the indexed setup declaration rather
than a `MarketplaceItem`, which is all the plan ever read from it. No behaviour changed; the
engine's trust-downgrade, source-removed, capability-mismatch and missing-record tests are the
characterization. What remains for the canonical route is one implementation of that port and a
durable setup record it can own.

**The engine no longer names the store that recorded the installation (D-126, D-127).** The plan's
last two install-state-shaped fields are now `installation_record_path` /
`installation_record_lock_path` -- the durable file that says this artifact is installed here and
the lock guarding it, whichever store holds it -- and `InstalledSubject` holds those two paths
instead of an `InstallStatePaths`. The identity JSON that derives `setup_state_ref` deliberately
keeps its old `install_state_path` key, because it is a digest input and renaming it would rename
every existing setup record. The last check only a separate index could satisfy is now a union:
`IndexedSetupDeclaration` keeps the legacy cross-check unchanged, and `ApprovedObjectIdentity`
checks the loaded object against the digest the approved registry publishes for the coordinate --
two values from two documents, where the alternative would compare a value read out of the package
against a value compiled out of the same package. No behaviour changed; the engine tests are the
characterization and three new ones cover the new arm.

What (3b) still needs is a canonical `SetupSubjectPort` and a canonical `persist_setup`. Every
field the port must produce is now traced to a real source, including `manifest_digest`, which this
file previously recorded as not constructible: `native_tree.py:512` defines it as
`json_digest(artifact_manifest_to_json(manifest))` over the package's own `artifact.json`, which
the object carries. Recording it is not the same as cross-checking against it, and the independent
check is the approved object identity above. Step 7j of the CP-14 slice carries the rest.

## CP-14 step 7 — the wizard implementation is swept (D-129)

`agent_artifacts/tui.py` is **2,767 -> 1,087 lines**. The removal was driven by reachability
computed to a fixpoint from the module's live entry points, not by a single-pass reference scan:
the retired wizard's definitions call each other, and the one-pass estimate this file and `NEXT.md`
previously carried (~571 lines) kept whole clusters alive by their own internal references. The
true figure was 1,680, and the sweep terminates with the detector reporting `0 dead definitions`.

No test file was deleted before D-091 was applied to every assertion it held. That produced one new
file and five retargeted ones. The new file matters on its own account:
`tests/setup_receipt_cli_test.py` drives `aart marketplace receipt show|verify|undo` on real
on-disk records, which nothing did — the renderers and the rollback were characterized, but the
only front-end reachability test for them drove the retired wizard skins. Three assertions were
carried into `tests/consumer_shell_test.py` and each proven red against a real production mutation.
Three behaviours the canonical shell does not have (a filter's match count, refusal wrapping, the
dot-separator rule) are recorded as B-047, B-048 and B-049 rather than asserted as though they held.

Step 7 of CP-14 is therefore complete. The next executable work is B-046.

## Update rule

Never mark a slice beyond the strongest evidence actually present.
`IMPLEMENTED` means code exists; `VERIFIED` requires relevant tests; `MIGRATED` means callers/flows
use the new path; `LEGACY REMOVED` requires the old authority/path to be safely removed.
