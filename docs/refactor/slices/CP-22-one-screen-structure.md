# CP-22 — One screen structure, and the third manual run

Status: OPEN — 15 OF 16 STEPS DONE

## Goal

CP-21 gave every screen one skeleton and the operator walked it again. The verdict was that the
skeleton is real but the screens still do not fill it the same way: *"kazdy widok powinien miec ta
strukture … bo teraz co widok jest inaczej mam wrazenie"*, and *"to powinno byc w kodzie zeby nie
bylo zbyt wielu wyjatkow od reguly"*.

That is not a request for tidier screens. It is a request to move the arrangement out of the
screens entirely, so that a screen written tomorrow is arranged by the type it fills rather than by
whoever writes it. The exceptions are to be few and named, not emergent.

## Product Specification authority

- 161.1 and INV-187: navigation and presentation remain understandable and safe.
- 161.4: a screen states what it is, what it offers and what state it is in, without the reader
  having to derive any of the three.

## The structure, as the operator drew it

```
AART / Dashboard / <where this screen sits>
✓ Registry Maintainer → ▸ Init Registry → · Review Init     (only while walking a sequence)

────────────────────────────────────────────────────────────────

   what the cursor can act on: rows, toggles, commands

────────────────────────────────────────────────────────────────

   what the cursor is on right now                          (Verbose only, QA-070)

────────────────────────────────────────────────────────────────

   the state of the whole view: counts, guidance, what failed

────────────────────────────────────────────────────────────────

   (the terminal's blank space)

working at /private/tmp/aart-cli-manual-lab/consumer-project
────────────────────────────────────────────────────────────────

   the keys this screen accepts, and no key it does not
```

The rule the operator stated by name is the seam between the second and fourth blocks: **"nigdy
akcja i menu do wyboru nie powinno byc w jednym bloku z statusem widoku"**. A reader scanning for
something to press should not have to read prose to find it, and prose standing between two rows
reads like a row.

## Findings

| Item | Surface | State |
|---|---|---|
| QA-085 | A lab that loses its marker can be neither reset nor set up over | partly landed |
| QA-086 | `working at` floated above the terminal's blank space instead of sitting on the footer | landed, `D-242` |
| QA-087 | Every view fills the skeleton differently; actions and view status share a block | in progress |
| QA-088 | A form described in prose the keys the footer directly below it advertises | landed |
| QA-089 | A row glued its own explanation onto itself, so five choices read as five sentences | landed |
| QA-090 | A confirmation screen never said what it was confirming | landed |
| QA-091 | A screen with no rows still drew its report inside the actions block | landed, `D-244` |

## Steps

1. **`working at` is the footer's caption (`QA-086`).** DONE — `f43e9ff`, `D-242` revising `D-235`.
   `render` draws it flush on the footer rule and `footer_start` reaches back over it, so the
   terminal's padding lands above the caption and a clipped body keeps it.

2. **The skeleton is a type, not a call convention (`QA-087`).** DONE — `4869c10`.
   `Frame` names the blocks and its field order *is* the layout; `render` derives the arrangement
   from `dataclasses.fields` so no second place can disagree. The claims are properties over
   generated frames rather than examples: blocks drawn whole and in declared order, a rule only
   between two blocks that both spoke, text touching a rule only under a caption, the footer block
   being the caption and everything after it, anchoring inserting nothing but blanks, and the keys
   holding the bottom rows at any height.

3. **The screen source answers blocks rather than lines.** DONE — `D-243`.
   `ConsumerScreenSource.lines` returned one undifferentiated body, which is the hole the prose
   kept falling through: a screen had nowhere to put "what this view is" except the block the
   cursor rows live in. It is `actions` now, `status` carries the rest, and
   `tests/screen_block_structure_test.py` holds it over every screen with `MIXED_SCREENS` naming
   the nine that still mix. That list is the enforcement — without it this slice is a convention
   again — and nothing may be added to it.

4. **Dashboard and Maintainer Dashboard.** DONE — `D-243`.
   The navigation rows alone in the actions block; the first-run guidance and the installed
   counts are one `status` that picks between them rather than a panel that replaces the body;
   the maintainer overview and the unavailable-composition notice likewise. `Navigation:` and
   `Maintainer navigation:` are gone, because a block whose contents are the navigation does not
   need to announce that it is the navigation.

5. **Screen 21 Registries.** DONE. The `[ Add Registry ]` row alone, with connected registries as
   rows below it; what a registry *is* and what this machine *has* are answers to different
   questions, so both went to the view status, the second only while there is nothing connected.
   This is the screen the operator drew.

6. **Screen 27 Settings.** DONE. The four toggles alone, keeping the group headings that organise
   them — a heading is how rows are arranged, not prose about them. What the Maintainer Mode
   toggle currently implies is a consequence of a setting rather than a setting, so it is view
   status: `settings_consequence`. A sentence standing under four toggles reads like a fifth.

7. **Screen 29 Doctor.** DONE. `doctor_rows` is one row per artifact with whatever drifted on it;
   `doctor_status` is the counts, what repair would do, and Verbose's independently-repairable
   list — all facts about the set rather than about any row. `render_doctor` composes both plus
   the title for the command line, which has no blocks to put them in; the TUI drops that title,
   since the trail already says where this is (`QA-077`).

8. **Screen 46 Registry Maintainer.** DONE. The screen has two subjects and rows for only one of
   them, so `maintainer_registry_rows` is the subscribed snapshots under the heading that
   introduces them — and nothing at all when nothing is subscribed, since a heading over nothing
   is the empty section `QA-065` reported. `maintainer_registry_status` carries what connected
   snapshots are for, what is missing while nothing is subscribed, and the local checkout whole.
   `render_maintainer_registries` still composes both for the command line.

9. **Screen 22 Add Registry.** DONE. The operator settled the open question on the rendered frame:
   *"Wszystko pod pola (jak reszta)"* — a form is not an exception and `Frame` gains no block above
   the rows. `_body` returns the five fields and nothing else; `_REGISTRY_ADD_INTRO` holds what
   connecting a registry does and what it does not change; `_form_prose` wraps that in
   `action_prompt` so the key line stays last with a blank above it, and `status` answers with it
   ahead of the per-screen cases. `QA-029` was preserved by moving the prompt's block, not its
   position.

10. **Screen 31 Add Source**, **11. Screen 46a Initialize Registry**, **12. Screen 46c Scan
    Repository**, **13. Screen 46h Rebuild Registry.** DONE. The same split step 9 settled: fields
    alone in the actions block, every explanatory line below the rule, the key prompt last. Five
    screens saying one rule is a table rather than five branches, so `_form_prose` reads
    `_FORM_PROSE` — screen to introduction and the one line addressed to the reader — and a sixth
    form adds a row instead of a shape of its own. The sentences `161.7` and `164.7` require where
    a run stops changed block with the rest and are held there by name, since prose that moves is
    prose that can be lost. `MIXED_SCREENS` is now empty; the assertion on it stays, because an
    empty set that something asserts on is what stands between a future exception and nobody
    noticing.

13a. **A key is advertised, not described (`QA-088`).** DONE. Moving each form's prose below the
    rule put four keys described in a sentence directly above a legend that advertised two of
    them, and the operator read it back: *"duzo z tego powinno byc w klawiszach u dolu a nie w
    informacji"*, then *"ta informacja jest zbedna: Enter reviews the run under the cursor"*. The
    sentence is gone from all five forms. `key_bindings` now gives a form `[Type] Edit`,
    `[Backspace] Delete` and `[Enter] Next / continue`, and `_FORM_TOGGLE_LABELS` names what Space
    changes on each screen that has something to change — a shared "Toggle" would have dropped the
    only word that said what the key is for. This is the canonical structure's last line read
    strictly: *the keys this screen accepts, and no key it does not* — and, now, no key said twice.

13b. **A row is the choice; the explanation follows the cursor (`QA-089`).** DONE. Screen 46h's
    rows read `Lock only: pin everything the registry references` -- the choice and its purpose in
    one line, so five things to choose between could not be scanned as five things. The operator
    drew it apart and named where the purpose goes: *"z czego to wyjasnienie powinno oczywiscie byc
    collapsed albo uncollapsed jak sie klika v"*. The labels are bare now and `description`
    answers `REGISTRY_STAGE_PURPOSE` for the row under the cursor, so `[v]` opens and closes it
    like every other cursor description (`QA-070`). The whole-sequence row names its four stages in
    its own label and so says nothing here, which costs the block rather than drawing an empty one.

14. **Review and result screens.** DONE. Reading the reviews back showed a worse fault than the
    one this step was opened for: between a filled-in form and an irreversible action, every review
    drew exactly one line — *"Press Enter to connect this registry."* — over a legend that already
    offered `[Enter] Confirm`. It said nothing about what was about to happen, which 161.4 forbids
    (`QA-090`). `_review_facts` now states the subject from the draft the reader just filled in:
    which registry from where and whether it becomes the default, which Source at which location,
    which registry is created and whether the files are committed, which stage a rebuild runs, what
    a refresh fetches and what it leaves alone. A stopped run replaces that rather than joining it,
    because the plan it described was discarded when the run stopped (`QA-033`).

    The result screens then settled the other half by rule rather than by list (`QA-091`, `D-244`).
    A result, a review and a refusal have no rows, so there is nothing for a cursor to act on and
    everything they draw is the state of the view — which `actions` reads off the row model
    instead of off a set of named screens. That is the operator's own constraint applied to the
    fix: *"zeby nie bylo zbyt wielu wyjatkow od reguly"*. The notice reads last there, under the
    line that says it is coming.

15. **`QA-085` — a lab that lost its marker.** DONE. Two halves. A lab stops arriving here:
    `reset_lab` empties the root and removes the marker only once nothing else is left, so a
    removal that fails partway through always leaves a lab that is still owned and still
    resettable — a single `rmtree` walks in directory order and could unlink the marker first.
    And a lab that is already unmarked has a way out: refusing stays right, because an unmarked
    directory is not the tool's to delete, but the refusal now prints `chmod -R u+w <root> && rm
    -rf <root>` with the exact path, and `docs/testing/END_TO_END_ACCEPTANCE.md` carries the same
    line under *If the lab loses its marker*. The `chmod` is not decoration: an installed payload
    is delivered read-only, directories included, so `rm -rf` alone stops at the first artifact
    root. The test runs both commands against a real read-only lab — the blunt one to show it
    fails, then the printed one — so the recovery is checked rather than described.

16. **Full quality gate, and the operator's third manual run** over `QA-044`…`QA-087`.

## Evidence discipline

Each screen step ends with the frame rendered before and after, read off the real composition
rather than described, because the finding is about what the screen looks like. The operator's
standing instruction is that we talk about concrete views: *"musimy rozmawiac zawsze o konkretnych
widokach"*.
