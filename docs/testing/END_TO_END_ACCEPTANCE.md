# AART end-to-end manual acceptance

## Purpose

This is the repeatable manual procedure for testing AART as a real product. It starts with author
repositories on Git hosting, carries their exact commits through Maintainer review into an approved
registry, and finishes with installation, update, repair and removal on a clean consumer machine.

The Product Specification remains the product authority. This procedure records how an operator
tests it. Findings are tracked in the first section of [`TODO.md`](../../TODO.md).

## System under test

```text
fork of obra/superpowers ─┐
                          ├─> AART test registry ─> Marketplace ─> consumer project
test MCP repository ─────┘
```

Use four repositories/directories with deliberately different responsibilities:

1. `aart-cli` — the AART checkout being tested.
2. `superpowers-aart-test` — a fork containing one or two explicit AART author manifests.
3. `aart-test-mcp` — a small self-contained MCP server with an explicit AART author manifest.
4. `aart-test-registry` — the reviewed registry consumers subscribe to.

Do not add manifests to every Superpowers skill in the first pass. One small Skill is enough to
prove discovery, compilation, promotion, installation and update. Expand only after that path is
green.

## Ground rules

- Use test Git repositories and test values only. Never enter a real token into a fixture or commit.
- Keep maintainer and consumer state in different test homes.
- Keep the consumer project outside all four source repositories.
- Commit every author change before Source Sync. Dirty author checkouts are intentionally refused.
- Review first; confirm only after reading the plan.
- Promotion is not publication. A consumer sees a change only after push, review and merge to the
  registry branch it follows.
- Record every unexpected result in the current section of `TODO.md` before fixing it.
- Perform one stage at a time. A failure blocks only the next stage that depends on it.

## Harness coverage for this pass

The author manifests may declare `claude`, `tabnine`, `opencode` and `codex` so one published
package reaches every intended compatibility boundary. That declaration is metadata, not proof that
AART can install into a harness.

- Claude and Tabnine are the currently measured canonical installation targets.
- OpenCode is an explicit no-write refusal until B-085/QA-011 is implemented.
- Codex is an explicit no-write refusal until B-086/QA-012 is implemented. Its native contract uses
  `.agents/skills`, layered `AGENTS.md` and TOML `mcp_servers` entries; it is not a Claude alias.
- The TUI currently has no harness selector and therefore exercises only its derived
  Claude/Tabnine target set.

Keep the OpenCode and Codex refusal checks in the pass: they prevent compatibility labels from
being mistaken for working installation adapters.

Suggested local variables use task-specific names:

```sh
export AART_CHECKOUT=/absolute/path/to/aart-cli
export AART_QA_ROOT=/absolute/path/to/aart-e2e-work
export AART_REGISTRY_CHECKOUT="$AART_QA_ROOT/aart-test-registry"
export AART_MAINTAINER_HOME="$AART_QA_ROOT/maintainer-home"
export AART_CONSUMER_HOME="$AART_QA_ROOT/consumer-home"
export AART_CONSUMER_PROJECT="$AART_QA_ROOT/consumer-project"
mkdir -p "$AART_MAINTAINER_HOME" "$AART_CONSUMER_HOME" "$AART_CONSUMER_PROJECT"
```

Run the checkout under test from another directory with this shape:

```sh
env HOME="$AART_CONSUMER_HOME" PYTHONPATH="$AART_CHECKOUT" \
  python3 -m agent_artifacts.cli --version
```

Do not export a replacement `HOME` for the whole terminal session. Apply the isolated home only to
the AART process being tested.

## Stage 1 — create and publish an empty registry

- [ ] Create an empty remote repository named `aart-test-registry`.
- [ ] Clone it to `$AART_REGISTRY_CHECKOUT`.
- [ ] Configure a test Git author in that checkout.
- [ ] Review registry initialization without `--yes` and confirm it writes nothing.
- [ ] Run the same command with `--yes`.

```sh
env HOME="$AART_MAINTAINER_HOME" PYTHONPATH="$AART_CHECKOUT" \
  python3 -m agent_artifacts.cli registry init \
  --source "$AART_REGISTRY_CHECKOUT" \
  --source-id aart-test-registry \
  --display-name "AART Test Registry"
```

After reviewing the output, repeat with `--yes`, then commit and push the initialized registry.
The remote `main` branch is now a valid empty consumer registry.

Checkpoint:

- [ ] The review made no filesystem change.
- [ ] Initialization wrote only registry-owned files.
- [ ] The empty registry passes `registry validate`.
- [ ] The initialized commit is present on remote `main`.

## Stage 2 — prepare the Superpowers author source

- [ ] Fork `obra/superpowers` as `superpowers-aart-test`.
- [ ] Choose one small Skill with a `SKILL.md` and limited supporting files.
- [ ] Add `aart.json` beside that `SKILL.md`.
- [ ] Commit and push the manifest before AART observes the source.

Minimal shape:

```json
{
  "schema": "aart.dev/skill/v1",
  "artifact": {
    "name": "superpowers-example",
    "kind": "skill",
    "version": "1.0.0"
  },
  "payload": {
    "include": ["SKILL.md"]
  },
  "compatibility": {
    "harnesses": ["claude", "codex"],
    "platforms": ["darwin", "linux"]
  }
}
```

Add every supporting file the Skill actually needs to `payload.include`. Do not use a broad glob
until the minimal package works; a narrow payload makes the review meaningful.

Checkpoint:

- [ ] The fork is clean at one real Git commit.
- [ ] Exactly one intended manifest is discoverable.
- [ ] No private file, token or machine path is committed.

## Stage 3 — prepare the MCP author source

- [ ] Create or fork `aart-test-mcp`.
- [ ] Keep its first version self-contained and deterministic.
- [ ] Make the stdio server answer `initialize`, `tools/list` and one harmless `tools/call`.
- [ ] Add `aart.json`, commit and push.

Minimal manifest shape:

```json
{
  "schema": "aart.dev/mcp/v1",
  "artifact": {
    "name": "test-mcp",
    "kind": "mcp",
    "version": "1.0.0"
  },
  "payload": {
    "include": ["server.py"]
  },
  "transport": {"type": "stdio"},
  "runtime": {"type": "python", "version": ">=3.11"},
  "launch": {"type": "python", "entrypoint": "server.py"},
  "compatibility": {
    "harnesses": ["claude", "codex"],
    "platforms": ["darwin", "linux"]
  }
}
```

Add setup and a test credential only after installation and process launch work without them. That
keeps a runtime failure distinguishable from a setup or Keychain failure.

Checkpoint:

- [ ] The MCP works directly from its author checkout.
- [ ] The checkout is clean at one real Git commit.
- [ ] Its first version has no network or secret requirement.

## Stage 4 — configure the maintainer machine

Start AART from the registry checkout with the isolated maintainer home:

```sh
cd "$AART_REGISTRY_CHECKOUT"
env HOME="$AART_MAINTAINER_HOME" PYTHONPATH="$AART_CHECKOUT" \
  python3 -m agent_artifacts.cli
```

In the TUI:

- [ ] Open Registries and use **Add Registry** for the remote `aart-test-registry` URL.
- [ ] Keep it as the default registry.
- [ ] Confirm that a local path is refused as a consumer registry.
- [ ] In Settings, enable Maintainer Mode.

Add the two author repositories as remote author Sources through the CLI. Use their real
credential-free Git URLs and their real branch:

```sh
env HOME="$AART_MAINTAINER_HOME" PYTHONPATH="$AART_CHECKOUT" \
  python3 -m agent_artifacts.cli source add \
  --alias superpowers-test --kind source-git \
  --location https://github.com/OWNER/superpowers-aart-test.git --ref main

env HOME="$AART_MAINTAINER_HOME" PYTHONPATH="$AART_CHECKOUT" \
  python3 -m agent_artifacts.cli source add \
  --alias test-mcp --kind source-git \
  --location https://github.com/OWNER/aart-test-mcp.git --ref main
```

Checkpoint:

- [ ] Registry and author Sources are visibly distinct.
- [ ] Each Source reports the real remote commit, not a placeholder.
- [ ] Source Sync changes no installed artifact and no registry content.
- [ ] Maintainer Candidates contains the Skill and MCP exactly once each.

## Stage 5 — validate and promote the Candidates

Create a publication branch in the registry checkout before promotion. Then use Maintainer Mode in
the TUI so validation and policy evidence are derived by AART rather than replaced with arbitrary
digest strings.

For the Superpowers Skill:

- [ ] Open Candidate details and read the semantic diff.
- [ ] Inspect validation and policy results.
- [ ] Choose **vendored** mode.
- [ ] Review the exact registry changes.
- [ ] Confirm promotion.

For the MCP:

- [ ] Repeat Candidate review and validation.
- [ ] Choose **referenced** mode to test an exact external Git dependency.
- [ ] Review the pinned author commit and registry changes.
- [ ] Confirm promotion.

This deliberately covers both ownership models:

- `vendored` — the registry owns and ships a reviewed copy;
- `referenced` — the registry publishes an exact reference and the author repository retains the
  bytes.

Checkpoint:

- [ ] Every promoted artifact names the author commit observed during Source Sync.
- [ ] The vendored payload exists in the registry checkout.
- [ ] The referenced payload was not copied into the registry.
- [ ] No push or merge happened automatically.

## Stage 6 — reconcile and publish the registry

Run registry reconciliation over the local checkout:

```sh
env HOME="$AART_MAINTAINER_HOME" PYTHONPATH="$AART_CHECKOUT" \
  python3 -m agent_artifacts.cli registry lock --source "$AART_REGISTRY_CHECKOUT" --yes
env HOME="$AART_MAINTAINER_HOME" PYTHONPATH="$AART_CHECKOUT" \
  python3 -m agent_artifacts.cli registry build --source "$AART_REGISTRY_CHECKOUT" --yes
env HOME="$AART_MAINTAINER_HOME" PYTHONPATH="$AART_CHECKOUT" \
  python3 -m agent_artifacts.cli registry validate --source "$AART_REGISTRY_CHECKOUT" --frozen
env HOME="$AART_MAINTAINER_HOME" PYTHONPATH="$AART_CHECKOUT" \
  python3 -m agent_artifacts.cli registry audit --source "$AART_REGISTRY_CHECKOUT"
```

Review `git status` and the diff. Commit only the reviewed registry changes, push the publication
branch, open a pull request and merge it to `main`. Do not use `registry publish` in this acceptance
chain: Git review and merge are the publication authority being tested.

After merge, use a fresh checkout of remote `main` and require:

```sh
env HOME="$AART_MAINTAINER_HOME" PYTHONPATH="$AART_CHECKOUT" \
  python3 -m agent_artifacts.cli registry validate \
  --source /absolute/path/to/fresh-registry-main --strict --frozen
```

Checkpoint:

- [ ] The pull request shows every published byte.
- [ ] CI passes on the registry repository.
- [ ] Fresh remote `main` passes strict frozen validation.
- [ ] Publication history is an ordinary reviewed Git history.

## Stage 7 — first-run consumer acceptance

Start from the empty consumer home and empty consumer project:

```sh
cd "$AART_CONSUMER_PROJECT"
env HOME="$AART_CONSUMER_HOME" PYTHONPATH="$AART_CHECKOUT" \
  python3 -m agent_artifacts.cli
```

Walk the TUI as a new user:

- [ ] First-run explanation and `SETUP REQUIRED` appear before navigation.
- [ ] The permanent legend includes arrows, Enter, Space, Esc, help and quit.
- [ ] Moving the Dashboard cursor explains each destination.
- [ ] Esc returns immediately.
- [ ] Registries → Add Registry accepts the remote test registry.
- [ ] Review shows the exact alias, URL, branch/tag and default choice.
- [ ] After confirmation, Marketplace is populated without restarting AART.

Cross-check read-only CLI output:

```sh
env HOME="$AART_CONSUMER_HOME" PYTHONPATH="$AART_CHECKOUT" \
  python3 -m agent_artifacts.cli source list --json
env HOME="$AART_CONSUMER_HOME" PYTHONPATH="$AART_CHECKOUT" \
  python3 -m agent_artifacts.cli marketplace list --json
```

Checkpoint:

- [ ] Only the test registry is configured.
- [ ] Marketplace offers both expected artifacts.
- [ ] Provenance contains real registry and author revisions.
- [ ] No author Source is exposed as an approved registry.

## Stage 8 — install and run the artifacts

For each artifact, review first and cancel once. Confirm that cancellation writes nothing. Then run
the same installation and confirm it.

Skill checks:

- [ ] The selected harness receives the Skill and every declared supporting file.
- [ ] No undeclared Superpowers file is copied.
- [ ] Installed, Activity and the CLI status agree on version and health.

MCP checks:

- [ ] AART creates only the reviewed runtime/configuration effects.
- [ ] The harness configuration points to the generated launcher.
- [ ] Starting what the harness configuration names answers MCP `initialize`.
- [ ] `tools/list` exposes the expected harmless tool.
- [ ] `tools/call` returns the expected deterministic result.

General checks:

- [ ] Fast and Verbose change detail only, never plan identity.
- [ ] TUI and CLI reviews describe the same effects.
- [ ] Activity and receipts describe what actually reached disk.
- [ ] Nothing outside the isolated project/home was modified.

## Stage 9 — setup, credentials and receipts

After the plain MCP path works, publish version `1.1.0` with setup v2 and one dedicated test input.
Use a disposable value, never a real credential.

- [ ] Setup effects are shown before consent.
- [ ] Default/no consent performs no setup effect.
- [ ] Explicit consent runs only reviewed effects.
- [ ] Secret values never appear in TUI, JSON, receipts, logs or committed files.
- [ ] macOS stores the test secret through the Keychain boundary.
- [ ] `marketplace receipt show` describes the run.
- [ ] `marketplace receipt verify` measures its current truth.
- [ ] `marketplace receipt undo` reverses only effects the receipt proves reversible.

Delete the disposable Keychain entry during cleanup only after all dependant tests finish.

## Stage 10 — publish and consume an update

In the Superpowers fork:

- [ ] Change one observable Skill file.
- [ ] Raise the manifest version from `1.0.0` to `1.1.0`.
- [ ] Commit and push.

On the maintainer machine:

- [ ] Source Sync reports the new author commit.
- [ ] Candidate review reports the semantic change.
- [ ] Promote it on a new registry branch.
- [ ] Reconcile, validate, audit, push, review and merge the registry PR.

On the consumer machine:

- [ ] Record installed file digests before Registry Sync.
- [ ] Registry Sync discovers `1.1.0` but leaves installed `1.0.0` bytes unchanged.
- [ ] Status reports an available update.
- [ ] Update review names what changes and what remains.
- [ ] Cancelling Update changes nothing.
- [ ] Confirmed Update installs `1.1.0` and records the new registry/author revisions.
- [ ] Activity retains both the installation and update history.

## Stage 11 — drift, Doctor and minimal Repair

Damage one component at a time:

1. edit a managed Skill file;
2. remove the MCP launcher;
3. alter the MCP harness entry;
4. leave an interrupted setup working directory.

For each case:

- [ ] `aart doctor` reports the exact damaged component.
- [ ] A read-only Doctor run changes nothing.
- [ ] Repair review touches only repairable drift.
- [ ] Confirmation requires the reviewed digest.
- [ ] Repair changes only the damaged component.
- [ ] Unrepairable drift is reported honestly rather than treated as healthy.
- [ ] Interrupted work is discoverable and is not blindly resumed at the next imperative step.

## Stage 12 — uninstall and source removal

- [ ] Review and cancel uninstall once; verify nothing changes.
- [ ] Confirm Skill uninstall and verify only its owned files leave.
- [ ] Confirm MCP uninstall and verify launcher/runtime/harness effects follow the receipt.
- [ ] Shared or user-owned content remains where the review says it will remain.
- [ ] Doctor reports a clean consumer project afterward.
- [ ] Remove the configured registry with `source remove`.
- [ ] Verify the managed source snapshot is removed while audit receipts remain readable.

## Stage 13 — release-candidate acceptance

Only after all blocking manual findings are fixed and manually retested:

- [ ] Commit the accepted TUI/manual-test increment.
- [ ] Run focused tests for every fix.
- [ ] Run full `make quality`.
- [ ] Run full `make integration`.
- [ ] Build the wheel.
- [ ] Verify the wheel against the intended tag.
- [ ] Install the wheel into a clean tool environment.
- [ ] Repeat the first-run and one Skill/MCP smoke test using the installed `aart`, not the source
      checkout.
- [ ] Push the branch and require the public CI matrix.
- [ ] Create the test GitHub Release only after its generated release pull request is reviewed.

PyPI publication is outside this acceptance run. The release target is the GitHub Release and its
verified wheel.

## Known expected boundaries

Do not file these as new defects unless observed behavior contradicts the stated refusal:

- A local path is an authoring Source, not a consumer Registry.
- Registry promotion never pushes or merges automatically.
- Collection installation is currently unavailable and must refuse honestly (B-067).
- Artifact setup input entry is not yet a general TUI form (B-075).
- `registry publish` is not part of this Git-review publication chain (B-057).

## Finding template

Add every unexpected observation to `TODO.md` immediately:

```md
- [ ] **QA-NNN — Short problem statement.**
      Stage: N
      Surface: TUI screen or exact public command
      Severity: blocking | high | medium | low
      Blocks current stage: yes | no
      Reproduction: exact actions/arguments
      Expected: what should happen
      Observed: what happened instead
      Evidence: screenshot/output/receipt path with secrets removed
      Fix: pending
```

## Completion rule

The end-to-end run is accepted only when:

1. every stage checkpoint is checked;
2. every blocking/high finding is fixed and manually retested;
3. remaining lower-priority findings are explicit in `TODO.md`;
4. the clean installed wheel repeats the critical Skill and MCP path;
5. full local gates and the public CI matrix are green on the exact committed tree.
