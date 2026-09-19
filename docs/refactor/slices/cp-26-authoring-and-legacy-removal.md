# CP-26 — Canonical Registry maintenance, authoring tools and local consumption

Status: **active**. Steps 1–4 are done (D-308/D-311/D-318/D-319/D-320); step 5 is next. The
machine plan keeps an unfinished step as `todo` until its completion evidence is recorded.

PR #21 follow-up (2026-09-18): D-308's authoring refusal now points to the runnable `--help`
forms of `scan` and `promote`. The visible-command test was red first, green after correction,
red under a deliberate one-command regression, then green when restored. This release repair
precedes step 2 and does not alter its scope.

PR #21 second CI follow-up (D-310): two credential-shaped URL assertions now use the runtime
fixture builder, and the secret-shape gate runs before dependency installation. A deliberate
literal restoration made the scanner red; moving the gate back after installation made the
ordering test red. This release repair likewise precedes step 2.

This supersedes the earlier draft of this file, which planned a compatibility window. The
maintainer has withdrawn that requirement: AART is early, its users are few, and back-compatibility
is explicitly not to be paid for. The removal is therefore direct.

## Why removal and authoring belong in one epic

Removing `registry scaffold` takes away the only ergonomic way to start an artifact. That is
correct — it wrote the *compiled* form by hand, which is the defect, not the ergonomics — but it
leaves a real gap, and the gap already exists today for anyone not using `scaffold`:

AART **reads and validates** author manifests (`aart.json`, `aart.yaml`, through its own dependency
free YAML reader in `protocol/yaml.py`) and **writes none**. `cli.py` and the TUI both instruct the
user to "commit an `aart.yaml`/`aart.json` manifest in each directory", against a schema spread
over 2264 lines, with no way to produce a correct one. So the author-side commands are not
compensation for the removal; they close a hole that is open now.

---

# Part 1 — Design

## 1.1 What the older representation is, and exactly what happens to it

| | approved (canonical) | older (maintainer workspace) |
|---|---|---|
| artifact path | `artifacts/<kind>/<name>/<version>/artifact.json` | `artifacts/<kind>/<name>/artifact.json` |
| catalogs | `registry/index.json`, `registry/snapshot.json` | `aart.index.json` |
| resolution | `registry/versions/<kind>/<name>/<version>.json` | `aart.lock.json` |
| provenance | `registry/promotions/<digest>.json` | — |
| named by the Product Specification | yes (§164.7) | **not once** |

Established by reading the callers of `prepare_registry_lock`, `prepare_registry_build` and
`prepare_artifact_scaffold` in `curation/runtime.py` — not by matching names.

**Removed outright.** This has no approved-representation behaviour:

- `registry scaffold` — authors in place. Replaced by `aart author init` plus `scan` + `promote`.

**Kept, losing one branch.** `publish` is the supported aggregate for the approved representation:
build, validate, audit and create the reviewed local commit, without pushing. The `lock`, `build`,
`validate`, `audit`, `format` and `publish` commands remain; only their older-representation paths
are removed. Push remains a separate explicit operation, and step 18 exposes it on Registry
Maintainer's local-workspace row after the canonical readiness checks pass. Only any
representation-sensitive legacy preparation beneath Push is removed. On an approved Registry
`lock` remains a read-only check: immutable version and promotion records already pin the objects,
so there is no second lock file to resolve.

**Deleted once nothing calls them.** `parse_registry_lock` / `parse_registry_index` and the
lock/index schema in `protocol/registry_schema.py`; `_GENERATED_PATHS` in
`protocol/registry_tree.py`; the legacy halves of both `planning.py` modules; the `else` branch in
`sources/validation.py:269`; the legacy branch in `consumer/runtime.py`. Measured blast radius: 12
production modules, 16 test files.

**Not deleted.** `is_promoted_registry` and the D-308 guard survive the epic: they become the thing
that reports an older-shape registry honestly rather than failing on a missing file.

## 1.2 Why a registry cannot author its own artifacts

Not an aesthetic boundary. Every canonical package carries `provenance.json`, and
`OriginProvenance` has five fields, none optional:

```
kind: "git" | "local"    url    resolved_commit    path    input_digest
```

An artifact written directly into a registry has no revision it came from and no input it was
compiled from, so two of those five have nothing to put in them. `scaffold` did not solve this; it
wrote the package and skipped the record, leaving a registry whose `build` ignores the artifact and
whose `validate` refuses the snapshot. `kind: "local"` means the source may be a normalized local
path — so "our own artifacts, no hosted repo" is already supported, as a `source-local` checkout
beside the registry, not inside it.

## 1.3 `aart author init`

A new top-level group. Not under `registry` (wrong target) and not under `source` (that group is
about subscriptions, not content).

```
aart author init --kind {skill,guideline,mcp,hook,memory} --name <slug> [--into DIR]
```

Writes `aart.yaml` plus a payload skeleton. CP-26 delivers `mcp` and `skill` first; the other three
kinds follow the same generator in step 12.

**Every accepted option is present, and narrowing is the user's job.** The maintainer's
requirement: the skeleton carries the full surface so an agent or a person deletes down to what
they need, rather than discovering fields by reading the parser. Optional blocks are emitted
commented-out with a one-line explanation; required fields are emitted live with a working value.
The YAML reader strips comments (`_strip_comment`), so a skeleton parses whether or not anything is
uncommented.

**The generator must not become a second authority on the schema.** This is the central design
constraint and the reason for §1.5.

**A YAML writer does not exist.** `protocol/yaml.py` parses only. CP-26 adds a deterministic
emitter for the subset the generator produces — block mappings, block sequences, plain scalars,
comments — not a general YAML serializer, and not a round-tripper.

Field surface, collected from the parser rather than transcribed:

```
schema                                     required
artifact:   name kind version              required, + summary
payload:    include                        required, + exclude
transport runtime launch requirements inputs python credentials compatibility install   optional
  launch:         entrypoint path arguments
  compatibility:  harnesses platforms
  inputs[]:       id kind inject, + help{label description example format_hint
                  obtain_from{label url} validation_hint} validation{pattern
                  allowed_hosts message}
  python:         dependencies
```

Enumerations come from the same module: kinds are `skill|guideline|mcp|hook|memory`, injections
`environment|cli-argument|file|stdin`, dependency kinds `requirements|pyproject|uv`.

## 1.4 `aart author check`

```
aart author check [--source DIR] [--json]
```

Two claims, in this order, because the second is worthless if the first fails:

1. **Parseable** — every discovered `aart.yaml`/`aart.json` goes through the real
   `parse_author_manifest`. Not a copy of its rules: the function itself.
2. **Promotable** — the parsed manifest compiles to a canonical package and would be accepted by
   `registry scan`. This is the claim that matters to the maintainer's stated workflow, and it is
   the one a person cannot check by eye.

`check` is the higher-value half of the pair. An agent adding manifests needs a *loop* — amend,
check, amend — and it must receive the same verdict `scan` will later issue, before anything is
committed. A checker that merely lints is worse than none, because it licenses a manifest the
scanner then rejects.

## 1.5 The anti-drift oracle

The stated risk — a generator that quietly diverges from the parser — is answered by a test, not by
discipline. The test walks `protocol/authoring.py` with `ast`, collects every string in every
`required=` / `optional=` set on every field-accepting call, and asserts each name appears in the
generated skeleton. Adding a field to the parser turns the test red until the skeleton carries it.

The collector is already written and verified against the current parser; it recovers all twelve
field groups, including the three (`launch`, `validation`, `install`) that a naive search for
`_fields(` misses because they go through `_nested_type`. It is reproduced here so the next agent
does not have to derive it again — note that it keys on the `required=` / `optional=` keywords, not
on the callee name, which is exactly why it catches the `_nested_type` cases:

```python
import ast, pathlib

def accepted_fields(module="agent_artifacts/protocol/authoring.py") -> dict[tuple[str, str], list]:
    tree = ast.parse(pathlib.Path(module).read_text(encoding="utf-8"))
    owner = {}
    for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        for sub in ast.walk(fn):
            owner[id(sub)] = fn.name
    found: dict[tuple[str, str], list] = {}
    for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        callee = call.func.id if isinstance(call.func, ast.Name) else getattr(call.func, "attr", "?")
        for kw in call.keywords:
            if kw.arg in ("required", "optional"):
                values = sorted({s.value for s in ast.walk(kw.value)
                                 if isinstance(s, ast.Constant) and isinstance(s.value, str)})
                found.setdefault((owner.get(id(call), "?"), callee), []).append((kw.arg, values))
    return found
```

Its current output, which the skeleton must cover in full:

```
_nested_type          required: type
_parse_obtain_from    required: label                optional: url
_parse_guidance       required: label                optional: description example format_hint
                                                               obtain_from validation_hint
_parse_injection      required: type
_parse_input          required: id inject kind
_parse_python         required: dependencies
_parse_launch                                        optional: arguments entrypoint path
_parse_validation                                    optional: allowed_hosts message pattern
read_install_description                             optional: version
parse_author_manifest required: artifact payload schema
                                                     optional: compatibility credentials inputs
                                                               install launch python requirements
                                                               runtime transport
                      required: kind name version    optional: summary
                      required: include              optional: exclude
                                                     optional: harnesses platforms
parse_author_collection_manifest
                      required: artifacts name schema version   optional: summary
```

Two further tests hold the generator honest:

- the emitted skeleton parses with `parse_author_manifest` and yields no diagnostics;
- the emitted skeleton, uncommented, compiles to a canonical package — the `check` claim, run
  against the generator's own output.

## 1.6 The README has one reader: somebody who wants to install an artifact now

The README is 646 lines and currently mixes adoption, architecture, authoring, Registry
maintenance, Enterprise rollout, development, quality gates and release mechanics. Its primary and
only narrative audience after CP-26 is a normal user who wants the shortest supported route from no
AART installation to an installed artifact.

The top-level order is fixed:

1. **Install an artifact quickly.** Immediately after the title, show prerequisites and the
   shortest supported sequence: install AART, connect/synchronize a Registry, find or choose an
   artifact in Marketplace, install it into a selected harness and verify the result. The primary
   human route uses the TUI; a compact deterministic CLI equivalent may follow. Unknown Registry,
   artifact and harness values stay as obvious placeholders rather than product-specific defaults.
2. **What AART is.** Only after the working quick start, give a short product explanation: AART is a
   package manager, Registry client, policy/review surface and installer for agent artifacts. Name
   the supported artifact families and the Source → Candidate → Registry → Marketplace distinction
   only as far as a new user needs it. This is orientation, not an architecture chapter.
3. **Documentation.** Provide a compact categorized list of links for readers who need more:
   everyday use and lifecycle, TUI/CLI, artifact authoring, Registry maintenance, Enterprise setup,
   security/protocol contracts, development/testing and releases. Authoring and maintainer details
   belong in those linked documents, not in a second README tutorial. Every target must exist and
   the documentation gate checks every link.
4. **License and existing footer.** The License section remains the final README section. Preserve
   its current MIT wording and the existing copyright/footer text unless the owner separately asks
   to change the legal text.

The README may retain a one-sentence outcome directly below the title, but it must not make a new
user read the product explanation before reaching the quick start. Detailed current sections move
to focused documents rather than being discarded. Internal refactor records are not part of the
public documentation index.

**Install instructions must be executed, not described.** `tests/adoption_first_contact_test.py`
already holds the install section to a shape — no hardcoded host, one `<repository>` placeholder,
three installers — but shape is not the claim worth holding; *the command works* is. Two of the
documented routes are the ones a first-time reader actually takes and neither is covered end to end:
downloading the wheel from the Releases page by hand, and fetching it with `gh release download`.
`scripts/distribution_smoke.py` already builds a wheel and installs it into a disposable
environment, so the gate is an extension of a driver that exists, not a new one. The published lines
stay generated by `scripts/install_commands.py` (D-277, already settled: a markdown file cannot
interpolate a repository address, so the README names neither a host nor a release). What step 16
adds is that the generated form is run. The same gate also holds the section order, the bounded
product explanation, the existence of every documentation link and License as the final section.

---

# Part 2 — Plan (CP-26)

Removal comes first. D-308 already refuses `scaffold` on a registry that publishes approved
versions. Deleting it takes away no approved workflow, and every later step is then written against
a smaller surface. `publish` is not deleted: its approved-registry path is an independently useful
aggregate and remains. Old registries are not a consideration: there is no compatibility window,
no migration command, and no deprecation period.

| # | Step | Notes |
|---|---|---|
| 1 | A registry that has chosen one representation refuses the other's verbs | **done**, D-308 |
| 2 | `registry scaffold` is deleted | **done**; verb, planner, CLI surface and obsolete tests removed; `publish` remains |
| 3 | Keep canonical `lock`, `build`, `validate`, `audit`, `format` and aggregate `publish`; remove only legacy branches | **done**; empty and populated canonical Registries share one route; Push remains separate and rejects the retired shape |
| 4 | The consumer and source validators lose theirs | **done**; one refusal naming the retired paths, one naming the expected shape, no fallback |
| 5 | The lock/index schema, tree constants, planning halves and fixtures are deleted | B-057 closes here |
| 6 | The authoring-manifest field surface is collected from the parser, not transcribed | the `ast` oracle; lands before anything generates |
| 7 | A deterministic YAML emitter for the generated subset | block maps, sequences, plain scalars, comments |
| 8 | `aart author init` emits a full-surface `aart.yaml` for `mcp` | first kind end to end, guarded by step 6 |
| 9 | `aart author init` emits the same for `skill` | proves the generator is kind-driven, not special-cased |
| 10 | `aart author check` proves every discovered manifest parses | through `parse_author_manifest` itself |
| 11 | `aart author check` proves each manifest would be accepted by `scan` | the promotable claim |
| 12 | The remaining three kinds | `guideline`, `hook`, `memory` |
| 13 | README opens with the fastest normal-user path to an installed artifact | install AART → connect/sync Registry → choose in Marketplace → install into a harness → verify; TUI first, compact CLI equivalent second |
| 14 | A short “What AART is” and categorized documentation index follow the quick start | explanation stays bounded; authoring, Registry, Enterprise, architecture and contributor detail are links, not README tutorials |
| 15 | Detailed current material moves into focused documents; License remains last | preserve existing MIT wording and copyright/footer; every public documentation link resolves |
| 16 | Every final install line and README structural promise is executed by a gate | manual wheel download and `gh release download`, section order, bounded explanation, valid links and final License; later edits rerun it |
| 17 | Remove `M1F1` as a generated or operational default | Registry workflow/README, CLI guidance, release defaults and public configuration docs; no organization or repository baked into a generated registry |
| 18 | Registry Maintainer may push its publish-ready local snapshot | workspace-scoped action; visible readiness and blockers; current branch or a new review branch, never `main` or the default branch |
| 19 | Configuration and credential bindings are keyed by installation target | B-144; alias + artifact + destination + harness/profile + input id, with explicit sharing only |
| 20 | Add Registry synchronizes a canonical Registry from a local Git checkout | B-143; one admission/snapshot/Marketplace path for remote and local transports |
| 21 | Run the full CP-26 verification only after every implementation task is complete | full quality, integration/E2E, packaging/docs/secret gates and final acceptance evidence |

The numbered order is the execution order and is grouped into six dependency phases:

1. **Canonicalize Registry maintenance (1–5).** Refuse mixed state, remove only `scaffold` and the
   older representation, then delete its now-unreachable schemas and fixtures. Canonical
   maintenance commands survive.
2. **Build the author loop (6–12).** Collect the parser-owned field surface before writing the YAML
   emitter; land `init` before `check`; finish all five kinds before documenting the workflow.
3. **Publish the final documentation contract (13–17).** Rewrite README only after the commands
   exist: quick install first, short product explanation second, documentation links third and the
   preserved License/footer last. Move detailed material into the linked documents, then execute
   the final install lines and structural/link checks. Step 17 removes maintainer-specific defaults
   and must rerun step 16's gate if it changes README content or an install line.
4. **Restore explicit Push in the correct place (18).** This follows steps 1–5 so readiness proves
   one canonical Registry shape, and follows step 17 so no implicit maintainer repository can become
   a push target. `publish` still ends at the reviewed local commit; Push remains separately
   reviewed on Registry Maintainer.
5. **Make local consumption safe, then add it (19–20).** Target-qualified state ownership precedes
   the local Registry adapter so equal local/remote packages cannot collide in configuration or
   credentials.
6. **Verify the whole slice once (21).** Only after tasks 2–20 are complete, run the broad repository
   quality and integration/E2E suites and record the final acceptance evidence.

Command survival is an acceptance invariant: step 3 must leave canonical `lock`, `build`,
`validate`, `audit`, `format` and `publish` callable. `publish` performs the reviewed
build/validate/audit/local-commit aggregate and never pushes. Push remains its own explicitly
confirmed operation and is reachable from Registry Maintainer under step 18. A test proving only
that legacy code disappeared is insufficient unless these retained surfaces are also exercised.

### Test cadence for tasks 2–21

Tasks 2–20 use TDD and the smallest evidence set that holds their claim:

- run the named red/green test module for the changed behavior;
- run format, lint and type checks over changed files and production/test files inside the measured
  damage radius;
- run only the integration or E2E modules crossing a boundary the change actually touches;
- use Hypothesis where the claim is universal and scoped `mutmut` over each changed production
  module with the tests claiming it;
- run documentation, schema, packaging or secret checks early only when the task changes their
  inputs.

Do not run the whole repository quality suite, every integration/E2E module or another broad
cross-family set after each task. Task 21 owns those expensive checks once the implementation scope
is complete: full `make quality`, the full standalone integration/E2E gate where it is not already
included, packaging, docs and secret-shape verification, plus the final acceptance tests for the
five product phases. A failure is repaired at its owning layer and the affected focused set is run
before repeating the necessary closing gate. CP-26 is not verified until task 21 is green and its
results are recorded here.

### Step 2 — `registry scaffold` removed, canonical `publish` retained (2026-09-18)

The CLI parser, request dispatch, curation action/preparation, application exports, Registry
operation/options/planner, wizard route and generated Registry guidance no longer expose
`scaffold`. Active public README, protocol, Registry-maintainer, Enterprise-rollout and tutorial
material no longer tells a reader to invoke it. Historical refactor evidence keeps the old name as
history. Generated Registry README guidance now points to the Source `scan`/`promote` route, held by
an assertion over the actual `init` projection.

`registry publish` remains parseable and keeps its approved-Registry build/validate/audit/commit
path. The replacement test asserts both halves. A deliberate mutation that restored a visible
`registry scaffold --source` parser made exactly that test fail with `SystemExit not raised`; after
restoration it passed.

Focused evidence: 118 tests across the changed command/curation/Registry/wizard modules plus the
README adoption test are green. Ruff format/lint passed over 23 changed Python files; Mypy passed
over the 12 changed production files; `docs-check` and `secret-shape-check` are green. The scoped
mutation run over `registry_commands/templates.py` generated 46 mutants, killed 16 and left 30: two
equivalent UTF-8 codec-spelling changes and 28 pre-existing `_job`/`_aggregate` workflow-generator
survivors recorded as B-145. No broad repository suite was run; D-317 assigns that to step 21.

### Step 3 — canonical Registry commands have one route (2026-09-18)

An initialized Registry is canonical before its first promotion: the two root manifests identify
that empty state unless a retired path is present, while any `registry/versions/` record remains
decisive so a mixed checkout is refused rather than sent through the old compiler. `lock` is always
the read-only immutable-record check; `build` always regenerates `registry/index.json` and
`registry/snapshot.json`; `publish` always runs canonical build/validate/audit and commits locally.
`validate`, `audit`, `format` and the separate CLI `push` reject retired entries, lock/index files
and unversioned packages before their old preparation can run. The default publish subject now
reads the canonical catalog.

The red test started from `registry init` with no versions: the old dispatch created
`aart.lock.json`; the canonical dispatch leaves both old files absent and writes both canonical
catalogs. A deliberate mutation that made an empty initialized Registry non-canonical caused that
test alone to fail at `lock`; restoration is green. The focused command/curation/publish/push set
is 32 tests and passes. Ruff format/lint passed the eight changed Python files and Mypy passed the
three changed production modules. Scoped mutation over `registry_maintenance/promoted.py` killed
all mutants in the new shape detector; ten survivors are in pre-existing package extraction and
are recorded as B-146. The legacy vendor/audit tests now name behavior removed by this step and are
deleted with their fixtures in step 5; no broad suite ran under D-317.

### Step 4 — the consumer and source validators have one representation (2026-09-18)

`sources/validation.py::validate_registry_source_candidate` and
`consumer/runtime.py::_project_graph_source` chose their authority by looking for a `registry/`
prefix and fell through to the workspace compiler when they did not find one. Both now ask the same
two questions in the same order, through the one authority that answers them
(`registry_maintenance/promoted.py`): does this snapshot carry a retired path, and is it a canonical
approved Registry. A retired or mixed checkout is refused and the offending paths are named; a tree
that is not a Registry is refused and the two root manifests it must declare are named. Nothing
falls through.

Deleted with the branch, because nothing reached them afterwards: the consumer's
`_registry_references`, `_locked_index_agrees`, `_registry_entries`, `_verify_registry_owned` /
`_materialize_registry_owned`, `_acquire_registry_reference`, `_RegistryReferenceBinding`,
`_GraphProjection.references` and `_consumer_content_port` (D-320); in the source validator, the
`validate_registry_workspace` import. `_registry_security_evidence` stopped reading
`aart.index.json` and now recomputes the canonical registry state digest instead (D-319).

**One correction to a step-3 leftover.** `tests/source_remediation_test.py`'s rs09 audit test ran
`registry audit` over the retired `registry-v1` fixture, which step 3 had already taught the CLI to
refuse; the test was red before step 4 began. It now builds a canonical Registry on disk through
the new `write_snapshot` fixture helper and still holds its claim — `audit` states findings in a
report, each with its own next step. The twelve failures in `registry_vendor_license_test` and
`registry_quality_planning_test` are the other step-3 leftovers and are unchanged by step 4; step 5
deletes them with their fixtures, as D-318 records.

**Tests deleted rather than repaired.** `test_registry_reference_is_fetched_by_locked_commit_only_for_selected_content`
and `test_reference_only_registry_is_a_valid_marketplace_source` characterized the retired
external-reference mechanism (D-320). Every other registry test in both modules moved onto
`approved_registry_snapshot`, a new shared fixture that builds its registry through the real
promotion rather than by transcribing a tree.

**Targeted semantic mutation (two, one per module).** Weakening the source validator's refusal to
`if retired and not is_promoted_registry(snapshot)` — the mixed-checkout hole D-308 closed — failed
`test_a_registry_mixing_both_representations_is_refused_by_name` and nothing else. Deleting the
consumer's retired-path refusal outright failed
`test_a_registry_carrying_the_retired_representation_is_refused_by_name` and
`test_invalid_native_or_registry_snapshots_fail_closed`, and nothing else. Both restored green.

**Focused evidence.** 117 tests across the consumer runtime, source validation/remediation,
marketplace catalog/projection/trust/lifecycle, source acquisition, TUI marketplace, legacy-authority
reachability and architecture-boundary modules are green, plus 63 consumer install/marketplace E2E
tests. Ruff format and lint pass over the whole tree; Mypy passes over both changed production
modules; `secret-shape-check` is green. Scoped mutation over `sources/validation.py`: 195 mutants,
3 survivors inside the changed function, all string-spelling variants that keep the asserted
substring — down from 8, after adding the tests that hold the not-canonical refusal, the empty
Registry's catalog binding and the returned candidate. Scoped mutation over `consumer/runtime.py`:
592 mutants, 464 killed, 3 survivors in `_project_graph_source` (one pre-existing, two spelling);
the rest are recorded as B-148. No broad suite ran under D-317.

### Step 5 — the retired representation's schema, fixtures and planning halves are deleted (2026-09-18)

B-057 closes here. Deleted, because step 4 left nothing reaching them:
`protocol/registry_tree.py` whole; in `protocol/registry_schema.py` every entry/lock/index parser
and serializer; `protocol/registry_index.py::build_registry_index`; the lock, entry and index models;
`application/registry_maintenance.py`, `registry_maintenance/ports.py` and the mutation types that
only that port consumed; `tests/fixtures/protocol/registry-v1/` and the six test modules that only
described the retired shape.

**Two commands were decided rather than deleted.** `aart security scan` took `--index`/`--lock` as
operator-supplied files nothing produced; it now reads the approved Registry through `--registry DIR`
and projects the catalog from version records (D-322, closing B-147). `promote-native` and
`refresh-native` are withdrawn with the reference mechanism they wrote (D-321), and with them
`--strict`/`--frozen` on `validate`, which asked for a second compiled catalog to be strict about.

**One rule was rebound rather than lost.** `validate_registry_graph` — `requires` resolves inside one
registry, membership is derived — had `build_registry_index` as its only caller. It is now called
from `registry_native_content`'s promoted branch, so the approved representation is held to both
rules (D-325). The `referenced_from` half of `dependency_scope_error` and the `referenced_origins`
parameter went with `entries/`, their only producer.

**Targeted semantic mutations (two, one per claim).** Replacing `_native_registry_content`'s
retired-path refusal with `retired = ()` failed
`registry_quality_planning_test::test_a_registry_carrying_the_retired_representation_is_refused_by_name`
and nothing else — the CLI integration test stayed green, because the CLI refuses at the source
validator as well, which is the point of step 4. Deleting the new `validate_registry_graph` call
failed exactly the two `ApprovedRegistryGraphTest` claims. Both restored green.

**Focused evidence.** Every `tests/*_test.py` module was run one process at a time before the slice
and again after. The repairs that were behaviour, not bookkeeping: the generated CI workflow and its
E2E gate now run five gates rather than six; `registry init` writes `registry/index.json` and
`registry/snapshot.json` and neither retired marker; `_follow_up` no longer names `lock`; the audit's
"this registry also holds external references" coverage note is gone with the references; the
`corrupt-lock-object` system-matrix scenario becomes `corrupt-object` and `native-reference` is
removed. Ruff lint and format pass tree-wide; Mypy passes over the package; the schema freeze was
regenerated with `make release-freeze`. No broad `make quality` ran, under D-317.

**Still red, and deliberately so.** Twenty-six tests across seven vendoring modules fail on B-149:
`project_vendored_package` writes the retired unversioned `artifacts/<kind>/<name>/` layout, which
canonical maintenance refuses by name. D-323 records why they are kept rather than deleted — they
hold vendoring's license, drift and copy-integrity behaviour, none of which is the retired
representation. B-149 is critical and is the next slice's subject.

### B-149 — `registry vendor` writes an approved version, not the retired layout (2026-09-19)

Step 5 left a shipped command producing a Registry its own maintenance refuses: `vendor` wrote
`artifacts/<kind>/<name>/` with no version segment, which is the retired representation by name.
That outranked the numbered plan's next step, because a command that bricks a canonical Registry
cannot wait behind a refactor of the authoring field surface (D-326).

**What moved.** `project_vendored_package` writes `artifacts/<kind>/<name>/<version>/`. Both `vendor`
and `revendor` now project the package, assess its exact bytes, and hand the result to
`plan_bulk_promotion`, so the immutable version directory, the version record and the derived
catalogs are written by one reviewed workspace plan rather than by the vendoring path's own writer.
The maintainer stages an authored wrapper inside the destination version directory; `vendor` reads
it as staging input and prunes it, so it never survives as a second copy beside the promoted one.
`read_vendored_artifact` selects the latest approved `VENDORED` version rather than an unversioned
directory, which is what lets `revendor` report drift against the copy actually published.

**Two versions of one identity.** Re-vendoring into a second immutable version made the Registry
graph hold two packages under one identity, which `validate_registry_graph` had refused as a
duplicate. Duplicate detection is now keyed by identity **and** version; a dependency resolves when
any approved version satisfies its bounds, and collection membership is assigned per version rather
than per identity. Two versions from two different registries under one identity remain a refusal —
that is the ambiguity the check was for.

**Targeted semantic mutations (two), and what the first one revealed.** Reverting
`project_vendored_package`'s package root to the unversioned `artifacts/<kind>/<name>` failed only
`registry_vendoring_projection_test`, twice — the canonical gates stayed green. That is worth
recording rather than filing away: after this repair the approved layout is owned by
`plan_bulk_promotion`, which derives `artifacts/<kind>/<name>/<version>` itself, so the vendoring
writer's own root now only names the staging directory it reads the authored wrapper from. The
mutation that does carry B-149's claim is the second: writing `projected.value.files` instead of
`promoted.value` — bypassing promotion while changing nothing else — failed
`registry_vendored_gates_test`, `registry_vendoring_projection_test`, `registry_vendor_command_test`
and `registry_vendor_delivery_test`, which is exactly the set of claims that say a vendored package
reaches the Registry as an approved version. Both restored green.

**Evidence.** The seven vendoring modules D-323 kept red are green, as is `registry_index_test`.
Every `tests/*_test.py` module was then run one process at a time: no module outside the repair
changed state. Ruff lint and format pass tree-wide; Mypy passes over the package. No broad
`make quality` ran, under D-317.

### Step 6 — the authoring field surface is collected from the parser (2026-09-19)

`tests/authoring_field_surface.py` reads `protocol/authoring.py` and reports every site where the
parser accepts a fixed set of field names. Steps 7 to 12 generate `aart.yaml` from it, so a
generator that transcribed those names would go one field stale on the next parser change with
nothing failing.

Two rules make the reading trustworthy, and both are derived rather than listed. Which functions
accept fields is read from their signatures — a keyword-only `required` or `optional` parameter — so
a new helper is discovered rather than missed. And a wrapper's own fixed fields are read from its
body, so `_nested_type(value, "transport", path=path)` is reported as accepting `type` even though
it passes no field keyword at all. The first draft of this collector dropped exactly those two
`transport` sites, silently, which is the failure mode the step exists to prevent.

A field set the reader cannot resolve statically — `required=required`, a set built with `|`, an
f-string label — is reported as **unresolved**, never as empty. An empty set would claim the site
accepts no field, which is the one wrong answer a generator must not be given. Three of the parser's
seventeen sites are unresolved today, all in the dynamically dispatched input and descriptor
parsing; the generator will have to be told about them explicitly rather than quietly emit nothing.

**Targeted semantic mutations (two, one per rule).** Skipping call sites that pass no field keyword
failed `test_every_field_helper_call_in_the_parser_reaches_the_surface` and nothing else. Making a
computed field set read as the empty tuple failed `test_a_computed_field_set_is_marked_unresolved`
and nothing else. Both restored green.

**Amended while starting step 8.** An unresolved site reported no names at all, which lost
`required`, `help`, `default`, `validation` from `_parse_input` and `pyproject`, `lock`, `path` from
`_parse_dependencies` — every one a field a generated skeleton could have omitted with nothing going
red. An unresolved site now reports the literals it can see inside the computed expression, and,
when the keyword is a bare name, the literals assigned to that name anywhere in the function that
passes it. It stays marked unresolved because the union over branches is an over-approximation.
Two further targeted mutations: reporting no visible literals failed
`test_a_computed_set_still_reports_the_names_it_could_read`; dropping the branch-assignment lookup
failed `test_a_field_set_assigned_in_branches_is_read_from_those_branches` and the test that names
the seven fields directly.

### Step 7 — a deterministic YAML emitter for the generated subset (2026-09-19)

`aart author init` writes `aart.yaml`, and zero runtime dependencies means AART writes it itself.
`protocol/yaml.py` already held the parser for the finite subset, so the emitter was added beside it
and is defined as that parser's inverse: whatever `emit_yaml` returns, `parse_yaml` gives back the
value it was handed. The claim is universal over the subset, so it is a Hypothesis property over
generated documents, with example-based tests for the shapes `aart.yaml` actually uses.

**Quoting is decided by asking the parser.** A plain scalar is written unquoted only when
`_scalar` hands the identical string back, which rules out `true`, `null`, `12` and `---` without a
second list of special forms to keep in step, plus explicit guards for surrounding space, a `#` that
would start a comment, a `:` that reads as a mapping key inside a sequence item, and a reserved
opening character. Everything else is JSON-quoted, which the parser reads with `json.loads`.

**A hole the property found, and why an exhaustive test now holds it.** Hypothesis produced
`"0\x850"`: `\x85` is not a control character by `ord`, but `str.splitlines` ends a line on it, so
the tokenizer read one emitted line as two. The fix is to require `text.splitlines() == [text]`.
The property found it once and did not find it again on the next run, so the rule is held by a test
that derives the breaking set from `str.splitlines` itself and checks every one of them — three
today (`\x85`, `\u2028`, `\u2029`), and whatever a future Python adds.

**What it refuses rather than write.** An empty mapping or sequence has no spelling in the grammar;
a key the grammar rejects; an integer outside the protocol range; a document that is a bare scalar.
Each refusal names the position. `comments` maps a position — `""` for the header, otherwise a
dotted path of keys and sequence indices — to the lines written above it, and a comment aimed at a
position the document does not have is a refusal, because silently dropping it is how a generated
manifest loses its documentation (D-328).

**Targeted semantic mutations (two, one per claim).** Deleting the line-break guard failed
`test_every_character_python_ends_a_line_on_is_quoted` on all three code points and the sequence-item
round-trip property. Deleting the unused-comment refusal failed
`test_a_comment_aimed_at_a_key_the_document_does_not_have_is_refused` and nothing else. Both
restored green.

### Step 8 — `aart author init` writes a full-surface `mcp` workspace (2026-09-19)

A new top-level group, `author`, rather than an action under `registry` or `source`: a Registry is
where an artifact is published to, never where it is written, and `source` is about subscriptions.
`aart author init --kind mcp --name <slug> [--into DIR]` writes `aart.yaml` plus the payload the
manifest declares. `--kind` offers all five kinds from `get_args(AuthorKind)` — the parser's own
vocabulary, so a kind it gains appears in the help without an edit here — and the generator refuses
the four it does not yet build, by name.

**The full surface, with the optional part commented rather than absent.** Every block the parser
accepts is in the file. What is not required is written out as YAML behind `# `, one line of
explanation above it, so narrowing the manifest down is an edit rather than a search through
`protocol/authoring.py`. Three prefixes carry three meanings: `# ` is a line of the document that is
not enabled, `## ` is prose, `#? ` is an alternative to the line above it rather than an addition.
Uncommenting every `# ` yields exactly `AuthorSkeleton.full`, and a test proves that equality — the
commented text is produced by `emit_yaml` from the value itself, which is what makes it true.

**The generator is not a second authority on the schema, twice over.** Statically,
`tests/authoring_field_surface.py` reads the parser and the skeleton must name every field it finds
(step 6, D-327). Dynamically, `author_skeleton` parses what it just generated with the real
`parse_author_manifest` before returning it, so `artifact.name`'s rule is the parser's rule rather
than a copy of it — `github-mcp-` reads as a slug to a scan over the alphabet and is not one
(D-329).

**Three inputs, because one cannot carry every accepted field.** §91 keeps the confidential class
free of any field a credential could be written into, so a secret takes no `default`, no
`validation` and no `help.example`; and a validation is `pattern` or `url`, never both. So the
skeleton carries a secret, a URL-validated config and a pattern-validated config.

**The writer either writes the whole workspace or leaves the directory as it was.** `author init`
is the first AART command an author runs, often into a directory already holding their own work, so
every target is checked with `lexists` before the first byte — a dangling symlink is still something
they put there — and a failure part-way removes what the call made. The generator's own paths go
through `parse_relative_path`, because a path that climbs out of the workspace would be AART's
mistake to catch, not the author's.

**Two repository gates caught real drift and both were right.** `source_remediation_test` and
`adoption_first_contact_test` refused `aart author check` in the skeleton header and the command's
report: steps 10–11 add that command and until then naming it sends an author to a usage error. The
README now documents `author init`, because a shipped top-level command the README has no route to
is capability nobody can find.

**Targeted semantic mutations (eight, one per claim).** Neutralizing the occupied-target refusal
failed the three refusal tests; following links instead of `lexists` failed only the symlink test;
writing `content.strip()` failed only the byte-for-byte test; skipping the parser verification
failed the two name tests and the command's write-nothing test; dropping `parse_relative_path`
failed only the escape test; an empty receipt root, a removed `_undo` and a removed remediation line
each failed only the test that names that claim. All restored green.

**`make mutants` (advisory, scoped).** 87 mutants over `io/author_workspace.py`, 60 killed. The
survivors were diagnostic wording variants and `encoding=` spellings that behave identically for
ASCII, plus three real findings — an unnamed receipt root, an unexercised rollback path and an
unasserted remediation line — which are the last three targeted mutations above.

### Step 17 — no maintainer identity as a default

The owner explicitly requires generated registries and operational examples to carry no default
`M1F1` organization or `M1F1/aart-cli` repository. Current production occurrences include the
generated workflow and Registry README in `registry_commands/templates.py`, the registry-init
remediation in `curation/runtime.py`, and the reference registry origin in `scripts/release.py`.
The Enterprise rollout guide describes the same default; `pyproject.toml` still points at the
older repository. Inspect each consumer-facing occurrence and replace it with a value supplied by
configuration, a neutral example, or a clear missing-configuration refusal as appropriate. Update
tests so generated output and runtime defaults are checked for this rule. Historical records and
the Product Specification's identification of the target repository remain factual records, not
defaults. Record any necessary choice about an unset tool repository before implementation.

### Step 18 — Registry Maintainer owns Push and explains readiness

This step supersedes D-255's TUI-only withdrawal while preserving its safety boundary. Push does not
belong to initialization, rebuild, single promotion or bulk promotion. It is an action on screen
46's existing local Registry workspace row. Returning there after any workflow — or reopening AART
later — derives the same answer from current durable state. A connected approved-snapshot row, a
Candidate and a Source never own the action.

The screen must not collapse three different facts:

1. **Accepted snapshot** — the consumer-visible revision and snapshot read from the Registry's
   default branch.
2. **Local snapshot** — the exact Registry worktree path, branch, `HEAD` and canonical content
   digest currently under maintenance.
3. **Push readiness** — whether that exact committed local state passed every mandatory Registry
   publication gate and has something safe to push.

A local snapshot differing from the accepted snapshot is normal unpublished work. It becomes
push-ready only when the worktree and index are clean, `HEAD` is exact, the canonical generated
outputs are reproducible with no pending build change, and the mandatory gate set is green over
those committed bytes. Readiness reuses one application-level publication preparation shared with
`registry publish`; it is not inferred from a wizard flag, commit subject or the mere presence of
unpushed commits. The gate set is the Registry's canonical one: format check, strict/frozen
validation, canonical lock check, reproducible build check, audit and each required compatibility
check. Step 18 must remove any drift between that shared contract, CLI `publish` and the generated
Registry workflow rather than introduce a third list.

The workspace row always shows either `Push: ready` or `Push unavailable`, followed by every
blocking check and its actionable diagnostic. Typical blockers are: the launch worktree is not a
Registry, the worktree or index is dirty, no exact commit exists, generated files would change,
validation/audit/compatibility failed, there is nothing ahead of the remote, or the only current
target is forbidden. The `[p] Push` binding is advertised only when the composed state is ready;
preparation and execution repeat the identity, commit and gate checks so stale UI state fails closed
with the same diagnostics.

When AART was launched on an existing named branch that is neither `main` nor the Registry's
default branch, that current branch is the only target. If its remote branch does not exist, the
ordinary push creates it. AART does not redirect the commit to another existing branch. If the
checkout is on `main`, another default branch or detached HEAD, the review form accepts a new branch
name. Its suggestion comes from the most recent producing action when still available in the
session (`aart/init-registry`, `aart/rebuild-registry`,
`aart/promote-<artifact>-<version>`, `aart/bulk-promote`), otherwise it is
`aart/registry-update`.

The configured Registry remote is displayed, with `origin` as fallback. Confirmation reuses
`prepare_registry_publication` and `publish_registry_commit`: it pushes the exact eligible commit,
creates an absent remote branch, advances an existing one only when ordinary non-force Git permits
it, and refuses literal `main` plus the configured and remotely advertised default branch. It never
merges, fast-forwards the consumer branch or opens a pull request. The typed receipt remains visible
on Registry Maintainer with review/merge and Registry Sync as the remaining work.

The launch directory is a security boundary, not a hint. AART resolves the one Git worktree
containing `working_at` and proves that its root is the canonical Registry workspace represented by
the local row. If that worktree is a Source or another repository, resolution stops there rather
than continuing upward to a parent Registry. The row remains visible with the ownership refusal;
nothing in a Source checkout, Candidate source, unrelated Git repository or read-only Registry
subscription can trigger a push.

Acceptance covers state recomposition after init, rebuild and single/bulk promotion and after a
process restart; accepted-versus-local snapshot presentation; every readiness blocker and its
diagnostic; current-branch targeting and absent-branch creation; the fallback new-branch form;
non-force update and divergence; literal-`main` and default-branch refusals; exact Registry worktree
ownership; Source and parent-repository refusals; and a mutation proving that skipping any mandatory
gate makes the action unavailable.

### Step 19 — installation-target-qualified input and credential state (B-144)

Introduce one nominal installation-target identity at the domain/application boundary. Its stable
owner fields are Registry alias, artifact kind/name, normalized destination context (project/user
scope and concrete root), and harness/profile; `input_id` is unique only inside that owner. Version
is not part of the owner, so a compatible update at the same exact target may preserve state.

Carry that identity through input composition, persisted ordinary values, credential-provider
references, setup state, receipts and lifecycle dependency edges. Equal input ids or canonical
bytes never share state implicitly. The macOS Keychain adapter derives a deterministic,
collision-resistant item identity from the complete key and uses an opaque digest for filesystem
roots rather than exposing raw paths. Secret values remain solely inside the provider.

Red-first acceptance installs the same remote-Registry artifact into two project roots and user
scope, and installs equal artifacts from two aliases into one target. Each owner receives distinct
ordinary values and credential references, survives reopen/update/reconfigure independently, and
can be uninstalled without touching another owner. A separate path explicitly binds several owners
to one provider reference and proves every dependant edge and destructive-action warning remains.
Property tests hold that distinct valid complete keys do not collide; a scoped `mutmut` run covers
the identity module and input-composition seam. This closes B-144 and establishes INV-243 before
any local Registry adapter is admitted.

### Step 20 — local Git checkout as a configured canonical Registry (B-143)

Add `registry-local` beside `registry-git`, with a Remote Git / Local checkout choice in Add
Registry and the same capability in the deterministic CLI. A local path must normalize to the root
of a Git worktree containing a valid canonical Registry. Add snapshots its exact `HEAD`, commit and
content digest before saving configuration; Sync reads the successor without network access and
atomically advances only after the same validation used for remote Git. Failure preserves the last
known valid snapshot.

Both transports feed one Registry admission service, source-store snapshot representation,
Marketplace projection, resolver, policy evaluator and installation path. Local transport neither
changes trust nor turns `Promoted locally` into published; it makes the canonical version selectable
under its configured alias. A local and remote connection to the same Registry may coexist only
under distinct aliases. Qualified coordinates remain distinct, and an equal unqualified match is
explicitly ambiguous.

Acceptance covers coexistence, alias-qualified selection, unqualified ambiguity, dependency and
Collection closure, install/update/status, receipts containing alias/snapshot/commit/origin, and an
invalid local successor retaining last-known-good state. Reuse step 19's independent project/user/
harness configuration and credential cases through the local and remote aliases, including
explicit shared-provider warnings. Local Sync is read-only with respect to the checkout and proves
it performs no network operation. This closes B-143; it remains distinct from Candidate Test
Install, which exercises pre-promotion candidate content rather than the canonical Registry.

## Settled authoring boundary for this slice

CP-26 does not support authoring directly inside a Registry. Author manifests and payloads live in
a Source checkout; `scan` and `promote` compile them into the canonical Registry representation.
Supporting Registry-origin authoring would require a future explicit Product Specification change
and a new provenance origin kind. It is not an alternate implementation of any CP-26 task.
