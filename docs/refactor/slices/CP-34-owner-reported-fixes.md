# CP-34 — Owner-reported fixes after 0.12.0

Status: **done**, opened as a PR from `feat/cp-34-owner-fixes`, at the owner's request (2026-10-21): one epic
that collects the fixes the owner reports while using 0.12.0. Each fix is its own step.
Authority so far: Product Specification §178–§183, INV-277, INV-278, INV-279,
INV-280, INV-281, INV-282, INV-283, INV-284, D-456, D-457, D-458, D-459, D-460, D-461, D-462,
D-463.

## Steps

See `docs/refactor/plan.json`, epic CP-34. "Focused verification and the PR" stays last as steps
are added before it.

1. Marketplace pages ten offers, one line each, so More info stays on screen. Done.
3. A Skill, guideline, hook or memory is delivered from the canonical object, with no private
   `aart-cli/` tree beside the harness. Done.
4. Adopting a `kind/name` this Registry took from another upstream is refused, not made its next
   version. Done.
5. The Maintainer adopts such an artifact under another Registry name (CLI `--rename`, TUI
   Registry name row), and its upstream checks follow that name. Done.
6. Marketplace shows Registry and Upstream columns; the Artifact column drops the alias. Done.
7. The `Unset` column becomes `Configuration`: `configured`, or
   `not configured (N missing)`. Done.
8. The Collection Editor filters its artifacts with `/`, keeping hidden ticks. Done.
9. The Collection Editor keeps its Collection after a refusal or Back; no screen numbers in
   messages; a wrong-workspace refusal names the directory and the Registry. Done.
10. Collections name their Registry, and `o` opens them only from a Registry row. Done.
2. Focused verification and the PR. Done.

## Step 1 — Marketplace lists a page of ten

**Why.** With many artifacts, More info could not be read: the list and the More info block were
paged as one stream, so the focused offer's details sat below every offer, off screen. The owner
also asked for one line per offer and no blank lines between offers; the fixed nine-column
Harnesses cell wrapped most rows into two or three lines.

**Change.** `render_marketplace_rows` draws only the page of `MARKETPLACE_WINDOW = 10` offers
that holds the cursor, with `Offers a–b of n; ↑/↓ for more.` when there are more. Columns are
as wide as their widest value over all offers and narrow widest-first only when the terminal is
too narrow. The Marketplace grid uses the whole terminal width rather than `CONTENT_MEASURE`.
Grid rows have no blank lines between them; the stacked layout keeps one (D-456).

**Evidence.** `tests/marketplace_list_window_test.py`: a Hypothesis property over offer counts
0–60 and every cursor position (the drawn offers are exactly the cursor's page, the counter is
there iff more than ten, at grid and stacked widths); a frame with 60 offers and the cursor on
offer 37 shows offers 31–40 and the More info of offer 37 on the first screen; realistic rows
with a long Harnesses cell are one line each, directly under the headings, at their natural
width and wider, and wrap without gaps one column narrower. `marketplace_readable_rows_test.py`
(INV-274) passes unchanged.

Targeted mutations, each restored:
- `MARKETPLACE_WINDOW = 1000` → `test_more_info_of_a_late_offer_is_on_the_first_screen` red.
- the old fixed column widths restored → `test_each_offer_is_one_line_…` red.
- the blank line after every grid row restored → `test_each_offer_is_one_line_…` red.

The Marketplace, TUI, consumer, collection, frame, layout and screen test modules pass (874),
except two `screen_skeleton_test` properties that fail identically on a clean `origin/main`
(B-217).

## Step 3 — one copy where the harness reads

**Why.** The owner saw each Skill twice in a Tabnine project: `.tabnine/agent/skills/<name>`,
which Tabnine reads, and `.tabnine/agent/aart-cli/skill/<registry>/<name>/payload`, which nothing
read. §169.3's private tree was built for every kind, and deliveries were copied out of it.

**Change (D-457, §179, INV-278).** `ArtifactPlacement.shared_payload` is true for every delivered
kind but a plugin. Deliveries and merges name the canonical object's `payload/` as source. The plan
carries it as `PlannedPlacement.payload`, with no copy component, and
`PlacedArtifactReceipt.payload` records it. Containment checks, observation (doctor), removal and
setup effect proofs read that path. MCP servers and plugins keep their tree.

**Evidence.** `tests/shared_payload_e2e_test.py` runs the real CLI: an install writes no
`.claude/aart-cli`, records an object payload that every delivery source lies in, and a doctor
repair review of it is empty. With the Registry disabled, doctor re-delivers a deleted Skill from
the object. Uninstall withdraws the Skill and leaves the object. Four tests that characterized the
old tree were updated: `artifact_placement_resolution_test`, `placed_installation_e2e_test` and
two in `doctor_activity_e2e_test`. A Skill's uninstall is now truly undoable, because it only
withdraws a delivery the retained object restores. INV-192's irreversible half lost its
end-to-end evidence; that is B-218.

Targeted mutations, each restored and each red in `shared_payload_e2e_test`:
- `shared_payload=False` → all three tests red.
- observation of the private tree instead of `receipt.payload` → the install itself fails to
  converge, all three red.
- removal deleting the shared payload → the uninstall test red.


## Steps 4 and 5 — an adopted name belongs to its upstream

**Why.** The owner adopted `skill/brainstorming` from one repository and then a different
`skill/brainstorming` from another. The second became `1.0.1` of the first, because versions are
keyed by kind/name and input digest only. A probe with `scan_repository`, `prepare_adoption` and
`apply_adoption` reproduced it: two adopted records with different URLs on one version line.

**Change (D-458, §180, INV-279).** `recorded_upstreams` and `upstream_conflicts` in
`application/promotion.py` read the upstream each approved version records. `prepare_adoption`
refuses a conflict before writing anything and names both URLs, with `--rename` as the CLI
remedy and the Registry name row as the TUI remedy. `ScannedArtifact.held_by` reports the holder
in the scan (CLI text and JSON, screen 46d). `compile_author_manifests(names=…)` compiles a
manifest under another Registry name with the author's input digest unchanged.
`prepare_adoption(renames=…)` recompiles the scan's pinned acquisition with those names, and
`check_adopted_upstream` always compiles under the Registry name. The CLI adds
`--rename KIND/NAME=NEW-NAME`. Screen 46d adds a typed `name:<coordinate>` row, and the legend
does not offer letter keys while typing.

The check is not in `plan_bulk_promotion`. There it refused three valid
`local_registry_promotion_e2e_test` Source promotions, because one Source records `--source-url`
from the CLI and its local path from the TUI. That is B-219.

**Evidence.** `tests/registry_upstream_name_test.py`, with real Git and a real Registry checkout:
- the same upstream still gets `1.0.1`;
- another upstream is refused, naming both URLs, and the checkout stays clean;
- the scan names the holder;
- a renamed copy is its own `1.0.0` holding the other author's bytes;
- the renamed artifact's upstream check is unchanged, then proposes `brainstorming-official@1.0.1`;
- an invalid, unselected, duplicate or held new name is refused;
- the CLI scan shows `held_by`, a bare adopt is refused with `--rename`, and adopt with `--rename`
  succeeds;
- the composed TUI ports draw the holder and the name row, take typed letters (including `a`) as
  text, and adopt under the typed name.

`maintainer_repository_adoption_test`'s fake port takes the new `renames` argument. The adoption,
promotion, registry, maintainer, Source, authoring and TUI test modules pass (1598), except the two
B-217 properties.

Targeted mutations, each restored and each red in `registry_upstream_name_test`:
- `upstream_conflicts` never conflicts → the refusal, held-name and CLI tests are red.
- the compiler ignores `names` → the rename, check, CLI and TUI tests are red.
- `check_adopted_upstream` compiles without the Registry name → the renamed-check test is red.
- the UI command drops `adoption_names` → the TUI test is red.
- the scan never reports `held_by` → the scan, CLI and TUI tests are red.

## Step 6 — Marketplace Registry and Upstream columns

The owner could not tell two adopted copies apart in Marketplace (§180): the Artifact column was
`alias/kind/name@version`, and nothing said where the work came from. §181/INV-280/D-459.

`marketplace_cells` returns seven cells: `kind/name@version`, the Registry alias, `short_upstream`
of the provenance origin URL (its last two path segments, without scheme, host, port, credentials
or `.git`), then status, scope, harnesses and unset. `MarketplaceArtifactRow.upstream` carries the
origin URL. More info shows it whole as `Upstream`, through `redact_text`.
`render_marketplace_rows(..., keys=)` keys rows by the full offer coordinate, because the first
cell no longer is one. Collections draw `(collection, alias, "", status)`. The grid minimum is now
74 columns. A narrower terminal wraps as §178 says.

**Evidence.** `tests/marketplace_upstream_columns_test.py`:
- `short_upstream` examples (HTTPS, scp-like, ssh with port, credentials, local path, `file://`,
  empty);
- a Hypothesis property: any scheme/userinfo/host/groups URL reads as `owner/repository` and never
  shows its userinfo;
- the seven cells;
- keyed rows draw `kind/name@version` while the cursor and selection follow the full key;
- the composed frame shows both headings and the short upstream on the cursor row, and More info
  shows the whole URL;
- a URL with credentials never shows the token, and More info shows it redacted.

The Marketplace column, window, cursor, readable-row, shell, text-terminal and application E2E
tests were updated to seven columns. The Installed screen still draws the full coordinate. The
Marketplace, consumer, TUI, maintainer, terminal and screen modules pass (1200), with the two
B-217 properties deselected. ruff and mypy are clean.

Targeted mutations, each restored and each red in `marketplace_upstream_columns_test`:
- `short_upstream` returns the URL whole → the property, cells and redaction tests are red.
- the Artifact cell keeps the alias → the cells and frame tests are red.
- `render_marketplace_rows` ignores `keys` → the keyed-rows and frame tests are red.
- More info drops `Upstream` → the frame and redaction tests are red.
- More info shows the URL unredacted → the redaction test is red.

## Step 7 — Configuration, not Unset

The owner found the `Unset` column (`3 not set`) unclear. §182/INV-281/D-460: the column is
`Configuration`, on Marketplace and Installed. It says `configured`, or
`not configured (N missing)` while inputs still hold `AART_NOT_SET`, and is empty for an offer
nothing installs. `configuration_cell` words it for both screens. Column minimums are never below
their headings: Configuration is 13 and Artifact drops to 8, so the grid minimum is 78 and an
80-column terminal keeps the grid. `docs/using/consumer-lifecycle-v1.md` now describes the
Registry, Upstream and Configuration columns.

**Evidence.** `tests/marketplace_configuration_column_test.py`:
- the wording for nothing installed, configured, 1 and 3 missing;
- a Hypothesis property: for any installations' missing counts, the offer is empty, `configured`
  or `not configured (sum missing)`;
- an Installed row's own configuration;
- the heading at 160 and 40 columns, with no `Unset` left.

The Marketplace column, window, readable-row and upstream tests were updated to the new heading
and words. The Marketplace, consumer, TUI, installed, terminal and screen modules pass (904), with
the two B-217 properties deselected.

Targeted mutations, each restored and each red:
- a configured installation says nothing → the wording, property, Installed and cells tests are red.
- an offer nothing installs says `configured` → the property, cells and E2E column tests are red.
- the heading back to `Unset` → the heading and E2E column tests are red.
- Installed ignores its missing inputs → the Installed tests are red.
- the old minimums (Configuration 5) → `marketplace_readable_rows_test`'s grid and width property
  are red.

## Steps 8–10 — Collections are found, kept and placed plainly

The owner asked for search in the Collection Editor. While using it, they started `aart-cli` outside
the Registry checkout and pressed Continue. The editor came back empty, saying "Open a Collection
from screen 51 first", under a refusal about "promotion". With two Registries, nothing said which
Registry `o` opened. §183, INV-282/283/284, D-461/462/463, B-220.

- **Step 8 (D-461).** The editor is searchable. `/` off its text rows opens the Marketplace
  filter. Rows filter by `kind/name` and the form rows stay. Esc clears an applied filter first.
  The cursor lands on the first match when its row is hidden.
- **Step 9 (D-462).** The root cause was `_navigate` making `save` the review's focus. The
  `_KEEPS_FOCUS` pair Collection Editor → Registry Validation fixes the refusal and Back alike.
  `_workspace_refusal` names the launch directory, the Registry and its location, and runs before
  planning in all three preparation paths. Seven screen-number strings are reworded.
- **Step 10 (D-463).** "Collections of Registry ALIAS" and "Saving writes into the Registry
  checkout aart-cli was started in" are on screens 51/52. `o` is offered only on a Registry row.

**Evidence.**
- `tests/collection_editor_search_test.py`:
  - `/` filters and keeps the form, and the cursor lands on the first match;
  - `/` on Name is text, with no `/` in the legend;
  - the legend offers `/` on an artifact row;
  - ticks hidden by the filter are counted (`2 selected`) and both reach `COLLECTION_DEFINE`;
  - Esc clears the filter, keeps the draft, and only then means Back;
  - a Hypothesis property: any query shows exactly the matching artifacts, in order, with the
    form rows.
- `tests/collection_editor_recovery_test.py`:
  - a refused Continue and Back from the review both return to the same Collection, draft and
    ticks;
  - an AST scan of every module finds no non-docstring string naming `screen N`;
  - real Git: another repository is classified `WRONG_WORKSPACE` and refused, naming it, the
    Registry and its location, without the word "promotion";
  - every other mismatch is left to the baseline check.
- `tests/collections_registry_choice_test.py`:
  - with two Registries, `o` on `team` opens team's Collections and says so;
  - the editor names `team` and lists only its artifacts;
  - `o` is not offered, and does nothing, on the workspace row.
- `tests/registry_baseline_diagnosis_test.py`: the real-Git wrong-workspace case now pins the new
  wording.

The maintainer, Registry, promotion, collection, consumer, TUI, screen, local-Registry,
Marketplace, adoption and help modules pass (1496 + the updated diagnosis test), with the two
B-217 properties deselected. ruff and mypy are clean.

Targeted mutations, each restored and each red:
- the rows ignore the query → four search tests are red.
- `/` off text rows does not search → three search tests are red.
- Esc with a filter means Back → the Esc test is red.
- the cursor stays on Name → the filter test is red.
- the legend offers `/` while typing → the text-row test is red.
- the `_KEEPS_FOCUS` pair is removed → both recovery tests are red.
- `_workspace_refusal` never refuses → the unit test and the real-Git diagnosis test are red.
- a screen-number string comes back → the AST scan is red.
- `o` is offered on any row → the registry-row test is red.
- Collections do not name their Registry → the Collections test is red.

## Step 2 — focused verification and the PR

ruff, the format check, mypy, docs-check and secret-shape-check pass. Every test module this epic
added or changed passes (149 tests, 21 subtests), with the B-217 property deselected. The full
suite runs in CI on the PR, not locally (D-317/D-334). The PR title is a `feat`, so the release is
a minor one.
