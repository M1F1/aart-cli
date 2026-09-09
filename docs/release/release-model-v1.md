# The release model

**Status: built.** `release-please-config.json`, `.release-please-manifest.json`,
`.github/workflows/release-please.yml` and `.github/workflows/release.yml` match this page.

This is the live procedure. Everything under `release-checklist-v1.md` through
`release-checklist-v18.md` is a dated record of releases cut under the model this replaced, and is
left as written.

## What a release is now

```text
pull request, titled as a Conventional Commit
   ↓
pr-check: ten gates, and the title
   ↓
squash merge to main
   ↓
Release Please updates the one open release pull request
   ↓
a person merges it            <- the release boundary
   ↓
tag + GitHub Release + generated CHANGELOG entry
   ↓
release run: build the wheel, verify it against the tag, attach, publish
```

Nobody edits a version. Nobody writes a changelog entry. Nobody pushes a tag. The single decision
left to a person is *when* the accumulated changes should be published, and it is made by merging
one pull request.

## The classification

| The title says | The version moves |
|---|---|
| `fix`, `perf`, `revert` | patch |
| `feat` | minor |
| anything with `!` before the colon | major |
| `docs`, `test`, `ci`, `chore`, `build`, `refactor`, `security` | nothing releases on its own |

The mapping is in `release-please-config.json`, and two entries there are the reason it is exactly
this mapping rather than Release Please's default:

```json
"bump-minor-pre-major": false,
"bump-patch-for-minor-pre-major": false
```

Below `1.0.0` the default downgrades a break to a minor and a feature to a patch. That is a
defensible reading of SemVer and it is not this project's. Both switches are written down so the
file says what the engine does, on every fork, at every version — which is what INV-086 and INV-104
ask for: the semantics are committed, reviewable configuration, and a fork that changes runners,
images and mirrors does not change what a `feat` means.

`pr-check` validates the title on every pull request, through `scripts/conventional_title.py`. That
script reads the accepted types out of the same config file, so there is one policy rather than two
that agree today.

## One version, written by one thing

`agent_artifacts/__init__.py` holds the only version literal in the tree:

```python
__version__ = "0.0.1"  # x-release-please-version
```

`pyproject.toml` is rewritten by Release Please's Python release type, `README.md` on the lines
carrying `<!-- x-release-please-version -->`, and `runtime_contract.EXECUTABLE_VERSION` parses
`__version__` rather than declaring its own.

Nothing compares any of them to anything. There is no gate proving they agree, because nothing can
disagree — which is the point of INV-085, and is not the same claim as "the copies are checked".

What this removed: `scripts/version.py` and its `_MIRRORS` table, `scripts/bump_version.py`,
`scripts/changelog.py`, `scripts/release_docs.py`, `scripts/prepare_release.py`,
`scripts/cut_release.py`, `.github/workflows/cut-release.yml`,
`.github/actions/cut-release/`, the `version-*` Makefile targets, the `DOC011` changelog-shape
gate, the `scripts/version.py check` half of the `validate` gate, and the release checklist's
pinned `EXPECTED_VERSION`, PROGRESS.md ledger sweep and "every document names this version" rule.

## What the release run proves

Its subject is the artifact. The source was proven by the pull request that put it on `main`;
proving it again at the tag proves the same tree twice.

| Step | Refuses when |
|---|---|
| the tagged commit is an ancestor of `main` | the tag names source nobody reviewed |
| `scripts/release.py check` | schema freeze, system matrix, packaging, and the seven registry reconciliation checks |
| `scripts/packaging_check.py` | the wheel does not build cleanly in a throwaway copy, or does not import back out |
| `scripts/release_artifact.py --tag` | the wheel's filename, metadata version, project name or declared dependencies disagree with the tag, or the installed `aart` reports another version |
| attach, publish | — |

The fourth is the one a pull request could not have run: the wheel did not exist yet. It is also
where "zero runtime dependencies" is finally checked on the thing a user installs rather than on
the source that claims it.

## The wall this hit, and where the answer went

GitHub raises no workflow event for anything done with the repository `GITHUB_TOKEN`. The tag and
the GitHub Release that Release Please creates therefore start nothing: a release run waiting for
`push: tags` or `release: published` would wait forever.

`release.yml` is `workflow_call`-able for exactly this reason, and `release-please.yml` calls it
when the release-please step reports `release_created`. Its two event triggers stay, for a tag a
person pushes.

The retired release button hit the same wall and answered it the same way. The answer outlived the
button.

## What is deliberately not automatic

Merging the release pull request. Auto-merge is available and is a repository release-policy
choice; it is not turned on here, and nothing in the version automation turns it on as a side
effect. That distinction is INV-105, and it is why the workflow contains nothing to disable.

## For a fork

`release-please.yml` reads one repository variable, `AART_RUNNER`. It reads no image, no
interpreter and no index, because the action it runs brings its own runtime. Everything else about
a fork's release — where it runs, which image, which index, which registry, where the wheel is
published — is unchanged and is on
[`enterprise-fork-v1.md`](../ci/enterprise-fork-v1.md).
