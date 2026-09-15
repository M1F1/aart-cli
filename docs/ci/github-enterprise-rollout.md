# Rolling out AART on GitHub Enterprise Server

This is the walkthrough for bringing AART into a company that runs its own GitHub Enterprise Server
(GHES). It goes in the order the work has to happen:

1. [Put `aart-cli` on the instance](#part-1--put-aart-cli-on-the-instance) — one repository, a copy
   of this one.
2. [Configure its Actions variables](#part-2--configure-the-aart-cli-repository) and prove its CI is
   green.
3. [Create the company registry with `aart`](#part-3--create-the-company-registry).
4. [Configure the registry's Actions variables](#part-4--configure-the-registry-repository) so its
   own CI passes.
5. [Point people at the registry](#part-5--point-consumers-at-the-registry).

The order is not optional: **the tool first, the registry second.** A registry's CI fetches AART, so
a registry created before AART has a home on the instance has nowhere to fetch it from.

Nothing below edits a workflow file. Every step is a push, a repository setting, a variable, or an
`aart` command. The [reference](#reference) at the end lists every variable in one place.

Throughout, `ghe.corp` stands for your instance, `platform` for the organisation that owns the
tooling, and `0.1.0` for the AART release you are rolling out. Substitute your own.

## Before you start

| You need | Why |
|---|---|
| An organisation on the instance you can create repositories in, and admin on those repositories | variables, workflow toggles and branch protection are repository or organisation settings |
| A runner the repositories can use, with `git` and a Python 3.10+ interpreter — directly or inside a container image | every job runs Python; nothing else is assumed (no `make`, `curl` or `gh` for the tool's own workflows) |
| `actions/checkout@v4` available on the instance | both repositories check out with it |
| `actions/setup-python@v5`, **unless** jobs run in a container image (`AART_CI_IMAGE`) | it downloads interpreters from github.com; an image skips it |
| `googleapis/release-please-action@v4`, **only** if the copy will cut its own releases | see [Part 1, step 4](#step-4--turn-off-the-release-engine-on-the-copy) — a plain copy does not need it |
| A package index the runner can reach for the tool's own gates (`ruff`, `mypy`, `coverage`) | the default is `pypi.org`; most instances point at an internal mirror |
| Optionally, a hosted repository on that index you may publish to | the cleanest way for registries to fetch AART — [Part 2, step 4](#step-4--publish-the-release-to-the-internal-index-recommended) |

Actions from github.com reach a GHES instance through GitHub Connect or `actions-sync`. That is an
instance administrator's setting, and `uses:` cannot be redirected by a variable, so check it before
anything else.

## Part 1 — Put `aart-cli` on the instance

### Step 1 — Create an empty repository

Create `platform/aart-cli` on the instance. Leave it **empty**: no README, no licence, no
`.gitignore` — the push below brings all of them.

### Step 2 — Switch Actions off for the first push

In the new repository: **Settings → Actions → General → Actions permissions → Disable actions**.

The first push lands `main` and the release tags at once, and each would start a workflow before a
single variable is set. Those runs would fail for reasons that have nothing to do with AART. You turn
Actions back on in Part 2.

### Step 3 — Copy the code and the tags

```bash
git clone --bare https://github.com/M1F1/aart-cli.git
git -C aart-cli.git push https://ghe.corp/platform/aart-cli.git main
git -C aart-cli.git push https://ghe.corp/platform/aart-cli.git --tags
```

The **tags** are load-bearing. A registry pins an AART version, and the Git route clones the tag
`v` + that version. A copy without tags cannot serve any version.

`--bare` rather than `--mirror` is deliberate: a mirror clone of a github.com repository also carries
`refs/pull/*`, which the instance refuses on push.

### Step 4 — Turn off the release engine on the copy

Once `main` is on the instance, the **Actions** tab lists the workflows. Open **release please** and
choose **Disable workflow**.

The copy does not decide versions — github.com does, and the tags you pushed are the result.
Left on, `release please` would run on every update of `main`, find no GitHub Releases on the
instance, and open a release pull request covering the whole history.

To take a later AART release, repeat the two pushes from the same bare clone:

```bash
git -C aart-cli.git fetch origin main:main --tags
git -C aart-cli.git push https://ghe.corp/platform/aart-cli.git main
git -C aart-cli.git push https://ghe.corp/platform/aart-cli.git --tags
```

## Part 2 — Configure the `aart-cli` repository

### Step 1 — Set the variables

Set these under **Settings → Secrets and variables → Actions → Variables**. Set them on the
**organisation** where you can: the registry in Part 4 reads several of the same names, and one
organisation variable configures every repository at once. A repository variable still overrides it.

The short list for a private runner with an internal index:

| Variable | Set it to |
|---|---|
| `AART_RUNNER` | your runner labels, as JSON: `["self-hosted","linux","x64"]` |
| `AART_PIP_INDEX_URL` | the internal mirror's simple index, as a bare URL with no credentials: `https://nexus.corp/repository/pypi-group/simple` |
| `AART_PIP_INDEX_CREDENTIALS_SECRET` | if the index needs a login: the **name** of a secret holding `user:token` |
| `AART_CI_IMAGE` | if jobs run in a container: the image, e.g. `registry.corp/python:3.11` |
| `AART_PYTHON_VERSIONS` | with `AART_CI_IMAGE`: one entry, the image's interpreter, e.g. `["3.11"]` |
| `AART_PYTHON` | with `AART_CI_IMAGE`: the interpreter's name inside it, if not `python` |
| `AART_IMAGE_USERNAME_SECRET`, `AART_IMAGE_PASSWORD_SECRET` | if the image needs a login: the **names** of the two secrets |
| `AART_POETRY` | if the image keeps Poetry off `PATH`: its full path, e.g. `/opt/poetry/bin/poetry` |

Every variable holding a credential holds a secret's **name**, never its value. Create the secret
itself under **Secrets**, then name it in the variable. A secret's name is not a secret.

Everything left unset keeps its default, which is what the public github.com run uses. The
[reference](#variables-the-aart-cli-repository-reads) has the full table.

### Step 2 — Turn Actions back on

**Settings → Actions → General → Allow all actions** (or the allow-list your instance uses, which
must include the actions under [Before you start](#before-you-start)).

### Step 3 — Prove CI is green

`pr-check` runs on pull requests only, so open one. It does not have to change anything real:

```bash
git clone https://ghe.corp/platform/aart-cli.git && cd aart-cli
git switch -c ci-smoke
git commit --allow-empty -m "ci: prove the gates run on this instance"
git push -u origin ci-smoke
```

Open a pull request from `ci-smoke` into `main` and wait for **`pr-check`**. It runs all ten gates on
each interpreter in `AART_PYTHON_VERSIONS`, then reports one aggregate result. When it is green,
close the pull request **without merging** and delete the branch, so the copy stays identical to the
tags it serves.

A red run here is a runner, image or index problem. Fix it now — every later step inherits it. The
[troubleshooting table](#troubleshooting) names the common ones.

### Step 4 — Publish the release to the internal index (recommended)

This gives registries the most robust way to fetch AART: `pip install aart-cli==0.1.0` from the same
index everything else uses, with credentials the instance already manages.

1. Set two more variables on the repository:

   | Variable | Set it to |
   |---|---|
   | `AART_INDEX_PUBLISH_URL` | the upload endpoint of a **hosted** repository, e.g. `https://nexus.corp/repository/pypi-internal/`. A proxy or group repository refuses uploads |
   | `AART_INDEX_PUBLISH_CREDENTIALS_SECRET` | the **name** of a secret holding `user:token` for a *deploy* account |

2. **Releases → Draft a new release**, choose the existing tag `v0.1.0`, and **Publish release**.

Publishing starts the `release` workflow. It checks the tag is on `main`, runs the release
checklist, builds the wheel, verifies it against the tag, attaches it to the release, and uploads it
to the index. An index that already holds `0.1.0` refuses a second upload, so publish each tag once.

The checklist also reconciles against a reference registry when `AART_REFERENCE_REGISTRY_URL` is
set. Leave it unset on a copy: those checks report `skipped`, never `passed`, with a warning.

Skip this step if the instance has no index you can publish to. Part 4 has other routes.

### Step 5 — Install `aart` on your own machine

You need it locally to create the registry. CI fetches its own copy.

```bash
# from the internal index, if you did step 4
pipx install --index-url https://nexus.corp/repository/pypi-group/simple aart-cli==0.1.0

# or straight from the copy, with your own Git credentials
pipx install "git+https://ghe.corp/platform/aart-cli.git@v0.1.0"
```

```bash
aart --version
```

The command is `aart`; the package is `aart-cli`. `agent-artifacts` on a public index is somebody
else's project.

## Part 3 — Create the company registry

### Step 1 — Create and clone an empty repository

Create `platform/agent-registry` on the instance, empty, then:

```bash
git clone https://ghe.corp/platform/agent-registry.git && cd agent-registry
```

### Step 2 — Initialise it

Review first. Every mutating `aart` command prints what it would write and stops:

```bash
aart registry init --source . --source-id corp-registry --display-name "Corp Registry"
```

The review lists `.aart-version`, `.github/workflows/aart-registry.yml`, `.gitignore`, `README.md`,
`aart-registry.json` and `aart-source.json`. When it reads right, finalize:

```bash
aart registry init --source . --source-id corp-registry --display-name "Corp Registry" --yes
```

| Option | What it decides |
|---|---|
| `--source-id` | the registry's stable identity. Consumers see it; do not change it later |
| `--display-name` | the human-readable name |
| `--usage-reporting-repository platform/agent-registry` | optional. Also writes the usage-report issue form and the `aart-usage-validate` and `aart-usage-dashboard` workflows |
| `--minimum-version`, `--maximum-version` | the AART version window the registry declares; defaults are the running AART's version and the next major version (exclusive) |

`.aart-version` holds the version of the `aart` you just ran. That is the version the registry's CI
will run, and bumping it later is a pull request.

### Step 3 — Commit, publish, and push the first `main`

```bash
git add -A
git commit -m "chore: initialise the registry"

aart registry publish --source .
aart registry publish --source . --yes -m "chore: publish the empty registry"

git push -u origin main
git remote set-head origin --auto
```

`publish` locks, builds, validates and audits one snapshot, then commits `aart.lock.json` and
`aart.index.json`. It never pushes. A registry does not pass its own gates without those two files,
so the first `main` has to carry them.

This first push is the only one you make by hand. `git remote set-head origin --auto` records which
branch the remote calls default; `aart registry push` reads it to know which branch it must refuse.
Cloning an empty repository leaves it unset.

### Step 4 — From now on, every change is a pull request

```bash
git switch -c add-code-review
aart registry scaffold skill code-review --source . --summary "Review code." \
  --profile claude --platform linux --yes
aart registry publish --source . --yes -m "feat: add the code-review skill"
aart registry push --source . --branch add-code-review
```

`aart registry push` refuses the default branch by name, and AART never merges. Open the pull request
on the instance; its CI is what Part 4 makes pass. The generated `README.md` in the registry lists the
other everyday commands.

## Part 4 — Configure the registry repository

### Step 1 — Choose how the registry's CI fetches AART

The registry's workflow puts `aart` on the runner in one of four ways. **The first variable that is
set wins**; they are never combined. The version always comes from `.aart-version` — `{version}` in a
variable is replaced with it — so no variable carries a version number.

| Order | Variable | Example | Works when |
|---|---|---|---|
| 1 | `AART_PACKAGE` | `aart-cli=={version}` | you did [Part 2, step 4](#step-4--publish-the-release-to-the-internal-index-recommended). Installs from `AART_PIP_INDEX_URL`, with `AART_PIP_INDEX_CREDENTIALS_SECRET` if the index needs a login. **Recommended** |
| 2 | `AART_WHEEL_URL` | `https://ghe.corp/platform/aart-cli/releases/download/v{version}/aart_cli-{version}-py3-none-any.whl` | the release asset is readable **without a login**. The fetch sends no token, so a private repository returns a sign-in page instead of a wheel |
| 3 | `AART_TOOL_PATH` | `/opt/aart` | the CI image already carries an `aart-cli` source tree or unpacked wheel |
| 4 | `AART_TOOL_URL` | `https://ghe.corp/platform/aart-cli.git` | the runner can clone that repository — anonymously, or with a credential already in the image's Git configuration. Clones the tag `v` + the pin |

Row 4 is also what happens when **none** is set: the URL is built from the instance the job runs on
and `AART_REPOSITORY`, which defaults to `M1F1/aart-cli`. So on most instances you set at least
`AART_REPOSITORY` = `platform/aart-cli`. A repository that needs a login and a runner without one
fails that clone on the first run — which is why row 1 is the recommendation.

### Step 2 — Set the variables

Again on the **organisation** where you can, so every future registry is configured before it exists.

| Variable | When |
|---|---|
| one route from step 1 | always |
| `AART_PIP_INDEX_URL`, `AART_PIP_INDEX_CREDENTIALS_SECRET` | with `AART_PACKAGE` |
| `AART_REPOSITORY` | with the Git route, when the copy is not at `M1F1/aart-cli` on this instance |
| `AART_RUNNER`, `AART_CI_IMAGE`, `AART_IMAGE_USERNAME_SECRET`, `AART_IMAGE_PASSWORD_SECRET` | same meaning as in Part 2 |
| `AART_PYTHON` | the interpreter's name on the runner or in the image, if not `python3` |
| `AART_PAGES` = `false` | the instance offers no GitHub Pages and you used `--usage-reporting-repository`. The dashboard is still built and validated, only not published |
| `AART_GH_HOST` | the usage-report workflows run `gh`, which is pointed at the host in `GITHUB_SERVER_URL`. Set this only if the instance is served on a path or a non-default port |

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
`format --check`, `validate --strict --frozen`, `lock --check`, `build --check`, `audit`, and `test`
at both ends of the version window. Its **Provide AART** step ends with one line that says what
happened:

```text
AART: aart-cli 0.1.0  via index https://nexus.corp/repository/pypi-group/simple (aart-cli==0.1.0)  pinned by .aart-version
```

Which version ran, which route answered, and whether the pin was honoured. When it is green, merge.

From here, moving the registry to a new AART is a pull request that edits `.aart-version`: the gates
run on the new version before anyone merges it. Take the release into the copy first
([Part 1, step 4](#step-4--turn-off-the-release-engine-on-the-copy)), and publish it to the index if
you use one.

## Part 5 — Point consumers at the registry

Each person installs `aart` as in [Part 2, step 5](#step-5--install-aart-on-your-own-machine), then
adds the registry once:

```bash
aart source add --alias company --kind registry-git \
  --location https://ghe.corp/platform/agent-registry.git --ref main --default
```

The location must be a plain `https` URL with no credentials in it. AART reaches it through the
machine's own Git and credential helper; see
[`git-environment-v1.md`](../configuration/git-environment-v1.md), which also covers proxies.

Then run `aart` for the terminal UI, or use the flag form:

```bash
aart marketplace list
aart marketplace install --help
```

## Troubleshooting

| You see | It means |
|---|---|
| a job queued forever | no runner matches `AART_RUNNER`. It must be JSON — `["self-hosted"]`, not `self-hosted` |
| `Unable to resolve action` | the instance does not carry that action. An administrator enables GitHub Connect or syncs it |
| `CERTIFICATE_VERIFY_FAILED` or a timeout from `pypi.org` | `AART_PIP_INDEX_URL` is unset and the runner has no route to the public index |
| `poetry: command not found` in `release` | set `AART_POETRY` to Poetry's full path in the image |
| `pr-check` fails with "neither gate job ran" | `AART_IMAGE_USERNAME_SECRET` names a secret that does not exist |
| `no agent_artifacts package under …` | the registry's fetch route reached something that is not AART: wrong URL, wrong path, or a sign-in page instead of a wheel |
| `.aart-version pins X but … provided Y` | the route works and disagrees with the pin: a moved tag, an index that resolved another version, or an image with an old AART baked in |
| `pin X overridden by AART_REF` | not a failure. Someone set `AART_REF` to run a branch or tag on purpose, and the run says so |
| `aart registry push` refuses a branch that is not `main` | the checkout does not know the remote's default branch. Run `git remote set-head origin --auto` |
| `aart source add` says the URL is not a safe Git location | the location is not `https`, or it carries a user or token. Remove it and let the credential helper supply it |

## Reference

### Variables the `aart-cli` repository reads

Read by `.github/workflows/pr-check.yml` and `.github/workflows/release.yml`.

| Variable | Default | What it does |
|---|---|---|
| `AART_RUNNER` | `["ubuntu-latest"]` | JSON array of runner labels |
| `AART_CI_IMAGE` | unset | container image for every job. Unset runs on the runner itself and installs Python with `actions/setup-python` |
| `AART_PYTHON` | `python` | the interpreter's name inside the image |
| `AART_PYTHON_VERSIONS` | `["3.10", "3.11", "3.14"]` | JSON array for the `pr-check` matrix. Pin to the image's one interpreter when `AART_CI_IMAGE` is set |
| `AART_RELEASE_PYTHON_VERSION` | `3.11` | interpreter for the `release` job when no image is used |
| `AART_PIP_INDEX_URL` | `https://pypi.org/simple` | index for the development tools the gates install. Keep it a bare URL |
| `AART_PIP_INDEX_CREDENTIALS_SECRET` | unset | **name** of a secret holding `user:token` for that index. Each half is masked before use |
| `AART_IMAGE_USERNAME_SECRET` | unset | **name** of the secret holding the image registry's username. Setting it switches every job to the shape that logs in |
| `AART_IMAGE_PASSWORD_SECRET` | unset | **name** of the secret holding the image registry's password |
| `AART_POETRY` | `poetry` | how to invoke Poetry, which builds the wheel |
| `AART_INDEX_PUBLISH_URL` | unset | upload endpoint of a hosted index. Set, a published release also uploads the wheel there; unset, it only attaches it |
| `AART_INDEX_PUBLISH_CREDENTIALS_SECRET` | unset | **name** of a secret holding `user:token` for the publishing account |
| `AART_REFERENCE_REGISTRY_URL` | unset | registry the release checklist reconciles against. Unset, those checks report `skipped` with a warning |

### Variables a registry reads

Read by the workflows `aart registry init` writes. Those files are managed: `init` refuses to
overwrite one that was edited by hand, so configure them with variables, not edits.

| Variable | Default | What it does |
|---|---|---|
| `AART_PACKAGE` | unset | fetch route 1: a requirement such as `aart-cli=={version}`, installed with `pip --no-deps --target` |
| `AART_PIP_INDEX_URL` | `https://pypi.org/simple` | the index `AART_PACKAGE` installs from |
| `AART_PIP_INDEX_CREDENTIALS_SECRET` | unset | **name** of a secret holding `user:token` for that index |
| `AART_WHEEL_URL` | unset | fetch route 2: a wheel URL, downloaded without credentials and unzipped |
| `AART_TOOL_PATH` | unset | fetch route 3: an AART tree already on the runner |
| `AART_TOOL_URL` | instance URL + `AART_REPOSITORY` | fetch route 4: a Git URL, cloned at `v` + the pin |
| `AART_REPOSITORY` | `M1F1/aart-cli` | `owner/name` used to build the default `AART_TOOL_URL` |
| `AART_REF` | `v` + the pin | a branch or tag to run instead of the pin. Switches the version check off, and the run says so |
| `AART_RUNNER` | `["ubuntu-latest"]` | JSON array of runner labels |
| `AART_CI_IMAGE` | unset | container image for the jobs |
| `AART_PYTHON` | `python3` | the interpreter on the runner or in the image |
| `AART_IMAGE_USERNAME_SECRET` | unset | **name** of the image registry username secret; switches jobs to the shape that logs in |
| `AART_IMAGE_PASSWORD_SECRET` | unset | **name** of the image registry password secret |
| `AART_PAGES` | unset | `false` skips publishing the usage dashboard to Pages |
| `AART_GH_HOST` | derived from `GITHUB_SERVER_URL` | host for `gh` in the usage-report workflows |

### What a variable cannot change

- **Where an action comes from.** `uses:` must be a literal, so the instance has to carry
  `actions/checkout@v4` (both repositories), `actions/setup-python@v5` (the tool's jobs without an
  image), `googleapis/release-please-action@v4` (only if `release please` stays enabled), and
  `actions/upload-pages-artifact@v3` with `actions/deploy-pages@v4` (only a registry publishing its
  usage dashboard).
- **A credential in a variable.** Variables are visible to anyone with read access. Every credential
  above is a secret, named by a variable.
- **Many registries sharing one workflow.** Each registry carries its own copy of the managed
  workflow. Replacing it with a call to a shared reusable workflow works, but `registry init` then
  refuses that registry, because its managed file no longer matches.

### What has been run on a real instance

The tool's gate and release jobs have run green on a GHES instance, in a container
image on a company runner, against an internal index with credentials. The registry workflow's four
fetch routes, its pin check and its gates have been run locally from the exact bytes `registry init`
writes.

Not yet run on a real instance: the registry workflow end to end, the Git fetch route against a
repository that needs a login, and the usage dashboard's two-job Pages deployment. Treat those as
the places to look first if something fails.
