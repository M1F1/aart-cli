# CP-51 — A plugin's skills are installed with it, and their uses are the plugin's

Status: **done in code and evidence**, on `feat/cp-51-plugin-members`; the PR is next (2026-10-30).
Authority: Product Specification §214, INV-329–INV-331, D-506.

## Steps

See `docs/refactor/plan.json`, epic CP-51.

1. §214, D-506, INV-329–INV-331 and the plan. Done.
2. A plugin's members, read from its package. Done.
3. The installation's receipt records the members. Done.
4. Installed, Details and `consume status` show the members. Done.
5. Activity and telemetry attribute a member's use to its plugin. Done.
6. The lab with superpowers in opencode, then the PR. The lab is done; the PR is next.

## Why

After 0.22.0 the owner tried superpowers in opencode. Activity recorded its skills as "not
installed by aart-cli" and telemetry skipped them. They asked that installing a plugin work like a
Collection, so that what it carries is installed by aart-cli and visible in telemetry. Splitting the
plugin into separate skill artifacts was rejected (D-506): the plugin registers its own `skills/`
directory, so separate copies would load twice, and under names it does not know.

## What changed

- `aart_cli/domain/plugin_members.py` (new, pure): `PluginMember`, `plugin_members`. Members are the
  directories holding a `SKILL.md` below the payload root, named by the directory, less any name
  two directories share.
- `aart_cli/protocol/authoring.py`: `PackagedPlugin.members`, read by `package_plugin` off the
  package's payload.
- `aart_cli/domain/receipts.py`: `PlacedArtifactReceipt.members`, written as `members` only when
  there are any, read back strictly, and two members of one name refused.
- `aart_cli/io/artifact_placement.py`, `aart_cli/application/installation_offer.py`,
  `aart_cli/application/artifact_placement.py`, `aart_cli/application/installation_proposal.py`:
  the members go from the package to the receipt, through the placement and the plan.
- `aart_cli/application/consumer_views.py`:
  - `InstalledArtifactView.members`, from the receipt;
  - `installed_row_cells` counts the members on the row (`superpowers@7.0.0 (2 skills)`).
- `aart_cli/tui_consumer.py`: `render_installed_artifact` names the members ("Skills it carries,
  installed and removed with it: …"), in Details and in `consume status`'s text.
- `aart_cli/commands/marketplace.py`: `consume status --json` items carry `members`.
- `aart_cli/domain/artifact_usage.py`:
  - `InstalledName.member` and `InstalledName.label`;
  - `installed_names` gives each member of a plugin in each harness its settings entry registers;
  - the order includes the artifact and member, so a name two installations answer to resolves the
    same way every time;
  - `rank_usage` ranks by `label`.
- `aart_cli/domain/telemetry.py`: `use_event` sends a member's use as `skill`,
  `<plugin>:<member>`, the plugin's version. The contract, its digests and the server are unchanged.
- `docs/using/consumer-lifecycle-v1.md`: a paragraph on a plugin's skills.

## Evidence

- `tests/plugin_members_test.py` (new, 20 tests):
  - INV-329 as a Hypothesis property over payload paths;
  - members from a real compiled package;
  - receipt round trip, absence and refusal;
  - the Installed row and Details;
  - INV-331 as a Hypothesis property over members, harness and the name used;
  - the ranking and the event document.
- `tests/plugin_installation_e2e_test.py`, through the public command:
  - the receipt records both members, and nothing but `opencode.json` and the tree is written in
    the project (INV-330);
  - `consume status` names the members;
  - a member's use through the real hook entry point is ranked as the plugin's;
  - a skill of the person's own stays unattributed;
  - a sync delivers `skill superpowers:brainstorming 7.0.0` twice.
- Focused runs:
  - 519 tests for placement, receipts, plugins and installation;
  - 548 for Installed, usage, telemetry, consumer views, status, Activity, the consumer TUI and
    Marketplace;
  - the meta tests, `tach check`, ruff, format, mypy and `secret-shape-check`.

### Lab (2026-10-30, `plugin-lab` in the session scratchpad)

The Registry approved the real superpowers 6.2.0 (50 skill files, executable bits kept) as
`company/plugin/superpowers`. This branch's aart-cli then:
1. turned telemetry on to the server on 127.0.0.1:8765;
2. installed superpowers for opencode at project scope, where `consume status` named its 14 skills;
3. turned the opencode usage hook on.

`opencode run` loaded `brainstorming` from the installation's tree, with no duplicate-skill warning.
`consume usage show` ranked `company/plugin/superpowers:brainstorming` as installed. After
`consume telemetry sync` the server held:
- `artifact.installed plugin superpowers 6.2.0`;
- `artifact.used skill superpowers:brainstorming 6.2.0`.

### Targeted mutations

Each was run against the tests named, and each was killed.

| # | Change | Killed by |
|---|---|---|
| M1 | Keep a name two directories share | `plugin_members_test` (duplicate, property) |
| M2 | Accept a `SKILL.md` at the payload root | `plugin_members_test` (root) |
| M3 | Order members by path | `plugin_members_test` (property) |
| M4 | Keep the `payload/` prefix in member paths | `plugin_members_test` (package) |
| M5 | Accept a member whose path does not end in its name | `plugin_members_test` (refusal) |
| M6 | Placement records no members | `plugin_installation_e2e_test` (receipt) |
| M7 | Receipt never writes `members` | `plugin_members_test` (round trip) |
| M8 | Receipt reads `members` back as none | `plugin_members_test` (round trip) |
| M9 | Plan drops members before the receipt | `plugin_installation_e2e_test` (receipt) |
| M10 | Two members of one name accepted | `plugin_members_test` (refusal) |
| M11 | Offer drops members before the plan | `plugin_installation_e2e_test` (receipt) |
| M12 | Installed view takes no members from the receipt | `plugin_installation_e2e_test` (status) |
| M13 | `consume status --json` drops `members` | `plugin_installation_e2e_test` (status) |
| M14 | Row says "skills" for one | `plugin_members_test` (row) |
| M15 | Row counts no skills | `plugin_members_test` (row) |
| M16 | Details name no members | `plugin_members_test` (Details) |
| M17 | `installed_names` skips plugins | `plugin_installation_e2e_test` (use) |
| M18 | Ranking labels a member as its plugin | `plugin_installation_e2e_test` (use) |
| M19 | Telemetry sends a member's use as the plugin | `plugin_installation_e2e_test` (use) |
| M20 | Members named in `claude` instead of the entry's harness | `plugin_members_test` (property) |
| M21 | `artifact_id` as `<member>:<plugin>` | `plugin_members_test` (event) |
| M22 | A plugin's name without its member | `plugin_members_test` (attribution) |

### B-259, resolved here

Turning usage on, by `consume usage enable` or on Settings > Artifact usage, said "Kept only on
this machine … Nothing is sent anywhere." even with telemetry on. `usage_disclosure` now takes
`telemetry_endpoint`, which io reads from the outbox's setting (`io/usage_hooks.telemetry_endpoint`,
empty while telemetry is off, turned off or unreadable). With it on, the line says where each use
of an artifact aart-cli installed is sent, what is sent and that the project is not, and that
`aart-cli consume telemetry disable` stops it. The user guide says the same.
Tests: `tests/artifact_usage_screens_test.py` (`TheDisclosureTest`, the Settings row, and the
command with telemetry on and with it turned off).

| # | Change | Killed by |
|---|---|---|
| M23 | The telemetry sentence chosen when telemetry is off | `artifact_usage_screens_test` (disclosure) |
| M24 | An endpoint kept after telemetry was turned off counts as on | `artifact_usage_screens_test` (turned off) |
| M25 | `consume usage enable` passes no endpoint | `artifact_usage_screens_test` (command) |
| M26 | The Settings row passes no endpoint | `artifact_usage_screens_test` (Settings row) |
| M27 | `read_artifact_usage` reads no endpoint | `artifact_usage_screens_test` (command) |
| M28 | The line no longer says the project is never sent | `artifact_usage_screens_test` (disclosure) |
| M29 | It names `consume telemetry status` as the way to stop it | `artifact_usage_screens_test` (disclosure) |

## Not done here

- **B-260**: attribution from opencode's `metadata.dir`, so a person's own skill with a member's
  name is not the plugin's.
- A plugin installed before CP-51 records its members at its next update or reinstall. No migration
  is written (D-506).
