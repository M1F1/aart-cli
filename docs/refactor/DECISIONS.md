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
