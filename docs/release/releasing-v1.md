# Releasing

**Merge a pull request whose title says what kind of change it is. Later, merge the release pull
request that Release Please keeps open.** That is the release.

Nobody edits a version. Nobody writes a changelog entry. Nobody pushes a tag or presses a button.
The one decision left to a person is the one a machine has no business making: *when* the
accumulated changes should become a release.

## What a pull request title has to say

The title becomes the squash commit on `main`, and that commit is what decides the next version.

```text
fix(tui): preserve selected artifact after refresh
feat(mcp): add isolated Python runtime
feat(registry)!: replace legacy source schema
```

| The title says | The version moves |
|---|---|
| `fix`, `perf`, `revert` | patch |
| `feat` | minor |
| anything with `!` before the colon | major |
| `docs`, `test`, `ci`, `chore`, `build`, `refactor`, `security` | nothing releases on its own |

`pr-check` validates the title on every pull request, and refuses one it cannot classify. That is
a check on semantic change metadata, not on a version number — nothing in it knows what version
this project is. The types and what each is called in the changelog are declared in
[`release-please-config.json`](../../release-please-config.json), which is also where the `0.x` bumping
rules are turned off so that `feat` means minor and `!` means major at every version.

Locally:

```sh
python scripts/conventional_title.py "feat(tui): add a screen"
```

## What happens after the merge

Release Please reads the accumulated commits on `main` and keeps **one** pull request open: the
next version, the generated `CHANGELOG.md` entry, and the version written into `pyproject.toml`,
`aart_cli/__init__.py` and this README. It updates that same pull request as more changes
land, rather than asking anyone for a version-bump PR.

Merging it is the release: the tag and the GitHub Release are created, and the release run builds the wheel,
verifies it against the tag and attaches it.

Nothing merges that pull request for you. Automating the arithmetic is not automating the
decision; auto-merge is a policy this repository has deliberately not turned on.

## What the release run proves

Its subject is the artifact, not the source. The source was proven by the pull request that put it
on `main`, and proving it again at the tag proves the same tree twice.

| Step | Refuses when |
|---|---|
| The tagged commit is in `main` | the tag names source no one reviewed |
| Release checklist | schema freeze, system matrix, packaging, and the seven registry reconciliation checks |
| Wheel build | the pinned `poetry-core` is not the one building it |
| `scripts/release_artifact.py` | the wheel's filename, metadata version, project name or declared dependencies disagree with the tag, or the installed `aart` reports another version |
| Attach and publish | — |

The last one is the one a pull request could not have run: the wheel did not exist yet.

```sh
python scripts/release_artifact.py --tag vX.Y.Z
```

The seven registry checks are reported `skipped`, never `passed`, when no registry checkout is
available. In CI that choice is one repository variable, `AART_REFERENCE_REGISTRY_URL` — set, the
registry is cloned and reconciled against; unset, those checks are skipped. It has no default,
because a default naming a github.com repository reproduces nothing on an instance that cannot
reach it.

## One version, written by one thing

`aart_cli/__init__.py` holds the only version literal. `runtime_contract.EXECUTABLE_VERSION`
parses it, the release engine rewrites it and `pyproject.toml`, and nothing compares any of them to
anything, because nothing can disagree. This README names no release: it writes `X.Y.Z`, and the
exact commands come from `scripts/install_commands.py` and the release page.

## The workflow is read from the tag, not from `main`

This is the part that catches people. GitHub loads workflow files from the ref
that triggered the run, so a release runs `release.yml` **as it was at the tag**. A fix merged to
`main` after tagging is not in that run, and re-running the failed job replays the same commit
rather than picking the fix up. Move the tag and publish again:

```sh
git tag -f vX.Y.Z main && git push -f origin vX.Y.Z
```

Re-publishing is safe: the attach step replaces an asset of the same name instead of colliding
with it.
