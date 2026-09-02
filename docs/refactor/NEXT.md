# AART Refactor — Next Work

## Current objective

Continue **CP-14 Maintainer TUI 30–53**, step 4: implement the Validation and Policy Review screens
38–40 over the Candidates screens 35–37 now expose. The validation engine those screens project is
already landed and green; what remains is the projection, the renderers and the shell wiring.

Screens 30–37 are live in the production shared shell:

- screen 30 and screens 31–32 compose configured authoring Sources, durable health and only an exact
  matching Candidate-history observation (D-093–D-095);
- `s` on a focused Source enters typed screen-33 review, and Enter executes only its digest;
  execution rechecks registry and Source baselines, compiles exact `aart.yaml`/`aart.json`
  manifests, and atomically writes/rereads Candidate history under the Source instance lease;
- local Sources carry `local:<snapshot-sha256>` rather than invented Git commits (D-096), and
  screen 34 renders the persisted readback and reports no registry mutation (D-097, INV-200);
- screen 35 lists active Candidates keyed by stable Candidate ID and narrowed by the typed
  `MaintainerCandidateFilter`; screen 36 is the full authoring detail; screen 37 is semantic diff
  first with the bounded raw file diff behind the `f` toggle (D-098, INV-202).

Evidence: `tests/maintainer_candidate_shell_test.py`, `tests/maintainer_candidate_views_test.py`,
`tests/maintainer_composition_test.py` and a real temporary production installation in
`tests/maintainer_composition_e2e_test.py`, which now walks from the consumer dashboard to screen 37.

## Already done in step 4

`agent_artifacts/application/candidate_validation.py` runs the ordered, named pipeline 164.6
describes over one compiled Candidate, with `tests/candidate_validation_test.py` (17 tests) green
and `make lint`/`make typecheck` clean:

- `ValidationCheck` names the ten pipeline stages and `VALIDATION_PIPELINE` fixes their order;
  every `CandidateValidation` carries a result for every check, in that order, so a screen can
  never silently omit a stage.
- `ValidationOutcome` keeps `passed`, `warning`, `error` and `not-run` distinct; `not-run` is not a
  pass, and live acceptance stays `not-run` until CP-17 produces real evidence.
- `ValidationCheckResult.findings` maps outcomes to `FindingSeverity`, and a warning or error with
  no actionable detail is refused at construction.
- `CandidateValidation.unmet_requirements` / `.manual_approval_required` read
  `EffectivePolicy.required_checks`, and `.state` feeds `assess_candidate`, so a required check that
  did not pass yields `APPROVAL_REQUIRED` rather than `WARNING` or `READY` (D-099).
- `validate_candidate(bundle, policy=...)` and `validated_candidate(bundle, policy=...)` are the
  entry points; both are pure and take the already-compiled bundle.

## Exact next action

Finish step 4 by making the screens 38–40 surface exist.
`tests/maintainer_validation_views_test.py.pending` is the RED specification already written for it:
rename it back to `*_test.py` and drive it to green. It pins, and the work is:

1. `MaintainerValidationRowId(candidate_id, check)` and `parse_validation_row` in
   `application/maintainer_views.py`. Screen 38's rows address a *pair*, because a check name alone
   is ambiguous across Candidates and a Candidate ID alone cannot open one check; `str(row)` is
   `"<candidate-id>:<check>"` and parsing refuses an unknown check or a non-hex ID (D-100 still to
   be written up).
2. `project_maintainer_validation(bundle, policy=...) -> MaintainerValidationView` — one row per
   `ValidationCheck` with a human label, the outcome, whether policy requires it, and its details
   carrying declared vs expected. Plus `.error_count`, `.warning_count`, `.unmet_requirements`.
3. `project_maintainer_policy_review(validation, bundle, policy=...) -> MaintainerPolicyReviewView`
   for screen 40: the decision, the required checks, what is unmet, the allowed runtimes,
   transports and network hosts (`None` when a policy does not constrain them, which is not the
   same as an empty allowlist), the risk ceiling, and the blocking findings.
4. `MaintainerViews` gains a fourth `validations` field and `.validation(candidate_id)`;
   `read_maintainer_views` composes them once, taking the `EffectivePolicy` as a parameter rather
   than reaching for configuration inside a projection.
5. `render_maintainer_validation`, `render_maintainer_validation_check` and
   `render_maintainer_policy_review` in `tui_maintainer.py`, then rows/detail/body in
   `tui_consumer.py` and a `p` binding in `key_event` opening POLICY_REVIEW from VALIDATION.
   Screen 40 must open from either a bare Candidate ID or a check row.
6. An E2E walk in `tests/maintainer_composition_e2e_test.py` reaching 38, 39 and 40 against a real
   temporary installation, and a drawing test that opens no file.

Keep warnings and errors distinct all the way to the screen: the projections must not collapse the
two into one severity column, and validation state is never inferred from a Candidate's state enum
alone.

## Critical boundaries for this slice

- Product Specification is the sole product authority.
- Source, Candidate, Registry and Marketplace remain distinct values and screens (INV-199).
- Source Sync never promotes and never mutates approved registry state (INV-200).
- Discovery remains exact `aart.yaml`/`aart.json` only (INV-201).
- Maintainer review is semantic diff first and raw file diff only on demand (INV-202).
- Published coordinate/version content is immutable; digest conflicts are explicit, never repaired
  in place (INV-203/239).
- Superseded, rejected and source-removed records remain durable audit history (INV-229).
- Secret values never enter views, state, plans, receipts, logs, fixtures or committed files.
- `key_event` remains the only key interpreter; there is one reducer and one persistent stdlib TUI.
- Machine state is assembled once outside draw functions; application projections have no IO/clock.
- Candidate list narrowing stays typed application state; screen 53 edits `MaintainerCandidateFilter`
  when it lands rather than introducing a second filter model (D-098).
- When screens 41–47 land, local Candidate promotion must preserve D-096 local provenance instead of
  passing through the currently Git-only registry-index projection by disguise.
- Do not retire legacy direct/local or Collection authority until the corresponding CP-14 public
  flow is proven. B-031, B-038 and B-039 remain ordered behind that evidence (D-091).
- Do not modify older AART repositories.

## Durable handoff rule

At the end of the next increment update `MIGRATION_STATUS.md`, this file, the CP-14 slice file,
`DECISIONS.md` for material choices and `BACKLOG.md` for noncritical discoveries. Run focused gates
after each TDD cycle and the full repository quality suite before calling a CP-14 segment verified.
