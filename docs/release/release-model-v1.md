# The release model

`release-please-config.json`, `.release-please-manifest.json`,
`.github/workflows/release-please.yml` and `.github/workflows/release.yml` match this page.

## What a release is

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

`aart_cli/__init__.py` holds the only version literal in the tree:

```python
__version__ = "X.Y.Z"  # x-release-please-version
```

`pyproject.toml` is rewritten by Release Please's Python release type, and
`runtime_contract.EXECUTABLE_VERSION` parses `__version__` rather than declaring its own.

`README.md` names no release. It writes `X.Y.Z` where a command needs one, and the exact commands
come from `scripts/install_commands.py` and the release body. The generic updater cannot keep a
README current: it rewrites only the first version on a marked line, and it reads the `-py3` of a
wheel filename as a pre-release.

Nothing compares any of them to anything. There is no gate proving they agree, because nothing can
disagree — which is the point of INV-085, and is not the same claim as "the copies are checked".

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

## The schema freeze

`docs/release/schema-freeze.json` pins the sha256 of every file that defines a format other people
depend on — the manifest an author commits, the registry, configuration, installation state,
setup recipes and security assessments — listed as `SCHEMA_INPUTS` in
`scripts/release.py`. It is one file, overwritten in place,
and it names no release.

A change that edits one of those files runs `make release-freeze` and commits the new freeze with
it. That is the moment a person says *yes, this changes a format*; whether the change breaks
anyone is said where the version is decided, in the pull request title (`!` for a break).

The unit gate compares the committed freeze with the tree
(`tests/release_test.py::test_the_committed_freeze_is_the_freeze_of_this_tree`), so a schema moved
without its freeze fails the pull request that moved it. `scripts/release.py check` compares it
again at the tag.

## Why the release engine calls the release run

GitHub raises no workflow event for anything done with the repository `GITHUB_TOKEN`. The tag and
the GitHub Release that Release Please creates therefore start nothing: a release run waiting for
`push: tags` or `release: published` would wait forever.

`release.yml` is `workflow_call`-able for exactly this reason, and `release-please.yml` calls it
when the release-please step reports `release_created`. Its two event triggers serve a tag a
person pushes and a release a person publishes.

## What is deliberately not automatic

Merging the release pull request. Auto-merge is available and is a repository release-policy
choice; it is not turned on here, and nothing in the version automation turns it on as a side
effect. That distinction is INV-105, and it is why the workflow contains nothing to disable.

## For a fork

`release-please.yml` reads one repository variable, `AART_RUNNER`. It reads no image, no
interpreter and no index, because the action it runs brings its own runtime. Everything else about
a fork's release — where it runs, which image, which index, which registry, where the wheel is
published — is on
[`github-enterprise-rollout.md`](../ci/github-enterprise-rollout.md).
