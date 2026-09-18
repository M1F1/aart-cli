# Removing the older registry representation (closes B-057)

Status: **planned**. Step 1 is done (D-308). Nothing else has started.

## What exists today

AART writes registries in two shapes. Only one is named by the Product Specification.

| | approved (canonical) | older (maintainer workspace) |
|---|---|---|
| artifact path | `artifacts/<kind>/<name>/<version>/artifact.json` | `artifacts/<kind>/<name>/artifact.json` |
| catalogs | `registry/index.json`, `registry/snapshot.json` | `aart.index.json` |
| resolution | `registry/versions/<kind>/<name>/<version>.json` | `aart.lock.json` |
| provenance | `registry/promotions/<digest>.json` | — |
| in the spec | yes (§164.7) | **not once** |

`aart.lock.json` and `aart.index.json` appear nowhere in the Product Specification. Neither does
the `scaffold` verb.

## Exactly what goes, and what only loses a branch

Established by reading the callers of `prepare_registry_lock` / `prepare_registry_build` /
`prepare_artifact_scaffold` in `curation/runtime.py`, not by name matching.

**Removed outright — these have no approved-representation behaviour at all:**

- `registry scaffold` — authors in place, which a registry publishing approved versions must not
  do. Replaced by: author in a source checkout, then `registry scan` + `registry promote`.
- `registry publish` — its whole contract is "lock + build + validate + audit + commit" over the
  older compiled shape. On an approved registry it already skips locking, which is what made
  B-142 unfixable. Replaced by `registry build --yes` plus an ordinary Git commit.

**Kept, losing only the legacy branch — these already dispatch on the representation:**

`lock`, `build`, `validate`, `audit`, `format`, `push`. Each keeps its approved-representation
path and drops the other. `lock` on an approved registry already dispatches to
`_prepare_promoted_lock`; `build` already writes `registry/index.json`.

**Deleted once nothing calls them:**

- `parse_registry_lock`, `parse_registry_index` and the lock/index schema in
  `protocol/registry_schema.py`
- `_GENERATED_PATHS` in `protocol/registry_tree.py`
- the legacy halves of `registry_maintenance/planning.py` and `registry_commands/planning.py`
- the `else` branch in `sources/validation.py:269`
- the legacy branch in `consumer/runtime.py` (see the compatibility window below)

Blast radius as measured: 12 production modules and 16 test files name the two files.

## The part that is not cleanup

**Existing registries.** Any registry already published in the older shape is readable today by
`consumer/runtime.py`'s legacy branch. Deleting that branch makes every such registry unreadable
by an upgraded consumer — a published-artifact break, not an internal one. This is the only step
here that is outward-facing and it is the reason the order below is not "delete it all".

**There is no migration path.** Nothing turns an authored registry into an approved one. A
maintainer holding one today can only re-promote every artifact by hand from a source checkout,
and for artifacts authored *in* the registry there is no source checkout to promote from. Step 3
exists because without it step 5 strands people.

## Order

1. **Make mixing impossible.** — **done**, D-308. `scaffold` and `publish` refuse a checkout that
   publishes approved versions. This is what broke a real registry and it is fixed independently
   of everything below.

2. **Deprecate in the open.** `scaffold` and `publish` warn on every run, naming the replacement.
   `registry init` stops being able to produce a registry that will need migrating — it already
   writes no lock or index, so this is a documentation and `doctor` change, not a code path.

3. **`registry migrate`.** Reads an authored registry, writes the approved representation beside
   it, reports the diff, refuses anything it cannot map exactly. This is the substantial slice:
   an authored artifact has no upstream revision, so its provenance record has to say honestly
   that the registry itself is the origin. Without this step, step 5 has no answer for anyone.

4. **Remove the legacy write path.** Delete `scaffold` and `publish`; drop the legacy branch from
   `lock`, `build`, `validate`, `audit`, `format`. After this AART can no longer create the older
   shape. Reading it is untouched, so every existing registry still works.

5. **Compatibility window, then remove the legacy read path.** Only after step 3 has shipped long
   enough for maintainers to migrate. `consumer/runtime.py` and `sources/validation.py` lose their
   legacy branches; a consumer meeting the older shape says so and names `registry migrate`
   instead of failing on a missing file.

6. **Delete the schema.** The parsers, the tree constants, the planning halves, the fixtures.
   B-057 closes here.

Steps 1–4 are internal and reversible. Step 5 is the one that changes what a published registry
means, and it should not start until step 3 is real.

## What is still unestablished

- Whether any registry outside this repository is on the older shape. That decides how long the
  window in step 5 has to be, and it is a question for the maintainer, not the code.
- Whether the Product Specification sanctions a registry that authors its own artifacts at all.
  It describes promotion from a Source and never describes authoring in place, but it does not
  refuse it in so many words. If it does sanction it, step 3 needs a supported shape to migrate
  such artifacts *into*, and that is a product decision rather than a refactor.
