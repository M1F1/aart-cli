# AART manual walkthrough — TUI only

## Purpose

This is the manual test for AART's **terminal application**. You play two roles in order: first a
maintainer who starts with an empty Registry and builds it entirely through the Maintainer screens,
then a consumer who subscribes to what you just published and installs from it.

Everything here happens in the TUI. There are exactly two exceptions, both deliberate:

- one command to create the disposable lab, and one to open the application;
- the Git work the TUI does not own: the first push of the *initialization* commit, so the
  Registry is subscribable at all, and — after the local commit on screen 45 — pushing the
  promotion, getting it reviewed and merged into the branch subscribers read, and updating your
  checkout. The TUI never pushes; it ends at the reviewed local commit and says what comes next
  (Product Specification 164.7, `D-249`/`D-255`, which supersede `D-228` for the TUI).

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
cd "$(git rev-parse --show-toplevel)"   # from anywhere inside your aart-cli checkout
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

Every frame is built from the same skeleton (`D-234`). The top line is the trail you walked, each
place named once (`D-236`); the launch directory is the footer's caption, flush on the rule above
the keys rather than a second line under the title (`D-242`, revising `D-235`):

```
AART / Maintainer / Sources

  …the screen…

working at /private/tmp/aart-cli-manual-lab/repositories/registry
────────────────────────────────────────────────────────────────
[↑↓] Move  [Enter] Open  [s] Sync  [v] Fast / Verbose  [Esc] Back  [?] Help  [q] Quit
```

The footer lists the keys that screen actually accepts, and the terminal pins it: a tall body
scrolls under it instead of pushing it off, and a short one is padded **above** the `working at`
line so the whole block — directory, rule, keys — sits on the bottom rows (`QA-086`). Blank space
between `working at` and the keys is a finding. `Esc` is always Back, `?` is always Help, `q` is always
Quit. If a key is in the footer and does nothing, that is a finding — and so is the other way round,
a key a screen tells you to press that the footer never offers (`QA-058`).

Three behaviours are new since the run that produced `QA-058`…`QA-084`, and each is worth one
deliberate press:

- [ ] `[v]` toggles Fast/Verbose on **every** screen: Fast hides the cursor-description region,
      Verbose shows it (`QA-064`/`QA-070`, `D-233`).
- [ ] `Esc` from a list reaches the dashboard that owns it, not the previous screen you happened to
      come from, and a sequence you finished by returning is off the back stack (`QA-072`, `D-237`).
- [ ] No screen shows an empty section and no screen names an internal identifier such as
      `Screen 46` (`QA-067`/`QA-077`).

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

- [ ] Push the initialization commit yourself. Initialize Registry writes a local commit and
      nothing more, and no TUI screen pushes anything (164.7, `D-255`):

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

CP-23 task 01 retest: after each successful addition, the cursor stays on the Source just added.
A separate notice names it and explains that **Source Sync** discovers/refreshes Candidates,
including new upstream versions; it neither promotes them nor updates installed artifacts.
Open that Source's details, start Sync, cancel with Esc, then return to Sources with Esc. The same
Source must remain selected, and `s` must review that Source. A refused addition must not show the
success notice. Adding the connection alone leaves Candidate discovery for the next step.

## 5 — Sync and discover Candidates

- [ ] On **Sources**, press `s` (**Sync**).
- [ ] On the result screen, press `Enter` — it returns you to Sources, not through five `Esc`
      presses (`QA-027`).

Expected: each Source reports a real commit, not a placeholder. Sync changes no installed artifact
and no Registry content.

- [ ] **Maintainer Dashboard** → **Candidates**.

Expected: the Skill and the MCP appear exactly once each. Columns keep their positions between
rows, and the focused value is readable in full (`QA-030`).

CP-23 task 02 retest: in Verbose, below the table and its own rule, `Artifact`, `Version`, `Source`
and `Status` describe the row under the cursor, with no `Under the cursor:` heading; moving the
cursor updates them. Press `v`: Fast shows only the table. Press `v` again: the same row is
described. Search for a name so no row matches: no stale detail remains.

One malformed manifest must not fail the whole Source (`QA-063`, `D-230`). It takes a minute to
prove and nothing else in the run tests it:

- [ ] Break one author manifest, push it, and sync that Source again:

```sh
cd /tmp/aart-cli-manual-lab/repositories/skill
printf 'not json' > manual-check/aart.json
git commit -am 'break one manifest' && git push
```

Expected: the Source still reports its commit and its other manifests, and the result screen adds
`Could not read N manifests:` with the path on the line. The Source is not failed whole, and
nothing is recorded as an `invalid` Candidate.

- [ ] Put it back (`git revert --no-edit HEAD && git push`) before continuing.

## 6 — Review a Candidate

- [ ] Open a Candidate. Press `d` (**Diff**), then `v` (**Fast / Verbose**) to fold the bounded
      redacted file diffs in and out (CP-23 task 03: `f` does nothing here any more). `r` on the
      Candidate opens its **Lifecycle**.

Expected: facts, decisions and the one line telling you what a key press will do are visually
separated, with the action prompt last (`QA-029`).

## 7 — Validate and promote

- [ ] From the Candidate, reach **Validation**. Press `Enter` on a check to open it, then `Enter`
      again for **Policy review** (CP-23 task 04: `p` does nothing on Validation).
- [ ] Walk on to **Promotion review** → **Promotion mode**.
- [ ] On Promotion mode, press `m` to toggle **Vendored** / **Referenced**.

Expected: the screen explains what each mode means *before* you toggle it, not after (`QA-039`).

- [ ] Continue to **Registry diff**, press `Enter` (**Review promotion**).
- [ ] Confirm through **Registry validation** and **Registry commit**.

Expected: workflow progress chrome shows where you are in the sequence, and going back preserves
context rather than resetting it (`QA-036`/`QA-037`). A refused or failed run leaves a terminal
screen saying the run did not happen, offering `Enter` back to the list — never a stale
confirmation (`QA-033`).

- [ ] After the commit, **Registry commit** stays on screen with its receipt; `Enter` goes on to
      **Registry Maintainer**, one key from the next promotion.

## 8 — Publish the promotion yourself, in Git

This step changed again. `D-228` once had AART push a reviewed commit to a review branch from this
screen; the product owner reversed that for the TUI (Product Specification 164.7, `D-249`), and
CP-23 task 05 removed it (`D-255`). The supported `aart registry push` CLI is unchanged — this
walkthrough is TUI-only, so it does not use it.

The committed **Registry commit** screen says what comes next, in order:

```
Subscribers cannot see this commit yet, and AART does not push it. In Git, you:
1. push this Registry branch to its remote;
2. where the Registry is reviewed, open a pull request and merge it into the branch
   subscribers read;
3. update this local checkout to that merged branch;
4. run Registry Sync to observe the approved state.
```

- [ ] Before leaving screen 45, press `p`, then type a few letters. Expected: nothing happens —
      no form, no review, no push — and the footer offers no `p` (`D-255`).
- [ ] Check nothing reached the remote yet:

```sh
git -C /tmp/aart-cli-manual-lab/remotes/registry.git log --oneline -1
```

Expected: the initialization commit, not your promotion.

**Then publish it yourself.** Act II subscribes at the run branch. In this lab the lab's run branch
is the one subscribers read and there is no reviewer, so pushing `HEAD` to it is the push and the
merge in one; in a real Registry you would push a review branch, open a pull request, and get it
merged first:

```sh
git -C /tmp/aart-cli-manual-lab/repositories/registry push origin HEAD
```

A pushed review branch that has not been merged is **not** published: a subscriber reading the
default branch cannot see it.

Checkpoint for Act I:

- [ ] The Registry was created, filled and committed in the TUI, and published by your own Git
      push — no TUI key pushed anything.
- [ ] Every destructive or writing step was reviewed first and cancellable.
- [ ] No screen leaked an internal screen identifier.
- [ ] Screen 45 listed push → review/merge → update checkout → Registry Sync, and never called
      the local commit published.
- [ ] Promotion records are visible in the merged branch.

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
- [ ] On **Success**, the choices are rows: `View installed`, `View receipt`, `Done`. The
      outcome above them has no bracketed buttons. `View receipt` opens the receipt of **this**
      install (its `Recorded:` time), not an older one. `Esc` and `Done` both land on
      **Marketplace**; `Esc` must never show Installing or Ready again. No Undo row is offered: the
      screen says why (D-256).

Expected: AART binds an isolated credential reference; the macOS Keychain owns value entry, the
screen is lent to its prompt and taken back, and no reset dialog is reachable (`QA-081`/`QA-084`,
`D-229`). The MCP reports only whether the variable is present and never echoes it.

Harness delivery must be one answer everywhere it is said (`QA-078`…`QA-080`, `D-241`):

- [ ] On the review, read the `Harnesses:` line. It names the set and says where it came from —
      every harness this machine measured that the artifact declares support for.
- [ ] Compare it with what **Artifact Details** refused and with what **Success** reports. A harness
      the details screen called unsupported must not appear as a delivery.
- [ ] If **Remediation** lists rows, each must name its own subject rather than repeat one summary.
- [ ] Setup steps are owed only for a harness the artifact actually reached: `dummy-mcp` installed
      into one harness must not produce four `configure harness` rows.

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
