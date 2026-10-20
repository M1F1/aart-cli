# AART manual walkthrough — CLI only

## Purpose

This is the manual test for AART's **command line**. You play two roles in order: a maintainer who
builds and publishes a Registry with `aart-cli maintain ...`, then a consumer who subscribes to it and
installs from it with `aart-cli consume registry ...` and `aart-cli consume ...`.

There are two routes through the same product, and this is one of them:

| route | document | what it exercises |
|---|---|---|
| terminal application | [`TUI_MANUAL_WALKTHROUGH.md`](TUI_MANUAL_WALKTHROUGH.md) | screens, navigation, review prompts, footer |
| command line | this file | commands, flags, review/`--yes` split, JSON output |

Run whichever matches what you are testing. Running both over one lab is fine and tests more than
either alone, but they are separate passes with separate findings.

The Product Specification remains the product authority. Findings go to
[`manual-acceptance.md`](manual-acceptance.md), in the format it describes.

## Build the lab

```sh
cd "$(git rev-parse --show-toplevel)"   # from anywhere inside your aart-cli checkout
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

Inside it, invoke AART as `python3 -m aart_cli.cli`. Every command below assumes that shell,
so nothing is exported into your own session and no command can reach your real AART state. Leave
with `exit`; throw the run away with `make manual-test-reset`.

> `make manual-test-setup` (without `-empty`) arrives with the Registry already published. Use it
> when you only want the consumer half; it skips all of Act I.

### If the lab loses its marker

`make manual-test-reset` only ever removes a directory that carries `.aart-manual-lab.json`, and
setup resets before it builds, so a lab whose marker is gone blocks both. That refusal is correct —
an unmarked directory is not the tool's to delete — but it leaves the directory to you. Look at it
first, then take the write bit back before removing it: an installed payload is delivered
read-only, directories included, so `rm -rf` on its own stops at the first artifact root.

```sh
chmod -R u+w /tmp/aart-cli-manual-lab && rm -rf /tmp/aart-cli-manual-lab
```

The refusal prints this same line with the exact path it refused, and `tests/manual_test_lab_test.py`
runs it against a read-only lab, so it is a recovery that is checked rather than one that is
described (`QA-085`).

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

- [ ] Run `maintain registry init` **without** `--yes` first.

```sh
python3 -m aart_cli.cli maintain registry init \
  --source . --source-id manual-registry --display-name "Manual Registry"
```

Expected: it reports what it would write and changes nothing. Confirm with `git status` that the
tree is untouched. Then repeat with `--yes`.

Expected after `--yes`: only registry-owned files appear, and the command prints the `next:` steps
it expects (`validate`, `lock`, `build`, `audit`).

## 2 — Observe the author sources as Candidates

`maintain upstream scan` reads a clean author checkout at its exact HEAD and never mutates anything:

```sh
python3 -m aart_cli.cli maintain upstream scan --source . \
  --checkout ../skill --source-alias manual-skill \
  --source-url https://manual.aart.test/skill.git --target-registry manual-registry
```

- [ ] Repeat for `../mcp` with `--source-alias manual-mcp`.
- [ ] Re-run one of them with `--json`.

Expected: each Candidate reports a `candidate_id`, a coordinate, an `input_digest`, a
`canonical_digest` and state `new`. `registry mutations: 0` on every scan. The JSON form carries the
same facts as the text form.

## 3 — Bring an artifact into the Registry

`maintain candidate promote` is the Candidate-promotion transaction. It takes the same boundaries as
`maintain upstream scan` plus one `--candidate` per Candidate ID the scan reported. It runs validation and
the effective policy for each Candidate itself, the same run the Maintainer screens show, and the
review names each Candidate's validation-report and effective-policy digests before `--yes`
writes them into its promotion record (D-387, closing `QA-056`). No evidence is typed in.

- [ ] Run `maintain candidate promote` review-only for the scanned Candidates and read the evidence it
      states, then repeat with `--yes`. Expected: one validation-report digest per Candidate,
      nothing committed and nothing pushed.

Adoption is the other CLI route into the Registry. It reads one repository's manifests without
subscribing to it:

```sh
python3 -m aart_cli.cli maintain upstream adopt --source . --url https://manual.aart.test/skill.git --ref "$REF"
```

- [ ] Run it review-only first, read what the manifests compile to, then repeat with
      `--artifact skill/manual-check@1.0.0 --yes`.

Expected: the review resolves the ref to an exact commit and lists each manifest's artifact with
the version the Registry assigns. Without `--yes` nothing is written and the command says AART will
not commit or push.

- [ ] Try `--url file:///...` once and confirm it is refused.

## 4 — Publish

```sh
python3 -m aart_cli.cli maintain registry publish --source .
```

Expected: it prepares lock and index in memory, runs validate and audit over that exact snapshot,
and lists every path Git would commit — `planned` for generated files, `??` for new ones. It ends
with *"Reviewed only. Re-run with --yes to write, validate, audit, and commit."*

- [ ] Repeat with `--yes -m "Publish manual fixtures"`.
- [ ] Confirm with `git log` that exactly one commit was created, and with `git status` that
      nothing was pushed.

Then push the commit to a review branch. `maintain registry publish` commits every listed change and
stops there; `maintain registry push` is the separate step, and it refuses the default branch by name:

```sh
python3 -m aart_cli.cli maintain registry push --source . --branch manual-review
```

- [ ] Try `--branch` with the default branch once and confirm it is refused.

If it answers that the checkout does not know the remote's default branch, run
`git remote set-head origin --auto` and push again.

## 5 — Read the Registry back

- [ ] `maintain registry validate --source .` and `maintain registry build --source . --check`
- [ ] `maintain registry audit --source .`
- [ ] `maintain registry diff --source .`
- [ ] `security scan` and `security show` over a published artifact envelope.

Expected: validation is clean, audit reports review/provenance/setup and available security
metadata, diff reports no drift immediately after a publish, and every security output states that
assessments reduce uncertainty rather than guaranteeing safety.

Checkpoint for Act I:

- [ ] Every mutating command reviewed first and changed nothing without `--yes`.
- [ ] Only `maintain registry push` pushed, and only to the review branch; nothing merged.
- [ ] `--json` output matched the text output wherever both exist.

---

# Act II — consumer, subscribe and install

Open `make manual-test-shell-consumer`. Fresh home, empty project, nothing configured.

## 6 — Subscribe

```sh
python3 -m aart_cli.cli consume registry add --alias manual-registry --kind git \
  --location https://manual.aart.test/registry.git --ref "$REF" --default
```

- [ ] Confirm a local path is refused for `--kind git`.
- [ ] `consume registry list --json`, then `consume registry health`.

Expected: `consume registry add` validates and snapshots the exact origin before saving, so it needs
no interactive confirmation.

## 7 — Browse

- [ ] `consume list --json`
- [ ] `consume search manual`
- [ ] `consume health`

Expected: both published artifacts appear with real provenance — the registry revision and the
author commit — and never a placeholder.

## 8 — Install

```sh
python3 -m aart_cli.cli consume install manual-registry/skill/manual-check@1.0.0 \
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

- [ ] `consume status --json`
- [ ] `consume setup` and `consume receipt show` for the MCP
- [ ] `doctor`

Expected: `doctor` reports installed health, offline readiness, activity, credentials and
configuration, and its account matches what you actually did.

## 10 — Update, repair, remove

- [ ] Publish `1.0.1` from the maintainer shell, then `consume registry sync` and `consume update`.
- [ ] Damage an installed file by hand, then re-run `doctor` and repair the reported issue.
- [ ] `consume uninstall` the Skill.
- [ ] `consume registry remove --alias manual-registry`.

Expected: an update names both the old and the new version before applying. Repair is minimal —
it restores what drifted and touches nothing else. Uninstall removes what the receipt recorded and
leaves unrelated files alone.

## 11 — Reset with backup

- [ ] `reset` — read the exact target list, then cancel at the confirmation.
- [ ] Run it again and type `RESET AART`; note the backup directory it prints.
- [ ] `reset --restore <that directory>` and type `RESTORE AART`.

Expected: the plan names exact AART-owned configuration/data/cache targets and nothing else. The
reset leaves aart-cli empty and the backup holds every target; the restore brings them back and
keeps the emptied state in a new backup. Cancelling or EOF changes nothing. Projects, harness files and other applications' credentials stay
untouched. Remember this reset acts on the **lab** home, not yours.

Checkpoint for Act II:

- [ ] Nothing installed, updated or removed without a plan you could review and refuse.
- [ ] No secret value appeared in any output, receipt or log.
- [ ] Every `--json` form was machine-readable and agreed with the text form.

---

## Known expected boundaries

These are correct behavior, not findings:

- AART never merges: `maintain registry publish` commits and stops, and `maintain registry push`
  pushes only to a named non-default branch. Merging is always the reviewer's work, through `gh` or
  the forge.
- `file://` origins are refused; origins must be credential-free HTTPS/SSH.
- A self-contained artifact does not track upstream: `maintain upstream check` reports what moved, and a new version is adopted explicitly.
- Security assessments reduce uncertainty and are not safety guarantees.
- `consume install` requires an explicit `--profile`.

## When you are done

```sh
make manual-test-reset
```

Removes only this marker-owned lab, after checking `.aart-manual-lab.json` and the exact absolute
root. It refuses an unmarked directory.
