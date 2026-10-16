# CP-31 — Collections end to end, Registry-owned versions, install paths, views and pruning

Status: **in flight** on `feat/cp-31-collections-and-registry-versions`.

Date opened: 2026-10-16. Authority: the product owner (B-067, #72–#75, #53, #54, #41; D-422,
D-423), Product Specification §173. The plan and the implementation land in one PR.

## Steps

See `docs/refactor/plan.json`, epic CP-31. In order:
1. Specification §173 (this document, D-424).
2. Registry-owned versions (#74).
3. `author init --kind collection`.
4. `author check` for Collections.
5. Promotion publishes Collections; the Registry reads them back (B-067 layers 1–2).
6. The Marketplace offers Collections (B-067 layer 3).
7. 05 and 07a treat a Collection as one artifact (D-422).
8. 07 and 07b per member, with Set later.
9. Installed, Doctor and uninstall for Collections (INV-186).
10. Default and custom install paths (#75).
11. Marketplace and Installed columns (#72, #75).
12. Documentation.
13. `RegistryContentMode` rename (#54).
14. Pruning: the vendor family and other legacy routes (#53, #73).
15. Full verification and the PR.

## Step 1 — specification

§173 is accepted, with INV-262–INV-266. D-424 records the implementation choices for versions:
the compiler is told the version by a `RegistryVersions` port built from approved state, "unchanged"
means the same input digest, and the number is chosen at Sync and checked at approval.

## Step 2 — Registry-owned versions (#74)

Done. A source manifest that writes `artifact.version` (or a Collection `version`) is refused. The
compiler takes a `RegistryVersions` port (`protocol/registry_versions.py`):
`next_registry_version` counts patch to 5, minor to 3, then major (D-423), and
`ApprovedRegistryVersions` (`application/registry_versions.py`) builds it from the approved
versions every caller already loads. Sync, `registry scan`, `adopt`, `check-upstream` and
`registry promote` pass it; `author check` uses `NO_REGISTRY`. A changed upstream is always a new
proposal, so `new_version_required` is gone from the CLI, the view and the TUI. A Collection's
digest includes its members' resolved versions (D-425). `author init` and the example manifest
write no version.

Evidence:
- `tests/registry_versions_test.py`: the owner's sequence, two Hypothesis properties (strictly
  greater and inside the limits; nothing on the grid is skipped), the assigner, member resolution.
- `tests/registry_repository_scan_test.py`: a changed payload and a changed manifest are each
  proposed as `1.0.1`. `tests/local_registry_promotion_e2e_test.py`: a change is committed as
  `registry/versions/mcp/github-mcp/1.0.1.json`.
- `tests/authoring_collection_compiler_test.py` `CollectionVersionFollowsItsMembersTest`: unchanged
  stays `1.0.0`, a member's `2.0.1` inside `^2` makes it `1.0.1`, a `3.0.0` outside changes nothing.
- `tests/maintainer_source_sync_application_test.py`: Sync numbers each manifest from the Registry
  it was reviewed against.
- 57 affected modules, 673 tests, green; ruff, mypy and tach clean.

Targeted mutations:
- Collection digest built with `dependencies=()`: only
  `test_a_member_s_new_version_is_the_collection_s_next_version` turned red.
- `ApprovedRegistryVersions.version` returning `max(known)` instead of the next number: the assigner
  tests, both upstream-change tests and three promotion e2e tests turned red.
- `make mutants ONLY=aart_cli/protocol/registry_versions.py TESTS=tests/registry_versions_test.py`:
  40/40 killed.

## Step 3 — `author init --kind collection`

Done (D-426). `aart-cli author init --kind collection --name data-engineer` writes one
`aart-cli.yaml`: `schema`, `name`, `artifacts` with an example member, and `summary` disabled. No
version and no payload. `author check` still skips it; that is step 4.

Evidence: `tests/author_collection_skeleton_test.py` -- what is written parses with
`parse_author_collection_manifest`; every field that parser accepts is named (the Collection half
of the CP-26.6 oracle); the fully enabled text parses; no version; no payload; a non-slug name is
the parser's own refusal; the CLI accepts `--kind collection`; `INIT_KINDS == AUTHORED_KINDS`.
Neighbours: `author_skeleton_test`, `author_command_test`, `author_check_test` (76 tests) green;
ruff, mypy, tach clean.

Targeted mutation: deleting the disabled `summary` line turned exactly
`test_every_field_the_collection_parser_accepts_is_named` and
`test_the_same_text_with_every_disabled_line_enabled_parses_too` red.

## Step 4 — `author check` for Collections

Done. A manifest the artifact compiler neither compiles nor refuses is a Collection, so the check
hands it to `parse_author_collection_manifest`, the parser Sync uses, with `NO_REGISTRY`: members
are not resolved, because a check has no Registry. It reports `ok ... -> collection/<name>` or the
parser's error. `skip`, `ManifestVerdict.checked` and the JSON `checked` field are gone (§173.3:
it never says the manifest was skipped).

Evidence: `tests/author_check_test.py` `CollectionTest` -- a Collection is `ok` with its identity
and counts as promotable; a written version is an error with the parser's message; no members is
an error; what `author init --kind collection` writes passes; JSON names `collection/<name>` and
has no `checked`. 79 tests across the four author modules green; mypy and tach clean.

Targeted mutation: a Collection verdict that drops the parser's diagnostics turned exactly the two
error tests red.

## Step 5 — promotion publishes Collections (part 1: the pure layer)

`application/registry_collections.py` assesses, packages and reads back a Collection;
`plan_bulk_promotion` takes `collections`; `validate_promoted_registry` checks a Collection package
(D-427). Sync already marks a Collection PROMOTED when the Registry holds its version.

Evidence: `tests/registry_collection_promotion_test.py` (12) -- ready and blocked assessment with
the member named; package, version record and audit written; read back as the approved Collection;
a later Sync records it PROMOTED; vendored inside a referenced transaction; one transaction with an
artifact; an invalid Collection refused; a published version immutable; a consistently rebound
Registry over a tampered package unreadable. 87 promotion, Collection, registry and maintainer
modules (885 tests) green; mypy and tach clean.

Targeted mutations: `_invalid_collection_package` returning nothing turned only the tamper test
red; member resolution never failing turned exactly the three blocking tests red.

## Step 5 — part 2: the entry points

The transaction a Maintainer reviews carries Collections next to artifacts:
`prepare_collection_promotion` assesses one against the approved baseline, and
`prepare_promotion_transaction(..., collections=)` plans both kinds in one reviewed state.
Execution reads every Collection Candidate again through the new `read_collection` port, then
re-assesses it and refuses if its member resolution moved since review. The commit subject names a
lone Collection (`Promote collection/<name>@<version> to <registry>`).

- **TUI.** Screen 52 continues with Enter to screen 43. Screen 43 is composed for each Collection
  Candidate in both modes; the transaction mode is the operator's, and the Collection is always
  vendored. The route 51 → 52 → 43 → 44 → 45 is one workflow. The configured io reads a Candidate
  ID from either `active` or `collection_active`, and a single promotion is now the
  one-element bulk transaction.
- **CLI.** `registry scan` and `registry promote` compile through `compile_author_source`, so a
  Collection authored in the checkout is a Candidate there too. `scan` lists it under
  `collections`, with the finding for each unresolved member. `promote --candidate <id>` accepts a
  Collection ID and refuses one whose members are not approved, naming each member.

Evidence:
- `tests/maintainer_composition_e2e_test.py::test_a_collection_candidate_is_approved_through_the_real_shell`:
  the real shell reaches screen 45 and commits. The Registry then reads the Collection back.
- `tests/registry_collection_cli_test.py` (3): `scan` lists the Collection; `promote` refuses
  before its member is approved, naming the member; it is promoted and read back once the member is
  approved.
- 133 TUI, maintainer, promotion, registry, Collection and author modules (1412 tests) are green.
  mypy and tach are clean.

Targeted mutations:
- Ignoring `collection_active` in the configured io turned only the shell approval test red.
- Skipping the CLI readiness check turned only the refusal test red. `plan_bulk_promotion` still
  refused (layered defence), but without the member named.

## Step 6 — the Marketplace offers approved Collections (D-428)

`io/configured_offers.py` stops declining kind `collection`. It reads each Collection back with
`read_registry_collection` and offers the highest approved version as one row, its members at the
exact versions their rows offer. It declines a Collection whose member constraint excludes the
offered version. `io/configured_selection.py` populates `ApprovedRegistrySnapshot.collections` for
the approved resolver. The test fixture `_promote_one_locally` promotes an authored Collection tree
through the real transaction, with members resolved against the Registry built so far.

Evidence: `tests/git_backed_bulk_install_e2e_test.py::CollectionsAreReachableTest` (4), over a
real Git-backed Registry and a real `source sync`:
- `marketplace list` offers `company/collection/starter@1.0.0`;
- its members are `company/mcp/notes@1.0.0` and `company/skill/code-review@1.2.0`;
- it is declined once `skill/code-review@2.0.0` moves past its `^1`;
- a Registry with none offers none.

152 consumer, marketplace, graph, install, TUI and screen modules (1511 tests) are green, apart
from two Hypothesis findings in untouched `tui_layout.py` (B-194). mypy and tach are clean.

Targeted mutation: dropping the member-constraint check turned only the moved-member test red.
