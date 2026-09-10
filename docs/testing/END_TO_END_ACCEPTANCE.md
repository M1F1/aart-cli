# AART manual walkthrough — CLI only

## Purpose

This is the manual test for AART's **command line**. You play two roles in order: a maintainer who
builds and publishes a Registry with `aart registry ...`, then a consumer who subscribes to it and
installs from it with `aart source ...` and `aart marketplace ...`.

There are two routes through the same product, and this is one of them:

| route | document | what it exercises |
|---|---|---|
| terminal application | [`TUI_MANUAL_WALKTHROUGH.md`](TUI_MANUAL_WALKTHROUGH.md) | screens, navigation, review prompts, footer |
| command line | this file | commands, flags, review/`--yes` split, JSON output |

Run whichever matches what you are testing. Running both over one lab is fine and tests more than
either alone, but they are separate passes with separate findings.

The Product Specification remains the product authority. Findings go to the first section of
[`TODO.md`](../../TODO.md), in the format its *Finding template* gives.

## Build the lab

```sh
cd /absolute/path/to/aart-cli
make manual-test-setup-empty
```

This creates `/tmp/aart-cli-manual-lab` with its own HOME/XDG, two published author repositories,
local bare remotes, a unique `manual/<run-id>` branch, and a **Registry repository that is empty on
purpose**. `START_HERE.md` in the lab root carries this run's exact URLs and ref — read the ref from
there, it changes every setup.

Then open a shell that is already inside the lab:

```sh
make manual-test-shell-maintainer   # cwd: the empty Registry checkout
make manual-test-shell-consumer     # cwd: a clean consumer project
```

Inside it, invoke AART as `python3 -m agent_artifacts.cli`. Every command below assumes that shell,
so nothing is exported into your own session and no command can reach your real AART state. Leave
with `exit`; throw the run away with `make manual-test-reset`.

> `make manual-test-setup` (without `-empty`) arrives with the Registry already published. Use it
> when you only want the consumer half; it skips all of Act I.

## About `https://manual.aart.test/...`

Those URLs are the lab's author repositories. `.test` is a reserved TLD that never resolves on the
real internet; the lab's own `.gitconfig` rewrites the prefix to its local bare remotes:

```
[url "file:///tmp/aart-cli-manual-lab/remotes/"]
	insteadOf = https://manual.aart.test/
```

They work only inside the lab shell. This indirection is deliberate: AART refuses a `file://`
origin — *"Git source location must be credential-free HTTPS/SSH"* — so the lab needs an
HTTPS-shaped URL that resolves locally, which exercises the real Git acquisition path without
depending on any GitHub account.

---

# Act I — maintainer, from nothing to a published Registry

Open `make manual-test-shell-maintainer`. The current directory is the empty Registry checkout.

## 1 — Review before initializing

- [ ] Run `registry init` **without** `--yes` first.

```sh
python3 -m agent_artifacts.cli registry init \
  --source . --source-id manual-registry --display-name "Manual Registry"
```

Expected: it reports what it would write and changes nothing. Confirm with `git status` that the
tree is untouched. Then repeat with `--yes`.

Expected after `--yes`: only registry-owned files appear, and the command prints the `next:` steps
it expects (`validate`, `lock`, `build`, `audit`).

## 2 — Observe the author sources as Candidates

`registry scan` reads a clean author checkout at its exact HEAD and never mutates anything:

```sh
python3 -m agent_artifacts.cli registry scan --source . \
  --checkout ../skill --source-alias manual-skill \
  --source-url https://manual.aart.test/skill.git --target-registry manual-registry
```

- [ ] Repeat for `../mcp` with `--source-alias manual-mcp`.
- [ ] Re-run one of them with `--json`.

Expected: each Candidate reports a `candidate_id`, a coordinate, an `input_digest`, a
`canonical_digest` and state `new`. `registry mutations: 0` on every scan. The JSON form carries the
same facts as the text form.

## 3 — Bring an artifact into the Registry

`registry promote` is the Candidate-promotion transaction, and it requires
`--validation-report` and `--policy-result` digests as evidence. **No CLI command emits those
digests today** — only the Maintainer screens derive them — so a CLI-only promotion would mean
inventing evidence, which is exactly what the flag exists to prevent. This is recorded as `QA-056`;
confirm it here and do not fabricate a digest to get past it.

The CLI's own route into the Registry is vendoring, which needs no external evidence because the
Registry takes ownership of the bytes:

```sh
python3 -m agent_artifacts.cli registry vendor --source . \
  --url https://manual.aart.test/skill.git --ref "$REF" --path manual-check \
  --artifact-version 1.0.0 --summary "Disposable manual skill" --license MIT \
  --profile claude --platform darwin skill manual-check
```

- [ ] Run it review-only first, read every check it reports, then repeat with `--yes`.

Expected: the review resolves the ref to an exact commit, names the subtree and the target path,
counts the payload files, and warns plainly that vendoring is not a safety claim and that upstream
fixes will not reach consumers until it is vendored again. Without `--yes` nothing is written and
the command says AART will not commit or push.

- [ ] Try `--url file:///...` once and confirm it is refused.

## 4 — Publish

```sh
python3 -m agent_artifacts.cli registry publish --source .
```

Expected: it prepares lock and index in memory, runs validate and audit over that exact snapshot,
and lists every path Git would commit — `planned` for generated files, `??` for new ones. It ends
with *"Reviewed only. Re-run with --yes to write, validate, audit, and commit."*

- [ ] Repeat with `--yes -m "Publish manual fixtures"`.
- [ ] Confirm with `git log` that exactly one commit was created, and with `git status` that
      nothing was pushed.

Then publish the branch yourself — AART separates publication from approval and never pushes
(Product Specification 161.7):

```sh
git push origin HEAD
```

## 5 — Read the Registry back

- [ ] `registry validate --source . --strict --frozen`
- [ ] `registry audit --source .`
- [ ] `registry diff --source .`
- [ ] `security scan` and `security show` over a published artifact envelope.

Expected: validation is clean, audit reports review/provenance/setup and available security
metadata, diff reports no drift immediately after a publish, and every security output states that
assessments reduce uncertainty rather than guaranteeing safety.

Checkpoint for Act I:

- [ ] Every mutating command reviewed first and changed nothing without `--yes`.
- [ ] No command pushed or merged.
- [ ] `--json` output matched the text output wherever both exist.

---

# Act II — consumer, subscribe and install

Open `make manual-test-shell-consumer`. Fresh home, empty project, nothing configured.

## 6 — Subscribe

```sh
python3 -m agent_artifacts.cli source add --alias manual-registry --kind registry-git \
  --location https://manual.aart.test/registry.git --ref "$REF" --default
```

- [ ] Confirm a local path is refused for `--kind registry-git`.
- [ ] `source list --json`, then `source health`.

Expected: `source add` validates and snapshots the exact origin before saving, so it needs no
interactive confirmation. The listing distinguishes an approved Registry from an authoring Source.

## 7 — Browse

- [ ] `marketplace list --json`
- [ ] `marketplace search manual`
- [ ] `marketplace health`

Expected: both published artifacts appear with real provenance — the registry revision and the
author commit — and never a placeholder.

## 8 — Install

```sh
python3 -m agent_artifacts.cli marketplace install manual-registry/skill/manual-check@1.0.0 \
  --profile claude
```

- [ ] Run it without `--yes` first and confirm the plan is printed and nothing changes.
- [ ] Install for real with `--yes`.
- [ ] Install `manual-registry/mcp/dummy-mcp@1.0.0` the same way; enter **disposable test text
      only** at the credential prompt.
- [ ] Try `--expect <wrong digest>` once and confirm the install is refused.

Expected: the reviewed plan is what executes. The MCP's `dummy-token` binds to an isolated
credential reference; the value never appears in output, receipts or logs.

## 9 — Inspect what happened

- [ ] `marketplace status --json`
- [ ] `marketplace setup` and `marketplace receipt` for the MCP
- [ ] `doctor`

Expected: `doctor` reports installed health, offline readiness, activity, credentials and
configuration, and its account matches what you actually did.

## 10 — Update, repair, remove

- [ ] Publish `1.0.1` from the maintainer shell, then `source sync` and `marketplace update`.
- [ ] Damage an installed file by hand, then re-run `doctor` and repair the reported issue.
- [ ] `marketplace uninstall` the Skill.
- [ ] `source remove --alias manual-registry`.

Expected: an update names both the old and the new version before applying. Repair is minimal —
it restores what drifted and touches nothing else. Uninstall removes what the receipt recorded and
leaves unrelated files alone.

## 11 — Factory reset

- [ ] `reset` — read the exact target list, then cancel at the first confirmation.
- [ ] Run it again and complete both confirmations (`RESET AART`, then `DELETE AART STATE`).

Expected: the plan names exact AART-owned configuration/data/cache targets and nothing else.
Cancelling or EOF changes nothing. Projects, harness files and other applications' credentials stay
untouched. Remember this reset acts on the **lab** home, not yours.

Checkpoint for Act II:

- [ ] Nothing installed, updated or removed without a plan you could review and refuse.
- [ ] No secret value appeared in any output, receipt or log.
- [ ] Every `--json` form was machine-readable and agreed with the text form.

---

## Known expected boundaries

These are correct behavior, not findings:

- AART never pushes or merges; publication is external by design (161.7).
- `file://` origins are refused; origins must be credential-free HTTPS/SSH.
- A vendored artifact does not track upstream — the Registry owns the copy until re-vendored.
- Security assessments reduce uncertainty and are not safety guarantees.
- `marketplace install` requires an explicit `--profile`.

## When you are done

```sh
make manual-test-reset
```

Removes only this marker-owned lab, after checking `.aart-manual-lab.json` and the exact absolute
root. It refuses an unmarked directory.
