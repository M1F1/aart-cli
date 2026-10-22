# CP-36 — Owner-reported Registry view fixes

Status: **done**, PR #89, on `feat/cp-36-readable-promotions`, at the owner's request (2026-10-22).
Authority so far: Product Specification §190–§191, INV-291–INV-292, D-472–D-473.

## Steps

See `docs/refactor/plan.json`, epic CP-36. The owner may report more; add each as a step before
"Focused verification and the PR", which stays last.

1. Recent promotions name each version as `kind/name@version`; digests stay in Verbose (§190,
   INV-291, D-472). Done.
2. A published Collection passes the Registry's own checks (§191, INV-292, D-473). Done.
3. Focused verification and the PR. Done: PR #89, shared with CP-37, all gates green.

## Step 1 — Recent promotions are listed by name (§190, INV-291, D-472)

**Why.** The owner found Recent promotions on the Maintainer Registry view unreadable. Each line
was a digest: the snapshot a promotion produced, then the candidate ids it promoted.

**Change.**
- `application/maintainer_views.py`:
  - `MaintainerPromotedVersionView(candidate_id, artifact)`, where `artifact` is
    `kind/name@version` or None.
  - `MaintainerRegistryTransactionView.versions` replaces the `candidate_ids` field. Named versions
    sort first. `candidate_ids` remains as a property.
  - `_registry_transactions` takes a map from candidate id to `_version_label`, built from the
    approved versions.
  - The missing-record diagnostic names versions rather than candidate ids.
- `tui_maintainer.py`:
  - `render_maintainer_registry` writes `N. K version(s)` per promotion, newest first, then each
    name. A candidate no approved version carries reads "no longer in this Registry (candidate
    <short id>)".
  - `maintainer_registry_detail` (Verbose) writes `Promotion N (<mode>) produced <snapshot>`, and
    `<name>  candidate <id>` under it.

**Tests.**
- `tests/registry_readable_promotions_test.py`:
  - two promotions are named newest first;
  - no line of the list holds a digest;
  - Verbose holds the snapshot and the full candidate id beside the name;
  - an unpublished candidate sorts after the named one and is said so;
  - the missing-record diagnostic names both versions and holds no digest.
- `tests/maintainer_screen_rows_test.py`: the Verbose layout follows.

**Targeted mutations.**
- Dropping the name lookup (every version None) turned the naming, list and Verbose tests red.
- Appending the short candidate id to a named line turned the list and unpublished-candidate tests
  red.

## Step 2 — A published Collection passes the Registry's own checks (§191, INV-292, D-473)

**Why.** On an Enterprise Registry, `registry collection --yes` published a Collection of 14
approved artifacts. The next `validate`, `audit --for-default-branch` and `publish` then failed with
"required file is missing: artifact.json". The owner's agent traced it to
`promoted_registry_artifacts`, which compiled the Collection's version as a native package.

**Change.** `registry_maintenance/promoted.py`: `promoted_registry_artifacts` skips versions of
kind `collection`. Their bytes are still checked against the approval by
`validate_promoted_registry`.

**Tests.** `tests/registry_collection_cli_test.py`,
`test_a_published_collection_passes_the_registry_s_own_checks`: promote one member, publish a
Collection with `--yes`, then `validate`, `audit`, `build --check` and `format --check` all exit 0.
It was red before the change, with "validate: required file is missing: artifact.json".

**Targeted mutation.** Matching a kind that never occurs instead of `collection` turned that test,
and only that test in the file, red.
