# Rolling out AART on GitHub Enterprise Server

This is the walkthrough for bringing AART into a company that runs its own GitHub Enterprise Server
(GHES). It goes in the order the work has to happen:

1. [Put `aart-cli` on the instance](#part-1--put-aart-cli-on-the-instance) — one repository, a copy
   of this one, kept in step with it.
2. [Configure its Actions variables](#part-2--configure-the-aart-cli-repository) and prove its CI is
   green.
3. [Create the company registry with `aart-cli`](#part-3--create-the-company-registry).
4. [Configure the registry's Actions variables](#part-4--configure-the-registry-repository) so its
   own CI passes.
5. [Point people at the registry](#part-5--point-consumers-at-the-registry).

The order is not optional: **the tool first, the registry second.** A registry's CI fetches AART, so
a registry created before AART has a home on the instance has nowhere to fetch it from.

Nothing below edits a workflow file. Every step is a push, a repository setting, a variable, or an
`aart-cli` command. The [reference](#reference) at the end lists every variable in one place.

Throughout, `ghe.corp` stands for your instance, `platform` for the organisation that owns the
tooling, and `X.Y.Z` for the AART release you are rolling out. Substitute your own.

**One remote convention, everywhere on this page:** in a clone of the copy, `origin` is the
**Enterprise copy** on `ghe.corp` and `upstream` is the **public repository** you copy AART from.
Part 1 makes the clone that way, so the convention is a command rather than an assumption.

## Before you start

| You need | Why |
|---|---|
| An organisation on the instance you can create repositories in, and admin on those repositories | variables, workflow toggles and branch protection are repository or organisation settings |
| A runner the repositories can use that can run **container jobs**, and an image with `git` and a Python 3.10+ interpreter | every job for the tool's own workflows runs in a container and takes its interpreter from the image; nothing else is assumed (no `make`, `curl` or `gh`) |
| A container registry the runner can pull from | unset, `AART_CLI_CI_IMAGE` falls back to the official `python:<version>` images, which come from Docker Hub |
| `actions/checkout@v4` available on the instance | both repositories check out with it |
| `googleapis/release-please-action@v4`, **only** if the copy will cut its own releases | see [Part 1, step 4](#step-4--turn-off-the-release-engine-on-the-copy) — a plain copy does not need it |
| A package index the runner can reach for the tool's own gates (`ruff`, `mypy`, `coverage`) | the default is `pypi.org`; most instances point at an internal mirror |
| Optionally, a hosted repository on that index you may publish to | the cleanest way for registries to fetch AART — [Part 2, step 4](#step-4--publish-the-release-to-the-internal-index-recommended) |
| `gh`, signed in to the instance | the commands below use it. `gh auth login --hostname ghe.corp` once, or set `GH_ENTERPRISE_TOKEN` — `GH_TOKEN` serves github.com only |

Actions from github.com reach a GHES instance through GitHub Connect or `actions-sync`. That is an
instance administrator's setting, and `uses:` cannot be redirected by a variable, so check it before
anything else.

`actions/setup-python` is not on that list, and its absence is deliberate. A step-level `if:` decides
whether a step **runs**, not whether its action is **fetched**: every action a job references is
resolved during "Set up job", before any condition is read. So a job that referenced it failed on an
instance that does not carry it even with `AART_CLI_CI_IMAGE` set and the step skipped. The reference is
gone; every job takes its interpreter from its container image instead.

## Part 1 — Put `aart-cli` on the instance

### Step 1 — Create an empty repository

Create `platform/aart-cli` on the instance. Leave it **empty**: no README, no licence, no
`.gitignore` — the push below brings all of them.

### Step 2 — Switch Actions off for the first push

In the new repository: **Settings → Actions → General → Actions permissions → Disable actions**.

The first push lands `main` and the release tags at once, and each would start a workflow before a
single variable is set. Those runs would fail for reasons that have nothing to do with AART. You turn
Actions back on in Part 2.

### Step 3 — Make the clone, then copy the code and the tags

`<aart-upstream>` is wherever you are copying AART from -- the public repository you found it in,
or another instance's copy. The clone renames its remote to `upstream` and adds the Enterprise copy
as `origin`:

```bash
git clone <aart-upstream>.git aart-cli
cd aart-cli
git remote rename origin upstream
git remote add origin https://ghe.corp/platform/aart-cli.git
git push origin main
git push origin --tags
```

If the clone already exists, check it before anything below means what it says: `origin` must
print `ghe.corp` and `upstream` the public repository.

```bash
git remote -v
```

The **tags** are load-bearing. A registry pins an AART version, and the Git route clones the tag
`v` + that version. A copy without tags cannot serve any version.

### Step 4 — Turn off the release engine on the copy

Once `main` is on the instance, the **Actions** tab lists the workflows. Open **release please** and
choose **Disable workflow**.

The copy does not decide versions — the public repository does, and the tags you pushed are the
result. Left on, `release please` would run on every update of `main`, find no GitHub Releases on
the instance, and open a release pull request covering the whole history.

### Step 5 — Take a later release

Do this only after `vX.Y.Z` exists upstream. In the clone from step 3:

```bash
git fetch upstream --tags
git log --oneline upstream/main..origin/main
```

The second command must print **nothing**: the copy has no commits of its own, so a fast-forward
is safe. Then fast-forward and push both, in this order. `--ff-only` fails loudly rather than
quietly creating a merge commit:

```bash
git checkout main
git merge --ff-only upstream/main
git push origin main
git push origin --tags
```

That is enough for the Git route. For a Release page with the wheel attached, or a wheel on the
internal index, publish the tag as in [Part 2, step 4](#step-4--publish-the-release-to-the-internal-index-recommended).

## Part 2 — Configure the `aart-cli` repository

### Step 1 — Set the variables

**No variable is mandatory.** Leaving every one unset reproduces the public github.com run exactly,
so the question is never "did I set them all" but "what is different about my instance". Set them
under **Settings → Secrets and variables → Actions → Variables**, on the **organisation** where you
can: the registry in Part 4 reads seven of the same names, and one organisation variable configures
every repository at once. A repository variable still overrides it.

**The names are exact, and a wrong one fails silently.** Every lookup has the shape
`vars.NAME || <default>`, so a name no workflow reads is indistinguishable from one never set.
Misspell `AART_CLI_RUNNER` and the run goes green on `ubuntu-latest` without a word. When a
configured copy behaves like an unconfigured one, check the names first.

What almost every Enterprise copy needs:

| Variable | Set it when | Example |
|---|---|---|
| `AART_CLI_RUNNER` | your runners are not `ubuntu-latest`. A JSON array, not a bare word | `["self-hosted","linux","x64"]` |
| `AART_CLI_CI_IMAGE` | the instance cannot pull the official `python:` images | `registry.corp/python:3.11` |
| `AART_CLI_PYTHON_VERSIONS` | whenever `AART_CLI_CI_IMAGE` is set: one entry, the image's interpreter. One image is one Python | `["3.11"]` |

Only with a private index or a private image registry:

| Variable | Set it when | Example |
|---|---|---|
| `AART_CLI_PIP_INDEX_URL` | the gates cannot reach PyPI. A bare URL, no credentials | `https://nexus.corp/repository/pypi-group/simple` |
| `AART_CLI_PIP_INDEX_CREDENTIALS_SECRET_NAME` | that index needs a login: the **name** of a secret holding `user:token` | `PYPI_PROXY_CREDENTIALS` |
| `AART_CLI_IMAGE_USERNAME_SECRET_NAME`, `AART_CLI_IMAGE_PASSWORD_SECRET_NAME` | the image registry needs a login: the **names** of the two secrets. Set both or neither | `IMAGE_REGISTRY_USER`, `IMAGE_REGISTRY_TOKEN` |
| `AART_CLI_PYTHON` | the interpreter inside the image is not called `python` | `python3` |
| `AART_CLI_POETRY` | the image keeps Poetry off `PATH`: its full path | `/opt/poetry/bin/poetry` |
| `AART_CLI_TEST_WORKERS` | the test gates should not use every CPU the job sees, as on a container runner that reports the host's CPUs rather than its quota. A positive whole number; empty uses every CPU (D-466) | `4` |

The rest each turn on one capability, described in the [reference](#variables-the-aart-cli-repository-reads):
publishing to an index (step 4), a reference registry for the release checklist, a default
Registry baked into the wheel, and the release interpreter.

Every variable ending in `_SECRET_NAME` holds a secret's **name**, never its value. Create the
secret itself under **Secrets**, then name it in the variable. A secret's name is not a secret.

List what is set, and delete anything that is not one of the names in the reference: a stale
variable looks like configuration and does nothing. That includes every name from an older AART:
the bare `AART_` spellings, and secret names ending in `_SECRET` rather than `_SECRET_NAME`.

```bash
gh variable list --json name --jq '.[].name' | grep -v '^AART_CLI_'
gh variable list --json name --jq '.[].name' | grep '_SECRET$'
```

Both must print nothing. Delete each name they print:

```bash
gh variable delete <stale-name>
```

When the name is right and the default still wins, it is one of three things: it was saved as a
**secret** (which `vars.` cannot read), it is an **organisation** variable whose visibility does not
include this repository, or it is an **environment** variable (none of these jobs declares
`environment:`).

### Step 2 — Turn Actions back on

**Settings → Actions → General → Allow all actions** (or the allow-list your instance uses, which
must include the actions under [Before you start](#before-you-start)).

### Step 3 — Prove CI is green

`pr-check` runs on pull requests only, so open one carrying an **empty commit**. The gates run over
the checkout, not over the change, so nothing about the change can fail them: a red run is a fact
about the runner, the image or the index. This is the only smoke procedure; repeat it after any
change to the variables.

In the clone from Part 1, step 3:

```bash
git switch -c ci-smoke
git commit --allow-empty -m "ci: prove the gates run on this instance"
git push -u origin ci-smoke
gh pr create --base main --head ci-smoke --title "ci: prove the gates run on this instance" --body "Empty commit. Do not merge."
gh pr checks --watch
```

- The branch name must **not** start with `release-please--`: such a branch narrows the gates to
  four, on one interpreter.
- The pull request title must be a Conventional Commit. `pr-check` checks it first and fails in
  seconds on one it cannot classify.

What a green run says: the gates ran on each interpreter in `AART_CLI_PYTHON_VERSIONS`, and
**exactly one** of the two gate jobs ran — `gates (Python …)` for the public shape, or
`gates (…, private image)` when `AART_CLI_IMAGE_USERNAME_SECRET_NAME` is set. **`pr-check`** is the
check branch protection should require, never a matrix job.

`::error::neither gate job ran` is the failure that would otherwise look like a pass: both shapes
skipped themselves, and GitHub counts a skipped required check as satisfied. `pr-check` fails on
purpose there.

What it does **not** prove: `release.yml` never runs without a tag, so the wheel build and the
release checklist are untested by it. Step 4 is what exercises those.

When it is green, close the pull request **without merging** and delete the branch:

```bash
gh pr close ci-smoke --delete-branch
```

Merging it would put a commit on the copy's `main` that upstream does not have. The check in
[Part 1, step 5](#step-5--take-a-later-release) would never print nothing again, and every later
sync would need a real merge. A red run is a runner, image or index problem; the
[troubleshooting table](#troubleshooting) names the common ones.

### Step 4 — Publish the release to the internal index (recommended)

This gives registries the most robust way to fetch AART: `pip install aart-cli==X.Y.Z` from the same
index everything else uses, with credentials the instance already manages.

1. Set two more variables on the repository:

   | Variable | Set it to |
   |---|---|
   | `AART_CLI_INDEX_PUBLISH_URL` | the upload endpoint of a **hosted** repository, e.g. `https://nexus.corp/repository/pypi-internal/`. A proxy or group repository refuses uploads |
   | `AART_CLI_INDEX_PUBLISH_CREDENTIALS_SECRET_NAME` | the **name** of a secret holding `user:token` for an account that may upload to that repository. It may be the same secret `AART_CLI_PIP_INDEX_CREDENTIALS_SECRET_NAME` names, when that account can also write |
   | `AART_CLI_LOCAL_VERSION_LABEL` | a short label of your own, such as `corp`. The wheel becomes `aart_cli-X.Y.Z+corp-py3-none-any.whl` |

   Set the label before you push the next tag. The public `aart-cli` is published to PyPI, and a
   group that proxies PyPI lists that public wheel too. Without a label, your wheel and the public
   one share a filename with different bytes, because yours carries your default Registry, and
   `publish-index` refuses yours. With it, the filenames differ, `aart-cli==X.Y.Z` matches both,
   and pip picks `X.Y.Z+corp`, because PEP 440 puts a labelled build above the same unlabelled
   version. Only the package version carries the label: `aart-cli --version` still says `X.Y.Z`,
   which is what a registry's `.aart-cli-version` is compared with. Lower-case letters and digits,
   in segments joined by dots; anything else fails the release. GitHub cannot keep `+` in an asset
   name, so the Release shows `aart_cli-X.Y.Z.corp-py3-none-any.whl`; the index receives it as
   `X.Y.Z+corp`, the name pip installs.

2. Create the Release at the tag you already pushed. A tag push alone builds the wheel but neither
   creates a Release nor attaches it; `--verify-tag` refuses to invent a new tag.

   ```bash
   gh release create "vX.Y.Z" --verify-tag --title "vX.Y.Z" --notes "AART X.Y.Z"
   gh release view "vX.Y.Z" --json assets -q '.assets[].name'
   ```

Publishing starts the `release` workflow. It checks the tag is on `main`, runs the release
checklist, builds the wheel, verifies it against the tag and attaches it to the release. Then its
`index` job runs `publish-index.yml`, which downloads that attached wheel and uploads it to the
index. Expect two `release` runs for one tag — the tag push and the Release — with the same result;
only the Release's run publishes. If the run is red at *Prove the tagged source was merged into
main*, the tags were pushed before `main`; redo [Part 1, step 5](#step-5--take-a-later-release) in
order.

The upload is its own workflow, so an index that refuses leaves the Release and its wheel green.
Run it again for any released tag, for example one released before these variables were set:

```bash
gh workflow run publish-index.yml -f tag=vX.Y.Z
gh run list --workflow publish-index.yml --limit 1
```

Running it again is always safe. It first asks `AART_CLI_PIP_INDEX_URL` whether the wheel is
there, so that index must include the hosted repository, as a Nexus group does. The same file
already listed is success and nothing is uploaded. A different file under the same name is refused
and nothing is replaced. Then check what a registry would install:

```bash
pip download --no-deps --index-url <AART_CLI_PIP_INDEX_URL> aart-cli==X.Y.Z -d "$(mktemp -d)"
```

The checklist also reconciles against a reference registry when `AART_CLI_REFERENCE_REGISTRY_URL` is
set. Leave it unset on a copy: those checks report `skipped`, never `passed`, with a warning.

Skip this step if the instance has no index you can publish to. Part 4 has other routes.

### Step 5 — Install `aart-cli` on your own machine

You need it locally to create the registry. CI fetches its own copy. From the hosted repository
you publish to, if you did step 4:

```bash
pipx install --index-url https://nexus.corp/repository/pypi-internal/simple aart-cli==X.Y.Z
```

Install `aart-cli` from the hosted repository, not the group. It has no dependencies, so the hosted
repository is enough, and it holds only your builds. The group also offers PyPI, where a newer
public version without your default Registry can appear before your copy releases it, and an
install with no `==` would take that one.

Or straight from the copy, with your own Git credentials:

```bash
pipx install "git+https://ghe.corp/platform/aart-cli.git@vX.Y.Z"
```

```bash
aart-cli --version
```

The command and the package are both `aart-cli`. `aart-cli` on PyPI is the public build, without
your default Registry. `agent-artifacts` on a public index is somebody else's project.

## Part 3 — Create the company registry

### Step 1 — Create and clone an empty repository

Create `platform/agent-registry` on the instance, empty, then:

```bash
git clone https://ghe.corp/platform/agent-registry.git && cd agent-registry
```

### Step 2 — Initialise it

Review first. Every mutating `aart-cli` command prints what it would write and stops:

```bash
aart-cli maintain registry init --source . --source-id corp-registry --display-name "Corp Registry"
```

The review lists `.aart-cli-version`, `.github/workflows/aart-cli-registry.yml`, `.gitignore`, `README.md`,
`aart-cli-registry.json` and `aart-cli-source.json`. When it reads right, finalize:

```bash
aart-cli maintain registry init --source . --source-id corp-registry --display-name "Corp Registry" --yes
```

`aart-cli docs maintain registry init` lists the options. `--source-id` is the registry's stable
identity: consumers see it, so do not change it later.

`.aart-cli-version` holds the version of the `aart-cli` you just ran. That is the version the
registry's CI will run; [Part 4, step 4](#step-4--read-the-run) is how it moves.

### Step 3 — Commit, publish, and push the first `main`

```bash
git add -A
git commit -m "chore: initialise the registry"
aart-cli maintain registry publish --source .
aart-cli maintain registry publish --source . --yes -m "chore: publish the empty registry"
git push -u origin main
git remote set-head origin --auto
```

`publish` prepares the shared publication gates, rebuilds `registry/index.json` and
`registry/snapshot.json` from approved version records, validates and audits the projected snapshot,
then commits the reviewed changes. It never pushes. The first published Registry snapshot must
carry valid derived catalogs, including when it has no approved versions yet.

This first push is the only one you make by hand. `git remote set-head origin --auto` records which
branch the remote calls default; `aart-cli maintain registry push` reads it to know which branch it must refuse.
Cloning an empty repository leaves it unset.

### Step 4 — From now on, every change is a pull request

The artifact is authored in its Upstream repository, not inside the Registry. Bring it in with
`maintain upstream scan` and `maintain candidate promote`, or with `maintain upstream adopt`; the
[maintainer's route](../registry/maintaining-a-registry-v1.md) walks both. Then commit and push to a
review branch:

```bash
git switch -c add-code-review
aart-cli maintain registry publish --source . --yes -m "feat: add the code-review skill"
aart-cli maintain registry push --source . --branch add-code-review
```

`aart-cli maintain registry push` refuses the default branch by name, and AART never merges. Open the pull request
on the instance; its CI is what Part 4 makes pass. The generated `README.md` in the registry lists the
other everyday commands.

## Part 4 — Configure the registry repository

This is a **different repository** from the `aart-cli` copy, with its own variables. The workflow
`maintain registry init` wrote is generated, and the same for every registry: configure it with
**variables, never edits**, so a newer copy can replace it whole.

`init` runs once and refuses a checkout that is already a registry, so a newer workflow comes from
a scratch one. A registry whose workflow predates the `_SECRET_NAME` names reads variables ending
in `_SECRET`, which nothing sets any more; there is no migrator, so replace it this way, commit the
new file in a pull request, and rename the variables to the names below:

```bash
git init /tmp/fresh-registry
aart-cli maintain registry init --source /tmp/fresh-registry --source-id scratch --display-name Scratch --yes
cp /tmp/fresh-registry/.github/workflows/aart-cli-registry.yml .github/workflows/aart-cli-registry.yml
```

From 0.14.0 the workflow's audit takes only versions that `upstream adopt` recorded as coming from
their remote upstream's default branch, or a tag on it (§185, §188, INV-286, INV-289). It refuses
versions promoted from a local checkout, versions adopted from another branch, and versions
promoted from a Git Source, pinned references or versions adopted with an older aart-cli, none of
which carry that record. It reads the whole Registry, not the change, so the pull request that
brings the new workflow and `.aart-cli-version` must also leave no such version behind. Adopt with
aart-cli 0.14.0 or later. Before you start, `aart-cli maintain registry audit --source .
--for-default-branch` lists every version it would refuse.
Then make `registry-quality-gate` a required check on the default branch, because without branch
protection GitHub merges a pull request whose check is red.

### Step 1 — Choose how the registry's CI fetches AART

The registry's workflow puts `aart-cli` on the runner in one of four ways. **The first variable that is
set wins**; they are never combined. The order runs from the most governed supply chain to the
least, so standing up an index later and setting `AART_CLI_PACKAGE` takes over without unsetting
anything. The version always comes from `.aart-cli-version` — `{version}` in a variable is
replaced with it — so no variable carries a version number.

| Order | Variable | Example | Works when |
|---|---|---|---|
| 1 | `AART_CLI_PACKAGE` | `aart-cli=={version}` | you did [Part 2, step 4](#step-4--publish-the-release-to-the-internal-index-recommended). Installs from `AART_CLI_PIP_INDEX_URL`, with `AART_CLI_PIP_INDEX_CREDENTIALS_SECRET_NAME` if the index needs a login. **Recommended** |
| 2 | `AART_CLI_WHEEL_URL` | `https://ghe.corp/platform/aart-cli/releases/download/v{version}/aart_cli-{version}-py3-none-any.whl` | the release asset is readable **without a login**. The fetch sends no token, so a private repository returns a sign-in page instead of a wheel |
| 3 | `AART_CLI_TOOL_PATH` | `/opt/aart` | the CI image already carries an `aart-cli` source tree or unpacked wheel |
| 4 | `AART_CLI_TOOL_URL` | `https://ghe.corp/platform/aart-cli.git` | the runner can clone that repository, anonymously or with `AART_CLI_GIT_CREDENTIALS_SECRET_NAME`. Clones the tag `v` + the pin, so it needs the tags from Part 1 |

Setting **none** of them is not a fourth route: the first run stops and lists these four. Where
AART comes from is a fact about your deployment, and a shipped default would send every company's
registry to a repository nobody in it had chosen. Row 4 is the shortest to arrange — set
`AART_CLI_REPOSITORY` = `platform/aart-cli` and the URL is built from the instance the job runs on. A
private copy cloned without `AART_CLI_GIT_CREDENTIALS_SECRET_NAME` answers `could not read
Username`, which is why row 1 is the recommendation.

### Step 2 — Set the variables

Seven names mean the same thing here as on the copy: `AART_CLI_RUNNER`, `AART_CLI_CI_IMAGE`,
`AART_CLI_PYTHON`, `AART_CLI_PIP_INDEX_URL`, `AART_CLI_PIP_INDEX_CREDENTIALS_SECRET_NAME`,
`AART_CLI_IMAGE_USERNAME_SECRET_NAME` and `AART_CLI_IMAGE_PASSWORD_SECRET_NAME`.

**Check the organisation first.** If they are set there and this repository is in their visibility,
it already reads them, and a repository copy would shadow the organisation value and drift from it:

```bash
gh variable list --org platform
```

Otherwise copy them from the `aart-cli` repository. Variable values are readable through the API —
they are not secrets, which is why credentials live elsewhere:

```bash
for n in AART_CLI_RUNNER AART_CLI_CI_IMAGE AART_CLI_PYTHON AART_CLI_PIP_INDEX_URL AART_CLI_PIP_INDEX_CREDENTIALS_SECRET_NAME AART_CLI_IMAGE_USERNAME_SECRET_NAME AART_CLI_IMAGE_PASSWORD_SECRET_NAME; do
  v=$(gh variable list --repo platform/aart-cli --json name,value --jq ".[]|select(.name==\"$n\")|.value")
  if [ -n "$v" ]; then gh variable set "$n" --repo platform/agent-registry --body "$v"; fi
done
```

- **The copy carries secret names, not secrets.** Each `_SECRET_NAME` variable now points at a
  secret that may not exist in this repository. Hand the list of names to whoever administers the
  secrets.
- **Read `AART_CLI_PYTHON` rather than accept it.** It defaults to `python` on the copy and
  `python3` here. Copying is right only when both run the same image.

Then the variables that exist only here:

| Variable | When |
|---|---|
| one route from step 1 | always |
| `AART_CLI_REPOSITORY` | with the Git route, unless you set `AART_CLI_TOOL_URL` in full |
| `AART_CLI_GIT_CREDENTIALS_SECRET_NAME` | with the Git route against a private copy: the **name** of a secret holding a token, or `user:token` |
| `AART_CLI_REF` | only to run a branch or tag instead of the pin, on purpose. It switches the version check off, and the run says so |

Unlike the tool's own jobs, the registry jobs do not install Python: the runner or image must
already have it.

### Step 3 — Protect `main`

**Settings → Branches → Add rule** for `main`:

- Require a pull request before merging.
- Require status checks to pass, and require exactly one: **`registry-quality-gate`**.

Do not require the individual gate jobs. Each runs in two container shapes and a compatibility
matrix, only one shape ever runs, and GitHub counts a skipped required check as satisfied.
`registry-quality-gate` has the same name in every configuration and fails if any gate failed or if
none ran.

### Step 4 — Read the run

Re-run the pull request from Part 3, step 4, or push a new commit to it. The job runs
`format --check`, `build --check`, `validate`, `audit`, and `test` at both ends of the version window.
Its **Provide AART** step ends with one line that says what happened:

```text
AART: aart-cli X.Y.Z  via index https://nexus.corp/repository/pypi-group/simple (aart-cli==X.Y.Z)  pinned by .aart-cli-version
```

Which version ran, which route answered, and whether the pin was honoured. When it is green, merge.

**The version lives in Git, not in a settings page.** Moving the registry to a new AART is a pull
request that changes one line:

```bash
echo "X.Y.Z" > .aart-cli-version
```

The gates run on the new version before anyone merges it, so a version that breaks this registry
fails in review, and `git blame` says who moved it. CI compares `aart-cli --version` with the pin
after fetching and fails on a mismatch, on purpose. Take the release into the copy first
([Part 1, step 5](#step-5--take-a-later-release)), and publish it to the index if you use one.

**Tell consumers where it comes from: `.aart-cli-source`.** Once the pin moves, every consumer of
this registry whose `aart-cli` is older is told so: the terminal UI's Home and its footer say
`aart-cli X.Y.Z available`, and each `consume` command says it in one line on stderr.
`aart-cli upgrade --how` and the UI's **AART CLI Update** screen then give the commands. They come
from a file committed beside the pin, in the names of the repository variables above:

```text
AART_CLI_PIP_INDEX_URL=https://nexus.corp/repository/pypi-group/simple
AART_CLI_PACKAGE=aart-cli=={version}
```

`{version}` is the pin. The first route set wins, in the order the **Provide AART** step uses:
`AART_CLI_PACKAGE` (with `AART_CLI_PIP_INDEX_URL`), `AART_CLI_WHEEL_URL`, `AART_CLI_TOOL_PATH`, then
`AART_CLI_TOOL_URL` or `AART_CLI_REPOSITORY`. A person who installed with pipx gets
`pipx install --force …`, with uv `uv tool install --force …`, with pip `python -m pip install
--upgrade --no-deps …`, and one running from a Git checkout gets `git fetch --tags` and `git
checkout vX.Y.Z` in that checkout. The file holds no credential: an address with a password or an
`https` address with a user name refuses the whole file. Signing in to the index stays with each
person's pip, pipx, uv or Git. Without the file, consumers are still told that a newer version
exists, and that you can add it. CI does not read this file; keep it in step with the variables.

## Part 5 — Point consumers at the registry

Each person installs `aart-cli` as in [Part 2, step 5](#step-5--install-aart-cli-on-your-own-machine). A wheel
built with `AART_CLI_DEFAULT_REGISTRY_ALIAS_AND_URL` connects that registry on its own, the first
time the person opens the terminal UI or runs a `consume` command. Without it, each person adds the
registry once:

```bash
aart-cli consume registry add --alias company --kind git \
  --location https://ghe.corp/platform/agent-registry.git --ref main --default
```

The location must be a plain `https` URL with no credentials in it. AART reaches it through the
machine's own Git and credential helper; see
[`git-environment-v1.md`](../configuration/git-environment-v1.md), which also covers proxies.

Then run `aart-cli` for the terminal UI, or use the flag form:

```bash
aart-cli consume list
aart-cli docs consume install
```

## Troubleshooting

| You see | It means |
|---|---|
| a job queued forever | no runner matches `AART_CLI_RUNNER`. It must be JSON — `["self-hosted"]`, not `self-hosted` |
| a configured copy runs exactly like an unconfigured one | a variable name is wrong, or the value was saved as a secret. See [Part 2, step 1](#step-1--set-the-variables) |
| `Unable to resolve action` | the instance does not carry that action. An administrator enables GitHub Connect or syncs it |
| `CERTIFICATE_VERIFY_FAILED` or a timeout from `pypi.org` | `AART_CLI_PIP_INDEX_URL` is unset and the runner has no route to the public index |
| `poetry: command not found` in `release` | set `AART_CLI_POETRY` to Poetry's full path in the image |
| `pr-check` fails with "neither gate job ran" | `AART_CLI_IMAGE_USERNAME_SECRET_NAME` names a secret that does not exist |
| `no aart_cli package under …` | the registry's fetch route reached something that is not AART: wrong URL, wrong path, or a sign-in page instead of a wheel |
| `.aart-cli-version pins X but … provided Y` | the route works and disagrees with the pin: a moved tag, an index that resolved another version, or an image with an old AART baked in |
| `pin X overridden by AART_CLI_REF` | not a failure. Someone set `AART_CLI_REF` to run a branch or tag on purpose, and the run says so |
| `aart-cli maintain registry push` refuses a branch that is not `main` | the checkout does not know the remote's default branch. Run `git remote set-head origin --auto` |
| `publish to index` says the index already lists the wheel with another sha256 | that version was uploaded from a different build. Find out which file is right before deleting anything from the index |
| `publish to index` says the Release must carry exactly one wheel | the Release has no wheel yet (its `release` run failed or is still running) or carries two. Fix the Release first |
| `aart-cli consume registry add` says the URL is not a safe Git location | the location is not `https`, or it carries a user or token. Remove it and let the credential helper supply it |

## Reference

### Variables the `aart-cli` repository reads

Read by `.github/workflows/pr-check.yml`, `.github/workflows/release.yml` and
`.github/workflows/deep-quality.yml`.

| Variable | Default | What it does |
|---|---|---|
| `AART_CLI_RUNNER` | `["ubuntu-latest"]` | JSON array of runner labels |
| `AART_CLI_CI_IMAGE` | `python:<version>` | container image for every job, and the only place an interpreter comes from. Unset, each `pr-check` matrix entry runs the official image for its own version and the release job runs `python:$AART_CLI_RELEASE_PYTHON_VERSION` |
| `AART_CLI_PYTHON` | `python` | the interpreter's name inside the image |
| `AART_CLI_PYTHON_VERSIONS` | `["3.10", "3.11", "3.14"]` | JSON array for the `pr-check` matrix. Pin to the image's one interpreter when `AART_CLI_CI_IMAGE` is set |
| `AART_CLI_RELEASE_PYTHON_VERSION` | `3.11` | which official image the `release` and `deep-quality` jobs run, and the single interpreter `pr-check` uses on a release pull request, when `AART_CLI_CI_IMAGE` is unset |
| `AART_CLI_PIP_INDEX_URL` | `https://pypi.org/simple` | index for the development tools the gates install. Keep it a bare URL |
| `AART_CLI_PIP_INDEX_CREDENTIALS_SECRET_NAME` | unset | **name** of a secret holding `user:token` for that index. Each half is masked before use |
| `AART_CLI_IMAGE_USERNAME_SECRET_NAME` | unset | **name** of the secret holding the image registry's username. Setting it switches every job to the shape that logs in |
| `AART_CLI_IMAGE_PASSWORD_SECRET_NAME` | unset | **name** of the secret holding the image registry's password |
| `AART_CLI_POETRY` | `poetry` | how to invoke Poetry, which builds the wheel |
| `AART_CLI_INDEX_PUBLISH_URL` | unset | upload endpoint of a hosted index. Set, `publish-index.yml` uploads each published release's wheel there, and can be run again by tag; unset, a release only attaches it |
| `AART_CLI_INDEX_PUBLISH_CREDENTIALS_SECRET_NAME` | unset | **name** of a secret holding `user:token` for the publishing account |
| `AART_CLI_LOCAL_VERSION_LABEL` | unset | a PEP 440 local label, such as `corp`, for the version of the wheel built here: `X.Y.Z+corp`. It keeps your wheel's filename apart from the public one on PyPI; `aart-cli==X.Y.Z` still matches it and pip prefers it. `aart-cli --version` keeps `X.Y.Z`. Lower-case letters and digits in dot-joined segments, no leading zero on a number; anything else fails the release |
| `AART_CLI_REFERENCE_REGISTRY_URL` | unset | registry the release checklist reconciles against. Unset, those checks report `skipped` with a warning. It has no default: one naming a github.com repository reproduces nothing on an instance that cannot reach it |
| `AART_CLI_DEFAULT_REGISTRY_ALIAS_AND_URL` | unset | `<alias>=<url>` for the one Registry a wheel built here connects on a first run that has nothing configured: the first `aart-cli` terminal session or `consume` command, except `consume registry add` and `--offline`. Unset bakes nothing, which is what the public build does. The alias is part of the value because it appears in the path of everything installed from that Registry, so it is chosen once and not changed. A malformed value fails the release rather than somebody's first run |
| `AART_CLI_DEFAULT_USAGE_HARNESSES` | unset | harness names separated by commas, such as `opencode` or `opencode,claude`, in which a wheel built here records which skills and MCPs are used from its first start, without asking; a person still turns it off in Settings. Unset or `none` records nowhere until a person turns it on, which is what the public build does. A harness that cannot record (only `claude` and `opencode` can), an empty or a repeated name fails the release. The release receipt records the value |
| `AART_CLI_TELEMETRY_ENDPOINT` | unset | the base address of the telemetry server a wheel built here sends to, such as `https://telemetry.example.com`. Set, it turns telemetry on at each application home's first `aart-cli` or `consume` command where nobody turned it on or off, says so once, and sends what Activity already holds as well as what happens next; `consume telemetry disable` turns it off for good, and `consume telemetry enable` without `--endpoint` uses it. `https://` for any host, `http://` only to `127.0.0.1`, `::1` or `localhost`, never with a user, password, query or fragment; anything else fails the release. Version 1 sends no credential, so a server beyond loopback sits behind your authenticating proxy. Unset offers none, which is what the public build does. The release receipt records the value |
| `AART_CLI_TELEMETRY_UNMANAGED_USES` | unset | whether a wheel built here also sends, while telemetry is on, each use of a skill or MCP it did not install, by the name the harness used. Unset, `on` or `true` sends them; `off` or `false` does not; anything else fails the release. It is only the default: a person changes it at any time in Settings > Telemetry or with `consume telemetry unmanaged on|off`. The release receipt records the value |

### Variables a registry reads

Read by the workflow `aart-cli maintain registry init` writes.

| Variable | Default | What it does |
|---|---|---|
| `AART_CLI_PACKAGE` | unset | fetch route 1: a requirement such as `aart-cli=={version}`, installed with `pip --no-deps --target` |
| `AART_CLI_PIP_INDEX_URL` | `https://pypi.org/simple` | the index `AART_CLI_PACKAGE` installs from |
| `AART_CLI_PIP_INDEX_CREDENTIALS_SECRET_NAME` | unset | **name** of a secret holding `user:token` for that index |
| `AART_CLI_WHEEL_URL` | unset | fetch route 2: a wheel URL, downloaded without credentials and unzipped |
| `AART_CLI_TOOL_PATH` | unset | fetch route 3: an AART tree already on the runner |
| `AART_CLI_TOOL_URL` | instance URL + `AART_CLI_REPOSITORY`, if that is set | fetch route 4: a Git URL, cloned at `v` + the pin |
| `AART_CLI_REPOSITORY` | unset | `owner/name` on this instance, used to build `AART_CLI_TOOL_URL` |
| `AART_CLI_GIT_CREDENTIALS_SECRET_NAME` | unset | **name** of a secret holding a bare token, or `user:token`, used only by the `git clone` route. A bare token is used with the user name `x-access-token`. Each half that came from the secret is masked before use |
| `AART_CLI_REF` | `v` + the pin | a branch or tag to run instead of the pin. Switches the version check off, and the run says so |
| `AART_CLI_RUNNER` | `["ubuntu-latest"]` | JSON array of runner labels |
| `AART_CLI_CI_IMAGE` | unset | container image for the jobs |
| `AART_CLI_PYTHON` | `python3` | the interpreter on the runner or in the image |
| `AART_CLI_IMAGE_USERNAME_SECRET_NAME` | unset | **name** of the image registry username secret; switches jobs to the shape that logs in |
| `AART_CLI_IMAGE_PASSWORD_SECRET_NAME` | unset | **name** of the image registry password secret |

### What a variable cannot change

- **Where an action comes from.** `uses:` must be a literal, so the instance has to carry
  `actions/checkout@v4` (both repositories), `googleapis/release-please-action@v4` (only if
  `release please` stays enabled), and
  the actions explicitly named in the generated workflow.
- **A credential in a variable.** Variables are visible to anyone with read access. Every credential
  above is a secret, named by a variable.
- **Many registries sharing one workflow.** Each registry carries its own copy of the generated
  workflow. Replacing it with a call to a shared reusable workflow works, but the registry then no
  longer carries the file a newer `aart-cli` generates, so taking the next one is a merge by hand.

### What has been run on a real instance

The tool's gate and release jobs have run green on a GHES instance, in a container
image on a company runner, against an internal index with credentials. The registry workflow's four
fetch routes, its pin check and its gates have been run locally from the exact bytes `maintain registry init`
writes.

Not yet run on a real instance: the registry workflow end to end, and the Git fetch route against a
repository that needs a login. Treat those as the places to look first if something fails.
