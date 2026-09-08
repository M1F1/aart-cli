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
| CP-14 Maintainer TUI | VERIFIED | Step 1 names screens 30–53 inside the shared mode-gated state machine (D-092, INV-193). Screens 30–32 bind configured authoring Sources, durable health and exact pinned Source Scans through strict Candidate history (D-093–D-095, INV-229/239). Screens 33–34 are now the production typed `SOURCE_SYNC` action: read-only digest-bound review; approved-registry and Source/history precondition checks; acquire/validate/publish, exact manifest compile/reconcile, atomic history write/readback under one Source lease; no registry mutation (D-096–D-097, INV-007/200/201). A real temporary installation syncs a local Source through the shared shell and proves the registry observation unchanged. Step 3 puts screens 35–37 in that same shell: the Candidate list is keyed by stable Candidate ID so two Sources publishing one artifact name cannot collide, narrowing is the typed `MaintainerCandidateFilter` rather than renderer string matching, screen 36 carries the full authoring detail with secret inputs valueless, and screen 37 is semantic diff first with the bounded redacted file diff behind an explicit `f` toggle that no navigation carries forward (D-098, INV-202). Drawing the three screens opens no file and rescans nothing; the shell draws the scans `read_maintainer_views` already read once, and corrupt history still refuses the whole observation. Codex's step-3 checkpoint left format-check, lint and typecheck red and all three were repaired rather than relaxed. Step 4's engine is landed ahead of its screens: `application/candidate_validation.py` makes validation an ordered pipeline of named checks with warnings, errors and a non-passing `not-run` kept distinct, refuses a warning or error carrying no actionable detail, and routes policy through the previously unread `EffectivePolicy.required_checks` so a required check that did not pass yields `APPROVAL_REQUIRED` rather than `WARNING` (D-099); which checks can actually fail was established by probing the compiler first, so the re-verification checks are tested against doctored canonical trees and the two that bite on clean artifacts -- a secret bound to argv, an executable payload file -- are tested directly. Step 4 is complete: screens 38-40 project one run per active Candidate, addressed by `"<candidate-id>:<check>"` row pairs that parse back to a typed value rather than being split inside a renderer, with the policy judgement composed into the run so screens 38 and 40 cannot disagree about the same Candidate (D-100). `read_maintainer_views` now takes the `EffectivePolicy` and validates every active Candidate once at composition time; drawing all three screens opens no file. `make quality` and `make integration` are both green after step 4: 3,052 unit tests, 209 E2E tests, 83.35% branch coverage. Step 5 now has screens 41–45 live. Screens 41–43 review, choose and plan without writing (D-101–D-102). Screen 44 projects pre-write validation of the promoted registry and its Candidate-policy evidence. Explicit confirmation on screen 45 rechecks the digest, exact Candidate, approved baseline and checkout; revalidates and replans; refuses movement; atomically applies the existing promotion plan; validates persisted versions and audit provenance; then creates one local Git commit containing only reviewed paths, with no push capability (D-103). Drawing screens 44–45 opens no file. A real temporary production installation walks screens 30 and 35–45, commits a promoted registry into a clean checkout with no remote, and validates the persisted readback. `make quality` is green with 3,098 tests and 83.28% branch coverage; format, lint, type, validation, packaging, docs and secret-shape gates pass. `make integration` is separately green with 210 E2E tests. Screen 46 now reads the registry back: validity is the named check that every approved version carries a promotion approval record, and recent promotions are ordered by walking the audit snapshot chain backwards from the approved snapshot rather than by any clock, because no promotion record carries one and stamping one at read time would make the order a property of when a Maintainer looked (D-104). Working-tree state is a separate observation of the D-103 project-root checkout, digested over the whole synchronized tree -- the same `source_snapshot_digest` D-103 requires a checkout to match before it may be promoted from -- while the audit chain head is read separately in the published-content `registry_state_digest` space the audits themselves name; the composition E2E caught the first attempt comparing the two spaces, which made a correct checkout read as diverged. After a local commit the checkout is legitimately ahead of the synchronized approved snapshot and the line says so rather than calling it an error, and a promotion now recomposes the Maintainer views the way a Source Sync already did, because the commit it just made moved the checkout. Enter on screen 45 confirms only while an action is pending and otherwise continues to screen 46. Drawing screen 46 opens no file. The E2E walk now runs from the consumer dashboard through diff, validation, promotion, the local commit and out to the registry view. `make quality` and `make integration` are both green: 3,167 tests. Screen 47's selection surface is live: what one registry's transaction may carry, with promotability read off the run screens 38–40 showed, Candidates of another registry not offered at all, and a refused Candidate named with its reason rather than silently absent; selection reuses the reducer's existing typed `selection` with `Space` (D-105). Screen 47's transaction is now live and is genuinely one transaction: `PreparedCandidatePromotionTransaction` carries a tuple of promotions rather than a single one, `plan_promotion_transaction` plans the whole set through the existing `plan_bulk_promotion`, and the single-Candidate path is the one-element case of it rather than a second path -- so there is one review flow and one chance for it to be right. Confirmation reads the approved baseline once and then rechecks every Candidate against it, because reading it per Candidate would let one transaction assemble members against two different registries. Screens 44 and 45 now carry a tuple of Candidates each with its own validation-report and effective-policy digests, and screen 45's commit subject names the artifact for one and the count for several. Screen 47's one forward route is screen 44, not screen 43, because a bulk selection has no single-Candidate diff to open, and the configured handler re-checks at action time that the confirmed selection is still a subset of what screen 47 composed (D-106). A real temporary production installation ticks two Candidates on screen 47 and proves they reach the checkout as exactly one commit, one registry snapshot and a clean working tree -- which a loop over single promotions could not produce. B-041 is complete and so is step 5: promotion audits now discriminate a 40-hex Git revision from a typed local snapshot SHA-256, canonical legacy Git records remain readable, and a local pin in that legacy field is refused (D-107). Direct tests prove local screen-43 planning and the audit shape; the production E2E takes a real filesystem Source through sync, validation, promotion, persisted registry validation and one clean local commit whose audit digest matches the durable Candidate-history pin. Mixed Git/local bulk planning remains one transaction and one registry snapshot, and D-089/B-037 rebinding is unchanged. Focused gates are green; full checkpoint results are in the active slice. Screen 53 completes the filter half of step 6: the Product Specification names four Candidate filter facets and the one typed filter now carries all four, with closed sets typed (`states`, `kinds`) and open sets as aliases (`sources`, `registries`) because that is what each facet is. Its rows are `"<facet>:<value>"` addresses parsed back by `parse_candidate_filter_row` and toggled through one entry point, not four; the offered values come from every composed Candidate rather than the narrowed list, since a row that vanished when ticked could never be unticked; and each option states what choosing it would leave, so a narrowing that selects nothing is legible before it empties screen 35 rather than after. `f` opens it from screen 35 and ticking a row puts nothing in `selection`, which is what every action reads. `f` now means the raw file diff on screen 37 and the filters on screen 35, each meaning what its own screen is about; the characterization test that pinned `f` as inert on screen 35 was corrected to the new behaviour rather than relaxed (D-111). Drawing screen 53 opens no file. `make quality` and `make integration` are both green. Screens 51-52 complete step 6. They already had projections, a renderer, validation against approved registry state and durable composition; what they lacked was a route, so every test entered by constructing a session already sitting on screen 51 -- the same gap screens 35-37 had in step 3. `c` on the Candidate list is the way in, because "Collections are candidates too" puts them on the Candidate surface and the accepted screen 30 panel describes no Collections entry to add one to (D-112). Writing the walk forced a real distinction into the open: the fixture first compiled through `compile_author_snapshot` and got no Collections at all, because that boundary returns artifacts only, while production Source Sync uses `compile_author_source`, which carries both kinds. A Collection authored beside an artifact in one tree is now compiled once, persisted once, reached with `c` and resolved on screen 52 to the exact version the registry approved, over one real installation. | Step 6 is complete. Step 7 is under way: its first removal deleted the legacy curses wizard shell `_run_curses`, the two setup shims it alone called and the seven tests that existed only to drive it, on evidence that already existed -- `run()` never reached it and ERR05 is pinned on the canonical `run()` (D-113). `run()`, `_run_text` and the whole text route stay, because no-TTY is a supported environment rather than a broken one, as do the wizard's curses primitives the surviving stages still compose. Step 7 is now done apart from a mechanical sweep: the whole wizard front-end is removed (D-115, D-116, D-117) and `tui.py` is 2,747 lines, down from 5,705. Its stated remainder -- `consumer/application.py`, `lifecycle/*`, `installation/*`, `setup_engine/*` -- was a wrong reading and is not removed: `commands/marketplace.py`, the public `aart marketplace install|update|uninstall|setup`, composes `ConsumerApplicationService` and runs the setup queue through it, and the canonical shell's own `tui_marketplace.py` takes `LifecycleItem` and `InstallMode` from that stack. B-039 is closed; B-038's remainder is restated as an `aart marketplace install` question. What step 7 actually leaves behind is **B-044 (critical)**: the canonical shell reaches none of that stack, so it performs no post-install setup and offers no usage report (D-118). |
| CP-15 Edge-case hardening | VERIFIED | Step 1 closes the registry-state half of INV-218 at the surface that uses it. `tests/source_sync_command_e2e_test.py` is the first thing anywhere to drive `aart source sync` over a real source whose upstream published an invalid revision -- a new payload plus an `aart-registry.json` that does not parse, so the refusal is observable rather than indistinguishable from the good snapshot. Eight tests hold the whole scenario through public verbs: the refusal is per-source and carries its remediation into the human rendering; the store still points at the last good snapshot and `marketplace list` offers every artifact of it digest for digest; the source degrades to `could-not-check` with a named `source-invalid` diagnostic rather than being withdrawn; an installation made from the good snapshot is byte-identical, its recorded state unchanged, and still `current`; installing after the refused sync places the accepted revision's bytes and updating is a no-op; and a repaired upstream publishes, so the refusal was about the content rather than `sync` being inert. Writing them found D-132: `could-not-check` -- exactly what the explicit last-known-good fallback `SyncDisposition.RETAINED` produces -- was read as "this source is gone" in three places, so one invalid upstream revision made `marketplace status` report every installation as `source-unavailable`, and made `install` and `update` fail on a plan-construction invariant with no remediation on it. Product Specification 165.11 settles it and both sets now admit it, with `missing` and `not-synchronized` still excluded because those mean there is no snapshot. Both seams carry their own red-first claims (`canonical_lifecycle_test`, `canonical_install_planning_test`), and reverting the `RS-08` refusal in `sources/validation.py` turns all eight end-to-end tests red. INV-218 moves to EVIDENCED; INV-210 stays PARTIAL with real evidence in place of "scattered safeguards". Step 2 asks what a *moving* upstream may rewrite. `tests/source_upstream_movement_e2e_test.py` republishes into the real source and proves a sync leaves the installation record identical in every field, the new revision is offered rather than applied (`update-available`, reviewed bytes still on disk), an explicit `update` is what rebinds it, and an upstream rolled back to its first revision is new work rather than an erased event. That last one is the case content addressing makes counter-intuitive: republishing the first revision's bytes republishes its digest, so the store looks untouched, and only the record remembers that the second revision happened. On the registry side `promotion_planning_test::test_a_second_promotion_rewrites_one_field_and_no_provenance` pins D-089's rebinding -- the one place an already-approved record is written over -- to `registry_snapshot` alone, with the promotion audit byte-identical. Mutations: deciding `check_installations` on version alone turns two of four end-to-end tests red; re-deriving one further field of a retained record turns the promotion test red, and it is the only one of that file's sixteen that catches it. INV-219 moves to EVIDENCED; INV-216's consumer half is closed and its Git revert half waits on CP-17. Step 3 takes Product Specification 165.11's decomposition of offline installability -- metadata cached / canonical payload cached / runtime dependencies cached -- and asks whether AART's single `--offline` boolean collapses them. It does not, and `tests/offline_capability_test.py` now pins that: an unsynchronized source refuses by naming the cache (`aart source sync`) rather than the artifact; a cached-metadata, uncached-object install refuses under a different code with the words "while offline" separating it from the connected case; and the dependency installer is denied an index (`pip --no-index`, `uv --offline`) exactly when offline is asked for, in both backends, with that flag the *only* difference between the connected and offline argument vectors. The three codes are asserted pairwise distinct, which is the invariant's actual prohibition -- conflating them is what sends an operator to re-sync a source to fix a missing wheel. Layers 1 and 2 collapse for a local source (the object store is empty before the first install and the object is published from the cached snapshot during it), so layer 2 is measured at the planning seam; that is the fixture's property, not the code's. Three mutations, one per layer: emptying `flags` in both branches of `io/python_runtime.py::_install_argv` turns three of four red; `if False:` in place of `if offline:` in `marketplace/catalog.py::_resolution_failure` turns one red; dropping the `" while offline"` suffix in `installation/application.py` turns a different one red. The dependency layer had no test at all before this -- `python_environment_integration_test` runs real offline installs and would have stayed green with the flag removed, silently reaching the network on every `--offline` install. INV-223 stays PARTIAL, now against a named gap rather than "scattered safeguards": nothing *reports* the three capabilities before an install is attempted, which is the reading 165.11 shows, recorded as B-051 for CP-16's `aart doctor`. Step 4 split into two halves with different subjects, and 4a is done: verification failure and the compensatable restore. `tests/verification_failure_e2e_test.py` runs a declared setup whose recipe writes one managed block and then runs a command that exits non-zero. Product Specification 165.12 makes two claims about that moment and they came apart. The report half already held: `aart marketplace setup` exits non-zero, the item is `verification-failed` -- its own word, not `apply-failed-rolled-back` and not `cancelled` -- the counts read `configured=0, incomplete=1`, the human rendering names the artifact and the retry rather than only a count, 165.13's compensatable-restore branch removed the block, and the separately placed payload is still `current`. The evidence half did not: the receipt recorded the verification result and the final health and recorded no applied effects at all, because `_apply_effects` dropped the step receipts whenever the rollback succeeded -- so `receipt show` said a check had failed while saying nothing about what had already been done to the machine before it did. D-133 keeps them, marked `setup_disposition: "compensated"` (the word the persistence-failure path already writes, and which all three readers already honour), and moves `rollback_command` to depend on the steps still standing, so a fully compensated record offers no undo to run. The two evidence tests were red against the shipped code while the four report tests were green, which measures the split rather than asserting it; reverting `standing` to `receipts` in `_record` turns the undo claim red on its own. INV-224 keeps EVIDENCED with public-flow evidence in place of seam-only evidence; B-052 records the consent-declined sibling branch, which the CLI's all-or-nothing `--approve-setup-effects` cannot reach. Step 4b closes INV-226 over the public verbs. `tests/interrupted_execution_e2e_test.py` uses a real custom entrypoint whose apply fails and whose rollback then also fails -- the one path that raises without removing its run directory -- so the working copy it asserts on is one the engine really created and really failed to clean up, rather than one a patched-away cleanup produced. It had to be that route: a run directory is opened only by `custom.install@1` and `docker.build@1`, so step 4a's managed-block recipe can leave no orphan and the claim answers `true` about a directory that was never made. Six claims: an incomplete compensation is `rollback-incomplete` and not `apply-failed-rolled-back`, and carries a recovery line (165.13); the working copy survives; `receipt verify` finds it, exits non-zero and names the directory the engine actually created, cross-checked against the record's plan hash; verify leaves it exactly where it is (`LAF-61`); the receipt reads back as JSON; and a retry re-plans rather than resuming -- a different review digest, the protocol restarted from its first phase, and both working copies then reported. The JSON claim exists because writing the file found the defect: a parsed record's steps are frozen recursively and the projection copied each shallowly, so `receipt show --json` ended in a `TypeError` for exactly the run whose evidence is hardest to reconstruct by hand; `setup.py`'s `_plain` is now public as `plain_value` and the projection uses it. Mutations: pointing the probe's run root at the project root -- the `LAF-66` defect class at the one seam `setup_verify_test` cannot reach -- turns two red; the shallow projection turns two red; calling an incomplete rollback a completed one turns two red. A fourth attempt killed nothing and is recorded in the slice: the outer `_rollback_all` re-creates the directory when it writes the receipt its own compensation needs. INV-226 moves to EVIDENCED. D-134 adds mutation adequacy as tooling: `mutmut` joins the dev group behind `make mutants ONLY=... TESTS=...` (`scripts/mutants.py`), advisory and always scoped, and `AGENTS.md` now names it and Hypothesis as the two tools that check the tests themselves. | All eight steps are done and every invariant the slice declared is EVIDENCED. Exact collection drift stayed out of scope, waiting on the Collection capability B-038 is sequenced behind (D-131). |
| CP-16 Doctor/supportability | VERIFIED | Step 1 adds the top-level, read-only `aart doctor` over real canonical project and user installations (D-139). One durable observation feeds both the accepted screen-29 health projection and `prepare_configured_repair`; six E2E tests hold healthy/no-plan, one-drift/one-plan, both scopes, source independence and unreadable-receipt refusal. Step 2 adds D-140's pre-install offline-readiness report: Source/artifact metadata, exact approved canonical payload and runtime-dependency evidence stay separate in JSON and human text. Eight public E2E scenarios cover cold, referenced, dependency-free, dependency-declaring, disabled/plain/multiple sources, multiple artifacts and a deprecated version without installing or publishing. Manual mutations independently break all three capabilities; fresh scoped mutmut runs killed 30/30 application and 73/76 I/O mutants, with three reviewed equivalent/unproducible survivors. Full gates are green: 3,251 tests, 1 skipped, 85.37% branch coverage and 287 separate integration tests. Step 3 adds the reviewed repair entry point (D-141): `aart doctor --repair` returns a complete plan and its review digest and applies nothing; `--yes` requires that digest; a machine moved between review and confirmation returns the recomputed plan instead of applying the stale one; and a machine moved after the command's own re-plan is refused by the lifecycle adapter as `execution-review-stale`, because the staleness check is deliberately made twice against two different things -- the command owns the operator-facing check and the adapter owns the effect-facing one. Confirmed repair records a `repair` receipt whose steps equal the observed drift, after which a plain `aart doctor` independently reports the machine ready. Eight E2E scenarios and five targeted mutations, each red only where claimed. The finding is the exactness test: named source *and* version, it only ever omitted the source, so dropping the version requirement killed nothing; both under-specified forms now run as subtests and each mutation half kills its own. B-059 records the one remaining survivor, an exactly-one-match guard whose duplicate case is not known to be representable. INV-194 is EVIDENCED. Step 4a makes the orphaned-run diagnostic reachable without a receipt to name it (D-142): `orphan_run_directories` filters the run root by one receipt's `plan_hash[:16]`, so finding an interrupted run's working copy required already knowing which run was interrupted -- and being interrupted is usually why the operator stopped watching. `aart doctor` is told nothing and reports the working copy at the path the engine actually created, with the plan-hash prefix that ties it back, cross-checked against the receipt. `LAF-61` is preserved: the report names it and leaves it, contents unchanged, and says it does not delete them. `LAF-66` is preserved: the run root is supplied by the caller, never derived a second time. "No working copy" and "the run root could not be read" stay distinct. Seven E2E scenarios over CP-15 step 4b's real failing custom entrypoint, seven targeted mutations, and a fresh scoped run of 43 mutants at 40 killed, whose survivors found four gaps the manual mutations had not -- a falsey-but-not-`false` `readable` that is `null` in JSON, and `continue`/`break` and `or`/`and` at the loop guards, which one working copy alone can never distinguish. Step 4b puts the audit trail behind a verb (D-143). `project_activity`, `activity_from_receipts`, `activity_view_to_data` and `render_activity` all existed and were referenced only by the TUI's assembly, so the record INV-191 makes the audit evidence was reachable from the interactive shell and nowhere else -- the third capability in this slice found sitting at a seam with no verb reporting it. The report now carries the day-grouped timeline and each recorded action's own undo answer, asserted to share the same recorded moments so they are one observation rendered twice. INV-192 is held as a pair one flow produces: an install reports an undo naming `delivery:claude` and `payload`, and the uninstall that follows reports none because nothing retained can reverse a removal. D-143 records what the first draft got wrong -- it cross-checked Doctor's undo against `marketplace receipt show`, which returns the *setup* receipt, a different record with no `recorded_at` or `undo` at all. Six mutations, each red only where claimed; the finding was that removing the "nothing has been recorded yet" line killed nothing, leaving the human report free to print a bare header that reads as a failed rendering rather than an idle machine. Step 4c completes step 4 by reporting the two configurations a machine honours in silence (D-144). A source with `enabled: false` is skipped by every other part of the report deliberately, so an operator asking why nothing offers an artifact saw a report that source did not appear in at all; and an organization policy that sets a reporting field replaces the value in the user's own configuration file, where `_locked_override_diagnostics` answers only the *runtime* override and `EffectiveConfiguration.locked_fields` had no reader anywhere in the package. Credentials were the fifth capability in this slice found built at a seam with no verb reporting it. Both empty cases are answered in words, and the no-leak guarantee is asserted structurally against `CredentialObservation`'s field names, so a future field called `value` fails there rather than reaching the report. Two claims are held at the seam for reasons named in the test file -- a populated credential list would write to the developer's real Keychain, and installing an organization policy would mean writing to a root-owned system path -- which is CP-15 step 8's recorded precedent. Nine targeted mutations, each red only where claimed. The finding came from the scoped run before a single mutant executed: its baseline failed on step 2's `assertNotIn("installed", output.lower())`, which scanned the whole report while claiming something about the offline capabilities alone, and the new credential section legitimately says "no installed artifact references one". The assertion is now scoped to the offline block and a mutation putting the word into that renderer still turns it red; D-144 records the general form. A second finding repeated step 4b's exactly: six credential payload keys and the disabled source's `kind` were published with no test reading any of them, and the human line for a credential nothing depends on was unheld -- all closed, taking the scoped run from 421/595 killed to 450/595 with no survivor left in any of this step's four functions; the remaining 145 are B-060's 84 in `_run_repair` and the new B-061's 47 in the report composition. Step 5 closes the slice on three things (D-145). The front door: `aart doctor --help` still described the step-1 report, naming one of the six sections the command now carries, so four steps of newly reachable capability stayed undiscoverable short of running the verb and reading its output; the help now names every section, says the report alone changes nothing, and is held by `doctor_help_e2e_test`. The universal halves: three times in this slice a scoped run found a gap whose immediate fix was to add a second item to a fixture -- `continue`/`break` in 4a, the undo separator in 4b, the dependant and locked-field separators in 4c -- which fixes the instance and not the kind, so `doctor_properties_test` states the claims as Hypothesis properties and eleven targeted mutations prove they hold, three of them (`disabled[:1]`, `dependants[:1]`, `runs[:1]`) being exactly what no single-item fixture can express. That run then found two real gaps in step 4a's own claims: the unreadable-run-root branch had no human-output assertion anywhere, leaving the report free to answer "I could not look" the way it answers "there is nothing here" -- the confusion D-142 exists to refuse, standing on the surface an operator actually reads -- and `LAF-61`'s promise was held by the fragment "does not delete" rather than its sentence. Both closed; `orphaned_runs.py` now kills 25 of 25, up from 40 of 43. The invariant walk moves INV-189, INV-191 and INV-192 to EVIDENCED and deliberately leaves INV-190 PARTIAL, because its sentence has two halves and a read-only report that lists affected consumers does not show that `replace` and `verify` account for them. | CP-16 is VERIFIED across all five steps. `aart doctor` is a complete read-only support surface -- installed health with minimal repair plans, offline readiness, interrupted-run working copies, the activity trail with each action's undo answer, credential health and the configuration the machine is ignoring -- and mutates nothing unless `--repair --yes --expect` are all present. Open questions are backlog only: B-060 and B-061 (unclassified mutation survivors in the repair entry point and the report composition) and B-062 (no credential provider reads as no credentials). |
| CP-17 Git-backed live acceptance | VERIFIED | Steps 1 and 2 are VERIFIED. Step 1 (D-146): the exact candidate from a real system-Git acquisition survives validation, atomic publication and a fresh store read, including Git's real SHA. Step 2 (D-147/D-148): a real user configuration retains a valid HTTPS source identity while only the acquisition port substitutes the temporary Git transport; public `source sync`, `marketplace list` and `marketplace install` then carry the real SHA into the returned and durably re-read lifecycle receipt and place the promoted Skill bytes. Its first RED exposed B-057's consumer half -- a promoted versioned registry was interpreted as an older compiled maintainer workspace -- so validation now dispatches each representation to its own existing authority and the read-only Marketplace reuses the canonical approved-registry projection. The legacy `registry publish` disagreement remains backlog. A placeholder-revision mutation fails exactly at the receipt; fresh scoped mutmut killed omission of the revision and omission of promoted-registry validation after adding the empty/stale-catalog negative. Full `make quality` is green with 3,295 tests, one skipped and 85.39% branch coverage; separate `make integration` is green with 324 E2E tests.  Step 2 was then independently reviewed (D-149), adding tests only. D-148's two guarantees -- a revision is a pinned Source revision, and every added field is optional so existing receipt bytes keep their canonical form -- are claims about inputs the chain cannot produce, so they were re-measured rather than accepted, and they came apart: deleting the `is_pinned_source_revision` clause from `ResolvedArtifact.__post_init__` left all 3,349 tests passing, while the decode tolerance was held incidentally by a round-trip whose name speaks of rebuilding an activity entry over a fixture that happens to carry no revision. `tests/git_revision_provenance_test.py` states both -- the shape as a Hypothesis property over every string that is not a pinned revision (D-145), the durability as the D-138 pair, plus the distinction between a key omitted and a key written as `null` -- with three mutations each red only where claimed and a scoped run leaving no survivor in the code those tests claim (B-063 records its twelve, all in `_safe_line` and the sort keys).  Step 3 is split the way CP-16 step 4 was, because the installed artifact *starting* and the installation *following* its upstream need different fixtures. Step 3a is done: the same Git-backed fixture re-promotes the registry with both versions, replaces the repository's working tree and commits, and one continuous run then holds five claims through public verbs -- a second sync reports the new commit; the delivered bytes are still the ones reviewed at install, so the sync offered and applied nothing; `marketplace update` without `--yes` reviews, names 1.3.0 and writes nothing; the confirmed update with the review's `--expect` digest converges the delivery and records a receipt naming the new commit; and the durable audit trail holds both revisions at once. Three mutations, of which the third justifies the increment: writing the source store's current pointer once and never advancing it turns this test red on a stale `1.2.0` offer while step 2's chain test still passes, because a fixture that syncs once from an empty store cannot see a pointer that never advances. Going to look for a second instance of D-149's gap also found one -- `ApprovedRegistrySnapshot` validates its `resolved_revision` exactly as `ResolvedArtifact` does, and deleting that guard likewise left all 3,357 tests passing -- and both are now stated as properties. No production code changed in either increment.  Step 3b completes step 3. `mcp_stdio_e2e_test` starts a real MCP server but assembles the installation itself -- payload written by hand, environment created by hand, `generate_launcher` called directly -- so nothing joined that runtime to the chain in front of it. `git_backed_runtime_e2e_test` carries an MCP artifact through the same real Git repository with public verbs only; the receipt's four effects (`copy-tree`, `create-python-environment`, `write-file`, `configure-harness`) show a virtual environment was really built, and the launcher the install wrote then answers `initialize`, `tools/list` and `tools/call` over stdio, running on the interpreter the install created, with the `--strict` argument the manifest declared, unable to import `agent_artifacts`. A second test starts what `.mcp.json` names. The artifact declares no inputs as a claim rather than a choice: the CLI has no flag that answers one, so an artifact declaring one is refused with `consumer-invalid` naming each field, and nothing is built -- no runtime directory, no harness entry, no receipt. The finding is where that refusal lives: disabling the adapter's own guard in `io/configured_installation.py` killed nothing because the CLI never reaches it, and the refusal an operator meets is `commands/marketplace.py`'s, the adapter's being a second line of defence with no public flow through it. Three mutations, each red only where claimed. B-064 records the CLI-cannot-answer-inputs capability question; B-065 records that `marketplace list` publishes a provenance `resolved_commit` of all zeros beside the real `source.resolved_revision`, which is the maintainer half of the chain still being synthetic.  Step 4 asks what `aart doctor` says about the installation the chain built, and is the first step in this slice to change production code. Measured against the live Git-backed MCP installation under four kinds of real damage, a rewritten launcher was reported `broken`, divergent and repairable -- while all three kinds of payload damage were reported `health: ready, drift: []`, with the server itself exiting 1. D-150 has the cause: both observers measure the payload, and both current-state builders then discarded it through `item.id in wanted`, because a doctor supplies no `payload_source` and so nothing desires the payload. Omitting it from the *desired* state is right -- guessing where a tree came from would overwrite it from somewhere nobody chose -- but that is a statement about repair, and it was being used as a reason not to report. INV-228 (external drift is surfaced) and INV-175 (AART says when it cannot repair rather than fabricating a guarantee) are both about reporting, and neither asks for an invented repair. `_reported` now keeps a damaged undesired payload and `compare_states` names it by what is wrong (`missing`/`divergent`) rather than `UNEXPECTED`, whose remedy is uninstall; `repairable` stays false, and the repair planner already escalates it. The first attempt kept every damaged undesired component and broke 15 tests, two of them rightly: `installation_health` turns any unrepairable drift into BROKEN including UNVERIFIABLE, and on a removal state absence is the goal -- so the keep-rule is payload-only and ABSENT/DIVERGENT-only, and mutation 4 is those tests catching the widening. The change also exposed a fixture that was lying: `placed_machine_e2e_test` recorded `"a" * 64` as its payload digest while measuring the real tree only for the delivery, so every `ready` it asserted was about a payload nobody had (D-091's shape again, surfacing as `'ready' != 'broken'`). And it forced D-029's distinction into the type: `InstallationObservation.payload_present` was `bool = False`, so any partial observation implicitly claimed the payload was deleted, and is now `bool | None`. Four targeted mutations, each red only where claimed. INV-228 and INV-175 move to EVIDENCED for the placement path, where a tree digest exists on both sides. B-066 records what is left: the installation path has no tree digest on the observation or the receipt, so an MCP payload rewritten in place is still invisible and only whole-tree deletion is caught -- stated in the observed component's detail rather than claimed as health. Step 4's other two halves complete it. Uninstall was proven reverse reconciliation only against installations a fixture assembled; `GitBackedUninstallE2ETest` starts the server first, then removes it through the public verb -- four effects in reverse dependency order, every step applied, the runtime gone, no `notes` left in `.mcp.json`, and doctor reporting a clean machine rather than a record for something that no longer exists (which after D-150 would now read `broken` forever rather than merely stale). Dropping the harness components from `removal_state_from_receipt` leaves `.mcp.json` pointing at a deleted launcher; removing the tree non-recursively turns all three red and does it honestly, with `Directory not empty` and a `partial` session rather than success over a tree still standing. Rollback's honest answer here is that there is none, which is INV-192's actual subject: building a virtual environment is not reversible by anything retained, so the receipt reports `undo.available: false` naming `runtime-environment` rather than refusing generically, and asking anyway is refused as `receipt-no-setup` with remediation while the tree stays untouched and the server still answers `initialize`. Forcing `irreversible` empty makes the receipt claim it can be undone and turns that one red alone. **Step 4 is VERIFIED.** All nine quality gates are green; `make integration` is green. Step 5 splits. Its bulk half is VERIFIED: an MCP server and a Skill published into one repository and installed in one confirmed run, each getting the installation its kind needs -- the server built into a runtime that starts beside the Skill, the Skill placed with neither an environment nor a launcher -- both carrying the same real commit into one receipt, with doctor reporting both ready. Forcing `_is_delivered` false turns all four red with an honest `installation-not-described`; letting only an `mcp` member carry its revision turns exactly the one test claiming it red. Its Collection half is blocked and that is the finding: `io/configured_selection.py` skips every approved version whose kind is `collection` and leaves `ApprovedRegistrySnapshot.collections` at its default, so no public verb can ever see a Collection -- `marketplace list` returns `"collections": []` while offering both members, and installing one answers `collection-not-found` with empty remediation. B-067 records it; `CollectionsAreNotReachableTest` pins the gap as an honest refusal so it cannot become a partial install. D-151 decides it: B-067 is not reclassified, and step 5 is complete for what CP-17 can prove. The gap is not a projection bug -- `CollectionCandidate` reaches six modules and `promotion.py` is not among them, `collection_active` reaches candidate history and stops, so no collection candidate is promoted, no registry version of kind `collection` is published anywhere, and no test publishes one; resolution is the one built part, which is what makes it look smaller than it is. Closing it needs promotion, registry representation, the configured projection and member install planning together, which is a vertical capability slice rather than a step inside an acceptance slice. **CP-17 is VERIFIED.** | CP-18 migration and release gate, unless the Collection capability is scheduled first: B-067 now carries the four-layer scope, and INV-186 and INV-213 cannot be evidenced through any public verb until it exists. |
| CP-18 Migration/release gate | VERIFIED | Steps 1–4 are complete: runtime purity is checked against the import graph; the CI/release profile contract is evidenced; only genuinely replaced legacy authority was removed; and public documentation is reconciled against the real parser. Step 5 is complete: the traceability matrix moved from 121 PARTIAL rows to 234 EVIDENCED / 8 honest PARTIAL / 0 CONFLICT. INV-081–105 are now held by one Release Please authority, Conventional Commit PR-title validation, a human-merged generated release PR, and artifact-first release CI. The manual version/changelog/cut-release stack is removed; issued schema freezes remain immutable (D-160–D-165). `scripts/release_artifact.py` verifies the wheel against its tag, including zero runtime dependencies and a clean-environment smoke run. Three deliberate mutations independently broke SemVer mapping, runtime-dependency refusal and workflow wiring. A fresh scoped mutmut run generated 373 mutants: 174 killed, four inspected equivalent/cosmetic survivors, and 195 real-install/entry-point mutants exercised by the closing artifact gate rather than per mutant. The run exposed and fixed the runner's hard-coded source root (D-166). B-068 became critical when the new manually dispatched deep-quality workflow invoked mutmut unattended; the regenerated lock now provisions mutmut/Textual under a dev-only Python `<4` marker. D-167 then corrected the first public-run failures without relaxing a gate: Poetry/tomli are locked, RFC 3339 UTC parses on 3.10, and platform/configuration fixtures are isolated. | All six steps are VERIFIED. Closing evidence: nine quality gates green over 3,322 tests on clean Linux Python 3.10, 3.11 and 3.14 (at least 85.09% branch coverage), 343 separate E2E tests green locally, a consistent Poetry lock, and a real built `aart_cli-0.0.1-py3-none-any.whl` passing metadata, dependency and clean-install smoke verification against tag `v0.0.1`. The mandatory execution plan is complete; eight traceability rows remain honestly PARTIAL against named absent capabilities/process claims. |

### Post-refactor manual acceptance (2026-09-04)

B-077 is done (D-168). The canonical TUI now advertises `↑/↓`, Enter, Space, Esc, `?` and `q` on
its first frame and every frame thereafter. Its complete contextual key list remains behind `?`;
the permanent footer is the discoverable route to it. Curses pins the footer below the body instead
of clipping it with a long screen. Both regression tests were red against the prior behavior; 67
focused shell, terminal-entry, text-fallback and layout tests are green.
Full verification is also green: all nine quality gates over 3,324 tests at 85.35% branch coverage,
and the separate 343-test integration run.

B-078 through B-082 are implemented for the next manual pass (D-169–D-171). Esc's terminal-prefix
delay is explicitly 50 ms; the highlighted Dashboard destination has a short explanation; zero
sources produces a `SETUP REQUIRED` first-run callout above Dashboard navigation and matching
guidance in Registries. Screen 21 now connects an
approved remote Git registry through the canonical source-add transaction after an exact review;
local paths remain Maintainer authoring Sources. The two August user-level
registry subscriptions were reviewed and removed via `aart source remove`, including their managed
snapshots, and a fresh public list returns no sources. The focused consumer/source suites pass 113
tests and typecheck. Per operator request, this feedback increment deliberately did
not rerun the full quality or integration gates; it awaits manual acceptance before commit.

D-172 makes that remaining acceptance repeatable. The full Registry → Marketplace → Install →
Update → Doctor/Repair → Uninstall walk now lives in
`docs/testing/END_TO_END_ACCEPTANCE.md`, with separate maintainer and consumer homes and real Git
publication boundaries. Findings from the walk have one queue: the current section at the top of
root `TODO.md`. Its older body remains the historical `M1F1/agent-artifacts` tracker and is not
product authority.

The TUI-first expansion uses `aart.yaml` in both external author repositories and exposed two more
honest surface gaps (D-173): Maintainer Sources has Sync but no Add Source (B-083/QA-009), and
consumer Registries has Add but no refresh after a new publication (B-084/QA-010). The local
machine-specific guide marks both minimal CLI fallbacks at their exact boundaries; it does not
count the downstream TUI flow as evidence for the missing actions.

OpenCode is also an honest gap, not an installed target (B-085/QA-011, D-174). OpenCode 1.18.29 is
present on the acceptance Mac, but the canonical MCP, delivery, memory and hook tables contain no
OpenCode targets and the TUI fixes its harness set to Claude/Tabnine. The dormant best-effort
profile is not reused because its MCP shape disagrees with OpenCode's current native configuration.
The local walkthrough now measures the no-write refusal explicitly.

Codex is likewise an honest unsupported target, recorded separately because its native contracts
are different (B-086/QA-012, D-175). Codex CLI 0.152.0 is present on the acceptance Mac, but the
canonical tables, built-in registry and TUI contain no Codex target. The local walkthrough declares
Codex compatibility and measures its no-write refusal; a future slice must use `.agents/skills`,
layered `AGENTS.md` and Codex's TOML `mcp_servers` format rather than aliasing another harness.

The operator's first real Registry initialization added B-087/QA-013 and B-088/QA-014. Optional
usage-reporting files are emitted even without the opt-in destination and then described as inert;
the confirmed human output also prints the same three warnings twice and repeats its path inventory
inside a long follow-up command. Both are post-refactor usability findings and do not change CP-18's
VERIFIED status.

Auditing that empty Registry added B-089/QA-015: the command passes, but renders two
not-applicable checks as dense warnings about unassessed risk and partial provenance. The empty
human result needs one clear explanation; actual missing evidence on a populated Registry must
remain visible.

The same bootstrap exposed B-090/QA-016: screen 46 cannot initialize a new Registry, leaving five
AART commands and the publication handoff outside the TUI. The desired local flow is one form, one
review and a fail-fast init/lock/build/validate/audit pipeline, optionally followed by an explicit
local commit. Automatic push and Git-host configuration remain outside AART's publication authority.

The next interactions added B-091/QA-017, B-092/QA-018 and B-093/QA-019. Add Registry leaks literal
CLI commands into a clipped TUI notice and leaves a refused preparation stranded on a Review screen
with nothing to confirm. Adding the Superpowers Source then correctly refused its sole Git symlink
but called it only an `unsafe entry`, giving no actionable explanation. These are post-refactor
manual-acceptance findings; no security boundary is to be weakened.

The clarified acceptance model exposed critical B-094/QA-020. Superpowers is intentionally a
monitored authoring Source; explicit YAML should become a Candidate and only its selected promotion
should enter the Registry. `source add` instead validates through the canonical native-package
loader before Maintainer Sync reaches the YAML compiler, so the accepted Source → Candidate path is
blocked. Neither print-only `registry scan` nor direct vendoring supplies the missing monitored TUI
flow. CP-18 remains historically VERIFIED, but post-refactor live acceptance cannot continue past
this mandatory entrance until B-094 is fixed.

B-094/QA-020 and B-083/QA-009 are now **fixed and awaiting manual retest** (D-176, D-177).
`validate_authoring_source_candidate` separates authoring-Source admission from consumer
native-package validation: a tree declaring root `aart-source.json` is still read by
`load_native_source`, any other tree is admitted when `discover_author_manifests` finds at least one
explicit `aart.yaml`/`aart.json`, and a tree declaring neither is refused by name. Admission is
discovery rather than compilation, because 164.2's `3 manifests · 1 invalid` Source row makes an
invalid manifest a Candidate state, not a subscription refusal. No transport, identity, symlink,
special-file or last-known-good boundary moved: symlinks and special entries never reach validation
at all, and the E2E fails itself if the public path requests weakened transport. An authoring
Source's declared identity is its configured alias, so an upstream commit is not read as an identity
transition, and its consumer Marketplace contribution is empty rather than an `Err`, which is what
stops one subscribed author repository from emptying the Marketplace. Maintainer screen 31 gained
`a` Add Source with its own form (31a) and review (31b), accepting only `source-git`/`source-local`
and executing through the same `add_configured_source` transaction as the CLI. Evidence:
`tests/authoring_source_admission_e2e_test.py`, `tests/source_validation_test.py`,
`tests/consumer_runtime_test.py`, `tests/maintainer_source_addition_test.py`,
`tests/maintainer_navigation_test.py`; ten targeted mutations, all killed. Focused suites, `ruff` and
`mypy` are green; full gates are deferred to the end of this manual-acceptance batch by the
operator's instruction. CP-18 remains historically VERIFIED.

B-084/QA-010 and B-087/QA-013 are now **fixed and awaiting manual retest** (D-179, D-180). Screen 21
routes `s` to a distinct `REGISTRY_SYNC` action whose review (21c) names the ref that will be
fetched, states PS 161.7's rule that a registry refresh is not an artifact update, and says a failed
fetch keeps the snapshot already held; execution goes through `sync_configured_sources`, the single
transaction `aart source sync` also uses, and `_prepare_registry_refresh` refuses a row that is not
a connected registry, so INV-199 stays testable rather than asserted. `registry init` now writes the
usage-reporting Issue Form and its two workflows only when `--usage-reporting-repository` names a
destination, and the generated README describes the registry that was actually created. Evidence:
`tests/consumer_registry_refresh_test.py`, `tests/registry_init_scaffold_test.py`; targeted
mutations killed, focused suites green.

B-089/QA-015 and B-088/QA-014 are now **fixed and awaiting manual retest** (D-181, D-182). An empty
registry's audit reports the provenance-coverage and installation-risk checks as `info` notes —
what the audit did rather than what it found — and both become warnings again the moment an
external reference or an owned package exists. A confirmed Maintainer action states its result
once: the outcome no longer repeats the warnings its review just stated, drops an `observed:` count
equal to its own headline, and the follow-up commands are the AART pipeline without the `git diff`
line that re-listed every reviewed path. `registry init` also stopped warning that the
usage-reporting templates were inert, because D-180 no longer writes them. `--json` is unchanged
and still carries review and outcome in full. Evidence: `tests/registry_empty_audit_test.py`,
`tests/curation_outcome_brevity_test.py`, `tests/registry_cli_integration_test.py`; thirteen
targeted mutations, all killed; verified through the public CLI.

B-093/QA-019 is now **fixed and awaiting manual retest** (D-183). The Git acquisition refusal is
unchanged and still fail-closed, but each refused entry names the kind that was observed — symbolic
link, submodule, unsupported Git mode, unsafe path or excessive depth — and carries remediation for
that case. A symlink's target is never printed, because it has not passed the repository's
path-safety rules. Deciding the entry kind before reading the size also stopped reporting every
submodule as a malformed listing, since `ls-tree -l` gives a gitlink no size. Evidence:
`tests/git_unsafe_entry_diagnostic_test.py` and a real committed symlink driven through the public
`source add` in `tests/authoring_source_admission_e2e_test.py`; nine targeted mutations, all killed.

B-092/QA-018 is now **fixed and awaiting manual retest** (D-184). A preparation that refuses returns
the session to the screen the action was asked from and clears the pending action, so no screen goes
on advertising a confirmation for a plan that does not exist and a later Enter cannot reach the
execution boundary. For Add Registry that screen is the form, with the operator's values intact. The
notice is drawn there because `_ANSWERABLE` now includes `ACTION_REQUEST_SCREENS`, derived from
`_ACTION_REVIEW` rather than hand-listed twice. Two consumer E2Es were corrected to the new landing
screen — both of their names already described it — keeping every other assertion and gaining a
check that no action stays pending. Evidence: `tests/consumer_declined_preparation_test.py`,
`tests/consumer_application_e2e_test.py`; five targeted mutations, all killed.

B-091/QA-017 is now **fixed and awaiting manual retest** (D-185). `Diagnostic` carries an
`interactive` projection beside `remediation`: the same next step written for somebody already
inside the application. `_refusal` renders that when a diagnostic has it and otherwise only the
remediation steps that name no command, so an unconverted producer degrades to saying less rather
than to printing shell syntax, and a refusal whose every step was a command still says that the next
step lives elsewhere. The duplicate alias, duplicate origin and ref, changed declared identity and
the two unsynchronized-source catalog refusals now carry prose that names this machine's own state.
CLI and JSON remediation contracts are untouched. Evidence:
`tests/tui_has_no_cli_commands_test.py` — the projection, `QA-017`'s own scenarios, a sweep over
every `ConsumerScreen` and `MaintainerScreen` drawn with a command-carrying refusal on it, a
sensitivity test for that sweep, and a Hypothesis property for the universal half; seven targeted
mutations, all killed.

B-090/QA-016 is now **fixed and awaiting manual retest** (D-186). Maintainer screen 46 offers `n`
Initialize Registry: a form (46a) collecting the registry ID, display name, an optional
usage-reporting destination and the one opt-in local commit, and a review (46b) that names all five
stages and states that nothing will be pushed or merged. One confirmation runs init → lock → build →
validate → audit fail-fast through `agent_artifacts/io/registry_bootstrap.py`, which is the ordering
and nothing else: the three writing stages go through the same `LocalCurationService` prepare/
finalize pair the CLI drives and the two gates are the same planning functions. The commit is part
of the review digest, so the two commit choices are two plans, and a test records every `git` call
the run makes and asserts none is `push` or `merge` — 165.27's publication authority stays with the
repository. A partial run is a report rather than an exception: the stages are a prefix of the five,
nothing is re-read, and the result says which stage stopped it. Evidence:
`tests/maintainer_registry_init_test.py` (19 tests, including one end-to-end confirmation that
leaves four real files in a project checkout); eleven targeted mutations, all killed.

Two regressions in the uncommitted manual-acceptance work were found and repaired while proving this
increment (D-178): the first-run welcome panel replaced the Dashboard body on a machine that had no
configured source but did have an installation, and the deferral of `load_local_reporting_service`
into `completion_factory` outran a test seam that substituted it only around composition. The
deferral is correct and kept; the panel now also requires nothing installed.

B-095/QA-021 records a second, complementary onboarding capability: scan explicit YAML manifests in
a repository without persisting it as a Source, select artifacts, and vendor only their declared
payload with pinned provenance. Four existing registry commands hold fragments of that flow but
nothing joins them or exposes it in TUI. Upstream movement would be an explicit per-artifact check,
not continuous Source monitoring.

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

## Canonical setup runs are readable through the public receipt verbs (D-130)

`aart marketplace receipt show|verify|undo` follows the setup pointer off a canonical installation
receipt as well as out of the retiring install-state manifest. Before this, a configured install
performed a real setup run (D-128) and then answered every question about it with "this scope has
no installation state": the effect was on disk, the record was under the data root, and neither was
reachable. The canonical store is asked first and the manifest second, so a machine holding only
legacy installations answers exactly as it did before.

Three things the canonical store's shape forced, each measured: scope is checked against the record
rather than rebound to it, because the store partitions nothing by scope; the profile is taken from
the record, because a receipt can serve several harnesses while setup ran for one; and the
manifest's "no installation state in this scope" is kept only when the canonical store is also
empty, because on a configured machine it names a file that will never exist. An install that
declines setup writes a `cancelled` record with its retry command, and `receipt show` finding that
is the useful answer, not a refusal -- an expectation this work corrected rather than enforced.

Acceptance is `tests/configured_setup_gap_test.py::ConfiguredReceiptVerbsTest`, which installs
through the public command and drives all three verbs over what that install recorded, with no
fixture standing in for any part of the chain.

## AART says what removing a leaked credential does not do (CP-15 step 5, D-135)

Product Specification 165.10 requires two things and CP-15 step 5 measured them apart.

The purge boundary held on shipped code, in the strongest available form: there is no `purge` verb
anywhere in `agent_artifacts`, and the registry lifecycle only deprecates and revokes. So
`tests/withdrawal_and_purge_e2e_test.py` measures the ordinary case instead -- a real upstream that
deletes an artifact and re-points its Collection, then `aart source sync`. The artifact stops being
offered and installing it is refused with a remediation; what is already installed is byte-identical
and reports `removed-upstream`; the payload stays in the content-addressed store; and `uninstall`
still works, so not-deleting never becomes not-removable.

The erasure claim did not hold. The `embedded-credential` finding -- the only place AART tells
anyone a credential is sitting in artifact content -- said "remove the value, rotate it if real",
which by saying "remove" with no caveat implies removing is what closes the leak. Artifact content
is published from a version-controlled source, so it is not. The remediation now states that
removing the current payload does not guarantee removal from Git history and names the repository's
own secret-removal procedure as still owed. The ruleset revision label stays `baseline-v1.1`
(D-135): the remediation is inside `BASELINE_RULES_DIGEST`, so recorded evidence goes stale on its
own, and the label is quoted in published compatibility documents as naming a *detection* ruleset
that did not change.

INV-221 and INV-222 both move from PARTIAL to EVIDENCED. Six targeted mutations, one per claim
group. The scoped `make mutants` run over `security/baseline.py` returned its first finding worth
acting on -- the assignment credential detector decided nothing in any test, because every fixture
also carried a vendor-shaped token -- and `security_baseline_test` gained the prose case that
isolates it. B-055 records the `ArtifactLifecycle.REMOVED` merge path no production caller reaches.

## What is installed now says whether the policy still allows it (CP-15 step 6, D-136)

`aart marketplace status` reported one word per installation and it was about the payload. An
artifact installed under a permissive policy, on a machine whose administrator later required
`registry-reviewed` trust for user scope, reported `current` -- while `aart marketplace install`
would have refused the very same artifact. Product Specification 165.21 makes compliance part of
health, and 165.23 asks that a development install stay distinguishable from a reviewed one after
the install is over. Both turn on the same fact: the trust an artifact's content came from.

Every lifecycle item now carries a `PolicyStanding` -- compliant, non-compliant with the unmet
requirement named, or `not-evaluated` where no current trust can be read -- plus the trust itself,
reported in the JSON payload and in the human rendering. It is a dimension beside `status` rather
than a new status value (D-136), because an installation can be out of date *and* non-compliant and
one slot cannot say both. The rule is the installer's own: `trust_shortfall` is now public and
`lifecycle` asks that function, so the gate and the health report cannot drift apart.

Nothing is mutated by the drift: 165.21 asks for a decision, and status remains a read.
`tests/policy_drift_e2e_test.py` drives it over a real machine whose administrator policy is
rewritten between commands, and asserts on both sides -- that the installation is untouched, and
that the operator is told. INV-233 and INV-237 move from PARTIAL to EVIDENCED.

Writing it found that the domain `EffectivePolicy` never reaches the consumer path at all: both
consumer seams construct the permissive default and nothing composes one from configuration
(B-056). The policy that is live is the administrator's `OrganizationPolicy`, and that is what the
compliance report judges.

## A local promotion is not a publication, and now something says so (CP-15 step 7, D-137)

Product Specification 165.27 splits the authority -- AART owns artifact and registry validation and
preparation, existing Git hosting owns branch protection, review and merge authorization -- and
165.28 draws the consequence: a local promotion or commit is not yet Published. Publication is
presence on the canonical consumer-visible branch, which a person or CI puts it there.

`registry promote --yes` already honoured that boundary exactly. It reports `commit: false` and
`push: false`, and it makes no commit, creates no branch, adds no remote and leaves every path it
wrote untracked for someone to stage. Nothing said so. `tests/promotion_publication_boundary_e2e_test.py`
now does, in nine tests, and it is the one CP-15 increment that changed **no production code** --
which is the finding, not a disappointment. The failure it guards against is a promotion quietly
becoming visible to consumers, and that failure is invisible in the maintainer's own terminal, where
everything looks like it worked.

The arrangement carries the claim (D-137). A maintainer's registry checkout and the published
registry a consumer is subscribed to are two separate directories, because in production they are
two states of one repository separated by a push and a merge. Promoting straight into the consumer's
source gets the right answer for the wrong reason: the consumer stops seeing the artifact because
`registry promote` writes a versioned layout the source validator then rejects (B-057), not because
the promotion was unpublished. The consumer here re-synchronizes after the promotion and is still
offered exactly what it was offered before, digest for digest, and still refuses to install the
promoted coordinate.

Two mutations found gaps in the new tests before they found anything else. The evidence test omitted
both required digests at once, so making either `--validation-report` or `--policy-result` optional
on its own survived it -- half the requirement could have been deleted under a green test named for
it; each is now asserted independently, in its own workshop. And the install-refusal test was resting
on a stale snapshot rather than on the boundary, staying green under a simulated push; it now
synchronizes first. The simulated push -- the promoted tree copied across, which is the publication
AART deliberately omits -- turns exactly the three consumer claims red and nothing else.

INV-238, 240, 241 and 242 move from PARTIAL to EVIDENCED. The Git hop itself stays with CP-17:
`git_location_parts` admits no `file://` remote, so branch protection, pull requests and the merge
that constitutes publication cannot be driven from this repository. Probing the two verbs against
one checkout also found B-057 -- `registry promote` writes a versioned layout `registry publish`
refuses, and `publish` requires an `aart-registry.json` workspace marker that `promote` does not --
which whoever opens CP-17 should read before driving them in sequence.

## The credential another artifact still needs (CP-15 step 8, closing the slice)

Product Specification 165.19 says old credentials remain if still referenced by other installed
artifacts. Nothing held it, and the reason was structural rather than an oversight: every credential
test in this repository has exactly one installation in scope, and what happens to B when A changes
cannot be measured with only an A.

Nothing needed changing. `aart marketplace uninstall` already says `credentials: retained` in both
renderings, `delete_credentials` defaults false through `prepare_configured_uninstall` and no
command-line verb sets it, and `_dependants` keys on the credential reference rather than the
provider account -- so two artifacts sharing an account but binding different inputs are not
dependants of each other's credential. `tests/credential_contract_migration_e2e_test.py` holds all
of it, together with 165.19's other two statements: a value already held is not asked for again, and
a redeclaration conflicting with one another owner still binds is refused, naming both owners.

The finding is what the third mutation exposed. The first draft asserted "no effect in the reviewed
removal deletes a credential" through the CLI, and switching credential deletion on by default
**killed nothing** -- the fixture registry's Skill declares no inputs, so the test asserted an
absence in a scenario where nothing could ever have been present. The native source protocol has no
`inputs` field at all, so a native-source artifact reaches a credential only through its setup
recipe. The claim is now a pair of calls differing in one keyword: the call the command makes, and
the same call when asked to delete. The absence in the first is evidence only because the second
shows the deletion was reachable. A fourth draft test was cut for the same reason -- it read a
receipt step's `effect` as a dict when it is a string, filtering every step away and asserting over
an empty set.

INV-231 and INV-232 move from PARTIAL to EVIDENCED. **CP-15 is VERIFIED**: all sixteen invariants it
declared -- INV-210, 216, 218, 219, 221, 222, 223, 226, 231, 232, 233, 237, 238, 240, 241, 242 --
now carry public-flow evidence in place of the words *scattered source/registry/lifecycle
safeguards* they all shared at slice start. Exact-collection drift remains out of scope, waiting on
the Collection capability B-038 is sequenced behind (D-131).

## Update rule

Never mark a slice beyond the strongest evidence actually present.
`IMPLEMENTED` means code exists; `VERIFIED` requires relevant tests; `MIGRATED` means callers/flows
use the new path; `LEGACY REMOVED` requires the old authority/path to be safely removed.
