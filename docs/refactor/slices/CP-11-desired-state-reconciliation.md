# CP-11 — Desired-state reconciliation engine
Status: VERIFIED

## Goal

Model `DesiredState`, `CurrentState` and drift over independently inspectable components, and turn
a comparison into the smallest plan that repairs only what drifted. Effects whose capabilities do
not support independent repair escalate explicitly rather than being replayed silently.

## Product Specification sections/invariants

Section 158 and 158.1–158.10; INV-046, INV-069–INV-082 and the CP-07 effect capability metadata.

## Legacy/current paths

- `setup_verify.py` and `setup_verify_probes.py` hold the current verification behaviour.
- `setup_undo.py` holds the current rollback behaviour.
- `lifecycle/application.py` replays a whole installation rather than repairing a part of it.
- CP-10 produced the first real drift vocabulary: `VerificationFinding` and
  `observe_installation` already measure six component-level facts on a real machine.

## Target paths/owners

`domain/reconciliation.py` for the component, state and drift algebra and the pure comparison;
`application/reconciliation.py` for policy-filtered, ordered, minimal repair planning.

## Dependencies

CP-07 planning, CP-08 credentials, CP-09 environments and CP-10 projection are verified.

## Non-goals

- No execution of a repair plan and no lifecycle routing (CP-12).
- No TUI rendering of the reconciliation view (CP-13/14).
- No rollback semantics beyond naming what is not reversible.

## Characterization / RED evidence

New RED covers: an installation with no drift planning nothing; a single drifted component
planning only its own effects; a component nobody observed counting as drift rather than a match;
a component that is not independently repairable escalating instead of being rebuilt; a policy
violation failing the plan rather than dropping an effect; and execution order following component
dependency order rather than canonical sort order.

## Implementation steps

1. `domain/reconciliation.py`: `Component`, `ComponentId`, `ComponentState`, `DesiredComponent`,
   `ObservedComponent`, `DesiredState`, `CurrentState`, `DriftKind`, `Drift`, `compare_states`.
2. `application/reconciliation.py`: `RepairStep`, `RepairPlan`, `plan_repair`, `repair_converged`.
3. Bridge CP-10: build a `DesiredState`/`CurrentState` pair from a receipt and an observation.

## Property tests

Minimality: the planned effects are always a subset of the drifted components' effects, and adding
a matching component to both states never changes the plan. Determinism: the review digest depends
only on the plan's content.

## Integration tests

The CP-10 receipt/observation pair reconciles: a real edited launcher produces a launcher-only
repair, and a real removed harness entry produces a harness-only repair.

## E2E/live acceptance

A real installation is damaged in one component at a time and each damage produces a plan touching
only that component.

## Done

- CP-11 opened from verified commit `d39dfb0`.
- `domain/reconciliation.py` models the seven components §158.1 draws, ordered by dependency rather
  than by name, so a reader and an executor both see the cause before the consequence.
  `ComponentId` requires a name for the components an artifact has several of and refuses one for
  the components it has once.
- `DesiredState` and `CurrentState` are separate types over the same vocabulary, and a desired
  component nobody observed is `UNOBSERVED` drift rather than a match (D-029).
- `DesiredComponent` says both how a component is established and how it is corrected (D-030),
  which is what lets a missing credential be stored and a wrong one replaced without either
  operation being issued in the other's situation.
- `application/reconciliation.py` plans only the drifted components' effects, in dependency order
  (D-031), and fails rather than dropping an effect the policy forbids (D-032). `RepairPlan.complete`
  says whether running the steps would actually leave nothing drifted.
- A component whose effects are not all `independently_repairable` escalates by name — the CP-07
  `EffectCapabilities` metadata now has its first consumer.
- `application/installed_state.py` bridges CP-10: a receipt becomes a desired state, an observation
  becomes a current state, and the two are paired so describing less cannot invent drift (D-033).
- Proven against a real installation: an edited launcher plans a launcher-only repair, a deleted
  harness entry plans a harness-only repair, and a credential nobody inspected reports as
  unobserved rather than converging.

## Remaining

- Executing a repair plan, re-inspecting after it and routing the lifecycle intents through it is
  CP-12. `repair_converged` exists and is tested, but nothing calls it after real effects yet.

## Known compromises

- `DriftKind.UNEXPECTED` cannot yet be produced from a real machine, because the CP-10 inspector
  walks only the registrations a receipt names (B-023).
- Configuration components are modelled and tested but not yet produced by the bridge: a receipt
  holds config fingerprints (D-027) and repairing one needs the desired value from the plan, which
  arrives with CP-12.

## Backlog discoveries

- B-023 — detecting registrations nothing owns.

## Blockers

None.

## Legacy removal criteria

`setup_verify.py` and `setup_undo.py` become removable once CP-12 routes repair and uninstall
through this engine with the legacy characterization evidence still green.

## Handoff

- Current working state: CP-11 verified. Comparison, minimal planning, escalation and the CP-10
  bridge are complete and proven against a real damaged installation.
- Exact next action: open CP-12 (installed lifecycle on reconciliation) — execute a `RepairPlan`
  through the existing interpreters, re-inspect with `repair_converged`, and route install, update,
  configure, repair, credential rotation, harness reconfiguration, downgrade and uninstall through
  it.
- Do not undo: desired and current being different types; unobserved counting as drift; the paired
  bridge; establishing and correcting being separate effect lists; dependency-ordered steps; a
  forbidden repair failing rather than being dropped.
- Tests last run/results: full quality green — all ten gates, 2,161 unit tests, 56 E2E tests,
  83.33% coverage.
- Failure evidence: the pairing rule (D-033) came from a real failing test in which a healthy
  runtime environment was reported as `UNEXPECTED` drift because the desired state had been built
  without a base interpreter.
