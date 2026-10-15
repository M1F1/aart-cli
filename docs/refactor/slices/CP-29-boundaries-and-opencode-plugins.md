# CP-29 — module boundaries as data, and OpenCode plugins as an artifact kind

Status: **in flight**. Steps 1–2 are done on `feat/cp-29-tach-and-opencode-plugins`.

Date opened: 2026-10-15. Authority: the product owner, after the 0.7.0 release: *"zajmij sie teraz
kolejnym CP w ktorym wdrozysz Tach i ogarniesz pluginy do opencode jako nowy rodzaj artefaktu
sprawdzajac go na superpowers ponadto sprawdzisz setup superpowers uzywajac skilli i memory i
przetestujesz go"*. The goal behind it: an enterprise fork of
[obra/superpowers](https://github.com/obra/superpowers) that a company installs into opencode
through aart-cli.

## Goal and scope

Two things, in order.

1. **#32: module boundaries as data.** tach goes into the dev group, `tach.toml` records the import
   graph the package has, and a `tach` gate refuses any edge the file does not declare.
2. **superpowers in opencode, two ways.**
   - First with what aart-cli already installs: the skills as Skill artifacts, and the bootstrap as
     Memory.
   - Then as a new artifact kind, an OpenCode plugin. The fork's plugin is installed as reviewed,
     vendored bytes. opencode does not fetch it from git at startup.

Out of scope: deleting the hand-written boundary tests in favour of tach rules (#32 step 3); the
import cycles tach found (B-186); plugins for harnesses other than opencode.

## Steps

**1. tach (#32 steps 1, 2 and 4, D-404).**
- `tach==0.35.3` is pinned in the dev group.
- `tach.toml` lists every top-level module of `aart_cli`, with `depends_on` written by `tach sync`
  and read by hand.
- `python scripts/quality.py tach` and `make tach` run `tach check`. The gate is part of
  `QUALITY_GATES`, so it runs in `pr-check` on every supported interpreter.
- Evidence:
  - an `aart_cli.io` import planted in `domain` turned the gate red, with nothing else red;
  - `tests/tach_config_test.py` holds that every top-level module is declared and that `domain`
    reaches only what `architecture_boundary_test.py` allows;
  - removing a module's entry turned the coverage test red.

**2. superpowers with Skills and Memory.** An enterprise fork's skills become Skill artifacts, and
the `using-superpowers` bootstrap becomes Memory (AGENTS.md). Both are installed into opencode from
a local Registry and checked live in the owner's opencode.

*Done, 2026-10-15.*

The fork:
- is superpowers 7.0.0 (`bb92a77`), with fifteen `skills/<name>/` trees;
- each tree carries an `aart-cli.yaml` (`skill/v1`, `include: ["**"]`, `exclude: [aart-cli.yaml]`);
- `memory/superpowers-bootstrap/` carries an OpenCode adaptation of what the upstream plugin
  injects: check skills first, the tool mapping, and how a `superpowers:<name>` reference meets an
  installed name.

The run, all in a throwaway `AART_CLI_HOME`, with an invented author:
- `author check` reported 16 manifests promotable;
- `registry init`, `scan`, `promote` ×16, `publish`, then `source add --kind registry-local`;
- `marketplace install --profile opencode <16 coordinates> --yes` succeeded.

Placement:
- skills went to `.opencode/skills/<name>-company-project/`, with every subfile (`scripts/`,
  `references/`, examples);
- `name:` in each frontmatter was rewritten to match the directory;
- the bootstrap went into `AGENTS.md` between the aart-cli memory markers.

Live evidence, opencode 1.18.29 with `opencode/big-pickle`:
- `opencode debug skill` lists all fifteen in the project and none in a control project with no
  install;
- asked to add a feature, the session in the project quoted the AGENTS.md instructions and called
  the native `skill` tool on `using-superpowers-company-project`. The control found no skill to
  load.

Found on the way:
- D-405: `**` reaching a directory was refused, so a skill tree could not be declared by a glob.
  Fixed, with tests.
- Installed skill names carry the installation suffix, so upstream cross-references
  (`superpowers:writing-plans`) no longer match a name exactly. The fork's bootstrap says how to
  read them. An upstream-faithful name is a plugin concern (step 3). A live run asking the session to follow
  `superpowers:writing-plans` hung without output (killed after ten minutes), so that reading is
  unverified.
- B-187: opencode `hooks` merge into a key opencode does not accept.

**3. Specify the plugin kind.** A specification amendment covering:
- what an OpenCode plugin is to aart-cli;
- vendored and digest-pinned, registered by local path rather than a git spec;
- high-risk execution on Ready;
- no install-time dependency fetch;
- opencode V1 (`plugin`) and V2 (`plugins`) registration;
- uninstall and verify.

*Done, 2026-10-15: §171, INV-255–257 and D-406.* V2 `plugins` is out of scope, as D-406 records.

**4. Implement the plugin kind end to end.**

*Done, 2026-10-15 (D-407).*
- **The kind is in every canonical set.** It is `plugin`, `aart-cli.dev/plugin/v1`, payload format
  `aart-cli-plugin-v1`, effects copy-tree and merge-json. The legacy profile path is untouched.
- **Authoring.** `plugin.entry` names a `.js`, `.mjs` or `.ts` module the payload carries. The
  field is refused on other kinds. A root `package.json` with runtime dependencies is refused, and
  so are `inputs`. `author init --kind plugin` writes a compiling skeleton.
- **Domain.** `PluginEntry` is a `./` path and nothing else. `SettingsListEntry` is a hook's or a
  plugin's entry, and the `settings_entry_*` functions own one member of a list. Merging a plugin
  entry is `high-risk-execution`. `PluginTarget` measures opencode at project and user scope.
- **Placement.** `_plugin_settings` writes one settings entry and no delivery. The status and
  uninstall scope view, and the harness projection, read settings entries.
- **Evidence.**
  - `tests/plugin_entry_test.py`, `tests/plugin_authoring_test.py`,
    `tests/plugin_installation_e2e_test.py`, plus the extended `installation_harness_choice_test`.
  - The plugin e2e covers install, review, status, drift, uninstall and the refusal of an
    unmeasured harness.
  - 571 tests across the kind, install and lifecycle suites are green, as are lint, typecheck,
    format-check, docs-check and tach.
- **Targeted mutations, each red only in its own tests.**
  - Risk as a configuration mutation turned the risk and review tests red.
  - `dependencies` dropped from the refused keys turned the dependency test red.
  - Removing the scope view's plugin branch turned the status and uninstall e2e tests red.
  - Removing the inputs refusal turned the inputs test red.
  - Removing settings from the harness projection turned its projection test red. Before the test
    was extended, that mutation survived.

**5. superpowers as a plugin.** The fork is installed through aart-cli and checked live.

**6. Full verification** (D-317), once steps 1–5 are done.
