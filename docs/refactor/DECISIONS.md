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
