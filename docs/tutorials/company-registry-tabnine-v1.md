# Standing up your first company registry, for Tabnine

From an empty Git repository to a colleague running `aart-cli consume install` and finding the
skill in their `.tabnine/` directory. Every command below was executed before this document was
written; the outputs quoted are real. Where something was not walked, it says so.

The examples use `company` as the registry id and `tabnine` as the profile throughout. Substitute
your own registry id; keep the profile.

**What you need**

- AART installed on your machine. `aart-cli --version` must print a version.
- A Git host you can push to — GitHub Enterprise, GitHub, anything reachable over HTTPS or SSH.
- Somewhere to put a new repository, and permission to create it.
- The URL of at least one existing company repository that holds material worth sharing. It does
  **not** need to know anything about AART. That is the point of most of this document.

**What AART does with Git**

Maintainer mutations stop after writing reviewed files. The explicit `maintain registry publish --yes`
workflow is the one exception: it runs the publisher gates and creates the listed commit. It never
pushes. AART also never handles credentials: it runs system Git, so if `git clone` works at your
prompt, AART works, and if it does not, fix it in Git.

---

## 1. Create the registry repository

Create an empty repository on your Git host — call it `agent-registry` — then clone it:

```sh
git clone https://ghe.company.example/platform/agent-registry.git
cd agent-registry
```

If you would rather start locally and add the remote later:

```sh
mkdir agent-registry && cd agent-registry
git init -b main .
```

**The directory must be a Git checkout before the next step.** Run `aart-cli maintain registry init` anywhere
else and it refuses:

```text
error: registry mutation requires a writable local Git checkout
```

## 2. Initialize the registry

Every mutating AART command runs twice: once to show you what it would do, once with `--yes` to do
it. Look at the first output before you type the second.

```sh
aart-cli maintain registry init --source . --source-id company --display-name "Company AART Registry"
```

```text
Review canonical Maintainer action: init
  Workspace: /path/to/agent-registry
  Review digest: sha256:209d2da8…
  Mutation: yes, only on Finalize
  - added: .gitignore
  - added: .github/workflows/aart-cli-registry.yml
  - added: aart-cli-registry.json
  - added: aart-cli-source.json
  AART will not commit or push; review the working-tree diff afterward.
```

```sh
aart-cli maintain registry init --source . --source-id company --display-name "Company AART Registry" --yes
```

`--source-id` is the identity every artifact coordinate starts with — your colleagues will type
`company/skill/release-evidence`. It is stable; changing it later changes every coordinate.
The generated `.gitignore` excludes AART caches, build output, and the project/user harness targets
used by the built-in profiles (`.aart-cli/`, `.claude/`, `.tabnine/`, `.opencode/`, `.vibe/`,
and `.mcp.json`), so an acceptance install inside the checkout does not pollute the next publish.

The marker it writes declares which AART versions may read this registry:

```json
{"requires_aart": {"min_inclusive": "0.1.0", "max_exclusive": "1.0.0"}, …}
```

The default is derived from the AART you ran, so it always contains it. Widen it with
`--minimum-version` if colleagues are on older builds — but only to a version that can actually read
what you publish.

Commit this before going further. It is the point where an empty repository becomes a registry.

```sh
git add -A && git commit -m "Initialize the company AART registry"
```

## 3. Adopt artifacts from a repository

Content enters a registry in one way: by adopting a manifest. Your company already has useful
material — a prompt somebody keeps pasting into Slack, a checklist in a platform-team repo, a
monorepo of MCP servers. Give each one an `aart-cli.yaml` beside it in that repository (see
[writing an artifact](../authoring/authoring-an-artifact-v1.md)), and commit it there. The
manifest names the artifact and its kind; it carries no version, because the registry assigns
those.

Then read the repository from your registry checkout. The first run only reports what the
manifests compile to:

```sh
aart-cli maintain upstream adopt --source . --url https://ghe.company.example/platform/shared-tools.git --ref main
```

Adopt the ones you want, by the coordinates that review printed:

```sh
aart-cli maintain upstream adopt --source . --url https://ghe.company.example/platform/shared-tools.git --ref main --artifact skill/release-evidence@1.0.0 --artifact guideline/branch-conventions@1.0.0 --yes
```

Each adopted version is a self-contained copy pinned to the commit it was read at, with its
provenance recorded beside it. The first approved version of an artifact is `1.0.0`; every later
approved change raises the version by the registry's own count, never by hand.

## 3b. Grouping artifacts so a colleague installs them in one command

The word for a group of artifacts is a **collection**. Compose one only from artifacts this registry
already holds:

```sh
aart-cli maintain registry collection platform-baseline --source . \
  --summary "What every platform-team repository starts with." \
  --include skill/release-evidence \
  --include guideline/branch-conventions
```

The review shows the canonical `collections/platform-baseline.json` it will add. Finalize the same
digest with `--yes`, or use the Maintainer TUI's **Author collection** flow for the same name,
summary, and member selection. Both interfaces refuse unknown members before writing anything.

```sh
aart-cli maintain registry collection platform-baseline --source . \
  --summary "What every platform-team repository starts with." \
  --include skill/release-evidence \
  --include guideline/branch-conventions --yes
```

Collections are compiled into the index. `maintain registry lock` validates their selectors before it writes
the lock, so a malformed or hand-written collection is rejected at the first publishing step. A
consumer can then install the baseline in one command:

```sh
aart-cli consume install company/collection/platform-baseline --profile tabnine --yes
```
## 4. Write an artifact of your own

Author new material in a separate upstream checkout. Add an explicit `aart-cli.yaml` or `aart-cli.json` beside
the payload, following the [native Upstream contract](../protocol/native-source-v1.md) and the
[example MCP upstream](../examples/author-source/example-mcp/aart-cli.yaml), then commit the checkout.
From the Registry checkout, scan that exact revision and promote the reviewed Candidate:

```sh
aart-cli maintain upstream scan --help
aart-cli maintain candidate promote --help
```

`scan` never changes the Registry. `promote` re-observes the clean pinned upstream checkout and writes
only the exact Candidate and evidence reviewed by the maintainer. The Registry stores the compiled
canonical package; it is not the artifact's authoring workspace.

## 5. Publish one reviewed cycle

Publishing is one command. First review the exact generated files, publisher checks, commit subject,
and every path Git would include:

```sh
aart-cli maintain registry publish --source .
```

Then finalize the reviewed cycle:

```sh
aart-cli maintain registry publish --source . --yes
```

The command prepares the shared publication gates, rebuilds `registry/index.json` and
`registry/snapshot.json` from approved records under `registry/versions/`, validates and audits
that projected snapshot, then writes the reviewed changes and creates one commit. A failed gate
stops before the commit. It never pushes.

Approved version records already carry their pins; `lock` writes no separate lock file. Standalone
`build` derives the catalogs from those records, and `publish` reviews and commits its changes in
one operation.

Every pre-existing Git change is listed alongside the generated files because finalization uses
`git add -A`. Keep unrelated work out of the registry checkout. Use `--message TEXT` to state the
commit subject; otherwise AART derives one from the compiled index. Re-running an unchanged,
already-clean registry reports that there is nothing to commit.

## 6. Check it before anyone else sees it

`maintain registry publish` already runs strict compiled validation and the audit before committing. CI
should independently verify what history contains:

```sh
aart-cli maintain registry validate --source .
aart-cli maintain registry build --source . --check
aart-cli maintain registry audit --source .
```

`build --check` fails when the committed index or snapshot does not match the approved versions.
The audit warns about every version promoted from a checkout on your machine, and every version
adopted from a branch that is not its upstream's default branch. The Registry's CI runs it as
`aart-cli maintain registry audit --source . --for-default-branch`. That refuses both, and every
version `upstream adopt` did not record as coming from the upstream's default branch, so none of
them reach the branch other people install from (INV-286, INV-289). The upstream's default branch
is the one its Git host names, not always `main`. Make that check required on the default branch. Push the commit,
open a pull request, and review it like any other repository.
## 7. Keeping an adopted copy current

Ask whether the repository has moved since a version was adopted. Without `--yes` this writes
nothing:

```sh
aart-cli maintain upstream check --source . skill/release-evidence@1.0.0
```

It answers `unchanged`, `changed`, `missing`, `unreachable` or `invalid`. A repository AART could
not read is never reported as unchanged, so this is safe to run in a scheduled job. When it says
`changed`, review the new version it would adopt, then run the same command with `--yes`. Then
publish the reviewed registry cycle as in section 5.

## 8. The consumer side — what a colleague runs

They need AART installed and nothing else. In their project:

```sh
cd ~/work/some-project

aart-cli consume registry add \
  --alias company \
  --kind git \
  --location https://ghe.company.example/platform/agent-registry.git \
  --ref main \
  --default
```

```text
registry added: company; snapshot published; default=yes
```

`consume registry add` clones, compiles and validates the whole snapshot before it saves anything, so a broken
registry fails here rather than halfway through an install.

```sh
aart-cli consume list
```

```text
registry company [healthy] git https://ghe.company.example/platform/agent-registry.git
company/guideline/branch-conventions@1.0.0 [healthy] How we name and merge branches. origin=https://ghe.company.example/platform/shared-tools.git@3706c2a…:packages/branch-conventions
company/skill/release-evidence@1.0.0 [healthy] Evidence checklist for a release. origin=https://ghe.company.example/platform/shared-tools.git@3706c2a…:packages/release-evidence
```

Every row carries the origin it was adopted from, so a colleague can see where a skill actually
came from without opening the registry.

Install — review, then finalize:

```sh
aart-cli consume install company/skill/release-evidence --profile tabnine
```

```text
Review consumer action
  Action: Install
  Scope: project
  Requested mode: copy
  Review digest: sha256:1ea04e2e…
  Registry freshness: company is healthy; origin matched; snapshot published 7s ago
  - company/skill/release-evidence@1.0.0#tabnine/project
    trust/security: local; unknown (not-scanned)
    digests: manifest=sha256:cf9ac726…; object=sha256:6a944c55…
    destination: /home/you/work/some-project/.tabnine/agent/skills/release-evidence
Reviewed only; re-run with --yes to apply this exact plan.
```

```sh
aart-cli consume install company/skill/release-evidence --profile tabnine --yes
aart-cli consume install company/guideline/branch-conventions --profile tabnine --yes
```

### Where the files land for Tabnine

Walked, not quoted from a design document:

```text
.tabnine/agent/skills/release-evidence/SKILL.md
.tabnine/agent/skills/release-evidence/LICENSE
.tabnine/agent/skills/release-evidence/references/verification-checklist.md
.tabnine/guidelines/branch-conventions.md
.aart-cli/manifest.json
```

| Artifact kind | Where it goes in a project | Where it goes at user scope | Walked |
|---|---|---|---|
| `skill` | `.tabnine/agent/skills/<name>/` | `~/.tabnine/agent/skills/<name>/` | yes |
| `guideline` | `.tabnine/guidelines/` | `~/.tabnine/guidelines/` | yes |
| `memory` | `TABNINE.md` at the project root | `~/.tabnine/agent/TABNINE.md` | no |
| `mcp` | `.tabnine/agent/settings.json`, key `mcpServers` | `~/.tabnine/agent/settings.json`, key `mcpServers` | yes — project and user filesystem contract |
| `hook` | `.tabnine/agent/hooks/<name>/` plus `hooks.BeforeTool`/`AfterTool`/`SessionEnd` in `.tabnine/agent/settings.json` | the same under `~/.tabnine/agent/` | no |

The user-scope Skill, memory and hook locations follow Tabnine CLI's published documentation
([Agent Skills](https://docs.tabnine.com/main/getting-started/tabnine-cli/features/agent-skills),
[hook configuration](https://docs.tabnine.com/main/getting-started/tabnine-cli/features/hooks/configuration)).
They have not been walked against the company build.

`.aart-cli/manifest.json` is AART's own record of what it installed. Commit it if you want
the project's artifact set to be reproducible for the next person who clones; it contains no
secrets.

**MCP location follows the company build, not a generic documentation page.** That build surfaced
an AART-installed server from project `.tabnine/agent/settings.json` as `disconnected`: it parsed
the `mcpServers` entry and reached the server runtime, where startup then failed. Other servers
authored in that same file work. AART therefore targets `.tabnine/agent/settings.json` for project
scope and `~/.tabnine/agent/settings.json` for user scope. The real CLI regression installs the
same server into both, reports both current, and uninstalls either without touching the other.

Published Tabnine documentation names standalone `mcp_servers.json` files, and another machine has
one at user scope. Whether the target company build also reads those files remains unmeasured; that
cannot displace the target it demonstrably reads. The `disconnected` server itself is a separate
runtime/startup problem and this file-target repair does not claim to fix it.

### Day-to-day

```sh
aart-cli consume status --profile tabnine          # what is installed, and is it current
aart-cli consume update --profile tabnine --yes    # pull newer versions from the registry
aart-cli consume registry sync --alias company                # refresh the snapshot explicitly
aart-cli consume uninstall company/skill/release-evidence --profile tabnine --yes
```

`list` and `status` never fetch. The snapshot only moves when someone runs `consume registry sync`; `consume update`
changes installed artifacts using that snapshot, so a colleague's environment cannot change under them because a maintainer pushed.

Uninstall removes what it installed and nothing else — walked: after uninstalling the skill,
`.tabnine/agent/skills/release-evidence/` is gone and `.tabnine/guidelines/branch-conventions.md`,
installed separately, is untouched.

---

## What was verified, and how

The original walkthrough was executed against a wheel in a disposable virtual environment on
2026-08-16, using real local Git repositories. Commands and role names were updated for CP-32 on
2026-10-17 and checked against the current parser and focused repository tests. This update does
not claim a new live run against your Enterprise host. Sections 3 and 7 now use
`maintain upstream adopt` and `maintain upstream check` for manifest-based ingestion.

Two things are **not** verified and are marked where they appear:

- The `memory`, `mcp` and `hook` rows of the destination table. They come from the Tabnine profile
  definition in the AART source, not from a walk.
- Everything about your Git host: URLs, credentials, and whether `git clone` works from your
  machine. AART runs system Git with a restricted environment — notably `https_proxy` is **not**
  passed through. If a repository clones at your shell prompt but not through AART, read
  [the environment AART gives Git](../configuration/git-environment-v1.md) first; behind a proxy,
  that is the entire failure.

## Where to read more

- [Maintaining a registry](../registry/maintaining-a-registry-v1.md) — adoption, Registry-owned
  versions and Collections.
- [The registry protocol](../protocol/registry-v1.md) — the file formats, if you are automating
  against them.
