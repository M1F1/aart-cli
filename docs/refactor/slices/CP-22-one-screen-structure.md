# CP-22 — One screen structure, and the third manual run

Status: OPEN — 4 OF 9 STEPS DONE

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

5. **Registries, Sources, Candidates and the other lists.** The rows alone; the empty-state
   guidance and the per-screen explanation into the view status.

6. **Forms and sequences: Add Registry, Add Source, Initialize Registry, Repository Scan, Registry
   Rebuild.** These carry three kinds of text — the fields, an introduction above them, and the
   line saying what a key press does (`action_prompt`, `D-` chain from `QA-029`). **Open question,
   to be settled on a concrete frame with the operator before the step is written:** whether the
   introduction drops below the rule with the rest of the prose, or whether a form's introduction
   is the one named exception.

7. **Review and result screens.** The same split, where "actions" is the decision being offered and
   "status" is what the review is about.

8. **`QA-085` — a lab that lost its marker.** `reset_lab` now removes the marker last and the
   refusal prints a recovery that works. Still open: there is no supported way to clear a lab
   directory that has already lost it.

9. **Full quality gate, and the operator's third manual run** over `QA-044`…`QA-087`.

## Evidence discipline

Each screen step ends with the frame rendered before and after, read off the real composition
rather than described, because the finding is about what the screen looks like. The operator's
standing instruction is that we talk about concrete views: *"musimy rozmawiac zawsze o konkretnych
widokach"*.
