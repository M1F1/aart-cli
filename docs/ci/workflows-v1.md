# The repository's workflows

Each thing is proven once, by the run whose job it is. The pull request proves the source; the
release run proves the artifact; a person merging the release pull request decides that a release
happens.

The whole shape rests on one assumption: **`main` is protected and is reached only through a pull
request.** If direct pushes to `main` were allowed, nothing would prove the source of a release.

| What is being proven | Which run proves it |
|---|---|
| the source is correct | `pr-check` |
| the change says what kind of change it is | `pr-check`, on the pull request title |
| merging is safe | branch protection, not a run |
| the release may be cut | merging the release pull request |
| the artifact is sound | `release` |

## The files

| File | Name | Trigger | What it runs |
|---|---|---|---|
| `pr-check.yml` | `pr-check` | `pull_request` | all ten quality gates on 3.10, 3.11 and 3.14, plus the title check |
| `release-please.yml` | `release please` | push to `main` | maintains the release pull request; when one is merged, calls `release.yml` |
| `release.yml` | `release` | tag push, release published, `workflow_call` | the release checks, build, attach, publish |
| `deep-quality.yml` | `deep quality` | `workflow_dispatch` | scoped mutation testing of one module |

Versions, tags and the changelog are Release Please's; see
[`release-model-v1.md`](../release/release-model-v1.md).

## What the release run checks

Only what has the release as its subject:

* the tagged commit is an ancestor of `main`
* the release checklist (`scripts/release.py check`)
* `packaging-check` — the one quality gate whose subject is the wheel rather than the source
* build, then `scripts/release_artifact.py --tag` — the wheel's filename, metadata, declared
  dependencies and installed command, against the tag it is published under
* attach to the release, and publish to an index when `AART_INDEX_PUBLISH_URL` is set

Everything else is left to `pr-check`: a release is cut from a commit that reached `main`, and
nothing reaches `main` except through a pull request that passed all ten gates.

GitHub raises no workflow event for anything done with the repository `GITHUB_TOKEN`, so the tag and
release Release Please creates start nothing on their own. `release-please.yml` therefore *calls*
`release.yml`, which is `workflow_call`-able for exactly that reason.

## Settings, not files

None of these can be committed. Each is set per repository, on every instance separately.

1. **Protect `main`.** Require a pull request; forbid direct pushes. The release pull request is
   merged like any other, and the tag that follows is a tag, which branch protection does not block.
2. **Require one check: `pr-check`.** It is an aggregating job with the same name on every instance.
   The gate jobs themselves come in two shapes, `gates` and `gates-private-image`, of which only one
   ever runs; requiring either by name would hang every pull request on an instance using the other.
   The aggregate fails when the shape that ran failed, and when neither ran — which is what a
   mistyped `AART_IMAGE_USERNAME_SECRET` looks like.
3. **Require branches to be up to date before merging.** Two pull requests can each be green and
   still break `main` together. `pr-check` does not run on `main`, so this setting is what catches
   the pair.
4. **Allow GitHub Actions to create pull requests.** Release Please opens the release pull request
   with the repository token.

## Traps

**A renamed check silently blocks every merge.** Branch protection stores the check by name. Rename
a workflow or job and re-point the required check in the same sitting.

**A branch without a pull request gets no CI.** `pr-check` triggers on `pull_request` only. Open the
pull request early if you want a branch checked while you work on it.

**Only Poetry builds the wheel.** The packaging gate runs in the release job and builds a wheel, so
an image without Poetry fails there. Name it in `AART_POETRY` if it is off `PATH`; see
[`wheel-reproducibility-v1.md`](../release/wheel-reproducibility-v1.md).

**The release pull request gets no `pr-check`.** It is opened with the repository token, which starts
no workflows. Its content is generated — the version bump and the changelog — and the release run
still checks the result.

Running these workflows on a company GitHub Enterprise Server instance is covered by
[`github-enterprise-rollout.md`](github-enterprise-rollout.md).
