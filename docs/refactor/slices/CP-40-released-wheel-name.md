# CP-40 — A Release's wheel is published under the name its metadata gives

Status: **done**, on `fix/cp-40-released-wheel-name`, after the owner's Enterprise agent reported it
(2026-10-23). Authority: Product Specification §193, INV-294, D-477.

## Steps

See `docs/refactor/plan.json`, epic CP-40.

1. `publish-index` names the downloaded wheel from its METADATA, not from the asset. Done.
2. Focused verification and the PR. Done: one PR.

## Step 1 — The index gets the name pip installs

**Why.** The Enterprise fork released 0.16.0 with a label. The built wheel was right. GitHub stored
the asset as `aart_cli-0.16.0.<label>-py3-none-any.whl`, because an asset name cannot hold `+`.
`released_wheel` saved and uploaded it under that name. pip refuses it ("Invalid wheel filename
(invalid version)"), so `aart-cli==0.16.0` found no distribution.

**Change.** `scripts/publish_to_index.py`:
- `wheel_filename(path)` builds the name from METADATA `Name` and `Version` and the asset's tags;
- `released_wheel` renames the download to it, so the index check and the upload both use it.

**Tests.** `tests/publish_to_index_test.py`:
- an asset `aart_cli-9.9.9.corp-py3-none-any.whl` whose METADATA says `9.9.9+corp` is saved as
  `aart_cli-9.9.9+corp-py3-none-any.whl` with the same bytes;
- `wheel_filename` gives that name;
- the existing download test now carries a real wheel.

**Evidence beyond the unit tests.** The wheel poetry-core built in CP-39 with `corp`, copied to the
name GitHub gives it, is named `aart_cli-0.15.0+corp-py3-none-any.whl` by `wheel_filename`.

**Targeted mutation.** Returning the download under the asset's name turned only
`test_the_file_is_named_by_its_metadata_not_by_the_asset` red.

**Repair on the fork.** Take this fix into the fork's `main`, then run
`gh workflow run publish-index.yml -f tag=v0.16.0`. No new tag or Release is needed.
