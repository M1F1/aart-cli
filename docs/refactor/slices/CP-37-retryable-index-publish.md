# CP-37 — Retryable publication to an internal index

Status: **in progress** on `feat/cp-36-readable-promotions`, shipped in one PR with CP-36, at the
owner's request (2026-10-22). Authority: Product Specification §192, INV-293, D-474.

## Steps

See `docs/refactor/plan.json`, epic CP-37.

1. `publish-index.yml` uploads the Release's wheel, asks the install index first, and runs again by
   tag (§192, INV-293, D-474). Done.
2. Focused verification and the PR, shared with CP-36. Todo.

## Step 1 — The index upload is its own retryable workflow

**Why.** On the owner's Enterprise fork, `v0.14.0` was released before
`AART_CLI_INDEX_PUBLISH_URL` was set. The upload was the last step of the release job and ran only
while a Release was being published, so there was no way to publish that tag without deleting and
recreating its Release. An index that refused also turned the whole release red. The owner's
company release template (bump, commit, tag and `poetry publish` from the Enterprise repository)
was weighed: only its upload fits, because a fork must stay a fast-forward of the public `main`.

**Change.**
- `.github/workflows/publish-index.yml` (new): `workflow_call` and `workflow_dispatch`, each with
  `tag`. Two container shapes, each guarded by `vars.AART_CLI_INDEX_PUBLISH_URL != ''`.
  `contents: read`.
- `.github/actions/publish-index/action.yml` (new): re-masks both halves of both logins, then runs
  `scripts/publish_to_index.py --url "$INDEX_PUBLISH_URL" --release "$TAG" --index
  "$AART_CLI_INDEX_URL"`.
- `.github/workflows/release.yml`: the publish variables leave both jobs. A new `index` job needs
  both shapes, runs with `always()` when the run attached the wheel and one shape succeeded, and
  calls `publish-index.yml` with `secrets: inherit`.
- `.github/actions/release/action.yml`: the upload step is gone.
- `scripts/publish_to_index.py`: `released_wheel` downloads the Release's one wheel;
  `indexed_digest` reads the PEP 503 project page with the install login; `publish_once` skips an
  identical file, refuses a different one, and otherwise uploads. `--release` and `--wheel` are
  mutually exclusive; `--index` is optional.
- `scripts/github_api.py`: `request` takes `accept`, and sends the token as an unredirected header.
- Docs: rollout Part 2 step 4 (retry by tag, one secret may serve read and write, `pip download`
  check), two troubleshooting rows, the variable reference, `docs/ci/workflows-v1.md`. The check to
  require on a Registry is `registry-quality-gate`, in the rollout page and in the README
  `registry init` writes.

**Tests.**
- `tests/publish_to_index_test.py`: same file listed means no upload; another sha256 is refused
  with no upload; a 404 project and another version listed are uploaded; the check reads with
  `AART_CLI_INDEX_CREDENTIALS` and the upload writes with its own login; no `--index` uploads; the
  Release's one wheel is downloaded with `Accept: application/octet-stream` and the token
  unredirected; zero or two wheels are refused naming the tag.
- `tests/release_workflow_test.py`: the guard on both shapes; the release action no longer
  uploads and `release.yml` calls the upload after both shapes; dispatch and call both take `tag`;
  no `upload-artifact` or `download-artifact` anywhere; both logins re-masked.
- `tests/enterprise_ci_template_test.py`: `publish-index.yml` joins the checked workflows;
  `AART_CLI_INDEX_PUBLISH_URL` may gate only that workflow.

**Targeted mutations.**
- Skipping the index check turned the three tests that depend on it red.
- Sending the token as an ordinary header turned the download test red.
