# CP-26 — Canonical Registry maintenance, authoring tools and local consumption

Status: **active**. Steps 1–18a are done; step 19 is next. The plan has **23 tasks** after the
2026-09-19 additions of CP-26.18a (D-332) and CP-26.20a (D-348); task 21 remains the final broad gate. D-333 requires
independent input entry for each installation and withdraws all cross-installation sharing.
Product Specification §169 defines the accepted layout and namespace; step 19's ownership wiring
is pending. §170 adds installed-MCP smoke verification, also pending. Historical step records
below retain the command names actually verified then.
The machine plan keeps an unfinished step as `todo` until completion evidence is recorded.

PR #21 follow-up (2026-09-18): D-308's authoring refusal now points to the runnable `--help`
forms of `scan` and `promote`. The visible-command test was red first, green after correction,
red under a deliberate one-command regression, then green when restored. This release repair
precedes step 2 and does not alter its scope.

PR #21 second CI follow-up (D-310): two credential-shaped URL assertions now use the runtime
fixture builder, and the secret-shape gate runs before dependency installation. A deliberate
literal restoration made the scanner red; moving the gate back after installation made the
ordering test red. This release repair likewise precedes step 2.

This supersedes the earlier draft of this file, which planned a compatibility window. The
owner confirms the product is just starting and has no users requiring backward compatibility
(D-334, 2026-09-19). **Every CP-26 task may make breaking changes** to old commands, names, paths,
formats, schemas and internal rules. Implement the accepted specification directly; do not add
compatibility aliases, fallback readers, dual state, migration commands or deprecation periods.
External harness contracts and the new ownership/secret rules remain acceptance boundaries.

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

- `registry scaffold` — authors in place. Replaced by `aart-cli author init` plus `scan` + `promote`.

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

## 1.3 `aart-cli author init`

A new top-level group. Not under `registry` (wrong target) and not under `source` (that group is
about subscriptions, not content).

```
aart-cli author init --kind {skill,guideline,mcp,hook,memory} --name <slug> [--into DIR]
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

## 1.4 `aart-cli author check`

```
aart-cli author check [--source DIR] [--json]
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

def accepted_fields(module="aart_cli/protocol/authoring.py") -> dict[tuple[str, str], list]:
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
| 8 | `aart-cli author init` emits a full-surface `aart.yaml` for `mcp` | first kind end to end, guarded by step 6 |
| 9 | `aart-cli author init` emits the same for `skill` | proves the generator is kind-driven, not special-cased |
| 10 | `aart-cli author check` proves every discovered manifest parses | through `parse_author_manifest` itself |
| 11 | `aart-cli author check` proves each manifest would be accepted by `scan` | the promotable claim |
| 12 | The remaining three kinds | `guideline`, `hook`, `memory` |
| 13 | README opens with the fastest normal-user path to an installed artifact | install AART → connect/sync Registry → choose in Marketplace → install into a harness → verify; TUI first, compact CLI equivalent second |
| 14 | A short “What AART is” and categorized documentation index follow the quick start | explanation stays bounded; authoring, Registry, Enterprise, architecture and contributor detail are links, not README tutorials |
| 15 | Detailed current material moves into focused documents; License remains last | preserve existing MIT wording and copyright/footer; every public documentation link resolves |
| 16 | Every final install line and README structural promise is executed by a gate | manual wheel download and `gh release download`, section order, bounded explanation, valid links and final License; later edits rerun it |
| 17 | Remove `M1F1` as a generated or operational default | Registry workflow/README, CLI guidance, release defaults and public configuration docs; no organization or repository baked into a generated registry |
| 18 | Registry Maintainer may push its publish-ready local snapshot | workspace-scoped action; visible readiness and blockers; current branch or a new review branch, never `main` or the default branch |
| 18a | Use `aart-cli` throughout active names and one portable application home | D-332; `~/.aart-cli` / `AART_CLI_HOME`, central canonical content/receipts, harness-owned installation path contract; no compatibility aliases |
| 19 | Each installation owns its runtime, names, receipt, configuration and credentials | D-333/D-349; B-144/B-150; full owner and input id; versionless harness names and Keychain addresses; separately entered values, no sharing |
| 20 | Add Registry synchronizes a canonical Registry from a local repo and selected branch | B-143/D-350; normal admission/Marketplace/install path, then installed-MCP smoke tests |
| 20a | CLI smoke verification of all or selected locally installed MCPs | D-348, §170, issue #27; declared read-only calls, full hierarchy, mandatory OpenCode/Tabnine CLI evidence and an additional Claude adapter |
| 21 | Run the full CP-26 verification only after every implementation task is complete | full quality, integration/E2E, packaging/docs/secret gates and final acceptance evidence |

The numbered order is the execution order and is grouped into seven dependency phases:

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
5. **Settle paths and isolate installations, then add local consumption (18a–20).** Step 18a
   unifies names/home resolution and defines harness-owned destinations. Step 19 wires those
   destinations and complete ownership through runtime, receipts, inputs and lifecycle, requiring
   separate entry for every target. Step 20 reuses that contract for local Registry acquisition.
6. **Verify installed MCPs locally (20a).** Build the safe probe contract and the direct/harness
   runners on 19's installation identity and 20's local Registry route. Keep the full hierarchy.
7. **Verify the whole slice once (21).** Only after all implementation tasks, including 18a and 20a, are complete, run the broad repository
   quality and integration/E2E suites and record the final acceptance evidence.

Command survival is an acceptance invariant: step 3 must leave canonical `lock`, `build`,
`validate`, `audit`, `format` and `publish` callable. `publish` performs the reviewed
build/validate/audit/local-commit aggregate and never pushes. Push remains its own explicitly
confirmed operation and is reachable from Registry Maintainer under step 18. A test proving only
that legacy code disappeared is insufficient unless these retained surfaces are also exercised.

### Test cadence for tasks 2–21

D-334 records the owner's request for proportionate implementation checks: use small focused
checks, reuse relevant tests and avoid over-testing mechanical changes. No compatibility matrix
or new test per renamed string is required. A namespace-only substitution is not a separate
semantic mutation claim. Runtime identity/isolation and new command/path behavior remain the
material checks; no broad or unrelated test/mutation campaign runs during implementation.

Implementation tasks 2–20a, including 18a, use the smallest evidence set that holds their claim:

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
six product phases. A failure is repaired at its owning layer and the affected focused set is run
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

**Two commands were decided rather than deleted.** `aart-cli security scan` took `--index`/`--lock` as
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

`aart-cli author init` writes `aart.yaml`, and zero runtime dependencies means AART writes it itself.
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

### Step 8 — `aart-cli author init` writes a full-surface `mcp` workspace (2026-09-19)

A new top-level group, `author`, rather than an action under `registry` or `source`: a Registry is
where an artifact is published to, never where it is written, and `source` is about subscriptions.
`aart-cli author init --kind mcp --name <slug> [--into DIR]` writes `aart.yaml` plus the payload the
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
`adoption_first_contact_test` refused `aart-cli author check` in the skeleton header and the command's
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

### Step 8 amendment — a payload path is relative to the manifest, not under `payload/` (2026-09-19)

The first generated manifest wrote `include: [payload/**]`, `entrypoint: payload/server.py` and a
dependency path under `payload/`, and put the files there. It parsed, and it compiled — which is
the whole problem. `compile_author_snapshot` places the author's files under the package's own
`payload/` root, so the generated workspace compiled to `payload/payload/server.py`. Nothing in the
parser, the compiler or any gate refuses that; the shipped example in
`docs/examples/author-source/example-mcp/aart.yaml` has had the correct shape all along, and the
generator was the thing that disagreed with it.

Found by asking what the author's *next* command does with the file rather than by re-reading the
manifest, which is the general lesson: a generated manifest is only correct against the pipeline it
feeds. The skeleton now names `server.py` and `requirements.txt`, and
`test_the_payload_arrives_under_its_own_names_and_not_a_second_time` compiles the generated
workspace through `compile_author_snapshot` and asserts both that each payload file arrives at
`payload/<name>` and that no entry contains `payload/payload/`. Two further targeted mutations —
restoring either prefix — fail exactly that test.

`test_the_payload_skeleton_matches_what_the_manifest_includes` asserted the old prefix convention
and was corrected rather than deleted: it now requires the written payload files and
`payload.include` to be the same set, which is the claim that was meant and does not depend on
where the files sit.

### Step 9 — the same generator writes a `skill` (2026-09-19)

A kind is not a parameter on one document, so the generator gained a `_Blueprint`: the document, the
keys written out disabled, the nested positions disabled inside a block that stays live, the closing
notes and the payload. `_BLUEPRINTS` maps kind to blueprint and `GENERATED_KINDS` is derived from
it, so registering one is the whole of adding a kind. Every claim in `author_skeleton_test` now runs
over every generated kind rather than over `mcp`: parseability, the `full` document, the
uncommenting equality, compilation, the anti-drift oracle and the alternatives.

**What a skill declares is different, not smaller.** A skill is delivered by copying its tree into
the harness. The parser accepts `transport`, `runtime` and `launch` on one — probed directly, it
compiles — and the resulting package advertises `transport/stdio` and `protocol=stdio`, which is a
skill claiming to be a server. So the generator does not write them, live or into `full`, and names
them in a closing `#?` note with the reason. `python` is offered the same way, because enabling it
also means adding the dependency file to `payload.include`, which the generator cannot do for an
author who has not decided on one. Naming them keeps §1.5's requirement intact: the anti-drift
oracle still finds every accepted field as a key in the skill skeleton, and the mutation that
removes the note fails it.

**`payload/SKILL.md` is what `init` owes a skill author.** `native_tree` refuses a skill package
without it, so discovering it from a promotion refusal is exactly the failure §1.3 is written
against. The generated `SKILL.md` carries the section shape a harness reads.

**A trap the alternatives test caught.** The offered `launch.arguments` alternative was written
`- --once`, which does not parse: `-` is a reserved opening character in this subset, so an author
uncommenting it would get a refusal from the file AART wrote them. The value is now quoted, and the
test that had asked only for a mapping entry now asks the emitter's own question — a sequence item
an author uncomments must be quoted unless `_plain_safe` would have written it bare.

**Targeted semantic mutations (three).** Renaming the required skill document failed the payload,
compilation and protocol tests; dropping the not-generated note failed the anti-drift oracle for
`skill` and the block-naming test; pointing the `skill` blueprint at `_mcp_blueprint` failed seven
tests across compilation, the launch-block claim and the payload claim. All restored green.

### Step 10 — `aart-cli author check` proves every manifest parses (2026-09-19)

The first of §1.4's two claims. `aart_cli/authoring/check.py` is pure: it takes a
`SourceSnapshot` somebody else read and returns an `AuthorCheckReport` of one `ManifestVerdict` per
discovered manifest. Discovery is `discover_author_manifests` and acceptance is
`parse_author_manifest` -- both called, neither copied, for the reason §1.4 gives: a checker that
lints licenses a manifest the scanner then rejects, and one that is stricter makes an author edit a
correct file until a wrong one passes.

**The tree is read the way a Source Sync reads one.** `read_author_workspace` builds a
`LocalSnapshotRequest` against the same `read_local_snapshot` the source path uses, under a
`working-tree` alias. So `check` sees the file set a Source Sync would see -- the same limits, the
same exclusions -- rather than a second walk of its own that could disagree about what is in the
tree (D-330).

**Every manifest is reported, not the first refusal.** An author with four manifests gets four
verdicts and one exit code. A tree holding no manifest at all is a refusal rather than an empty
pass, because an author who mistyped a directory would otherwise read "nothing wrong" as "nothing
wrong with my manifest".

**Targeted semantic mutations (three).** M14, returning `()` instead of the parser's diagnostics,
failed the acceptance and refusal tests. M15, treating an empty discovery as a pass, failed the
empty-tree test. M16, `all` -> `any` in `AuthorCheckReport.accepted`, failed exactly
`test_one_bad_manifest_beside_a_good_one_fails_the_whole_check`. All restored green.

**A process finding worth carrying.** M16 is a same-length edit, so reverting it left a
`__pycache__` entry CPython considered current: the source read `all` while the loaded bytecode ran
`any`, and the test failed against code that was already correct. Disassembling the property found
it. Any targeted mutation that does not change a file's length must be followed by clearing
`__pycache__`, or the revert is not real.

**Evidence.** 87 tests across the five affected modules, `make unit`, `make typecheck`, Ruff check
and format. `aart-cli author check` is now a command the package may name, so the pointers in the
skeleton header, `init`'s closing line and the README are live again and
`source_remediation_test` parses them. The empty-tree remediation names
`aart-cli author init --kind mcp --name my-artifact`, because a bare `aart-cli author init` is a dead end
that gate refuses.

### Step 11 — `aart-cli author check` proves the manifest would be promoted (2026-09-19)

§1.4's second claim, and the one a person cannot check by eye. `check` now calls
`compile_author_manifests` -- the per-manifest boundary -- and reports the coordinate each manifest
compiled to:

```
ok    github-mcp/aart.yaml  ->  mcp/github-mcp@0.1.0
```

**The compile needs an identity the tree already has.** Compiling requires a canonical source
location and an immutable pin, and the local reader computes both. `read_author_workspace` now
returns `AuthorWorkspaceRead(root, revision, snapshot)` rather than a bare snapshot, so the
`local:<sha256>` revision the reader produced is what the compiler is handed. Nothing is invented
and nothing is persisted.

**The redundant parse was deleted, and mutmut is why.** The first version called
`parse_author_manifest` and then the compiler. `make mutants` killed 61 of 70 and one survivor was
`parsed = None` -- which is correct, because `_compile_manifest` parses first and carries the
parser's own diagnostics as the refusal. The explicit parse produced the same text twice and made
this module a second place §1.4's ordering could drift, so it is gone. Ordering is still held,
inside the function that owns it.

**A Collection manifest is no longer judged as a broken artifact.** `registry scan` compiles
artifacts and passes over Collections; the step 10 checker parsed every discovered manifest as an
artifact and told an author with a correct `aart.json` that it was "missing required field
'artifact'" -- §1.4's stricter-is-no-better failure, in the form an author would actually hit. A
manifest the compiler neither compiled nor refused is how the compiler says "not mine", so it is
reported `skip` with the reason and no package. Checking a Collection against
`parse_author_collection_manifest` is **B-154**, not this step.

**Targeted semantic mutations (three).** Ignoring the compiler's refusals failed the
parses-but-will-not-compile test; treating an uncompiled manifest as an artifact failed the
Collection test and its JSON twin; dropping the version from the reported coordinate failed the
coordinate test and its JSON twin. All restored green.

**`make mutants` findings, acted on.** Two `continue` -> `break` survivors said no test held that
every discovered manifest is reported however the one before it ended; one said the empty-tree
refusal need not name a command. Both are now tests. Survivors fell from 9 to 4, and the four left
are `"text"` -> `"XXtextXX"` and case flips on prose, which is the class this repository does not
pin in a test.

**Evidence.** 17 tests in `author_check_test`, `make unit`, `make integration`, `make typecheck`,
`make docs-check`, Ruff check and format. No broad `make quality` ran, under D-317.

### Step 12 — the generator covers every kind the parser accepts (2026-09-19)

`guideline`, `hook` and `memory` joined `mcp` and `skill`, and `GENERATED_KINDS ==
tuple(sorted(get_args(AuthorKind)))` is now a test: a kind the parser accepts with no blueprint
behind it would be a `--kind` the CLI offers and the generator refuses, and this turns red the day
that happens.

**Each shape was taken from the compiler, not chosen.** `native_tree` refuses a `guideline` or a
`memory` package whose payload is not *exactly one* Markdown document and nothing else. That is why
neither skeleton can offer a dependency file: the file such a descriptor would name could not be in
the payload at all. The closing note says so, rather than leaving an author to discover it from a
promotion refusal. A `hook`'s `hook.json` is *authored*, unlike `mcp.json`, which
`parse_author_manifest` reserves for the compiler; `package_hook` requires non-empty `name`,
`command`, `event` and `matcher`, requires `command` to begin `${SCRIPT_DIR}/`, and requires the
file it names to be in the payload **and executable**.

**The executable bit is why a payload entry became a value.** Compilation does *not* check it --
probed directly, a hook with a non-executable script compiles and would be promoted -- and
`package_hook` refuses at install time with "the harness could not run it". An `init` that wrote
`run.sh` unexecutable would therefore hand an author a workspace that compiles, promotes, and then
refuses to install, which is exactly the failure §1.3 exists to prevent. So `AuthorSkeleton.payload`
is now a `tuple[PayloadFile, ...]` carrying `executable`, and `write_author_skeleton` chmods it
(D-331).

**`launch` on a document kind is refused; `transport` and `runtime` are not.** Probed: a guideline
declaring a launch fails compilation with `launch.entrypoint run.py is outside the declared
payload`, because the payload is one Markdown file. `transport` and `runtime` are accepted on every
kind. All three are therefore named in a `#?` note rather than generated, which keeps §1.5's
requirement intact.

**Targeted semantic mutations (five).** Writing the hook script non-executable failed both the
install-time reader test and the on-disk test; giving a memory a second payload file failed the
one-document, compilation and payload-matches-`include` tests; a hook `command` that does not name
the delivered script failed the install-time reader test; returning the wrong `kind` on the
skeleton failed the new identity test for four kinds; and emptying the list of generated kinds in
the refusal failed the new refusal test. All restored green.

**`make mutants` findings, acted on.** Scoped mutation of `skeleton.py` killed 771 of 1045; 274
survived, 29 of them in the generator's logic and the rest in literal template text. Two were real
unheld claims and are now tests rather than backlog: nothing asserted `AuthorSkeleton.kind` or
`.name` (every other test read the manifest text instead of the value carrying it), and the
ungenerated-kind refusal could stop naming the kinds it *does* generate unnoticed. The remainder is
B-155.

**Evidence.** 65 tests across the three author modules, `make unit`, `make integration`, `make
typecheck`, `make docs-check`, Ruff check and format. No broad `make quality` ran, under D-317.

### Step 13 — the README opens with the route, not with the architecture (2026-09-19)

`## Install an artifact` is now the first section after the title, and it is the whole of §1.6's
sequence: install AART, connect a Registry, find the artifact, install it into a selected harness,
verify. The TUI follows as the route for a person, stated as what it is -- the same canonical
requests, not a second command engine. `## One contract` and the three-names warning moved below
it; nothing was discarded.

**Everything unknown stays a placeholder.** `<repository>`, `<alias>`, `<registry-url>`,
`<kind>/<name>` and `<harness>`, with the four built-in profiles named once. The route names no
host, for the same reason the install grid does not: a markdown file cannot know which instance it
is being read on, so an address written here is wrong in every fork (D-277).

**The route is held as commands, not as prose.** `QuickStartRouteTest` slices the section and hands
every `aart …` line in it to the shipped parser with the placeholders substituted. A flag the
parser does not have is the failure this is written against -- the reader is at a shell, and prose
that reads well and does not run costs them the afternoon the page was meant to save. The other
claims are the ordering (§1.6 fixes that a new user does not read an architecture section first),
completeness of the five steps, that the reviewing command is shown before the one that applies it,
and that no address a fork would correct appears.

**A test that failed as an error, fixed.** The section was first sliced between two named
headings, so reordering it raised a slice error in five tests instead of failing the one that
names the claim. It now slices at the next top-level heading, which also leaves step 14 free to put
something else after it.

**Targeted semantic mutations (three).** Replacing `--profile` with a flag the parser does not have
failed only the parser test, naming the offending line; showing only the `--yes` form failed only
the review-before-apply test; moving `## One contract` above the route failed only the ordering
test. All restored green.

**Not in this step.** Step 14 owns the bounded "What AART is" and the documentation index; step 15
moves the detailed sections into focused documents; step 16 executes the install lines themselves.
`## Install and quick start` therefore keeps its heading and its content, and the quick start links
down to it for `pip`, `pipx` and the private-instance cases.

**Evidence.** 20 tests in `adoption_first_contact_test`, `make unit`, `make typecheck`,
`make docs-check`, Ruff check and format. No broad `make quality` ran, under D-317.

### Step 14 — what AART is, and where everything else is written down (2026-09-19)

`## One contract` is gone as a heading; its three claims are inside `## What AART is`, which is now
the second section. The orientation says what AART is a package manager *of* -- the things an agent
is configured with rather than the code it edits -- names all five artifact families, walks the four
places an artifact passes through, and only then names the three roles the tool plays on the
consumer's side. Nothing about compilers or effect boundaries; §1.6 asks for orientation and the
reader has already installed something by the time they reach it.

**Source, Candidate, Registry and Marketplace are introduced in that order**, which is also the
order a test checks. They are four different things, the diagnostics name them individually, and a
reader who has conflated any two cannot act on the message they will eventually get.

**Bounded, held as a ratio rather than as a number.** A line ceiling written in a test is a number
somebody raises by one. The claim is that the orientation stays under half the length of the route
it explains: 22 lines against 72, so there is room for another paragraph and no room for a chapter.
The first version of this claim said merely "shorter than the route", and the mutation that was
supposed to prove it walked straight through -- forty lines of invented architecture still fit under
72. A bound a mutation walks through is not a bound, and the test now says what it holds.

**The index holds the direction `docs-check` cannot.** That gate reads every link and refuses one
whose target is missing. Nothing read the documents and refused one that no link reaches, and
unreachable is the commoner failure of the two: a page is written, merged, and then found by nobody
while the README goes on pointing at the handful somebody remembered. Before this step the README
linked 15 of the 25 public documents. It now links all 25, in nine groups, and a new document under
`docs/` that nothing links fails the test by name. `docs/refactor` is excluded deliberately: it is
the migration's working record, evidence for the next agent rather than something a reader is
offered, and a separate test refuses a link into it.

**The Product Specification is a group, not a preamble.** It was first a lead sentence above the
groups, which made it the one link floating outside the structure and cost the grouping test its
meaning. It is now the first group of one, so "no link outside a group" is a claim with no
exception carved into it.

**Targeted semantic mutations (six).** Dropping `hooks` from the families sentence, renaming
`Candidates` to `Registry` in the path, deleting one document's link, floating a link above the
first group, and padding the orientation past half the route each failed exactly one test -- the one
whose name states that claim. Moving the orientation above the route failed four, which is correct:
that mutation breaks the ordering and empties the section at the same time. All restored green.

**Not in this step.** Step 15 moves the detailed sections into these documents and keeps License
last; step 16 executes the install lines and holds the section order, the bounded explanation, the
links and the final License as a gate. CP-26.18a will rename the advertised commands and reruns
step 16 afterwards. `## Install and quick start` and everything below it is unchanged here.

**A gate repaired on the way through, not caused here.** `make unit` failed on
`release_test::test_the_committed_freeze_is_the_freeze_of_this_tree`. `docs/protocol/native-source-v1.md`
and `docs/protocol/registry-v1.md` are normative schema inputs, the specification-alignment commit
added warning banners to both, and `docs/release/schema-freeze.json` was not recomputed. D-275 puts
that comparison in the unit gate precisely so the pull request that moved a schema fails, rather
than the release after it. `make release-freeze` was run and the diff is those two digests and
nothing else. Nothing in step 14 touches either document.

**Evidence.** 28 tests in `adoption_first_contact_test`, `make unit`, `make typecheck`,
`make docs-check`, Ruff check and format. No broad `make quality` ran, under D-317.

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

**Current status: done.** The later dated partial record is historical; its producing-action
branch suggestion carry-over was completed in 18a (D-347). On 2026-09-20, a stale handoff pointing
at `4fe1fe4` was checked against HEAD `64db5c0`: 76 focused tests passed across publication
readiness, publication I/O, branch suggestions, Push CLI, publish CLI and workspace presentation.
No implementation or plan status was changed by this audit. Step 19 remains in progress with its
separately recorded failures; this is not whole-branch verification.

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

### Step 18a — aart-cli namespace, portable home and harness path contract (D-332)

Status: **complete**. Added by the owner on 2026-09-19; executed after 18 and before 19. Names
and paths must be settled before wiring the new installation identity. Do not renumber task 21.

**Done so far — the name the machine sees.** The import package is `aart_cli` (254 modules moved,
no `agent_artifacts` left to import), the single console script is `aart-cli`, `prog="aart-cli"`,
and every command line the product prints, documents or executes now begins `aart-cli ` rather than
`aart ` (125 files). The pieces that carry the name outside the package moved with it: the
Enterprise CI shim writes and version-checks `$bin/aart-cli`, the pin file is `.aart-cli-version`,
the diagnostic is `aart-cli-version-unsupported`, and `scripts/distribution_smoke.py` looks for
`aart-cli` on the routes it installs. The schema freeze was regenerated in the same change, because
the rename moved every normative schema input's path (D-275). `unit`, `integration`, `lint`,
`typecheck`, `format-check`, `packaging-check`, `docs-check` and `secret-shape-check` are green over
that state; task 21 still owns the full suite (D-317).

Two guards had to be told what the rename means rather than being weakened by it. The install-route
gate reported `documented install line installed no \`aart\``, which was true and was the point --
it reads the documented lines and runs them, so it caught the one place the sweep had not reached.
The first-contact guard began reporting five invented commands, all of them from the Product
Specification, which the owner had already written in the new namespace: the specification names
commands the executable does not have yet, on purpose, so it is the one linked document that is not
instructions to a reader and is now excluded there with that reason recorded in the test.

**Done so far — the names the filesystem sees.** Author manifests are `aart-cli.yaml` and
`aart-cli.json`; a registry init writes `aart-cli-registry.json`, `aart-cli-source.json` and
`.github/workflows/aart-cli-registry.yml`; the managed region inside somebody else's `CLAUDE.md` is
delimited by `<!-- >>> aart-cli memory:<name> >>> -->`; the project state directory is `.aart-cli`;
payload formats are `aart-cli-<kind>-v1`, compliance levels `aart-cli-native` and
`aart-cli-compatible`, manifest schemas `aart-cli.dev/<kind>/v1`, the built-in security provider
`aart-cli-baseline`; and every environment and CI variable is `AART_CLI_*`, including the
`AART_CLI_SECRET_` and `AART_CLI_CONFIG_` prefixes a launcher injects an installation's inputs
through. `AART_DUMMY_USER` and `AART_DUMMY_TOKEN` stayed: they belong to a fixture artifact rather
than to the tool, and an artifact binding whatever variable it likes is what they demonstrate.

Three of those are content-addressed rather than merely spelled, so the rename is a format change
and is meant to be: the compiler options digest seed, the payload format in every artifact manifest
and the schema identifier in every author manifest. A regular expression cannot see an assembled
name, and two places assembled one -- `f"aart-{kind}-v1"` in a security fixture and the marker's
literal text in two block tests -- which the gate caught.

**Done so far — one portable home.** `resolve_config_paths` resolves `AART_CLI_HOME` if it is set
and `<user-home>/.aart-cli` otherwise, identically on macOS and Linux, and refuses an unusable
explicit value rather than falling back (D-344). The §169.2 layout needed no design: `objects/`,
`sources/`, `state/`, `locks/` and `tmp/` were already composed under one `data_root`, which became
the home, and `cache/` moved inside it. Machine policy stayed outside, because a rule an
environment variable can step around is not a rule. `plan_factory_reset` was rewritten rather than
renamed -- it names the seven managed entries and the configuration lock and never the home itself,
so a reset cannot delete whatever a variable pointed at, and a file the tool did not write inside
its own home now survives one (D-345). `domain/installation_tree.py` holds the §169.3 policy,
`<harness root>/aart-cli/<kind>/<alias>/<name>`, with the harness root as an argument because which
directory each harness tolerates is measured in 19 (D-346). `docs/configuration/application-home-v1.md`
documents the home, the variable and what the variable cannot move; nothing documented
`AART_CLI_HOME` before.

Evidence: four targeted semantic mutations, each red then restored -- an unusable explicit home
falling back to the default (4 subtests red), machine policy following the home into it (2 red),
the reset plan naming the home itself (11 red), and the Registry alias dropped from the tree (9
red). Scoped `make mutants ONLY=aart_cli/configuration/paths.py` left fifteen survivors, all
message arguments, dead `else` branches under the narrowed test scope, or -- in `_absolute`'s
`or` -> `and` -- a condition whose behaviour `ConfigPaths.__post_init__` re-checks one layer down,
so the refusal still happens for the reason the test names. None is a claim the slice makes and
nobody holds.

**Deferred by contract to step 19.** `install_state/paths.py` still writes a project-scope receipt
store at `<project>/.aart-cli`, which §169.2 replaces with a project-root-qualified record in the
application home; that is receipt identity, which step 19 owns ("Step 19 connects that policy to
every lifecycle writer"), and `domain/placement.py` keeps its beside-the-receipt authority until
the same step replaces it.

**Carried in from step 18, now complete.** The Push review's branch suggestion used to be the
constant `aart-cli/registry-update`. Step 18 required it to come from the most recent producing
action -- `aart-cli/init-registry`, `aart-cli/rebuild-registry`,
`aart-cli/promote-<artifact>-<version>`, `aart-cli/bulk-promote` -- which needs the reducer to carry
which action produced the commit, because the commit subject cannot tell init from rebuild
(`publish` writes both). It was left here rather than done twice because this step renamed that
namespace, and is implemented with the new names below.

**The implemented mechanism (traced 2026-09-19).** The Push review's branch field is not a placeholder
the suggestion merely decorates. `[p] Push` on screen 46's ready workspace row navigates to 46j and
issues `PREPARE_ACTION` with an empty `publication_branch`; `_prepare_registry_push` answers with
`command.publication_branch or workspace.suggested_branch`; and `_action_prepared` writes that
answer back into `state.publication_branch`, which is what the field draws, what the status names as
the target, and what `_request_action` refuses to push without. The suggestion therefore has exactly
one seam -- that fallback -- and the session's knowledge has to reach it on the command rather than
through `publication_branch`, because that field means *the maintainer chose this*, and a non-empty
one is refused when the checkout already stands on its own eligible branch.

The shape that follows:

- `domain/publication.py` gains `RegistryCommitOrigin` (`init-registry`, `rebuild-registry`,
  `promote`, `bulk-promote`), `PUBLICATION_BRANCH_NAMESPACE = "aart-cli"`,
  `DEFAULT_PUBLICATION_BRANCH = "aart-cli/registry-update"` and
  `suggested_publication_branch(origin, *, subject="") -> PublicationBranch`. It returns the default
  for no origin and for any subject that would not compose a usable Git branch name -- refused
  rather than encoded, the way `installation_tree` refuses a path component it cannot compose, since
  an encoded branch is a name nobody can read back to the run that produced it.
- `ConsumerUiState` carries `registry_commit_origin` and `registry_commit_subject`, set in
  `_action_recorded` from `event.action` -- which is the one thing that tells init from rebuild, and
  the reason this item needed the reducer at all. Both of its return paths have to set them: a
  promotion recorded on screen 45 takes the early `registry_commit_applied` branch.
- The promotion subject is the only part the reducer cannot derive, so `ConsumerUiEvent` carries it
  and `_execute_candidate_promotion` fills it from `pending.transaction.plan.versions` when there is
  exactly one, as `<artifact>-<version>`. Bulk promotion runs through the same executor and is told
  apart by `command.action`; it names itself and needs no subject.
- `ConsumerUiCommand` gains `suggested_branch`, set by `_request_action` on the navigation to 46j,
  and `_prepare_registry_push` reads `command.publication_branch or command.suggested_branch or
  workspace.suggested_branch`. `MaintainerRegistryWorkspaceView.suggested_branch` keeps the constant
  as the answer for a session that knows nothing, which is exactly what §169's "otherwise" names.

Tests were written first: the domain suggestion per origin and both fallbacks in
`tests/registry_publication_branch_test.py`, with a Hypothesis property that every suggestion is a
usable branch name under the product namespace whatever subject it is handed; and the session
carrying each producing action through to the prepare command in
`tests/registry_commit_manual_publication_test.py`, whose `_on` helper and recorded screen case
already build 46j. Targeted mutation: return the constant from `suggested_publication_branch` for a
known origin, and watch the per-origin assertions turn red and nothing else.

Implement Product Specification §169.1–3/5 and INV-244/247. Inventory all active producers and
consumers: executable/package/import names (`aart-cli`, `aart_cli`), manifest discovery and schema/
URI identifiers, CLI/help/JSON labels, filenames, managed markers, environment and CI/release
names, Registry templates, public docs, examples, scripts and tests. Historical evidence and
external harness filenames remain literal. Delete former aliases/readers directly; no migration
command, compatibility window, old-path probing or dual writes. Re-run step 16's executed
installation/README contract after changing its advertised commands.

Resolve one normalized absolute `AART_CLI_HOME`, defaulting to `<user-home>/.aart-cli`, for both
macOS and Linux. Put tool settings, canonical objects, snapshots/Candidates, receipts/activity/setup
metadata, cache, locks and temporary files under it. Establish adapter-owned path policy for
private installation trees under harness directories, qualified by Registry alias and artifact,
and distinct roots for different profiles/homes. Step 19 connects that policy to every lifecycle
writer. Preserve administrator-policy and secret-provider authority; an application-home override
cannot bypass machine policy. No ordinary artifact input values belong in the central home.

Acceptance: same relative layout on macOS/Linux; explicit override honored by CLI, TUI, headless
execution and reset/doctor paths; invalid/broad destructive roots refused; no fallback to former
paths/XDG roots; packaged `aart-cli --help`/`--version` work and old entry points are absent;
generated/public instructions use the same names; bounded cache cleanup leaves receipts/objects
intact. A reset must expose the effect of forgetting receipts without silently destroying harness
files or credentials. Unsupported harness destinations refuse before effects. Focused unit/property tests and packaging/docs/reset/CI checks appropriate to changed boundaries,
one recorded targeted semantic mutation for material behavior and scoped mutmut
hold these boundaries. No full `make quality` until task 21.

**Completed branch suggestion.** `RegistryCommitOrigin` records init, rebuild, single promotion or
bulk promotion in session state when the corresponding action succeeds. A single promotion also
carries `<artifact>-<version>` from the reviewed transaction. Opening Push passes the resulting
suggestion on `ConsumerUiCommand.suggested_branch`; an explicit edit remains distinct, and an
eligible current branch remains authoritative. A restarted session, an absent origin or an
unusable promotion subject falls back to `aart-cli/registry-update`. D-347 records why this state is
session context rather than inferred from commit text or persisted as another authority.

The branch policy has example and Hypothesis coverage, the reducer carries all four origins through
to Push, the adapter boundary proves the session suggestion wins over the restart fallback, and the
promotion executor is held to deriving the single-promotion subject from the transaction. The
targeted mutation returned the default for init and made the named per-origin test red, then was
restored. Scoped mutmut over `aart_cli/domain/publication.py` with
`tests/registry_publication_branch_test.py` killed all 135 mutants.

**Step 16 re-run and final evidence.** Both `make unit` (4596 tests, one skipped) and `make
integration` (402 tests) passed, so the renamed install lines and README contract were executed
again rather than assumed from the earlier rename segment. `make lint`, `make format-check`, `make
typecheck`, `make packaging-check`, `make docs-check` and `make secret-shape-check` passed. No new
noncritical finding was discovered, so `BACKLOG.md` needs no entry. No broad `make quality` ran,
under D-317/D-334.

### Step 19 — private installation trees, names, input entry and lifecycle (B-144/B-150, D-333/D-349)

Status: **in progress**, depends on 18a. Implement Product Specification §§38–39, 84–85, 96, 161.5–8 and
169 with INV-243/245/246/253. Stable owner fields are Registry alias, artifact kind/name, scope,
normalized concrete project/user target root and harness/profile; `input_id` is unique only inside
that owner. Version is excluded so compatible updates can retain that owner's inputs.

Expand selected targets before input composition. Give each installation its own harness-local
payload/runtime/launcher/configuration, registration fragment and central receipt. Wire identity
through placement, input collection, provider references, setup, Installed/Credentials views,
health and all lifecycle actions. Reject global InputId grouping and one-source-for-all-targets
projection. Never copy/prefill another target's values or offer shared/copy-answers controls.
Ordinary values remain in the installation tree, secrets in its provider; central metadata holds
paths/digests/references only. macOS Keychain derives distinct deterministic, collision-resistant
service/account pairs from complete keys with opaque roots. Provider items cannot serve two owners.

**Naming acceptance added 2026-09-19 (D-349, issues #26/#28); implementation pending.** Apply
§169.7 within this task, not a separate release task. Harness-visible names expose artifact,
Registry alias and scope, without version. Respect each adapter's actual naming grammar, discovery
depth and fixed filenames. For skills, use a valid spelling such as `github-company-project` in
both the installed directory and frontmatter; preserve canonical content and record the installed
projection for verify/repair. For MCPs namespace registration keys; the private runtime tree can
keep §169.3's structured layout. Other artifact kinds use supported keys/owned markers when their
filenames are fixed. Characterize installed OpenCode and Tabnine CLI capabilities, including user
skill discovery, before replacing existing adapter assumptions.

Keychain is part of this same acceptance: derive deterministic collision-resistant service/account
pairs from the complete owner plus input id, never only the readable harness name. Use readable
artifact/alias/scope/harness/profile/input labels with an opaque root discriminator; no version,
raw root paths or secret-derived material. Document the exact encoding as an implementation
decision. Preserve same-owner references on compatible update and isolate rotation/deletion.

Acceptance (red first):

- Install a skill from `company` in eligible OpenCode/Tabnine CLI project and user targets;
  prove actual discovery at the supported depth and matching directory/frontmatter names.
  Assert canonical bytes remain unchanged and verify/repair accepts the recorded projection.
  Exercise MCP registration keys and fixed-filename owned fragments for other artifact kinds.
- Show version in AART CLI/TUI and metadata, but not installed naming identity. A compatible
  version update preserves paths, registration names and that owner's credential references.
- Validate actual harness name grammars and length limits. Cover hyphenated artifact/alias join
  collisions, oversized names and unmanaged entries; fail before filesystem/settings/provider
  mutation without silent truncation, overwrite or encounter-order renaming.
- With one artifact/input, vary Registry alias, project/user scope, concrete root and harness/
  profile independently: Keychain service/account pairs remain distinct; a second input id is
  distinct too. Independently entered equal values do not merge items. Labels reveal no raw roots
  or secret material, and retries derive the same address for the same owner/input. Rotation or
  deletion of one item leaves the others untouched; force an address collision and assert refusal
  before a provider write. Use equivalent ownership cases for other supported providers.
- One MCP into Tabnine/project and Claude/user produces two private trees, two registrations and
  two independently actionable Installed rows with exact roots, versions and health.
- One MCP with two config variables and one secret on four eligible harnesses collects eight
  ordinary fields and four secure entries, then writes four config files, four runtimes, four
  receipts and four provider items. Four eligible test profiles may exercise the universal rule;
  this criterion does not require adding support for a new external harness. Exercise CLI/TUI
  application paths; equal manually entered
  values still produce independent ownership. No copy/share control or global prefill exists.
- Headless input bindings are target-qualified; omitting one fails for that target without a
  prompt, fallback or cross-owner reuse. Reject explicit attempts to bind the same provider item
  to two owners. Secret values never appear in plans/receipts/logs/files.
- Same remote artifact in two project roots and user scope, equal packages from two Registry
  aliases, and separate profiles/homes remain independent. Duplicate selection of one exact owner
  may coalesce while preserving Collection reasons; distinct targets never coalesce.
- Install byte-identical `mcp/github@1.5.0` from remote alias `company` and local alias
  `company-local` into the same harness/scope. Assert two paths under
  `<harness-root>/aart-cli/mcp/company/github/` and
  `<harness-root>/aart-cli/mcp/company-local/github/`, distinct registration keys and launchers,
  receipts, provider items and Installed rows. Repeat across Claude/user and Tabnine/project for
  four independent installations. Step 19 tests the identity/placement contract; step 20 repeats
  it through real local and remote acquisition adapters. Canonical package deduplication must not
  collapse installations or permit alias/path traversal.
- Multiple owners writing the same harness settings file preserve each other's fragments, even
  from separate application homes. Complete identity does not permit uncoordinated file overwrite.
- Reopen, update, configure, rotate, repair and uninstall one owner leave every other owner's
  files, config, credential and receipt untouched. Compatible update/repair retains inputs only
  for that owner. Retained credentials never become a pool for new installations.
- Canonical object availability alone creates no Installed row. Verification failure and partial
  effects produce honest recorded health. Launch succeeds without the installer or central object
  store; cache pruning never deletes private runtime state.

**Done so far — who an installation is, and where its credential therefore lives.**
`domain/installation_owner.py` holds the complete owner: Registry alias, artifact kind and name,
scope, the normalized concrete root, and the harness with its profile. `installation_owner()` drops
the version there rather than at each call site, so no caller can decide to keep it and turn every
compatible update into a fresh installation with nothing entered.

`credential_address()` composes
`aart-cli.<harness>.<profile|->.<scope>.<alias>.<kind>.<name>.<16 hex of sha256(root)>` with the
declared input as the account (D-352). Every label is held to the canonical slug, the separator is
one no slug can contain, the profile keeps a slot even when the harness has none so the components
cannot shift, the root is hashed because a project directory is frequently a client's name, and an
address over 255 characters is refused rather than shortened -- truncation being exactly how two
owners quietly become one item.

What this replaces is still live and is the reason it was written first: `io/consumer_actions.py`
addresses a Keychain item as `aart.<12 hex of the user home>` with the input id, which is one item
for every harness, scope and Registry alias on the machine. That call site cannot adopt the new
address yet, because `application/installation_inputs.py` still composes one field per `InputId`
across artifacts -- "one semantic form field and every artifact whose launch contract depends on
it", with an explicit duplicate check -- which is the global grouping this step rejects and the
reason the acceptance asks for eight ordinary fields and four secure entries from one artifact on
four harnesses. Splitting that composition per owner is the next commit, and it is what removes
`domain.installation_owner` from `DELIBERATE_NON_RUNTIME_MODULES`, where it is recorded with that
dated reason.

Evidence: two targeted semantic mutations, each red then restored -- dropping the profile's empty
slot (1 red, the test that names it) and making the root discriminator a constant (2 red, the
per-field separation subtest for `root` and the property). Scoped
`make mutants ONLY=aart_cli/domain/installation_owner.py` killed 44 of 62; of the eighteen
survivors, one was a real hole and is now held (a non-string root reached `posixpath` and came back
as `TypeError`, which is not a refusal), and the rest are message arguments, an encoding spelled
`UTF-8`, mutmut's own `X` padding inside the newline set, and the `>`/`>=` boundary of the length
refusal, which no test pins deliberately.

**Done so far — every target collects its own answers.**
The unit of collection is now `InstallationOwner` rather than `InputId` (D-353).
`application/installation_inputs.py` composes one field per `(owner, declared input)`, each owner
binds its own `BoundInputs`, and answers arrive as `OwnedInputSource` so an answer belongs to the
installation that gave it. `io/configured_installation.placement_owners` is what names those
installations: a placement reaches a harness either through a registration target or through a
delivery, merge or settings entry, and that harness with this scope and this root is the owner.

Two things were deleted rather than configured. `INPUT_DECLARATION_CONFLICT` is gone: two artifacts
declaring one id differently were a conflict only because the id was the key, and they are now two
fields each keeping its own declaration and its own guidance. `InstallationInputField.dependants`
is gone: a field has exactly one owner, so the list of dependants was the thing that made four
installations share one value. §165.19's "a contract change must not touch credentials owned by any
other installation" is now held by separation instead of by refusing the pair.

Planning is not per installation yet, and the gap is named rather than papered over (D-354).
`generate_launcher` renders the credential reference into the launcher text, so one launcher carries
one address, and `PlannedInstallation` requires every harness's configuration file to hold the one
reviewed set. Where one placement's owners answered differently, `prepared_placements()` refuses by
name (`configured-installation-per-target-values-differ`). Screen 07 now shows and collects one row
per installation as recorded below. `credential_address` is wired at `io/consumer_actions.py`, and
the launcher composes the harness-specific service at startup. The remaining refusal concerns
different ordinary values reaching the still-shared runtime projection; it does not merge answers.

Evidence: `make unit` green (4628 tests). Five targeted semantic mutations, each red then restored
-- the field key dropping the owner, one owner's answers handed to every owner, an answer accepted
for an installation that never declared it, diverging targets installed with whichever came first,
and a placement claiming every owner rather than its own artifact's. The last of those survived at
first and was a real hole: with a multi-artifact Selection a placement would have been prepared
against answers nobody gave it, and no test used two artifacts. It is now held. Scoped
`make mutants` over `application/installation_inputs.py` killed 73 of 94; of the fourteen survivors
one was real -- the argument guard could be weakened so a bad `uses` or `sources` passed unrefused
-- and is now held, one is a redundant sort (`BoundInputs` orders its own inputs, so the explicit
key changes nothing observable), and the rest are message arguments.

`domain/installation_owner.py` is reachable from the runtime and no longer carries a
`DELIBERATE_NON_RUNTIME_MODULES` exception.

**Done so far — every installation reaches its own Keychain item.**
`io/consumer_actions.py` addresses a secret with `credential_address(field.owner, field.input.id)`.
The per-machine `aart.<sha256(home)[:12]>` service is gone: one item per machine and declared input
was the address §169.4-6 replaces, and it is deleted rather than kept beside the new one (D-334).

Three things had to move with it, in one slice, because any of them alone leaves the product broken.

The *launcher* is one file registered with every harness, so `plan_artifact_installation` carries
`credential_service_template` to `generate_launcher` (D-355) and the launcher composes its address
from the harness it is started with. `_with_service_variable` substitutes inside an argv word
rather than over the list, because a provider may name the service as its own argument (`-s
<service>`) or fold it into one reference string, and both are one word once quoted. The sentence
the launcher prints when it cannot read the item passes the composed address as a `printf`
argument rather than substituting into prose -- searching a sentence for something that looks like
an address is how `aart: could not read` became `"$AART_CLI_SERVICE": could not read`.

The *placement* now carries both: `credential_service_template` is launcher text and names nothing
anyone holds, so `credential_addresses` carries every installation's concrete item beside it, and
that is what a provider is inspected for and what the receipt records
(`PlannedInstallation.credentials`). `prepared_placements()` folds each owner's own address back to
the template it composes from and compares what remains, so separate items stop reading as a
disagreement; a reference pointing anywhere else is left alone and still refuses (D-354, narrowed).

The *reconciliation vocabulary* had to stop naming a credential component by its declared input
alone (D-356), because four installations of one artifact then name one component four times, which
`DesiredState` refuses. `credential_component_names` names a whole set: an input that still names
one item keeps exactly the name it had, and one that does not is suffixed with a short digest of
its address. Both the desired state and the observation take names from that one function.

The characterization that changed is the one that said it: two artifacts declaring one input were
asked for once with both owners in a single briefing. They are now asked for separately, each in
front of its own author's guidance, which is what §169.4-6 means by a value never being quietly the
value for something else. The recording provider in `tests/credential_action_rows_test.py` held one
`present` flag for every address; storing one installation's item made every other look ready, and
the second of two artifacts then failed its pre-execution check with "installed state changed after
Review". A provider holds state per item, and the double now does too.

Evidence: focused suites green -- `tests/runtime_projection_test.py` (32), the configured-draft,
planning, proposal, reconciliation, credential-guidance and credential-action-row suites. `lint`,
`format-check`, `typecheck` green. The later Screen 07 segment reran `make unit`: 4654 tests pass
with one skipped. Both owed targeted mutations were red and restored. Scoped mutmut over
`domain/credentials.py` killed the owner-collapsing change; its twelve survivors are
message/encoding/name-width details outside the claim. The configured-installation run killed 212
of 276 after the test was strengthened to retain a non-default provider; its 64 survivors are in
older snapshot/materialization/draft branches and are findings rather than this claim.

**Done so far — Screen 07 asks every installation separately (D-357).**
`InstallationConfigField`, `ConfigInputView` and `CredentialInputView` expose the same
owner-qualified row key. The form uses that key for navigation, editing, acceptance and submitted
answers; it draws the owner beside both the ordinary field and the provider-backed credential
status. Existing ownerless unit fixtures retain the plain input-id key, while live installation
composition always supplies an owner.

The two temporary sharing helpers are deleted. `_one_row_per_input` no longer hides all but the
first installation, and `_addressed_to_owners` no longer broadcasts one answer. The action handler
recomposes the authoritative draft, maps each submitted row to exactly one field, and creates one
`OwnedInputSource`. A stale row matches nothing and is dropped rather than rebound to a different
installation. One accepted row leaves every other owner unanswered. A whole TUI walk enters the
ordinary value independently for three targets, narrows to two harnesses and proves only those two
configuration files are written; a rendering test proves both owners remain visible.

Red-first evidence: the E2E assertion for multiple distinct owner rows failed against the collapsed
screen. The targeted mutation replaced the owner-qualified action key with `input_id`; exactly
`test_answer_reissues_the_real_preparation_as_a_prompted_source` went red and was restored. The
focused Screen 07/configured-draft/reconciliation set passes 61 tests. A file-scoped mutmut attempt
on `application/consumer_ui.py` generated 2502 mutants for unrelated screens because the runner can
scope only by file; it was stopped after 253 as disproportionate and recorded as B-158. Full
`make unit` passes 4654 tests with one skip.

**Done so far — one launcher, four addresses (D-355).**
The launcher already receives the harness that started it, because D-264 is why it can find its own
configuration file. `generate_launcher` now accepts `credential_service_template`: the
installation's credential service with its harness left open as `HARNESS_PLACEHOLDER`, produced by
`credential_service_template()` from the same `_service_labels` join `credential_address` uses, so
the address the launcher composes and the address anything else derives cannot drift apart. The
launcher emits its harness preamble, composes `AART_CLI_SERVICE` from the template around
`"$AART_CLI_HARNESS"`, and substitutes that variable for the service element of the provider's
resolution argv. That is what turns one generated file into four Keychain items.

Nothing composed is evaluated. The preamble holds `$1` to a canonical slug before anything is built
from it; each side of the template is single-quoted, so no part of an address is read by the shell;
and the placeholder itself must be letters, digits, underscore or hyphen, so `$(id)` cannot be one.
A template must leave exactly one slot open -- none has no harness and two have no single one --
which is also what makes the partition unambiguous. A provider whose argv does not name the service
is refused (`launcher-provider-unparameterised`) instead of quietly given one address for every
harness, because that silence is the defect, not a fallback.

The evidence is executed rather than inspected: the test writes the generated launcher to disk with
a stub provider that reports the `-s` service it was asked for, runs it once as `claude` and once as
`opencode`, and asserts the two differ and each equals `credential_address` for that harness.
Without a template the launcher is byte-for-byte what it was, which is what lets this land before
the call sites move.

Evidence: 31 tests in `tests/runtime_projection_test.py`; `lint`, `format-check`, `typecheck` green;
the dependent projection/proposal/verification/planning suites green. One targeted semantic mutation
-- the composed address naming one fixed harness instead of the starting one -- turned exactly the
test that names it red, then restored. Scoped `make mutants` over
`application/runtime_projection.py` killed 286 of 316 with 28 unreached (`configuration_projection`,
which this file does not exercise) and two survivors, both real and both now held: `_error` could
drop its message with no test noticing, and `partition` could become `rpartition`, which the
exactly-one-slot guard now makes equivalent by construction.

Still open, and deliberately one slice: threading the template through
`plan_artifact_installation` to `io/consumer_actions.py` belongs with writing the secret at
`credential_address` and deleting the D-354 divergence refusal. A launcher reading the new address
before the secret is written there would find nothing at it.

**Done so far — the name the harness shows, and the collision it must not resolve by itself.**
`installed_name()` projects the same owner to §169.7's harness-visible spelling: artifact name,
Registry alias and scope joined once, `github-company-project` and `github-company-user`. The
version is absent deliberately -- a name that moved with every update would rename a directory the
harness had already discovered -- and so are the harness and the root, because the name lives inside
that harness's own root and a readable name is not an identity. `credential_address` remains the
thing that carries the complete owner. The composed name is held to the published skill contract
(lowercase alphanumeric, single hyphens, 1-64 characters), which OpenCode, Agent Skills and Tabnine
CLI all discover, so one bound holds for every adapter instead of each carrying its own.

`installed_names()` names a whole operation at once because the join is ambiguous by construction:
the separator between labels is also legal inside them, so the split can move. `github` from
`company-user` and `github-company` from `user` both spell `github-company-user-project`. Neither
name is wrong and neither can be disambiguated silently -- a counter would depend on encounter order
and truncation is worse -- so the set is refused by name before any directory exists to overwrite.
An owner listed twice is not a collision with itself.

Evidence: four targeted semantic mutations, each red then restored -- dropping the scope from the
join, removing the length bound so an 81-character name is accepted, accepting a collision so the
last owner wins, and counting a repeated owner twice. Each turned red on the test that names it.
Scoped `make mutants` over the module surfaced two survivors inside these claims that were real and
are now held: the `>`/`>=` boundary of the name length, where §169.7 makes exactly 64 legal, and a
refusal losing its remediation without any test noticing. The remaining survivors are message prose
and the credential service's own length boundary, which no test pins deliberately.

**Done so far — the name reaches the harness, and only the copy it reads (D-358).**
`installed_name_for(coordinate, scope)` is the same join asked for before an owner exists, which is
what placement has: `io/artifact_placement._deliveries` composes the name there and uses it for the
destination, so a Skill is delivered to `.claude/skills/code-review-company-project` and the same
artifact at user scope is a second directory rather than a competitor for the first.
`installed_name(owner)` delegates to it, so a directory cannot be delivered under one spelling and
recorded under another.

A Skill also names itself. `application/skill_projection.project_skill_document` rewrites the
`name:` of the installed `SKILL.md` and supplies a `description:` from the manifest summary when the
author wrote none, keeping whatever else the frontmatter says and refusing -- rather than guessing
at -- an unterminated header, a repeated field or bytes that are not UTF-8. `ArtifactDelivery`
records `projected_name`, `projected_description` and `projected_document`, the payload-relative
path whose text carries the name; only a Skill has one, because a hook's script and a guideline's
document name nothing.

Three things had to agree and none follows from the others: the path, the bytes at it, and the
digest a receipt records. `package_delivery` takes a `projection` applied by payload-relative path
*before* the tree digest, so the digest is of what will be on disk; `DeliveryEffectInterpreter`
applies the same function to the same path after copying, borrowing owner write access and giving it
straight back so a read-only payload stays read-only. Without the first half, every clean install
reads as drift on its first reconciliation. The payload this installation owns is never rewritten,
and the test that proves the delivery is a copy asserts the two now differ.

`io/consumer_machine._targets_scope_and_profile` rebuilt the expected destination from the authored
name to decide which installations a status view holds. After the rename it matched nothing, so
`marketplace status` listed nothing at all -- green in every delivery test and visible only end to
end. It asks the delivery for the name it was delivered under.

Evidence: `make unit` 4728 green with one skip; lint, format-check and typecheck pass. Four targeted
semantic mutations, each red on its named test and restored -- the destination taking the authored
name, the executor skipping the projection, the digest taken before the projection, and the status
view looking for the authored name. Scoped `make mutants` over `skill_projection.py` left 32
survivors; two were real and are now held, and one of them was a defect rather than a test gap: rows
were written with `\n` into documents whose own rows end `\r\n`, so the installed frontmatter was
spelled two ways. The rest are message prose (D-134). Hypothesis holds the two universal claims --
the authored body survives whatever was written, and projecting twice says what projecting once
says, because a second install re-delivers from the same payload.

Forty-five tests spelled the authored name and were corrected;
`tests/placed_installation_e2e_test.as_delivered` is now the one place that spells what a delivered
Skill looks like.

Property-test complete owner keys, composed-name validation and provider-address stability and
separation across generated owners/input ids. Use existing focused tests where
possible; record targeted semantic mutation evidence for the material isolation claims and scoped
mutmut over their changed modules. Do not build a broad compatibility or cross-product matrix. B-144 and B-150 close only after this
acceptance, before step 20 consumes the model. No sharing feature is part of this task.

### Step 20 — local Git checkout as a configured canonical Registry (B-143)

Add `registry-local` beside `registry-git`, with a Remote Git / Local checkout choice in Add
Registry and the same capability in the deterministic CLI. Collect alias, normalized local repo
path and selected local branch. Persist the branch and resolve it to an exact commit on Add/Sync;
read its committed canonical Registry content independently of the checked-out branch. Record
commit and content digest before saving configuration. Never switch branches, include uncommitted
worktree edits, fetch, or fall back to `HEAD`/the default branch. Sync atomically advances only
after the same validation used for remote Git. Missing branches and invalid successors preserve
the last known valid snapshot.

**Owner clarification, D-350:** commit the candidate's canonical artifact to a local Registry
branch → add that repo/branch as a normal Registry → install from its alias → run step 20a's
smoke command on the installed MCP. This task introduces no separate candidate installation
process and has no dependency on implementing Candidate Test Install.

Both transports feed one Registry admission service, source-store snapshot representation,
Marketplace projection, resolver, policy evaluator and installation path. Local transport neither
changes trust nor turns `Promoted locally` into published; it makes the canonical version selectable
under its configured alias. A local and remote connection to the same Registry may coexist only
under distinct aliases. Qualified coordinates remain distinct, and an equal unqualified match is
explicitly ambiguous.

Acceptance covers coexistence, alias-qualified selection, unqualified ambiguity, dependency and
Collection closure, install/update/status, receipts containing alias/branch/snapshot/commit/origin, and an
invalid local successor retaining last-known-good state. Reuse step 19's independent project/user/
harness configuration and credential cases through the local and remote aliases, including
refusal of cross-installation provider-item binding and separate target-qualified input entry. Local Sync is read-only with respect to the checkout and proves
it performs no network operation. Exercise a selected test branch while another branch is checked
out and the worktree has edits; only the selected branch's committed content is installed and the
worktree stays unchanged. Advance that branch and prove explicit Sync/update adopts its successor;
delete it or commit an invalid Registry and prove last-known-good preservation without fallback.
Step 20a then proves the normal installed MCP can be smoke-tested. This closes B-143.

### Step 20a — local CLI smoke verification of installed MCPs (D-348/D-350/D-351, issue #27)

Status: **in flight**, after 19 and 20, before final gate 21. Implement Product Specification §170
and INV-248–252 as revised by D-365. The implementation checkpoint and current owner revision below
identify existing code and outstanding work.

**Selection and ownership.** One CLI command tests all or selected already installed MCPs in an
explicit local target scope. Include ordinary installs from a configured local Registry repo/branch
and remote Registries. Already supported installation origins remain eligible, but implementing a
separate Candidate Test Install flow is not part of this task (D-350). Uninstalled Source/Candidate/Registry content is not a test
target. Optional provenance filters do not bypass installation requirements. Resolve exact owner,
content and harness/profile; ambiguous or empty selections are non-success. Do not install,
update, configure, repair, sync or publish as a side effect of testing. Existing configuration and
secrets remain installation-owned; selecting several MCPs or harnesses does not join their inputs.

**Implement in bounded parts, retaining the full hierarchy:**

1. Define the parser-owned optional top-level `smoke_test` block. Only `tool` and
   `read_only: true` are required; omitted arguments are an empty object, the default tool-call
   timeout is 15 seconds, and `expect` is optional. Optional arguments are fixed values or explicit
   installation-local non-secret references. Carry this through canonical compilation/validation
   and generated author guidance; do not create a second schema authority or embed secret values.
   Implement §170.3's generic protocol evaluator and a small deterministic optional expectation
   vocabulary; document its exact syntax/defaults as an implementation decision. Existing tools
   and their existing content formats work without a dedicated health tool or `{"ok": true}`.
2. Add pure selection, verification planning and stage-result evaluation. Configuration,
   startup/protocol, MCP/service, harness/model-provider and harness/MCP/service claims remain
   distinct. Failed prerequisites suppress only dependent stages. Empty, unconfigured, blocked,
   unverified or unsupported runs never return an aggregate pass. Report protocol-level invocation,
   optional result expectations and service evidence separately. A normal response containing an
   application error or cached data must not by itself yield an external-service PASS.
3. Execute the installed launch/transport contract directly with explicit effects. Call only the
   declared operation; validate completion, MCP/JSON-RPC errors, `isError`, declared output schema
   and optional `expect`. Do not infer business success from arbitrary content. Preserve successful
   call evidence while reporting service access as NOT VERIFIED when it lacks adequate evidence.
   Missing declarations leave independent checks available and operation stages not configured.
4. Add version-aware OpenCode CLI and Tabnine CLI adapters and an additional Claude Code adapter.
   Headless tests use the real selected installation's discovery path. Verify current-session
   call identity, arguments and completed result. Enforce allowed operations before invocation;
   deny shell/direct-HTTP/other-tool substitutes and unbounded or unrelated background work.
   A fixture config is adapter evidence, not evidence that the user's installation was discovered.
5. Present one human/JSON result model with safe owner/content/version/time metadata and bounded
   diagnostics. Never persist config values, secrets, raw service payloads or harness transcripts.
   Preserve zero installed runtime dependencies and existing enterprise network/provider policy.
6. Document the preferred author flow: commit canonical artifact to local Registry branch → add
   that repo/branch under an alias → install normally → run
   smoke checks on the intended harnesses → fix/retest → publish the tested content to the public
   remote Registry. Also document a consumer checking a batch of existing installed MCPs. Do not
   turn this recommendation into a new implicit publication gate.

**Evidence required before completion.** Characterize both CLI implementations/versions. A local
controlled MCP plus protected fixture service first proves genuine execution and negative cases;
then run a declared read against a configured real service through eligible full-route adapters.
For Tabnine without the required allowed-tools boundary, prove direct MCP/credential coverage and
that no harness prompt runs (D-365). If an enterprise executable, account or endpoint is absent,
record that pending live obligation; do not count a skipped case as final acceptance. No new
scheduled workflow or broad hosted compatibility matrix is required.

Negative coverage includes uninstalled/ambiguous/stale targets, cross-owner credentials, missing
or unsafe declarations, undeclared calls/changed arguments blocked before execution, missing
credentials, explicit authentication/authorization failure, timeout/tool errors, unavailable
model provider, an answer without a tool call, old-session evidence and a substitute MCP config.
Dependency tests prove direct service checks still run when model login fails. Property tests hold
selection boundaries, owner isolation, allowlist narrowing and result aggregation where universal.
Targeted semantic mutations must make the relevant assertions red; run scoped mutmut for changed
modules. Focused checks belong here; the full repository gates stay in 21.

**D-351 minimal-manifest acceptance.** A two-field smoke block survives parsing, compilation,
packaging and installation unchanged in meaning; no additional expectation or custom response is
required. Prove valid text, structured, image and empty results are accepted at protocol level,
including omitted `isError`. Reject malformed results, `isError: true`, transport/JSON-RPC errors,
timeouts, missing required arguments and output-schema violations. Unsupported schema validation
is explicit. Optional expectations can fail an otherwise successful call and are evaluated equally
through direct MCP and harness routes. Missing expectations do not enable keyword/LLM heuristics.
Fixtures with a disguised textual error or cached response prove that successful invocation alone
cannot make the service stage green. Preserve the full hierarchy and current-session harness
evidence; a harness's final prose never supplies the tool result. Exercise bounded/malformed
expectations and prove neither scripts nor resource-link fetches are executed by the evaluator.

Read-only is a reviewed server/tool contract, not a promise that arbitrary startup/tool code is
incapable of mutation. Do not silently swap credentials to strengthen that claim. This distinction
and the declaration-required behavior must be visible in operator documentation.

**2026-09-19 planning record.** Added 20a without renumbering or changing existing statuses:
23 tasks, 19 done, 19 next. Canonical §170, INV-248–252, D-348, execution/NEXT/status records and
author guidance carry the same installed-only/full-hierarchy scope. GitHub issue #27 is covered
by this implementation task but remains open; B-073's scheduled live CI scope remains separate.
Documentation/plan checks are recorded in MIGRATION_STATUS; no runtime test/mutation claim is made.

## Settled authoring boundary for this slice

CP-26 does not support authoring directly inside a Registry. Author manifests and payloads live in
a Source checkout; `scan` and `promote` compile them into the canonical Registry representation.
Supporting Registry-origin authoring would require a future explicit Product Specification change
and a new provenance origin kind. It is not an alternate implementation of any CP-26 task.

### Planning segment — installation layout and input isolation (2026-09-19)

The owner accepted Product Specification §169 and D-332–D-334, including alias-qualified paths,
breaking changes throughout CP-26 and proportionate implementation checks. CP-26.18a adds the namespace/home
work; CP-26.19 now includes private harness runtime placement, one receipt per target and mandatory
separate inputs. The plan has 22 tasks with existing ids/statuses retained; 13 are complete and 14
is next at this recording. Shared-credential allowances in the specification and future acceptance
criteria were removed; previous decision records carry explicit supersession notices. B-150 is
promoted into mandatory step-19 acceptance, with B-144, and remains unimplemented.

This segment changes specification/planning only. No runtime, live files, Keychain items or step
completion statuses are changed. Verification: `handoff-plan validate` and a plan comparison pass (22 tasks, 13 done; existing
statuses unchanged, 18a before 19, 21 last); `make docs-check` passes. `git diff --check` and a
consistency review of sharing allowances complete the documentation-only checks.
Targeted semantic mutation/mutmut evidence belongs to implementation tasks 18a/19; no executable
behavior is claimed here. No broad quality gate is run (D-317).

### Consistency audit — execution and invariant evidence (2026-09-19)

D-335 and `../CONTRACT_ALIGNMENT.md` record the pre-implementation review. The Product Specification
now uses the complete installation owner consistently in runtime isolation, Collection reasons,
input aggregation, active-version constraints and registration examples. Bulk receipts link
per-owner records; shared harness-file mutations preserve independent fragments. Four eligible test
profiles can prove separate input collection without adding an external harness adapter.

Root instructions, CODEX_GOAL, slice index and local handoff now identify the current work and
D-317/D-334's focused checks. The invariant matrix adds 243–247 and reclassifies affected historical
proof instead of treating old passing tests as new acceptance. Earlier decisions/slices are marked
historical. B-121 is absorbed by 19 and B-076 is guidance-only; B-151 remains open despite the public
protocol warning banners. No implementation backlog item or task is closed. The plan remains
13/22 done, 14 next, with 18a → 19 → 20 before final gate 21.

Verification is limited to docs/plan/traceability consistency; no runtime behavior changed.
Results: `make docs-check` passed; the existing `tests.traceability_matrix_test` passed all five
tests with the application-first import; `handoff-plan validate` passed (27 epics, 160 units,
151 done repository-wide). A direct catalog/plan check confirmed all 247 unique invariant rows,
CP-26's 13/22 done, unchanged existing statuses, 14 next, 18a before 19 and 21 last.
`git diff --check` passed. No semantic mutation is claimed for this documentation-only segment and
full `make quality` is not run. The local `.claude/HANDOFF.md` is refreshed but ignored by Git;
tracked NEXT/status/slice/alignment records contain the same resumption information.

### Step 15 — the detail moves off the page, into documents the index already reaches (2026-09-19)

Six hundred and thirty-nine lines left the README and none of them were rewritten. `## Install and
quick start` through `## Releasing` are now eight documents, each linked from the index that step 14
built, and the page is the four sections §1.6 asks for: the route, the orientation, the index and
the licence. 783 lines became 152.

| what moved | where it lives now |
|---|---|
| Install and quick start, with all three subsections | `docs/install/installing-aart-v1.md` |
| Consumer lifecycle, MCP setup and credentials, reading/checking/undoing a setup | `docs/using/consumer-lifecycle-v1.md` |
| Writing an artifact | `docs/authoring/authoring-an-artifact-v1.md` |
| Maintaining a registry | `docs/registry/maintaining-a-registry-v1.md` |
| Running inside a company | `docs/ci/running-inside-a-company-v1.md` |
| Canonical package, Interface, Verification | `docs/development/packaging-and-interface-v1.md` |
| Development dependencies and the ten gates | `docs/development/quality-gates-v1.md` |
| Releasing | `docs/release/releasing-v1.md` |

**Moved, not discarded, is a claim somebody has to hold.** The three tests that read sections which
moved now read the documents those sections landed in, by path: `InstallDocumentTest`,
`QualityGateDocumentTest`, `ReleaseDocumentTest` and `RegistryDocumentTest` replace
`ReadmeAdoptionTest`. A section dropped rather than relocated fails there by name, which is the
difference between a move and a deletion that nothing measures. The claims themselves are unchanged
-- same grid, same Enterprise narrowing, same gate table read off `build_gates`, same release
description with the retired half still refused.

**The command surface widened rather than narrowed** (D-338). Most shipped commands now appear one
link away, so `DocumentedCommandSurfaceTest` reads the README *and the documents it links*, taking
the set from the page's own links rather than from a list in the test. Narrowing to what is left on
the page would have reported the move as missing documentation; widening to all of `docs/` would
let a file no route reaches count as documentation, which is what D-336 refuses.

**A gate that would have been wrong at the new depth** (D-339). `../../releases` reaches the
repository root from the README and reaches `blob/branch/` from a document two directories down.
`docs_check` held the root-level form in a literal allowlist, so the move would have turned the
correct link into a DOC002 and let the incorrect one pass. The allowed forms are now computed from
the file's depth, red test first: from `docs/install/`, four steps up is accepted and both three and
five are refused.

**Relocated links, checked rather than assumed.** Fourteen link targets travelled. Every
`docs/...` became `../...`, `release-please-config.json` became `../../release-please-config.json`,
the same-directory link in the company document dropped its detour, and the quick start's anchor
into a section that no longer exists became a link to the install document -- the one wording change
in the step, held by its own test.

**Targeted semantic mutations (seven).** Flipping the Enterprise answer, deleting a gate row,
drifting a release command, renaming `revendor`, breaking the quick start's install link, growing a
fifth section back onto the README, and deleting the install document outright each failed the tests
that name those claims -- the fifth failed two and the seventh three, which is correct: a missing
document breaks every claim that reads it. All restored green.

**One citation repaired.** `INVARIANT_TRACEABILITY.md` cited INV-101's evidence as
`ReadmeAdoptionTest::test_the_release_section_...`; the class is now `ReleaseDocumentTest`. The
traceability gate caught it, which is the gate doing its job.

**Not in this step.** Step 16 executes the install lines and gates the structure; CP-26.18a renames
the advertised commands and reruns 16 afterwards. Neither is pulled forward.

**Evidence.** 31 tests in `adoption_first_contact_test`, `RepositoryRelativeLinkTest` red then green,
`make unit` (4534 tests), `make typecheck`, `make docs-check`, Ruff check and format. No broad
`make quality` ran, under D-317.

### Step 16 — the install lines are run, not read (2026-09-19)

`run_install_routes` in `scripts/distribution_smoke.py` builds this checkout's wheel, puts it where
an authenticated download would have left it, and runs the lines the install document publishes.
Five of the nine fenced blocks execute -- three clipboard routes through `uv`, `pipx` and
`python -m pip`, and two from a file on disk -- plus the `gh release download` line added in this
step. Each installs and then answers `aart-cli --version` with the version that was built. Four are
declined with a recorded reason: two name a `<repository>` that only a real remote has, one is the
consumer example, one is the generator whose output belongs to a release body rather than to a
reader's shell.

**Read from the document, not transcribed.** The commands come out of the fenced blocks with
`X.Y.Z` substituted, and go to a shell as written -- `$(pbpaste)` included, because the substitution
is part of the line. Anything the classifier does not recognise is `unclassified` and fails, so a
line added to the page has to be declared runnable or unrunnable by whoever adds it.

**The stand-ins are strict on purpose** (D-340). `gh` parses its arguments the way
`gh release download` does and refuses anything else; a stub that accepted everything would prove
its own tolerance and nothing about the page. What it cannot prove is that a remote answers, which
is why the URL row stays declined.

**A gate that does not damage the machine it runs on.** `UV_TOOL_DIR`, `PIPX_HOME` and their bin
directories are redirected into the workspace. Without that, the gate would reinstall the
developer's own `aart` from a throwaway wheel every time it ran.

**No eleventh quality gate.** The `integration` gate discovers `*e2e_test.py`, so
`tests/install_routes_e2e_test.py` rides it and `unit` without a new gate, a new row in the gate
table, or a heading that says eleven. The structural half -- section order, bounded explanation,
link reachability, licence last -- is loaded into the same test, so the integration gate does not
prove the lines work on a page whose shape it never checked.

**Targeted semantic mutations (four).** A pip flag that does not exist, a `gh` flag the real `gh`
would reject, an unclassifiable line added to the page, and a wheel name drifted from what the build
produces each failed the gate. The first two failed by the line refusing to run, which is the point;
the last two by the classification claim, which is the same defect seen one step earlier.

**Not in this step.** Step 17 removes `M1F1` as a generated or operational default and must rerun
this gate if it changes README content or an install line.

**Evidence.** 3 tests in `install_routes_e2e_test` (five executed routes plus the download),
`make integration`, `make unit`, `make typecheck`, `make docs-check`, Ruff check and format. No
broad `make quality` ran, under D-317.

### Step 17 — no maintainer identity as a default (2026-09-19)

Four consumer-facing surfaces carried `M1F1`. None of them does now, and the decision each one
needed is D-341.

**The generated workflow.** `TOOL_URL` was `vars.AART_TOOL_URL || format(..., vars.AART_REPOSITORY
|| 'M1F1/aart-cli')`. It is now empty when neither variable is set, and the Git arm -- the only arm
that carried a shipped default -- stops and lists the four variables instead of cloning a
repository nobody chose. The test runs the emitted shell with everything empty and requires exit 1
and those names, because a refusal that exists as text and not as an exit code is a refusal nobody
has seen happen.

**The generated Registry README** loses its link to the maintainer's repository and its
`AART_REPOSITORY` default row, and says plainly that setting none of the four stops the first run.
**The registry-init remediation** in `curation/runtime.py` names the variables rather than the
repository it used to say would be cloned. **The Enterprise rollout guide** -- a public setup
example -- says `<aart-upstream>` where it printed a clone URL, and its two tables agree with the
workflow again.

**The release checklist.** `approved_registry_origin()` fell back to the maintainer's registry, so
a fork's release reconciled against somebody else's. Unset is now no registry, the diagnostic says
`(none configured)`, and `release_test` sets `REFERENCE_REGISTRY_URL` in `setUp` -- which is what a
real release run does. Its fixture origin was the maintainer's registry *and* the script's default,
so those tests had been passing by agreeing with a constant; the fixture is now neutral.

**What stays, because it is a fact rather than a default.** `pyproject.toml`'s project URLs named
the predecessor repository and are corrected to this one. The Product Specification's target
repository, the CHANGELOG's release links and these refactor records are records of what happened.
D-309 draws that line and this step enforces it.

**Evidence.** 6 tests in `maintainer_default_test` (red before each change), `make unit`,
`make typecheck`, `make docs-check`, Ruff check and format. No broad `make quality` ran, under
D-317.

**Step 16's gate was rerun** as the slice requires: `make unit` includes it and passed. Nothing in
this step changed README content or an install line.

### Step 18 — Registry Maintainer owns Push and explains readiness (2026-09-19, partial)

**Status: in progress.** The shared contract, the readiness computation, the screen and the branch
targeting are in. The acceptance list below is not yet fully covered; what is missing is named at
the end of this record rather than implied by an absence.

**One gate contract, three readers.** `registry_commands/publication.py` names the mandatory gates
once. `prepare_registry_publication_state` computes readiness from it, `registry publish` runs it,
and the generated workflow renders it. D-342 records why the list also has to say *where* each gate
runs: rendering it whole put `lock` back into every generated registry's CI, which CP-26.5 removed
because over the approved representation it resolves nothing.

**A shipped defect the shared list exposed (B-156).** `aart-cli registry validate --source . --strict
--frozen` had been in the generated workflow since `0.0.1` and the CLI has never accepted either
flag, so that step failed with `unrecognized arguments` in every registry `registry init` has ever
produced. `EveryVisibleCommandMentionTest` could not see it while it lived in a `bytes` template;
moving the list into a `.py` file made the guard fail on the first run. The slice text above still
says "strict/frozen validation" -- the correct command is `aart-cli registry validate --source .`.

**Screen 46j.** Push is reached from screen 46's ready workspace row and from nowhere else; the
commit screen offers no `p` and promises no push. Recording the screen in the frame matrix found
three faults at once, all repaired and recorded as D-343: six labelled facts drawn among the two
rows, `v`/`?`/`q` swallowed on the `continue` row while the legend offered them, and four separate
copies of the "is this a branch subscribers read" question, now `needs_a_new_branch`.

**Readiness is derived, never asserted.** `read_registry_workspace` blocks on a launch directory
that is not this worktree's root, a missing exact `HEAD`, a dirty worktree or index, generated
outputs that would change, any failed gate, and nothing committed to publish. `_prepare_registry_push`
re-reads all of it, so stale UI state fails closed.

**Evidence.** `make unit` (4556 tests, green), `make typecheck`, Ruff check and format on the
changed files. Targeted mutations, each red and then restored: `lock` marked as running in CI
(readiness test red); the push status dropped from the view (eight assertions red); the universal
keys returned to their old position after the 46j block (frame matrix red); the edited branch
ignored by the status (one red). No broad `make quality` ran, under D-317.

**The acceptance list, second pass.** Five of the six open items are now held as tests.
`RegistryPushMovesNothingItDoesNotOwnTest` states them against a real Git repository, because what
is being claimed is what Git does: an existing review branch is advanced by an ordinary push, a
diverged one is refused rather than forced, resolution stops at the launch directory instead of
walking up to the registry above it, a Source checkout inside a Registry worktree is not that
Registry, and readiness is read from the directory each time it is asked -- a later commit moves
it, which is the restart claim stated where it can be observed.
`ThreeFactsScreen46KeepsApartTest` holds the accepted snapshot, the local snapshot and push
readiness apart on screen 46, and proves `[p]` is absent while anything blocks. Four more targeted
mutations, each red then restored: `--force` on the push; the upward walk restored to the reader;
the local content digest dropped from the row; the ready row offered regardless of blockers.

**One item is deliberately left.** The branch suggestion is still the constant
`aart-cli/registry-update` rather than the most recent producing action (`aart/init-registry`,
`aart/rebuild-registry`, `aart/promote-…`, `aart/bulk-promote`). Deriving it needs the reducer to
carry which action last produced the commit -- the durable alternative, the commit subject, cannot
tell init from rebuild, since both are written by `publish`. Step 18a renames that whole namespace,
so implementing the scheme now means writing strings 18a rewrites. The field is editable and the
constant is correct, so nothing is unsafe meanwhile. Do it in 18a, with the new names.

### Step 19 — the split itself: one placement per harness, one record per installation (2026-09-20, D-360)

Until this, one placement covered every selected harness and two mechanisms existed only to hold
that shape together against §169.4-6: D-354's refusal when two harnesses answered one input
differently, and D-355's `HARNESS_PLACEHOLDER` launcher composing its credential address at start
time from `$AART_CLI_HARNESS`. Both were correct descriptions of a workaround, which is why both
had tests. Both are gone: `io/artifact_placement.placements_for` answers with one placement per
harness, each with its own `InstallationOwner`, its own tree under that harness's measured
`MANAGED_TREE_TARGETS` directory, its own launcher, its own configuration file and one concrete
credential address. `domain/placement.py` is deleted with them.

**What the split actually cost, which is the part worth recording.** A coordinate stopped
identifying one thing on this machine, and every structure that keyed by one had to say which
installation it meant. Three did not, and none of the three was found by reasoning about it:

- `LocalReceiptStore.path_for` digested the coordinate alone, so the second harness's record
  overwrote the first's. The key is the owner now, which is why the owner had to reach the
  receipts: nothing at the ten call sites had one in scope.
- `planned = {installation.coordinate: ...}` in `io/configured_installation_action.inspect` kept
  one of the two installations, so **both** members were then measured against one tree and both
  failed preflight as "installed state changed after Review". An existing E2E test caught it.
- `available = dict(receipts)` in `record_installation_transaction` would have recorded one
  installation with the other's paths.

The first was predicted by the probe recorded in `NEXT.md`; the other two were not, and they are
the argument for splitting a shared key by finding its readers rather than by listing them.

**The narrowing had to move, not be repeated.** `_declared_narrowing` refuses a single
non-declared profile passed alone, so running it per harness turned "this harness skips" into
"installs nowhere". It runs once for the whole selection before the loop, and the three
"installs nowhere" refusals -- `registers with none of`, `is read by none of`,
`merges into no file of` -- belong to the operation rather than to a harness.

**Where this stops.** The Installed view and the TUI focus key are still
`str(record.coordinate)`. With three harnesses that is three inspections with one key, so two are
unreachable and an action takes whichever the dict kept -- a defect the split created and has not
yet repaid. The suite is red on it, and `NEXT.md` names each failing module and what it waits on.
No targeted mutation is recorded for this step yet; three are owed and named there.

### Step 19 — the key that addresses one installation, and what it repaid (2026-09-20, D-361)

The previous entry stopped at a defect it had created: the Installed view and the TUI focus key
were still `str(record.coordinate)`, so three harnesses were three inspections under one key and
two of them were unreachable. That is now `installation_key(coordinate, owner)` --
`<coordinate>#<harness>`, `+<profile>` where the harness has them, and the bare coordinate where a
record names no owner. One function composes it and `InstalledInspection.installation`,
`InstalledArtifactView.row`, `ConfigurationFileView.row`, the TUI row list, `screens.artifact()`,
`_inspections`, `credential_dependants` and the health map all read it, because a key spelled two
ways addresses nothing and the two spellings would not disagree until a profile appeared.

**What the rewrite of `configured_configuration_action_e2e_test.py` says, which the number did
not.** Nine tests failed on `3 != 1`, and the honest repair was not a count. An installation owns
one configuration file, so `_inspection(harness)` selects the installation and `_edit` drives one
reviewed prepare/complete **per installation** instead of one call spanning three. The assertions
afterwards are unchanged and that is the point: the harnesses nobody edited keep their file, their
digest and the answer their server reports, and Screen 22b now opens with the one harness this
installation is, already chosen.

**Two things found by running it rather than by reading it.**

- Only one of two chosen harnesses was installed in `install_time_config_form_test`. Progressive
  instrumentation showed `credential:github-token` absent at Review and present at execution for
  the second harness. Probing the prepared placements proved the addresses were already
  per-harness, so the product was right and the *test double* was wrong: `_MemoryCredentialProvider`
  held one flag for every address, so it answered `present` for an item nobody had stored. It holds
  one item per service/account now, and the test asserts the two distinct addresses.
- `marketplace update` on an artifact installed into two harnesses was refused outright --
  `installation-proposal-invalid: an artifact was superseded twice` -- because `dict(previous)` in
  `propose_installation` collapsed two previous states naming one coordinate. That is §169.3's
  update acceptance failing, so B-160 was reclassified critical and closed here: supersession is
  keyed by the owner the previous state already carries.

**Found on the way.** A Hypothesis property in `skill_projection_test` generated a body holding a
lone `\r` and showed `_ending` reading it as the document's line ending, writing the whole
frontmatter with `\r` as its row terminator. Detection is `\r\n` or `\n` and nothing else now, with
an example test pinning it.

**Evidence.** `unit` 4671 tests OK, `integration` 410 tests OK, lint/format/typecheck clean. Five
targeted mutations, each reverted after watching the named test turn red:

| Claim | Mutation | What went red |
|---|---|---|
| `path_for` keys by installation | drop the owner from the digested identity | `installation_harness_choice_test` — "a transaction records each installation once" |
| `placements_for` is per harness | keep only the first placement | `installation_harness_choice_test` (5) |
| `inspect` pairs plan with tree per installation | re-key `planned`/`recorded` by coordinate | `install_time_config_form_test` |
| a row addresses an installation | `InstalledArtifactView.row` returns the coordinate | `installed_artifact_paths_test` |
| supersession is per installation | `_supersession_key` ignores the owner | `configured_update_command_e2e_test` |

Scoped `mutmut` over `domain/installation_owner.py` with `installation_owner_test.py`: the
structural mutants of `installation_key` are killed; its three survivors are `ValueError` message
text on a programming-error guard, which is the same class as the survivors already present in
`credential_address` and `installed_name_for` and is not a claim worth asserting. The first run
reported `installation_key` as "no tests" because `mutants/` held a cache from before the function
existed — clear `mutants/` and `mutmut-stats.json` when mutating a module that has gained one.

### Step 20 — a Registry repository on this disk is a Registry (2026-09-20, D-350, D-362)

**Done — a Registry repository on this disk is a Registry (D-350, D-362).**
`registry-local` is a fourth `SourceKind`, carrying an absolute normalized repository path and the
branch to read, which is required rather than defaulted: a local checkout has no remote default to
fall back to. Both transports run the same acquisition, validation, source-store representation,
Marketplace projection, resolver, policy evaluator and installation path; what differs is a flag on
one request. `GitSnapshotRequest.allow_local_transport` lets the bare managed mirror fetch from a
filesystem path, and `ref_is_branch` says the ref is a selected branch rather than one somebody
typed. A bare-mirror `git fetch` from a local path reads only committed refs, resolves
`refs/remotes/origin/<branch>` exactly, touches no worktree and needs no network, so "never switch
branches, never read worktree edits, never fall back to HEAD" is a property of the existing
acquisition rather than a new code path; what had to be added is the refusal of the *tag* that would
otherwise answer for a deleted branch.

Three questions were being asked with the wrong spelling and are now asked with `is_registry`,
`is_git` or `is_local_checkout` on `ConfiguredSource`: "does this publish approved Registry
content", "does this have a remote Git origin", "is this read out of a checkout here". The
consumption path (selection, offers, installation, offline readiness, the install-routing alias
sets, the Marketplace origin, the native-source branch in `consumer/runtime`) asks the first.
`configuration/policy.py` and the `allow_direct_sources` checks deliberately still ask
`kind is REGISTRY_GIT`, because they mean *reviewed remote* (D-362).

Screen 21a gains a Transport row that Space cycles, and relabels itself for a local checkout:
`Repository path` and `Branch`, and a review line that says branch rather than branch-or-tag. The
source stage shows a local checkout's path instead of "invalid Git origin", lets it be selected and
lets it be the default registry.

Evidence: `tests/local_registry_checkout_e2e_test.py` (14 tests) drives the whole thing through the
real CLI against a real repository that holds three different answers at once -- `main`'s 1.2.0, the
selected branch's 1.3.0, and an uncommitted worktree edit -- and asserts that only the second is
ever installed and that the repository's HEAD, status, worktree and refs are unchanged afterwards.
It covers add resolving the branch to its exact commit, the branch that was named rather than the
one checked out, the committed body rather than the edited one, an advanced branch adopted by
explicit sync, a deleted branch and an invalid successor each keeping the last snapshot that
validated, a tag of the branch's name refusing to stand in for it, coexistence of the local and
remote aliases, alias-qualified install, unqualified ambiguity, update converging on the branch
successor, two aliases producing two installations with two trees and two delivered names, the five
provenance facts, and a no-network claim made the only honest way -- the repository has no remote
and no URL anywhere in its configuration.

**Two corrections to what this slice believed while it was being written.**

- The duplicate-source-ID refusal in `compiler/graph.py` was removed on the reasoning that no test
  held it. One did: a case inside
  `compiler_graph_test.test_duplicate_or_mismatched_sources_and_collections_fail_closed`, which the
  broad `unit` gate caught after the focused suites were green. That case is now the positive claim
  `test_one_registry_reached_two_ways_compiles_under_its_two_aliases`; the other five fail-closed
  cases, including duplicate *aliases*, are untouched. `docs/release/schema-freeze.json` was
  regenerated in the same run, for the one input that changed: `configuration/schema.py`.
- The dependency closure through a local alias was planned as an end-to-end test and is not one.
  `requires` is a field of the published native artifact manifest, and the authoring manifest has
  no such field -- `protocol/authoring` neither parses nor emits it -- so no artifact a maintainer
  can author ever reaches a registry carrying a dependency, and the e2e fixture would have had to
  write content promotion does not. What the re-addressing actually changes is held instead by
  `tests/configured_registry_alias_test.py`, against the real reader and a Registry whose content
  calls it `company` while this machine calls it `local-registry`; the authoring gap is B-161.

**Targeted mutations, each red in exactly the test that names the claim, each restored.**

- `load_configured_registry_versions` returns the published versions unchanged (no re-aliasing):
  `configured_registry_alias_test` fails with `approved registry snapshot is inconsistent`, and the
  companion test, where the alias happens to equal the registry's own name, stays green -- which is
  what makes it the discriminating pair rather than one test run twice.
- `_resolved_expressions` ignores `branch_only`: the deleted branch resolves to the tag of its name
  and `source sync` reports success, so
  `test_a_tag_named_like_the_branch_does_not_stand_in_for_it` fails `0 != 1`.
- The duplicate-source-ID refusal is put back in `compile_marketplace_graph`:
  `test_one_registry_reached_two_ways_compiles_under_its_two_aliases` fails with
  `marketplace-graph-invalid: duplicate source ID: company-registry`.

Scoped `make mutants` over the changed modules has **not** been run for this step and is owed.

### Step 20a — implementation checkpoint (2026-09-20, D-363/D-364)

**In flight; do not mark the plan task done.** `smoke_test` is parser-owned and canonical, with
`tool` plus literal `read_only: true`, empty arguments and 15 seconds by default, a 1–60 second
bound, fixed values or installation-local non-secret configuration references, and the two exact
expectation forms recorded in D-363. `aart-cli mcp test` addresses existing installation owners in
one scope/root/harness set. It validates installed bytes, performs schema preflight before sending
the sole declared `tools/call`, evaluates protocol/expectation/service separately, and emits only
safe metadata and bounded reasons. OpenCode and Claude use real discovery plus current structured
events and a one-tool permission ceiling. Tabnine refuses before a prompt because the required
allowlist contract is not available (D-364, B-162).

Focused evidence: 58 tests across authoring, skeleton, selection, evaluation, stdio, harness and CLI
modules, including Hypothesis properties for selection confinement and aggregate results. Ruff and
mypy are green. Four semantic mutations were killed: accepting `read_only: false`; bypassing the
preflight refusal; accepting an extra/old OpenCode session and call; and promoting cached ordinary
content to service PASS. The report test proves neither a configuration value nor raw tool payload
appears in its result.

Still required: a protected fixture observer that can honestly set service PASS; live declared
reads through OpenCode and Tabnine; the remaining focused/unit/docs gates; and scoped mutmut on the
new modules. Tabnine's missing pre-invocation restriction makes its live obligation currently
blocked, so CP-26.20a and GitHub issue #27 remain open.

### Current owner revision — capability-dependent smoke coverage (2026-09-20, D-365)

This supersedes earlier requirements for mandatory Tabnine harness execution, blanket prohibition
of model assessment and unconditional suppression of response display. Implement revised Product
Specification §170 / INV-250–252. Unsupported allowed-tools capability means direct MCP testing with
that installation's credentials and an explicit excluded harness stage; it does not block completion.
Eligible harnesses have a 120-second deadline, exact operation/argument enforcement and an English
prompt requesting `status` (`ok`, `error`, `uncertain`), `summary`, and `possible_error`. Human-readable
fields are English. Assessments remain separate from deterministic checks and service evidence.
Add default-off `--show-response` for bounded current-output inspection, without application
persistence. Keep zero runtime dependencies; use Python's standard library.

Implementation is pending for this revision. Required evidence includes direct-only Tabnine coverage,
capability-based aggregation, deadline/process cleanup, malformed assessment and uncertain/error
cases, argument enforcement, bounded opt-in display and default non-disclosure. Existing tests do not
establish these new claims. CP-26.20a remains in flight; do not mark it done.

## Step 20a — CLI-only smoke verification of installed MCPs

Two decisions landed here, and the second replaced most of what the first was built on.

**D-366 made the external-service stage reachable.** `McpCallResult.service_observed` was the only
thing that could turn `mcp-to-external-service` into a `PASS` and nothing ever set it, so the stage
was always `NOT VERIFIED` and, being unconditionally required, made `aart-cli mcp test` exit nonzero
for every installation that worked perfectly. The backlog offered two readings and §170 rules out
both: §170.3 refuses "any expectation upgrades the stage" ("output shape alone does not prove a
fresh network request") and §170.5 refuses "NOT VERIFIED may still pass" ("unverified required
stages cannot pass"). The specification supplies the third itself -- the judgement comes from "the
selected tool's reviewed behavior **and** the observed result" -- so the stage now needs an author's
`smoke_test.reaches_service` claim *and* a declared `expect` that holds. An absent claim is
`NOT CONFIGURED`, outside the required set, which is what lets a working installation exit zero.

**D-368 removed the harness driver.** Owner-directed: AART no longer launches a harness, submits a
prompt to one, or reads its session. `mcp test --prompt` composes a prompt naming every selected
installation, its server name as that harness sees it, the declared tool with resolved arguments
and the report shape; a person runs it; `mcp test --report <path>` grades what comes back;
`mcp report <path>` checks a report's shape alone, which is what a session can run on its own
output. 220 lines of process control, event parsing, deadlines and the capability gate went with
the driver, and no harness is special any more because none is driven.

What is given up is stated rather than glossed: report evidence is operator-attested, carries its
own coverage value `direct-and-attested`, and never counts as direct evidence. INV-251 was replaced.
The enforcement paragraph of §170.3 no longer claims the harness route blocks unexpected operations;
it says the direct client blocks and the operator observes. What keeps an attested report honest is
D-366: `expect` must carry a value only the real service returns, so an invented or unfaithfully
copied result fails rather than passes, and the runner grades every carried result with the same
evaluator the direct route uses.

### Evidence

Nine targeted mutations across the two decisions, each restored afterwards. **Four first survived,
and every one of them exposed a test that did not hold its own name** rather than a gap in the code:

* the "last JSON object wins" fixture contained only one JSON object, so first and last agreed;
* no fixture carried the self-contradictory `called: false` *with* a result, so dropping the
  `called` check changed nothing;
* the duplicate-installation check appeared to survive being made conditional on correlation,
  because nothing tested duplicates in the no-selection mode.

Each test was corrected -- never the code, and never by weakening an assertion -- and each mutation
then died in exactly the test whose name claims it.

Gates: unit 4754 and integration 424 at D-368, both green, with lint, format-check, typecheck,
validate, docs-check, packaging-check, secret-shape-check and the release gate clean.

## Step 21 — the closeout: what the repository still claimed, and where the suite runs

**2026-09-20 closeout update:** B-151 is closed. Protocol/maintenance/publication guidance uses
`registry/versions/`, versioned packages or references and derived `registry/index.json` /
`registry/snapshot.json`; security scan takes `--registry`. QA-032 explicitly preserves its old
failure as history. README required no edit; the vendoring tutorial's additional obsolete entry
trust claim was corrected. Historical refactor records were not rewritten. The normative schema
freeze was regenerated. Its exact guard passed, failed on a deliberate unfrozen document change,
and passed after restoration; documentation and diff checks passed. PR #29 CI remains the required
full-suite evidence; this step stays in flight pending its result on the updated branch.


The last step of CP-26 is its broad verification, and the first thing broad verification found was
in the repository's own record rather than in the code.

### The matrix was wrong in the direction nobody checks for

`traceability_matrix_test.py` exists because a slice that deletes a module leaves rows citing it.
CP-18 step 3 removed `policy.py` and five rows went on offering it as evidence. The guard closes
that direction: every cited test file, package module and `file::Class::method` case must resolve.

It cannot close the other direction. Eleven rows -- INV-243 through INV-253 -- described behaviour
that steps 18a, 19, 20 and 20a had built, and six of them still said "No implementation evidence
yet" in the column a reader goes to first. Nothing was red, because a row that under-claims breaks
no test. It is still a false statement about the repository, and it is the more corrosive kind: a
reader who finds one row wrong has no way to know which of the remaining two hundred to trust.

Each of the eleven now names the module that owns the clause and the test cases that hold it. Two
record that the contract moved rather than only that it was implemented:

* **INV-250** grades the external-service stage from a declared `smoke_test.reaches_service` plus a
  declared `expect` that holds (D-366). Output shape alone never proved a fresh network request, so
  the product stopped implying that it did; an absent claim is `NOT CONFIGURED` and leaves the
  required set rather than failing it.
* **INV-251** is operator-attested (D-368). AART launches no harness, submits no prompt and reads
  no session, so "current execution evidence" became something a person produces and the tool
  grades, and the absence of a report is an honest non-success state rather than a failure.

### Evidence

**Targeted mutation.** Renaming one cited case in the matrix
(`test_no_harness_is_started_and_coverage_says_so` → `…_said_so`) turned
`test_every_cited_test_case_exists_under_the_name_it_is_cited_by` red, and nothing else; reverted,
the module is green. The guard is load-bearing over the rows this step wrote.

**What the guard cannot do, stated rather than glossed.** It resolves citations; it does not read
them. A row could cite a real test that establishes something other than what the row claims. That
stays a reading job, which is why every rewritten row's characterization column says what its cited
tests actually establish, in the words of the tests.

**Where the full suite runs.** Not here. CP-26.21 owns the full quality, integration/E2E and
release-facing gates (D-317), and by the owner's standing instruction they run on CI across three
interpreters through the pull request rather than locally, where the same answer arrives hours
later. The local checks for this step are the ones that verify the change it made:
`tests.traceability_matrix_test` plus `docs-check`.
