# CP-26 — Author-side manifests, and the end of the older registry representation

Status: **design**. Step 1 is already done (D-308); nothing else has started.

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

## Why both halves are one epic

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

**Removed outright.** These have no approved-representation behaviour at all:

- `registry scaffold` — authors in place. Replaced by `aart author init` plus `scan` + `promote`.
- `registry publish` — its contract is lock + build + validate + audit + commit over the older
  compiled shape. On an approved registry it already skips locking, which is what made B-142
  unfixable. Replaced by `registry build --yes` and an ordinary Git commit.

**Kept, losing one branch.** `lock`, `build`, `validate`, `audit`, `format`, `push` already
dispatch on the representation; each keeps the approved path and drops the other.

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

Writes `aart.yaml` plus a payload skeleton. CP-26 delivers `mcp` and `skill`; the other three
kinds follow the same generator and are step 8.

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

## 1.6 The README, once there are two readers and not three

The README is 646 lines and serves whoever happens to be reading. After this epic there are exactly
two people it is for, and they want opposite things:

1. **Somebody who wants to use an artifact.** They need AART on their machine, a registry
   subscribed, and an install. Nothing else. Today that path is buried under a three-way install
   grid, an Enterprise section, ten quality gates and the whole release model.
2. **Somebody who wants to publish one.** They need to write a manifest in the repository that
   holds the artifact, check it, and have a registry compile it.

The second half is where the tool's shape has to be stated outright, because every confusion this
epic came out of was the same confusion: **a registry stores compiled artifacts, it does not author
them.** The manifest lives with the source it describes; the registry reads that source at a named
revision and compiles a canonical package from it. `pyproject.toml` lives in the project, not in the
package index — the README says that, in those words, because it is the sentence that makes
`scan`/`promote` obvious and `scaffold`'s removal self-explanatory.

**Install instructions must be executed, not described.** `tests/adoption_first_contact_test.py`
already holds the install section to a shape — no hardcoded host, one `<repository>` placeholder,
three installers — but shape is not the claim worth holding; *the command works* is. Two of the
documented routes are the ones a first-time reader actually takes and neither is covered end to end:
downloading the wheel from the Releases page by hand, and fetching it with `gh release download`.
`scripts/distribution_smoke.py` already builds a wheel and installs it into a disposable
environment, so the gate is an extension of a driver that exists, not a new one. The published lines
stay generated by `scripts/install_commands.py` (D-277, already settled: a markdown file cannot
interpolate a repository address, so the README names neither a host nor a release). What step 13
adds is that the generated form is run.

---

# Part 2 — Plan (CP-26)

Removal comes first. D-308 already refuses `scaffold` and `publish` on a registry that publishes
approved versions, so deleting them takes away nothing anyone can currently use, and every later
step is then written against a smaller surface. Old registries are not a consideration: there is no
compatibility window, no migration command, and no deprecation period.

| # | Step | Notes |
|---|---|---|
| 1 | A registry that has chosen one representation refuses the other's verbs | **done**, D-308 |
| 2 | `registry scaffold` and `registry publish` are deleted | verbs, planners, CLI surface, tests |
| 3 | `lock`, `build`, `validate`, `audit`, `format`, `push` lose their legacy branch | each keeps only the approved path |
| 4 | The consumer and source validators lose theirs | one clear error naming the shape, no fallback |
| 5 | The lock/index schema, tree constants, planning halves and fixtures are deleted | B-057 closes here |
| 6 | The authoring-manifest field surface is collected from the parser, not transcribed | the `ast` oracle; lands before anything generates |
| 7 | A deterministic YAML emitter for the generated subset | block maps, sequences, plain scalars, comments |
| 8 | `aart author init` emits a full-surface `aart.yaml` for `mcp` | first kind end to end, guarded by step 6 |
| 9 | `aart author init` emits the same for `skill` | proves the generator is kind-driven, not special-cased |
| 10 | `aart author check` proves every discovered manifest parses | through `parse_author_manifest` itself |
| 11 | `aart author check` proves each manifest would be accepted by `scan` | the promotable claim |
| 12 | The remaining three kinds | `guideline`, `hook`, `memory` |
| 13 | Every install line in the README is executed by a gate, not described | the manual wheel download and `gh release download`, through `distribution_smoke.py` |
| 14 | The README opens with the consumer's path and nothing else | install AART → subscribe a registry → install an artifact |
| 15 | Its second half is authoring in a source checkout, then the registry that compiles it | `author init` → `author check` → `scan` → `promote`; states the store-not-author rule |
| 16 | Everything that serves neither reader moves out of the README | gates, release model, development setup → `docs/` |

Two ordering constraints, both internal: step 6 precedes steps 8–9, because the generator is written
against the collected surface rather than against a transcription of it; and steps 14–16 come last,
because a README rewritten before the verbs exist documents a surface that is still moving. Step 13
is independent of both and can be taken at any point.

## Still unestablished

Whether the Product Specification sanctions a registry that authors its own artifacts at all. It
describes promotion from a Source and never describes authoring in place, but does not refuse it in
so many words. If it does sanction it, the honest form is a new provenance origin kind meaning "this
registry is the origin" — a product decision, not a refactor, and not part of CP-26.
