# AART

AART installs reviewed **skills, guidelines, MCP servers, hooks, and memory** from canonical,
validated registry snapshots into a selected harness. It uses only the Python standard library and
has zero runtime dependencies.

Three names, because they differ and the difference has cost someone an afternoon: the command is
**`aart`**, the package you install is **`aart-cli`**, and the import package is
**`agent_artifacts`**. `agent-artifacts` on a package index is a **different project, belonging to
someone else** — installing it gives you their code, not this one. The wheel also installs
`agent-artifacts` as a second name for the `aart` command.

## One contract

AART is one product with one interface: `source`, `marketplace`, and `registry`. Input outside the
contract is rejected with a diagnostic; there are no compatibility flags or silent fallbacks.

`native-source-v1` and `registry-v1` name the document families, and setup v2 is the recipe format.
The same compiler validates them at both publication and consumption boundaries.

The [Product Specification](docs/product-specification/PRODUCT_SPECIFICATION.md) is the product's
single source of truth. See also the [native source contract](docs/protocol/native-source-v1.md) and
the [registry contract](docs/protocol/registry-v1.md).

## Install and quick start

Python 3.10 or later is required.

**The exact commands are on this repository's [Releases page](../../releases).** Every release
carries them, filled in with the address of the repository you are reading them in -- so a fork on
a company instance shows its own host, and nobody has to guess or substitute anything. That link is
relative on purpose: it resolves inside whatever repository this file lives in, which is why this
page can point at a release without naming an address that would be wrong in a fork, and would
conflict on every merge from upstream.

From a checkout, the same commands print here:

```sh
python scripts/install_commands.py
```

The shapes are below, if you want them before you look. `<repository>` is the address of the
repository you are reading this in, and `X.Y.Z` is the release you want; the command above prints
both filled in.

| Source | `pip` (inside your environment) | `pipx` | `uv` |
|---|---|---|---|
| Tagged Git repository, no clone | `python -m pip install --no-deps "git+<repository>.git@vX.Y.Z"` | `pipx install "git+<repository>.git@vX.Y.Z"` | `uv tool install "git+<repository>.git@vX.Y.Z"` |
| Downloaded wheel | `python -m pip install --no-deps ./aart_cli-X.Y.Z-py3-none-any.whl` | `pipx install ./aart_cli-X.Y.Z-py3-none-any.whl` | `uv tool install ./aart_cli-X.Y.Z-py3-none-any.whl` |
| Release wheel by URL | `python -m pip install --no-deps <the wheel's address on the release>` | `pipx install <the wheel's address on the release>` | `uv tool install <the wheel's address on the release>` |

### The short way: copy the wheel's link, paste one line

The full shape of a wheel install names the version three times, which is three chances to mistype
it. With `uv`, where `<repository>` is the address you are reading this in and `X.Y.Z` is the
release you want:

```sh
uv tool install --force "<repository>/releases/download/vX.Y.Z/aart_cli-X.Y.Z-py3-none-any.whl"
```

Nobody should type that. **Copy the link instead, and let the shell read your clipboard.** On the
release page, under **Assets**, right-click `aart_cli-X.Y.Z-py3-none-any.whl` and choose *Copy link
address*. Then paste whichever of these you use -- each one is complete as written, with no
placeholder left to fill in:

```sh
uv tool install --force "$(pbpaste)"
```

```sh
pipx install --python "$(command -v python3)" --force "$(pbpaste)"
```

```sh
python -m pip install --no-deps --force-reinstall "$(pbpaste)"
```

The version never appears, because the address you copied already carries it. `uv tool` and `pipx`
build an isolated tool environment; the `pip` line installs into **whatever environment is active
right now**, so use it deliberately.

`pbpaste` is macOS. The same line works elsewhere by swapping it for your clipboard reader --
`wl-paste` on Wayland, `xclip -o -selection clipboard` on X11, `powershell.exe Get-Clipboard` under
WSL.

Two things that make this fail, both worth recognising:

- **The clipboard holds something else.** Copying a shell command from a page and then running one
  of these makes the installer try to install that command as a package name. Check with
  `pbpaste` alone before you paste.
- **The release is private.** `pip`, `pipx` and `uv` send no token when fetching a URL, so a
  private asset returns a sign-in page and the installer fails on a corrupt archive. Use the
  download-first blocks below instead.

### When the wheel has to be downloaded first

A private release cannot be installed from its URL at all, for the reason above. Download the file
with something that does authenticate -- the instance's own web UI, or a CLI you are already signed
in to -- and install the path:

```sh
uv tool install --force ./aart_cli-X.Y.Z-py3-none-any.whl
```

```sh
pipx install --python "$(command -v python3)" --force ./aart_cli-X.Y.Z-py3-none-any.whl
```

`pipx` is handed `python3` explicitly because the interpreter it cached as its own default may be a
different or a broken one; whichever it is must be 3.10 or newer. If an install fails complaining
about a corrupt archive, the downloaded file is probably a saved sign-in page rather than a wheel --
`python3 -m zipfile -t aart_cli-X.Y.Z-py3-none-any.whl` says so in one line.

The Git row needs no pre-downloaded wheel: `git+https://` uses your Git credentials. It does build
from source, however, so its environment must be able to obtain the pinned `poetry-core` build
backend. The downloaded-wheel route avoids that build requirement.

`pipx` and `uv tool` create an isolated tool environment. AART has no runtime dependencies. The
release wheel is byte-reproducible from its tag; see
[wheel reproducibility](docs/release/wheel-reproducibility-v1.md) to check one.

### On a private Enterprise instance

A fork on a GitHub Enterprise Server instance is normally private, and that changes which of those
sources work at all.

| Source | Works on a private instance |
|---|---|
| Tagged Git repository, no clone | Yes, if git authenticates **and** the build environment can obtain `poetry-core==2.4.0` |
| Downloaded wheel | Yes, once the file is on disk -- see below for getting it there |
| Internal index, once the wheel is published to it | Yes. Add `--index-url <your index>` (`--default-index` for `uv`) and ask for `"aart-cli==X.Y.Z"` |
| Release wheel by URL | **No.** See below |

The last row is the one that surprises people. `pip`, `pipx` and `uv` send no token when they fetch
a URL, so a release asset on a private repository answers with a sign-in page. The installer then
fails on a corrupt archive rather than on a refusal, and the message names neither cause nor fix.
Use that row only where the address answers without a login.

To get the wheel onto disk instead, download it with something that does authenticate -- your
instance's own UI, or a CLI you already have signed in -- and install from the file.

Keep a reviewed tag rather than following a moving branch. Where `pipx` is unavailable, an unzipped
wheel is a working installation on its own -- AART has no runtime dependencies, so a directory on
`PYTHONPATH` is enough.

The editable install is for working on AART itself, not for a colleague adopting it:

```sh
git clone <repository>.git
cd aart-cli
python -m pip install --no-index --no-deps --no-build-isolation -e .
```

Then, in a consumer project:

```sh
cd /path/to/consumer-project
aart source add \
  --alias company \
  --kind registry-git \
  --location https://github.example.com/company/agent-registry.git \
  --ref main \
  --default \
  --json
aart marketplace list --json
```

`source add` acquires, compiles, and validates the exact snapshot before it saves configuration.
With automatic synchronization (the default), source-bearing marketplace and TUI entry points
compare with the origin and publish a validated changed snapshot first. Manual mode reports
`not-synchronized` or `could-not-check` without moving the local pointer.

## Consumer lifecycle

Every mutation uses the same review and finalize boundary. Without `--yes`, a command renders its
reviewed plan only; `--yes` finalizes that exact plan. `--json` changes only rendering, never
selection, consent, effects, or exit semantics.

```sh
# Explicit source refresh
aart source sync --alias company --json

# Review, then finalize
aart marketplace install company/skill/code-review --profile claude --json
aart marketplace install company/skill/code-review --profile claude --yes --json

aart marketplace status --profile claude --json
aart marketplace update --profile claude --yes --json
aart marketplace update --profile claude --prune --yes --json
aart marketplace uninstall company/skill/code-review --profile claude --yes --json
```

An empty `marketplace update` selects every installed artifact in the given profile and scope.
After `source sync`, status distinguishes `current`, `update_available`, `removed_upstream`,
`source_unavailable`, and `local_drift`. `--prune` removes only the reviewed items outside the
authoritative selected set.

An artifact can declare `requires`. Direct install and update calculate a deterministic transitive
closure before review; an unavailable or conflicting dependency cannot create a partial install.

### Finding an artifact without reading the whole list

`list` prints everything. On a catalog of any size, the way to find one artifact is to type part
of it:

```sh
aart marketplace search review
aart marketplace search review python --json
```

Every word must match, so a second word narrows the answer rather than widening it. Matching is
case-insensitive substring over the name, the coordinate, the summary, and collection membership:
`review` finds `code-review`. The best matches come first -- a name that *is* the word, then a
name that starts with it, then a name that holds it, then a coordinate, then a summary -- and rows
that tie keep catalog order, so two runs over one catalog print one order. The coordinate printed
is the one `install` takes.

The TUI searches the same way. In the list of artifacts press `/` and keep typing: the list
narrows as you type, Enter keeps the filter and hands the arrows back, Escape drops it. In the
text fallback the same thing is a line: `/review` shows the matching rows, `/` on its own lists
everything again. A filter only hides rows -- what was ticked stays ticked, and every row keeps
the number it has in the full list.

## MCP setup and credentials

A v2 recipe and its package-root `SETUP.md` are compiled before AART plans an installation effect.
Review shows effects, capabilities, entrypoint, trust, and the manual route without secrets.

A human supplies credentials in an approved interactive session. AART never writes them to a
registry, state, JSON output, or logs. Registries may use safe placeholders such as
`${GITHUB_PERSONAL_ACCESS_TOKEN}`; container images should be pinned by digest.

## Reading, checking, and undoing a setup

Every setup run writes a complete account of itself — the plan hash, the installer hash, when it ran,
how it exited, and one receipt per step. Three actions read that account after the run is over.

```sh
# What did the run actually do?
aart marketplace receipt show company/mcp/github --profile claude --json

# Is any of it still true?
aart marketplace receipt verify company/mcp/github --profile claude

# Reverse it — review first, then finalize
aart marketplace receipt undo company/mcp/github --profile claude
aart marketplace receipt undo company/mcp/github --profile claude --yes
```

`show` renders the persisted record. `verify` asks this machine whether each receipt's claim still
holds: does the image tag exist and still resolve to the recorded id, does the managed block still
carry the text that was installed, does the Keychain item exist **and hold a non-empty value**. A
claim it cannot ask is reported `unknown` rather than `true`, and `verify` exits non-zero when any
claim is false, so it is usable from CI. It reports and never repairs — an orphaned run directory is
named and left where it is.

`undo` is a mutation, so it follows the same boundary as everything else: without `--yes` it prints
the effects it would reverse and changes nothing. `--expect <digest>` binds the decision to the exact
undo that was read.

The review names what it will **not** reverse, and why, before you approve it:

```text
Review undo: company/mcp/github#claude/project
reverses: Keychain item service='aart-github' account='token'
  step    3
  module  macos-keychain.store@1
  reason  deletes the Keychain item this run created
reverses: /Users/you/.zshrc
  step    2
  module  file.managed-block@1
  reason  restores the file to the block it held before this run
keeps: aart/mcp/github:1.0.0
  step    1
  module  docker.build@1
  reason  the tag named an image before this run, so it is not removed — but it now points
          at what this run built, and the receipt never recorded the earlier image id, so
          the undo cannot restore the original binding
Undo: reverses=2, keeps=1
Reviewed only; re-run with --yes to apply this exact undo.
```

Steps are numbered in the order the rollback runs them, which is the reverse of the order they were
applied — so the review reads top to bottom in the order you will watch it happen.

A step whose receipt no longer matches the reviewed plan is reported and skipped, never forced. On
partial success the record is written back as `rollback_incomplete`.

All three are also reachable from `aart` with no arguments, under **Action → receipt**.

### One report for the whole machine

The three commands above each answer a question about one installation. `aart doctor` answers them
for everything at once, and reads only — it resolves no marketplace content and applies nothing.

```sh
# What is the state of everything installed here?
aart doctor
aart doctor --json
```

One run reports measured drift with the smallest policy-permitted repair plan for each item; offline
readiness for every enabled source, as three separate answers — cached metadata, cached canonical
payload, cached runtime dependencies — because `--offline` is one flag and those are three different
reasons it can fail; any working copy an interrupted run left behind; the activity trail and what
each entry can still undo; credential health and which installations depend on it; and the
configuration this machine is ignoring, meaning disabled sources and fields your organization's
policy has locked.

Repair follows the same review-then-confirm boundary as everything else, one artifact at a time:

```sh
# Review one artifact's minimal plan — applies nothing
aart doctor --repair company/mcp/github

# Apply exactly the plan that review returned
aart doctor --repair company/mcp/github --yes --expect <digest>
```

`--yes` without `--expect` is refused, and a machine that changed between the review and the
confirmation returns the recomputed plan instead of applying the stale one. There is no flag that
repairs everything.

What it cannot repair, it still reports: an artifact whose payload is missing or divergent is named
with what is wrong, rather than being omitted because no repair for it exists.

## Writing an artifact

`aart author init` starts one in the directory you name. It writes an `aart.yaml` carrying every
field this build accepts — the optional blocks commented out, one line of explanation above each —
so narrowing the manifest down to what your artifact needs is an edit rather than a search through
a schema. A payload skeleton is written beside it, and nothing already in the directory is
replaced.

```sh
aart author init --kind mcp --name github-mcp --into ./github-mcp
aart author init --kind skill --name code-review --into ./code-review
aart author check --source ./github-mcp
aart author check --source . --json
```

This build generates the `mcp` and `skill` skeletons. Each carries the payload file its package
format requires — an entrypoint for an MCP server, a `SKILL.md` for a skill — and names the blocks
it deliberately leaves to you.

`aart author check` reads the directory the way a Source Sync reads one and puts every `aart.yaml`
and `aart.json` it finds through the parser *and* the compiler a Registry uses. A manifest that
passes here parses and compiles to the package `aart registry scan` would accept, and the check
prints the coordinate it compiled to:

```
ok    github-mcp/aart.yaml  ->  mcp/github-mcp@0.1.0
```

It is the command to run in a loop while editing; `--json` makes the verdict machine-readable.

## Maintaining a registry

A registry is an ordinary Git checkout. Maintainer mutations prepare reviewed files and stop. The
explicit `registry publish --yes` flow runs every publisher gate and creates the listed commit, and
stops there. `registry push --branch NAME` then pushes that commit to a review branch — never the
registry's default branch, which is refused by name, because a subscriber reads the default branch
and only a merge should change what it can install. Merging is the reviewer's work, on the forge.
An empty Git repository is not a registry until its `aart-registry.json` marker exists.

AART reaches every remote by running system Git, with an allowlisted environment rather than the
operator's. If a repository clones at a shell prompt but not through AART, the environment is where
to look: [the environment AART gives Git](docs/configuration/git-environment-v1.md) lists what is
passed, what is dropped, and what to configure instead — `https_proxy` is dropped, and behind a
proxy that is the whole failure.

`registry init` turns an empty checkout into a registry: the two JSON markers, a `.gitignore`,
the quality workflow, a `README.md` describing the registry it just made, and a `.aart-version` pinning the AART
that created it. Those last two are written only when absent — they are the files
you own afterwards, and AART never compares or overwrites them. The workflows and the JSON are
managed: hand-edit one and `init` refuses the registry.

The generated workflows need no configuration to run on github.com. To run them inside a company,
set repository variables — no file in the registry changes. See
[Rolling out AART on GitHub Enterprise Server](docs/ci/github-enterprise-rollout.md).

```sh
# Create a registry
aart registry init --source . --source-id company --display-name "Company Registry"
aart registry init --source . --source-id company --display-name "Company Registry" --yes

# Author in a separate Source checkout, then scan and promote its reviewed Candidate
aart registry scan --help
aart registry promote --help

# Or copy foreign content the upstream has not packaged for AART
aart registry vendor skill code-review --source . \
  --url https://github.com/acme/prompts.git --ref main --path prompts/code-review \
  --artifact-version 1.0.0 --summary "Review code." \
  --profile claude --platform darwin

# Review, then finalize lock + build + validate + audit + one commit
aart registry publish --source .
aart registry publish --source . --yes

# Push the commit to a review branch, then open a pull request
aart registry push --source . --branch add-code-review
```

`vendor` is the foreign-repository path: it copies a file or subtree into this registry, records the
origin and pinned commit in `provenance.json`, and makes this registry the copy's owner. `revendor`
compares that copy with upstream and plans an explicit versioned refresh; validation and audit reject
a copied payload that drifts from its provenance.

For the complete path, use the [walked company-registry tutorial for Tabnine](docs/tutorials/company-registry-tabnine-v1.md).
The [vendoring tutorial](docs/tutorials/vendoring-v1.md) covers provenance and re-vendoring, and
[porting an MCP server](docs/tutorials/mcp-servers-into-the-registry.md) covers setup recipes.

An author team whose repository becomes a Source commits one `aart.yaml` beside each artifact. A
complete MCP example — Python stdio server, `requirements.txt` dependencies, one Keychain secret and
one per-harness setting — is [docs/examples/author-source/example-mcp/aart.yaml](docs/examples/author-source/example-mcp/aart.yaml),
held to what AART accepts by `tests/author_manifest_example_test.py`.

## Running inside a company

Every setting in this project's CI, and in the workflows `registry init` writes, is a GitHub Actions
variable whose default reproduces the public github.com run. A copy on a company GitHub Enterprise
Server instance configures itself from its settings page and never edits a workflow.

[Rolling out AART on GitHub Enterprise Server](docs/ci/github-enterprise-rollout.md) walks it in
order — put `aart-cli` on the instance, configure its CI, create a registry, configure the
registry's CI, point people at it — and lists every variable.

## Canonical package

A package lives at `<artifact-root>/<type>/<name>/` and contains `artifact.json` and `payload/`.
Its manifest defines SemVer, compatibility, installation, optional `setup`, `requires_aart`, and
`requires`. When it declares setup, `setup/installer.json` must be v2 and `SETUP.md` must be at
the package root; the modules a recipe may use are listed in the
[setup recipe reference](docs/protocol/setup-recipe-v2.md). An invalid hook, setup, dependency, symlink, or unknown file fails compilation
before lock, index, or installation.

```json
{
  "requires": [
    {"type": "skill", "name": "using-residues"}
  ]
}
```

`aart.lock.json` binds references to commits and digests. `aart.index.json` is a deterministic,
payload-free consumer projection. Both are generated and must pass their gates before publication.

## Interface

```text
aart author init|check
aart source add|list|sync|remove|resubscribe|health
aart marketplace list|search|health|install|update|uninstall|status|setup|receipt
aart doctor
aart reset
aart registry init|collection|scan|promote|adopt|check-upstream|discover|format|vendor|vendor-batch|revendor|validate|lock|build|audit|publish|push|test|diff
aart security scan|show|verify|analyzers|suites
aart upgrade --wheel FILE | --source-checkout DIR
```

Running `aart` without a subcommand on a TTY opens the human-oriented TUI (curses or text
fallback). The TUI submits the same canonical requests as flag mode; it is not a second command
engine.

`aart reset` is the CLI-only factory reset. It lists the exact AART-owned per-user configuration,
managed state and cache paths, then requires two different typed confirmations. It never removes
projects, harness files, organization policy or credentials owned by another application.

## Verification

```sh
python -m unittest
git diff --check
```

The manual walks are [the TUI walkthrough](docs/testing/TUI_MANUAL_WALKTHROUGH.md) and
[the command-line walkthrough](docs/testing/END_TO_END_ACCEPTANCE.md); what they find is tracked in
[manual acceptance](docs/testing/manual-acceptance.md).

## Development dependencies and what the quality gates run

**The installed runtime has no dependencies.** `dependencies = []` in `pyproject.toml`, standard
library only — that is a design rule, not an accident, and the gates below exist partly to keep it
true. Everything in this section is developer and CI tooling that a user of `aart` never installs.

Install them into a virtual environment, so nothing lands in the system interpreter:

```sh
python3 -m venv .venv
```

```sh
source .venv/bin/activate
```

```sh
poetry install --with dev
```

Or, with pip and no Poetry — which is what CI runs:

```sh
python scripts/dev_tools.py install
```

Both install the same versions: Poetry decides what they are, in `pyproject.toml` and
`poetry.lock`, and `scripts/dev_tools.py` carries the lock's pins to pip. The second route exists
because Poetry cannot be pointed at a per-fork internal index — it takes an install source only
from a block inside `pyproject.toml` — while pip reads `PIP_INDEX_URL` and always could. Behind an
internal index, set `PIP_INDEX_URL` and use the second command.

`.venv/` is already in `.gitignore`. Activate it in every new shell before running the gates or
`scripts/packaging_check.py`; `deactivate` leaves it. If `python3 -m venv` fails with an
`ensurepip` error, that interpreter's venv support is broken — use another one, for example
`python3.11 -m venv .venv`.

Without these tools six of the ten gates cannot run. `scripts/quality.py` says so before it starts,
names the ones that are missing, and prints the install command; the other four — `unit`,
`integration`, `validate`, `docs-check` — need nothing but Python and can be run on their own.

| Package | Constraint | Used for |
|---|---|---|
| `ruff` | `0.16.4` | formatting and linting — the `format-check` and `lint` gates. Pinned exactly: a formatter that changes its mind between two versions fails the gate on a file nobody edited |
| `mypy` | `^1.11` | the `typecheck` gate |
| `coverage` | `^7.6` | the `coverage` gate, branch coverage with `fail_under = 82` |
| `poetry-core` | `2.4.0` | the build backend, at the exact version `[build-system]` pins. Present in the environment so an offline editable install has a backend to build with |

Tests are **stdlib `unittest`** — there is no test-runner dependency. The wheel is built by
Poetry, wrapped by `scripts/build_wheel.py`; see
[docs/release/wheel-reproducibility-v1.md](docs/release/wheel-reproducibility-v1.md) for what that
wrapper holds and why building now needs Poetry on the machine.

### The ten gates

`python scripts/quality.py` runs all ten, each in a temporary cache directory with
`PYTHONDONTWRITEBYTECODE=1`, stopping at the first failure. `make quality` is a wrapper around
the same script; CI calls the script directly, because a CI image is not obliged to carry GNU Make
and a real one did not. Run a single gate with `make <gate>`.

| Gate | Command | Depends on |
|---|---|---|
| `format-check` | `ruff format --check agent_artifacts tests scripts` | `ruff` |
| `lint` | `ruff check agent_artifacts tests scripts` | `ruff` |
| `typecheck` | `mypy` | `mypy` |
| `unit` | `unittest discover -s tests -p "*_test.py"` | stdlib |
| `integration` | `unittest discover -s tests -p "*e2e_test.py"` — drives the real CLI over real trees | stdlib |
| `validate` | `scripts/validate.py` | stdlib |
| `coverage` | `coverage run --branch --source=agent_artifacts` over the unit suite, then `coverage report` | `coverage` |
| `packaging-check` | `scripts/packaging_check.py` — builds the wheel and inspects it | stdlib |
| `docs-check` | `scripts/docs_check.py` | stdlib |
| `secret-shape-check` | `scripts/secret_shape_check.py` — refuses credential-shaped literals anywhere in the tracked tree, so the repository stays pushable to an instance with push protection on | stdlib |

Four of the ten — `unit`, `integration`, `validate`, `docs-check` — need nothing installed beyond
Python itself.

One more gate exists that the full run does not include:

| Gate | Command | Depends on |
|---|---|---|
| `release-bump` | `unittest` over the release policy, release, packaging and install-command tests | stdlib |

It is selectable by name and deliberately outside `make quality`, because every module it names is
already discovered by `unit` and the full run would prove one thing twice. It exists for the release
pull request, which is gated on what it changes rather than on everything (INV-096); see
[`docs/ci/workflows-v1.md`](docs/ci/workflows-v1.md).

## Releasing

**Merge a pull request whose title says what kind of change it is. Later, merge the release pull
request that Release Please keeps open.** That is the release.

Nobody edits a version. Nobody writes a changelog entry. Nobody pushes a tag or presses a button.
The one decision left to a person is the one a machine has no business making: *when* the
accumulated changes should become a release.

### What a pull request title has to say

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
[`release-please-config.json`](release-please-config.json), which is also where the `0.x` bumping
rules are turned off so that `feat` means minor and `!` means major at every version.

Locally:

```sh
python scripts/conventional_title.py "feat(tui): add a screen"
```

### What happens after the merge

Release Please reads the accumulated commits on `main` and keeps **one** pull request open: the
next version, the generated `CHANGELOG.md` entry, and the version written into `pyproject.toml`,
`agent_artifacts/__init__.py` and this README. It updates that same pull request as more changes
land, rather than asking anyone for a version-bump PR.

Merging it is the release: the tag and the GitHub Release are created, and the release run builds the wheel,
verifies it against the tag and attaches it.

Nothing merges that pull request for you. Automating the arithmetic is not automating the
decision; auto-merge is a policy this repository has deliberately not turned on.

### What the release run proves

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

### One version, written by one thing

`agent_artifacts/__init__.py` holds the only version literal. `runtime_contract.EXECUTABLE_VERSION`
parses it, the release engine rewrites it and `pyproject.toml`, and nothing compares any of them to
anything, because nothing can disagree. This README names no release: it writes `X.Y.Z`, and the
exact commands come from `scripts/install_commands.py` and the release page.

### The workflow is read from the tag, not from `main`

This is the part that catches people. GitHub loads workflow files from the ref
that triggered the run, so a release runs `release.yml` **as it was at the tag**. A fix merged to
`main` after tagging is not in that run, and re-running the failed job replays the same commit
rather than picking the fix up. Move the tag and publish again:

```sh
git tag -f vX.Y.Z main && git push -f origin vX.Y.Z
```

Re-publishing is safe: the attach step replaces an asset of the same name instead of colliding
with it.

## License

AART is released under the [MIT License](LICENSE). Free for any use, including commercial, with no
obligation beyond keeping the copyright notice and the warranty disclaimer. The software is provided
as is, with no warranty and no liability on the author.

Copyright (c) 2026 Michał Filek. From Poland with <3
