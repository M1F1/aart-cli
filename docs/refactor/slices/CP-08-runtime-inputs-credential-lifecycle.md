# CP-08 — Runtime inputs and credential lifecycle
Status: VERIFIED

## Goal

Separate `ConfigInput` from `SecretInput`, value sources from process bindings, and
`CredentialReference` from credential values. Plan the full inspect/store/verify/replace/delete
lifecycle with dependent-artifact awareness, behind an explicit provider port whose first concrete
interpreter is the macOS Keychain — without any secret value entering domain or application code.

## Product Specification sections/invariants

Sections 14–21, 35, 37–39, 91–104 and 154–157; INV-048–INV-057, INV-051–INV-055, INV-067,
INV-159–INV-168, INV-180, INV-185, INV-190 and INV-232.

## Legacy/current paths

- `setup_runtime.py` `_keychain_apply`/`_advise`/`_stored_secret_length` hold the reviewed macOS
  Keychain behaviour: the secret is never read into the process, existing values are kept unless
  replacement is explicit, and a truncated paste is measured and reported.
- `setup_engine/*`, `setup.py` and `configuration/*` own the current text-input/config seam.
- `redaction.py` is the single redactor and must stay the only one.
- `runtime_contract.py` publishes the `keychain-secret` capability.
- No canonical runtime-input algebra exists: `domain/artifacts.py` has no `inputs`, and the CP-04
  compiler does not compile them.

## Target paths/owners

Frozen `RuntimeInput`/binding/guidance values and credential reference/observation values in
`domain/`; pure binding resolution and credential-mutation planning in `application/`; the
transient secret carrier and macOS Keychain interpreter in `io/`.

## Dependencies

CP-07 canonical facts/assessment/plan pipeline is verified.

## Non-goals

- No Python environment or dependency backend (CP-09).
- No launcher generation or harness projection (CP-10).
- No effect interpreter, receipt or reconciliation engine (CP-11/12).
- No Fast/Verbose UI (CP-13); both will project the same bound inputs.
- No additional secret providers beyond macOS Keychain (B-004).

## Characterization / RED evidence

Retain the existing Keychain apply/advise/rollback and setup text-input tests. New RED covers
secret/config type separation, binding independence from value source, the absence of any
persistent secret-value type, guidance metadata rules including secret example safety, required
input coverage, policy restriction over providers and bindings, dependant-aware replace/delete,
and the rule that no credential operation returns or logs a value.

## Implementation steps

1. Add `domain/inputs.py`: `InputId`, process bindings, guidance/validation metadata, `SecretInput`
   and `ConfigInput`.
2. Add `domain/credentials.py`: `CredentialProviderRef`, `CredentialReference`, provider/credential
   observation states and the credential mutation algebra.
3. Add `application/input_binding.py`: pure required-input coverage, source/binding compatibility
   and policy restriction, producing credential references and config values only.
4. Add `application/credential_lifecycle.py`: pure dependant-aware inspect/store/verify/replace/
   delete planning that never reads or returns an old value.
5. Add `io/credentials.py`: a transient secret carrier that redacts itself and cannot be
   serialized, plus a macOS Keychain interpreter behind the provider port.
6. Extend `EffectivePolicy` with runtime-input primitives that compose restrictively.

## Property tests

Binding kind cannot change which value source is legal; restrictive policy overlays cannot add a
provider or binding permission; no bound-input or credential projection ever contains a value.

## Integration tests

Real provider interpreter against a temporary store: inspect absent → store → verify → replace →
delete, with the old value never read and dependants surfaced before destructive mutation.

## E2E/live acceptance

Existing public setup/credential behaviour stays characterized; the canonical path reaches a public
flow in CP-10. Full remote-backed proof is CP-17.

## Done

- CP-08 opened from verified commit `d53f313`.
- `domain/inputs.py` holds the three separate axes. `SecretInput` and `ConfigInput` differ in
  lifecycle; `ProcessBinding` says only how a process receives a value; `InputValueSource` says
  only where the value comes from. Each binding pins its own `BindingExposure`, so a plan can say
  a delivery is weaker without the domain guessing at platform specifics.
- `domain/credentials.py` separates `CredentialProviderRef`, `CredentialReference`, `ProviderState`
  and `CredentialState`. `CredentialObservation` has no value field and refuses the incoherent
  case of an unavailable provider reporting a credential as present.
- `application/input_binding.py` resolves required-input coverage, source/binding compatibility and
  policy restriction. A `SecretInput` binds only to a `SecretProviderReference` and a `ConfigInput`
  never does, both enforced in `BoundInput.__post_init__` rather than by convention.
- `application/credential_lifecycle.py` plans inspect/store/verify/replace/delete with dependants
  surfaced before destructive mutation and no operation accepting, returning or reporting a
  previous value. `policy` is a required keyword argument, so a permissive policy cannot appear by
  omission.
- `io/credentials.py` holds `TransientSecret` — redacted in every string form, unpicklable,
  uncopyable, single-use — and `MacOsKeychainProvider` behind `CredentialProviderPort`. The default
  store path delegates to `security`'s own prompt so no value enters this process; the
  non-interactive path declares `PROCESS_TABLE` exposure through `store_exposure`.
- The legacy 128-byte prompt-ceiling measurement is preserved and improved: the stored length is
  counted in child processes so this process never receives the value, and a hex-encoded value is
  measured in bytes rather than in printed characters.
- `EffectivePolicy` gained `allowed_secret_bindings` (composing by intersection) and
  `forbidden_persisted_config` (composing by union).
- `domain/inputs.py` validates URL host allow-lists with its own strict reader (D-018), so the
  domain imports nothing whose package can reach the network and no lenient parse can disagree
  with a later consumer about which host was named.

## Remaining

- Nothing in this slice. The canonical path reaches a public flow in CP-10 and full remote-backed
  proof in CP-17.

## Known compromises

- The non-interactive store path passes the value on argv for the duration of one call, because
  `security` offers no stdin or file-descriptor form of `add-generic-password -w`. The exposure is
  declared rather than hidden, the interactive prompt remains the default, and B-015 tracks a
  lower-exposure path.
- Replacement is delete-then-add and therefore not atomic (D-017). A failure after the removal
  reports that the credential is now absent, which CP-11/12 repair as ordinary drift.
- URL validation refuses address literals; B-016 tracks naming one in an allow-list.

## Backlog discoveries

- B-015 — a non-interactive Keychain store path that does not use argv.
- B-016 — address literals in URL host allow-lists.

## Blockers

None.

## Legacy removal criteria

`setup_runtime.py` Keychain authority remains until CP-10 routes a real MCP installation through
the canonical provider port with equivalent truncation/kept-existing evidence.

## Handoff

- Current working state: CP-08 verified. Domain, application and io layers complete with the
  provider interpreter proven against `security` itself.
- Exact next action: open CP-09 (isolated Python runtime and dependency effects).
- Do not undo: `TransientSecret` living only in `io`; `SecretInput` having no value or default
  field; `policy` being a required keyword on `plan_credential_mutation`; the delete-then-add
  replacement and the test asserting `-U` is absent; the domain's own URL host reader.
- Tests last run/results: full quality green — all ten gates, 2,034 unit tests, 46 E2E tests,
  83.19% coverage. `tests/credential_lifecycle_integration_test.py` is 22 tests, four of which run
  the real lifecycle against a temporary macOS Keychain and are skipped off darwin.
- Failure evidence: `add-generic-password -U` was measured to block on an authorization dialog —
  a six-second probe and a twenty-second test both timed out. That measurement is why replacement
  removes and re-adds; see D-017.
