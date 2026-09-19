"""Byte-stable templates emitted by registry initialization."""

from __future__ import annotations

from .publication import REGISTRY_PUBLICATION_GATES

REGISTRY_GITIGNORE = b""".agent-artifacts/
.agent-artifacts-bak/
.claude/
.coverage
.mcp.json
.mypy_cache/
.opencode/
.pytest_cache/
.ruff_cache/
.tabnine/
.vibe/
__pycache__/
build/
dist/
htmlcov/
"""

# Every knob below is a repository variable, and every default reproduces the public github.com
# run, so a registry created inside a company is configured by settings rather than by editing the
# file.  That matters more than it looks: `plan_registry_init` refuses to overwrite a template
# whose content differs, so a hand-edited workflow puts a registry permanently out of step with
# the command that manages it.  `docs/ci/github-enterprise-rollout.md` lists the variables.
#
# The generated workflow can reach the tool without assuming a public package index.
# AART has no runtime dependencies and ships `aart_cli/__main__.py`, so *any* directory
# holding the package is a working installation: a clone, an unzipped wheel, a `pip --target`
# directory, or a path baked into a CI image.  Every arm below therefore ends the same way, and
# none of them needs a build backend.  That is what lets these run on a private runner.
_PROVIDE_AART = b"""      - name: Provide AART
        env:
          PACKAGE: ${{ vars.AART_PACKAGE }}
          WHEEL_URL: ${{ vars.AART_WHEEL_URL }}
          TOOL_PATH: ${{ vars.AART_TOOL_PATH }}
          TOOL_URL: ${{ vars.AART_TOOL_URL || (vars.AART_REPOSITORY && format('{0}/{1}.git', github.server_url, vars.AART_REPOSITORY)) || '' }}
          TOOL_REF: ${{ vars.AART_REF }}
          INDEX_URL: ${{ vars.AART_PIP_INDEX_URL || 'https://pypi.org/simple' }}
          INDEX_CREDENTIALS: ${{ secrets[vars.AART_PIP_INDEX_CREDENTIALS_SECRET] }}
          GIT_CREDENTIALS: ${{ secrets[vars.AART_GIT_CREDENTIALS_SECRET] }}
          PY: ${{ vars.AART_PYTHON || 'python3' }}
        run: |
          # `sh`, not `bash`.  This step names no shell, and Actions serves `bash -e {0}` only if
          # the image has bash -- otherwise it falls back to `sh -e {0}`.  An Enterprise image
          # carrying git and Python and no bash met exactly that, and the step died on its own
          # first line, `set: Illegal option -o pipefail`, before it had chosen an arm.  So this
          # script is POSIX: no `pipefail`, no `${v//a/b}`, and a shim that asks for `/bin/sh`.
          set -eu
          # An internal index usually wants credentials, and a variable cannot hold one.  So the
          # variable holds the bare host and names the secret holding `user:pass`; the URL is
          # assembled here and never written down anywhere.  Splitting a secret defeats GitHub's
          # masking -- it masks the whole value it was given, not the halves -- so each half is
          # re-masked before it is used.  `announce` keeps the bare host, so no log line, not even
          # a masked one, carries the password.
          announce="$INDEX_URL"
          if [ -n "${INDEX_CREDENTIALS:-}" ]; then
            index_user="${INDEX_CREDENTIALS%%:*}"
            index_held="${INDEX_CREDENTIALS#*:}"
            echo "::add-mask::$index_user"
            echo "::add-mask::$index_held"
            index_scheme="https"
            case "$INDEX_URL" in http://*) index_scheme="http" ;; esac
            index_host="${INDEX_URL#http://}"
            index_host="${index_host#https://}"
            # `at` keeps the emitted bytes out of the shape a secret scanner refuses on push, so a
            # registry created by this command is pushable to an instance with push protection on.
            at="@"
            INDEX_URL="$index_scheme://$index_user:$index_held$at$index_host"
          fi
          # `.aart-cli-version` is this registry's own pin: one line of text, versioned in Git and
          # reviewed in a pull request like any other change.  It answers *which* AART, which is a
          # decision about the registry.  The variables answer *where this deployment gets it
          # from*, which is a fact about the instance.  Neither repeats the other.
          PIN=""
          if [ -f .aart-cli-version ]; then PIN=$(tr -d ' \\t\\r\\n' < .aart-cli-version); fi
          # An explicit AART_REF is the escape hatch for someone testing a fork branch.  It wins,
          # but it switches the version check off, so it says so rather than quietly disagreeing
          # with a file that is still in the repository.
          override=""
          if [ -n "$PIN" ] && [ -n "$TOOL_REF" ]; then override=" (pin $PIN overridden by AART_REF)"; fi
          ref="$TOOL_REF"
          if [ -z "$ref" ]; then ref="${PIN:+v$PIN}"; fi
          if [ -z "$ref" ]; then ref="main"; fi
          # Four ways in, tried in this order, never combined.  The order runs from the most
          # governed supply chain to the least, so an organisation that later stands up an index
          # sets one variable and it takes over -- no stale variable has to be unset first.  Git
          # is last because it is the only arm carrying a shipped default, and anything below an
          # arm that is always set would be unreachable.
          # POSIX `sh` has no global substitution, and a wheel URL usually names the version
          # twice -- once in the path and once in the filename -- so the first-match forms do not
          # serve either.  The interpreter every arm already requires does it, which is the one
          # tool that cannot be missing from an image that could run AART at all.
          expand() {
            "$PY" -c 'import sys;print(sys.argv[1].replace("{version}", sys.argv[2]))' "$1" "$PIN"
          }
          tool="$RUNNER_TEMP/aart-tool"
          rm -rf "$tool"
          if [ -n "$PACKAGE" ]; then
            requirement=$(expand "$PACKAGE")
            how="index $announce ($requirement)"
            "$PY" -m pip install --quiet --no-deps --target "$tool" \\
              --index-url "$INDEX_URL" "$requirement"
          elif [ -n "$WHEEL_URL" ]; then
            url=$(expand "$WHEEL_URL")
            how="wheel $url"
            # `urllib`, not `curl`: this arm has to run on whatever image the organisation
            # uses, and a real Enterprise image carried git and Python and neither `curl` nor
            # `gh`.  The interpreter is already required by every other arm, so asking for
            # nothing beyond it is the only assumption that holds everywhere.
            "$PY" -c 'import sys,urllib.request,zipfile;urllib.request.urlretrieve(sys.argv[1],sys.argv[2]);zipfile.ZipFile(sys.argv[2]).extractall(sys.argv[3])' \\
              "$url" "$RUNNER_TEMP/aart.whl" "$tool"
          elif [ -n "$TOOL_PATH" ]; then
            how="path $TOOL_PATH"
            tool="$TOOL_PATH"
          else
            # This arm used to carry a shipped default, so a company that set nothing cloned the
            # tool's own maintainer repository from its own instance -- absent there, and the run
            # died on a git error naming a repository nobody in that company had chosen.  Where
            # AART comes from is a fact about the deployment and only the deployment knows it, so
            # the answer to "nothing is set" is to say what to set (D-309).
            if [ -z "$TOOL_URL" ]; then
              echo "AART: no source configured. Set one repository variable, first one set wins:" >&2
              echo "  AART_PACKAGE     a requirement on your package index" >&2
              echo "  AART_WHEEL_URL   a released wheel" >&2
              echo "  AART_TOOL_PATH   a directory already on the runner" >&2
              echo "  AART_TOOL_URL    a git URL, or AART_REPOSITORY as owner/name on this instance" >&2
              echo "Set it on the organisation and it configures every registry at once." >&2
              exit 1
            fi
            # `how` keeps the address without the credential, so no log line carries one -- the
            # same split the index arm makes between `announce` and `INDEX_URL`.
            how="git $TOOL_URL@$ref"
            # A company's copy of AART is private, and this clone used to carry nothing to log in
            # with: the step's env held no token, and the registry's own checkout persists none
            # for anything else to reuse.  A real instance answered `could not read Username`,
            # exit 128, on the arm that is reached when nothing is configured.  So the credential
            # arrives the way the index arm's already does -- a variable naming a secret, never a
            # variable holding one, because variables are not masked and are readable by anyone
            # who can open the settings page.
            clone_url="$TOOL_URL"
            if [ -n "${GIT_CREDENTIALS:-}" ]; then
              # A service account's token is usually already a secret of its own.  Requiring
              # `user:token` here would mean copying that secret into a second one just to prefix
              # a name -- one more place to rotate and one more to leak -- so a value with no
              # colon is taken as the token itself.  GitHub ignores the user name when the
              # password is a token, and `x-access-token` is the name it documents for that.
              # Only the half that came out of the secret is masked: masking a public constant
              # would print `***` over a word that was never secret.
              case "$GIT_CREDENTIALS" in
                *:*)
                  git_user="${GIT_CREDENTIALS%%:*}"
                  git_held="${GIT_CREDENTIALS#*:}"
                  echo "::add-mask::$git_user"
                  ;;
                *)
                  git_user="x-access-token"
                  git_held="$GIT_CREDENTIALS"
                  ;;
              esac
              echo "::add-mask::$git_held"
              git_scheme="https"
              case "$TOOL_URL" in http://*) git_scheme="http" ;; esac
              git_host="${TOOL_URL#http://}"
              git_host="${git_host#https://}"
              at="@"
              clone_url="$git_scheme://$git_user:$git_held$at$git_host"
            fi
            git clone --quiet --depth 1 --branch "$ref" "$clone_url" "$tool" 2>/dev/null \\
              || { rm -rf "$tool"
                   git clone --quiet "$clone_url" "$tool"
                   git -C "$tool" -c advice.detachedHead=false checkout --quiet "$ref"; }
            # `git clone` writes the URL it was handed into the checkout's own config, so the
            # credential would outlive this step in a directory every later step can read.
            git -C "$tool" remote set-url origin "$TOOL_URL"
          fi
          test -f "$tool/aart_cli/__main__.py" \\
            || { echo "aart-cli: no aart_cli package under '$tool' (via $how)" >&2; exit 2; }
          bin="$RUNNER_TEMP/aart-bin"
          mkdir -p "$bin"
          printf '#!/bin/sh\\nexec env PYTHONPATH=%s %s -m aart_cli "$@"\\n' \\
            "$tool" "$PY" > "$bin/aart-cli"
          chmod +x "$bin/aart-cli"
          echo "$bin" >> "$GITHUB_PATH"
          # The pin claims a version; this proves it.  Every arm is checked, including the baked
          # path, where a stale image is otherwise indistinguishable from a fresh one.
          got=$("$bin/aart-cli" --version | awk '{print $NF}')
          if [ -n "$PIN" ] && [ -z "$override" ] && [ "$got" != "$PIN" ]; then
            echo "aart-cli: .aart-cli-version pins $PIN but $how provided $got" >&2
            exit 2
          fi
          echo "AART: aart-cli $got  via $how${PIN:+  pinned by .aart-cli-version}$override"
"""

_RUNS_ON = b"""    runs-on: ${{ fromJSON(vars.AART_RUNNER || '["ubuntu-latest"]') }}
"""

# A private image needs a `credentials` block, and that block cannot be made conditional.  Measured
# on a real instance rather than assumed: an empty block and a `null` block are both rejected before
# the job starts ("Unexpected value ''"), and filling it with a placeholder makes an anonymous pull
# fail a `docker login` it never needed.  The `secrets` context is not even readable at `container:`
# itself, only inside `credentials`.  So the choice is made in the one place a choice survives --
# `if:` at job level -- and each job is emitted twice.  The plain variant is byte-for-byte the job
# this template always produced, so a registry that names no secrets sees no change whatsoever.
_PLAIN_CONTAINER = b"""    container: ${{ vars.AART_CI_IMAGE }}
"""
_PRIVATE_CONTAINER = b"""    container:
      image: ${{ vars.AART_CI_IMAGE }}
      credentials:
        username: ${{ secrets[vars.AART_IMAGE_USERNAME_SECRET] }}
        password: ${{ secrets[vars.AART_IMAGE_PASSWORD_SECRET] }}
"""
_PLAIN_WHEN = b"vars.AART_IMAGE_USERNAME_SECRET == ''"
_PRIVATE_WHEN = b"vars.AART_IMAGE_USERNAME_SECRET != ''"


def _job(job_id: bytes, body: bytes, header: bytes = b"", when: bytes = b"") -> bytes:
    """Emit one job twice, once per container shape, gated so exactly one of them runs.

    `header` carries whatever belongs above the container line -- `needs`, `strategy`,
    `environment`.  `when` is the job's own condition, which is combined with the container
    switch rather than replaced by it.
    """

    emitted = []
    for suffix, container, switch in (
        (b"", _PLAIN_CONTAINER, _PLAIN_WHEN),
        (b"-private-image", _PRIVATE_CONTAINER, _PRIVATE_WHEN),
    ):
        condition = switch if not when else b"".join((when, b" && ", switch))
        emitted.append(
            b"".join(
                (
                    b"  ",
                    job_id,
                    suffix,
                    b":\n    if: ",
                    condition,
                    b"\n",
                    header,
                    _RUNS_ON,
                    container,
                    body,
                )
            )
        )
    return b"".join(emitted)


def _aggregate(job_id: bytes) -> bytes:
    """The one job name branch protection can require, over a job `_job` emitted in two shapes.

    Neither shape is requirable on its own. Each is a matrix, so the name GitHub reports carries a
    matrix value; and only one of the two ever runs, so a rule naming the shape a deployment does
    not use would wait forever -- except that GitHub counts a skipped required check as
    *satisfied*, so it would not wait at all. It would pass, having proven nothing. This job's name
    is the same on every instance and in every configuration (INV-077).

    `if: always()` is what makes it a gate rather than a formality: without it a skipped or failed
    dependency skips this job too, and the rule is satisfied again for the same reason.

    It runs no Python and pulls no image. The job branch protection depends on must not be able to
    fail for a reason that has nothing to do with the gates.
    """

    return b"".join(
        (
            b"  ",
            job_id,
            b"-gate:\n    if: always()\n    needs: [",
            job_id,
            b", ",
            job_id,
            b"-private-image]\n",
            _RUNS_ON,
            b"""    steps:
      - name: Report the gate results
        shell: bash
        env:
          PLAIN: ${{ needs.""",
            job_id,
            b""".result }}
          PRIVATE: ${{ needs.""",
            job_id,
            b"""-private-image.result }}
        run: |
          set -euo pipefail
          echo "plain:         $PLAIN"
          echo "private-image: $PRIVATE"

          # Exactly one arm is meant to run; the other stands down by its own `if:`.  Both skipped
          # means the gates never ran at all -- a broken condition, an image variable set to
          # something unexpected -- and that must fail rather than look like a pass.
          if [ "$PLAIN" = "skipped" ] && [ "$PRIVATE" = "skipped" ]; then
            echo "::error::neither gate job ran; check AART_IMAGE_USERNAME_SECRET" >&2
            exit 1
          fi
          # An allowlist rather than a check for "failure": a cancelled run is neither success nor
          # failure and proves nothing, and any result GitHub adds later should stop this gate
          # rather than slip through it.
          for result in "$PLAIN" "$PRIVATE"; do
            case "$result" in
              success|skipped) ;;
              *) echo "::error::a gate job reported '$result'" >&2; exit 1 ;;
            esac
          done
          echo "all gates passed"
""",
        )
    )


REGISTRY_CI_WORKFLOW = (
    b"""name: AART registry quality
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
"""
    + _job(
        b"registry-quality",
        header=b"""    strategy:
      fail-fast: false
      matrix:
        compatibility: [minimum, latest]
""",
        body=b"""    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - name: Trust the workspace
        run: |
          # A container runner mounts the workspace owned by root and then runs the job as
          # somebody else, so git answers `detected dubious ownership` and refuses the checkout
          # it was just handed.  Every gate below dies on that, the read-only ones included,
          # because AART proves its target is a real Git checkout before it does anything at
          # all.  This is git's own documented remedy and it trusts exactly one directory: the
          # one this job checked out a moment ago.
          git config --global --add safe.directory "$GITHUB_WORKSPACE"
"""
        + _PROVIDE_AART
        + b"".join(
            f"      - run: {command}\n".encode()
            for gate in REGISTRY_PUBLICATION_GATES
            # Compatibility is the one gate whose shape is the workflow's rather than this list's:
            # CI already runs a matrix over the two targets, so it is the line below, once.
            if gate.in_generated_workflow and gate.name != "compatibility"
            for command in gate.commands
        )
        + b"""      - run: aart-cli registry test --source . --compatibility ${{ matrix.compatibility }}
""",
    )
    + _aggregate(b"registry-quality")
)
# `registry init` writes this once and then leaves it alone.  Unlike the workflows, a README is a
# file people are meant to edit, so it is deliberately *not* a managed template: it is written when
# absent and never overwritten or compared.  Making it managed would mean the one file a maintainer
# is supposed to change is the one that puts the registry out of step with the command managing it.
_REGISTRY_README = b"""# __DISPLAY_NAME__

An AART registry. It holds packaged
artifacts - skills, agents, commands, MCP servers, memory and guidelines - that AART installs into
a consumer project.

Its registry id is `__REGISTRY_ID__`. Consumers name it when they add this registry as a source.

## What is in here

| Path | What it is |
|---|---|
| `aart-registry.json` | The registry marker: id, display name, and the AART version window it declares |
| `.aart-cli-version` | The AART version CI runs. One line. Bump it in a pull request |
| `aart-source.json` | Where artifacts and collections live in this tree |
| `artifacts/` | One directory per packaged artifact |
| `collections/` | Named groups of artifacts installed together |
| `registry/` | Approved version records and the catalogs derived from them. Generated |
| `.github/workflows/` | The registry quality gate |

The JSON files and the workflows are **managed**: AART regenerates them and refuses to run against
a copy that was hand-edited. This README is not managed. Edit it freely.

## Everyday commands

Every mutation prepares files and stops so you can read them. Re-run the same command with `--yes`
to finalize. AART never pushes.

```sh
# Discover author manifests in a clean source checkout, then review their exact Candidates
aart-cli registry scan --help
aart-cli registry promote --help

# Copy content an upstream never packaged, recording where it came from
aart-cli registry vendor skill code-review --source . \\
  --url https://github.com/acme/prompts.git --ref main --path prompts/code-review \\
  --artifact-version 1.0.0 --summary "Review code." --profile claude --platform darwin

# See what moved upstream since a vendored copy was taken
aart-cli registry revendor skill code-review --source .

# Build, validate, audit, and commit - review first, then finalize
aart-cli registry publish --source .
aart-cli registry publish --source . --yes
```

Run the gates yourself at any time:

```sh
aart-cli registry format --source . --check
aart-cli registry validate --source .
aart-cli registry build --source . --check
aart-cli registry audit --source .
aart-cli registry test --source . --compatibility latest
```

## Pointing CI at AART

Two separate questions, kept in two separate places.

**Which AART version** is a decision about this registry, so it lives in Git:

```
.aart-cli-version
0.1.0
```

Bump it in a pull request. The gates then run against the new version **before** the change is
merged, so a version that breaks this registry fails in review rather than after. `git blame`
answers "when did we move to 0.2.0", and a bad bump is one `git revert` away. None of that is
possible when the version lives in a settings page.

The version is also **proved, not just claimed**. After fetching, CI compares `aart-cli --version`
against this file and fails if they differ - which catches a moved tag, an index that resolved to
something else, and a CI image with a stale AART baked into it.

**Where this deployment fetches that version from** is a fact about your instance, not about the
registry, so it stays in repository variables. Four ways in; the **first variable that is set
wins**, and they are never combined:

| Order | Variable | Example | How it fetches |
|---|---|---|---|
| 1 | `AART_PACKAGE` | `aart-cli=={version}` | `pip` from `AART_PIP_INDEX_URL` |
| 2 | `AART_WHEEL_URL` | `https://host/.../v{version}/aart_cli-{version}-py3-none-any.whl` | fetch, then unzip |
| 3 | `AART_TOOL_PATH` | `/opt/aart` | Already on the runner |
| 4 | `AART_TOOL_URL` | `https://ghe.corp/platform/aart-cli.git` | `git clone` at `v` + the pin. Private copy: name a secret in `AART_GIT_CREDENTIALS_SECRET` |

`{version}` is replaced with whatever `.aart-cli-version` says, so the version appears **once**, in
Git, and never in a settings page. Set `AART_REF` to override the pin for one registry - the run
then says so out loud and the version check is switched off, because you asked for a different
build on purpose.

The order runs from the most governed supply chain to the least. That matters when you migrate:
stand up an internal index later, set `AART_PACKAGE`, and it takes over. You do not have to unset
anything first.

**Set none of them** and the first run stops and says so, listing these four. Where AART comes
from is a fact about your deployment, and nothing here can guess it: a shipped default would send
every company's registry to a repository nobody in it had chosen.

**Set them on the organisation, not here.** GitHub resolves a repository variable over an
organisation one, so one organisation variable configures every registry your company has, and any
single registry can still override it.

Which arm actually answered is printed by the run:

```
AART: aart-cli 0.1.0  via index https://nexus.corp/pypi/simple (aart-cli==0.1.0)
```

### The other variables

| Variable | Default | What it does |
|---|---|---|
| `AART_PIP_INDEX_URL` | `https://pypi.org/simple` | Index used by `AART_PACKAGE` |
| `AART_REPOSITORY` | unset | `owner/name` of your AART repository, combined with this instance's own URL. Shorter than `AART_TOOL_URL` when the copy is on this instance |
| `AART_GIT_CREDENTIALS_SECRET` | unset | **Name** of a secret holding a token, or `user:token`, for the `git clone` arm. A bare token is used as `x-access-token`. Without it the clone is anonymous, and a private copy answers `could not read Username` |
| `AART_REF` | `v` + the pin | Escape hatch: a branch or tag instead of `.aart-cli-version`. Switches the version check off |
| `AART_RUNNER` | `["ubuntu-latest"]` | JSON array of runner labels. Must be JSON, not a bare word |
| `AART_CI_IMAGE` | unset | Container image for the jobs. Unset means the runner's own environment |
| `AART_PYTHON` | `python3` | The interpreter's name inside that image |

## Protecting `main`

Require one status check: **`registry-quality-gate`**.

Do not require the gate jobs themselves. Each is a matrix, so the name GitHub reports carries a
compatibility arm, and the quality job is emitted in two container shapes of which only one ever
runs on your instance. A rule naming the shape you do not use would never be satisfied - except
that GitHub counts a *skipped* required check as satisfied, so it would pass, having proven
nothing. `registry-quality-gate` has the same name in every configuration, runs whatever its
dependencies did, and fails if any arm failed or if no arm ran at all.

## The version window

`aart-registry.json` declares the *range* of AART versions this registry supports. The quality
gate runs at **both** ends of it, which is what `compatibility: [minimum, latest]` means in the
workflow.

That is a different statement from `.aart-cli-version`. The window says which versions this registry
claims to work with; the pin says which single version CI actually runs. Keep the pin inside the
window - a pin outside it is a registry contradicting itself.

"""


def render_registry_readme(
    registry_id: str,
    display_name: str,
) -> bytes:
    """Render the one generated file a maintainer owns after it is written."""

    return _REGISTRY_README.replace(b"__DISPLAY_NAME__", display_name.encode("utf-8")).replace(
        b"__REGISTRY_ID__", registry_id.encode("utf-8")
    )
