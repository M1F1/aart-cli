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

## D-069 — A legacy installation is unknown, never absent
- **Decision:** `read_consumer_machine` reads the project and user `manifest.json` beside the
  canonical receipt store, and every record it finds that no canonical receipt already answers for
  becomes an `UnadoptedInstallation`. Those are assembled into the same `machine.installed` list as
  measured installations, projected by `project_unadopted_installation` with the new
  `InstalledHealth.UNKNOWN`, a single `unobserved` drift that is not repairable, and no actions at
  all. The legacy roots are required keyword arguments rather than optional ones.
- **Status:** accepted.
- **Reason:** canonical receipts are MCP-specific, while Skills, guidelines, hooks and memory are
  still installed through the setup path into `install_state`. A reader that consulted only the
  receipt store therefore reported a machine with a Skill installed as a machine with nothing
  installed, and that emptiness is not inert: it is what a later install writes over and what a
  repair finds nothing to repair. This is D-029 applied across the strangler seam -- a component
  nobody observed is drift rather than a match -- and the same rule that keeps an uninspectable
  credential `UNKNOWN` rather than absent.
- **Consequence:** one list, not two. Splitting unadopted installations into their own band would
  leave `machine.installed` still able to answer "not installed" about something installed, which
  is the exact failure being closed. `UNKNOWN` is not a fifth degree of badness and nothing derives
  it from drift; the Dashboard counts such a row as installed but neither ready, updatable nor
  needing attention, and the Doctor neither reports it as an issue nor offers to repair it. No
  action is offered because `repair` would promise reconciliation against a desired state nobody
  holds and `uninstall` a removal the canonical effects cannot describe; the legacy path remains
  the one that operates these until a kind-neutral canonical receipt replaces them. Deduplication
  compares coordinates with the version stripped: a manifest record cannot carry a version and a
  receipt can, so comparing printed forms would list one installation twice, once measured and once
  unknown. The roots are required because a caller that omitted them would silently get the lying
  machine, and no signature should make that easy to ask for by accident. A missing manifest is no
  installations in that scope; a manifest that exists and cannot be parsed is a refusal.

## D-070 — One Selection becomes one offer, and accepting it is a separate call
- **Decision:** `offer_installation` composes the four functions an install already had --
  `plan_artifact_installation`, `aggregate_requirements`, `inspect_requirements` and
  `installation_remediations` -- into one `InstallationOffer` carrying the planned installations,
  the measured facts, the remediations that could be agreed to, and one observation per artifact.
  It selects nothing and mutates nothing; `begin_installation` remains the second call, and
  `InstallationOffer.selected()` is the convenience for a caller with nobody to ask.
- **Status:** accepted.
- **Reason:** every part of a canonical install was verified and none of it was reachable. The only
  caller of `plan_artifact_installation` was a test that wired the four together by hand, so the
  shell's action handler and the public commands would each have had to repeat that wiring -- and
  two copies of it disagree the first time one changes. This is the composition both need.
- **Consequence:** the whole Selection plans or the offer refuses, because offering the half that
  planned would let somebody confirm an install of two artifacts and receive one, which is the
  failure `execute_installation` prevents one layer down (D-064). `facts` in and `facts` out are
  deliberately different values: going in they are this machine's remediation capabilities, which
  decide which installer a plan may choose, and coming out they are what the inspection port
  measured. Observation is a required port rather than a default, because `begin_installation`
  refuses an unobserved artifact on purpose (D-029): an observer that cannot look refuses, since
  reporting an empty state would say "nothing is installed" about a machine nobody managed to look
  at, and a first install would then write over whatever is there. Remediation selection stays out:
  a non-interactive command accepts the whole offer or none of it, while screens 07 and 08 pass the
  subset somebody ticked, and the offer must not decide for either.

## D-071 — An installed artifact's own tree lives beside the manifest that records it
- **Decision:** `artifact_root(coordinate, scope, project_root=…, data_root=…)` places the tree an
  artifact owns -- payload, environment, interpreter -- at `<project>/.agent-artifacts/runtimes/
  <source>/<kind>/<name>` for project scope and `<data_root>/runtimes/<source>/<kind>/<name>` for
  user scope. Pure path policy in `domain/`: no filesystem, no working directory, no environment.
- **Status:** accepted.
- **Reason:** nothing decided this. The only answer in the repository was a path typed into an
  end-to-end test (`.tabnine/agent/aart/mcp/github`), which is fine for a test and useless to a
  command, and it is also wrong as a rule: it puts the tree inside one harness's directory when one
  artifact may register with several, so uninstalling that harness's registration would look like it
  should take the runtime with it.
- **Consequence:** the two roots are exactly the two `install_state_paths` already uses, so the
  manifest and the runtime it records are siblings rather than two places to look. The source is
  part of the path because two sources may publish the same name and they are not the same artifact.
  The version is deliberately absent: an update reconciles the one installation that is there rather
  than installing a second beside it and leaving somebody to work out which is live -- which is also
  what makes the root stable across the desired-state reconciliation CP-11 and CP-12 are built on.
  No harness name appears anywhere in it.

## D-072 — Supporting an effect means being allowed to carry it out
- **Decision:** `EffectInterpreter.supports` answers whether this interpreter may perform this
  effect, not whether it recognizes the effect's type. `FileEffectInterpreter` and
  `RuntimeEffectInterpreter` additionally require that they own the path the effect names,
  `HarnessEffectInterpreter` that it holds a matching registration *and* that the effect names the
  artifact it was built for, and `CredentialEffectInterpreter` that it was given the reference.
- **Status:** accepted.
- **Reason:** `_dispatch` takes the first interpreter that says yes, and one Selection is one
  transaction (D-064), so a Collection of two MCP artifacts hands the executor one interpreter tuple
  with a file interpreter per artifact. Under the type-only answer the first one claimed every
  `WriteFile` in the transaction -- including the second artifact's -- and then refused it for being
  outside the environment it owns. A bulk install of two artifacts therefore could not execute at
  all, which INV-130 and INV-138 require.
- **Consequence:** an effect nobody may carry out now fails as "no interpreter" rather than as the
  wrong interpreter's ownership refusal, so the message names the real fault. This narrows dispatch
  and never widens it: the ownership, registration and reference checks that produced those
  refusals still run inside `apply`, so an interpreter reached directly refuses exactly as before.

  The harness half is the one that was not failing closed. `ConfigureHarness` names the harness and
  the artifact but never the server, so two artifacts registering with the same harness were
  indistinguishable to an interpreter matching on the harness alone: the first would answer for the
  second artifact's step and register *its own* server under it. That is a wrong write rather than a
  refused one, and no later inspection of the second artifact would notice, because the entry it
  looked for would be present and correct. `HarnessEffectInterpreter` therefore takes the artifact
  it may register as a required argument -- the same doctrine as the content it may write and the
  reference it may act on, which are also supplied at construction rather than read off the effect.

## D-073 — One confirmed Selection gets one capability-bound interpreter set
- **Decision:** `interpreters_for` assembles the execution adapters for all planned installations
  before execution: one file, Python-runtime and artifact-bound harness interpreter per artifact,
  and one credential interpreter per provider holding the deduplicated references that name it.
  A referenced credential provider with no supplied adapter refuses the assembly before the
  mutation lock is taken. No credential value crosses this composition boundary.
- **Status:** accepted.
- **Reason:** the public commands and the shell action handler need the same adapter set. Leaving
  that wiring in each caller would duplicate security-sensitive ownership rules and had already
  hidden a multi-artifact ambiguity: two artifacts may register with the same harness, while a
  `ConfigureHarness` effect names the artifact rather than the server. A harness-only interpreter
  match could therefore carry out the second artifact's effect with the first artifact's
  registration.
- **Consequence:** `HarnessEffectInterpreter` is explicitly bound to the artifact whose
  registrations it holds, and both dispatch and direct application reject another artifact. Two
  artifacts sharing a provider share its one adapter, while missing providers are named as a
  composition failure instead of surfacing after files have been written. The authored-package E2E
  now installs through this assembler, proving the verified object-store package, generated
  launcher, owned environment, harness registration and provider reference all execute through the
  production composition rather than a test's hand-wired tuple.

## D-074 — Preparation and completion are the two halves of one installation action
- **Decision:** `prepare_installation_action` composes an `InstallationOffer` and
  `begin_installation` into one immutable `PreparedInstallationAction`; the caller supplies the
  remediation subset somebody selected, while `None` is the explicit non-interactive convention
  for accepting the whole offer. `complete_installation_action` accepts only that preparation's
  structural `ObjectDigest`, executes its whole proposal once, records one transaction plus each
  installed member, and returns a flow whose outcome is the exact durable transaction receipt.
- **Status:** accepted.
- **Reason:** the shell and four public command seams otherwise have to repeat the most sensitive
  order in the workflow: offer, accept, compare review, execute, project, record action, record
  installed members. Preserving the digest only inside either adapter would allow the other to
  execute a recomputed plan, while recording per member would reopen D-064's fragmented receipt.
- **Consequence:** a mismatched review is refused before the mutation lease, inspection or store is
  touched. Resolution, placement, input collection, effect adapters, inspection, the lease,
  persistence and the clock remain explicit caller-owned boundaries; this operation invents none
  of them. The authored-package E2E now uses this action and the D-073 assembler, proving one
  verified object-store package is offered, reviewed, executed, durably recorded and started by its
  harness without test-only orchestration between those stages.

## D-075 — A version's package digest and its store object digest are two values
- **Decision:** `RegistryArtifactVersion` carries `canonical_digest` and `object_digest`.
  `canonical_digest` stays the CP-05 tree digest of the promoted package with `provenance.json`
  excluded; `object_digest` is the store envelope digest over every entry, provenance included.
  Promotion computes the second where it writes the package and records it in the version record,
  the reference record and the catalogue, and `validate_promoted_registry` checks it against the
  vendored files exactly as it already checks the first.
- **Status:** accepted.
- **Reason:** CP-13 had treated them as one value, and they are not equal by construction. The
  consequence was silent and total: `placement_for` asked the object store for the package digest,
  the store addresses objects by their envelope digest, and the read returned nothing -- an install
  that resolves a version correctly and then reports that this machine does not hold what it just
  resolved. Nothing in the resolver or the store was wrong; the two were being asked to agree on a
  value neither of them computes.
- **Consequence:** the seam between an approved version and the bytes on this machine now names
  which digest it means, so neither can be substituted for the other by inference. A legacy row is
  still not evidence of approval and cannot manufacture either digest. The cost is one more
  immutable field on a published version, which is deliberate: both digests are part of what
  `_immutable_version_fields` refuses to let a republication change.

## D-076 — One adapter composes a configured install, and it derives its own roots
- **Decision:** `prepare_configured_installation` and `complete_configured_installation` are the
  single production composition over the D-074 action. They take an `InstallationHost` -- data root,
  project root, user home, scope, profiles -- and derive the state root, the harness root and the
  lock scope from it rather than accepting them. Preparation returns the screen-07 form when an
  input is unanswered and a reviewable action when none is; completion executes only the confirmed
  review digest and then re-reads the machine from disk.
- **Status:** accepted.
- **Reason:** every port the action needs was explicit and correct, and nothing supplied them. The
  shell's action handler and each of `install`/`update`/`uninstall` would have composed resolution,
  placement, capabilities, inspection, observation, interpreters, the lease, the receipt store and
  the clock independently. Two copies of that disagree the first time one changes, and the
  disagreement is silent, because both copies install something.
- **Consequence:** the roots are derived because preparation and completion have to act on the same
  machine, and a pair of roots passed twice can be passed differently -- an install prepared against
  project scope and completed against user scope would take the wrong lease and record into the
  wrong store, which no later inspection would report as anything but a missing installation.
  Unanswered inputs come back as the form rather than as a refusal, because screen 07 exists for the
  answer "not yet"; `action is None` holds exactly while the draft is not ready, and the type
  refuses to exist in any other combination. Remediation capabilities are measured or supplied, one
  per dependency backend this interpreter can actually run, one per credential adapter handed in and
  one per targeted profile: nothing is assumed to exist because it usually does. The returned
  machine is read after the run rather than assembled from the run, so an install that half-worked
  is visible as what it left behind instead of what it intended.

## D-077 — Delivering an artifact into a harness is a configuration mutation

- **Decision:** an artifact a harness reads rather than starts is installed by `DeliverArtifact`
  and removed by `WithdrawArtifact`, two effects at `CONFIGURATION_MUTATION` beside
  `ConfigureHarness`/`UnconfigureHarness` -- not by `CopyTree`/`RemoveOwnedPath`. A placed
  installation is recorded by `PlacedArtifactReceipt` and converges to a payload plus one
  `DELIVERY` component per harness, with no launcher, environment or dependency component at all.
- **Status:** accepted.
- **Reason:** INV-010 keeps artifact kind, package format and runtime protocol separate, and the
  canonical pipeline had not: it required a launcher, an interpreter and a transport of every
  installation, so four of the five kinds could not be planned, executed or recorded through it
  (B-033). Reusing `CopyTree` would have carried `LOCAL_MUTATION`, and a policy ceiling set there
  would then refuse to register an MCP server while permitting a Skill to be written straight into
  the directory that same harness reads. That is the same act at a lower stated risk, which is
  exactly what Fast review is forbidden to hide.
- **Consequence:** the delivery destination is the harness's, so withdrawal removes only what this
  installation delivered rather than a path AART claims to own; a withdrawal is reversible in the
  way an entry in a settings file is, because the payload it was made from still stands. The
  receipt records each delivery's source and the receipt refuses one outside the artifact root, so
  a repair copies from the artifact that owns it and never from somewhere nobody chose. One harness
  reads one delivery, because the reconciler names a delivery component by its harness and two
  would collide into one -- a hook's settings entry stays a `ConfigureHarness`, which is what it is.
  No `LAUNCHER` component is emitted for a placed artifact rather than an empty one: a reconciler
  comparing components would read a missing launcher as drift and repair it into a process nobody
  installed.

## D-078 — Permission hardening must remain reversibly owned

- **Decision:** immediately before recursively removing an AART-owned payload or an exact
  capability-bound harness delivery, restore owner read/write/search bits on directories inside
  that tree. Do not follow or chmod directory symlinks, and never change the parent directory or a
  sibling. File contents and permissions outside the named tree remain untouched.
- **Status:** accepted.
- **Reason:** promoted object trees and their delivered copies may deliberately retain read-only
  owner modes. On macOS, recursive removal then fails at the first child because deleting a
  directory entry requires write permission on its parent. The effect had already passed its
  ownership/capability check, but AART's own hardening made a reviewed uninstall impossible and
  left a half-removed installation.
- **Consequence:** permission restoration is a removal implementation detail, not a new effect or a
  widened authority. A delivery interpreter can alter only the destinations it was constructed
  with, and a file interpreter only paths its `ArtifactEnvironment` owns. Tests freeze nested trees
  read-only, preserve neighboring harness artifacts and prove symlink targets survive both removal
  paths.

## D-079 — Public install strangles by configured source kind

- **Decision:** `marketplace install` routes a Selection through the configured canonical action
  when every member is a direct artifact and its explicit source, or the configured default for an
  unqualified selector, is an enabled `RegistryGit` source. Direct/local sources and Collections
  remain on the characterized legacy route. The public envelope stays stable while `review` is the
  `consumer_plan_to_data` projection and `receipt` is `receipt_detail_to_data`; human text renders
  those same canonical values.
- **Status:** accepted.
- **Reason:** a promoted registry snapshot has approved version and object identities that the
  legacy root-manifest reader neither understands nor may infer. Routing by coordinate kind alone
  would send an unapproved local Skill through the approved resolver, while routing every install
  at once would strand Collections that protocol v1 cannot version (B-031). Source kind is the
  narrow authority boundary already present in configuration.
- **Consequence:** a stale `--expect` digest refuses before target mutation, and completion writes
  canonical installation and activity receipts rather than the legacy manifest. Canonical `status`
  is now the next seam because the legacy status reader cannot report that receipt. Explicit
  symlink mode is refused rather than silently copied until B-035 exists; this does not alter the
  local/direct legacy behavior still under characterization.

## D-080 — Public canonical status measures the requested durable view

- **Decision:** `marketplace status` reads `read_consumer_machine` when its explicit Selection, or
  its configured default when no coordinate is supplied, belongs to an enabled `RegistryGit`
  source. The machine reader may be narrowed by scope and harness profile: canonical receipts are
  selected by their measured registrations or delivery destinations, and legacy manifest records
  by their recorded scope/profile. The stable command item keeps `status: current` to mean that a
  durable installation record is present, while the additive `health` field carries the measured
  `ready`/`update`/`attention`/`broken`/`unknown` state. Human text renders the same
  `InstalledArtifactView`.
- **Status:** accepted.
- **Reason:** the new public install writes a canonical installation receipt and no legacy
  manifest, so the legacy status path necessarily reported it as absent (and could fail earlier
  while trying to parse a registry root as a legacy source). Reading a receipt alone would still
  be insufficient: status must detect drift on disk, and a project-scoped request must not expose a
  user-scoped installation merely because canonical receipts share a durable store.
- **Consequence:** a later invocation reports an approved-registry Skill installed by the public
  command, an edited delivery reports `health: attention`, and the opposite scope/profile remains
  absent. Empty canonical state remains a successful empty result. Direct/local sources retain
  their characterized legacy source-availability semantics until their own route moves; `update`
  is the next public lifecycle seam.

## D-081 — Supersession is decided by the plan, not by the command

- **Decision:** `propose_installation` accepts a `previous` mapping of unversioned coordinate to the
  `DesiredState` each artifact is replacing, and `supersession_intent` turns the pair into
  `UPDATE`, `REPAIR` or a refusal. Public `marketplace update` therefore rebuilds its Selection from
  the canonical records rather than from typed coordinates, pins no version unless somebody pinned
  one, and never decides for itself whether the approved version is newer.
- **Status:** accepted.
- **Reason:** the command does not know the resolved version until after resolution, so deciding
  update-vs-install there would need a second, throwaway preparation. Keying `previous` by
  unversioned coordinate is what lets one side carry the installed version and the other the
  resolved one; a versioned key could only ever agree with one of them.
- **Consequence:** `update` on an artifact already at the approved version reports `current` and
  writes nothing; an older approved version is refused by name as a downgrade rather than applied;
  and `artifact_root` staying version-independent means an update converges in place.

## D-082 — A payload is judged by its content, not by its presence

- **Decision:** `PlacementObservation` carries a measured `payload_digest` beside
  `payload_present`, produced by the extracted `tree_digest_at`. `ComponentState` for the payload is
  `MATCHED` only when that digest equals the receipt's, `DIVERGENT` when it differs, and `UNKNOWN`
  when nobody could measure it.
- **Status:** accepted.
- **Reason:** `artifact_root` is version-independent, so an update writes the new version into the
  directory the old one occupies. Presence-only judgement therefore reported an already-converged
  payload, the `CopyTree` was skipped, and the harness kept reading the previous version's content
  under the new version's name -- reported as a successful update.
- **Consequence:** an edited payload is drift a repair can find, an unmeasurable one says so rather
  than passing, and `FileEffectInterpreter._copy` had to become convergent: it removes an existing
  destination tree (clearing the object store's read-only modes first) before copying.

## D-083 — Uninstall runs through the install executor, from receipts alone

- **Decision:** `RemovalProposal` is planned from `InstalledRecord`s -- never from resolution -- and
  `execute_installation` is widened to `ReviewedTransaction = InstallationProposal | RemovalProposal`
  so a removal runs under the same scope lease, the same confirmed review digest and the same
  per-member accounting. `prepare_configured_uninstall` measures each member against the state the
  removal converges to, which is the vocabulary the executor re-measures in at preflight.
- **Status:** accepted.
- **Reason:** the load-bearing properties of a transaction -- one lease, one review, every member
  accounted for -- are direction-independent, and a second executor would be the half that drifts.
  Planning from receipts is what keeps `_PROJECT_LOCAL`'s existing guarantee: an installed artifact
  outlives the configured source that delivered it, so removing the subscription must not strand it.
- **Consequence:** a converged release forgets its record, so a later `status` reports nothing
  installed rather than an installation nothing can find; withdrawal interpreters stay bound to the
  deliveries the receipt names, so a neighbouring Skill in the same harness directory survives; and
  credentials are retained by default, with no credential adapter required unless the reviewed
  removal actually deletes one.

## D-084 — A memory artifact owns a region of a file, not the file

- **Decision:** memory is installed by `MergeManagedBlock`/`UnmergeManagedBlock` rather than
  `DeliverArtifact`. `MEMORY_TARGETS` is its own measured table, deliberately not a
  `DeliveryTarget`: a delivery destination must name the artifact, and a memory destination must
  not, because every memory artifact for a harness shares one file with the user. The receipt
  records an `ArtifactMerge` whose digest covers the block body as stored, never the file, and the
  reconciliation component is `MERGE`, named by the harness that reads it.
- **Status:** accepted.
- **Reason:** every measured memory location -- `CLAUDE.md`, `.claude/CLAUDE.md`, `TABNINE.md` -- is
  a file a person writes in. Delivery replaces its destination, so installing memory as a delivery
  would destroy the user's own notes, and digesting the file would report every note they added
  afterwards as drift in an artifact that had not changed.
- **Consequence:** a memory artifact installs, reports health, detects an edited block as drift,
  ignores writing beside it, and uninstalls leaving the file. The `ManagedBlockInterpreter` refuses
  three things rather than guessing: a symlinked destination (never followed, per D-078), a
  destination that is not UTF-8 text, and a file whose markers are damaged. It also preserves the
  mode of a file it did not create, which `write_atomic` alone would have reduced to 0600. Tabnine
  has no user-scope memory target on purpose: that build documents no always-loaded global
  instruction file. Hooks stay open (B-034), because a hook needs a list merge with an identity
  tuple rather than a delimited block.

## D-085 — A hook is delivered and merged, and its descriptor must say when it runs

- **Decision:** a hook is installed by both halves at once. Its script is an ordinary
  `DeliverArtifact` into a directory named for the artifact, and what makes the harness run it is a
  `MergeSettingsEntry` owning one element of one list inside a settings file the harness and its
  user share. `HOOK_TARGETS` keeps the script directory, the settings file, the event map and the
  entry shape as one measured fact per harness/scope, and `delivery_target` routes
  `ArtifactKind.HOOK` through it rather than through a second `DELIVERY_TARGETS` row. Identity is
  `(matcher, command)`, the entry is modelled as a typed `HookEntry` rather than rendered from a
  `${...}` template, and `payload/hook.json` now requires `event` and `matcher` beside the existing
  `name` and `command`.
- **Status:** accepted.
- **Reason:** the two halves are one artifact and cannot be recorded separately: a hook whose script
  is placed and whose entry is not installs cleanly and never runs. Keeping the three hook facts in
  one table stops a build's script directory and its settings file from drifting apart, and keeping
  the entry typed keeps an untyped renderer out from between what somebody reviewed and what is
  written into their configuration. The descriptor rule was strengthened rather than worked around:
  without an event there is no slot to write the entry into and without a matcher there is nothing
  for the harness to match, so a package missing either compiles into something nothing can place
  -- and the author is the only person who can still fix it.
- **Consequence:** a hook installs, reports health, detects an edited entry as drift, ignores
  another hook added beside it, and uninstalls taking its entry and its script while leaving the
  settings file, the user's own configuration and every other hook intact. The list itself is never
  removed on uninstall: it is the harness's key, not this artifact's.
  `SettingsEntryInterpreter` refuses rather than guesses -- a symlinked destination (D-078), a file
  that is not JSON, a document that is not an object, and a list holding something other than
  entries -- and preserves the mode of a file it did not create. `package_hook` refuses a command
  that does not begin `${SCRIPT_DIR}/` or names a file the package does not carry, and refuses a
  script that is not executable, because a hook that installs and then does nothing is worse than
  one that refuses to build. Tabnine has no user-scope hook target on purpose: that build documents
  no user-global hook discovery location. B-034 is now closed.

## D-086 — A repair may only put back what the receipt describes

- **Decision:** `prepare_configured_repair` takes an already-measured `InstalledInspection` rather
  than measuring again, resolves nothing, and `interpreters_for_receipt` builds the adapter set from
  the receipt alone. An `InstallationReceipt` records `launcher_digest` and never launcher content,
  so no launcher bytes are offered; a repair step that would rewrite the launcher fails closed at
  that one step rather than writing something nobody planned.
- **Status:** accepted.
- **Reason:** a repair is the lifecycle that has to work when nothing else does -- the source
  unsubscribed, the registry unreachable, the object store pruned. Re-measuring would answer a
  different question from the one on the screen, and re-resolving would make repair depend on the
  very thing that is usually broken. The receipt is the only thing guaranteed to still be there.
- **Consequence:** everything a receipt can describe is repairable -- deliveries, merges, settings
  entries, harness registrations, environments, dependencies -- and the tests prove a deleted
  delivery is restored after the source has been disabled. What a receipt cannot describe is refused
  by name ("nothing here holds the content ... names") instead of approximated. A wrong confirmed
  digest is refused before any write, and a machine that moved between the review and the
  confirmation is refused under the lease.

## D-087 — A refusal is drawn where it was asked, never raised

- **Decision:** the production `ConsumerActionHandler` never raises on a refused action. It returns
  `ACTION_PREPARED` with an empty `review_digest`, or `ACTION_RECORDED` with empty `text`, which the
  reducer already reads as "nothing was established", and carries the diagnostics as a
  `ConsumerScreens.notice`. The notice is rendered only on the screens an action lands on
  (`_ANSWERABLE`); everywhere else it would be an answer to a question nobody asked there.
- **Status:** accepted.
- **Reason:** a persistent terminal application that threw on an artifact that failed to resolve
  would take the session down with it, losing the selection and everything else in flight. The
  reducer already had a representation for "nothing was established"; inventing an error path beside
  it would have given the same fact two spellings.
- **Consequence:** an action on something that is not installed, an offer the registry has since
  withdrawn, a confirmation naming a different plan, and a selection with unanswered inputs are all
  drawn under the screen they were asked from, with the session left exactly where it was. This is
  also how Fast keeps from hiding material risk: the reason is on the screen, not swallowed.

## D-088 — The Marketplace projects configured registries, and trust is the promotion record

- **Decision:** `read_consumer_offers` now reads `io/configured_offers.read_configured_marketplace`
  instead of the characterized protocol-v1 loader. An offer is an approved *published, vendored,
  non-deprecated* version of a configured `RegistryGit` source, read from `registry/versions/*` --
  the same approval identity `resolve_configured_selection` resolves against. Each offered version's
  published package is re-rooted and recompiled with `compile_native_package`, so the row's
  compatibility, digests and setup capabilities come from the package the registry published rather
  than from a second copy of the rules. An enabled source that is not a registry still contributes
  its health and offers nothing. Trust comes from the promotion that approved the version:
  `load_registry_promotions` reads `registry/promotions/<candidate_id>.json` back with the writer's
  own canonical form, and its `effective_policy_result` becomes the offer's `ReviewRecord` policy.
- **Status:** accepted.
- **Reason:** INV-026 -- "a marketplace is a human-facing projection over configured registries; it
  does not silently redefine registry trust decisions." The two layouts had drifted apart: the shell
  offered artifacts from native sources that `prepare_configured_installation` could not resolve,
  and refused outright on a canonical published registry, so the composed application could not
  install what it offered. Deriving trust from anything other than the promotion record would be
  restating an approval the registry alone can make -- and leaving `review=None` understated it to
  `unverified`, which is redefining the registry's decision downward.
- **Consequence:** what is browsed in the canonical shell is installable from it. One version is
  offered per identity -- the highest approved SemVer, which is what an unconstrained request would
  resolve to -- and an older approved version is superseded rather than declined, since it is still
  reachable under the same row. Everything approved but not offerable is declined by name:
  Collections (B-031), referenced versions with no verified content in the snapshot, revoked
  versions, and deprecated ones, whose warning the row has nowhere to render yet (B-036). A version
  whose promotion record is missing is refused rather than offered with a review nothing evidences.

## D-089 — A promotion rebinds every approved version record to the snapshot it produces

- **Decision:** `plan_bulk_promotion` rewrites `registry/versions/<kind>/<name>/<version>.json` for
  the versions it retains as well as the ones it promotes, replacing each retained record's
  `registry_snapshot` with the digest of the registry content this transaction produces. Retained
  records are written as mutable changes; newly promoted ones stay immutable. The plan's `versions`
  field still carries only the transaction's own versions, because `PromotionPlan.__post_init__`
  requires one audit per version and `load_registry_versions` already returns the full validated set.
- **Status:** accepted.
- **Reason:** `registry_snapshot` is the digest of the whole registry's approved content, and
  `validate_promoted_registry` requires every version record to bind one exact digest. Promoting
  anything changes that content. Rewriting only the new records left the second and every later
  promotion of a registry unreadable to every consumer -- reachable from `aart registry promote`, so
  a live defect rather than a fixture problem (B-037). The alternative, narrowing `registry_snapshot`
  to the version's own package, would drop the property that an approved version names the exact
  registry state it was approved against, which is what makes an approval auditable after the fact.
- **Consequence:** rebinding is metadata only -- the package at a published coordinate is never
  rewritten, guarded by `test_a_second_promotion_leaves_the_first_package_byte_identical`. It stays
  inside one reviewed transaction, so a promotion is still all-or-nothing and no record is ever
  bound to a snapshot that was not itself reviewed. Registries can now hold many approved versions
  across many transactions, which is what an identity with more than one released version requires.

## D-090 — Screen 28 is a durable preference, and the reducer asks for it to be kept

- **Decision:** the four controls of accepted screen 28 are row identities (`SETTING_ROWS`), the
  screen has rows and a cursor like every other list, and Enter or Space on the focused row emits
  `TOGGLE_SETTING`. `v` and screen 28's Detail level are one preference, so `TOGGLE_PROFILE` now
  goes through the same `_apply_setting` path. Both emit a `PERSIST_SETTINGS` command; the reducer
  stays pure and the shell's injected `settings_writer` is what makes the preference outlive the
  session. `io/consumer_settings.py` keeps it at `<data_root>/state/consumer-settings.json`, mode
  `0600`, written atomically. `opening_state` seeds the session's profile and stored settings
  together, and screen 28 draws `state.settings` rather than the composed source's copy.
- **Status:** accepted.
- **Reason:** Product Specification 161.10 accepts Settings with four controls and makes Maintainer
  Mode the boundary that hides Sources, Candidates, Promotion, Registry Diff, Validation and
  Publish. A preference that dies with the terminal is not a setting, and an opt-in that has to be
  re-chosen every session is not an opt-in -- which also makes this a prerequisite for CP-14, whose
  whole surface is behind that toggle. Only `v` could change anything before, and nothing was ever
  written down.
- **Consequence:** a stored value AART cannot mean is refused rather than repaired, because
  falling back to Fast after somebody chose Verbose, or to Maintainer Mode off after they turned it
  on, is the frontend deciding for them; `_canonical_consumer_actions` therefore refuses instead of
  opening on a view that contradicts what screen 28 was last told. A shell composed with no
  `settings_writer` raises when a preference changes rather than silently forgetting it, so a
  frontend without durable storage is a test double by construction. The file holds preferences
  only -- no coordinate, registry, credential or path -- so it says nothing about what is installed.

## D-091 — The last of CP-13's legacy authority is a CP-14 dependency, not a product question

- **Decision:** CP-13's remaining legacy retirement -- `commands/marketplace.py` routing Collections
  and direct/local sources through `consumer/application.py` and the `setup_engine`/`installation`/
  `lifecycle` stack -- is sequenced behind CP-14 rather than treated as blocked on two open product
  questions. B-031 and B-038 are reclassified accordingly. CP-13 is otherwise complete: every
  accepted screen 01-29 now draws from canonical views over a real machine, and the coverage table
  records what closed each row.
- **Status:** accepted.
- **Reason:** both questions are already answered by the Product Specification, and both answers
  land in CP-14. Section 145.1 states a Collection is *versioned* and its example declares
  `version: 2.1.0`; the gap is that `CollectionManifest` carries no version and
  `discover_author_manifests` never looks at a collection root, so nothing has ever compiled,
  promoted or published a Collection as a registry artifact. EXECUTION_PLAN CP-14 owns "collection
  candidates". Section 1737 lists Source as the origins a *registry* pulls from, and INV-019-INV-026
  describe consumer installation entirely over approved registry content -- INV-021: installing an
  approved vendored registry artifact uses the registry snapshot, not the author repository. CP-14
  owns Sources screens 31-34. So the canonical consumer seam offering nothing from a native source
  is the specified behavior; it is the legacy route's direct native install that has no basis.
- **Consequence:** no legacy module is removed in CP-13, and none is removed on a guess: the two
  routes that still reach legacy authority are exactly the two CP-14 gives a canonical home. Nothing
  installable is lost in the meantime, because the legacy route still operates both. CP-13's own
  acceptance does not wait on that removal, and the removal criteria in the slice file stand as
  written -- public machine-output tests first, deletion after.

## D-092 — Maintainer screens are a separate catalog inside the one application state machine

- **Decision:** screens 30–53 are `MaintainerScreen`, separate from the consumer-only
  `ConsumerScreen` enum, and `ApplicationScreen` is the union carried by the existing
  `ConsumerSession`, UI events, commands, reducer, keymap and shell. `navigation_targets` takes the
  durable Maintainer Mode value: while off it exposes no Maintainer target and even a direct forged
  navigation event is refused; while on it adds only screen 30 to the Dashboard roots, with the
  complete Maintainer graph reachable beneath it. A state cannot be seeded on a Maintainer screen
  while the setting is off. Dashboard rows and Enter targets derive from this same graph.
- **Status:** accepted.
- **Reason:** Product Specification 161.10, 162 and INV-193 make the whole Maintainer surface an
  opt-in advanced area, while 164 requires screens 30–53 to share the persistent application. One
  widened enum would make CP-13's invariant that every consumer screen is implemented falsely
  include unfinished Maintainer bodies; a second reducer would split navigation and key semantics.
  Separate catalogs inside one typed state preserve both truths. Deriving the drawn Dashboard menu
  from the guarded graph also fixes a discovered reachability defect: the canonical Dashboard had
  no rows or Enter target, so a default terminal could not reach Settings to enable the mode.
- **Consequence:** disabling the preference hides Sources, Candidates, Validation, Promotion,
  Registry Diff and Publish by construction, not by renderer convention. The grouped accepted
  screens have stable internal identities for incremental implementation without being counted as
  implemented merely because their names exist. Every future Maintainer renderer/action joins the
  existing session and keymap, and a test that bypasses the terminal cannot cross the mode boundary.

## D-093 — Maintainer Source views bind configuration, health and one exact Source Scan

- **Decision:** screens 30–32 project from a `MaintainerSourceView` that binds one non-registry
  `ConfiguredSource`, its `SourceHealth`, and an optional `SourceScan`. When a scan is present its
  alias and pinned revision must equal the current durable Source observation; mismatched or
  source-less scans are refused. Candidate/manifest counts and target registries come only from the
  scan's active `CandidateBundle`s. `MaintainerDashboardView` aggregates those already-projected
  values and supplied activity; it performs no read, discovery, validation or clock access.
- **Status:** accepted.
- **Reason:** Product Specification 164.1–164.2 requires the Maintainer Dashboard and Sources views
  to distinguish authoring Sources from registries and to report real Candidate state. Configuration
  alone cannot say what was discovered, Source health alone cannot say what compiled, and a scan
  from another revision would combine observations that never coexisted. Counts inferred from file
  names in a renderer would also duplicate CP-04/CP-05 discovery authority.
- **Consequence:** Fast shows source/candidate outcomes and an abbreviated revision; Verbose reveals
  the full pinned revision, target registries, state counts and already-redacted diagnostics. The
  shared screen source can draw and navigate screen 30, Source list and Source detail from injected
  immutable views. Production composition must now provide the matching durable scan; it may not
  silently reconstruct a previously reviewed Candidate state as New on every application start.

## D-094 — Candidate history is an atomic index over retained immutable compiled objects

- **Decision:** one configured authoring Source keeps its current `SourceScan` beneath its managed
  Source instance at `candidates/current.json`. The strict canonical index records complete
  Candidate lifecycle metadata and references compiled artifact envelopes by their SHA-256 object
  digest; those immutable envelopes live below `candidates/objects/sha256/`. A writer publishes and
  verifies every object before atomically replacing the private-mode index. Objects no longer named
  by the current index are retained as audit evidence. The reader loads only exact digests named by
  the bounded canonical index and refuses missing, corrupt, mismatched or symlinked state.
- **Status:** accepted.
- **Reason:** INV-229 and INV-239 make superseded and digest-aware rejected Candidates durable
  product history. Recompiling an author repository on application startup would reconstruct every
  Candidate as New, while embedding compiled payloads in an ever-growing mutable index would erase
  the already-established content-addressed object boundary. Publishing objects before the one
  pointer-like index also gives interruption an honest outcome: at worst an unreferenced retained
  object, never a current scan that references bytes which were not established.
- **Consequence:** screen composition can recover reviewed, rejected, promoted, removed and
  superseded state without scanning a repository or guessing. Missing history remains distinct from
  corrupt history; a corrupt store is not presented as zero Candidates. Serialization additionally
  refuses an active Candidate that is not the exact history record, another Source alias, another
  pinned revision or non-canonical ordering. Source Sync must perform the write while holding the
  existing per-instance mutation lease; this adapter supplies atomic publication, not a second lock
  or lifecycle authority.

## D-095 — Maintainer Source screens are one composed observation, not live draw-time reads

- **Decision:** `io/maintainer_views.read_maintainer_views` walks configured non-registry Sources
  once, reads each current Source observation and its Candidate-history index once, and projects the
  already-bound D-093 views. Registry Sources are excluded because screens 31–34 are authoring
  Sources, not approved registries. The resulting immutable `MaintainerViews` travels in
  `ConsumerActionContext` and through every `screens_from` refresh; `_canonical_consumer_actions`
  composes it beside the consumer machine, offers and settings before the shell starts.
- **Status:** accepted.
- **Reason:** Product Specification 164.1–164.2 requires Source health and Candidate counts to
  describe the same pinned observation, while D-051 keeps filesystem and clock effects outside a
  draw. Re-reading either side in a renderer could combine a new Source pointer with old Candidate
  state. Silently dropping a corrupt or previous-revision history would instead present an observed
  failure as zero Candidates.
- **Consequence:** absent history means a configured Source has not produced a durable scan yet;
  corrupt, missing-object or mismatched-revision history refuses the composition. A real production
  application journey now enters Dashboard → Maintainer Dashboard → Sources → Source Details and
  renders the persisted Candidate count with no hand-injected view. Screens 33–34 must refresh this
  same context only after a successful Source Sync and durable reconcile write.

## D-096 — Pinned Source revisions retain their origin kind

- **Decision:** the canonical immutable revision of a Git Source remains its 40-lowercase-hex
  commit, while a local authoring Source uses `local:<snapshot-sha256>`. The shared domain accepts
  exactly those two forms. Native authoring provenance records `origin.kind: local`, the normalized
  absolute configured location and that tagged revision for a local Source; the existing v1 JSON
  field remains named `resolved_commit` for wire compatibility even though its value is the tagged
  Source revision. `SourceScan`, artifact provenance and Candidate history carry the same value
  end to end.
- **Status:** accepted.
- **Reason:** `read_local_snapshot` already establishes immutability by hashing the exact safe tree,
  and the Source pointer already requires `local:<that digest>`. Narrowing screens 33–34 to Git would
  violate the accepted local Source kind; truncating or disguising a SHA-256 as a Git commit would
  destroy the origin distinction and weaken audit evidence.
- **Consequence:** local Source Sync can compile, persist and strictly reread Candidate history
  without invented Git identity. Git-only registry index/provenance projections remain intentionally
  narrow for now; the CP-14 promotion increment must make the local-origin handling explicit before
  it claims that a local Candidate can be promoted, rather than silently rewriting its provenance.

## D-097 — Source Sync is one reviewed transaction under the Source lease

- **Decision:** `SOURCE_SYNC` joins the shared typed action reducer. Preparation reads the focused
  enabled authoring Source, its exact current pointer and Candidate-history index, and the configured
  default registry's exact approved snapshot, then binds those observations plus acquisition limits,
  runtime capabilities and offline/fallback semantics into one review digest. Confirmation rereads
  the registry before mutation, acquires the configured Source instance lease, rechecks the
  Source/history baseline, acquires/validates/publishes through `SourceSyncPorts`, discovers and
  compiles exact author manifests, reconciles against retained history and approved versions,
  atomically writes Candidate history, and rereads the exact scan before releasing the lease.
- **Status:** accepted.
- **Reason:** INV-007 requires review before mutation, INV-200 forbids Source Sync from promoting,
  and D-094 requires Candidate history publication to share the Source mutation lease. A nested
  `sync_source()` followed by an unlocked history write would expose a new Source pointer beside old
  Candidates; recomputing the review at confirmation would execute a plan nobody saw.
- **Consequence:** `sync_source_while_locked` is the narrow application seam for a caller that owns
  the correct instance lease. A changed approved registry refuses before the Source lock; a changed
  Source/history baseline refuses under the lock before acquisition. Successful screen 34 state is
  projected from the persisted readback, and both Fast and Verbose say that registry mutations are
  none. Compilation failure after a valid Source publication remains an explicit partial failure:
  no Candidate index is published, and the next production composition refuses the revision mismatch
  rather than presenting zero or stale Candidates.

## D-098 — Candidates are addressed by Candidate ID and narrowed by typed filter state

- **Decision:** screens 35–37 join the shared screen source. Screen 35's row identity is the stable
  Candidate ID rather than the artifact name or coordinate; screens 36 and 37 resolve their subject
  from that ID. What the list is narrowed to is `MaintainerCandidateFilter` — typed application
  state carrying selected Candidate states, Source aliases and a query — rather than string matching
  performed by a renderer; an open search box narrows that filter instead of replacing it. The raw
  canonical file diff on screen 37 is a separate `f` toggle over the same projection, off on entry
  and cleared by any navigation.
- **Status:** accepted.
- **Reason:** 164.5 makes Maintainer review semantic diff first and raw file diff second (INV-202),
  which is a statement about what is offered by default and not only about ordering inside one
  frame. Two authoring Sources may both publish an artifact called `github-mcp`, so a list keyed by
  artifact name would open the wrong Candidate, while `candidate_id_for` already binds identity to
  the package and its target registry. Filter logic living in a renderer would make a filtered
  review irreproducible across presentation profiles and terminals.
- **Consequence:** `filter_maintainer_candidates` is the one predicate and `_candidate_filter` is
  the one place the search box meets it, so screen 35's rows and body cannot disagree. Screen 53
  has a typed value to edit when it lands and needs no second filter model. Drawing 35–37 reads
  nothing from the machine: the shell is handed the composed scans `read_maintainer_views` already
  read once, and the `d`/`f` keys stay inside `key_event` as the only key interpreter (D-041).

## D-099 — Candidate validation is a named pipeline, and policy is what makes a warning block

- **Decision:** `application/candidate_validation.py` runs the ten checks 164.6 names, in that
  order, over the compiled artifact a Candidate already carries. Each check reports its own
  `ValidationOutcome` — `passed`, `warning`, `error` or `not-run` — with actionable details carrying
  path, declared and expected values. `not-run` is deliberately not a pass: a check that produced no
  evidence has not agreed that anything is fine. Live acceptance is always `not-run` here, because a
  real installation on a real machine is CP-17's, and ticking it would claim evidence nothing
  produced. Policy enters through the existing `EffectivePolicy.required_checks`: any required check
  that did not pass makes the Candidate `APPROVAL_REQUIRED` rather than `WARNING` or `READY`.
- **Status:** accepted.
- **Reason:** 164.6 makes three separations load-bearing — warnings distinct from errors, policy
  deciding whether a warning blocks promotion, and policy-required manual approval being its own
  Candidate state rather than a warning treated specially. `required_checks` already existed on
  `EffectivePolicy` and had no reader; using it is the smallest choice that satisfies all three
  without inventing new policy configuration. `assess_candidate` already ranks error above manual
  approval above warning, so the pipeline feeds it rather than re-deciding.
- **Consequence:** the same Candidate is `READY` under an undemanding policy and
  `APPROVAL_REQUIRED` under one that requires live acceptance, and neither answer is a defect.
  Several checks are re-verifications — `compile_author_snapshot` refuses most malformed manifests
  long before a Candidate exists — so their value is catching a Candidate history corrupted or
  tampered with after the fact; they are tested against deliberately doctored canonical trees.
  Two checks are reachable on artifacts that compile cleanly and are the pipeline's real teeth: a
  secret bound to a command-line argument is an **error**, because argv is readable from the process
  table, and an executable payload file is a warning the Security check names by path.
  Wiring organization configuration into `EffectivePolicy` is not done here: the canonical path
  still composes a default `EffectivePolicy()`, exactly as `io/consumer_actions.py` already does.

## D-100 — A validation row is a Candidate and a check together, and the policy judgement travels with the run

- **Decision:** screen 38's rows are `MaintainerValidationRowId` values rendered as
  `"<candidate-id>:<check>"`, parsed back by `parse_validation_row`, which returns nothing rather
  than raising for anything that is not one. Screen 40 accepts either shape — a bare Candidate ID or
  one of its check rows — and resolves both to the same Candidate. The policy judgement is composed
  into `MaintainerValidationView.review` by `project_maintainer_validation`, not derived again when
  screen 40 draws. `read_maintainer_views` takes the `EffectivePolicy` as a parameter and composes
  every active Candidate's run once.
- **Status:** accepted.
- **Reason:** the subject of screen 39 is neither a Candidate nor a check but both at once: a check
  name alone is ambiguous across Candidates, and a Candidate ID alone cannot open one check. Making
  that pair a parsed typed value rather than a string a renderer splits is what lets screens 39 and
  40 be entered directly and still know what they are about — which the shell does in practice, as
  the E2E walk enters screen 40 from a check row rather than from a Candidate ID. Returning `None`
  from the parser rather than raising follows D-087: the focus is whatever the previous screen put
  there, and a screen that cannot recognise it refuses inside the frame instead of crashing the
  session.
- **Consequence:** screen 38 and screen 40 cannot disagree about the same Candidate, because they
  read one run rather than two. Validation now happens once per active Candidate at composition
  time, which is the same place the Candidate projections are already built; drawing opens no file,
  and a test asserts it across all three screens. `EffectivePolicy` still arrives as the default at
  the canonical call sites, so wiring organization policy into configuration remains open work
  rather than something this slice guessed at. An allowlist that is `None` renders as
  "unconstrained" and an empty one as "none permitted": a policy that does not constrain runtimes
  permits every runtime, one that constrains them to nothing permits none, and a Maintainer has to
  be able to tell those apart. `RiskClass` is an `IntEnum` whose lowest member is `0`, so the review
  carries its name rather than its falsy value.

## D-101 — A promotion carries the run that approved it, and the run decides whether it may proceed

- **Decision:** `application/maintainer_promotion.py` binds one Candidate, the validation run that
  judged it, the policy behind that run and the approved registry baseline into one
  `PreparedCandidatePromotion` with a review digest. The `PromotionEvidence` it produces digests the
  validation report and the effective policy, and carries the warnings a Maintainer was shown, each
  prefixed by the check that raised it. The run's state decides promotability — `INVALID` and
  `APPROVAL_REQUIRED` are refused with the reason — rather than the state the scan recorded
  earlier. Screen 41 projects the refusal instead of raising it, and never shows a review digest
  for a review that cannot be confirmed.
- **Status:** accepted.
- **Reason:** promotion is the first Maintainer action that writes approved registry state, so what
  it records has to be the review that actually happened. Digesting the report and the policy is
  what lets an audit record answer "who approved this, against which rules" rather than only "this
  was promoted"; two policies that a digest could not tell apart could not prove which one approved.
  The run governs rather than the stored state because policy may have changed since the scan, and
  the run is what screens 38–40 actually showed. A refusal is a legitimate answer to "can this be
  promoted", and D-087 already settles that a refusal is drawn under the screen it was asked from.
- **Consequence:** `read_maintainer_views` now reads the approved state of each registry its active
  Candidates target and composes a promotion review per Candidate; a registry with no synchronized
  snapshot becomes a stated refusal rather than an error that hides the rest of the composition.
  The review digest covers the mode and the registry baseline as well as the Candidate, so
  confirming a review cannot apply a transaction other than the one reviewed. An unconfirmable
  review renders its reasons *in place of* the digest, because a digest on screen is an invitation
  to confirm. D-103 now defines how that digest and every observed baseline are rechecked at
  execution.

## D-102 — Both promotion modes are composed, and the chosen one is typed state

- **Decision:** `read_maintainer_views` composes a promotion review for every active Candidate in
  *both* `PromotionMode` values, and `MaintainerViews.promotion(candidate_id, mode)` selects one.
  The chosen mode is `ConsumerUiState.promotion_mode`, toggled by `m` on screen 42 only, and
  screens 41 and 42 draw the review of the mode currently chosen.
- **Status:** accepted.
- **Reason:** the mode is inside the review digest (D-101), so changing it has to produce a
  different review to confirm rather than a relabelled one. That leaves two ways to satisfy screen
  42: recompose a review when the mode changes, or compose both up front. Recomposing would put
  projection work behind a keypress and, worse, inside drawing — the boundary CP-14 has kept
  everywhere else. There are exactly two modes, so composing both is bounded and cheap, and it
  keeps the shell selecting a projection rather than making one.
- **Consequence:** `MaintainerViews.promotions` is keyed by Candidate *and* mode, and its
  uniqueness check is over the pair. The E2E walk asserts that toggling the mode changes the review
  digest on screen, so the two projections cannot silently be the same transaction under two names.
  If a third mode is ever added the composition cost stays linear in modes, which is acceptable;
  a mode that required its own registry read would change that calculus and should be reconsidered
  then.

## D-103 — Promotion writes one exact project-root checkout, validates twice and commits without push

- **Decision:** the configured installation's normalized absolute project root is the explicit
  writable checkout for screens 43–46. Preparing screen 44 requires that checkout's exact tree
  digest to equal the synchronized approved-registry baseline. Confirming screen 45 re-reads the
  exact durable Candidate and approved baseline, revalidates under the reviewed policy, rereads and
  replans the checkout, and requires the new plan digest to equal screen 43's. It then drives the
  existing `project_promotion`/`validate_promoted_registry`/`finalize_promotion` path, validates the
  persisted readback, stages only the reviewed paths into an initially empty Git index and creates
  one deterministic local commit. The commit port has no push operation. A commit failure after the
  validated atomic write is reported as partial completion and says the reviewed changes remain in
  the checkout.
- **Status:** accepted.
- **Reason:** source-store state is a synchronized immutable observation, not a writable registry
  checkout, and the accepted configuration schema contains a registry source URL but no separate
  checkout path. The existing project root is already an explicit local root supplied to the shell;
  requiring its entire tree to match the synchronized baseline binds it safely without guessing a
  location or widening configuration during this slice. Screen 43 is composed earlier from machine
  state, so checking only its digest at confirmation would miss a moved Candidate, policy result,
  approved baseline or checkout. Pre-write projection validation keeps planning inert; locked
  compare-and-apply plus readback validation closes the final filesystem race. Refusing a nonempty
  Git index prevents AART from accidentally committing user work.
- **Consequence:** screen 44 is a projection of evidence already assembled outside drawing and
  writes nothing. Screen 45 is the first Maintainer screen that writes approved registry state, and
  its success reports both the resulting registry snapshot and local 40-hex Git revision. The local
  commit does not update synchronized source-store state and is not publication; canonical-branch
  integration remains external as INV-242 requires. A real temporary checkout proves the complete
  shell path with no configured remote. Launching AART outside the exact registry checkout produces
  a refusal rather than writing elsewhere. B-041 remains: local-origin Candidate provenance still
  needs an audit representation and is not disguised as a Git revision.

## D-104 — Registry recency is the audit snapshot chain, and the checkout is a separate observation

- **Decision:** screen 46 orders promotions newest-first by walking the registry snapshot chain
  backwards from the approved snapshot: every `PromotionAudit` names the snapshot its transaction
  started from and produced, audits sharing an after-snapshot are one transaction, and the walk is
  bounded at 50 transactions and stops on any cycle or gap. Registry validity is the named check
  that every approved version carries a promotion approval record. Working-tree state is a separate
  observation of the D-103 project-root checkout, compared against the approved snapshot through
  `source_snapshot_digest` — the whole synchronized tree, which is exactly the digest D-103
  requires a checkout to match before it may be promoted from. The audit chain head is read
  separately, through the now-public `registry_state_digest` (published `artifacts/` and
  `references/` content only), because that is the digest space promotion audits name; comparing a
  working tree in that space made a correct checkout read as diverged, which the composition E2E
  caught. That checkout is observed only when exactly one registry is configured; otherwise it is
  reported as unobserved rather than attributed to a registry it may not belong to. A promotion
  moves the checkout, so the configured action handler recomposes the Maintainer views after a
  successful commit exactly as it does after a Source Sync.
- **Status:** accepted.
- **Reason:** no promotion record carries a clock, and stamping one at read time would make the
  order a property of when a Maintainer looked rather than of what happened; the chain is already
  durable, reproducible evidence. A published version nobody approved is precisely the failure
  registry validity exists to catch, and the audit records are the only supported way to read
  approval back. Synchronized source-store content is an immutable record of what the registry
  published, so answering "does my working tree still match" from it would answer a different
  question. Digesting published content rather than the whole tree lets a Maintainer be told the
  checkout still holds the approved artifacts while metadata is being rewritten.
- **Consequence:** screen 46 composes once outside drawing from evidence already read, and drawing
  it opens no file. After a D-103 local commit the checkout is legitimately ahead of the
  synchronized approved snapshot, and the working-tree line says so rather than calling it an
  error. Screen 45 keeps its receipt on screen, so Enter there means "confirm" only while an action
  is pending and "go on to the registry" once the write happened. Attributing a checkout per
  registry in a multi-registry installation is B-042.

## D-105 — Screen 47 projects what is selectable; the transaction is planned at action time

- **Decision:** screen 47 is a projection of the selectable set per registry, composed once outside
  drawing: promotability is read off the validation run screens 38–40 showed rather than re-derived,
  Candidates scanned for another registry are not offered at all, and a Candidate the run refused is
  listed by name with its reason rather than omitted. Selection uses the reducer's existing typed
  `selection`, with `Space` as the accepted Maintainer shortcut. The bulk transaction itself is
  prepared at action time from that selection, not while drawing.
- **Status:** accepted.
- **Reason:** a bulk plan depends on which subset is selected, so precomposing one is impossible
  without enumerating subsets and composing one while drawing would break the boundary every other
  CP-14 screen holds. A transaction has exactly one target registry, so offering Candidates of
  another registry would create a selection that can only ever be refused. "Not in the list" and
  "does not exist" look identical on screen, which is why an excluded Candidate is named.
- **Consequence:** screen 47 draws without opening a file and without judging anything itself, and
  `MaintainerViews.bulk_promotions` carries one selectable set per configured registry. `Enter` on
  screen 47 requests `BULK_PROMOTION`, which is refused outright while the selection is empty. Its
  one forward route is screen 44, not screen 43: a bulk selection has no single-Candidate diff to
  open, so the transaction goes straight to the validation screen a single promotion is also
  reviewed on, and screen 45 commits it. The configured handler re-checks at action time that the
  confirmed selection is still a subset of what screen 47 composed, and declines with "the
  selection changed after screen 47 was composed" rather than promoting something nobody ticked.

## D-106 — One reviewed transaction carries a set of promotions, not one

- **Decision:** `PreparedCandidatePromotionTransaction` carries `promotions: tuple[...]` rather than
  a single promotion, `plan_promotion_transaction` plans the whole set through the existing
  `plan_bulk_promotion`, and `prepare_promotion_transaction` prepares it; the single-Candidate
  functions are the one-element case of the same path rather than a separate one. Confirmation
  reads the approved baseline once and then rechecks every Candidate the transaction carries.
  Screens 44 and 45 carry a tuple of Candidates, each with the validation-report and
  effective-policy digests that approved it.
- **Status:** accepted.
- **Reason:** bulk promotion is one transaction, which is exactly what a loop over single
  promotions is not: each iteration would take its own registry snapshot, write its own commit and
  be able to half-succeed, leaving the registry in a state no review ever described. Two prepared
  transaction types would have meant two review paths and two chances for them to diverge. The
  approved baseline is read once because every member must be prepared against the same one;
  reading it per Candidate would let one transaction assemble members against two registries.
  Evidence stays per Candidate because each is approved by its own run and policy result, and one
  summarized pair of digests could not be traced back through the transaction.
- **Consequence:** the single-promotion flow is unchanged in behaviour and its execution now reads
  `approved` before `candidate`, which its port-order tests state explicitly. A transaction whose
  plan carries a Candidate the review never saw is rejected by construction. Screen 45's commit
  subject names the artifact for one Candidate and the count for several. The composition E2E
  proves the whole route end to end over a real Git checkout: two ticked Candidates reach the
  registry as one commit, one registry snapshot and one working tree with nothing left uncommitted.

## D-107 — Promotion audit provenance discriminates Git revisions from local snapshot digests

- **Decision:** `PromotionAudit.source_provenance` is a frozen discriminated value. A
  `git-revision` carries only a 40-hex `git_revision`; a `local-snapshot` carries only a canonical
  SHA-256 `snapshot_digest`. New canonical audit JSON writes a `source_provenance` object with
  exactly the fields for its kind. The reader also accepts the canonical legacy `source_revision`
  shape when and only when its value is a Git revision; a `local:<sha256>` value in that legacy
  field is rejected. Single and bulk planning construct this value from the Candidate's already
  validated immutable Source pin before entering the existing one-transaction planner.
- **Status:** accepted; closes B-041 and completes CP-14 step 5.
- **Reason:** a Git revision and a filesystem snapshot digest identify different things. Allowing
  both through one text field would make local provenance look like a commit and would leave future
  readers guessing which validation rules apply. Keeping separate fields behind an explicit kind
  makes the impossible combinations unrepresentable. Existing Git audit history is durable under
  INV-229, so changing the writer cannot make the old canonical record shape unreadable.
- **Consequence:** the by-name local promotion refusal is removed from both the single wrapper and
  the transaction planner; neither path loops, and mixed Git/local members still produce one bulk
  plan and one registry snapshot. A filesystem-backed Source fixture now uses a filesystem source
  location, and direct tests prove screen 43 is plannable and the audit holds a typed local digest.
  A live temporary installation proves local Source sync, validation, promotion, persisted registry
  validation and one clean local Git commit. Rebinding retained versions remains unchanged, so the
  pre-existing approved version and the local promotion remain readable together (D-089/B-037).

## D-108 — Candidate lifecycle joins durable history to exact registry evidence

- **Decision:** screen 48 walks the active Candidate's exact predecessor chain from durable
  Candidate history and treats promotion as proven only when one registry version and one promotion
  audit both match the Candidate ID, target coordinate, input/payload/canonical digests, typed Source
  provenance and promotion mode. Candidate state alone never proves promotion. For the one-registry
  configuration D-103 supports, the locally committed checkout is the evidence source so a promotion
  is visible before external publication; otherwise the synchronized registry observation is used.
- **Status:** accepted.
- **Reason:** Candidate review state and approved registry state are deliberately different values
  (INV-199). A stored `PROMOTED` state with no matching registry record is an assertion, while D-089
  legitimately rebinds old version records to the newest registry snapshot and therefore prevents
  historical audit matching from depending on the version record's current snapshot field.
- **Consequence:** the lifecycle reports unavailable, unverified and not-promoted separately; it
  retains an earlier exact promotion when a later Source revision creates a Changed Candidate. The
  projection has no IO or clock, and screen drawing opens no file.

## D-109 — Provenance is projected from compiler output and cross-checked at the domain boundary

- **Decision:** screen 49 reads the canonical package provenance produced by the author compiler,
  cross-checks its Source URL, Source kind, immutable pin, manifest path, input digest and importer
  identity/version against the Candidate's domain provenance, and refuses disagreement. Git and
  local provenance retain the distinct D-107 fields. Payload paths are every canonical regular file
  below `payload/`; warnings remain ordered compiler output.
- **Status:** accepted.
- **Reason:** showing only the Candidate's summary metadata would omit the importer and exact shipped
  paths, while trusting two independently carried provenance records without comparing them could
  present a hybrid record that never existed. The canonical compiler result already contains every
  accepted field for this screen.
- **Consequence:** screen 49 is a pure projection composed once with the rest of Maintainer state.
  It never labels a local snapshot digest as a Git revision and never reads a Source while drawing.

## D-110 — Version conflict is a refusal view, never an in-place repair path

- **Decision:** screen 50 exists only for an immutable coordinate/version collision. When the exact
  approved registry version is available it shows the published and Candidate input, payload and
  canonical digests side by side; when it is unavailable, the durable
  `registry-version-immutable` Candidate finding keeps the refusal visible but explicitly says the
  exact published evidence is unavailable. Both outcomes prescribe a new version and expose no
  mutation action for the published coordinate.
- **Status:** accepted.
- **Reason:** INV-203 and INV-239 forbid different content under a published coordinate/version.
  Hiding the conflict when the current registry read is unavailable would erase a durable finding;
  inventing the published digests would be worse. A matching exact Candidate is not a content
  conflict and receives no screen-50 view.
- **Consequence:** production composition compares against `ApprovedRegistryState.versions`, while
  rendering is read-only. A contradictory durable conflict finding plus an exact matching approved
  version is rejected as inconsistent state instead of choosing whichever record is convenient.

## D-111 — Screen 53 edits the one typed filter, and its rows are addresses rather than text

- **Decision:** the Product Specification names four Candidate filter facets — status, kind, Source
  and target registry — and `MaintainerCandidateFilter` gains the two it lacked: `kinds` is typed
  `ArtifactKind` and `registries` is a tuple of aliases. Closed sets stay typed (`states`, `kinds`)
  and open sets stay strings (`sources`, `registries`), matching what each facet actually is. Screen
  53's rows are `"<facet>:<value>"` pairs read back by `parse_candidate_filter_row`, and the reducer
  toggles the parsed facet through one `toggled(facet, value)` entry point rather than four. The
  offered values come from every composed Candidate, not from the already narrowed list. Each option
  states what choosing it would leave, measured by applying that one value to the rest of the
  current filter. `f` opens screen 53 from screen 35; `Space` and `Enter` toggle a row there and
  put nothing in `selection`.
- **Status:** accepted; completes the filter half of CP-14 step 6.
- **Reason:** a second filter model was explicitly ruled out by D-098, so the two missing facets
  belong on the value screen 35 already obeys. Rows parse back for the same reason screen 38's do
  (D-100): a row is an address the reducer resolves, never a string a renderer takes apart. Offering
  values from the narrowed list would make a row vanish the moment it was ticked, so it could never
  be unticked. Counting what an option would leave — rather than how many carry it — is what makes a
  narrowing that selects nothing legible before it is applied instead of discovered as a blank
  screen 35. Ticking a filter row must not reach `selection`, because `selection` is what every
  action reads and a filter is not a chosen artifact.
- **Consequence:** `f` now means two things across two screens: the raw file diff on screen 37 and
  the filters on screen 35, each meaning what its own screen is about; the characterization test
  that pinned `f` as inert on screen 35 was corrected to state the new behaviour rather than
  relaxed. Drawing screen 53 opens no file and composes nothing beyond the Candidates already read
  once. A facet value the composed Candidates cannot address is skipped rather than drawn as a row
  that would do nothing.

## D-112 — Collections are reached from the Candidate surface, not from a place of their own

- **Decision:** `c` on screen 35 opens screen 51. Screens 51 and 52 already had projections, a
  renderer, validation and durable composition, but no route: every test entered by constructing a
  session already on screen 51. The navigation graph already accepted screen 35 → screen 51, so the
  missing piece was the key, and `c` on the Candidate list is it.
- **Status:** accepted; with the screen-51/52 walk this completes CP-14 step 6.
- **Reason:** the Product Specification says "Collections are candidates too", which puts them on
  the Candidate surface rather than in a separate branch of the dashboard — and the accepted screen
  30 panel lists Overview, Sources, Candidates and Registry with no Collections entry, so adding one
  there would have invented a surface the specification does not describe. The accepted contextual
  shortcut table names no Collections key, but it also names none for screens 46, 47 or 50, which
  are reached by navigation; it constrains what the keys it lists mean, not what may exist. `c` was
  unclaimed on every screen.
- **Consequence:** a Collection authored in a Source now reaches screen 52's resolution through the
  production shell — one compile, one durable scan, one route. The E2E goes through
  `compile_author_source` rather than `compile_author_snapshot`, which is the boundary that carries
  Collections and the one production Source Sync already uses; a fixture built on the artifacts-only
  boundary would have proven nothing about Collections.

## D-113 — The legacy curses wizard entry point is removed; the text route is not

- **Decision:** `_run_curses` (754 lines) is deleted from `agent_artifacts/tui.py`, together with
  the two setup shims it was the sole caller of (`_legacy_setup_stage_failure`,
  `_run_post_install_setup`) and the five tests that existed only to drive it
  (`tests/tui_fallback_boundary_test.py` ×3, `tests/tui_curation_test.py` ×2, plus the two flow
  tests in `tests/tui_wizard_curses_test.py`). `run()` and `_run_text` are untouched, and the
  wizard's curses *primitives* (`_curses_onboarding`, `_curses_singleselect`, `_curses_multiselect`,
  `_curses_install_mode`, `_curses_review`, …) stay: they are still composed by the surviving
  wizard stages and still covered by the 36 remaining tests in `tests/tui_wizard_curses_test.py`.
- **Status:** accepted; the first removal of CP-14 step 7, and closes B-039's `_run_curses` half.
- **Reason:** B-039's rule is that nothing is removed before a public-flow test proves the canonical
  path already carries it. Both halves were already true and neither needed a new test.
  `run()` composes `_canonical_consumer_actions` and calls `run_consumer` before any wizard
  composition (B-025/D-087), so no terminal reached `_run_curses`. ERR05 — the one condition under
  which a text fallback is legitimate — is pinned on the canonical `run()` by
  `test_run_starts_the_text_wizard_once_when_curses_is_unavailable`,
  `test_run_never_restarts_the_application_after_an_internal_defect` and
  `test_unexpected_terminal_probe_error_is_not_silently_downgraded_to_text`. Three duplicates of
  those were written against the entry test and then reverted rather than left as second coverage of
  one behaviour.
- **Consequence:** the wizard can no longer be entered as a whole; only its widgets remain, as
  widgets. `tests/tui_fallback_boundary_test.py` now holds ERR05 against the canonical application
  alone, which is what its class docstring says. The text route stays: no-TTY is a supported
  environment, not a broken one. `_dispatch_result` survives this removal — it lost its last
  production caller here, but `tests/tui_consumer_text_test.py` still patches it to prove the
  canonical text route does *not* dispatch legacy commands, so it is retired with the command
  dispatch path rather than with the wizard shell (B-039's remaining half).

## D-114 — Screen 21 lists the configured sources, and a native Source says why it offers nothing

- **Decision:** `read_consumer_offers` now projects the catalog it already read through
  `project_registries` and carries the result on `ConsumerOffers.registries`; `screens_from` takes
  them and `LocalConsumerActions.source()` passes them, so screen 21 draws the configured sources of
  the machine the shell was composed over. `RegistryView` gains a typed `is_registry`, set in the
  projection from `SourceKind.REGISTRY_GIT`. A row that is not a registry says "An authoring Source,
  not a registry." and "Its content is offered here once a maintainer promotes it into a registry.",
  and its `actions` are `("details",)` rather than `("details", "sync")`. The dashboard's
  `registry_count` counts the registries among the configured sources rather than all of them.
- **Status:** accepted; closes B-038's screen-21 half, which was its remaining CP-14 dependency.
- **Reason:** screen 21 was reachable and empty in the composed application for the same reason
  screens 02–04a once were: nothing on the composition path projected the configured sources, so
  `machine.registries` stayed the empty default `assemble_consumer_machine` assembles it with. A
  machine with two configured registries drew an empty screen 21 and a dashboard reading
  "0 registries". Which sources are configured is *configuration* rather than durable machine
  evidence, which is why it arrives through the offers seam — already read once at composition —
  instead of being read a second time by the machine.
  The B-038 half is INV-026: a Marketplace projects configured registries, so an enabled
  `SOURCE_GIT` or `SOURCE_LOCAL` contributes health and offers nothing. Drawing that as a bare
  "0 artifacts" describes a correct state as a fault, and advertising a sync that "refreshes
  Marketplace availability" names an effect that source cannot have. `is_registry` is decided in the
  projection rather than by a renderer splitting `kind`, for the reason D-100 and D-111 give: a
  screen resolves typed values, it does not take strings apart.
- **Consequence:** the count on screen 01 and the list on screen 21 now agree with the configuration
  on disk, over the production composition rather than a `screens_from` call a test made. The
  characterization test that pinned `("details", "sync")` on *every* row was corrected to state what
  each kind of row now offers rather than relaxed. `machine.registries` remains the fallback when no
  registries are passed, so nothing that composed screens without them changes. B-038's other half —
  removing the legacy route's ability to install directly from a native Source — is unchanged and
  still sequenced behind its own public-flow evidence.

## D-115 — The text fallback is the canonical application, not a second product

- **Decision:** `run()` now composes `_canonical_consumer_actions` **once** for whichever terminal
  answers, and a terminal that cannot host curses runs `run_consumer_text` — the same screen source,
  reducer, action handler and settings writer the curses route runs, over a `_TextTerminal` that
  draws with `write` and reads with `read`. The entire legacy tail of `run()` is gone: no
  `_runtime_source_stage_context`, no `ConsumerServiceFactory`, no `_run_text` call. A line editor
  has no arrow keys and no bare Escape, so `_TextTerminal` names those (`up`, `down`, `enter`,
  `esc`/`escape`, `back`/`backspace`, `space`), treats a single-character line as that character and
  a blank line as Return, and gives an unknown word no meaning at all. On `EOFError` it answers `q`
  once and `y` thereafter.
- **Status:** accepted; the enabling step for the rest of CP-14 step 7.
- **Reason:** step 7's remaining removals — `consumer/application.py`, `lifecycle/*`,
  `setup_engine/*`, and B-038's legacy direct-install-from-a-native-Source — are all reachable
  only through `_run_text`, which is built on `ConsumerApplicationService` and through it on that
  whole stack. So none of them could be removed while `_run_text` was the only thing the text route
  had; the blocker was not evidence but a missing replacement. ERR05 permits a text fallback for
  exactly one condition, the terminal cannot host curses. It says nothing about the *product*
  changing, and a no-TTY environment — CI, a pipe, a dumb terminal, SSH without a pty — was getting
  a different application from the one a terminal gets. The shell already takes its terminal as a
  port of two methods, so the replacement is an adapter rather than a second frontend.
  An unknown word means nothing rather than its first character, because taking the "d" out of
  "delete" would act on a key nobody pressed. EOF answers the discard prompt because a pipe that
  ends mid-selection would otherwise redraw that prompt forever.
- **Consequence:** `_run_text` and everything below it now have no production caller — the same
  position `_run_curses` was in before D-113, and the removal follows with the same evidence
  discipline. The ERR05 tests in `tests/tui_fallback_boundary_test.py` were retargeted at
  `run_consumer_text`: "degrades exactly once", "a defect never restarts the application as text",
  "an unexpected probe error is not silently downgraded" all now hold against the canonical route,
  and the assertions that had become vacuous (patching a `_run_text` nothing calls) were restated
  rather than left standing. `run()` composing once is now pinned: composing again on the
  degradation path would open the same local state twice.

## D-116 — The legacy text wizard shell and everything only it reached are removed

- **Decision:** `_run_text` (325 lines) is deleted, together with `_runtime_source_stage_context`,
  `_dispatch_result` and the 26 further private definitions in `agent_artifacts/tui.py` that became
  unreferenced once it was gone — `_run_canonical_maintainer_text`, `_run_maintainer_text`, the
  `_prompt_*` family, the `_curses_source_*` maintenance screens, the stage-failure helpers, and the
  rest: 1,546 lines out of `tui.py`. With them go the tests that existed only to drive it —
  `tests/tui_curation_e2e_test.py` and `tests/tui_vendoring_test.py` whole,
  `SourceLifecycleTextTests`, two curation tests and six wizard-flow tests in
  `tests/tui_consumer_text_test.py` — about 2,200 lines in all. The module docstring, which still
  described "two front-ends, one body", was rewritten to say what the module is now.
- **Status:** accepted; the removal D-115 unblocked.
- **Reason:** D-115 put the canonical application on the text route, which left `_run_text` in
  exactly the position `_run_curses` was in before D-113: defined, exercised by tests, reachable
  from nothing. Every capability the removed tests pinned is carried by a public flow with its own
  evidence, which is what D-091 requires and what was checked before each removal rather than
  assumed:
  - **scaffolding** (`tests/tui_curation_e2e_test.py`) → `aart registry scaffold`, proven by
    `tests/registry_init_scaffold_test.py` and `tests/registry_cli_integration_test.py`;
  - **source add / remove / sync / resubscribe** (`SourceLifecycleTextTests`) → the `aart source`
    command surface, proven by `tests/source_cli_command_test.py`'s 23 tests, which pin the same
    review-then-finalize semantics the wizard tests did;
  - **vendoring** (`tests/tui_vendoring_test.py`) → the flags half of the parity it was testing;
    with one front end left, parity has nothing to compare, and the assessment rendering it checked
    is pinned by `tests/registry_vendor_assessment_test.py`;
  - **the ERR04 legacy install state** → `install-state-legacy` is asserted in four other test
    modules;
  - **ERR06 refusals and the setup queue** → the canonical shell carries a refusal as a drawn
    notice, proven by `tests/consumer_application_e2e_test.py`.
  The removal was driven by a reference sweep repeated to a fixpoint rather than by hand, because
  removing one orphan orphans its callees, and a hand-picked list would have left a tail.
- **Consequence:** `tui.py` falls from 5,705 lines to 4,262. `lifecycle/*` and `setup_engine/*` are
  now reachable only through `consumer/*`, and `curation/*` only through `cli.py` and
  `commands/registry.py` — the public flag-mode commands, which is where they belong.
  `ConsumerApplicationService` survives because the curses wizard *stages* still compose it and 36
  tests still cover them; those stages, and then `consumer/application.py` with `lifecycle/*` and
  `setup_engine/*` behind it, are the next removal. Two entry tests that asserted "not the legacy
  wizard" were restated as "the canonical application and nothing else", because a comparison to
  something that no longer exists pins nothing.

## D-117 — The wizard front-end is removed, and the stack behind it is not legacy

- **Decision:** the last of the legacy wizard front-end is deleted: `_run_user_curses_wizard`,
  `_run_user_text_wizard`, `_prompt_curation_request`, the `_curses_source_*` maintenance screens
  with `_selected_source_row`, `_offer_usage_report`, `_run_canonical_setup_queue`,
  `_is_canonical_maintainer_workspace`, `_type_rank`, and the 22 further private definitions that
  became unreferenced once they were gone — 1,515 lines out of `agent_artifacts/tui.py`, which
  falls from 4,262 to 2,747. `tests/tui_curation_test.py` and `tests/reporting_tui_test.py` are
  deleted, `SourceLifecycleCursesTests` and `CursesWizardFlowTests` with them.
  **`consumer/application.py`, `lifecycle/*` and `setup_engine/*` are not removed, and are not
  removable:** `NEXT.md` recorded that nothing but the wizard reached them, and that is wrong.
- **Status:** accepted; corrects the removal plan recorded under D-116.
- **Reason:** `agent_artifacts/commands/marketplace.py` — the public `aart marketplace
  install|update|uninstall|setup` command — composes `ConsumerApplicationService` directly, and
  runs the setup queue through it (`_run_setup_queue`, `service.setup_queue`,
  `service.finalize_setup_queue`). `tui_marketplace.py`, which the canonical shell imports, takes
  `LifecycleItem` from `lifecycle/model.py` and `InstallMode` from `installation/model.py`. So the
  stack under the wizard is load-bearing for a public flow, exactly as `installation/*` already
  was: it goes by symbol, if at all, and not by package.
  Each removed test's capability was checked against a public flow before the removal, as D-091
  requires:
  - **`registry init`'s default compatibility window** (LAF-90, `tests/registry_cli_test.py`) was
    the one assertion the wizard held alone — `RS-02`'s loop covers every registry action *except*
    `init`, because `init` is the action that owns the two flags. It is restated against the CLI
    parser's own defaults and verified red against a dead literal window;
  - **the usage-report offer** (`tests/reporting_tui_test.py`) → `_render_cli_reporting` in
    `commands/marketplace.py`, which had **no** test at all. Consent defaulting to no, the exact
    payload being readable before anything opens, and a reporting failure leaving the marketplace
    outcome unchanged are privacy boundaries, so they were carried to the reachable surface as
    `tests/reporting_cli_offer_test.py` and verified red against a consent default of yes;
  - **workspace classification** (`tests/tui_curation_test.py`) → the canonical planner requires
    the exact `aart-registry.json` marker and refuses a snapshot without it, proven by
    `tests/registry_maintenance_edges_test.py`. A retired `registry.json` is not translated into it,
    which is the same statement the removed test made;
  - **the maintainer action menu's no-commit-no-push label** → stale rather than carried: the
    canonical Maintainer flow *does* commit locally and never pushes, proven by
    `tests/maintainer_composition_e2e_test.py::test_validated_promotion_is_committed_locally_and_never_pushed`;
  - **source maintenance** (`SourceLifecycleCursesTests`) → the `aart source` surface, 23 tests;
  - **ERR06 refusal-as-a-record and quit-confirms-a-basket** (`CursesWizardFlowTests`, the
    `_run_user_text_wizard` tests) → the canonical shell draws a refusal where it was asked, keeps
    the application up and clears the review digest
    (`tests/consumer_application_e2e_test.py::ConsumerApplicationRefusalTest`), and asks before
    discarding a selection on quit (`tui_consumer.py`, `tests/consumer_text_terminal_test.py`).
- **Consequence:** the wizard's *widgets* survive only as far as their tests hold them; 571 lines of
  `tui.py` are still production-orphaned and are the next sweep. `_canonical_setup_run` and
  `_complete_canonical_consumer_action` are **deliberately retained** — see D-118.

## D-118 — The canonical consumer shell runs no setup queue and offers no usage report

- **Decision:** record this as a gap rather than ratify it by deleting the code. The setup and
  reporting completion the wizard performed — `_canonical_setup_run` and
  `_complete_canonical_consumer_action` — is kept in `agent_artifacts/tui.py`, production-orphaned
  and pinned by tests, as the material the canonical route will be wired to. It is promoted to the
  critical path as **B-044**.
- **Status:** accepted; the work itself is not done here.
- **Reason:** `io/consumer_actions.py` contains no reporting and no setup: `_execute_installation`
  calls `complete_configured_installation`, which reaches neither. So since D-115 put the canonical
  application on both terminal routes, an artifact installed from the TUI that declares setup
  requirements lands unconfigured, and no usage report is offered. The Product Specification names
  interactive setup as work AART performs, and screen 09/11 summarize outcomes as "configured MCP
  servers, isolated environments ... securely stored credentials" — so this is a mandatory
  invariant a shipped path no longer satisfies, which is what makes it critical rather than backlog.
  ~~The public `aart marketplace install` carries both and is unaffected.~~ Corrected by
  **D-120**: that holds only for a direct or local Selection. An approved registry coordinate
  reaches the same configured seam and skips setup identically.
  Deleting the two helpers as orphans would have been the mechanical reading of D-091 and the wrong
  one: they are not legacy authority to strangle, they are the only implementation of a capability
  the replacement lacks.
- **Consequence:** `ConsumerApplicationService` stays reachable from `tui.py` as well as from
  `commands/marketplace.py`. Closing B-044 means giving the canonical action handler its own setup
  and reporting completion, at which point these two helpers are replaced rather than deleted.

## D-119 — The internal-failure record names the boundary `run` actually reached

- **Decision:** `InternalFailureContext.stage` accepts a `CanonicalBoundary` —
  `"compose" | "curses" | "text"` — and defaults to `"compose"`; `run()` sets `"curses"` or
  `"text"` before starting each terminal. The dead `capture(session, ...)` is removed. An
  unexpected exception from `_canonical_consumer_actions` is now caught and rendered through
  `internal_failure_lines` rather than propagating.
- **Status:** accepted.
- **Reason:** the field was typed `WizardStage` and set only by the wizard, so after D-117 the live
  route could report exactly one value — `stage: onboarding` — naming a screen that no longer
  exists and sending anybody who reported it looking in the wrong place. What `run` knows is
  whether it was still composing or had handed the application to a terminal, and which terminal,
  and those are reproduced differently. The composition reads local state, so an untyped defect
  there carries paths and file contents in its message; `internal_failure_lines` exists to withhold
  exactly that, and letting the exception past `run` bypassed it.
- **Consequence:** `tests/tui_fallback_boundary_test.py` asserts the three boundaries produce three
  different records, and the assertion that read `stage: onboarding` now reads `stage: curses`.

## D-120 — A setup declaration is added at package time, and the seam that skips it is shared

- **Decision:** the B-044 fixture puts a setup-declaring artifact into a published registry by
  adding the declaration to the *compiled* package rather than to the authored manifest, and
  recompiling: `AuthoredSetup` and `_with_setup` in
  `tests/configured_installation_draft_e2e_test.py` write `artifact.json`'s `setup` reference,
  `setup/installer.json` and `SETUP.md` into the canonical entries and call
  `compile_native_package` over the result, which then goes through the whole real promotion
  transaction. The characterization built on it,
  `tests/configured_setup_gap_test.py`, asserts the gap on **both** front ends rather than on the
  shell alone.
- **Status:** accepted.
- **Reason:** two things were established by trying to build the fixture. First, the authoring
  format has no setup section at all, so a setup declaration genuinely does enter at packaging;
  modelling it that way is where it actually happens, not a shortcut around the compiler, and the
  recompile is what proves the declaration valid rather than merely well-formed. Second, and this
  corrects D-118: `aart marketplace install` skips setup too. Both front ends reach installation
  through `complete_configured_installation` — the command via `_configured_lifecycle`, the shell
  via `_execute_installation` — and setup runs only on the legacy path, which
  `_configured_registry_selection` selects by returning `None`, and it returns `None` only for a
  direct or local source. The observed CLI install of a setup-declaring registry Skill reports
  `session_status: succeeded` with no `setup` key and no diagnostic, and the configuration file the
  recipe declares is not written.
- **Consequence:** B-044 is one fix at one seam, not two wirings, and the reporting half is subject
  to the same reading. There is also no operator recovery today: `aart marketplace setup` run
  afterwards refuses with `registry company has invalid root manifests`, because it resolves through
  the legacy catalogue, which reads root manifests a promoted registry snapshot does not carry.
  Two constraints bound any future fixture: a setup declaration's platforms must be a subset of the
  artifact's, and `setup.py:562` requires the recipe's own `platforms` to be exactly `['darwin']`,
  so an artifact declaring no `compatibility.platforms` cannot declare setup.

## D-121 — The working setup route is proven where it works, on the platform it works on

- **Decision:** `tests/marketplace_lifecycle_e2e_test.py::DeclaredSetupE2ETest` proves declared
  setup end to end from the CLI over a real machine, on the legacy native-local-source route, and
  is `skipUnless(darwin)`. The fixture is the shared native source copied writable and taught to
  declare setup — `setup` on `artifact.json`, `setup/installer.json` beside the payload, a
  package-root `SETUP.md` — so it is compiled, validated and synchronized as it stands.
- **Status:** accepted.
- **Reason:** B-044 characterizes an absence, and an absence is only legible against the presence.
  Nothing proved the presence: the only setup coverage over a real machine was the empty case, and
  the rest was unit-level against a hand-built install state, which is how a draft that hardcoded
  `TrustClass.COMPANY_REVIEWED` into the policy check passed 3,216 tests. Applying that same
  mutation now fails two of these four. The platform skip is honest rather than a gap: `setup.py:562`
  requires a recipe's `platforms` to be exactly `['darwin']`, so on any other platform the run is
  refused for the platform before it reaches a single one of these boundaries, and
  `canonical_setup_application_test.py` already pins that refusal at unit level.
- **Consequence:** the four gates on the route are now asserted rather than assumed — `install`
  names the setup it did not run, an unreviewed source refuses without explicit authorization, an
  authorized plan applies nothing until its effects are separately approved, and only both answers
  together write the managed block. The first of those is the sharpest statement of B-044: the same
  install through the configured seam emits no `setup` key at all.

## D-122 — The canonical receipt names the immutable object the installation came from

- **Decision:** `PlacedArtifactReceipt` and `InstallationReceipt` carry an optional
  `object_digest`, populated by `intended_placement_receipt` / `intended_receipt` from the
  `RegistryArtifactVersion` the Selection resolved. A record written before the field existed reads
  back with `object_digest is None` rather than being refused or defaulted.
- **Status:** accepted.
- **Reason:** the receipt recorded what the effects left behind — the delivered tree, its digest,
  the harness that reads it, the root the payload was copied out of — but not which package in the
  object store those bytes came from. That gap is the first thing B-044 hits: setup is declared on
  the package manifest, and `setup_engine/application.py::_prepare_setup_object` finds it by
  loading the object by digest, which is why the legacy route can run setup off `ArtifactEvidence`
  and the canonical route cannot. It is not only setup — reconciling a repair against the payload
  digest alone cannot tell one package from another that happens to deliver identical bytes.
  Nothing had to be derived: the digest is already in hand where the receipt is written.
- **Consequence:** the durable store gains a field, so back-compatibility is a correctness
  requirement, pinned by a test on each shape that an older document still reads and reads as
  unknown. Optional is the honest shape for the same reason: an installation whose object nobody
  wrote down is unknown, and inventing a default would put a dangling identity on a real
  installation. `tests/installed_object_identity_test.py` asserts the recorded digest resolves to a
  real object in the store whose manifest is the installed package's — a digest nothing answers to
  would read as an identity and behave as a dangling pointer. This is step (2) of B-044's recorded
  ordering; it does not yet run setup, and B-045 (the canonical seam registers no CAS reference at
  all) remains separately open.

## D-123 — The configured seam names the setup it does not run, before it can run it

- **Decision:** `complete_configured_installation` reads the objects it just recorded, and carries
  what they declare as `CompletedConfiguredInstallation.pending_setup`. `aart marketplace install`
  emits it as an additive `pending_setup` key and renders it; the persistent shell carries it on
  `ConsumerScreens` and draws it under screen 11's success. `agent_artifacts/application/
  installed_setup.py` holds the pure value and `agent_artifacts/io/installed_setup.py` the reading.
- **Status:** accepted.
- **Reason:** the legacy route's install already names the setup it did not perform — D-121's first
  gate — and the configured route said nothing at all. Silence is the worse of the two failures:
  an operator who is told an artifact is installed and unconfigured has one step left, while one
  who is told the install finished believes a Skill is configured when it is not. It is also the
  first thing the receipt's object identity is spent on, and not scaffolding: setup is declared on
  the package manifest rather than on anything the plan carries, so "does this artifact declare
  setup" is answered by going back to the object the receipt names (D-122) — which is exactly the
  first half of `_prepare_setup_object` for the canonical route.
- **Consequence:** the key is absent rather than empty when nothing declares setup, because an
  install that always carried it would read as "checked and found to need nothing", which is a
  stronger claim than this seam makes. The reading is done after completion from the durable
  record rather than from the plan, so it is a statement about the machine and not the action
  repeating its own intention. A receipt that names no object is passed over in silence; an object
  a receipt names and the store cannot produce is an error, because reporting "nothing to
  configure" there would turn a broken store into a clean bill of health. Half of
  `tests/configured_setup_gap_test.py` inverts: what it still characterizes is that the work is not
  done, and `tests/configured_setup_report_test.py` owns the assertions that moved.

## D-124 — Which store says an artifact is installed is separated from what the object contains

- **Decision:** `setup_engine/application.py::_prepare_setup_object` no longer reads the
  install-state manifest or resolves the legacy catalogue. Those became
  `_install_state_subject`, which returns a typed `_InstalledSubject` (the install-state paths, the
  `InstallationRecord` and its `MarketplaceItem`); `_prepare_setup_object` takes that subject and
  validates the object it names. `prepare_setup_attempt` composes the two. No behaviour changed;
  the existing 27 engine tests and the darwin end-to-end route are the characterization.
- **Status:** accepted.
- **Reason:** the two answer different questions and are answered by different stores. *That this
  artifact is installed here* is a durable record, and which store holds it is a property of the
  route that installed it — the legacy install-state manifest today, the canonical receipt store
  for whatever the configured seam installs. *What the installed object contains* is the same
  question either way, asked of the same content-addressed store. Until this split they were one
  function, which is why B-044 reads as "the engine cannot be reached" rather than "the engine
  needs a second subject": every canonical fact was blocked behind a legacy read.
- **Consequence:** the canonical route now has exactly one seam to fill rather than a function to
  fork. What remains for it is recorded as B-044 step (3b), and three things are known to be
  needed: the engine's marketplace evidence has no canonical equivalent (`resolve_artifact` cannot
  read a promoted registry snapshot, which is the same reason `aart marketplace setup` refuses with
  `registry company has invalid root manifests`); `_preconditions_current` re-resolves through that
  same catalogue at finalize time; and `persist_setup` records that setup ran by replacing
  `setup_state_ref` inside the install-state record under its lock, which
  `setup_receipt.locate_setup_record` reads for `aart marketplace receipt show|verify|undo`.
  A canonical `InstallationRecord` is constructible from the receipt — `ArtifactEvidence` from the
  coordinate and the recorded `object_digest`, `SourceEvidence` from the configured registry source
  and its synchronized revision, and the required non-empty `effects` from the receipt's deliveries,
  which carry destination, kind and digest per harness. What is *not* constructible is a faithful
  `manifest_digest` cross-check: computing it from the same object the engine just loaded compares a
  value to itself. The canonical equivalent is an independent one — the object the approved registry
  publishes for this coordinate must be the object the receipt recorded — which `object_digest`
  binds the whole package by, manifest and recipe included.

## D-125 — The setup engine takes a subject port, not a marketplace catalogue

- **Decision:** `prepare_setup`, `prepare_setup_attempt`, `finalize_setup` and
  `execute_setup_queue` take a `SetupSubjectPort` — `(SetupRequest) -> Result[_InstalledSubject]` —
  in place of the `MarketplaceCatalog`. `install_state_subject(catalog, effective, location, ports)`
  builds the legacy one, and `consumer/application.py` passes it. `_preconditions_current` re-asks
  the port instead of re-resolving the catalogue and separately re-reading install state, so
  `_selected_state_matches` is gone. The subject carries the trust decision and the indexed setup
  declaration rather than a `MarketplaceItem`, which is all the plan ever read from it.
- **Status:** accepted.
- **Reason:** the engine had a hard dependency on the store that recorded the installation and on
  the catalogue that indexed it, and neither can answer for a canonical install: `resolve_artifact`
  cannot read a promoted registry snapshot, which is why `aart marketplace setup` refuses with
  `registry company has invalid root manifests`. A port is the honest shape because the answer
  genuinely comes from different places for different routes, and because the question is asked
  twice — once to plan, once at finalize to prove nothing moved — so it has to be re-askable.
  Folding the finalize-time record re-read into the same re-ask makes it one check where it was
  two, which is also why it cannot drift: the record the plan was bound to and the trust it was
  bound to are now proven current by the same call that established them.
- **Consequence:** no behaviour changed and the engine's tests are the characterization —
  the trust-downgrade, source-removed, capability-mismatch and missing-record cases all still fail
  where they failed before, now by passing a changed subject rather than a changed catalogue. The
  canonical route's remaining work is a second implementation of this one port plus a durable setup
  record it can own; nothing else in the engine needs to know which route installed the artifact.

## D-126 — The setup plan names the record that says an artifact is installed, not the store that holds it

- **Decision:** `CanonicalSetupPlan.install_state_path` / `install_state_lock_path` are renamed to
  `installation_record_path` / `installation_record_lock_path`. The digest input that derives
  `setup_state_ref` deliberately keeps its old JSON key, `install_state_path`, and carries a comment
  saying why.
- **Status:** accepted.
- **Reason:** those two fields are the last place in the engine that assumes which route installed
  the artifact. What `persist_setup` actually needs of them is narrower than their old names claim:
  the durable file that says this artifact is installed here, and the lock that guards it while
  setup is recorded. For a legacy install that is the install-state manifest; for one the configured
  seam made it will be the canonical receipt. Renaming them is the prerequisite for D-125's second
  port implementation, because `persist_setup` was hard-bound to install state by these names alone.
- **Consequence:** no behaviour changed — `setup_review_value` does not serialize either field, and
  the identity JSON keeps its key, so every `setup_state_ref` and every stored review digest is
  byte-identical to what it was. The key is *not* renamed with the field on purpose: it is a digest
  input, and the value it produces is the durable ref an already-configured installation's record is
  filed under, so renaming it would rename every existing setup record and make each one invisible
  to the run that looks for it.

## D-127 — Two shapes of setup-declaration evidence, not one optional field

- **Decision:** `InstalledSubject` (formerly private) carries
  `declaration: IndexedSetupDeclaration | ApprovedObjectIdentity` in place of
  `indexed_setup: IndexSetup | None`, and it names the durable record as `record_path` /
  `record_lock_path` rather than holding an `InstallStatePaths`. `_prepare_setup_plan` cross-checks
  the compiled recipe against the index's declaration for the first shape, and checks the loaded
  object's digest against the digest the approved registry publishes for the second.
  `InstalledSubject`, `SetupSubjectPort` and both evidence shapes are exported.
- **Status:** accepted.
- **Reason:** the plan required an index declaration to cross-check, which no canonical route can
  give honestly. A promoted registry snapshot *is* the package, so reading a declaration out of it
  and comparing it to the recipe compiled out of it compares a value to itself — which is exactly
  the shape of check that produced the hardcoded trust constant in the preserved draft. The
  independent question a snapshot can answer is which object the registry publishes for the
  coordinate, and that digest is compared against the one the durable installation record names, so
  the two values come from different documents. Making it a union rather than a second optional
  field means neither route can silently fall through the other's arm.
- **Consequence:** legacy behaviour is unchanged, including the `None` case — an index that declares
  no setup is still refused with the same message, which is now explicitly a declaration
  (`IndexedSetupDeclaration(None)`) rather than an absence. Three tests cover the new arm: the
  registry's object plans, another object is refused with "registry publishes", and the legacy arm
  keeps its own meaning. The subject no longer references `InstallStatePaths`, so nothing left in
  the engine names the store that recorded the installation.

## D-128 — Configured setup is a receipt-backed engine composition, followed by terminal-owned consent

- **Decision:** `io/configured_setup.py` is the configured implementation of the public
  `SetupSubjectPort` and setup persistence boundary. It reconstructs an `InstallationRecord` in
  memory from the canonical receipt, the synchronized configured source and the approved registry
  version; project destinations are relativized before becoming `EffectProof`s; trust is exactly
  `RegistryTrust.REGISTRY_REVIEWED -> TrustClass.REGISTRY_REVIEWED`; and declaration evidence is
  `ApprovedObjectIdentity` for the registry-published object. It never writes the retiring
  install-state manifest. `LocalConfiguredSetupAdapter.persist_setup` takes the receipt-side lock,
  writes the setup record, replaces the receipt's optional `setup_state_ref`, and moves the setup
  CAS reference as one compensated unit. Both receipt shapes keep older documents readable by
  treating absence of that pointer as unknown/not-yet-recorded.
- **Status:** accepted.
- **Reason:** the engine already owns recipe parsing, trust, policy, capability, object-identity,
  precondition and per-effect consent decisions. The configured route needed ports supplying real
  evidence, not a third planner. Re-asking the subject under the receipt lock gives finalize the
  same stale-review protection as the legacy record. A forced reference-write failure proves the
  receipt pointer and setup-state file return to their prior bytes.
- **Consequence:** configured `marketplace install|update` now prepare setup after the payload is
  durably recorded, and their parsers expose the same three independent setup authorizations as the
  legacy route. Omitting effect approval applies nothing and leaves `pending_setup`; explicit
  approval configures it. `marketplace setup` resolves canonical receipts before the legacy
  catalogue, so a declined configured install is recoverable. The persistent shell receives a
  typed completion from its action update; the IO handler accepts an injected completion factory
  and never imports the terminal module. The terminal adapter uses `draw(lines)` / `key()` and
  sends every key through `key_event`, with bracketed decisions completing on one key. It then
  reuses `_canonical_setup_run` and `_complete_canonical_consumer_action`, including exact redacted
  usage-report preview and default-no consent. Reporting failure remains advisory and cannot change
  the installation result. The bridge into those retained contracts is a real `ConsumerReview`:
  its documented sentinel is supplied only to the constructor, which immediately replaces it with
  the digest of the exact projected items; setup plans retain their own engine review digests.
  The three acceptance tests that assert setup *ran* are `skipUnless(darwin)`, for the reason
  D-121's `DeclaredSetupE2ETest` already carries: the seam takes its platform from `sys.platform`
  and a recipe may declare only `darwin`, so elsewhere the run is `unsupported` and the artifact is
  reported as still-pending setup with a retry command rather than as a failed install. That was
  measured by forcing the platform, not assumed.

## D-129 — The wizard surface in `tui.py` is removed by reachability, with every unheld assertion carried first

- **Context:** `NEXT.md` named an evidence-led orphan sweep of `agent_artifacts/tui.py` as the next
  executable work once B-044 closed. An earlier handoff estimated ~571 orphaned lines from a
  single-pass scan. That estimate was wrong in a way worth recording: the retired wizard's dead
  definitions call each other, so a one-pass "is this name referenced anywhere?" check keeps whole
  clusters alive by their own internal references. Computing reachability to a fixpoint from the
  module's live entry points instead found 1,680 lines, and the sweep terminates with the detector
  reporting `0 dead definitions` over the remaining 1,087.
- **Decision:** remove the unreachable definitions, and apply D-091 to the tests that held them
  before deleting any test file: for each assertion, either find the public flow that already
  covers it, or carry it to the reachable surface and prove it red against a real mutation.
  `tui.py` goes from 2,767 to 1,087 lines; four test files are deleted; six are retargeted.
- **Status:** accepted.
- **Reason:** the surface is genuinely gone (D-113, D-116, B-039), so keeping tests that drive it
  reports coverage of screens no one can open. Deleting them without the D-091 step is what loses
  behaviour, which is why the carries below exist rather than a bare removal.
- **Consequence:** what was carried, and where it landed:
  - `tests/setup_receipt_cli_test.py` is new. `tui_receipt_test.py` was the only place any front
    end was driven through `show`, `verify` and `undo` on real records: the renderers and the
    rollback are characterized in `setup_receipt_show_test.py`, `setup_verify_test.py` and
    `setup_undo_test.py`, but nothing proved an operator could reach them. The same fixture now
    drives `aart marketplace receipt`, including verify reporting a hand-edited managed block as
    `false=1` with a nonzero exit, and undo reviewing before `--yes`.
  - `tests/consumer_shell_test.py` gains three: the `?` help advertises the filter key exactly
    once; a filter matching nothing empties the screen without leaving it; and the artifact *type*
    is searchable, because the row a screen carries names its kind. Each was proven red by
    mutating production code, the last by matching only the final coordinate segment.
  - `tests/tui_consumer_entry_test.py` moves three tests from the removed
    `_canonical_consumer_source` wrapper to `_canonical_consumer_actions(...).source()`, which is
    what the shell actually draws. ERR03's surviving claim -- a refusal comes back as the object
    the boundary raised, not a rewrapping -- is now `assertIs` there rather than in the deleted
    wizard-loader test.
  - `tests/tui_source_lifecycle_test.py` retargets the refusal test from
    `tui._source_flow_diagnostics` to `io/consumer_actions.py::_refusal`.
  - `tests/memory_cli_test.py` retargets `tui._TYPE_ORDER` to `tui_marketplace._KINDS`.
  What was deliberately *not* carried, with the reason:
  - The wizard's "no screen string uses the dot as a separator" guard. The Product Specification's
    own screen mockups use ` · `, and the Specification wins; the equivalent guard survives where
    it is still true (`tui_marketplace_test.py`), and the divergence is B-049.
  - The wizard's key-hint chrome guard. Its regex is wizard vocabulary (`enter=finalize`,
    `b=back`) and matches no literal in any shipped shell module, so carrying it would add a test
    that cannot fail. The claim behind it -- keys are advertised in one place -- is what the new
    help-screen test asserts.
  - The match-count notice (B-047) and refusal wrapping (B-048), which the canonical shell does
    not do. Neither is asserted as though it held.

## D-130 — Two stores can say an artifact is installed, so there are two setup-record locators

- **Context:** B-046. D-128 gave configured installs a real setup run whose durable pointer is the
  receipt's `setup_state_ref`, but `setup_receipt.locate_setup_record` reads that pointer only out
  of the retiring install-state manifest. A configured install therefore performed a setup run that
  `aart marketplace receipt show|verify|undo` answered for with "this scope has no installation
  state" -- a run the operator had to take on faith and could not roll back.
- **Decision:** add `locate_receipt_setup_record`, which takes the pointer off the receipt, beside
  the manifest-backed locator that keeps reading it out of install state. `receipt_service.
  load_receipt` asks the canonical store first -- the same order `marketplace setup` already uses
  (D-128) -- and falls back to the manifest when the canonical store does not know the selector.
  Nothing writes legacy install state.
- **Status:** accepted.
- **Reason:** the pointer is the only thing that differs. The file it names, the three absences it
  can report and the record it yields are identical, so a second locator is a few lines while a
  second reader would be a second set of refusals to keep in agreement. Canonical-first, because
  that is the store the manifest is being retired in favour of; falling through rather than
  choosing means a machine holding only legacy installations answers exactly as it did before, and
  one holding both answers for each from the store that recorded it.
- **Consequence:** three things the canonical store's shape forced, each measured rather than
  assumed:
  - **Scope is checked, not rebound.** The receipt store keeps one file per coordinate and
    partitions nothing by scope, so until the record is read the scope is only the one the operator
    asked about. A record belonging to the other scope is refused, naming the scope it is in --
    answering `--scope project` with a user-scope installation reads exactly like a correct answer
    to a question nobody asked.
  - **The profile comes from the record.** A receipt can serve several harnesses while setup ran
    for exactly one, and only the record knows which. `receipt_service._bound` replaces the
    provisional profile after parsing; the test proves it by giving the receipt a second harness
    that sorts *before* the one setup ran for.
  - **"This scope has no installation state" is now conditional.** On a machine whose
    installations are all configured, that sentence is false and points the operator at a file that
    will never exist. It is kept only when the canonical store is also empty; otherwise an unknown
    selector gets the refusal that names the selector.
  A fourth was a corrected expectation rather than a design choice: an install that declines setup
  still writes a record, with status `cancelled`, no steps, and the exact retry command. The test
  written to assert a refusal there was wrong and now asserts what the machine does, because the
  record is the more useful answer -- it names the thing to do next.
  `domain/receipts.py` gains `receipt_profiles`, moved out of `io/configured_setup.py` where it was
  private, because the read path needs the same derivation and duplicating it is how two readers
  start disagreeing about which harnesses an installation serves.

## D-131 — B-038's routing question is sequenced behind two canonical capabilities, and pinned meanwhile

- **Context:** `NEXT.md` named B-038's remaining half as the next executable work: make
  `commands/marketplace.py::_configured_registry_selection` stop returning `None` for direct and
  local sources, on the reading that INV-021/INV-026 imply installing from a Source is refused
  rather than routed. The item asked for a characterization of `aart marketplace install
  <direct-source-artifact>` first.
- **Decision:** do not change the route. Record that the characterization already exists, that the
  route is load-bearing for more than the question it is being asked about, and pin the decision
  and each of its reasons in `tests/marketplace_install_routing_test.py`.
- **Status:** accepted.
- **Reason:** measured, not assumed. `tests/marketplace_lifecycle_e2e_test.py` configures one real
  `SOURCE_LOCAL` source, synchronizes it for real, and drives 27 end-to-end tests of this exact
  command through it -- so the characterization the item waits on is already there, and all 27 go
  down this `None`. More importantly, only one of the seam's three declining reasons is the policy
  question: it also declines every Collection, because the canonical seam expands none, and
  `_configured_lifecycle` refuses anything but `--mode copy`. Removing the route now would delete
  direct/local installs, Collection installs and symlink installs together, and two of those three
  are the canonical route being unfinished rather than anything INV-021 or INV-026 argues about.
  A capability is not retired by deciding a different question next to it.
- **Consequence:** B-038 stays open with the sequencing written down: the Collection and symlink
  capabilities are the work, and the routing decision is cheap once they exist. Nothing about the
  route is now implicit -- the new test names the approved-registry case, the default-registry
  case, both direct source kinds, the Collection case, the disabled-registry case, and the fact
  that one direct selector declines a whole batch because a Selection executes as one transaction.
  Closing either capability turns exactly one of those red.

## D-132 — `could-not-check` is the last-known-good state, not a missing source

- **Context:** CP-15's first increment drove `aart source sync` over a real source whose upstream
  had published an invalid revision. INV-218 held where it was already tested -- the store kept the
  last-known-good snapshot and the Marketplace kept serving it -- and then failed everywhere else.
  After a refused sync the source's health is `could-not-check`, and three places read that as
  "this source is gone": `lifecycle/application.py::_recorded_subscription_current`, which made
  `aart marketplace status` report every installation from that source as `source-unavailable`;
  `prepare_update`, which takes the same branch, so `aart marketplace update` returned a terminal
  refusal for an installation that was current against the snapshot on disk; and
  `installation/model.py::InstallPlan.__post_init__`, which carried the same set as a *construction*
  invariant, so no plan could be built at all and `aart marketplace install` answered `canonical
  install plan is not exactly review-bound` -- an internal sentence, with no remediation -- on a
  machine whose store was intact.
- **Decision:** `could-not-check` joins `healthy`, `stale` and `degraded` in both sets. `missing`
  and `not-synchronized` stay excluded.
- **Status:** accepted.
- **Reason:** Product Specification 165.11 settles it: a registry that cannot be reached is shown as
  Offline and *"Marketplace may continue using the last known valid local snapshot."*
  `could-not-check` is not a report that the snapshot is absent -- it is what
  `SyncDisposition.RETAINED`, the explicit last-known-good fallback, produces, and every branch that
  returns it returns a published snapshot with it. Whether a snapshot exists is already tested one
  line above, by requiring a resolved revision and a snapshot digest; health was being asked the
  same question a second time and answering it wrong. Both plans pin the snapshot and the object
  they install by digest, so they depend on nothing the failed check would have told them, which is
  why `--offline` already installed the identical bytes successfully while the plain command died.
  `missing` and `not-synchronized` stay excluded because they mean there is no snapshot, so there is
  nothing to install from.
- **Consequence:** the plan still records which reading it was built under, so the review states it
  and the finalize recheck has something exact to compare against; the separate rule that a source
  which *degraded* between review and finalize invalidates the plan is unchanged. Two questions that
  were being answered by one field are now separate: `check_installations` stays fetch-free and
  says whether an installation is current against the snapshot the store serves, while the source's
  own health says, next to it, that the origin could not be checked. Evidence is
  `tests/source_sync_command_e2e_test.py` over the public verbs plus the two seam tests; reverting
  the `RS-08` refusal in `sources/validation.py` turns all eight end-to-end tests red, so they
  measure the gate rather than the fixture.

## D-133 — A rolled-back setup step is kept as evidence, not dropped

- **Context:** Product Specification 165.12 requires the receipt of a run whose verification failed
  to record *"applied effects, verification result and final health"*. CP-15 step 4a drove that
  through the public verbs for the first time: a recipe that writes one managed block and then runs
  one command that exits non-zero. The report half held -- `aart marketplace setup` exits non-zero,
  the item is `verification-failed` and not `apply-failed-rolled-back`, the counts say
  `configured=0, incomplete=1`, and 165.13's compensatable-restore branch removed the block. The
  evidence half did not: `_apply_effects` passed `receipts=() if rolled_back else receipts`, so the
  persisted record's `steps` list was empty and `aart marketplace receipt show` said a verification
  had failed while saying nothing about what had already been done to the machine before it did.
- **Decision:** a run that rolled back keeps its step receipts, each marked
  `setup_disposition: "compensated"`. `_record` decides `rollback_command` from the steps that are
  still standing, so a fully compensated record offers no undo.
- **Status:** accepted.
- **Reason:** the effects were applied -- they are what the rollback undid -- so a receipt that
  omits them fails 165.12 on its own terms. The alternative reading, that an empty list is how the
  record says "nothing is standing", conflates two different states: a run that applied nothing and
  a run that applied and reversed. An operator investigating a failed setup needs to know which.
  Nothing new was invented for it: `setup_disposition: "compensated"` is the word
  `setup_engine/application.py` already writes on the persistence-failure path, and all three
  readers already honour it -- `_rollback_receipt` treats a compensated step as terminal,
  `plan_verification` asks nothing about its former target, and `plan_undo` keeps rather than
  reverses it. The change makes one path use the vocabulary the other already had.
- **Consequence:** `rollback_command` moves from "any receipt" to "any *standing* receipt", which is
  what the persistence-failure path was already doing by hand with an explicit
  `rollback_command=""`; both paths now get it from one place. A retained compensated step makes no
  live-world claim, so `receipt verify` still reports zero false claims after the rollback and
  `receipt undo` offers nothing to reverse -- which matters, because offering to undo an already
  undone change would delete whatever a person put back in its place. The consent-declined path in
  `_apply_effects` gets the same retention for the same reason; it has no public-flow test because
  `--approve-setup-effects` is all-or-nothing at the CLI, so a cancel can only land before the first
  effect applies (B-052). Evidence is `tests/verification_failure_e2e_test.py`; the two evidence
  tests were red against the shipped code and reverting `standing` to `receipts` in `_record` turns
  the undo claim red on its own.

## D-134 — Mutation adequacy is a scoped, advisory tool, not a gate

- **Context:** every slice from CP-13 on has proved its tests by hand: make one deliberate,
  semantically real change to the code a test names, and watch that test turn red. That practice
  answers "is this claim load-bearing" and cannot answer "what claims did nobody think to make",
  which is the question coverage also cannot answer — a line that ran is not a line whose behaviour
  anything asserts. `mutmut` answers it mechanically, and this repository was not using it.
- **Decision:** `mutmut` joins Poetry's dev group and is run through
  `make mutants ONLY=<path.py> TESTS="<test files>"` (`scripts/mutants.py`). It is advisory, never a
  release gate, and always scoped to the module a slice just changed. Hypothesis, already in the dev
  group and used by eleven test files, is named alongside it in `AGENTS.md` as the tool for
  universal claims. Neither replaces the targeted per-claim mutation the slice documents record.
- **Status:** accepted.
- **Reason:** scope and advisory status are both forced by measurement rather than preference. The
  first run managed ~3 mutants a second; `agent_artifacts` is 40k statements, so a whole-repository
  run is days of compute and could never sit in `make quality`. And the survivor *count* is not
  meaningful on its own: a scoped run's figure depends entirely on which tests were selected, so
  728 survivors in `setup_render.py` against two end-to-end files says nothing about the module's
  real coverage. What is meaningful is a specific survivor read against a specific claim. Making it
  a gate would therefore create pressure to move a number that does not mean what it looks like —
  the exact failure the "do not weaken quality gates" rule exists to prevent, arriving from the
  other direction.
- **Consequence:** `scripts/mutants.py` writes the scope into `setup.cfg` and restores it in a
  `finally`, because mutmut 3.x reads its configuration from that file and accepts no scope on the
  command line. That means `make mutants` must not run while a quality gate is running:
  `scripts/quality.py` fails a run whose tracked files moved under it, and that is the guard
  working. `mutants/`, `mutmut-stats.json` and `.mutmut-cache` are ignored. Read survivors as
  findings: one inside the current slice's claims is a test that does not hold what its name says,
  one outside them is a backlog note (B-054 records that no module has a trustworthy baseline yet).
  Never weaken a test to change the figure.

## D-135 — A remediation reworded does not bump the ruleset revision label

- **Context:** CP-15 step 5 changed the `embedded-credential` rule's remediation text so it carries
  165.10's Git-history statement. `_RULESET_REVISION` is commented "bumped when the rules or their
  reach change", and it currently reads `baseline-v1.1`.
- **Decision:** keep the label at `baseline-v1.1`.
- **Why:** the remediation string is already inside `BASELINE_RULES_DIGEST`, so every assessment
  recorded under the old wording is reported stale by the mechanism that exists for exactly that —
  the staleness guarantee needs no label change to work. What the label is *for* is telling a reader
  which detection ruleset produced a finding, and it is quoted as such in `compatibility-v14/15/18`
  and the v2.5.0 release notes. Nothing about what the scanner detects changed here. Bumping it
  would announce a detection change to those published documents that did not happen, and would
  require editing them to stay true.
- **Consequence:** the label moves when the rules or their reach move; the digest moves whenever any
  rule's text does, which is the finer-grained guarantee and the one staleness is computed from.

## D-136 — Policy compliance is reported beside the status, not folded into it

- **Context:** Product Specification 165.21 makes effective-policy compliance part of an installed
  artifact's health. `LifecycleStatus` already has fifteen members and `marketplace status` reports
  exactly one of them per installation.
- **Decision:** carry compliance as its own dimension — `PolicyStanding(status, detail, trust)` on
  `LifecycleItem`, flattened to `policy_status`, `policy_detail` and `trust` on
  `ConsumerTerminalItem` and in the JSON payload — rather than adding a `policy-drift` status value.
- **Why:** the two answer different questions and an installation can need both. An artifact that is
  out of date *and* no longer compliant has one status slot and two things to say, and whichever
  won would make the other invisible. A new status value would also have had to be added to three
  separate allowed-value sets and would change the answer every existing reader gets for an
  artifact that is otherwise `current`. `setup_status` is the precedent in the same record: an
  orthogonal dimension carried beside the status, defaulting to a value that means "nothing to say".
- **Consequence:** the compliance rule is not duplicated. `installation/application.py`'s user-scope
  trust check is now the public `trust_shortfall` and `lifecycle` asks that same function, so the
  gate and the health report cannot drift apart — health computed by a near-miss rule would tell an
  operator something false in the most expensive way. `not-evaluated` is a third value and not a
  pass: where the record resolves to no current item there is no trust to judge, and every such path
  reports it by leaving `PolicyStanding()` alone rather than by answering.

## D-137 — Publication is measured as two directories, not as one directory before and after

**Context.** CP-15 step 7 had to show that a local promotion is not publication (INV-242) without a
Git host to publish to. The available shortcut was to promote into the consumer's own source and
watch the consumer not see it.

**Decision.** Model the maintainer's registry checkout and the published registry a consumer is
subscribed to as two separate directories, and assert that promotion moves neither the published
tree's bytes nor the consumer's view — after a real re-synchronization, not merely before one.

**Why.** The shortcut gets the right answer for the wrong reason. `registry promote` writes a
versioned layout that a native source tree does not accept (B-057), so the consumer stops seeing the
artifact because its source became invalid, not because the promotion was unpublished — and a test
whose green depends on an unrelated defect turns red the day that defect is fixed. Two directories
are also what production actually is: two states of one repository separated by a push and a merge.

The cost is that "published" is simulated by a directory rather than performed by a merge, so the
mutation that must turn these claims red is a simulated push — the tree copied across — rather than
a code change. That mutation kills exactly the three consumer claims and nothing else, which is the
evidence that the assertions are not vacuous. The hop itself stays with CP-17, where a real remote
exists; `git_location_parts` admits no `file://` remote, so it cannot be driven here.

**Consequence.** A test that measures a boundary must be red for the boundary's own reason. Where
the only available failure mode is an unrelated one, arrange the fixture until the intended failure
is the one that fires, and record the mutation that proves it.

## D-138 — An asserted absence is evidence only where the fixture could have produced the thing

**Context.** CP-15 step 8 had to hold INV-232: a removal does not delete a credential another
installed artifact still references. The obvious test drives `aart marketplace uninstall` and asserts
no credential deletion appears in the reviewed plan.

**Decision.** Assert an absence only against a fixture in which the thing asserted absent is
reachable, and prove that reachability in the same test. Where the public verb's fixture cannot
produce it, measure the claim one level down at the function the verb calls, passing exactly the
arguments the verb passes, and say in the docstring why.

**Why.** The obvious test passed, and defaulting `delete_credentials` to true — the whole behaviour
it claimed to guard — killed nothing. The fixture registry's Skill declares no inputs, and the native
source protocol has no `inputs` field at all (`protocol/native_schema.py` never mentions one), so a
native-source artifact reaches a credential only through its setup recipe. The test was asserting
that nothing was deleted in a scenario with nothing to delete, which is a sentence that stays true
however the code changes.

The replacement makes two calls on one record that does carry a credential reference: the call
`commands/marketplace.py` makes, which passes no `delete_credentials` at all, and the same call when
asked. The second is what makes the first mean something. Driving it at the seam is not a
convenience either — `commands/marketplace.py` wires a real `MacOsKeychainProvider` on darwin, so a
command-line test that stored a credential would write into the developer's own Keychain, which is
why every existing credential test uses a file-backed provider.

**Consequence.** Two habits, both of which caught a defect in the same increment. Before asserting
that something is absent, make the fixture produce it once and watch the assertion fail. And assert
that any collection an absence is checked against is non-empty first — a fourth draft test here read
a receipt step's `effect` as a dict when it is a string, filtered every step away, and passed over an
empty set. See [[D-091]]: a test is not evidence until a real mutation turns it red.

## D-139 — Doctor is one read projected twice, and repair starts as a plan

**Context.** CP-16 needs a public, environment-wide `aart doctor`. The accepted screen-29
projection already answers health, while the reconciliation engine already answers the smallest
policy-permitted repair. Reimplementing either answer in the command would let the visible finding
and the executable plan disagree. Resolving Marketplace content would also make inspection of an
installed artifact depend on its source still being available.

**Decision.** Read all canonical project and user installations once with
`read_installed_inspections`. Project each same immutable observation through `project_doctor` for
human health and through `prepare_configured_repair` for a canonical repair plan. Emit plans only
where observed drift is non-empty. The first public command is read-only: it reports those plans but
does not apply them, and an attention finding exits non-zero. It loads configuration without
requiring source content.

**Why.** "Environment-wide" is a scope statement, not a synonym for the current project, and the
real two-scope E2E turns red if the read is narrowed. "Doctor uses reconciliation" means the plan
must come from the same planner lifecycle repair executes, not that Doctor may choose a convenient
installation action. A non-empty healthy fixture turns red if healthy artifacts receive plans, so
the empty repair collection is evidence rather than an empty-machine accident. Source-independent
inspection is what lets Doctor explain an installation whose registry has disappeared.

**Consequence.** JSON carries every measured artifact, its component drift, and the complete domain
repair plans; the existing screen-29 renderer now lists the same artifacts and reasons before its
counts. A later repair entry point must review, re-inspect and re-plan before applying one of these
plans. It may not treat this report as authorization and may not replace the plans with
reinstall-all.

## D-140 — Offline readiness reports durable evidence, never a guessed boolean

**Context.** Product Specification 165.11 requires three independently readable capabilities:
metadata cached, canonical payload cached and runtime dependencies cached. AART durably records a
configured Source snapshot and a registry's approved object digest, but has no durable package-
manager cache index. Merely finding an artifact package cannot establish that pip or uv can resolve
its declared dependencies without a network.

**Decision.** `aart doctor` observes every enabled configured Source once and reports four evidence
states: `cached`, `missing`, `not-required` and `unverified`. Source metadata is cached only when a
current Source snapshot exists. An approved registry artifact's canonical payload is cached only
when its vendored package can be extracted from that same snapshot and re-digested to the approved
object identity. Runtime dependencies are `not-required` only when that verified package declares
none; a declared dependency is `unverified` until AART owns durable package-cache evidence. A
referenced publication therefore has cached metadata and a missing canonical payload, and never
inherits readiness from some other local copy. The report is informational and does not change an
installed machine's healthy/attention exit status.

**Why.** Collapsing the observations to one offline boolean recreates the exact defect INV-223
forbids: synchronizing a registry does not download package-manager dependencies, and possessing a
payload says nothing about wheel or index availability. Calling declared dependencies `missing`
would be equally unsupported because the installer may have a usable cache that AART cannot yet
inventory. `unverified` says exactly what the current evidence permits. Reusing the configured
installation's package extraction and digest verification keeps install and Doctor from defining
"canonical payload" differently, while stopping before object publication keeps Doctor read-only.

**Consequence.** The JSON and human outputs keep all three capability names separate before any
install is attempted. Unsynchronized, referenced, dependency-free and dependency-declaring cases
are independently reachable in real public-command tests; multiple sources and artifacts are all
observed, deprecated versions are not advertised as installable, and Doctor writes no target or
object-store content. B-051 is closed and INV-223 is EVIDENCED. Full offline dependency-cache
inventory and installation remain the distinct deferred B-010 capability.

## D-141

A confirmation digest computed by the command proves only that the command re-planned. The claim
worth holding is that the machine has not moved since the operator saw it, and only the layer that
holds the execution lease can hold that.

`aart doctor --repair` therefore checks `--expect` twice, against two different things. The command
compares the operator's digest to its own freshly recomputed plan, which catches drift between the
review the human read and the confirmation they typed, and returns the recomputed plan rather than
applying the stale one. The configured lifecycle adapter then re-observes the machine under its
lease and refuses with `execution-review-stale` if it moved again. The second check is not redundant
with the first: a test that moves the machine only before the command runs cannot tell them apart,
which is why the evidence includes a scenario that moves it *after* the command's own re-plan.

The consequence for future repair-like verbs is that the command layer owns the operator-facing
staleness message and the adapter owns the effect-facing one, and neither is allowed to stand in for
the other.

Evidence/links: CP-16 step 3; `commands/doctor.py`; `io/configured_repair_action.py`; INV-194;
D-091.

## D-142

A diagnostic that requires the operator to name its subject cannot report the case where the subject
is unknown, and that is usually the case worth reporting.

`orphan_run_directories` filters the run root by one receipt's `plan_hash[:16]`, so finding an
interrupted run's working copy required already knowing which run was interrupted. The global report
sweeps the same root with no plan hash and reports whatever is there, keyed by the prefix each run
directory's own name encodes so the result still ties back to a receipt.

Two boundaries are preserved rather than widened. `LAF-61`: the sweep reports, names and leaves —
Doctor deletes nothing, and the human rendering says so. `LAF-66`: the run root is supplied by the
caller and never derived a second time, because that defect was this exact path composed from the
project root in one place and the data root in another.

The observation distinguishes "no working copy" from "the run root could not be read", and the
projection refuses to represent an unreadable root that also lists runs. The general rule for
diagnostics added to a global report: a surface that can only answer when asked a specific question
is not the same capability as one that can find the thing unprompted, and the second is what a
report is for.

Evidence/links: CP-16 step 4a; `application/orphaned_runs.py`; `io/orphaned_runs.py`;
`setup_verify_probes.py::orphan_run_directories`; CP-15 step 4b; INV-192.

## D-143

A cross-check is only evidence when both sides are records of the same thing.

`aart doctor` now reports the lifecycle audit trail with each action's undo availability. The first
draft asserted that Doctor's undo block matched what `aart marketplace receipt show` returned, and
that was wrong twice over: `receipt show` returns the *setup* receipt for one coordinate, which
carries `retry_command` and `rollback_command` and has no `recorded_at` or `undo` field at all,
while the trail carries lifecycle receipts — install, update, uninstall, repair. The test failed
with `KeyError: 'recorded_at'`, and the useful part was not the fix but what the failure said: the
two are different receipts about different things, and a passing version of that assertion would
have encoded a relationship that does not exist.

INV-192 is held instead by showing that the undo answer varies with what actually took effect, in a
pair one flow produces: an install that placed a payload and a delivery reports an undo naming
exactly those components, and the uninstall that follows reports none, because nothing retained can
reverse a removal. Neither half is a second opinion about reversibility — both are
`receipt_detail_to_data`'s own block — and the pair is what makes the false half evidence (D-138).

The general rule: before asserting that two surfaces agree, establish that they are reporting the
same record. Two names containing the word "receipt" are not that establishment.

Evidence/links: CP-16 step 4b; `commands/doctor.py::_action_data`; `receipt_service.py::show_view`;
`application/consumer_views.py::_undo_availability`; INV-191; INV-192; D-133; D-138.

## D-144

An asserted absence over a whole report holds its claim only until some other part of the report
legitimately uses the word.

CP-16 step 2 established that a cached payload is not an installed artifact, and held it with
`assertNotIn("installed", output.lower())` over the entire human `aart doctor` report. That was
correct when the report had two sections. Step 4c added a credential section whose empty answer is
"no installed artifact references one" — a true statement, in the section whose subject genuinely
is installed artifacts — and the step-2 test failed. Nothing had regressed: the assertion had been
holding "no section of this report says installed" while its claim was "the offline capabilities
are not described as installations", and the two coincided only by accident of how little else the
report said.

The assertion is now scoped to the offline-readiness block, and the narrowing is a strengthening
rather than a weakening: it names the section the claim is about, and a mutation that puts the word
`installed` into the offline renderer still turns it red. The whole-report form would have gone on
passing for the wrong reason, or forced every later section to avoid a word Doctor's own subject
matter requires.

The general rule: scope an absence assertion to the surface whose claim it is. An absence measured
somewhere the thing could never have appeared measures nothing (D-138); an absence measured
everywhere is a claim about vocabulary, not about the thing.

Evidence/links: CP-16 step 2 and step 4c; `tests/doctor_offline_readiness_e2e_test.py::
test_human_output_keeps_the_three_capabilities_visibly_separate`; `commands/doctor.py::
_credential_lines`; D-138; D-140.

## D-145

A single-example fixture cannot see a separator, a loop guard, or a plural. State those claims as
properties, not as one more example.

Three times in CP-16 a scoped mutation run found the same class of gap, and each time the immediate
fix was to add a second item to a fixture. Step 4a: `continue` and `break` were indistinguishable
in the run-root sweep, because with one working copy there is nothing for `break` to skip. Step 4b:
the separator joining an undo's components was invisible until two components existed. Step 4c: the
separator between a credential's dependants, and between locked configuration fields, was invisible
for the same reason, and "only the first one is rendered" would have passed every test in the file.

Adding the second item fixes the instance. It does not fix the kind — the next section rendered as
a list starts with one example again, and nothing in the repository says why that is not enough.

The claims are universal, so `tests/doctor_properties_test.py` states them that way: for any mix of
enabled and disabled sources the reported set is exactly the complement of the enabled ones; for any
number of locked fields, dependants or working copies, none is dropped from the rendering; a
credential is deletable exactly when nothing depends on it; and the count in a summary line agrees
with the list beneath it. Eleven targeted mutations confirm the properties are load-bearing, and
three of them -- `disabled[:1]`, `dependants[:1]`, `runs[:1]` -- are precisely the defect no
single-item fixture can express.

This does not replace example tests. The Product Specification names specific scenarios and those
stay as examples; what moves to a property is the part of the claim that was always "for every",
and was only ever demonstrated for one.

Evidence/links: CP-16 steps 4a, 4b, 4c and 5; `tests/doctor_properties_test.py`; D-091; D-134;
D-138; D-144.

## D-146 — A cross-stage fixture carries the whole prior result, not a reconstruction

**Context.** Before CP-17, the real Git adapter and every consumer stage had separate E2E evidence,
but the consumer fixtures rebuilt a source candidate from fixture bytes and `"a" * 40`. That proves
each stage against a precondition invented by its test, not against the value the preceding stage
emits. Selected-field assertions have the same weakness: the first scoped mutation run showed that
the store could replace a candidate's source instance while commit, digest and entries still passed.

**Decision.** Each CP-17 increment passes the complete value returned by the preceding stage into
the next one and asserts complete equality at the durable readback boundary. Step 1 passes the real
`SourceCandidate` from `acquire_git_snapshot` through validation and publication unchanged, then
compares the fresh reader's candidate to it. Local transport is enabled only on this direct adapter
request; later public-flow steps retain a valid remote identity and substitute the acquisition port,
never configuration validation or the transport verdict.

**Why.** A chain is evidence only when identity, provenance and payload move together. Reconstructing
one stage's output at the next seam can preserve the fields the test remembers while silently losing
the ones it does not. Full value equality killed that exact mutation and also covers immutable-Git
origin, aliases and executable metadata without duplicating their representation in the test.

**Consequence.** CP-17 fixtures grow by extending one continuous result, not by publishing a new
hand-built prerequisite at each step. A port may stand in for unavailable network transport, but its
input and output remain the real production values and every security verdict remains unmodified.

Evidence/links: CP-17 step 1; `tests/git_source_publication_e2e_test.py`; INV-112; INV-115; D-091;
D-134.

## D-147 — Each registry representation is validated by the authority that writes it

**Context.** CP-17 step 2's first public sync of a real promoted registry failed before Marketplace
or installation. Promotion writes the accepted versioned representation -- vendored packages under
`artifacts/<kind>/<name>/<version>` and exact `registry/versions`, `registry/index.json` and
`registry/snapshot.json` metadata. Source validation and the read-only CLI Marketplace instead
interpreted those bytes as the older maintainer workspace, requiring unversioned artifact roots and
`aart.lock.json` / `aart.index.json`. This was B-057's consumer-facing consequence.

**Decision.** A configured RegistryGit snapshot carrying the `registry/` namespace is an approved
promotion representation and is validated by `load_registry_versions` plus
`validate_promoted_registry`, the reader and validator paired with promotion's writer. A snapshot
without that namespace retains the characterized compiled-workspace validation during the
strangler migration. The read-only Marketplace projection calls the same
`project_configured_registry` package compiler as the persistent shell for the approved shape,
rather than growing a second versioned-layout reader.

**Consequence.** A real promoted registry can pass public source sync and Marketplace listing, and
malformed or stale catalogs are still refused -- including an empty approved projection, whose
negative test kills omission of the explicit validator. No transport or configuration allowlist
changed. The old `registry publish` verb still expects the compiled maintainer-workspace shape and
remains B-057; CP-17 follows 165.27/165.28, where Git review and merge publish promotion's local
state.

Evidence/links: CP-17 step 2; `git_backed_consumer_e2e_test.py`;
`source_registry_validation_test.py`; B-057; INV-112; INV-119.

## D-148 — The transport revision is digest-bound installation provenance

**Context.** After public sync and Marketplace listing carried Git's real commit, the configured
install receipt did not. Resolution kept the approved object and registry snapshot but discarded
the `CurrentSource` revision, so a receipt could identify exactly what content was installed without
identifying the Git state through which the consumer obtained that approval.

**Decision.** The configured boundary adds the pinned revision to `ApprovedRegistrySnapshot`,
resolution copies it to each `ResolvedArtifact`, and canonical install-plan serialization includes
it before calculating the review digest. Receipt projection takes the revision from that reviewed
plan, never from a later source-store read, and serializes it on the matching artifact member.
Every added field is optional so hand-built/domain-only selections and existing receipt bytes keep
their old canonical form; reading an older receipt yields unknown provenance rather than a guessed
commit.

**Consequence.** The public install payload and a fresh durable receipt read both name the actual
commit produced by Git. Changing the configured revision to `"a" * 40` turns the end-to-end test red
at the receipt while sync and Marketplace continue to report the real SHA, proving the value is not
being re-read or inferred at presentation time. Because it is part of the plan, a changed revision
also changes what a person reviews and confirms.

Evidence/links: CP-17 step 2; `git_backed_consumer_e2e_test.py`; `domain/plans.py`;
`application/consumer_views.py`; INV-112; INV-119; D-146.

## D-149 — A claim held by accident is not held

**Context.** CP-17 step 2 added a Source revision to resolved artifacts, install plans and receipts,
and D-148 recorded two guarantees about it: the value is a pinned Source revision, and every field
is optional so existing receipt bytes keep their canonical form. Both are claims about inputs the
end-to-end chain cannot produce -- a real run builds exactly one well-formed revision, and it cannot
write a receipt from before the field existed -- so neither could be evidenced by the chain test
that motivated them.

Measured separately, they came apart. Deleting the `is_pinned_source_revision` clause from
`ResolvedArtifact.__post_init__` left all 3,349 repository tests passing: the shape of a revision
was held by nothing. Removing the decoder's tolerance of a missing key does turn
`installation_transaction_receipt_test` red, so that half was held -- but incidentally, by a
round-trip whose name speaks of rebuilding an activity entry, over a fixture that happens to carry
no revision.

**Decision.** Both halves are stated in `tests/git_revision_provenance_test.py`, the shape as a
Hypothesis property over every string that is not a pinned revision (D-145: the guard admits an
unbounded set, and three examples cannot say so), the durability as the D-138 pair -- a receipt
carrying a revision reads it back, and the same receipt with the key removed reads back as unknown
-- plus the distinction between a key omitted and a key written as `null`, which is the same answer
to a reader and different bytes on disk.

**Consequence.** Three mutations, each red only where claimed: deleting the shape guard turns the
two property tests red and no receipt test; refusing an absent key turns the two decode tests red;
writing `null` in place of omitting turns the byte-level test red on its own assertion. The
incidental round-trip coverage is unchanged and still passes -- this states what it was holding
without being asked to, which is what makes it survivable when the encoder is next edited.

**The second instance, found by looking for it.** The same guard is written twice: `ResolvedArtifact`
validates the revision it carries, and `ApprovedRegistrySnapshot` validates the revision an operator
is offered and resolution copies downstream. Deleting the second one also left the whole repository
green -- 3,357 tests -- and for the same structural reason: every revision any test supplies is well
formed, so nothing could reach the branch. Both are now stated as properties in the same file. A gap
of this shape is rarely alone, because what causes it is not carelessness but the fixtures being
realistic.

**The general form.** A test that turns red under a mutation is evidence that *something* holds the
claim, not that the claim is stated. A claim held only by a fixture's accidental shape is one
refactor of that fixture away from being held by nothing, and its name gives the next reader no
reason to preserve it. When a decision record names a guarantee, some test's name should carry it.

Evidence/links: CP-17 step 2 review; `tests/git_revision_provenance_test.py`; D-091; D-138; D-145;
D-148.

---

## D-150 — What a reconciler cannot repair, it must still report

**Context.** CP-17 step 4 measured `aart doctor` against a live Git-backed MCP installation under
four kinds of damage. A rewritten launcher was caught: `broken`, `divergent`, repairable. All three
kinds of payload damage -- one file rewritten, one file deleted, the whole tree deleted -- were
reported as `health: ready, drift: []`, while the server itself exited 1. The report claimed
readiness for a component it had not examined.

**Cause.** Not a missing measurement. `observe_installation` and `observe_placement` both measure
the payload, and `current_state_from_placement` even judges it by tree digest under a docstring
arguing that presence is the wrong question. The measurement was then discarded: both current-state
builders ended with `tuple(item for item in components if item.id in wanted)`, and `wanted` is the
desired components, from which the payload is absent whenever no `payload_source` was supplied.
`io/consumer_machine.py` supplies none, because a doctor has no plan knowledge. So the payload was
measured, dropped, and its absence from the drift list read as health.

**The distinction the omission conflates.** Omitting the payload from the *desired* state is right,
and `desired_state_from_receipt` says why: a reconciler that guessed where a tree came from would
overwrite it from somewhere nobody chose. That is a statement about **repair**. It was being used as
a statement about **reporting**, and INV-228 (state changed outside AART is surfaced) and INV-175
(AART says when it cannot safely repair a component rather than fabricating a minimal-repair
guarantee) are both about reporting. Neither is satisfied by silence, and neither asks for an
invented repair.

**Decision.** Keep the desired state as it is; stop discarding the observation.

1. `_reported` replaces the `item.id in wanted` filter in both builders. An undesired component that
   is `MATCHED` is still dropped -- nothing is wrong with it and nobody asked for it. An undesired
   component that is damaged is kept.
2. `compare_states` names undesired damage by what is wrong -- `MISSING`, `DIVERGENT`,
   `UNVERIFIABLE` -- instead of `UNEXPECTED`. `UNEXPECTED` means "here and nobody wanted it", whose
   remedy is uninstall; telling an operator whose payload is gone that they have one too many
   describes the opposite of their situation. A stray *matched* component is still `UNEXPECTED`,
   which is what that word is for.
3. `repairable` stays `False` on both paths. Nothing planned an effect, so no plan may claim to put
   it right -- which is precisely what INV-175 asks to be said out loud.

`Component.PAYLOAD` was already in `installation_health`'s critical set, so a kept payload drift
turns `READY` into `BROKEN` with no change to the health rule.

**A conflation the change exposed.** `InstallationObservation.payload_present` was `bool = False`,
so every caller assembling a partial observation implicitly claimed the payload was deleted. Once
undesired damage stopped being dropped, one existing test -- the regression that describing less
must not invent drift -- turned red and said so. It is now `bool | None = None`: `False` is "the
tree is gone", `None` is "nobody looked", and the component is omitted so the comparison reports
`UNOBSERVED`. That is D-029's distinction, which a plain bool could not hold.

**Reclassification.** Recorded as critical rather than backlog. CLAUDE.md admits a backlog item to
the critical path when evidence proves a mandatory invariant cannot otherwise be satisfied; a health
verdict of `ready` over a deleted payload violates INV-228 and INV-175 directly, and the evidence is
a measured probe against a real installation rather than an argument.

**What this does not close.** On the placement path the payload is judged by tree digest, so
rewritten and deleted are both caught. On the installation path `InstallationObservation` carries no
tree digest and `InstallationReceipt` records no payload digest to compare one against -- only
`object_digest`, which names the package the tree was materialized *from*, not the tree. So an MCP
payload rewritten in place is still invisible, and only whole-tree deletion is caught. Closing that
is a receipt schema change; B-066 carries it with this evidence.

Evidence/links: CP-17 step 4; INV-175; INV-194; INV-228; D-029; D-091;
`tests/placement_observation_test.py::UnrepairablePayloadIsStillReportedTest`;
`tests/reconciliation_test.py::ComparisonTest`.

---

## D-151 — CP-17 step 5's Collection half is an unbuilt capability, not an acceptance gap

**Context.** CP-17 step 5 is written as "Collection and bulk install with one full-chain acceptance
proof". Its bulk half is done and verified. Its Collection half cannot be done, and the reason is
not that the chain is synthetic somewhere -- it is that nothing in the product can produce an
approved Collection for the chain to carry.

**Evidence, traced end to end.** The maintainer side models Collections properly:
`domain/collection_candidates.py` defines `CollectionCandidate`, `compile_author_source` returns
`.collections` beside `.artifacts`, `reconcile_source_scan` takes `collections=` and
`previous_collections=` and produces `collection_active`, and the maintainer TUI shows them. Then it
stops. `CollectionCandidate` appears in exactly six modules -- the two TUIs, `maintainer_views`,
`candidate_history`, `maintainer`, and its own domain module -- and `promotion.py` is not among
them. `collection_active` reaches candidate *history*, which is an audit record, and nothing else.
No collection candidate is ever promoted, so no registry version of kind `collection` is ever
published, and no test anywhere publishes one.

The consumer side is consistent with that. `io/configured_selection.py::_approved_snapshot` skips
approved versions of kind `collection` and leaves `ApprovedRegistrySnapshot.collections` at its
default; `marketplace list` returns `"collections": []`; installing one answers
`collection-not-found`. Resolution is the one part that is ready -- `resolve_selection` documents
"one/many/direct/Collection intent through one deterministic pipeline" and the expansion exists --
which is why the gap reads at first like a projection bug. It is not. The projection has nothing to
project.

**Decision.** B-067 is **not** reclassified as critical for CP-17, and step 5 is recorded as
complete for what CP-17 can actually prove.

The reclassification rule admits a backlog item to the critical path when evidence shows a
critical-path slice cannot complete without it. That rule is about *unblocking a slice's own
subject*. CP-17's subject is that each stage of the chain is real rather than assembled by a
fixture: a real Git commit, real validation and publication, a real install, a real runtime, real
drift and removal. It is an acceptance slice. Building promotion for collection candidates, a
registry representation for a collection version, the configured projection, and install planning
over members with ownership is a capability spanning four layers -- and CLAUDE.md's migration
discipline is explicit that discovered work does not expand the active slice, and that new
capability arrives as its own vertical slice rather than as a big-bang addition inside another.

Proving an acceptance claim about a capability that does not exist is not a thing a slice can be
blocked on; it is a step whose premise was wrong. The step was written expecting Collections to be
installable, and they never have been -- this is the same Collection capability D-131 already
sequenced B-038 behind, seen from the consumer end.

**What was done instead.** The gap is pinned by a test rather than left as prose.
`CollectionsAreNotReachableTest` asserts that the Marketplace offers no collections and that
installing one is refused by name and installs nothing. That is deliberately a test of a refusal
nobody wants: when the capability is built, it is what should turn red, and it should be replaced by
the install it stands in for rather than deleted to make room. B-067 carries the corrected scope --
four layers, not one -- and the empty `collection-not-found` remediation, which is worth fixing on
its own while the capability is absent.

**Consequence for the plan.** CP-17 step 5 reads "Collection and bulk install"; what it can deliver
is bulk install plus an evidenced refusal. Recorded here so the next agent does not re-derive the
same four-layer trace before reaching the same conclusion, and does not read the step's wording as
licence to build the Collection capability inside an acceptance slice.

Evidence/links: B-067; D-131; B-038; INV-186; INV-213;
`tests/git_backed_bulk_install_e2e_test.py::CollectionsAreNotReachableTest`;
`agent_artifacts/application/promotion.py`; `agent_artifacts/io/configured_selection.py`.

## D-152 — A declaration is not a dependency graph, so INV-071 is read off the source

Date: 2026-09-03 · Slice: CP-18 step 1 · Status: accepted

**Context.** INV-071 requires that development verification tooling stay outside the
production/runtime dependency graph. Two checks claimed to cover it. `dev_tools_test` reads
`[project] dependencies` out of `pyproject.toml` and asserts it is `[]`. `scripts/packaging_check.py`
builds the wheel and refuses any non-extra `Requires-Dist` in its metadata. Both are true, both are
worth keeping, and both are statements about what the project *declares*.

**The finding.** A runtime module can import a development tool without declaring anything. Put the
import inside a function body and it adds no `Requires-Dist`, changes no manifest, ships inside the
wheel, and breaks on the first call in an environment installed from that wheel. This was measured
rather than reasoned about: with `import hypothesis` inserted into a function body in
`agent_artifacts/application/installed_state.py`, `dev_tools_test` and `packaging_test` reported 36
passed and 1 skipped, and `packaging_check` reported `packaging check OK`.

**Decision.** INV-071 is evidenced against the import graph. `tests/runtime_purity_test.py` parses
every module under `agent_artifacts/` with `ast` and asserts that none of them imports a development
tool, the test suite, or the gate scripts.

Two choices carry the claim and should not be undone:

- **The forbidden set is derived, not hardcoded.** It is read out of Poetry's dev group at test time,
  so a tool added to the group tomorrow is covered without anyone remembering to extend a literal.
  `poetry-core` maps to its import name `poetry`; names normalise `-` to `_`.
- **`ast`, not import-time introspection.** Walking `sys.modules` after importing the package sees
  only what module-level imports pulled in. The function-body case is both the realistic shape of
  such a leak and the *only* shape that defeats both incumbent checks, so the one approach that
  cannot see it is the one approach that must not be used here.

Two of the file's four tests are guards on the test itself, because an absence assertion evaluated
over an empty tree passes for the wrong reason (D-149): the forbidden set must be non-empty, and the
package tree must yield more than a hundred sources. Without them a rename of `agent_artifacts/`
turns this file into four green tests that assert nothing.

**Consequence.** Neither existing check is replaced; a third has been added at the layer the
invariant is actually about. The general form is worth carrying into the rest of CP-18's
traceability audit: a row is not EVIDENCED because something adjacent is green, and a check that
reads a manifest has not checked the code.

Evidence/links: INV-071; D-149; D-091; `tests/runtime_purity_test.py`; `tests/dev_tools_test.py`;
`scripts/packaging_check.py`; `docs/refactor/slices/CP-18-migration-and-release-gate.md`.

## D-153 — The aggregate gate is proven by running it, and the emitted registry gets one too

Date: 2026-09-03 · Slice: CP-18 step 2 · Status: accepted

**Context.** INV-077 requires branch protection to depend on one stable aggregate gate name rather
than matrix- or environment-specific job names, and requires that aggregate to fail "when no valid
gate arm ran or when any selected arm failed". The audit of the CP-18 CI rows found two different
situations under that one invariant.

**This repository's own `pr-check` was right and untested.** `.github/workflows/pr-check.yml`
already carries the aggregate, correctly: one stable name, `if: always()`, an explicit failure when
both arms are `skipped`, and an allowlist rather than a check for `failure`. Nothing tested it.
`quality_gates_test` covers the matrix default and the delegation to the composite action; the
shell that decides the verdict — the one thing branch protection actually depends on — was covered
by nothing.

**Decision: run it.** The script takes its inputs from the environment and writes its verdict to an
exit code, so `tests/aggregate_gate_test.py` extracts it from the YAML and executes it under `bash`
with each combination of `needs.*.result`. This is INV-076 collecting on its own promise that such
logic stays "runnable/testable outside GitHub Actions when practical" — a workflow cannot be run
here, but this part of one can, and reading YAML for the substrings a correct script would contain
is a much weaker claim than watching it exit 1.

The verdicts asserted: the arm that ran succeeding is a pass in both directions; both arms skipped
fails, naming the variable that would cause it; `failure` and `cancelled` fail in either arm; and
both arms are named in the output whatever the verdict, which is INV-080's visible-evidence half.

**The emitted registry CI had no aggregate at all.** `aart registry init` writes a workflow with
`registry-quality` and `registry-quality-private-image` — two container shapes of which exactly one
ever runs, each a matrix over `compatibility: [minimum, latest]`. So a registry owner protecting
`main` had no name that is the same in every configuration. Naming an arm this deployment skips is
worse than useless: GitHub counts a skipped required check as *satisfied*, so the rule would pass
precisely when nothing was proven. That is INV-077's failure mode in a shipped scaffold, and it was
a real defect rather than a bookkeeping gap.

`_aggregate()` now emits `registry-quality-gate` beside the two arms, with the same verdict logic,
no container and no Python — the job branch protection depends on must not be able to fail for a
reason unrelated to the gates. The registry README gained a "Protecting `main`" section naming it,
because a stable name nobody is told about protects nothing (INV-075); a drift test reads the name
out of the emitted YAML rather than repeating the literal, so the two cannot separate.

**Mutations.** Five, each red only on the test stating the claim it breaks: deleting the
both-skipped branch; widening the allowlist to admit `cancelled`; dropping `if: always()` from the
emitted gate; deleting the README section while leaving the workflow intact; and giving the emitted
gate a container.

**Consequence.** INV-077 moves to EVIDENCED for both the repository's CI and the CI it ships to
others. The general form is the one D-152 already named: a row is not EVIDENCED because something
adjacent is green, and this time the audit found not only an untested claim but an unimplemented one
behind it.

Evidence/links: INV-077; INV-075; INV-076; INV-080; D-152;
`tests/aggregate_gate_test.py`; `.github/workflows/pr-check.yml`;
`agent_artifacts/registry_commands/templates.py`;
`docs/ci/pr-check-and-release-split-v1.md`.

## D-154 — A path-referenced consumer is authority the import graph cannot see

Date: 2026-09-03 · Slice: CP-18 step 3 · Status: accepted

**Context.** B-070 asks whether four modules listed as reachability exceptions are legacy. Three of
them — `domain/ports.py`, `domain/collections.py`, `domain/outcomes.py` — looked equally dead:
`tests/legacy_authority_reachability_test.py` builds an import graph from the two runtime roots and
reported all three unreachable, and each duplicated a vocabulary the shipped code already had
elsewhere. `domain/outcomes.py` in particular defines a `TerminalStatus` enum whose live
counterpart is `reporting/model.py`'s `SessionOutcome`, which carries a `no-op` state the domain
enum never had. On that evidence all three were removed.

**What the removal ran into.** The unit gate went red in `tests/release_test.py`, ten tests deep
inside `shutil.copy2`, with a bare `FileNotFoundError`. `scripts/release.py:31` declares
`SCHEMA_INPUTS`, a hand-maintained tuple of *paths* that the release contract hashes, and
`agent_artifacts/domain/outcomes.py` is one of them — pinned by sha256 in fifteen issued
`docs/release/schema-freeze-v*.json` documents including the live v18. Nothing imports the module;
the release contract reads it by path.

**Decision.** `domain/outcomes.py` stays. `ports.py` and `collections.py`, named by no freeze and
no importer, are removed. Reachability from the runtime roots is evidence about *imports*, and an
import graph is silent about every consumer that addresses a file by its path — a schema freeze, a
packaging manifest, a data file loaded at runtime. Unreachability is therefore a reason to *ask*
whether a module is legacy, never on its own an answer.

**Consequence.** Retiring `domain/outcomes.py` is a release-contract change, not a cleanup: it
needs a new `RELEASE_CONTRACT_VERSION` with its own freeze, its own compatibility and checklist
documents, and it must leave v18's frozen evidence untouched, per the immutability rule at
`scripts/release.py:22`. Filed as B-071. Two claims now hold the gap that let this happen:
`TheDeclaredSchemaInputsExistTest` states in the unit gate that every declared input exists — so
the next such deletion names the release contract instead of surfacing an errno — and asserts the
issued freeze covers exactly the declared path list. It checks paths and deliberately not hashes;
hashes are release-time evidence that legitimately drifts mid-cycle (three inputs drift from v18 on
this branch right now), and `make release-check` is where that is answered.

**Also worth keeping.** The first draft of this decision put an explanatory docstring at the top of
`domain/outcomes.py`, where someone about to delete it would read it. That edit changed the file's
sha256 and so broke the very freeze it was describing. A file pinned by content cannot carry the
note explaining that it is pinned by content; the note lives here and in B-071.

## D-155 — `profiles/loader.py` is an unwired invariant, not legacy

Date: 2026-09-04 · Slice: CP-18 step 3 · Status: accepted

**Context.** `profiles/loader.py` was the fourth and last of B-070's unreachable modules. Every
surface signal said legacy: no runtime importer, only three test files reach it, the Product
Specification never says the words "profiles.json", and the only documents describing the overlay
are `docs/design/DESIGN.md` and `docs/plan/PLAN.md` — which CLAUDE.md classes as historical
evidence rather than authority. Its own docstring dates it to WP-8.

**INV-001 reverses that.** "Enterprise-specific artifact definitions, policy values, profiles,
internal endpoints, credential references, and trust decisions live outside the public tool", and
the private-repository layout the specification draws holds a `profiles/` directory of per-tool
profile files. A profile that lives outside the public tool needs some mechanism to get in.
`profiles/loader.py` is the only such mechanism in the tree; `profiles/builtin.py` is the opposite,
a fixed set compiled into the public tool.

**Decision.** Keep it. The absence of the literal string "profiles.json" from the specification is
not evidence the capability is unwanted — the specification describes *what must be possible*, and
this module is the only implementation of one of those things.

**What is actually wrong is worth more than the deletion would have been.** Nothing calls it.
`consumer/runtime.py:947` passes `builtin()` straight into the `ConsumerContext`, so a project's
`.agent-artifacts/profiles.json` is parsed by three test files and ignored by the product. The
public tool currently admits no externally-defined profile at all, which is INV-001 unsatisfied,
not merely untested. Filed as B-072, and the INV-001 traceability row must carry it into CP-18
step 4 rather than being marked covered by the existence of `profiles/loader.py`.

**Consequence, and the general rule this makes explicit.** Three of B-070's four modules were
decided by the same question asked four times — *what shipped thing answers the question this
module claims authority over?* For `ports` and `collections` the answer was "thirty other Protocol
classes" and "nothing, it has no caller". For `outcomes` it was `reporting/model.py`, and the
module still stays for a reason outside the import graph entirely (D-154). For `profiles.loader`
the answer is *nothing does*, and a module that is the sole answer to a question the specification
requires an answer to is never legacy — however few things import it. An unreachable module is
either replaced, unadopted, or unwired, and only the middle case is safe to delete.

## D-156 — Docs reconcile against the parser, not against a reviewer's memory

Date: 2026-09-04 · Slice: CP-18 step 4 · Status: accepted

**Context.** "Reconcile docs with the Product Specification" invites a reading pass, and a reading
pass finds what the reader happens to notice. The three CP-18 steps before it were decided by
mechanical comparison against a shipped artefact — the import graph, the emitted YAML, the release
contract's declared inputs — and the same method applies to prose: a document that names a command
is making a checkable claim about the parser.

**Decision.** Read the command surface off `cli.build_parser()` and compare in both directions,
because the two failures are different failures. A command the README invents wastes a reader's time
at the shell; a command the README omits is capability nobody can find. The second is the one a
reading pass never finds, because nothing on the page is wrong.

It found `aart doctor` — the whole of CP-16, three verified steps, an entire top-level command —
documented nowhere in the README. Both directions are now held in
`tests/adoption_first_contact_test.py`, and the same comparison is applied to the *product's own*
strings: a diagnostic's remediation is documentation read at the worst possible moment, and it
drifts the way a page does with no reader to notice. Every command AART names in its own user-facing
strings does exist; that is now a claim rather than a coincidence.

**The first draft of the test was right for the wrong reason** and said so out loud: requiring a
backticked `` `aart <name> `` spelling made it report five commands the README documents perfectly
well inside fenced shell blocks. A test that reports true findings among false ones teaches the next
reader to skim it.

**What the sweep found beyond the README.** Two unlinked tutorials still used the flat 0.1 verbs
(`aart status`, `aart check`, `aart update`, `aart uninstall`) and pinned a wheel version in a
literal; `docs/installation/canonical-setup-v1.md` claimed "legacy `aart setup` remains available
during the staged 0.1.x migration", which `docs/release/compatibility-v8.md` had already recorded as
replaced. The largest was `docs/state/installation-state-v2.md`, which opens "This document records
the **implemented** STATE01/MIG01 boundary" and then describes a `prepare`/`apply`/`rollback`
migration service, a `LegacyMigrationCandidate`, an `aart migrate state` command surface and two
`state-migration-*` diagnostics — none of which exist. What ships is the opposite: the retired
envelope is detected and *refused* with `install-state-legacy`, whose remediation says the state is
"not converted at runtime". Its schema, path and transaction sections are still accurate, so the
document is bannered rather than deleted.

**Three root files were the sharpest case, because they are what a newcomer opens first.**
`PLAN.md`, `PROGRESS.md` and `TODO.md` are the completed `M1F1/agent-artifacts` 1.0 program, cited 75
times between them, and `TODO.md` opened by stating that its GitHub issues "remain the source of
truth for discussion and status" — pointing at a repository the execution contract names as legacy.
CLAUDE.md classifies them correctly, which does nothing for a reader who never opened CLAUDE.md, so
the documents now say it themselves and a test holds both halves.

**Consequence.** Where a doc and the code disagree, the check belongs in the gate, not in a review
comment. Where a document is a design record rather than shipped behaviour, it says so in its own
first paragraph, since the alternative is that its accuracy depends on the reader already knowing.

**What this method cannot do.** It compares names. A page whose every command exists can still
describe behaviour those commands do not have, and no parser comparison will say so. That is step
5's subject, and the remaining PARTIAL rows are where it gets answered.

## D-157 — An architectural boundary is a reachability claim, not a behavioural one

CP-18 step 5 audited INV-062/064 (the TUI is a projection and does not implement infrastructure) and
INV-149/152/158 (presentation detail does not select a planner, a policy path or an effect). Both
already had behavioural evidence and both were unheld.

The screen tests asserted what a given frame contains. A screen that grew a `subprocess.run` would
still render correctly and every frame assertion would still pass. The presentation tests asserted
that switching Fast to Verbose changes neither the selection, the review digest nor the machine
payload — over generated plans, which is strong — but a policy path that *read* the preference and
branched on it would satisfy every one of them for as long as the two branches happened to agree.

**Decision.** Where an invariant says a layer must not *be* something, or must not *know* something,
state it over the layer as reachability and let the behavioural tests keep doing their own job:

- `tui_boundary_test.py`: no screen module imports infrastructure, reaches `agent_artifacts.io`
  outside the one declared seam, imports dynamically, or branches on the host platform; and the
  whole layer imports with `curses` absent.
- `presentation_is_not_semantics_test.py`: no module under `domain/`, `security/`,
  `configuration/`, `installation/` or `application/` may name a presentation profile at all, the
  one exception being the module that declares the type.

Both are stated over a directory rather than a list of module names, because a list is a second
place to forget and goes stale in the same direction as the code it guards. Both carry a positive
probe — the detector must find the thing where it legitimately appears — so an absence assertion
cannot pass by matching nothing (D-149).

**The corollary that cost the most to learn.** INV-066 forbids a screen deciding anything from the
platform. The first draft searched the source text for `sys.platform`, and a screen carrying
`__import__("sys").platform` survived it, while `view.platform` — the platform arriving as data from
the core, which is exactly what the invariant wants — had to keep passing. Text search finds a word;
the invariant is about a dependency. The check is now read off the syntax: an attribute access on
`os`, `sys` or `platform`, or on a dynamic import, with dynamic imports separately forbidden so the
static sweep can be complete.

## D-158 — Coverage is not the reason a claim is held, and the two gaps this step found prove it

Both of the sharpest findings in step 5 were in code that every suite executed on every run.

`render_ready(view, VERBOSE)` returns `_verbose_plan(view)` — the same function the non-interactive
review uses — so `aart install` printing a plan and the shell drawing screen 09 produce the same
bytes. That *is* INV-061, "one core, multiple skins", in one line of code. Both paths were exercised
constantly by different tests; nothing compared them, so screen 09 could have drifted from the
reviewed plan and the drift would have shown up as two green suites.

`configured_offers.py` declines a referenced approved version by name, and
`configured_installation.py` refuses to materialise one. Both lines ran in the composition E2E.
Neither refusal was asserted, so the seam that keeps content the registry holds no verified bytes for
out of the Marketplace could have been deleted in silence (INV-025).

**Decision.** When auditing an invariant, look for the assertion, never for the execution. The
question is not "does anything run this?" but "what would notice if this stopped being true?" A line
that ran is not a line whose behaviour anything asserts, and the second question is the only one the
traceability matrix is allowed to answer with EVIDENCED.

## D-159 — A superseded state is better made unconstructible than merely detected

INV-239 requires that an unchanged rejected candidate stays rejected while a material source change
reopens review. The mechanism is that `candidate_id_for` derives the id from the artifact's input
digest, so identical source produces the identical id and `reconcile_source_scan` reuses the prior
record whole.

Two mutations were run against the new test. Skipping the reuse branch turns it red, as intended.
The second — re-deriving the rejected candidate as `CHANGED`, which is the defect an operator would
actually experience as "rescanning gets you a second opinion" — cannot be constructed at all: the
`Candidate` invariant refuses it, because only a rejected candidate may carry a rejection reason.

**Consequence.** Where a lifecycle state carries evidence that only that state may hold, the type
refuses the laundering rather than a test noticing it afterwards. Prefer that shape when adding
lifecycle states: give the state a field only it can carry, and the illegal transition stops being
a bug to catch.

## D-160 — The version is not a value to reconcile; it is a value to have once

INV-085 forbids "multiple independently maintained version values plus tests whose only purpose is
synchronizing them". The obvious reading is that the tests are the problem, and the obvious fix is
to let the release engine write all three values through `extra-files` — one engine, three files,
no human keeping them in step. That reading is wrong. Three generated values still need a test to
notice when the generation misses one, and that test has the same only-purpose the invariant names.

**Decision.** There is one literal: `agent_artifacts/__init__.py`. `pyproject.toml` and `README.md`
are rewritten by the engine on annotated lines, and `runtime_contract.EXECUTABLE_VERSION` *parses*
`__version__` rather than declaring its own. `scripts/version.py`, its `_MIRRORS` table and the
`validate` gate's `version.py check` are deleted.

**What replaced the synchronization test is a different claim.** Not "the copies agree" but "no
file quotes this release that the release engine does not write" — a scan of `pyproject.toml`,
`agent_artifacts/` and `scripts/` for a version declaration whose value is the released version,
checked against the `extra-files` list. It fails on a *new* copy appearing, which is the thing that
actually goes wrong; the old test could only fail after someone had already forgotten to edit one.

## D-161 — An issued freeze's release version is the freeze's data, not a mirror of a version

D-154 established that an issued schema freeze is immutable. It records `release_version`, and
`schema_freeze_bytes` used to regenerate that field from `scripts/release.py:EXPECTED_VERSION` —
which meant the pin had to exist for the freeze to be checkable at all, and a version bump made the
freeze stale for a reason that had nothing to do with schemas.

**Decision.** `schema_freeze_bytes` reads `release_version` back out of the freeze it is being
compared against. `release.py freeze --write` takes `--release-version` only when issuing a freeze
that does not yet exist, and refuses rather than inventing one. `schema-freeze-stale` therefore
means exactly one thing again: a normative schema moved.

## D-162 — A release run's subject is the artifact, and the tag is what it is checked against

The tag pipeline used to prove that a version pinned in a script matched a version written into
three source files matched the tag somebody pushed. Every one of those is a property of the source
tree, and the pull request that put the tree on `main` had already proven the tree.

**Decision.** `scripts/release_artifact.py` checks the wheel: its filename, its metadata name and
version, its `Requires-Dist` lines, and — through a real install into a throwaway environment —
what `aart --version` says. The metadata and the program are asked separately on purpose: they come
from different places, so a build that packaged the wrong tree agrees with itself everywhere except
there.

## D-163 — The engine's event silence is a design constraint, and the answer outlived the button

GitHub raises no workflow event for anything done with the repository `GITHUB_TOKEN`. The retired
release button hit this and answered it by *calling* the release action rather than waiting for an
event. Release Please creates its tag and release with the same token and is silent in the same way.

**Decision.** `release.yml` is `workflow_call`-able, and `release-please.yml` calls it when the
release-please step reports `release_created`. The event triggers stay for a tag a person pushes.
The alternative — a personal access token so the events fire — buys the same behaviour for the cost
of a secret every fork has to provision.

## D-164 — The title gate reads its accepted types from the release configuration

`scripts/conventional_title.py` could have carried its own list of Conventional Commit types. Then
the interesting failure would not be "a title nobody can classify" but "the gate and the engine
disagree about what `security:` means", which is a bug with no symptom until a release comes out
wrong.

**Decision.** The accepted types are read out of `release-please-config.json`'s
`changelog-sections`. One file says which types exist and what each is called; the gate is a reader
of that policy rather than a second copy of it. A test asserts the two sets are equal, which is
cheap precisely because it can only fail if someone reintroduces the second list.

## D-165 — Mutation testing gets an explicit workflow and deliberately no schedule

INV-103 asks that expensive verification not lengthen mandatory pull-request feedback. The ten
gates, including the property suites and the whole end-to-end lifecycle, run in about four minutes
and fit that budget, so they stay on the pull request. Mutation does not fit it: mutating this
repository whole is days of compute (D-134).

**Decision.** `.github/workflows/deep-quality.yml` runs `scripts/mutants.py` on
`workflow_dispatch`, over a module the dispatcher names. There is no schedule. A weekly run would
have to pick a module, the pick would be arbitrary, and an arbitrary survivor count produced every
Monday is a number nobody reads. Mutation answers a question about a specific module's tests, and
it is worth running when somebody has that question.

## D-166 — Mutation scope owns its source roots, and unattended tooling must be locked

Date: 2026-09-04 · Slice: CP-18 steps 5–6 · Status: accepted

The first scoped run against `scripts/release_artifact.py` did not mutate that module. The runner
still wrote `source_paths = agent_artifacts`, so mutmut copied the runtime package, generated zero
useful mutants for the requested script and then failed collection because the script was absent.
`ONLY` looked authoritative while a second hard-coded scope silently overruled it.

**Decision.** `scripts/mutants.py` derives the top-level source roots from every repository-relative
path in `ONLY`; multiple requested trees become multiple `source_paths`, and absolute or parent-
traversing paths are refused. Script tests import `scripts.*` by its real package name so the module
identity is the same in the repository and mutmut's copied tree. The focused release-artifact run
then generated 373 mutants rather than zero.

The same increment changed B-068's classification. Mutation remains advisory and manually scoped,
but `.github/workflows/deep-quality.yml` now promises to run it unattended. A dev dependency absent
from `poetry.lock` would therefore make the published workflow fail before it could answer its own
question, which is critical to CP-18's closing gate rather than a local-tooling nicety.

**Consequence.** The lock is regenerated and carries mutmut 3.7 plus Textual. The dependency has a
dev-only `python >=3.10,<4.0` marker: Textual's supported range must not make Poetry reject AART's
deliberately open-ended runtime range, and no mutation dependency enters the runtime graph.

## D-167 — Release verification includes the clean public matrix, not only the maintainer host

Date: 2026-09-04 · Slice: CP-18 step 6 · Status: accepted

The first pull-request run after CP-18 closed failed on Linux/Python 3.10, 3.11 and 3.14 even though
all local gates were green. The failures were independent: `scripts/dev_tools.py` installed the
backend but not the Poetry executable the wheel gate invokes; Python 3.10 lacked stdlib `tomllib`
and rejected RFC 3339's `Z` suffix; scripted Keychain tests still asked the real host whether macOS
Keychain existed; configured setup supplied a Darwin request to the Linux runtime; and isolated
Marketplace request-mapping tests accidentally consulted the maintainer's real configured source.

**Decision.** A release gate is verified only after its supported public OS/interpreter matrix has
run in clean environments. Poetry itself is a locked dev dependency, with dev-only `tomli` making
the build script support Python 3.10. Timestamp parsing normalizes only a terminal `Z` to `+00:00`.
`MacOsKeychainProvider` retains the real platform and executable check as its default but accepts an
injected host-availability probe for scripted adapter tests. Fixtures must inject their intended
runtime/configuration rather than inherit the machine running them.

**Evidence.** Before the implementation, the new tool-presence test failed and the Keychain probe
test could not construct the adapter. Afterward the focused 88-test set and a real wheel build pass
in clean Linux containers on Python 3.10, 3.11 and 3.14; the complete nine-gate quality runner also
passes all three arms over 3,322 tests. No runtime dependency, Keychain availability verdict, or
quality threshold changed.

## D-168 — Global navigation is permanent chrome; contextual keys remain in help

Date: 2026-09-04 · Increment: B-077 manual acceptance · Status: accepted

The canonical shell carried a complete `_HELP_LINES` table behind `?`, but drew no indication that
help existed. This made the key reference circular: a first-time user had to know the undocumented
help key in order to discover the keys. Product Specification 161.1 names the global interaction
vocabulary and INV-187 protects its navigation semantics; discoverability cannot depend on prior
knowledge of that vocabulary.

**Decision.** Every frame ends with one concise footer naming arrows, Enter, Space, Esc, `?` and
`q`. Space belongs there because it is the shared selection/toggle control across lists, settings
and forms. Contextual operations such as install, sync, repair and search stay in the expanded `?`
help instead of making the permanent line change unpredictably between screens. The curses adapter
pins the frame's final line below the body, reserving it before clipping long content. The text
adapter renders the same frame and may additionally explain how a line-oriented terminal spells
arrow and escape keys.

**Evidence.** The first-frame test failed with the dashboard's `none yet` line in the footer
position; the terminal-placement test failed with a clipped body row there. Both were observed red
before implementation. The focused consumer shell, canonical entry, text-terminal and layout suites
pass 67 tests without changing key interpretation or application state.
All nine quality gates then pass over 3,324 tests at 85.35% branch coverage, followed by the
separate 343-test integration run.

## D-169 — Esc latency is terminal protocol configuration, not application work

Date: 2026-09-04 · Increment: B-078 manual acceptance · Status: accepted

The reducer turns `escape` into Back immediately, but curses cannot emit that name until it decides
whether the byte begins a longer terminal key sequence. Inheriting ncurses' long default made every
Back look like an expensive machine reload even though the application had not received the event.

**Decision.** Configure the curses escape-prefix delay once, at its entry boundary, to 50 ms before
starting the shared shell. `key_event` remains the only interpreter and text fallback is unchanged.
The value is short enough for an immediate local Back while leaving a small window for a terminal's
multi-byte arrow/function-key sequence.

**Evidence.** The focused entry test patched the real curses setting and was red because it was
never called; it now requires a value no greater than 100 ms. The five related suites pass 53 tests.

## D-170 — First-run guidance names only a setup route that actually exists

Date: 2026-09-04 · Increment: B-079/B-080 manual acceptance · Status: accepted

Dashboard destinations used Product Specification vocabulary without explaining it, and a machine
with no sources displayed only zero counts. Automatically navigating to empty Registries would not
solve that: accepted screen 21 supports visibility and synchronization, while the canonical TUI has
no URL-entry surface (B-075). Advertising an Add button would promise an action the product cannot
perform there.

**Decision.** The Dashboard projects one short static purpose statement for the row under its
cursor. When both the configured-source projection and registry count are empty, its normal metrics
are replaced by a compact first-run panel explaining AART. Manual acceptance subsequently moved
that panel above navigation and made the missing-source action a `SETUP REQUIRED` callout pointing
to Registries → Add Registry (D-171). Empty Registries repeats that same honest route. These are
presentation choices over the
already-composed screen snapshot; drawing reads no configuration and derives no policy or health.

**Evidence.** Three headless shell tests were red against the previously unexplained/blank surfaces:
the description changes when the cursor moves, the first frame explains AART and the missing source,
and Registries names the real command. The five related suites pass 53 tests.

## D-171 — Registry onboarding reuses source-add authority; local paths remain Sources

Date: 2026-09-04 · Increment: B-082 manual acceptance · Status: accepted

Product Specification 161.7 presents connected and not-connected registries as the consumer's
Marketplace availability surface. Sending a first-time user from that screen to a multi-flag CLI
command made the persistent application incomplete. At the same time, 164.2 is explicit that a
Source is an authoring/discovery location rather than an approved registry, and the configuration
schema intentionally refuses local paths for `registry-git`.

**Decision.** Screen 21 owns Add Registry for approved remote Git registries. Its pure reducer holds
only alias, credential-free URL, branch/tag and default choice, then binds those exact values to a
review digest. Confirmation crosses one injected action boundary. Both CLI and TUI call
`commands.source.add_configured_source`, which retains source-schema validation, policy planning,
fresh immutable snapshot validation, stale-review detection and the checked configuration write.
The TUI re-reads effective configuration, Marketplace offers and Maintainer projections after the
write; draw functions still perform no IO. `source-local` and `source-git` remain Maintainer
authoring choices and neither security boundary is widened.

**Evidence.** `consumer_registry_addition_test` was first red because no form type or route existed.
It now holds navigation, exact command values, whole-line text fallback, the shared transaction
call, refresh after confirmation and refusal of a local path before any connector runs. The CLI's
source-add suite remains green after extracting its typed surface-independent result.

## D-172 — Whole-product manual acceptance has one procedure and one finding queue

Date: 2026-09-08 · Increment: post-refactor manual acceptance · Status: accepted

The automated acceptance suites prove individual public flows, but an operator now needs to
exercise one continuous chain across real Git repositories: authoring, source synchronization,
promotion, reviewed Git publication, consumer installation, update, drift, repair and removal.
Keeping that procedure in chat would make it neither repeatable nor available to the next agent.
The root `TODO.md` already exists, but its body is a historical tracker for the old
`M1F1/agent-artifacts` program and cannot become product authority for this repository.

**Decision.** `docs/testing/END_TO_END_ACCEPTANCE.md` is the repeatable operator procedure for the
whole-product pass. It isolates maintainer and consumer state, names checkpoints for each stage and
keeps publication behind Git review and merge. The first section of root `TODO.md` is the single
current queue for findings from that procedure. Historical content remains below it unchanged as
evidence. Neither document supersedes the Product Specification or the critical-path tracker in
`docs/refactor/NEXT.md`.

**Evidence.** The documentation check accepts both documents and every finding already raised in
the first manual pass is represented once as QA-001 through QA-008, awaiting operator retest.

## D-173 — TUI-first acceptance names its CLI fallbacks instead of hiding missing screens

Date: 2026-09-08 · Increment: post-refactor manual acceptance · Status: accepted

The operator wants the real external-Git acceptance chain to exercise the TUI, with author
manifests written as `aart.yaml`. Surveying the key and action graph found two preconditions the TUI
cannot currently produce: adding an authoring Source, and refreshing a consumer Registry after a
new publication. Substituting an unmentioned CLI call would let the later screen appear while
falsely claiming the interactive chain was complete.

**Decision.** The machine-specific local walkthrough uses TUI for every implemented product action
and YAML for both manifests. Each unavailable action is a separately named, minimal CLI bootstrap,
marked at the exact point it occurs and tracked as B-083/QA-009 or B-084/QA-010. Add Registry is not
widened to authoring Sources: registry trust and Source discovery remain different concepts.

**Evidence.** `key_event` routes `a` only from Registries, while `SOURCE_SYNC` is reachable only from
Maintainer Sources and Source Details. No consumer Registry screen produces a sync command. The
local walkthrough is excluded through `.git/info/exclude`; durable findings remain in repository
documentation.

## D-174 — A named harness is not supported until its native contract is measured end to end

Date: 2026-09-08 · Increment: post-refactor OpenCode acceptance · Status: accepted

The old built-in profile names plausible OpenCode paths, while the canonical target tables omit
OpenCode entirely. Treating the old record as ready to copy would appear to close the gap, but the
current OpenCode MCP schema already proves it is not a faithful adapter: local servers require a
typed object and command array that the generic canonical registration cannot express. The TUI
also derives its fixed target set from the MCP table and offers no harness selector.

**Decision.** OpenCode remains an honest, named refusal until a dedicated vertical slice measures
its current Skill, rule/memory, MCP and plugin contracts against a real installed OpenCode. That
slice must introduce the native registration shape and TUI harness selection together; dormant
profile data is evidence for reconnaissance only. The manual acceptance guide declares OpenCode in
both YAML manifests, proves the present refusal writes nothing and continues Claude/Tabnine testing
without calling it OpenCode coverage.

**Evidence.** On the acceptance Mac, OpenCode 1.18.29 reports its real config/data paths. Direct
lookups for project/user MCP, Skill, guideline, memory and hook targets all raise the corresponding
`no measured ... target` refusal. Official OpenCode source documentation confirms the Skill and
AGENTS.md locations and the native `mcp` object shape. B-085/QA-011 carry the implementation gap.

## D-175 — Codex support is a native harness slice, not a Claude alias

Date: 2026-09-08 · Increment: post-refactor Codex acceptance · Status: accepted

Codex appears in authoring and test data as a compatibility label, but no canonical target table or
built-in profile gives that label installation meaning. Reusing Claude paths would make an install
look successful while writing Skills, instructions or MCP configuration to contracts Codex does not
own.

**Decision.** Codex is tracked separately from OpenCode as B-086/QA-012. Its implementation must be
measured against the installed Codex CLI and use Codex-native `.agents/skills`, layered `AGENTS.md`
and `mcp_servers` TOML contracts. Common effect machinery may be reused, but neither another
harness's paths nor a generic registration shape is accepted as evidence. TUI harness selection,
reconciliation, uninstall and a real Codex invocation belong to the same vertical slice.

**Evidence.** The acceptance Mac runs Codex CLI 0.152.0. `codex` is absent from all four canonical
target tables and from `profiles/builtin.py`, while the TUI derives its two choices from the MCP
table. Official Codex documentation independently names the Skill, instruction and MCP contracts
the slice must measure.

## D-176 — Authoring-Source admission is manifest discovery, not native-package validation

Date: 2026-09-08 · Increment: post-refactor manual acceptance, B-094/QA-020 · Status: accepted

`source add --kind source-git` validated every acquired tree through `load_native_source`, which
is the loader for a *consumer* native package tree: a root `aart-source.json`, then
`<root>/<kind>/<name>/artifact.json` and `payload/`. A real authoring repository declares none of
that. It declares an `aart.yaml` beside the files that manifest names, which is exactly what
Product Specification 72.1 says an author opts in with. The public entrance therefore refused the
accepted Source → Candidate → Promotion flow before manifest discovery could run at all, and
adding `aart-source.json` to the author's repository only moved the refusal to the package loader.

**Decision.** Authoring Sources (`source-git`, `source-local`) are admitted by
`validate_authoring_source_candidate`, which reads the tree as whichever of the two formats it
declares itself to be. A tree carrying a root `aart-source.json` is still judged by
`load_native_source`, unchanged — claiming the marker is not a way to skip its loader. Any other
tree is admitted when `discover_author_manifests` finds at least one explicit `aart.yaml` or
`aart.json`, and refused with a remediation naming both formats when it finds none.

Admission is deliberately discovery, not compilation. Specification 164.2 shows an admitted Source
whose list entry reads `3 manifests · 1 invalid`, so an invalid manifest is a Candidate state that
Source Sync reports, not a subscription this refuses (INV-199). Requiring every manifest to compile
would move a Candidate verdict into the subscription gate.

No safety boundary moved. Symlinks and special entries cannot reach validation at all:
`source_snapshot_digest` refuses them and `SourceCandidate` will not construct without that digest.
Transport, size limits and revision pinning stay the acquisition adapter's, already applied before
this runs; the E2E fails itself if the production path ever asks for weakened transport. Discovery
still refuses a manifest that is not a regular file and a boundary declaring both spellings at once.

**Identity.** An authoring repository declares no identity of its own, so its `declared_source_id`
is its configured alias. Nothing in such a repository has the job of saying "this Source is X", and
deriving one from the URL or the content would make an ordinary upstream commit look like the
Source becoming a different Source. The alias is already the identity the Candidate model uses:
`compile_author_source` stamps candidates with `source_alias` and the Maintainer screens key their
history by it. Naming the same thing here keeps identity single-valued and leaves the
identity-transition check inert for a Source that has no declared identity to move.

**Marketplace.** An authoring Source now projects an *empty* contribution to the consumer
Marketplace rather than refusing. The consumer projection loop returns on the first `Err`, so the
old refusal meant one subscribed author repository emptied the whole Marketplace of the consumer
who subscribed to it. A Candidate is not approved content (INV-199); it contributes nothing, and
"nothing" has to mean an empty projection. A tree that claims `aart-source.json` and is broken
still fails closed, and `consumer_runtime_test` holds both halves side by side.

**Evidence.** `tests/authoring_source_admission_e2e_test.py` drives a real temporary Git repository
whose only declaration is `skills/verification-before-completion/aart.yaml` through the real public
command, then through the same configured composition the Maintainer Source Sync screens call:
add → sync → one Candidate → durable history → a later upstream commit reported as movement →
selected promotion written into the local approved registry. `tests/source_validation_test.py`
states the admission rule as a Hypothesis property over generated trees. Five targeted mutations
(admit-anything, marker-inverted, projection-always-empty, identity-constant,
discovery-ignores-yaml) were each killed by the test that names the claim.

## D-177 — Add Source is its own Maintainer form, not a widening of Add Registry

QA-009/B-083. Maintainer → Sources could synchronize and inspect a configured authoring Source but
could not create one, so the TUI could not build the precondition its own Candidate and Promotion
screens consume. The obvious economy — teach screen 21a's Add Registry form to also accept
`source-git` — is refused. A Source is an authoring/discovery location and a Registry is approved
canonical content (Specification 164.2, INV-199); one form producing either would put the two on the
same trust footing at the exact place the operator chooses between them.

Add Source is therefore a separate pair of Maintainer screens, `31a-add-source` and
`31b-review-source`, numbered the way screen 21's own addition pair is, reached with `a` from
screen 31 and unreachable from consumer Registries. They carry a separate `SourceDraft`
(alias/kind/location/ref), a separate `ConsumerActionKind.SOURCE_ADD`, and a separate
`SourceConnectionPort`. Space cycles the kind between exactly the two members of
`AUTHORING_SOURCE_KINDS`; `_prepare_source_addition` refuses any other kind by name, so a
`registry-git` value reaching this action is a refusal rather than a second way to add a Registry.
`ref` is passed only for `source-git` and rendered `not applicable` for `source-local`.

Execution goes through `add_configured_source`, the same transaction the CLI's `source add` uses.
Nothing about connection, transport or validation is re-implemented for the TUI: the form's only
job is to build the request and show the exact review before the operator confirms it, which is
what keeps the widened admission of D-176 single-authority.

**Evidence.** `tests/maintainer_source_addition_test.py` holds the interaction (Space cycles only
the two kinds, Enter reviews before running, a refusal does not run) and the composition (the real
`tui.py` closure reaches `add_configured_source` with the form's own alias, kind, location and ref,
and never sets `source_make_default`). The composition test runs both kinds, because with only
`source-git` a hardcoded `source_kind` constant is invisible — that survivor is what the fifth
targeted mutation found. Five targeted mutations (a-key-ignored, registry-git-allowed,
default-registry-set, kind-hardcoded, space-does-not-cycle) are each killed by the test that names
the claim.

## D-178 — A first run is a machine with nothing, and reporting is resolved when an install completes

Two regressions the uncommitted manual-acceptance work had left in the tree, found by running the
suites the changed modules belong to rather than only the suites the new slices added.

**First-run guidance.** B-080 gated the welcome panel on `not screens.registries and
registry_count == 0`, and the panel *replaces* the Dashboard body rather than joining it. A machine
with no configured source but an installed artifact — a direct install, or a source since removed —
therefore lost its own counts to a welcome message. Getting this condition wrong does not merely add
a panel; it takes away the one thing the Dashboard exists to state. The condition now also requires
`installed_count == 0`, and `consumer_shell_test` holds the negative case beside the positive one.

**Deferred reporting.** The registry-connection work moved `load_local_reporting_service` out of
`_canonical_consumer_actions`' body and into `completion_factory`, so that an install authorized by
a registry connected mid-session is reported under the configuration that authorized it rather than
the snapshot taken before onboarding. That is the correct production behaviour and it is kept. What
it broke was a test seam: `configured_setup_report_test` substituted the loader only around
composition, so after the move the shell ran against the real service and previewed nothing. The
substitution now spans the run. No assertion changed, and mutating the resolved service back to
`None` still turns that test red.

## D-179 — Refreshing a connected Registry is its own action, and it is not an artifact update

`QA-010`/`B-084`. Screen 21 projected `("details", "sync")` for every connected registry row and
routed neither: `s` was interpreted only on the Maintainer authoring-Source screens, so the one
CLI fallback (`aart source sync`) was the only way to receive a newly published registry commit.

**A separate action, for the same reason D-177 kept Add Source and Add Registry apart.** Screen 21
now has `ConsumerScreen.REGISTRY_SYNC = "21c-sync-registry"` and
`ConsumerActionKind.REGISTRY_SYNC`, distinct from the Maintainer `SOURCE_SYNC`. INV-199 is what
makes them distinct rather than one parameterised action, and the boundary is testable rather than
asserted: `_prepare_registry_refresh` declines an alias that is not a connected row *and* declines
a row whose `is_registry` is false, so an authoring Source reaching screen 21's action is a
refusal.

**The review says what sync is not.** PS §161.7 is explicit that registry sync is not artifact
update — a sync may discover `github-mcp 1.6` while an installed `1.5` stays exactly as it is — so
screen 21c states that in the review the operator confirms, along with which ref will be fetched
and that a failed fetch keeps the snapshot already held. Naming the ref required threading
`ConfiguredSource.ref` through `MarketplaceSourceView` and `RegistryView`: `RegistryView.revision`
is the resolved commit, which answers a different question than "what will be fetched".

**One transaction.** `sync_configured_sources` in `commands/source.py` is now the single
transaction behind both `aart source sync` and screen 21c, so the TUI re-implements no part of
fetch, verification or last-known-good retention. On `Err` the action reports the failure and
leaves the context untouched, which is the last-known-good boundary held at the port rather than
restated in the renderer.

**Evidence.** `tests/consumer_registry_refresh_test.py` holds the interaction, the review text, the
composition against the real `tui.py` closure and the navigation. Targeted mutations that had
survived — no test held the authoring-Source refusal, and the alias was free to be a constant — are
killed by the refusal test and the two-alias composition loop.

## D-180 — Usage-reporting scaffolding is generated only when a destination is named

`QA-013`/`B-087`. `registry init` always wrote `.github/ISSUE_TEMPLATE/usage-report.yml` and
`.github/workflows/aart-usage-dashboard.yml`, and the generated README described a reporting
workflow that the registry had not opted into. The files said they were inert, which is worse than
absent: a maintainer reading a fresh registry cannot tell a deliberate feature from a default.

`REPORTING_TEMPLATES` is now conditional on `options.usage_reporting_repository is not None`, and
`render_registry_readme` takes `usage_reporting` so the README describes the registry that was
actually created. Naming a destination is the opt-in; there is no separate flag to keep in sync
with it.

`test_init_never_overwrites_an_existing_reporting_template` still holds — it opts in, because
without an opt-in there is nothing to overwrite — and is joined by
`test_a_declined_init_leaves_an_unrelated_issue_form_alone`, so the no-clobber claim is held on
both sides of the choice rather than weakened to fit it.

## D-181 — An empty registry's audit reports what does not apply, and init stops warning about what it no longer writes

`QA-015`/`B-089`. `aart registry audit` on a freshly initialized registry passed and then printed
two warnings: that provenance coverage was partial, and that no per-object installation-risk
evidence had been supplied. Both are true of a registry with nothing in it, and neither is a defect
of one — the first thing an operator sees after creating a registry should not read as two problems
they cannot fix.

`REGISTRY_AUDIT_NOTE` already existed for exactly this distinction: a report of what the audit did
rather than what it found, carrying no remediation because there is nothing to remedy. It is what
`_upstream_check_note` already used to say there were no vendored artifacts to check. Both findings
now use it when the registry holds neither an external reference nor an owned package, and stay
warnings the moment either exists — with one package present there really is an object whose risk
nobody assessed.

Deciding this required knowing whether the registry owns any packages before the first finding is
emitted, so the artifact-root scan moved above it into one `owned` tuple that the per-package loop
then consumes. That made the root filter load-bearing for the empty/occupied distinction, and
`test_a_manifest_outside_the_declared_roots_is_not_a_package_of_this_registry` holds it: a valid
`artifact.json` outside the roots `aart-source.json` declares belongs to something else and must not
make an empty registry look occupied. The neighbouring symlink test records the stronger boundary it
sits behind — a workspace containing any symlink is refused whole, before any per-file check runs.

`registry init` also stopped warning that the usage-reporting templates were inert. After D-180 it
does not write them unless a destination is named, so the warning described files that no longer
exist; warning that an unchosen optional feature was not chosen is the same non-finding this entry
removes from the audit, and the init review is read in the TUI, where a flag name is not an action.
`docs/reporting/usage-reporting-v1.md` and `LA-R-01` are corrected to the behaviour.

**Evidence.** `tests/registry_empty_audit_test.py` (7 tests) and the amended
`tests/curation_runtime_test.py`. Six targeted mutations — ignoring `owned`, never reporting
not-applicable, keeping either finding a warning, dropping the root filter, and giving `_note` a
warning severity — are each killed. Verified through the public CLI: `registry init` writes six
paths and no reporting templates, and `registry audit` prints `passed` with two `info` lines.

## D-182 — A confirmed Maintainer action states its result once

`QA-014`/`B-088`. A confirmed `registry init` printed about twenty lines, most of them said twice.
The review and the outcome are two renderings of one run, and they overlapped: every warning the
plan carried was carried again by the result, `observed: 6 review paths` restated the headline that
had just counted the same six, and the first follow-up command re-listed all six paths a third
time. The operator's question after a mutation is whether it worked and what to do next, and that
answer was the hardest thing in the output to find.

**Three removals, no hiding.** `render_curation_outcome` takes the `CurationReview` it finalizes and
states only the warnings that review did not already state — a warning the finalization itself found
is always news and always printed. The `observed:` line is suppressed when it equals
`changed_paths` and kept when it differs, because a read-only action that changes nothing and
observes drift is exactly what that line exists to report. `_follow_up` no longer leads with
`git -C … diff -- <every reviewed path>`: `render_curation_review` already closes a mutating action
with "AART will not commit or push; review the working-tree diff afterward", which is the same
instruction without the repetition — and without a shell command, which is also what keeps screen 46
free of one when `QA-017` gets there.

The `--json` envelope is untouched and still carries the review and the outcome in full, so nothing
left the record; what left is the second printing of it.

**Evidence.** `tests/curation_outcome_brevity_test.py` holds the renderer's claims on both sides —
a stated warning is not restated, an unstated one is, an equal `observed` is dropped and a differing
one kept, and the follow-up tuple is the AART pipeline for both branches.
`tests/registry_cli_integration_test.py` holds the composition through the public CLI: a confirmed
human init prints no duplicate warning line, no `observed:` line and no `git -C`. Seven targeted
mutations, including the one that found the composition claim unheld (finalization dropping the
review it passes to the renderer), are each killed.

## D-183 — A refused Git entry names its kind and what to do about it

`QA-019`/`B-093`. The Superpowers fork had a root `AGENTS.md` committed as a symbolic link, and
`source add` said `Git tree contains an unsafe entry: 'AGENTS.md'`. That is true, correctly
fail-closed, and unusable: a symlink, a submodule, an unreadable Git mode, an unsafe path and a
too-deep path all produced the same sentence, so the operator could not tell which correction their
repository needed.

**The rule did not move.** `_unsafe_entry` refuses exactly what `_tree_listing` refused before —
anything that is not a `blob` at mode `100644` or `100755`, under a safe relative path, within the
configured depth. What changed is that each case says which one it is and carries remediation:
replace the link with a committed regular file, commit the submodule's files or subscribe to that
repository separately, use a plain relative path, re-commit as an ordinary file, or move the entry
nearer the root.

**The link target is still never printed.** It has not passed the repository's path-safety rules,
and reading or echoing an unreviewed path is the thing this boundary exists to prevent. The
remediation says what to do without naming where the link points.

One real mislabel was fixed on the way: `ls-tree -l` reports `-` rather than a size for a gitlink,
and the old code parsed the size before deciding the entry kind, so every submodule was reported as
a malformed listing. The kind is now decided first.

**Evidence.** `tests/git_unsafe_entry_diagnostic_test.py` holds each kind, the "never name the
target" rule and the two modes that stay accepted; `tests/authoring_source_admission_e2e_test.py`
holds it through the public `source add` against a real repository with a real committed symlink.
Nine targeted mutations are killed — including one that found the E2E asserting less than it said,
because "symbolic link" appeared in the remediation and the assertion read the whole envelope; it
now reads the message.

## D-184 — A declined preparation returns to where the action was asked

`QA-018`/`B-092`. Add Registry navigates to Review and *then* asks the adapter to prepare the exact
transaction, because consent is given on that screen. When preparation refused — a duplicate alias,
an origin already connected — `_declined` cleared the pending action and reported a decline with no
review digest, and `_action_prepared` correctly refused to record that as a plan. It then left the
session on Review, which went on saying "press Enter to connect". Enter reached the execution
boundary with nothing pending and answered "nothing was prepared for this action".

`_declined_preparation` now pops the session back to the screen the review was opened from and
clears `state.action`, so a later Enter cannot reach a confirmation at all — the reducer has nothing
to confirm, and the guard in `_confirm_action` is no longer the only thing standing between a
refusal and an execute command. For a form this lands on the form, with everything the operator
typed still in `registry_draft`, which is B-092's "correctable form input" repair; Esc from there
still returns to Registries.

**The refusal had to become visible where it now lands.** `_ANSWERABLE` listed only the screens
`_request_action` and `_confirm_action` move *to*, so after this change the notice would have been
drawn on a screen nobody was on any more. It now also includes `ACTION_REQUEST_SCREENS`, derived
from `_ACTION_REVIEW`'s own keys rather than hand-listed a second time: a second copy of the same
set is a set that drifts, and the symptom of that drift is a refusal nobody can see.

**Two E2Es changed, and their names were already on the new side.**
`test_an_offer_that_is_no_longer_there_is_refused_where_it_was_asked` asserted the session stayed on
Review Selection — where it was *reviewed*, not where it was asked; it now asserts Artifact Details.
`test_an_action_on_something_that_is_not_installed_is_drawn_not_raised` asserted Uninstall Review,
which would have gone on offering to uninstall something that is not there; it now asserts Installed
Artifact Details. Every other assertion in both — the refusal is drawn, nothing is written, no
review digest survives — is unchanged, and each gained `self.assertIsNone(finished.action)`.

**Evidence.** `tests/consumer_declined_preparation_test.py` holds both sides of the branch (a
decline returns and clears; a real digest still records a plan and stays), the negative B-092 asks
for (Enter after a decline emits no execute command), and the no-history case. Five targeted
mutations, including the one that proved `ACTION_REQUEST_SCREENS` load-bearing, are each killed.

## D-185 — A refusal drawn inside the application is written for somebody who is already in it

`QA-017`/`B-091`. Connecting an already-connected Registry produced diagnostics whose remediation is
literally `aart source sync …`, `aart source resubscribe …` and `aart source remove …`, and the
interactive adapter copied them into the notice verbatim. The line was long enough to be clipped
after `aart source remove`, so the TUI answered a refusal by sending the operator to a terminal and
then cut the instruction in half.

**Typed projection, not renderer parsing.** `Diagnostic` gained `interactive: tuple[str, ...]` — the
same next step, in the words of somebody already inside the application. `remediation` is unchanged
and stays the CLI's and JSON's contract; `diagnostic_to_data` is untouched, so no envelope moved.
The producers `QA-017` actually hit now carry prose: the duplicate alias, the duplicate origin and
ref, the changed declared identity, and the two unsynchronized-source refusals in the Marketplace
catalog. Each names what is true of *this* machine — which alias already holds it, that the snapshot
already held is kept — and points at a screen rather than a command.

**The net under it.** `_refusal` renders `interactive` when a diagnostic has it, and otherwise the
remediation steps that name no command, so a producer nobody has converted degrades to saying less
rather than to printing shell syntax. When every step was withheld it says that the next step is not
available on this screen yet, because a refusal that names no next step is the dead end `D-183` had
just removed one boundary over. This is a guarantee, not the mechanism: the mechanism is
`interactive`, and each new refusal that matters gets prose rather than relying on the net.

**Evidence.** `tests/tui_has_no_cli_commands_test.py` holds the projection, the fallback on both
sides, `QA-017`'s own two duplicate-connection scenarios, the CLI contract that still carries the
exact commands, and `B-091`'s audit as a sweep: every `ConsumerScreen` and `MaintainerScreen` drawn
through `frame` with a command-carrying refusal on it contains no `aart <verb>` — with a
sensitivity test, because a sweep that stopped reaching the notice would pass by drawing nothing.
The universal half is a Hypothesis property over generated remediation rather than four chosen
examples. Seven targeted mutations, all killed; two of them found claims that were not yet held.

## D-186 — Creating a registry is one reviewed run of five ordered stages, and it never publishes

`QA-016`/`B-090`. Maintainer Mode could promote into a registry, diff one and audit one, but had no
way to bring one into existence. The operator opened screen 46, found nothing, left for a terminal,
ran `aart registry init`, `lock`, `build`, `validate` and `audit` in that order by hand, and came
back. The order is not a convenience: a lock over an uninitialized workspace has nothing to pin, and
an index built before the lock describes a registry that was never pinned.

**One decision, not five.** Screens `46a`/`46b` are a form and its review, lettered the way `21a`/
`21b` and `31a`/`31b` already are, and they extend screen 46 rather than adding a twenty-fifth
Maintainer destination. The review names all five stages because the maintainer is agreeing to a
registry existing in this project, not to `init` in isolation; confirming it runs all five,
fail-fast, and the result says stage by stage what each one did. `n` opens it rather than `a`:
`a` is the word both subscription forms use, and creating the registry this project publishes is not
connecting to somebody else's (INV-199).

**The run is local, and that is a product boundary rather than an omission.** `commit` is the one
effect the operator opts into, and it is part of the review digest — a digest that ignored it would
let a review of "write the files, make no commit" be confirmed into a run that writes to the
repository's history. Nothing pushes and nothing merges. Publishing a registry is a decision made
through the repository's own review process (161.7), so it is stated on the form, stated again in
the review, and held by a test that records every `git` invocation the run makes and asserts none of
them is `push` or `merge`.

**No second implementation of what a registry is.** `agent_artifacts/io/registry_bootstrap.py` is
the ordering and nothing else: the three writing stages go through the same `LocalCurationService`
prepare/finalize pair the CLI drives, and the two gates are the same `validate_registry_workspace`
and `audit_registry_workspace` planning functions. What it adds is sequencing, a per-stage record,
and the commit boundary. `registry_identity_refusal` validates through the very `RegistryInitOptions`
that `init` builds, so a form cannot accept an identity the canonical action would later refuse.

**A refused stage is a report, not an exception.** `Err` from the port means nothing was attempted;
`Ok` with a report that has not passed means some of it was, and the report is a prefix of the five
stages rather than always all five — the screen can only honestly say which stage stopped the run if
the ones after it really did not run. Nothing is re-read from a partial run, because the screens
would then describe a registry the operator was simultaneously being told did not finish. Per
`QA-014` a passing gate contributes no lines of its own, and per `QA-017` the stage detail comes from
diagnostic messages rather than from the CLI's follow-up commands.

**Evidence.** `tests/maintainer_registry_init_test.py` holds the route and the navigation map, the
form and its one toggle, the exact draft reaching one review, the digest distinguishing the two
commit choices, the five stages run in order against a real checkout, mid-run fail-fast at a writing
stage and at a gate, the commit's subject and its locality, and one end-to-end confirmation that
leaves four real files in the project. Eleven targeted mutations, all killed; three of them found
claims that were not yet held.

## D-187 — Adopting from a repository is a scan, a selection and one atomic registry transaction

`QA-021`/`B-095` asks for a second onboarding model beside the monitored Source: look at a
credential-free Git URL once, see exactly what its authors declared, choose some of it, and let the
registry own immutable copies of only those files. `agent_artifacts/io/registry_adoption.py` is that
path's application half. Four choices carry it and each is a boundary rather than a convenience.

**Nothing is subscribed, so nothing is written to configuration.** `scan_repository` acquires,
compiles and reconciles entirely in memory; a test compares `git status --porcelain` before and
after and asserts `aart.config.json` does not appear. INV-199 and INV-200 are the reason: a Source is
an authoring location AART watches, and looking at a repository once is not that.

**The scan's alias is a mechanism, never an identity.** Compiling a Candidate needs a Source name and
this repository has none, so `_scan_alias` invents `scan-<slug>` for the life of the call. What the
registry publishes carries the registry's own alias, read from the checkout's `aart-source.json`, so
the throwaway name cannot leak into registry identity — held by a test that reads every file the
adoption wrote and refuses to find `scan-superpowers` in any of them. What *is* recorded about the
repository is its URL, resolved commit, manifest path and input digest, as ordinary native
provenance (`origin.url`, `origin.resolved_commit`, `origin.path`, `origin.input_digest`). That is
what a later explicit upstream check has to compare against, and it is the reason the flow can stay
one-off without pretending the origin is forgotten.

**Only the declared payload is copied, because nothing here re-derives the payload.** Adoption routes
through `compile_author_snapshot` → `plan_bulk_promotion(mode=VENDORED)` → `finalize_promotion`,
exactly as the monitored path does. `CompiledAuthorArtifact.canonical_entries` is already built from
each manifest's own `payload.include`, so a file that merely sits beside a manifest is not adopted by
proximity, and INV-201's explicit discovery is inherited rather than reimplemented. A repository that
declares no manifest is refused by name (`declares no aart.yaml or aart.json artifact at <ref>`), not
by silently returning an empty scan.

**Validation happens at scan time, not at adoption time.** A Candidate straight out of reconciliation
is `new`; only assessment makes it `ready`. Validating while building the scan means the state the
maintainer reads on the scan screen is the state adoption enforces, rather than two answers that can
disagree — offering an unassessed artifact as adoptable would promise something the plan would then
refuse. Terminal Candidates (promoted, superseded, source-removed) are carried as found, because the
registry's own answer is the record and reassessing it is a contradiction the domain already refuses.
One selection is one transaction: an artifact whose own plan refuses takes the whole preparation down
by name, and `apply_adoption` re-checks the review digest so a confirmation can only apply the plan
it was shown.

**Evidence.** `tests/registry_repository_scan_test.py` (14 tests) builds a real Git repository with
two declared skills and undeclared files beside them, and a real registry checkout created through
`bootstrap_registry_workspace`. It holds: the scan finds exactly the declared coordinates and pins
the commit; it names only declared files; it writes nothing and saves no Source; a repository
declaring nothing is refused by name; only the selected artifact becomes registry content; only
declared payload files are copied; the adopted copy's provenance records URL, commit, manifest path
and input digest; the scan alias never reaches registry identity; an artifact that did not validate
is refused by name; preparing alone writes nothing; an unknown coordinate is refused; a confirmation
naming another plan is refused and writes nothing; adopting the same version twice is refused as
immutable. Five targeted mutations, all killed; two of them found claims that were not yet held (the
scan alias reaching registry identity, and an unvalidated Candidate being adoptable).

**Built next.** D-188 records the TUI projection over this application service. The explicit
per-artifact `Check upstream` action that `B-095` describes, and a machine-complete CLI equivalent,
remain open.

## D-188 — A repository scan is a completed read; adoption is the separately confirmed mutation

The one-off adoption flow has two different operations and the TUI must not make them look like one
large mutation. `REPOSITORY_SCAN` acquires a credential-free URL/ref and produces a pinned immutable
observation. It changes neither configuration nor the registry, so its `PREPARE_ACTION` is the
completed read: screen 46d receives the result and the reducer clears the action immediately. There
is no fake Enter confirmation for a read that has already happened and no pending mutation an
accidental Enter could execute.

`REPOSITORY_ADOPT` starts separately from the selected rows of that observation. It prepares one
`PreparedAdoption`, screen 46e names every selected coordinate, the resolved commit and every path
that will change, and Enter applies only the review digest on that exact value. The shell holds the
scan object rather than reacquiring the repository between selection and review, so the maintainer
cannot select from one commit and adopt another.

The screen catalog extends 46 rather than inventing a 54th destination: 46c is the URL/ref form,
46d is the scan result, and 46e is the adoption review. `s` is contextual: on Sources it synchronizes
a subscribed Source; on Registry it scans a repository once. The form and result say explicitly
that the repository is not saved or monitored. Invalid artifacts remain visible with their state
and declared payload but do not become selectable rows, so the UI cannot promise an adoption the
application service will refuse.

The terminal layer receives immutable application views, not the acquired Git snapshot. Two ports
are composed in `tui.py`: the scan callable and an adoption boundary with prepare/apply halves, both
bound to the current project registry. A production-composition test substitutes only transport,
then drives real Git acquisition and real registry writes. It proves the chosen canonical package
is written, an undeclared adjacent file is not, and no Source configuration is created.

**Evidence.** `tests/maintainer_repository_adoption_test.py` (8 tests), the existing
`tests/registry_repository_scan_test.py` (14 application tests), and the screen-catalog/no-command
sweeps. Three targeted mutations were killed: moving the `s` route, admitting an invalid artifact
to the selectable rows, and replacing the selected coordinates at the adoption port with an empty
tuple. A machine-complete CLI equivalent and explicit per-artifact `Check upstream` remain B-095.

## D-189 — A pinned commit proves what was adopted; a recorded ref says what to check next

The first implementation pass over B-095's explicit `Check upstream` found that the adopted native
provenance was necessary but insufficient. `origin.resolved_commit` is immutable. Reacquiring that
value will always look unchanged, even after the branch or tag the maintainer selected moves. The
requested ref therefore has to survive adoption too.

New adoptions add one namespaced native-provenance extension:
`aart.repository-adoption: {"ref": <branch-or-tag>}`. This is deliberately not the legacy
`aart.vendor` record: that format describes a conventionally taken subtree and authored overlay,
whereas repository adoption recompiles an explicit author manifest and copies only its declared
payload. It is also not Source configuration. The repository remains unsubscribed and nothing is
watched automatically.

`compile_author_snapshot` accepts optional namespaced provenance metadata so the record is present
before candidate validation and promotion; its default is empty, preserving every monitored Source
caller. Provenance is part of the immutable stored object and registry snapshot, while the author's
manifest and selected payload still determine `origin.input_digest`. Thus the ref cannot silently
alter an existing published package, but adding acquisition metadata does not invent a content
change. The RED read the real adopted `provenance.json` and failed because the key was absent;
`tests/registry_repository_scan_test.py` now holds the ref as `main` over a real Git repository.

## D-190 — An upstream check compares declared input, and only a new version can become a proposal

`check_adopted_upstream` is an explicit read, not a miniature Source sync. It validates the current
Registry version/object binding, reads the adoption record, acquires that URL/ref once, and saves no
snapshot or Candidate history. The comparison is `origin.input_digest` against a freshly compiled
manifest input digest. A branch may move because README or other undeclared files changed; treating
commit inequality as artifact drift would be a false positive, and a targeted mutation replacing
the input comparison with commit comparison is killed by the real-Git unrelated-change test.

The answer is a typed five-way disposition: unchanged, changed, missing, unreachable or
invalid-manifest. In particular an acquisition failure cannot be presented as missing or current,
and a removed declaration cannot be presented as a network failure. Diagnostics from unreachable
and invalid observations are retained as data on the read-only result.

Immutable publication decides proposal shape. Changed bytes at the already published coordinate
set `new_version_required` and carry no plan. If the manifest declares a different version and the
ordinary validation pipeline clears it, the result carries the existing `PreparedAdoption` for
that one version. It is still only a prepared transaction: applying it requires the same exact
review digest as initial adoption. No path rewrites the published version. Evidence is eight
scenarios in `tests/registry_repository_scan_test.py`, including real Git ref movement, unrelated
commit churn, versioned and unversioned payload movement, deletion, invalid YAML and an unreachable
origin. TUI and CLI projections remain B-095.

## D-191 — Checking upstream is a completed TUI read; adopting its proposal is a new action

The TUI follows the same separation D-188 established for initial scanning. Registry key `u` opens
46f, a list composed only from immutable packages that carry `aart.repository-adoption`. Enter on a
row requests `REPOSITORY_UPSTREAM_CHECK`; screen 46g receives the typed D-190 result, and the reducer
immediately clears the action because the check is complete and has written nothing. Missing,
unreachable and invalid are rendered as different operator situations, not flattened into one
failure notice.

A changed result may contain a prepared plan, but that does not make the read a mutation. Only then
does `a` request the separate `REPOSITORY_ADOPT_UPDATE` action, enter the existing 46e adoption
review and bind the exact `PreparedAdoption.review_digest`. Enter applies through the same adoption
port as an initial copy. Pressing `a` on any result without a proposal is refused and returns to the
result; no same-version overwrite path exists.

Machine state is composed outside renderers. `LocalConsumerActions` holds the adoption records and
last check, projects immutable views, and refreshes the records after a confirmed adoption. The
production E2E uses real Git and real Registry writes: adopt 2.1.0, move `main` to a declared 2.2.0,
check, review, apply, then assert both immutable package directories exist and no Source was saved.
Focused evidence is 51 tests across adoption, navigation and the no-command-in-TUI property. Three
targeted mutations were killed: moving the Registry key, dropping the focused coordinate at the
check port, and binding the proposal to the wrong action so confirmation cannot execute. The
machine-complete CLI remains B-095.

## D-192 — The adoption CLI is one command per question, and `--yes` is the only thing that writes

`B-095` requires the one-off adoption path to be machine-complete on the public CLI, not only in the
TUI. `aart registry adopt` and `aart registry check-upstream` are that projection, and they are a
skin over `io/registry_adoption.py`: no planning, no discovery and no provenance logic lives in
`commands/registry.py`, so the CLI and the TUI cannot drift into two different answers about what
adopting means.

**Selection is what turns looking into a transaction.** `registry adopt --url URL --ref REF` with no
`--artifact` is a complete answer on its own: it reports every coordinate the repository declares and
writes nothing, because an operator has to be able to see what is there before naming any of it.
Repeating `--artifact KIND/NAME@VERSION` prepares exactly that selection and reports the review
digest and the paths that would change, still writing nothing. `--yes` is the only thing that
applies, and it applies the transaction the same invocation just prepared. Three phases —
`scan`, `review`, `adopted-local` — are named in the payload rather than inferred from which keys are
present, and `applied` is stated explicitly in all three.

**`--expect` binds a finalization to the review that produced it.** It is optional, because a single
`--yes` invocation reviews and applies the same plan; it is verified whenever given, because the
repository can move between two invocations, and the digest is the only thing that can notice. On
`check-upstream` the review and the finalization are necessarily two acquisitions, so a stale
`--expect` there refuses rather than adopting whatever upstream happens to declare now.

**Checking upstream never rewrites a published version.** The command reports the D-190 disposition
as it is — unchanged, changed, missing, unreachable, invalid-manifest are five different operator
situations, not one failure — and carries the proposal only when upstream released a new version.
`--yes` applies that proposal as an ordinary adoption, so the old package's bytes are untouched and
the new version appears beside it. When upstream changed without versioning, the command says so and
proposes nothing, because INV-203 makes the published coordinate immutable and there is nothing
honest to offer.

**The machine-readable listing is sorted.** The compiler's order is an implementation detail of how a
snapshot was walked; a listing that reorders itself between runs is not machine-readable. The command
sorts by coordinate, and a test reverses what the scan hands over to prove the sort belongs to the
command rather than to this repository's layout.

**Evidence.** `tests/registry_adoption_cli_test.py` (8 tests) drives the real public CLI over a real
Git repository and a real Registry checkout, substituting only transport: the scan lists every
manifest and leaves `git status` unchanged; a selection is reviewed before any write; `--yes` copies
only the declared payload and saves no Source; an unchanged check writes nothing and offers no
proposal; a released upstream version is reviewed and then added without touching the old package's
bytes; and a stale `--expect` refuses on both commands. `tests/registry_cli_test.py`'s action-set
contract now names `adopt` and `check-upstream`. Five targeted mutations, all killed; three of them
found claims that were not yet held — both `--expect` checks and the listing order.

With this, `B-095` is complete: application (D-187), TUI adoption (D-188/D-189), upstream check
(D-190/D-191) and the CLI projection.

## D-193 — Codex is measured against the installed Codex, and what was not measured stays absent

`QA-012`/`B-086` asks for a native Codex adapter rather than an alias for Claude. `domain/harness.py`
exists precisely to make that distinction enforceable — its opening line is that a target is
measured, not derived — so the work was measurement first and table rows second.

**How it was measured.** `codex debug prompt-input` renders the model-visible prompt as JSON,
including the skill roots Codex is about to read and the instruction files it has already loaded.
It reads configuration and contacts no network, which makes it a repeatable observation rather than
a documentation claim. Against Codex CLI 0.152.0 it named four skill roots in order:
`<project>/.codex/skills`, `$CODEX_HOME/skills`, `$CODEX_HOME/skills/.system` and
`<project>/.agents/skills`. Writing a marker into candidate instruction files and looking for it in
the same output established that `AGENTS.md` at the repository root and `$CODEX_HOME/AGENTS.md` are
both read, and that `$CODEX_HOME/instructions.md` — the location older Codex documentation names —
is not.

**Why `.codex/skills` and not `.agents/skills`.** Both are real roots that build reads. `.agents` is
the cross-vendor interop directory, and the same binary carries an external-agent migration that
detects and adopts other agents' installations from it; an artifact placed there is claimed by
whichever harness looked at it last. An installation the operator asked for by harness name should
land in that harness's own first root, which is `.codex/skills` at both scopes — user scope resolves
against the home directory, and `~/.codex` is exactly what `$CODEX_HOME` defaults to.

**What is deliberately absent.** No guideline row: that build reads Skills and `AGENTS.md` and
documents no separate guidelines directory, so a delivered guideline would be a file nothing opens.
No hook row: Codex has a hook system with `hooks.json` and twelve event names, but none of it was
measured here and a guessed slot is worse than none. No MCP row: Codex keeps servers as TOML tables,
which `LocalHarnessRegistry` cannot edit without risking the keys around them, and INV-071 leaves no
room for a TOML dependency — `B-096` carries the full finding, including that a project-scope
registration is inert until the operator trusts the project, and that `codex mcp add` is the
harness's own editor for that file. Until then `mcp_target("codex", …)` raises the ordinary
unmeasured-harness `KeyError` and an MCP artifact is refused by name.

**Harness selection stopped being an MCP question.** `_canonical_marketplace_target` derived the
machine's harness set from `MCP_TARGETS` alone, so a harness AART can install Skills and instructions
into was invisible until it also started a server. Codex is measured exactly that way. The set is now
the union of every measured table — MCP, delivery, memory and hooks — which is what "harnesses this
machine has measured" always meant. Nothing is widened past measurement: an artifact this machine
cannot actually place for a harness is still refused by name at installation, which is where that
refusal belongs.

**Evidence.** `tests/codex_harness_test.py` (10 tests). Four are ordinary table assertions, one is
the measured absence of a guideline location, one is the named MCP refusal, one is the TUI harness
set, and two are the observation itself: they build a temporary project and a temporary
`CODEX_HOME`, write a Skill and an instruction file into the destinations the table names, run the
installed `codex debug prompt-input`, and assert Codex found them. Those two skip when no Codex is
installed, which keeps the suite portable without weakening the claim where it can be checked. Five
targeted mutations, all killed — aliasing the Skill destination to Claude's, aliasing project
instructions to `CLAUDE.md`, moving user instructions to the home root, moving the user Skill root to
`.agents/skills`, and reverting harness selection to MCP-only. The live observation killed three of
them on its own.

`QA-012` is therefore partially closed: Skills and instructions install natively at both scopes and
Codex is selectable, while MCP (`B-096`) and hooks remain unmeasured and refuse by name. `QA-011`
(OpenCode) is untouched and still open.

## D-194 — OpenCode's MCP entry has its own shape, so the shape became part of the target

`QA-011`/`B-085` asks for a native OpenCode adapter. The dormant `profiles/builtin.py` already names
OpenCode, and `B-085` recorded why that is not an implementation to reconnect: its own labels say
best-effort, and its MCP projection writes a `command` string beside `args`, which is not what this
build reads. Measurement first, table rows second, as with Codex (`D-193`).

**How it was measured.** OpenCode 1.18.29 ships three read-only debug subcommands that answer
exactly the questions the tables ask. `opencode debug skill` lists every skill it found and the file
each came from; `opencode debug config` prints the merged configuration; `opencode debug paths`
prints the roots. Runs used a temporary `HOME` with the XDG variables cleared, so user scope was a
directory this repository created rather than the operator's own.

**The rows.** Skills at `.opencode/skills/<name>` for the project and `.config/opencode/skills/<name>`
for the user; `AGENTS.md` at the repository root and `.config/opencode/AGENTS.md` for the user; MCP
under the `mcp` key of `opencode.json` at the project and `.config/opencode/opencode.json` for the
user. That build also auto-loads `~/.claude/skills` and `~/.agents/skills`, and both were observed
working — they are another harness's directory and the cross-vendor interop root, and an installation
asked for by harness name goes in that harness's own directory, which is the same reasoning `D-193`
applied to `.agents/skills` for Codex.

**A measured contradiction, kept rather than smoothed.** That build also reads
`~/.opencode/opencode.json`, which its own shipped `customize-opencode` skill says it does not
("NOT `~/.opencode/`"). Two paths work, so the user-scope row is a choice and not a discovery: it is
the config root `opencode debug paths` reports and the one the build documents, which is the one
that will still be read when the undocumented path stops being. The comment in `MCP_TARGETS` and a
test record both halves, because a later reader finding two working paths deserves the reason for
the one chosen rather than a guess that the other was never noticed.

**`McpEntryShape`.** A local server in `opencode.json` is `{"type": "local", "command": ["/path",
"--flag"]}` — one vector, no `args`. Claude and Tabnine take `{"command": "/path", "args":
["--flag"]}`. Both are correct for their harness, so the difference belongs to the target and not to
the caller: `McpTarget` gained an `entry_shape`, defaulting to the shape already written, and
`registration_entry` switches on it. Nothing else in the pipeline learned that harnesses differ.

**What is deliberately absent.** No guideline row: that build reads skills, agents, commands and
`AGENTS.md`, and documents no guidelines directory, so a delivered guideline would be a file nothing
opens. No hook row: OpenCode has a plugin/event model, none of it was measured here, and a harness
being present in one table is not permission to guess it into another —
`tests/delivery_targets_test.py` now holds that as its own claim.

**A stand-in that stopped standing in.** Three tests used `"opencode"` as the name of a harness
nobody measured. Measuring it made them pass for the wrong reason, and they now name `cursor`, which
this repository genuinely has never measured.

**Evidence.** `tests/opencode_harness_test.py` (9 tests): table rows, the entry shape at both ends
(including that Claude keeps the shape Claude reads), the documented-config-root choice, and two
live observations that write a Skill, an `AGENTS.md` and a server into the destinations the table
names and assert the installed OpenCode reports them back. The live tests skip when no OpenCode is
installed. Six targeted mutations, all killed: OpenCode MCP written in Claude's shape, the vector
dropping its arguments, user config at `.opencode`, the user Skill root inside Claude's directory,
user memory at the home root, and the typed shape leaking into Claude.

`QA-011` is therefore closed for Skills, instructions and MCP at both scopes, with OpenCode
selectable in the TUI through the union harness set `D-193` introduced. Guidelines and hooks stay
refused by name until someone measures them.

## D-195 — Codex hooks stay absent because they were measured, not because they were not

`D-193` left `HOOK_TARGETS` without a Codex row and said so honestly: nothing had been measured, and
a guessed slot is worse than none. Measuring it now does not add the row, and the reason is worth
recording, because "we did not look" and "we looked and a written file cannot work" are different
claims and only the second is durable.

`codex features list` reports `hooks` as `stable` and enabled and `plugin_hooks` as `removed`, so
hooks in Codex CLI 0.152.0 are a first-class configured capability rather than a plugin extension.
The build names twelve events and four handler kinds. What stops the row is not absence but three
measured properties: the configuration is reached through a `hooks` path key in `config.toml`, which
is `B-096`'s TOML problem unchanged; project-local hooks stay disabled until the operator trusts the
project, which is the same trust decision `B-096` measured for MCP and is not AART's to make; and
every new or changed hook is held for interactive review before it runs, which the build's own
`--dangerously-bypass-hook-trust` flag exists to skip.

The consequence is a receipt question, not a plumbing question. AART could write a file and report a
hook installed, and the hook would not run until a person opened Codex and trusted it. A receipt for
something that did not happen is worse than a refusal by name, so the refusal stands. `B-097` carries
the finding, including the two things deliberately left unmeasured — whether the hooks file has a
default location and whether it is JSON or TOML, since the binary carries error strings for both.

Whether AART should install a hook and tell the operator plainly that Codex will ask them to review
it is a defensible product answer and a reasonable future slice. It is a product decision about what
a receipt means, and it does not belong in a target table.

## D-196 — A harness whose file AART cannot write safely gets written by the harness

`B-096` blocked Codex MCP on a constraint that was real and correctly stated: Codex keeps servers as
`[mcp_servers.<name>]` TOML tables, `tomllib` reads only and only from 3.11 while `requires-python`
is `>=3.10`, nothing in the standard library writes TOML at any version, and INV-071 forbids a
dependency. What that entry got right, and what matters here, is that the objection was never the
syntax. `LocalHarnessRegistry` exists to promise that a registration leaves the operator's file
otherwise untouched — unrelated keys, ordering, permissions, a map it cannot parse reported rather
than replaced. A hand-rolled TOML writer cannot promise that, and a registration that destroys
somebody's configuration to succeed is not a successful registration.

**What unblocked it is a measurement.** Codex ships `codex mcp add`, `remove`, `get` and
`list --json`, and against an isolated `CODEX_HOME` it keeps exactly the promise this repository
could not: a config file holding an operator's comment, an unrelated `model` key, another server's
table and a following `[tui]` table came back byte-identical after a server was added and removed.
So the answer is not to write the file better; it is not to write the file.

**`McpEditor` on the target.** A target now says who writes it: `SETTINGS_FILE`, which is AART's
JSON interpreter and every other measured harness, or `HARNESS_COMMAND`, which is the harness's own
editor. `LocalHarnessRegistry` routes on that, so nothing above it learns that harnesses differ —
the same reason `McpEntryShape` lives on the target rather than in a caller (`D-194`). Delegation is
the exception it was measured to be, and a test pins that Codex is the only harness holding it.

**The trade, stated rather than hidden.** A delegated registration needs the Codex executable on
this machine, and says `harness-editor-missing` by name when it is absent instead of reporting a
registration that did not happen. That is honest: installing into a harness that is not installed
was never meaningful. There is no silent fallback to writing the file directly — a fallback would
defeat the entire reason for delegating, and a test holds that the file stays untouched when the
editor is missing.

**Reading came with it.** Observation used to parse the settings file as JSON, which for Codex is a
file that cannot parse. `observed_command` moved onto the registry port, so whoever writes a
harness's servers is also who reads them back. That closed a defect this work found in the harness
that was already shipping: see `D-197`.

**User scope only.** `codex mcp add` reports "Added global MCP server" and offers no project flag,
and a project-scope registration would be inert until the operator trusts the project. So there is a
user row and no project row, and `mcp_target("codex", Scope.PROJECT)` keeps raising the ordinary
unmeasured-target `KeyError`.

**One measured correction.** The first implementation removed a server before re-adding it, on the
assumption that `add` refuses a name it already knows. A surviving mutant said no test held that,
and measuring it found `add` overwrites in place. The removal was deleted: it was dead, and it would
have widened a window in which the operator's Codex had no server at all.

**Evidence.** `tests/codex_mcp_registration_test.py` (17 tests): the target row, the routing, the
named refusal when the editor is missing with the file left untouched, and eight that run the
installed Codex — register, list back, re-register unchanged, replace, unregister twice, the
operator's file surviving byte-identical, another server surviving, and an unregistered name reading
back as nothing. `tests/codex_installation_e2e_test.py` (4 tests) is the whole path: an author's
manifest compiled, published, planned against the measured target and installed, after which Codex
lists the server and the launcher Codex was handed starts the author's server and answers with the
declared arguments, the supplied config value and the secret read at launch. Nine targeted
mutations, all killed; two survived first and both were findings — a test that skipped where it
should have failed, and the unmeasured removal above.

`QA-012`'s MCP half is therefore closed at user scope. Hooks remain refused for the reasons in
`D-195`/`B-097`, which delegation does not change: the blocker there is a trust and review gate, not
a file format.

## D-197 — Whoever writes a harness's registration is who reads it back

Installing an MCP server into OpenCode wrote a correct `opencode.json`, started a working server,
and then reported the harness component absent. The install ended partially-applied, status showed
drift that was not there, and repair would have rewritten an already-correct file forever.

Writing had learned about shapes and reading had not. `registration_entry` grew `McpEntryShape` when
OpenCode's typed command vector arrived (`D-194`); the observation still did `entry["command"] if
isinstance(command, str)`, which is Claude's spelling, so every vector-shaped entry read as nothing.
The failure is quiet in the worst way — the file is right, the server starts, and the installation
simply never converges — and nothing in the harness tables could catch it, because both halves were
individually correct.

Two changes, both of them the same idea. `registered_command` is now the inverse of
`registration_entry` and lives beside it, because a reader that knows one spelling reports every
other harness's correct registration as missing. And `observed_command` moved onto the registry
port, so the observation asks whoever owns the file rather than parsing it — which is what let Codex
join at all (`D-196`), since its file is TOML that this build cannot parse.

The round trip is held as a property rather than by examples, because the claim is universal over
harnesses, launchers and arguments: for every measured MCP target, what `registration_entry` writes
is what `registered_command` reads back. That property would have failed the day the second shape
existed. The example-based half covers what the two shapes disagree about, an entry hand-edited into
another harness's spelling, an empty vector and a non-object.

The general lesson, recorded because the next harness will be someone else's: a harness is not
integrated when its tables are measured. It is integrated when something installs through them and
the thing that was installed is read back, started, and asked a question. Both harness slices now
have that, and it is what found this.

**Evidence.** `tests/harness_registration_roundtrip_test.py` (5 tests, two of them properties);
`tests/opencode_installation_e2e_test.py` (8 tests, including the launcher started from the vector
that landed in `opencode.json`, the public `marketplace install --profile opencode` landing a Skill
in `.opencode/skills/<name>` and in neither `.claude` nor `.agents`, and two that run the installed
OpenCode). Six targeted mutations for this defect, all killed.

## D-198 — A harness this machine has is not a harness somebody asked for

Measuring Codex (`D-193`) put it in `_canonical_marketplace_target`'s harness set, which is the
union of every measured table. That set is what the persistent shell installs into. Codex registers
MCP servers only at user scope (`D-196`), so `mcp_target("codex", PROJECT)` raises, and
`placement_for` refused the whole placement by name — which meant the shell could no longer install
*any* MCP artifact on a machine where Codex is measured. Claude's and Tabnine's servers included.
Nobody had asked for Codex; the machine simply had it.

The refusal it hit is the right one for the caller it was written for. `aart marketplace install`
refuses without `--profile`, so every profile that reaches it was typed by somebody, and dropping
one silently is an install that reports success and leaves the harness they named with nothing to
read and no way to start a server.

So the two callers now say which they are. `placement_for` takes `profiles_requested`, defaulting to
the honest value for a command — these were asked for, and one that cannot host this artifact is a
refusal naming it. `_canonical_installation_host` passes `False`, because the shell's profiles are
what this build measured rather than what anybody typed, and a measured harness that cannot host
*this* kind at *this* scope is not a mistake in a request that was never made.

The skip stays narrow on both sides. A harness no table names is refused however the profiles
arrived — the machine's own set can never contain one, so that only ever fires on a typed name — and
a Selection every profile left out is refused too, because an install with no effect anywhere is not
a successful one. `measured_harnesses()` is the one place that answers "has this build looked at
that harness", and `_canonical_marketplace_target` now derives its set from it rather than unioning
the four tables inline.

## D-199 — Screen 28's installation scope is where installations go

Settings has offered `Default scope: Project/User` since the canonical shell replaced the wizard.
It was written, persisted and drawn, and nothing read it: composition fixed the host at
`Scope.PROJECT`, so choosing User installed into the project anyway. A preference an application
displays and then ignores is worse than one it never offered, because the operator reads it as a
statement about where their files went.

The scope is now derived at the point of use rather than frozen at composition, so toggling it takes
effect in the same session that toggled it — `save_settings` already replaces the context's
settings, and `_host()` reads through them. Only the scope moves: `harness_root` follows from it,
and the machine is otherwise the same machine. The maintainer registry root moved off `harness_root`
onto `project_root` for exactly that reason — the registry a maintainer curates is the checkout this
session opened in, and it must not follow an installation preference into the home directory.

What is executed stays what was reviewed. Each `_prepare_*` records the host it prepared against and
each confirmation acts on that one, so a scope toggled between a review and its confirmation cannot
record a project plan as a user installation. The completion factory is handed that host too, for
the same reason: setup and usage reporting describe the installation that happened, at the scope it
happened at.

## D-200 — The registry run the TUI never owned, minus the stage that happens once

`B-090` gave screen 46 the run that brings a registry into existence: init, lock, build, validate,
audit, in the one order that means anything. Everything afterwards was still typed. A maintainer who
promoted a Candidate, adopted an artifact or edited the checkout had to leave for a terminal and run
four commands — with flags no screen had ever named — in an order held in their head. That is the
same product defect `B-090` described, one step further along the maintainer's day.

Screen 46h re-runs those four stages and 46i reviews them, through the same authority `init` uses:
`_run_stages` is shared, so there is one implementation of what a stage is and one place the order
lives. `init` is deliberately not offered. A registry is created once; re-creating one is not
maintenance, and a picker that offered it would let a rebuild rename the registry it was rebuilding.

Three narrower choices are worth stating.

**The whole sequence and one stage are both offered**, because they are different jobs. After a
promotion the maintainer wants all four; while fixing one refusal they want `validate` and nothing
else, and a rebuild that silently rewrote the index while they were reading a validation failure
would be answering a question they did not ask. The stages always run in canonical order however the
choice arrives, because the order is the knowledge the module exists to hold.

**There is no commit toggle**, unlike `init`'s. Initialization creates a tree that did not exist, and
a commit is how that tree becomes reviewable at all. A rebuild writes generated files into a checkout
the maintainer is already curating, and those changes belong to whatever caused them — the promotion,
the adoption — rather than to a separate "rebuild" commit that would split one change across two.
Publication stays where 161.7 puts it: the repository's own review.

**The stage vocabulary lives in `application/maintainer_views.py`**, not at the effect boundary that
runs it. Screen 46h offers the stages, 46i reviews them and the run executes them; those are one
piece of product knowledge, and two copies of it drift in the direction where the screen describes a
run the code no longer performs.

## D-201 — A review that draws no plan, and a request that inherits the wrong row

Two defects surfaced while walking screen 46h's keys in a headless shell, and neither was visible
from the adapter tests that covered the same flow.

`Enter` did nothing on screens 31b and 46b. Both reviews said "press Enter", and the key translated
to no event at all, so the Add Source and Initialize Registry flows could be typed, reviewed and
never confirmed. The confirmation list in `key_event` is hand-written; those two were simply never
added. They are now, together with 46i.

Worse, neither review drew what it was asking about. `_ANSWERABLE` — the screens a notice may be
drawn on — derived the *request* screens from `_ACTION_REVIEW`'s keys and then hand-listed five of
its values, so every review screen not on that hand-list showed its prompt with nothing under it,
and every result screen not on it reported that a run had happened without saying what it did. The
set is now derived from both tables: a screen an action moves to, or lands on, can draw that
action's answer. The hand-list is gone, which is the point — it was a second copy of the same
knowledge, and the symptom of its drift was an answer nobody could see.

The third finding is why `_ROW_IS_THE_REQUEST` exists. `_request_action` reads `state.focus or
state.current_row`, and `focus` is the row that opened the current screen — on 46h that is the
registry alias focused back on screen 46, which is not a stage. The first confirmed run therefore
asked to rebuild `company`. For screen 46h the rows *are* the choice, so the action reads the cursor
first. Stated as a set of actions rather than a special case in the key handler, because the question
"is this screen's row the subject, or the thing that opened it" is a property of the action.

These are recorded together because they share a cause: every piece was tested where it was written,
and nothing had pressed the keys in order. The shell walk-through in
`tests/maintainer_registry_rebuild_test.py` is the test that would have caught all three.

## D-202 — A key and the words that advertise it are one binding

Date: 2026-09-09 · Increment: QA-026 manual acceptance · Status: accepted

The accepted TUI catalog says contextual shortcuts appear only where relevant. A fixed navigation
legend violated both halves: it hid the actions Maintainer screens had accumulated and advertised
Space/Enter on screens where the reducer could do nothing with them. Moving each missing shortcut
into another renderer table would repeat the drift behind D-201.

A contextual letter binding therefore contains the key, its application event and its short label.
`key_event` translates that value and the footer displays the same value. Structural keys do not
receive a parallel table: selection, search, forms and confirmation derive from the same screen sets
and action-review map the reducer already enforces. Each frame lists those local actions first and
the universal movement/back/help/quit routes second. Modal search and quit prompts replace the
footer with only the keys their mode accepts.

This also settles where action instructions belong. Screen 46's `Actions:` body block was a second
copy of its keyboard contract and is removed; the body describes Registry state, while the chrome
describes how to act on that state. A headless test presses advertised `b Rebuild` and reaches 46h,
so the claim is not held by matching label text alone.
