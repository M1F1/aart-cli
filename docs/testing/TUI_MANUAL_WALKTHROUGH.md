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

Findings go to [`manual-acceptance.md`](manual-acceptance.md), in the format it describes.

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

CP-23 task 14 (D-271): with nothing subscribed and no workspace there is no row, so there is no
cursor. The status says the project is not a Registry; press `v` and *Connected Registry snapshots*
joins it as status, not as a description.

- [ ] Press `n` (**Initialize**). The form has five rows; `↑`/`↓` move between them, typing edits
      the focused one, `Backspace` deletes, `Space` toggles a choice, `Enter` advances.
- [ ] Check that the legend follows the cursor (D-269). On a text field it offers `[Type] Edit`,
      `[Backspace] Delete`, `[Enter] Next`, `[↑/↓] Move` and `[Esc] Back`, with no `v`, `?` or `q`.
      Typing `v`, `?` or `q` there puts that character in the field. On **Local commit** it offers
      `[Space] Local commit`. On **Continue** it offers `[Enter] Continue` and `v`, `?` and `q`
      again; `?` opens Help from the form.

| row | what to enter |
|---|---|
| Registry ID | `manual-registry` — a slug, this is the name coordinates are built from |
| Display name | `Manual Registry` — what people see |
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
Registry snapshots* block is no longer empty. Each subscribed registry is a `> ` cursor row with its revision,
snapshot and promotions shortened under it. Press `v`: the rows stay exactly as they were, and the
description below them spells out the digests of the registry under the cursor (D-271).

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
rows, and the focused value is readable in full (`QA-030`). The column heading is flush left and each
row starts with the `> ` / blank gutter inside its first column (D-271).

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

A Source whose Candidate history was recorded at another revision than the snapshot it has pinned
shows `Attention` and lists no Candidates. `aart-cli source sync` produces exactly that, because the
consumer refresh moves the pin and writes no Candidate history — writing it is Maintainer
authority. It takes a minute to prove, and it is the failure the first released version could not
recover from (issue #8, D-280 to D-282):

- [ ] Push a commit to one author repository, then refresh it from outside the screens:

```sh
aart-cli source sync
aart-cli doctor
```

Expected: `aart-cli doctor` exits non-zero and its `Candidate history` section names the Source, the
revision its history was recorded at, the revision now pinned, and the remedy — `run Source Sync on
<alias> to rebuild its Candidate history`. Every other Source, Candidate and Registry still loads.

- [ ] Do what it says: **Sources** → that Source → `s` (**Sync**), and confirm.

Expected: the Source reports the new commit and its Candidates are listed again; `aart-cli doctor` exits
zero and its `Candidate history` section is gone. Nothing under the data root is edited by hand.

## 6 — Review a Candidate

- [ ] Open a Candidate. Press `d` (**Diff**), then `v` (**Fast / Verbose**) to fold the bounded
      redacted file diffs in and out (`f` does nothing here). `r` on the
      Candidate opens its **Lifecycle**.

Expected: facts, decisions and the one line telling you what a key press will do are visually
separated, with the action prompt last (`QA-029`).

## 7 — Validate and promote

- [ ] From the Candidate, reach **Validation**. Press `Enter` on a check to open it, then `Enter`
      again for **Policy review** (CP-23 task 04: `p` does nothing on Validation).
- [ ] On **Validation**, the checks are `> ` cursor rows under a `Checks` heading; the verdict is the
      status above the legend, and `v` describes the check under the cursor (D-271).
- [ ] On **Candidate filters**, the values are rows and `Showing N of M` is the status. With no
      Candidate at all there is no row and the legend offers no `Space/Enter` toggle.
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
- [ ] Go back to **Candidates**. The Candidate you just committed reads **Promoted locally**, not
      New, Ready or Published (CP-23 task 09, `D-259`).
- [ ] Open its promotion review. It refuses: already promoted in the local checkout, so publish
      that commit with Git, then run Registry Sync. Bulk promotion does not offer it either.
      Bulk promotion's Candidates are `> ` cursor rows under their registry; what cannot be
      promoted reads `Not promotable: …` in the status, never as a row (D-271).
- [ ] Quit and reopen the TUI. The same Candidate still reads **Promoted locally**.

## 8 — Publish the promotion yourself, in Git

This step changed again. `D-228` once had AART push a reviewed commit to a review branch from this
screen; the product owner reversed that for the TUI (Product Specification 164.7, `D-249`), and
CP-23 task 05 removed it (`D-255`). The supported `aart-cli registry push` CLI is unchanged — this
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
- [ ] After Registry Sync and then Source Sync, the Candidate reads **Promoted** and its earlier
      history is still listed on the Candidate lifecycle screen (`r`).

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

- [ ] On **Marketplace**, press `v` for Verbose. Below the list's rule, the row under the cursor is
      described: Artifact, Kind, Version, Source and its approved Description (a Collection row
      shows what it Includes). Move the cursor and it follows; search it away and nothing stale
      remains; `v` again hides it.
- [ ] **Marketplace** → `Enter` on the Skill opens **Artifact Details**. It lists **Eligible
      installation harnesses** (Claude, OpenCode, Tabnine for the lab Skill) and, separately, any
      detected harness that is not eligible. No unselected harness appears under *What it needs*.
      There is no `Actions: select, install, verbose.` line. The footer shows `[Space] Select`:
      press it, the status reads `Selected for installation.` and the label becomes Deselect. `Esc`
      back to Marketplace keeps the tick on that row (D-261).
- [ ] From **Artifact Details**, `i` starts the install without any Marketplace tick, and screen 05
      offers exactly the harnesses Details called eligible. `Esc` out of it.
- [ ] **Marketplace** → select the Skill → `i` (**Install**). Screen 05 lists Claude, OpenCode and
      Tabnine as unticked rows even when only one is eligible. Read the selection summary, tick one
      harness with `Space`, then **cancel once** with `Esc`.
- [ ] Confirm nothing was written. Return to the install, choose **OpenCode and Tabnine together**,
      and continue. The status must read `Installing into: opencode, tabnine` before Continue opens
      the next step.
- [ ] Install `dummy-mcp`, choosing **OpenCode and Tabnine together**. At the provider prompt,
      enter **disposable test text only**.
- [ ] On **Success**, the choices are rows: `View installed`, `View receipt`, `Done`. The
      outcome above them has no bracketed buttons. `View receipt` opens the receipt of **this**
      install (its `Recorded:` time), not an older one. `Esc` and `Done` both land on
      **Marketplace**; `Esc` must never show Installing or Ready again. No Undo row is offered: the
      screen says why (D-256).

Expected: AART binds an isolated credential reference; the macOS Keychain owns value entry, the
screen is lent to its prompt and taken back, and no reset dialog is reachable (`QA-081`/`QA-084`,
`D-229`). The MCP reports only whether the variable is present and never echoes it.

Harness delivery must be one answer everywhere it is said (`QA-078`…`QA-080`, `D-260`):

- [ ] Before choosing, the footer offers no `[Enter]` and the status says to choose at least one
      harness. Once a tick has been re-prepared, `[Enter] Continue` appears (D-270). In Verbose,
      moving the cursor names the artifacts that each harness can host. Unticked harnesses remain
      eligibility, not planned delivery.
- [ ] On **Ready**, the `Harnesses:` line names exactly the chosen set and says it was chosen for
      this installation. Compare it with **Artifact Details** and **Success**. An unsupported or
      unselected harness must not appear as a delivery.
      Where the plan stores a credential, Ready counts `credential(s) stored securely` once; where
      the credential already exists, it says nothing is stored (D-272).
- [ ] On **Ready** for an MCP install, the counts must be reconcilable with what you asked for
      (D-284): `1 launcher(s) written` and one `configuration file(s) written` per chosen harness --
      never `2 launcher(s) written` for one server. For the Skill, the deliveries are named as
      harness files, never as `other change`.
- [ ] Where a Python dependency could be installed by either backend, **Remediation** offers it
      once, naming the backend that will run (D-283), not `pip` and `uv` as two changes.
- [ ] While the installation runs, the screen names the step running (`▸`) and the ones already
      done (`✓`), counting `(n of m done)`, inside the same frame as every other screen (D-285).
      A short install may pass quickly; `dummy-mcp` into two harnesses is the one to watch.
- [ ] After the Skill install, inspect the project: both
      `.opencode/skills/manual-check/SKILL.md` and
      `.tabnine/agent/skills/manual-check/SKILL.md` exist; `.claude/skills/manual-check` does not.
- [ ] After each MCP install, inspect the project. OpenCode is registered only in `opencode.json`
      under `mcp`; Tabnine is registered only in `.tabnine/agent/settings.json` under `mcpServers`.
      No unchosen MCP settings file gains `dummy-mcp`.
- [ ] If **Remediation** appears, it says what AART will change after the final review, and each
      change names its own subject. `Continue` is its row, never `[ Continue ]` text. A Skill that
      only configures a harness goes straight to **Ready**, which lists that change (D-258).
- [ ] Installing `dummy-mcp`: **Required Inputs** shows, in Fast, `Disposable dummy credential —
      needed by manual-registry/mcp/dummy-mcp@1.0.0`, what it is for, `Get it: Nothing issues it;
      make up disposable text …` and its format (D-263).
- [ ] When the Keychain asks, the same lines appear just above its prompt. The screen is released,
      nothing is drawn over the footer, and it ends with `macos-keychain asks for it next. Type it
      there; AART never sees or keeps it.` Type disposable text only.
- [ ] Installing `dummy-mcp` first stops on **Required Inputs** as a form, before the review
      (D-265). `dummy-user` is prefilled with `lab-user` but is not accepted until you press
      `Enter` on it, so Continue does nothing before that. Pasting disposable text shaped like a
      token is refused on the field with `looks like a credential`, and the text itself is not
      drawn. The credential is listed separately, under Credentials.
- [ ] On that form, the block above the rule holds only `Configuration`, the field rows with what
      each says under itself, and `Continue`. The introduction and the Credentials section,
      guidance included, are the status below the rule in Fast. `v` on Continue leaves the rows
      exactly as they were; with the cursor on a field, Verbose describes its binding (D-270).
- [ ] If the lab offers a **Collection**, its details show only the summary (Includes, what you will
      need, `N / M selected`) with no member rows and no `N selected` twice. `Enter` opens the
      Contents, where members are `[x]` rows ticked with `Space`, and unticking one adds
      `Warning: Custom selection` to the status (D-270).
- [ ] After installing into OpenCode and Tabnine, the artifact's installed root has
      `config/opencode.conf` and `config/tabnine.conf` holding `dummy-user=…`. No
      `config/claude.conf` exists, and the value appears nowhere under the lab's AART data or
      state (D-264).
- [ ] Setup steps are owed only for a harness the artifact actually reached: `dummy-mcp` installed
      into one harness must not produce four `configure harness` rows.

## 12 — Inspect

- [ ] **Installed** → artifact details. **Credentials** → the reference and its dependants.
- [ ] **Credentials** → a credential → Enter (**Credential Action**). Verify and Replace are rows,
      and Delete is absent while something uses it. The `[Enter]` label follows the cursor, and
      `v` describes the focused row below the list.
- [ ] On **Verify**, Enter reports health with `Checked just now; nothing was changed.` under a
      trail ending `/ Verification`. Enter goes back to the credential.
- [ ] On **Replace**, Enter opens **Review Replacement**, which names every installation using it
      and says no copy is kept. Esc returns to Credential Action with nothing prompted. The trail
      fits on one line: the middle places read `…`, and the area and Credential Action stay
      (D-272).
- [ ] Credential Details states the provider, health and dependants with no `Actions:` sentence;
      the legend is what offers `[Enter] Open`. Installed artifact and Collection details do the
      same.
- [ ] Confirm the review. The provider (Keychain) asks in this terminal; type disposable text only.
      It lands on Credential Details with `Replaced <input> in <provider>.`, and no frame shows the
      value (D-262).
- [ ] **User variables and credentials** lists installed artifacts. Open `dummy-mcp`: its
      **Configuration** section shows `dummy-user` per harness with `matched`, and its
      **Credentials** section shows the token's health only, never a value (D-266).
- [ ] Edit one harness's file by hand, then reopen the area. That harness reads
      `changed outside AART`, and an edit of it is refused until you put the file back.
- [ ] On `dummy-user`, `Enter` opens **Choose Configuration Harnesses** with every installed
      harness ticked. Untick all of them: `Enter` does not advance. Tick only Tabnine, then
      **Continue**. The field opens holding Tabnine's current value, not yet accepted (D-273).
      Clear it with `Backspace`, type a new disposable value, press `Enter` on it, then
      **Continue**. On that edit form the artifact, `Harnesses:` and the explanation are the status
      below the rule, not rows (D-270). Ticking harnesses that hold different values opens the field
      empty, and the status lists what each one holds.
- [ ] The review reads `Change dummy-user for …` and `tabnine: <old> → <new>`, with no other
      harness and no review identity until `v` (D-273). Confirm it. Back on the area, Tabnine shows
      the new value `matched` while OpenCode keeps the old one. Only `config/tabnine.conf`
      changed on disk, and **Activity** records `Reconfigured` without the value (D-267).
- [ ] Repeat with both harnesses ticked, which changes all of them. Ask the MCP from each harness:
      each reports its own `user:` value.
- [ ] Delete the dummy token from the Keychain, then open it from the area. **Credential Action**
      offers `Verify` and `Set`, not `Replace`. `Set` → review → confirm lends the terminal to the
      Keychain with the authored briefing above its prompt. Type disposable text only; it lands
      with `Set <input> in <provider>.` and verifies (D-267).
- [ ] **Doctor** → health, offline readiness, activity, configuration.
- [ ] **Activity** → what actually happened, with real provenance. Each entry is a row under its
      day with the cursor on one. `v` shows that entry's review identity below the rows rather
      than widening every row (CP-23 task 14).

Automated preflight for this walk (D-274): `tests/frame_matrix_test.py` records all 74 declared
Consumer and Maintainer screens plus search, Help, quit, form, refusal and failure states. It checks
every cursor in Fast and Verbose against the shared frame, key, literal-input and `v` laws, and
checks the same composed frame through text and curses terminals, including clipped footer
retention. This does not check off the manual observations above; task 15 still requires the owner
to walk them.

Expected: Dashboard, lists, help and footer have a readable hierarchy with visible focus
(`QA-035`/`QA-038`/`QA-040`/`QA-041`/`QA-042`).

## 13 — Repair, update, remove

- [ ] Break an installed file by hand, then **Doctor** → `r` (**Repair issues**). Minimal repair only.
      The repairable issue is a row with the cursor on it, and healthy artifacts and counts are
      listed below the rule, so it is clear which issue `r` acts on.
- [ ] Publish a `1.0.1` from the maintainer side and check **Updates** → `i`.
- [ ] **Installed** → artifact → `u` (**Uninstall**).
- [ ] **Registries** → `d` (**Disconnect**) — reviewed and bounded (`QA-050`).

Checkpoint for Act II:

- [ ] Nothing installed, repaired or removed without a review you could cancel.
- [ ] Disconnecting a Registry removed the subscription and nothing else.
- [ ] Doctor's account of the machine matched what you actually did.

---

## CP-23 acceptance — what closes the slice

CP-23 is IMPLEMENTED, and its full gates and the frame matrix are recorded in the slice. It becomes
VERIFIED only when this walk passes in your lab and your terminal; no agent runs it. Walk Acts I
and II in order and check these links of the chain, each at the step that owns it:

- [ ] **Source → Candidate (steps 4–5).** Sync explains itself after Add Source. Candidates is a
      table with the row under the cursor described only in Verbose.
- [ ] **Candidate → local commit (steps 6–7).** `v` folds diffs; there is no `f`, `d` guidance, or
      `p` on Validation. The commit is receipted, and the Candidate reads **Promoted locally** after
      a restart.
- [ ] **Manual publication → Registry Sync (steps 8 and 10).** The TUI never pushes. It says to
      publish with Git, then sync.
- [ ] **Marketplace → selected-harness install (step 11).**
  - The focused description shows in Verbose.
  - Artifact Details `i` works.
  - Harnesses are chosen explicitly, one or several.
  - Remediation says what changes.
- [ ] **Guided credential entry (step 11).** Screen 07 and the lent terminal show the author's help
      in the same words. The value never appears on screen or in AART's data.
- [ ] **Success and receipt (step 11).** `View installed`, `View receipt` and `Done` are rows that
      work.
- [ ] **Credential lifecycle (step 12).**
  - Credential Action rows Verify, Replace and Delete when unused; 24a is named **Review
    Replacement**, **Review Deletion** or **Verification**.
  - The provider asks, and Details has no `Actions:` sentence.
  - Configuration edits open on the held value and review `harness: old → new`.
- [ ] **On every screen you pass:**
  - the trail fits one line;
  - `v` changes only the presentation;
  - every key in the footer does what it says;
  - a narrow or short terminal keeps the whole footer.

File anything that fails as a CP-23 finding in [`manual-acceptance.md`](manual-acceptance.md). When everything passes,
record it in the slice's task 15 evidence and mark CP-23.15 done.

---

## When you are done

```sh
make manual-test-reset
```

Removes only this marker-owned lab, after checking `.aart-manual-lab.json` and the exact absolute
root. It refuses an unmarked directory.

Then move confirmed items in [`manual-acceptance.md`](manual-acceptance.md) from *Fixed — awaiting
retest* to *Confirmed*, and file anything new in *Open*.
