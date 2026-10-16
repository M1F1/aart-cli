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
