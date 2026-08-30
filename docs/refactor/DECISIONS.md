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
