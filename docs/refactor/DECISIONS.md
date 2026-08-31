# AART Refactor Decision Log

This log records implementation decisions needed to execute the Product Specification. It cannot
override or weaken the Product Specification. If a decision would change product semantics, update
the Product Specification first instead of hiding the change here.

## D-001 — Refactor target
- **Decision:** only `M1F1/aart-cli` is the target repository.
- **Status:** accepted.
- **Consequence:** older AART/Agent Artifacts repositories are read-only reference sources.

## D-002 — Product Specification precedence
- **Decision:** `docs/product-specification/PRODUCT_SPECIFICATION.md` is the sole product source of truth.
- **Status:** accepted.
- **Consequence:** historical plans/specs/design docs cannot override it.

## D-003 — Unattended execution
- **Decision:** agents are expected to run unattended for long periods. Resolve non-product
  ambiguities with the smallest safe invariant-preserving choice, record it and continue.
- **Status:** accepted.

## D-004 — Discovery scope discipline
- **Decision:** useful work discovered outside the mandatory critical path goes to BACKLOG unless
  evidence shows it blocks a mandatory invariant/acceptance gate.
- **Status:** accepted.

## D-005 — Harden the existing migration seam before moving modules
- **Decision:** retain the existing `agent_artifacts/domain`, application-service and explicit port
  seams as the initial strangler boundary; enforce their dependency direction with tests before
  adding the five canonical algebras. Do not perform a broad package move in CP-02.
- **Status:** accepted.
- **Reason:** current boundary and vertical-path tests prove useful behavior, while the Product
  Specification makes semantic ownership—not a prescribed directory tree—the invariant.
- **Consequence:** legacy subsystem-local models may remain temporarily, but new canonical domain
  code cannot depend on them or on concrete infrastructure/interfaces.

## D-006 — Canonical algebras are additive until a flow migrates
- **Decision:** introduce the five canonical algebras as new frozen domain modules without
  re-exporting or deleting subsystem-local values in CP-03.
- **Status:** accepted.
- **Reason:** source compatibility is not the product contract, but removing legacy flow authority
  before a complete adapted vertical path would violate the strangler migration rule.
- **Consequence:** later slices must adapt real application flows and then remove duplicated legacy
  authority only after acceptance evidence.

## D-007 — Native authoring uses a finite, dependency-free YAML grammar
- **Decision:** accept strict JSON and the authoring manifest's required YAML block
  mapping/sequence/scalar subset in the public runtime; reject YAML tags, anchors, aliases, merge
  keys, flow collections, block scalars and ambiguous indentation.
- **Status:** accepted.
- **Reason:** Product Specification sections 55–70 require ergonomic `aart.yaml` and
  `aart.json`, while the zero-runtime-dependency invariant forbids adding a YAML library. The
  finite manifest schema does not need YAML's executable or graph features.
- **Consequence:** the accepted subset is deterministic and duplicate-key safe. Syntax outside it
  receives an `author-manifest-invalid` diagnostic rather than being guessed or silently lowered.

## D-008 — Authoring lowers through the existing canonical package validator
- **Decision:** the CP-04 compiler emits the existing canonical `artifact.json + payload/ +
  provenance.json` protocol package and the new canonical `domain.ArtifactPackage` envelope from
  the same selected inputs. Omitted compatibility dimensions remain empty/unconstrained rather
  than receiving invented profile or platform names.
- **Status:** accepted.
- **Reason:** this preserves the verified native package/install seam while separating semantic
  kind, concrete format and runtime protocol as required by INV-010. It also makes every compiled
  artifact pass the same package validator used by registry and installation flows.
- **Consequence:** CP-05 can create Candidate state from `CompiledAuthorArtifact` without a second
  compiler. Legacy native source loading remains public-flow authority until Source Sync migrates.
  Declarative launch is `AART Native`; an explicit external-script escape hatch is `AART
  Compatible` and remains visible for later policy evaluation.

## D-009 — Candidate identity binds selected author input, not repository revision churn
- **Decision:** derive Candidate ID from source alias, manifest path, target registry and the
  ArtifactInputDigest. Preserve the exact prior Candidate record when that identity is unchanged;
  source revision alone cannot reopen a rejected Candidate.
- **Status:** accepted.
- **Reason:** INV-015 and edge case 165.25 require unrelated monorepo changes to remain invisible
  and digest-aware rejection to survive repeated Source Scan.
- **Consequence:** a selected manifest/payload change creates a new Candidate linked to and
  superseding the prior record. Source Scan remains a read-only observation and cannot mutate the
  approved registry.

## D-010 — Approved payload identity and full workspace preconditions are separate digests
- **Decision:** a registry version's `registry_snapshot` hashes approved immutable artifact or
  reference content only. A promotion/lifecycle plan separately binds the full registry workspace
  before and after, including version, index, snapshot and audit records.
- **Status:** accepted.
- **Reason:** promotion audit must record the approved content snapshot after promotion, while
  lifecycle metadata must be able to change without changing immutable payload identity. Including
  an audit record's own after-digest in that digest would also create a self-reference.
- **Consequence:** vendored package integrity and lifecycle metadata integrity are both validated,
  but deprecation, revocation and canonical-branch publication do not rewrite payload identity.
  The public `registry promote` flow applies locally only; commit, push, merge and publication
  remain separate authorities.

## D-011 — Unqualified registry collisions require an explicit provenance choice
- **Decision:** if an unqualified artifact Selection can resolve from more than one configured
  registry, resolution fails with every valid qualified coordinate, including when the candidate
  payload digests are identical.
- **Status:** accepted.
- **Reason:** the Product Specification permits identical digests to be deduplicated visually but
  still requires installation provenance to record the selected registry/snapshot. Without an
  explicit registry choice, choosing that provenance would introduce hidden priority.
- **Consequence:** a presentation layer may collapse identical rows, but it must retain explicit
  registry choices for resolution. Different-content collisions receive the same fail-closed
  treatment and can never be shadowed.

## D-012 — Dependencies prefer their declaring registry
- **Decision:** an unqualified dependency first resolves within the selected parent artifact's
  registry. It may fall back to another registry only when no satisfying local version exists and
  effective policy explicitly permits cross-registry resolution.
- **Status:** accepted.
- **Reason:** this preserves registry review boundaries and existing same-registry semantics while
  implementing the Product Specification's explicit, policy-governed cross-registry capability.
- **Consequence:** explicit foreign-registry dependencies and fallback both fail closed by default.
  Allowed crossings retain the exact registry alias, snapshot and dependency ownership edge in the
  resolved result.

## D-013 — Absent observations are explicit Unknown facts, never silent satisfaction
- **Decision:** `EnvironmentFacts` carries at most one `EnvironmentFact` per `RequirementId`, and
  `inspect_requirements` fills every requested requirement the inspector did not observe with
  `FactState.UNKNOWN`. An inspector returning a fact outside the requested boundary is an error.
- **Status:** accepted.
- **Reason:** INV-004/INV-005 require deterministic planning over a closed fact set, and section 11
  makes `Satisfied | Unsatisfied | Unknown` the requirement state algebra. Treating a missing
  observation as satisfied would let a partial inspector silently widen what installs.
- **Consequence:** unsupported observations (credential, network, harness, Python package) remain
  Unknown until CP-08/09/10 add their specialized inspectors, and Unknown blocks planning exactly
  like Unsatisfied unless an allowed remediation is selected.

## D-014 — Remediation availability derives from declared capabilities, not from probing
- **Decision:** `_possible_remediations` derives options from typed `RemediationCapability` values
  supplied with the facts, then intersects them with the effective policy's allow-lists, forbidden
  effects and risk ceiling. `interactive_remediation=False` yields zero options and planning fails
  closed with `no-allowed-remediation`.
- **Status:** accepted.
- **Reason:** INV-035 defines availability as `Possible ∩ PlatformCapabilities ∩ EffectivePolicy`,
  INV-036 requires deterministic non-interactive failure, and INV-004 forbids planning from
  touching the host to discover what it could install.
- **Consequence:** capability discovery belongs to inspection adapters, so a platform that cannot
  install a runtime simply contributes no capability rather than offering a remediation that would
  fail at execution. `EffectivePolicy` gained `allowed_network_hosts` and `interactive_remediation`,
  both composing restrictively (intersection and logical AND).

## D-015 — Review identity covers the whole plan except the digest itself
- **Decision:** `InstallPlan.review_digest` is SHA-256 over the canonical JSON of the plan with the
  digest field omitted: resolved selection with ownership/provenance, platform, owned assessments,
  chosen remediations with owners and risk, deduplicated effects with all owners, risk summary and
  the effective-policy digest.
- **Status:** accepted.
- **Reason:** INV-005 requires one identity for the same artifact/target/policy/facts, INV-127
  requires deduplication to retain why an artifact is present, and INV-152 requires Fast and Verbose
  to project the same immutable plan. Including the digest in its own preimage is self-referential.
- **Consequence:** intent, requirement, owner and effect ordering cannot change review identity, so
  a review approval binds exactly one semantic plan. Environment facts enter the digest through the
  assessments they produced rather than as a second raw copy.

## D-016 — A secret value exists only in `io`, in a carrier that resists every way of keeping it
- **Decision:** `TransientSecret` lives in `agent_artifacts/io/credentials.py`. It renders as
  `[redacted]` from `__repr__`, `__str__` and `__format__`, raises on `pickle`, `copy` and
  `deepcopy`, and yields its value exactly once through `consume()`. No domain or application type
  can hold one: `SecretInput` has no value or default field, and the only source a `SecretInput`
  may bind to is a `SecretProviderReference`. `CredentialObservation` carries provider state,
  credential state and a length, never content.
- **Status:** accepted.
- **Reason:** INV-048/INV-051/INV-053 separate `CredentialReference` from a credential value, and
  the standing constraint is that secret values never appear in registry content, plans, receipts,
  provenance, logs, exceptions, JSON output, snapshots, tests or TUI history. Making the carrier
  unserializable and single-use turns that from a review rule into a type-level one: the paths that
  would leak a value are the paths that raise.
- **Consequence:** planning is total over references and never blocks on a provider. A caller that
  wants to log a plan, snapshot it or diff it cannot accidentally include a value, because no value
  reached the plan. passing `store()` no carrier at all — its default — delegates acquisition to the
  provider's own prompt, so the common path never materialises a `TransientSecret`.

## D-017 — Keychain replacement removes and re-adds, because in-place update blocks on a dialog
- **Decision:** `MacOsKeychainProvider.store(..., replace=True)` runs `delete-generic-password`
  followed by `add-generic-password`. It does not use `add-generic-password -U`.
- **Status:** accepted.
- **Reason:** measured, not assumed. Against `security` on macOS 15, `add-generic-password -U` on an
  existing item raises an authorization dialog and never returns without a human — a six-second
  probe and a twenty-second test both timed out, and the killed process left the item unreadable
  afterwards. `delete-generic-password` then `add-generic-password` completes with status 0 and no
  dialog, with default item access control and no `-A`. An operation that cannot complete
  unattended cannot be part of desired-state reconciliation.
- **Consequence:** replacement is not atomic. There is a window in which the credential is absent,
  so a write that fails after the removal says exactly that ("the previous value was already
  removed, so the credential is now absent and has to be stored again") and CP-11/12 repair it as
  an ordinary absent-credential drift. `-U`'s absence is asserted by test, not left to habit.

## D-018 — The domain parses host allow-lists itself rather than importing `urllib`
- **Decision:** `agent_artifacts/domain/inputs.py` validates a URL with `_url_host`, a strict
  reader that refuses anything it cannot read plainly: non-`http(s)` schemes, userinfo, backslashes,
  quotes, angle brackets, control characters and DEL, address literals, non-numeric ports, and
  empty, leading or trailing host labels. It returns the lowercase host or None.
- **Status:** accepted.
- **Reason:** two reasons, and either alone would be enough. `tests/domain_kernel_test.py` forbids
  the `urllib` root in `domain` because `urllib.request` reaches the network, and the ban is coarse
  on purpose — widening it to `urllib.parse` would weaken a gate to make a test pass. Separately,
  `urlsplit` is lenient exactly where a host allow-list is attacked: it accepts userinfo,
  backslashes and control characters, so the checker and whatever opens the URL later can disagree
  about which host was named. Refusing the unusual case is the conservative reading.
- **Consequence:** `ObtainFrom` uses the same reader, so guidance links are held to the same
  standard as validated configuration. The bypass cases are permanent test cases rather than
  comments, and IPv6 literals are refused until an allow-list can name one (backlog).

## D-019 — An installer is chosen by intersection; a preference selects inside it, never widens it
- **Decision:** `select_python_installer` computes `compatible(spec) ∩ available(platform) ∩
  permitted(policy)` and picks from that set. A `preferred` argument is honoured only when it is
  already in the set; otherwise the lowest name is taken, so the same three sets always give the
  same answer. An empty intersection is `no-compatible-python-installer` carrying all three sets by
  name. A lock narrows compatibility to the resolver that wrote it (`installers_for_lock`), and the
  same rule serves both `PythonDependencySpec` and `PythonPackageRequirement`.
- **Status:** accepted.
- **Reason:** INV-042 separates the specification from the backend and INV-043 lets an artifact
  declare one contract, so compatibility is a property of the artifact while availability is a
  property of the machine and permission is a property of policy. §111 makes a preferred installer
  a profile setting and says the final choice is filtered through capabilities and policy — which
  makes preference a selector inside the permitted set, not a fourth input that could widen it.
- **Consequence:** `EffectivePolicy` gained `allowed_python_installers`, composing by intersection,
  and preference deliberately stayed out of the policy algebra: a non-restrictive field in a
  restrictive algebra is how an overlay eventually widens something. A uv-locked project on a
  machine with only pip fails at planning time with the reason, instead of at execution time.

## D-020 — The interpreter enforces artifact ownership, not just the planner
- **Decision:** `LocalPythonRuntime` is constructed for one `ArtifactEnvironment` and refuses, before
  starting any process, an effect naming another artifact, a destination or descriptor outside that
  root, or a base interpreter inside the environment being built. `ArtifactEnvironment` derives
  `payload`, `environment` and `interpreter` from the root as `init=False` fields, so no caller can
  supply an interpreter path at all.
- **Status:** accepted.
- **Reason:** INV-044 gives one artifact one environment and INV-045 forbids implicit global
  mutation. Planning already refuses bad paths, but "the plan was correct" is the wrong thing for
  the component that runs `venv` and `pip` to assume — a plan can be replayed, edited, or built by
  a future code path that has not been written yet. Two checks in different layers cost almost
  nothing; one check in the wrong layer costs the invariant.
- **Consequence:** the refusal tests assert no process ran at all, so a regression shows up as an
  executed command rather than as a wrong outcome. `PYTHONNOUSERSITE=1` and a reduced environment
  are set for the same reason: an inherited `VIRTUAL_ENV` is how an install silently lands
  elsewhere.

## D-021 — A declared lock is honoured or refused, never quietly ignored
- **Decision:** `InstallPythonDependencies` carries `descriptor_kind` (`requirements`, `pyproject`,
  `locked-project`). The interpreter implements the first two for both pip and uv, and returns
  `python-runtime-unsupported` for a locked project rather than installing the loose versions.
- **Status:** accepted.
- **Reason:** INV-047 makes author intent and approved resolution distinct concepts, so a lock
  exists precisely to stop something else being installed. Installing unlocked versions from a
  locked contract would satisfy the type and violate the reason it exists — and it would do so
  silently, which is worse than not supporting it. The domain and the planner model locks fully;
  only the execution of one is deferred (B-018).
- **Consequence:** `PythonPackageRequirement` gained `lock_format`, so planning offers only backends
  that can read the artifact's contract. `descriptor_kind` also tells the interpreter whether to
  pass `-r <file>` or a project directory, which it could otherwise only guess from a filename.

## D-022 — A launcher carries the command that reads a secret, never the secret
- **Decision:** `generate_launcher` writes a shell command substitution that asks the credential
  provider for each secret when the artifact starts. The provider supplies that argv through a
  `CredentialResolutionPort`; `MacOsKeychainProvider.resolution_argv` builds it without running it.
- **Status:** accepted.
- **Reason:** §97 and §98 make the launcher an installation projection that may hold non-secret
  configured values and references to secret providers, and never secret values. A resolved value
  written into a file outlives every review that approved it, survives backups, and is readable by
  anything that can read the file — while resolving at launch gives the value the lifetime of the
  process that needs it.
- **Consequence:** a provider that no interpreter can resolve fails generation
  (`launcher-provider-unresolvable`) rather than producing a launcher with a hole in it, and a
  provider that will not answer at run time exits 77 with the reference named and no value shown.

## D-023 — The transport owns stdin, so a stdin-bound input is refused
- **Decision:** an input bound to stdin under the stdio transport fails generation with
  `launcher-transport-conflict`.
- **Status:** accepted.
- **Reason:** CP-08 deliberately separated `ProcessBinding` from `InputValueSource` so a secret
  could be delivered on stdin — the lowest-exposure binding there is. Under stdio, stdin is the
  protocol channel. Writing a value into it would corrupt the first JSON-RPC message and produce a
  failure that looks like a broken server rather than a mis-bound input.
- **Consequence:** `BindingExposure.PRIVATE` remains reachable for transports that do not claim
  stdin. The refusal names the transport, so the fix is visible.

## D-024 — A generated launcher does not write a secret to disk
- **Decision:** a `FileBinding` fails generation with `launcher-binding-unsupported`.
- **Status:** accepted.
- **Reason:** a file-bound secret needs a lifetime: a mode, a directory nothing else can read, and
  removal on every exit path including a killed process. Emitting a `trap` and hoping is not that
  design. Environment and argument bindings cover the real MCP servers in front of us, and both
  already declare their exposure honestly.
- **Consequence:** B-019 tracks the design. Until then the refusal is loud, which is the CP-09
  precedent (D-021): an unsupported contract is refused, never approximated.

## D-025 — A harness target is measured, not derived
- **Decision:** `MCP_TARGETS` holds observed settings paths and map keys; `mcp_target` raises
  `KeyError` for any harness nobody has measured, and `McpTarget` refuses a path that leaves its
  scope root.
- **Status:** accepted.
- **Reason:** the legacy `profiles/builtin.py` already carries this hard-won knowledge, including
  the note that a Tabnine build surfaced its MCP entry from `settings.json` while published docs
  name a different file. A registration written to a guessed path is worse than none: it reports
  success and the server never starts.
- **Consequence:** OpenCode and Vibe are not carried forward yet — their MCP keys are marked
  unverified in the legacy profile, so importing them would launder a guess into a canonical value.
  B-020 tracks measuring them.

## D-026 — A harness settings file is merged, never replaced
- **Decision:** `LocalHarnessRegistry` preserves every unrelated key and server, keeps the file's
  existing permissions, reports unparseable JSON (`harness-settings-unreadable`) and refuses a
  server map that is not a map (`harness-settings-unusable`) instead of overwriting either.
- **Status:** accepted.
- **Reason:** the file belongs to the harness and the person using it. An installer that has to
  destroy a configuration to record itself has not installed anything; it has traded one working
  setup for another.
- **Consequence:** registering is idempotent — an unchanged entry rewrites nothing and reports
  `changed=False`, which CP-11 can read directly as "no drift here".

## D-027 — A receipt fingerprints config values rather than copying them
- **Decision:** `InstallationReceipt.config` holds `ConfigFingerprint(input, sha256(id||value))`.
- **Status:** accepted.
- **Reason:** config values are not secret — the launcher holds them in the open — but
  `EffectivePolicy.forbidden_persisted_config` exists because some of them must not be persisted
  anyway. A digest detects drift exactly as well as a copy and leaves that policy nothing to
  violate. The input id is folded in so the same value under two names cannot share one digest.
- **Consequence:** repairing a drifted config value needs the desired value from the plan, not from
  the receipt. That is the correct direction: a receipt records what happened, not what should.

## D-028 — Verification with nothing measured is drift, not a pass
- **Decision:** `verify_installation` reports `launcher-changed` when the observed digest is
  `None`, and `observe_installation` converts every measurement failure into a fact rather than
  raising.
- **Status:** accepted.
- **Reason:** the failure mode being defended against is a verifier that returns "no findings"
  because it could not look. An unreadable launcher and a matching launcher must never produce the
  same answer.
- **Consequence:** findings are a closed enum in a fixed order, so CP-11 maps each to a remediation
  rather than parsing prose.

## D-029 — Desired and current are different types, and a component nobody looked at is drift
- **Decision:** `DesiredState` and `CurrentState` are separate frozen types over the same
  `ComponentId` vocabulary. A desired component with no observation is `DriftKind.UNOBSERVED`, not
  a match.
- **Status:** accepted.
- **Reason:** §158 makes the comparison the centre of the whole engine, and the two failure modes
  worth engineering against are comparing a state to itself and converging by declining to look.
  Separate types make the first impossible to write; a distinct unobserved kind makes the second
  visible instead of silent. It is the same rule as D-028, one level up.
- **Consequence:** an inspector that covers less produces more drift, not less, which is the
  correct direction for a safety property. The CP-10 end-to-end test asserts exactly this for a
  credential nobody inspected.

## D-030 — A desired component says how it is established and how it is corrected
- **Decision:** `DesiredComponent` carries `effects` and an optional `correction`, and
  `effects_for(kind)` returns `correction` for `DIVERGENT` and `UNVERIFIABLE` drift, `effects`
  otherwise. `correction` defaults to `effects`.
- **Status:** accepted.
- **Reason:** credentials proved one effect list insufficient. CP-08 refuses `StoreCredential` when
  a credential is already present and `ReplaceCredential` when it is absent, both deliberately. A
  component that could only name one of them would issue the wrong one half the time, and the
  refusal would surface as a repair failure rather than as the modelling gap it is. Every other
  component in front of us is an idempotent write where establishing and correcting are the same
  act, which is why `correction` defaults rather than being required.
- **Consequence:** `independently_repairable` considers both lists, so a component cannot look
  repairable through its establishing path and escalate through its correcting one.

## D-031 — Repair steps run in dependency order, not the canonical review order
- **Decision:** `RepairPlan.steps` are ordered by `Component` declaration order — payload, runtime
  environment, dependencies, configuration, credentials, launcher, harness — rather than by the
  canonical effect sort `MutationPlan` uses.
- **Status:** accepted.
- **Reason:** `MutationPlan` sorts effects canonically so a review digest is stable, which is right
  for a document and wrong for a script. An environment has to exist before dependencies go into
  it, and a launcher has to exist before a harness is told to run it. The component enum is already
  the dependency order the Product Specification draws in §158.1, so ordering by it needs no second
  source of truth.
- **Consequence:** `RepairPlan` keeps its own ordered steps and computes its own review digest over
  them, so determinism comes from the ordering being total rather than from re-sorting.

## D-032 — A repair the policy forbids fails the plan instead of being dropped
- **Decision:** `plan_repair` returns `reconcile-policy-violation` when any effect needed by a
  drifted component exceeds the risk ceiling or is forbidden.
- **Status:** accepted.
- **Reason:** the alternative — omitting the effect and planning the rest — produces a plan that
  looks complete, runs cleanly, and leaves the machine exactly as broken as it was. Failing names
  the component and the effect, so the answer is to change the policy or accept the drift, both of
  which are decisions somebody makes rather than an outcome nobody sees.
- **Consequence:** `plan_repair` takes `policy` as a required keyword, matching
  `plan_credential_mutation` (D-016's line of reasoning).

## D-033 — A current state is paired with the desired state it answers
- **Decision:** `current_state_from_observation` takes the `DesiredState` rather than a coordinate,
  and reports only components that state describes.
- **Status:** accepted.
- **Reason:** found by a failing test. A desired state built without a base interpreter omits the
  runtime environment, and an observation that reported the perfectly healthy environment anyway
  produced `UNEXPECTED` drift — the engine calling a working component stray because the caller had
  described less. "Unexpected" is only an honest claim against a complete description.
- **Consequence:** detecting genuinely stray registrations needs an inspector that reads a harness
  file whole rather than one that checks the entries a receipt names. B-023 tracks it.

## D-034 — Absence is a desired component target, not a separate uninstall engine
- **Decision:** `DesiredComponent.target` is either `MATCHED` or `ABSENT`. Uninstall builds absent
  payload/runtime/launcher/harness components and plans them through `plan_repair`; absent effects
  execute in reverse dependency order.
- **Status:** accepted.
- **Reason:** an empty desired state can identify unexpected components but cannot say how an owned
  component is safely removed. A second imperative uninstall would violate INV-173. An explicit
  absent target preserves the same comparison, policy, review, effect and re-inspection path while
  giving removal a typed, reviewable effect.
- **Consequence:** `RemoveOwnedPath` is still confined by `ArtifactEnvironment.owns`, and
  `UnconfigureHarness` names exactly one measured registration. Harness removal precedes launcher,
  runtime and root removal; installation keeps the forward dependency order from D-031.

## D-035 — Effect completion never substitutes for re-inspection
- **Decision:** `execute_repair` re-inspects after an empty plan, success, adapter refusal/exception,
  interruption and partial failure. Outcomes distinguish `CONVERGED`, `UNCONVERGED`, `FAILED`,
  `INTERRUPTED` and `UNVERIFIED` and retain residual component drift.
- **Status:** accepted.
- **Reason:** §158.8 makes observed convergence the success condition. An interpreter can report
  success without changing the machine, and an interrupted process leaves a real state that is
  more important than the instruction number it reached.
- **Consequence:** a future resume always starts by inspecting and planning again; it never blindly
  continues from the first unattempted step. The outcome projection is the secret-free lifecycle
  receipt payload for Activity/receipt UI work.

## D-036 — Review preconditions are compared inside a per-scope mutation lease
- **Decision:** `execute_lifecycle` acquires a lease derived from the relevant scope identity,
  re-inspects under the lease, reconstructs the plan and requires its review digest to match before
  any effect executes. Read-only inspection remains unlocked.
- **Status:** accepted.
- **Reason:** acquiring a lock only around writes leaves a gap in which another process can change
  the state after Review. A global lock would serialize unrelated projects. Hashing the scope key
  into the managed path makes the boundary explicit without trusting a project path as a filename.
- **Consequence:** same-scope contention returns an operation-lock diagnostic and mutates nothing;
  different scopes proceed independently. Release runs on success, failure, stale review and
  interruption.

## D-037 — Update restoration is reconciliation and only follows reversible applied effects
- **Decision:** after a failed update, restoration is planned against a fresh observation paired
  with the previous desired state. It runs only when at least one effect was applied and every
  applied effect declares `reversible=True`.
- **Status:** accepted.
- **Reason:** replaying a receipt is not proof that the earlier state can be restored, and claiming
  transaction atomicity over environment creation or package installation would violate INV-225.
  The previous desired state plus a new observation is the same honest input used for every other
  lifecycle intent.
- **Consequence:** verified restoration reports `RESTORED`; failed restoration is distinct;
  non-reversible work reports `PARTIALLY_APPLIED` with residual drift and never calls itself rolled
  back.

## D-038 — Ownership and credential cleanup are decisions before uninstall planning
- **Decision:** uninstall subtracts the released Collection/direct/dependency ownership reasons
  first. Any remaining reason retains the artifact with a no-mutation plan. Credential components
  are excluded from the removal desired state unless deletion is explicitly requested.
- **Status:** accepted.
- **Reason:** a component planner cannot infer whether another Collection or direct selection still
  owns the artifact, and a final known dependant disappearing is not authority to erase a reusable
  credential. Both choices must be visible before effects exist.
- **Consequence:** Collection removal explains retained ownership and removes only final-owner
  artifacts. The real uninstall E2E proves the runtime/root and harness entry disappear while the
  provider-held credential remains.

## D-039 — Activity groups by the day a record names, and today is supplied
- **Decision:** `ActivityRecord` carries its own ISO-8601 timestamp with an explicit UTC offset,
  and `project_activity` takes `today` as a required keyword rather than reading a clock.
- **Status:** accepted.
- **Reason:** the application layer has no clock by construction, and a receipt that dated itself
  when somebody opened the timeline would be a record of the reading rather than of the action. A
  naive timestamp also cannot be ordered against one written on another machine.
- **Consequence:** "Today"/"Yesterday" mean the reader's today; every other day is named by its
  date. A record without a time or an offset is refused at construction, not silently coerced.

## D-040 — A receipt records what happened; it does not promise an undo
- **Decision:** `UndoAvailability` offers undo only when at least one effect was applied, every
  applied effect declares `reversible=True`, and no applied effect is a credential mutation.
- **Status:** accepted.
- **Reason:** §161.9 states a receipt does not imply guaranteed undo, and INV-161 forbids retaining
  an old secret value. Manufacturing credential undo would require keeping exactly the value the
  architecture refuses to hold, so the honest answer is the refusal and its reason.
- **Consequence:** the receipt screen says plainly why undo is unavailable — nothing took effect,
  nothing retained can reverse it, or no previous value exists — instead of offering an action that
  cannot complete.

## D-041 — Key meaning is decided in the reducer, not in the terminal
- **Decision:** `key_event` translates a key *name* to an event inside the application layer, with
  the current mode in hand; `tui_consumer.key_name` maps one `getch` code to a name and the curses
  adapter does nothing else.
- **Status:** accepted.
- **Reason:** what a key means depends on mode: while the search filter is open every printable key
  is a letter of the query, and at the quit prompt only the answer keys act. A shell that decided
  that for itself would eventually let `q` quit instead of typing a q — the exact bug the legacy
  wizard warns about in its own comment.
- **Consequence:** the whole keyboard is headlessly testable against canonical view models, and no
  ncurses constant reaches `agent_artifacts/application/`.

## D-042 — Esc goes back in the persistent consumer application
- **Decision:** in the canonical consumer application `Esc` is Back and `q` quits; the legacy
  wizard's Esc-also-quits stays where it is.
- **Status:** accepted.
- **Reason:** §161.1 lists Esc among the global keys of a persistent application with left
  navigation, where Back is what Esc means. Esc-as-quit is a wizard behaviour: a wizard has no
  position to return to.
- **Consequence:** Esc at the Dashboard does nothing rather than exiting. Quitting with a selection
  still asks first.

## D-043 — A detail screen is about a focused row, not about the cursor
- **Decision:** navigation records the row it was opened from as `ConsumerUiState.focus`, keeping
  the previous focus when the current screen has no rows of its own; Back clears it.
- **Status:** accepted.
- **Reason:** loading a detail screen replaces the row set with that screen's own — usually empty —
  so the cursor cannot say what the screen is about. Discovered by the headless shell test, which
  drew "Nothing is installed here" for an artifact that was plainly installed.
- **Consequence:** 25 → 26 → 27 stays about one action, and 12 → 13 about one artifact. Back
  returns to the list with the cursor still on the row that was opened.

## D-044 — A record stores identity structurally, not as its printed form
- **Decision:** persisted receipts carry credential references and artifact coordinates as objects
  with named parts; `str(reference)` is kept alongside them as a label, never as the storage.
- **Status:** accepted.
- **Reason:** `CredentialReference` prints as `input@provider:service/account` and a coordinate as
  `source/kind/name@version`, but nothing forbids `@`, `:` or `/` inside a service, an account or a
  name. A parser over the printed form would be right until the first punctuated provider, and then
  silently wrong about which credential an installation holds.
- **Consequence:** `installation_receipt_to_data` emits a mapping per credential; the label stays
  under `"reference"` so existing readers and the MCP stdio E2E assertion keep working.

## D-045 — A receipt that cannot be read is reported, never skipped
- **Decision:** `LocalReceiptStore` returns `Err` for an unreadable record rather than omitting it
  from `installations()` or `actions()`; a limit bounds what is opened, not what is reported.
- **Status:** accepted.
- **Reason:** a skipped receipt presents itself to every later reader as an installation that never
  happened. Reconciliation would then plan a fresh install over an existing one, which is the exact
  failure a receipt exists to prevent. Absence and corruption are different answers and get
  different codes (`receipt-absent`, `receipt-unreadable`).
- **Consequence:** one corrupt file makes the whole listing an error until a person resolves it.
  That is deliberate: a partial truth about what is installed is worse than a refusal.

## D-046 — An action that took effect is recorded even when it did not finish
- **Decision:** `record_lifecycle_outcome` records the installation whenever any step applied or the
  run converged; it leaves the store untouched when nothing applied, forgets the record only when an
  uninstall converged, and leaves the existing record standing when an update was rolled back.
- **Status:** accepted.
- **Reason:** the leftovers of a half-finished install are on the machine whether or not a record
  names them. A record makes them drift a repair can find; no record makes them files nothing owns.
  The converse holds for a rollback: after a restored update the previous installation is the one
  that is still true, so writing the new receipt would describe a machine that does not exist.
- **Consequence:** Installed can show an artifact that is not healthy, which is the point — health
  is inspected, not inferred from the fact that a record exists. The timeline always gets the
  action, including failures, and gets it before the installation record, so a store that then
  refuses still leaves the attempt visible.

## D-047 — A Collection opens ticked, and customizing it stays about the Collection
- **Decision:** entering screen 04 seeds the selection with every member (a new `SET_SELECTION`
  event the screen source supplies on the way in), and the 04 → 04a step keeps `focus` instead of
  taking the row under the cursor (`keeps_focus`).
- **Status:** accepted.
- **Reason:** opening a Collection is asking for the Collection, so the exact membership is the
  honest starting point and Space then removes from it. And a Collection preview lists *members*,
  so D-043's "a detail is about the row under the cursor" would make Customize about one member
  rather than about the Collection it is customizing.
- **Consequence:** `project_collection` stays the only place a selection identity is decided, and an
  exact re-selection collapses back to the exact Collection because the ticks are ordered by
  membership before projection. Quitting with a Collection open now asks first, because a ticked
  Collection is a selection.

## D-048 — A credential's word is decided by the renderer, its state by the projection
- **Decision:** `CredentialRecordView.health` stays the canonical `CredentialState` value, and
  `tui_consumer` maps it to the accepted words: `present` with dependants reads `Ready`, `present`
  with none reads `Unused`, and `absent`/`invalid` read `Attention`.
- **Status:** accepted.
- **Reason:** the accepted screen (161.8) is written in outcomes, not provider states, and the two
  do not map one to one — material nothing uses is not "Ready" in any useful sense, and material a
  provider cannot honour is not merely "absent". Deciding this in the projection would put a
  presentation word where a machine consumer reads state, and deciding it in the domain would put
  it where no consumer is in view at all.
- **Consequence:** `--json` keeps the provider vocabulary while the screen keeps the accepted one,
  and a new provider state gets a word here without changing anything a machine reads.

## D-049 — Screen 09 compresses the review; it does not go quieter
- **Decision:** screen 09 draws `render_ready` (outcomes, remediations, risks, review identity) in
  Fast and the unchanged `_verbose_plan` under `Show details`. `render_install_plan` stays the whole
  plan in one piece: it is what a non-interactive `install` prints, not a screen.
- **Status:** accepted.
- **Reason:** 161.5 asks screen 09 for a concise outcome summary and defines `Show details` as "the
  same InstallPlan in Verbose mode", so the interactive flow spreads one plan across screens 05–09
  while a command that cannot ask has to print it at once. Both are disclosures of one reviewed
  plan, never two reviews.
- **Consequence:** the Fast/Verbose invariant is now asserted on the screen a person actually
  confirms from — a property test drives generated plans through `render_ready` and requires every
  risk the plan carries and every remediation it decided to be named there.

## D-050 — Why an artifact is installed is recorded beside what it left behind
- **Decision:** `InstalledRecord` is a value of coordinate, receipt and `ownership`, persisted
  together by `LocalReceiptStore`. Ownership stays outside `InstallationReceipt`. Only intents that
  speak to ownership set it (`establishes_ownership`: install, update, downgrade, uninstall); every
  other action records `ownership=None`, which the store reads as "carry forward what is there".
  An empty tuple is an opinion — nobody owns this — and replaces what was recorded.
- **Status:** accepted.
- **Reason:** ownership-aware uninstall is an accepted invariant (161.6), and the process that
  removes an artifact is rarely the one that installed it. Without persistence a later uninstall
  either deletes an artifact another Collection still needs or retains everything forever. It does
  not belong *inside* the receipt because the two answer different questions: a receipt records the
  effects that ran, while ownership comes from the Selection that asked and changes when another
  Collection starts or stops needing the artifact, with no effect running at all.
- **Consequence:** a repair cannot silently release a Collection's claim by carrying the nothing it
  happens to know. An uninstall that retained the artifact now narrows the record's ownership
  instead of forgetting it — a defect the test found: the recorder forgot the installation on any
  converged uninstall, including one that deliberately removed nothing.

## D-051 — The machine is assembled once, never inside a draw
- **Decision:** `application/consumer_session.py` turns what was read of a machine into one
  `ConsumerMachine`; `tui_consumer.screens_from` turns that plus the current offers and flow into
  `ConsumerScreens`. Inspection is an argument — each installed record arrives paired with the
  desired state it describes and the current state something else measured.
- **Status:** accepted.
- **Reason:** drawing the same screen twice must not be able to give two answers, and a screen that
  re-derived health while somebody scrolled would do exactly that. Splitting it in two also keeps
  the boundary honest: the decisions no projection can make (which Collection an artifact belongs
  to, which installations depend on a credential, what the Dashboard counts) stay in `application/`,
  while the offers — which wrap `tui_marketplace` rows — stay in the interface layer where they are
  already defined.
- **Consequence:** Collection membership comes from recorded ownership rather than from a
  Collection's current manifest, so a Collection that has since published a new member has not
  thereby installed it. Credential dependants are matched by reference, not by provider account:
  two artifacts sharing an account but binding different inputs are not dependants of each other's
  credential. CP-14 can assemble the maintainer catalog the same way.

## D-052 — One lowering stands behind the plan somebody reviews and the effects that run
- **Decision:** `application/installation_proposal.py` introduces `PlannedInstallation` — one
  artifact's whole intended installation — and lowers it two ways. `intended_receipt` writes the
  receipt the install means to leave; `desired_state_for` feeds that receipt to the existing
  `desired_state_from_receipt`, so the state an install converges to and the state a later repair
  keeps are built by one function. `propose_installation` then reconciles that desired state
  against a real inspection and hands the effects the reconciler chose to `prepare_install_plan`,
  so the review names exactly what will run. `InstallationProposal.__post_init__` refuses to
  construct when an effect that would run is not in the reviewed plan.
- **Status:** accepted.
- **Reason:** an install is described twice — as the review a person confirms (161.5 screens 05–09)
  and as the desired state CP-11 drives. Written separately the two are free to disagree, and
  somebody then confirms one thing while another runs. Deriving the review from the reconciliation
  rather than from an assumed fresh install is what makes this exact rather than approximate: a
  credential that is already present and wrong is *replaced*, not stored, and the review says so.
- **Consequence:** "what you confirmed is what runs" is a property of the type, not a discipline.
  `observed` is required for every planned artifact rather than defaulted, because "nobody looked"
  and "it is not there" call for different installs and a default would quietly pick one. An
  already-converged proposal is representable: an empty mutation plan and no steps.

## D-053 — The payload component rests on the payload, not on the root beside it
- **Decision:** `InstallationObservation.root_present` becomes `payload_present`, measured as the
  payload directory rather than the artifact root; `desired_state_from_receipt` gains an optional
  `payload_source` that adds the `payload` component as a `CopyTree`.
- **Status:** accepted.
- **Reason:** a fresh install has to establish the payload, and the root also holds the runtime
  environment — so a payload somebody deleted left the root standing and read back as present. The
  source of a payload is plan knowledge like the base interpreter and the dependency descriptor: a
  receipt does not hold it, and a reconciler that guessed would overwrite the payload from
  somewhere nobody chose.
- **Consequence:** repair keeps its existing behaviour until a caller supplies `payload_source`;
  when one does, a missing payload becomes drift the reconciler can put right instead of a
  component that quietly disappears from the comparison.

## D-054 — The manifest declares what an installation needs; the domain keeps the rules
- **Decision:** `protocol/authoring.py` parses the §91 `inputs` array and the §107/§108
  `python.dependencies` descriptor into `RuntimeInput` and `PythonDependencySpec`, and
  `AuthorManifest` carries both. Every one of these values is constructed through `_built`, which
  turns the domain constructor's `ValueError` into a manifest diagnostic. The parser decides only
  which fields a kind may carry; what makes a value acceptable stays where it already was.
- **Status:** accepted.
- **Reason:** the rules are already written once, in `domain/inputs.py` — a secret carries no value,
  guidance carries no plausible example credential (INV-168), an environment variable is a name and
  not an assignment. Restating them in the parser would give a manifest two sets of rules free to
  disagree, and the parser's copy is the one nobody would think to update.
- **Consequence:** a secret input's field set omits `default` and `value` entirely rather than
  validating them as empty, so there is no field a real credential could be written into and then
  be carried in the input digest. The declarations reach that digest exactly as the author wrote
  them: what an artifact asks for is part of what the artifact is, and re-serialising domain values
  would let a parser change round-trip into a different artifact identity. Declaration order is
  preserved for the same reason it exists — it is the order somebody is asked for the values.

## D-055 — A descriptor an artifact points at has to travel with it
- **Decision:** `_compile_one` refuses a manifest whose entrypoint, dependency descriptor or lock
  file is not among the selected payload files, with `AUTHOR_PAYLOAD_INVALID` naming the file.
  `_DEPENDENCY_KINDS` admits `requirements`, `pyproject` and `uv`; anything else is refused by name.
- **Status:** accepted.
- **Reason:** §108 requires the descriptor and its lock to ship inside the canonical payload. An
  artifact whose dependency list lives only in the author's repository installs today and fails to
  install tomorrow, and the failure arrives at the consumer rather than at the author. The same
  argument covers the entrypoint: a launcher naming a file the payload does not carry starts
  nothing. Refusing at compile time puts the error where it can still be fixed.
- **Consequence:** a resolver with no installer backend behind it — poetry today — is refused rather
  than approximated by installing the loose project the lock exists to prevent (B-027). The check
  runs after the input digest is computed and before canonical lowering, so a refused manifest never
  produces a package.

## D-056 — One value stands between what an artifact declares and what a machine offers
- **Decision:** `domain/install_description.py` holds `InstallDescription` — the launch contract,
  the runtime and its constraint, the declared runtime inputs and the dependency descriptor, and
  nothing about any machine. `protocol/authoring.py` produces one from a parsed manifest
  (`describe_installation`) and reads one back out of a compiled package's `aart.authoring`
  extension (`read_install_description`), using the same sub-parsers in both directions.
  `application/artifact_installation.py` joins that description to a root, an interpreter, input
  value sources, harness targets and a policy, and produces the `PlannedInstallation` that D-052
  lowers.
- **Status:** accepted.
- **Reason:** the package half knows nothing about any machine and the machine half knows nothing
  about any artifact; neither can produce an installation alone, and until now nothing joined them
  outside tests. Reading the description back through the writer's own parsers is what makes the
  round trip safe: a second grammar for reading what the first one wrote works right up until an
  author uses a field the reader forgot.
- **Consequence:** the machine installing an artifact reads what it needs from `artifact.json` on
  disk, never from the author's repository, which it has not seen. A description with no launch
  contract is refused by name rather than installed as something that starts nothing. Keys the
  reader does not need are ignored rather than refused, so a later manifest field is not a breaking
  change for installations that predate it. Which backend installs the dependencies stays
  `select_python_installer`'s intersection and what a launcher can deliver stays
  `generate_launcher`'s refusal — both are asked, never restated.

## D-057 — Dependencies are reported through the environment that holds them
- **Decision:** `current_state_from_observation` reports the `runtime-dependencies` component as
  matched when the artifact's interpreter is present and absent when it is not, with a detail
  saying the packages themselves were not re-resolved.
- **Status:** accepted, with the limitation recorded as B-029.
- **Reason:** the first install driven from a real dependency declaration ended
  `COMPLETED_WITH_ATTENTION` forever: the desired state named a dependency component and nothing
  ever observed one, so every healthy artifact with dependencies reported unobserved drift. A
  component nothing measures is worse than a partial measurement here, because "needs attention"
  on a working installation is the alarm people learn to ignore.
- **Consequence:** losing the environment is detected and repaired, since the repair rebuilds the
  environment and reinstalls into it. Drift *inside* the environment — a package removed or
  upgraded by hand — is not detected, and the detail says so rather than letting a partial check
  read as a full one. Verifying installed distributions against the descriptor is B-029.

## D-058 — A package that does not say how it is installed is refused, not read as saying nothing
- **Decision:** `read_package_description` reads a whole canonical tree — finds `artifact.json`,
  parses it, and requires the `aart.authoring` extension. A package without that extension is
  refused by name. `PACKAGE_PAYLOAD_DIRECTORY`, `PACKAGE_MANIFEST_FILENAME` and
  `package_payload_root` give the compiler and the reader one spelling of the layout.
- **Status:** accepted.
- **Reason:** "this artifact declares no runtime and no inputs" and "whatever wrote this package
  never recorded what it needs" are different facts, and only the first is safe to install. Reading
  the second as the first would produce an artifact that starts nothing and asks for nothing, with
  no error anywhere — the failure would arrive when somebody tried to use it.
- **Consequence:** the install path now begins at the content-addressed object store: a package is
  published, read back with its digest verified, described, planned and installed, and the payload
  an install copies from is the store's verified copy rather than any other tree with the same
  files.

## D-059 — A flow is held beside the machine, and an outcome is only reported under its own review
- **Decision:** `ConsumerFlow` holds an `InstallationProposal` together with the `ConsumerPlanView`
  projected from it, and refuses to exist when the review it would draw names a different plan than
  the proposal it carries. `begin_installation` builds one; `record_installation` attaches a
  `LifecycleOutcomeView` and refuses an outcome whose plan is not one this flow proposed.
  `PlannedInstallation` gained `declared`, the inputs the artifact asked for, so the review can show
  what somebody will be asked for rather than only what has already been answered.
- **Status:** accepted.
- **Reason:** screens 05–11 are projections of an action, not of a machine, and nothing built one:
  every piece existed and a running application still drew "Nothing has been planned yet". Building
  the plan view inside a draw was the alternative and is the one D-051 already rejects — a review
  re-derived while somebody scrolled is not the review they confirmed.
- **Consequence:** the guarantee `InstallationProposal` makes is now visible: what a person reads on
  05–09 is projected from the proposal whose effects run, and screens 10–11 can only report an
  outcome belonging to that proposal's own lifecycle plan. An input two artifacts both declare is
  asked for once; they agree because a selection's values are bound from one set of sources, so the
  first declaration is the declaration rather than a choice between rivals.

## D-060 — A later process reads environment provenance; it does not guess it
- **Decision:** `InstallationReceipt` records the optional absolute `base_interpreter` used to
  create the artifact environment. `intended_receipt` fills it from the reviewed
  `PlannedInstallation`; old receipt documents without the field still parse with `None`.
- **Status:** accepted.
- **Reason:** the durable consumer reader must construct the desired runtime state before it can
  compare an installed artifact with the machine. The environment interpreter is an effect, while
  the interpreter it was built from is the provenance needed to reproduce that effect. Guessing
  the current process's interpreter would make a later repair silently change what was reviewed;
  omitting the component would make a missing environment invisible to Installed health.
- **Consequence:** a receipt predating this evidence can still be displayed and its launcher and
  harness inspected, but the reader does not claim to know or repair its runtime origin. New
  canonical installs detect a missing environment after a process restart without consulting the
  plan that happened to be in memory when they were installed.

## D-061 — The full-screen entry opens one durable machine snapshot
- **Decision:** the supported-curses branch of `tui.py::run` composes
  `CanonicalScreenSource(screens_from(read_consumer_machine(...)))` and calls `run_consumer` before
  initializing any legacy source/wizard state. `read_consumer_machine` reads every installation and
  action once, inspects each installation once, and assembles one immutable `ConsumerMachine`.
  A credential reference for which no matching provider was supplied is observed as `UNKNOWN`, not
  absent; that unverifiable component gives the installation `Attention`, never a false `Ready`.
- **Status:** superseded by D-062 after public-entry characterization.
- **Reason:** D-051's "assemble once" rule is only useful if the public composition root uses it.
  Reading or inspecting inside a draw could change the answer while somebody scrolls. Treating an
  unavailable provider as absence would invent a missing credential, while treating it as matched
  would certify material nobody inspected. The canonical component algebra already has `UNKNOWN`
  for exactly this evidence boundary.
- **Consequence:** bare full-screen use reaches the CP-13 application and its accepted screens.
  A curses capability failure before interaction still falls back to the characterized
  line-oriented legacy path; an unreadable durable record fails closed instead of reopening a
  wizard over a machine that appears empty. B-025 is closed, while public flag commands remain the
  next migration boundary.

## D-062 — Rendering every screen is not authority to replace a working entry point
- **Decision:** keep `run_consumer` and `_canonical_consumer_source` available at the composition
  boundary, but do not route bare `aart` to them until the consumer reducer can start and apply the
  accepted lifecycle actions and its source includes the configured Marketplace as well as durable
  installed state. The characterized legacy curses/text wizard remains the public entry meanwhile.
- **Status:** accepted; reverses only D-061's routing consequence, not its durable-reader design.
- **Reason:** public-entry characterization after D-061 found two facts the renderer tests did not
  cover. `ConsumerUiCommandKind` contains only load, quit confirmation and exit, so Enter can reach
  Ready but cannot install, update, repair or uninstall. The composed source also supplied no
  Marketplace offers, and public installs still write the existing project manifest rather than
  `LocalReceiptStore`; a real user would therefore open an empty, read-only application and their
  valid existing installations would disappear from view. That violates the strangler rule and
  INV-149 even though all 29 screen renderers exist.
- **Consequence:** B-025 is reopened with concrete promotion evidence: live action commands, a
  configured Marketplace in the source, and a migration/adapter for existing project/user install
  records. The canonical durable reader, receipt provenance and all headless screen evidence remain
  useful and verified; only the premature public dispatch is removed.

## D-063 — The reducer requests actions; one injected handler replaces the immutable snapshot
- **Decision:** consumer interaction names four typed intents (`install`, `update`,
  `verify-repair`, `uninstall`) and emits only `PREPARE_ACTION` or `EXECUTE_ACTION`. Preparation
  carries Selection/focus and returns the semantic, Selection and review identities that were
  actually prepared. Execution carries that exact review identity. The persistent shell crosses
  one injected handler boundary, draws the running screen before synchronous execution, and accepts
  only a matching prepared/recorded response with a replacement immutable screen source. With no
  handler it fails closed.
- **Status:** accepted.
- **Reason:** navigation is not lifecycle authority. Putting planning or effects in `key_event`, the
  reducer or a renderer would duplicate the application services and let Fast/Verbose or a redraw
  change semantics. Letting a handler mutate a source in place would break D-051's one-snapshot
  rule; accepting an untyped callback response could display one action's outcome under another
  action's review.
- **Consequence:** Marketplace `i`, contextual update/repair/uninstall shortcuts and Ready/review
  confirmation are headlessly testable through the real shell without any filesystem or terminal
  dependency in the reducer. The production handler is still deliberately absent: multi-artifact
  execution must first gain one aggregate transaction outcome/receipt (B-030), because calling the
  singular CP-12 recorder once per artifact would violate INV-130 and INV-138.

## D-064 — The transaction is the unit recorded, because it is the unit reviewed
- **Decision:** `execute_installation` runs a whole `InstallationProposal` under one lease, and
  `project_installation_receipt`/`record_installation_transaction` turn it into **one** Activity
  receipt naming the Selection with every member accounted for beneath it, plus one installed
  record per member that actually applied. `ReceiptDetailView` gained `selection` and `artifacts`;
  both are omitted from the stored document when absent, so a receipt written before transactions
  existed still reads.
- **Status:** accepted.
- **Reason:** looping `execute_lifecycle`/`record_lifecycle_outcome` per artifact would produce N
  actions for one confirmation, violating INV-130/INV-138 and leaving no record of the thing that
  was actually reviewed. It would also make a Selection that half-applied indistinguishable from
  two unrelated installs on the timeline.
- **Consequence:** a member that applied is recorded even when a later member failed — its
  leftovers are on the machine either way, and a record is what makes them drift a repair can find
  rather than files nothing knows about. A member that applied and whose receipt was not supplied
  is refused rather than silently forgotten. Undo for a transaction is the weakest of its members,
  never the average: if any member did not run, or mutated a credential, or applied something
  irreversible, the transaction cannot be undone and the reason given is that member's own.

## D-065 — Screens 10 and 11 draw the transaction; 17 and 19 stay on one lifecycle action
- **Decision:** `ConsumerScreens` gained `transaction: ReceiptDetailView | None`, and
  `render_transaction_progress`/`render_transaction_success` draw a whole Selection: the summary,
  every member with its status, detail, diagnostics and steps, residual drift, and an `[ Undo ]`
  offered only when the transaction can actually be reversed. `INSTALLING` and `SUCCESS` prefer the
  transaction when one is present and fall back to the singular outcome; `UPDATING` and
  `UNINSTALLING` keep the lifecycle renderers, because an update or an uninstall is one artifact's
  action.
- **Status:** accepted.
- **Reason:** an install is confirmed once and may establish several artifacts (D-064), so drawing
  it through `render_success` would have to pick one member to name and drop the rest — including a
  member that never ran, which is exactly the member somebody needs to see. Offering an undo the
  transaction cannot perform would be worse than offering none.
- **Consequence:** a `not-attempted` member is drawn like every other status rather than filtered
  out for having no steps, and the undo refusal on screen 11 carries the member's own reason. The
  authored-manifest E2E now installs through `execute_installation` and draws 10/11 from the
  receipt that real run produced, so the transaction path has end-to-end evidence rather than
  view-level evidence only.

## D-066 — B-030's reload needed evidence, not code
- **Decision:** the durable half of B-030 is closed by acceptance evidence rather than by new
  production code. `tests/artifact_installation_e2e_test.py` now records a real install as a
  transaction into `LocalReceiptStore` and re-reads the machine with `read_consumer_machine` from
  the state root and harness root that install actually wrote — a reader that has never seen the
  proposal — asserting the artifact appears in Installed, the Collection that asked for it is still
  the reason it is there, and the transaction is one Activity entry whose receipt names the
  Selection and its members.
- **Status:** accepted.
- **Reason:** the transaction receipt gained `selection` and `artifacts` (D-064), and those fields
  cross the stored document, `activity_from_receipts` and the installed-record reader. A round-trip
  unit test proves the document; only a reload from disk proves that the next machine a person
  opens shows what the last one recorded.
- **Consequence:** an unavailable credential provider stays unavailable across the reload: the file
  provider that resolves this artifact's token at launch is not an inspector, so the reread machine
  reports the reference as `unknown` with the installation named as its dependant rather than
  inventing an answer, and no drawn screen or serialized machine carries the token. What remains
  before the default TTY route is Marketplace composition and legacy installed-state visibility,
  not durability.

## D-067 — The developer loop narrows tests; the release gate still runs all of them
- **Decision:** `scripts/affected.py` maps a change to the test modules that could have been
  affected, and `scripts/quality.py --changed` (`make check`) runs every cheap gate in full plus
  only those tests. `make quality` is unchanged in meaning: every gate, every test. Separately,
  `quality.py` now skips a gate whose tests are *provably* a subset of another selected gate's --
  `integration` discovers `*e2e_test.py`, which `unit`'s `*_test.py` already matches -- after
  checking the containment at run time rather than assuming it, and it prints the skip and its
  reason rather than dropping the gate silently.
- **Status:** accepted.
- **Reason:** the full suite took ~485s, and ~275s of that was the same tests running two and three
  times: `integration` re-ran 107 tests `unit` had just run, and `coverage` re-ran all 2,506 again.
  Every non-test gate together takes 5.7 seconds, so gate-level selection was never the lever --
  test execution was.
- **Consequence:** `make quality` is ~372s (the redundant `integration` run removed, no assertion
  lost) and `make check` is ~112s for a typical source change. The narrowing refuses far more
  readily than it narrows: any changed path that is not a `.py` file under `agent_artifacts/` or
  `tests/` -- a build file, a script, a fixture, a doc -- makes it decline and run everything, and
  so does a module it cannot parse, find, or place in the graph. A test that crosses a subprocess
  boundary is outside the import graph, so it runs whenever any source module changes; the
  narrower rule that would have released 30 such modules was rejected because it would have
  released `registry_cli_integration_test` and others that do drive the package, and a wrongly
  skipped test reports green without running. `coverage` is never narrowed: a percentage measured
  over part of a suite is not this repository's percentage.

## D-068 — The canonical shell composes real offers; Collections do not cross the seam yet
- **Decision:** `read_consumer_offers` reads the configured Marketplace once at composition and
  `_canonical_consumer_source` hands the result to `screens_from`, so screens 02–04a draw what the
  configured sources actually published. The catalog is still assembled by the characterized
  `load_read_only_marketplace`; that is the strangler seam, and where the offers come from can move
  to `aggregate_approved_marketplace` without the shell noticing. The compatibility target is built
  from the measured `MCP_TARGETS`, never from a list written beside them.
- **Status:** accepted.
- **Reason:** the composed application read the machine and passed `screens_from` no offers at all,
  so a person opening the canonical shell saw an empty Marketplace with their configured sources on
  disk beside it. Reading offers is an effect, so it belongs at composition rather than inside a
  draw (D-051).
- **Consequence:** Collections are declined rather than offered. A protocol-v1 Collection is
  identified by source and name alone; a canonical `Collection` is versioned and bound to the
  registry snapshot it was read from, so producing one here would mean inventing the version that
  tells two of them apart. Each is declined by name in `ConsumerOffers.declined`, because an offer
  missing from the Marketplace with no explanation reads as a source that published nothing. An
  unreadable configuration refuses startup rather than drawing an empty Marketplace: an empty one
  and an unreadable one are different facts.
