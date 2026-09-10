# AART manual walkthrough — TUI only

## Purpose

This is the manual test for AART's **terminal application**. You play two roles in order: first a
maintainer who starts with an empty Registry and builds it entirely through the Maintainer screens,
then a consumer who subscribes to what you just published and installs from it.

Everything here happens in the TUI. There are exactly two exceptions, both deliberate:

- one command to create the disposable lab, and one to open the application;
- one `git push` after the maintainer's Registry commit, because AART separates publication from
  approval on purpose — screen 45 commits and never pushes or merges (Product Specification 161.7).

There are two routes through the same product, and this is one of them:

| route | document | what it exercises |
|---|---|---|
| terminal application | this file | screens, navigation, review prompts, footer |
| command line | [`END_TO_END_ACCEPTANCE.md`](END_TO_END_ACCEPTANCE.md) | commands, flags, review/`--yes` split, JSON output |

Both run over the same lab. Running both tests more than either alone, but they are separate passes
with separate findings.

Findings go to the first section of [`TODO.md`](../../TODO.md), in the format its *Finding
template* gives.

## Build the lab

```sh
cd /absolute/path/to/aart-cli
make manual-test-setup-empty
```

This creates an isolated ecosystem under `/tmp/aart-cli-manual-lab` with its own HOME/XDG, two
published author repositories, local bare remotes, and a unique `manual/<run-id>` branch — and a
**Registry repository that is empty on purpose**. No manifest, no promotion, no configured Source.
Building it is your job, in the TUI.

`START_HERE.md` in the lab root carries this run's exact URLs and ref. Read the ref from there; it
changes every setup.

Open a surface:

```sh
make manual-test-maintainer   # cwd is the empty Registry checkout
make manual-test-consumer     # cwd is a clean consumer project
```

Neither touches your real AART state. To throw the run away: `make manual-test-reset`.

> The default `make manual-test-setup` arrives with the Registry already published. Use it when you
> only want to test the consumer half; it skips everything in Act I.

## About the lab URLs

`https://manual.aart.test/skill.git` and `.../mcp.git` are the lab's author repositories.
`.test` is a reserved TLD that never resolves on the real internet; the lab's own `.gitconfig`
rewrites the prefix to its local bare remotes:

```
[url "file:///tmp/aart-cli-manual-lab/remotes/"]
	insteadOf = https://manual.aart.test/
```

They resolve only inside the lab. AART refuses a `file://` origin — *"Git source location must be
credential-free HTTPS/SSH"* — so the lab needs an HTTPS-shaped URL that resolves locally, which
exercises the real Git acquisition path without any GitHub account.

## Reading the screens

Every frame names where you are and what the directory context is:

```
AART / Registry Maintainer
Working in /private/tmp/aart-cli-manual-lab/repositories/registry
```

The footer lists the keys that screen actually accepts. `Esc` is always Back, `?` is always Help,
`q` is always Quit. If a key is in the footer and does nothing, that is a finding.

---

# Act I — maintainer, from nothing to a published Registry

Open `make manual-test-maintainer`. You start on the consumer Dashboard, first run.

## 1 — Turn on Maintainer Mode

- [ ] Dashboard → **Settings** → move to **Maintainer Mode** → `Space`.
- [ ] Return with `Esc`.

Expected: the Dashboard now lists **Maintainer Dashboard** as a destination. Settings explains what
the mode hides when it is off.

## 2 — Create the Registry

- [ ] **Maintainer Dashboard** → **Registry Maintainer**.

Expected: two clearly separate blocks — *Connected Registry snapshots* (none) and *Local Registry
workspace*, which says the current project is not a Registry and that Initialize creates one here.
The two must not be conflated, and no internal screen number may appear in the text (`QA-044`).

- [ ] Press `n` (**Initialize**). The form has five rows; `↑`/`↓` move between them, typing edits
      the focused one, `Backspace` deletes, `Space` toggles a choice, `Enter` advances.

| row | what to enter |
|---|---|
| Registry ID | `manual-registry` — a slug, this is the name coordinates are built from |
| Display name | `Manual Registry` — what people see |
| Usage reporting | leave at `not enabled` |
| Local commit | `Space` to choose `yes, one local commit` |
| Continue | `Enter` — *Review the five stages* |

The ID is the one value that matters later: the consumer will see artifacts as
`manual-registry/skill/manual-check`. If you type something else here, use it consistently for the
rest of the run.

- [ ] Read the review, then confirm.

Expected: the form itself states that nothing is pushed and nothing is merged. The review names
exactly what will be written before anything is written, and cancelling writes nothing. After
confirming, the local workspace block reports a Registry.

## 3 — Publish the Registry and subscribe to it

Source Sync decides whether each Candidate is new, updated or unchanged by comparing what the
authors published against what the **target Registry already approved**, so it needs a default
target Registry to compare with. The Registry you just created exists only as a local commit, and
a subscription reads a remote — so publishing it comes before syncing, not only after promotion.

- [ ] Push the initialization commit yourself. AART did not and will not (161.7):

```sh
git -C /tmp/aart-cli-manual-lab/repositories/registry push origin HEAD
```

- [ ] Back in the TUI: **Maintainer Dashboard** → `Esc` → **Registries** → `a` (**Add Registry**).

| row | what to enter |
|---|---|
| Alias | `manual-registry` |
| Registry URL | `https://manual.aart.test/registry.git` |
| Branch or tag | this run's ref, from `START_HERE.md` |
| Make default registry | `Space` to set `yes` |
| Continue | `Enter` — *Validate and review* |

This is the same Add Registry form a consumer uses; here you are subscribing to your own Registry
so that Sync has a baseline. The Registry is empty at this point, which is correct — every
Candidate will therefore be *new*.

Expected: Registries lists `manual-registry` as the default, and Registry Maintainer's *Connected
Registry snapshots* block is no longer empty.

Skip this step and step 5 refuses with `Source Sync needs an explicit default target registry`,
every Source stays at `0 manifests`, and Candidates is empty (`QA-059`).

## 4 — Add the author Sources

- [ ] **Maintainer Dashboard** → **Sources** → `a` (**Add Source**).

Five rows again. `Space` switches **Kind** between `source-git` and `source-local`; leave it on
`source-git`.

| row | first Source | second Source |
|---|---|---|
| Alias | `manual-skill` | `manual-mcp` |
| Kind | `source-git` | `source-git` |
| Location | `https://manual.aart.test/skill.git` | `https://manual.aart.test/mcp.git` |
| Branch or tag | this run's ref, from `START_HERE.md` | the same ref |
| Continue | `Enter` — *Validate and review* | `Enter` |

The ref is different every setup, so take it from `START_HERE.md` rather than from any example.
Those `manual.aart.test` URLs are the lab's own author repositories — see *About the lab URLs*
above.

Expected: a Source is visibly an authoring location, not an approved Registry (`QA-043`). The
review shows alias, URL and ref before confirmation. Opening the Add Source form a second time
opens it **empty**; returning to a refused form keeps what you typed (`QA-028`).

## 5 — Sync and discover Candidates

- [ ] On **Sources**, press `s` (**Sync**).
- [ ] On the result screen, press `Enter` — it returns you to Sources, not through five `Esc`
      presses (`QA-027`).

Expected: each Source reports a real commit, not a placeholder. Sync changes no installed artifact
and no Registry content.

- [ ] **Maintainer Dashboard** → **Candidates**.

Expected: the Skill and the MCP appear exactly once each. Columns keep their positions between
rows, and the focused value is readable in full (`QA-030`).

## 6 — Review a Candidate

- [ ] Open a Candidate. Press `d` (**Diff**), then `f` (**Files**) to fold raw file changes in and
      out. `r` opens its **Lifecycle**.

Expected: facts, decisions and the one line telling you what a key press will do are visually
separated, with the action prompt last (`QA-029`).

## 7 — Validate and promote

- [ ] From the Candidate, reach **Validation**. Press `p` (**Promote**).
- [ ] Walk **Policy review** → **Promotion review** → **Promotion mode**.
- [ ] On Promotion mode, press `m` to toggle **Vendored** / **Referenced**.

Expected: the screen explains what each mode means *before* you toggle it, not after (`QA-039`).

- [ ] Continue to **Registry diff**, press `Enter` (**Review promotion**).
- [ ] Confirm through **Registry validation** and **Registry commit**.

Expected: workflow progress chrome shows where you are in the sequence, and going back preserves
context rather than resetting it (`QA-036`/`QA-037`). A refused or failed run leaves a terminal
screen saying the run did not happen, offering `Enter` back to the list — never a stale
confirmation (`QA-033`).

- [ ] After the commit, you land back on **Registry Maintainer**, one key from the next promotion.

## 8 — Publish the promotion

The TUI has committed and deliberately not pushed. Screen 45 says so — `Git push: no`, and after
the write `Canonical-branch publication remains external.` This is the second push of the run: the
first made the Registry subscribable, this one publishes what you just promoted into it.

- [ ] While you are on that screen, judge whether it **closes the path**: it states the boundary,
      but does it tell you that publishing is now yours to do? This is `QA-055`, recorded as
      unconfirmed — decide it here, at the terminal.

Publish the branch yourself:

```sh
git -C /tmp/aart-cli-manual-lab/repositories/registry push origin HEAD
```

Checkpoint for Act I:

- [ ] The Registry was created, filled and committed without leaving the TUI.
- [ ] Every destructive or writing step was reviewed first and cancellable.
- [ ] No screen leaked an internal screen identifier.
- [ ] Promotion records are visible in the pushed branch.

---

# Act II — consumer, subscribe and install

Open `make manual-test-consumer`. Fresh home, empty project, nothing configured.

## 9 — First run

Expected: the first-run explanation and `SETUP REQUIRED` appear before the navigation list, and
point at Registries → Add Registry. The permanent footer names movement, Enter, Space, Esc, help
and quit (`B-077`). Moving the Dashboard cursor explains each destination. `Esc` returns
immediately.

## 10 — Subscribe to the Registry you just published

- [ ] **Registries** → `a` (**Add Registry**).

| row | what to enter |
|---|---|
| Alias | `manual-registry` |
| Registry URL | `https://manual.aart.test/registry.git` |
| Branch or tag | this run's ref |
| Make default registry | `Space` to set `yes` |
| Continue | `Enter` — *Validate and review* |

- [ ] Confirm that a **local path is refused** here — the form says local folders are authoring
      Sources, not Marketplace registries. Try one and watch it be refused.

Expected: the review shows alias, URL, branch/tag and the default choice. After confirmation
Marketplace is populated **without restarting AART** (`QA-045`…`QA-048` cover the readability and
escapability of these flows).

## 11 — Install

- [ ] **Marketplace** → select the Skill → `i` (**Install**). Review, then **cancel once**.
- [ ] Confirm nothing was written. Install it for real.
- [ ] Install `dummy-mcp`. At the provider prompt, enter **disposable test text only**.

Expected: AART binds an isolated credential reference; the macOS Keychain owns value entry. The MCP
reports only whether the variable is present and never echoes it.

## 12 — Inspect

- [ ] **Installed** → artifact details. **Credentials** → the reference and its dependants.
- [ ] **Doctor** → health, offline readiness, activity, configuration.
- [ ] **Activity** → what actually happened, with real provenance.

Expected: Dashboard, lists, help and footer have a readable hierarchy with visible focus
(`QA-035`/`QA-038`/`QA-040`/`QA-041`/`QA-042`).

## 13 — Repair, update, remove

- [ ] Break an installed file by hand, then **Doctor** → `r` (**Repair issues**). Minimal repair only.
- [ ] Publish a `1.0.1` from the maintainer side and check **Updates** → `i`.
- [ ] **Installed** → artifact → `u` (**Uninstall**).
- [ ] **Registries** → `d` (**Disconnect**) — reviewed and bounded (`QA-050`).

Checkpoint for Act II:

- [ ] Nothing installed, repaired or removed without a review you could cancel.
- [ ] Disconnecting a Registry removed the subscription and nothing else.
- [ ] Doctor's account of the machine matched what you actually did.

---

## When you are done

```sh
make manual-test-reset
```

Removes only this marker-owned lab, after checking `.aart-manual-lab.json` and the exact absolute
root. It refuses an unmarked directory.

Then move confirmed items in [`TODO.md`](../../TODO.md) from *Fixed — awaiting manual retest* to
checked, and file anything new in *Open*.
