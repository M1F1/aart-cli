# Releasing

**Merge a pull request whose title says what kind of change it is. Later, merge the release pull
request that Release Please keeps open.** That is the release.

Nobody edits a version. Nobody writes a changelog entry. Nobody pushes a tag. The one button is
approving the release pull request's run ([step 3](#the-sequence)), and the one decision left to a
person is the one a machine has no business making: *when* the accumulated changes should become a
release.

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
| anything with `!` before the colon | major -- and below `1.0.0` that means `1.0.0` |
| `docs`, `test`, `ci`, `chore`, `build`, `refactor`, `security` | nothing releases on its own |

`bump-minor-pre-major` is off, so a `!` does not become the next minor below `1.0.0`: it becomes
`1.0.0`. Until that is the intent, leave `!` out of the title and out of the body's override block
below, and say what breaks in the description.

`pr-check` validates the title on every pull request, and refuses one it cannot classify. That is
a check on semantic change metadata, not on a version number — nothing in it knows what version
this project is. The types and what each is called in the changelog are declared in
[`release-please-config.json`](../../release-please-config.json), which is also where the `0.x` bumping
rules are turned off so that `feat` means minor and `!` means major at every version.

Locally:

```sh
python scripts/conventional_title.py "feat(tui): add a screen"
```

## What the body has to say

Branch commits disappear at the squash, so without help the changelog gets one line for the whole
pull request. A pull request that carries more than one change says what the changelog should list
in a `BEGIN_COMMIT_OVERRIDE` block in its description:

```text
BEGIN_COMMIT_OVERRIDE
feat(tui): Default says which Settings values cannot install the selection

feat(cli): aart-cli docs prints the command reference read from the parser

docs: one guide for maintaining a registry
END_COMMIT_OVERRIDE
```

- One entry per change, separated by blank lines.
- **No `!` anywhere in the block.** Release Please reads every entry, so one `!` makes the release
  major whatever the title says.
- It is a curated list, not a `git log` dump. Only `test`, `ci` and `chore` are hidden; `docs` and
  `refactor` are listed, so internal bookkeeping commits would appear as Documentation or Changed.

The title still decides the version; the block decides what the changelog says about it.

## The sequence

Run these inside a clone of the repository that is releasing; `gh` takes the repository from it.
`PR` is the pull request being merged.

```sh
PR=<number>
```

1. Wait for `pr-check` on the pull request, then squash merge it. The squash commit is what
   Release Please reads.

   ```sh
   gh pr checks "$PR" --watch
   gh pr merge "$PR" --squash --delete-branch
   ```

2. Release Please opens or updates one release pull request.

   ```sh
   gh pr list --search "chore: release main"
   ```

3. **Approve its run.** The release pull request is opened by a bot, so its `pr-check` waits for
   approval: open the pull request's run and press **Approve and run workflows**. Until somebody
   does, the pull request shows `UNSTABLE` and `gh pr checks` says *no checks reported*. That is
   waiting, not failing.

4. When `pr-check` is green, merge the release pull request. That is the release: the tag, the
   GitHub Release and the `CHANGELOG.md` entry follow from it.

   ```sh
   RELEASE_PR=$(gh pr list --search "chore: release main" --json number --jq '.[0].number')
   gh pr merge "$RELEASE_PR" --squash --delete-branch
   ```

5. Confirm the wheel is attached before telling anyone the version exists. The last step of the
   release run attaches it, so a Release page can be empty for several minutes, honestly.

   ```sh
   gh release view "vX.Y.Z" --json assets -q '.assets[].name'
   ```

An Enterprise copy takes the release afterwards; see
[taking a later release](../ci/github-enterprise-rollout.md#step-5--take-a-later-release).

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
| `scripts/release_artifact.py` | the wheel's filename, metadata version, project name or declared dependencies disagree with the tag, or the installed `aart-cli` reports another version |
| Attach and publish | — |

The last one is the one a pull request could not have run: the wheel did not exist yet.

```sh
python scripts/release_artifact.py --tag vX.Y.Z
```

The seven registry checks are reported `skipped`, never `passed`, when no registry checkout is
available. In CI that choice is one repository variable, `AART_CLI_REFERENCE_REGISTRY_URL` — set, the
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
rather than picking the fix up.

**A tag is never moved.** Moving it would be a force push, which rewrites a published ref that
registries pin and forks copy. What to do depends on what failed:

- **Something outside the tagged files**, such as a runner, an image, a variable, a secret or the
  index. Fix that, then re-run the failed jobs. The re-run uses the same commit and today's
  settings:

  ```sh
  gh run rerun <run-id> --failed
  ```

- **Publishing to the internal index.** `publish-index.yml` started by hand runs as it is on
  `main`, so a fix merged there applies to an existing tag:

  ```sh
  gh workflow run publish-index.yml -f tag=vX.Y.Z
  ```

- **`release.yml` or anything else in the tagged tree.** Merge the fix as a `fix:` pull request.
  Release Please then opens the next patch release, and that release is the one that ships. Leave
  `vX.Y.Z` and its Release where they are. Say on the Release page that it has no wheel and which
  version replaces it:

  ```sh
  gh release edit vX.Y.Z --notes "No wheel was built for this tag. Use the next patch release."
  ```

  Delete a tag or a Release only when the repository owner asks for it.

Re-publishing a Release is safe: the attach step replaces an asset of the same name instead of
colliding with it.
