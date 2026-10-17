# Using an installed AART

## Consumer lifecycle

Every mutation uses the same review and finalize boundary. Without `--yes`, a command renders its
reviewed plan only; `--yes` finalizes that exact plan. `--json` changes only rendering, never
selection, consent, effects, or exit semantics.

```sh
# Explicit Registry refresh
aart-cli consume registry sync --alias company --json

# Review, then finalize
aart-cli consume install company/skill/code-review --profile claude --json
aart-cli consume install company/skill/code-review --profile claude --yes --json

aart-cli consume status --profile claude --json
aart-cli consume update --profile claude --yes --json
aart-cli consume update --profile claude --prune --yes --json
aart-cli consume uninstall company/skill/code-review --profile claude --yes --json
```

An empty `consume update` selects every installed artifact in the given profile and scope.
After `consume registry sync`, status distinguishes `current`, `update_available`, `removed_upstream`,
`source_unavailable`, and `local_drift`. `--prune` removes only the reviewed items outside the
authoritative selected set.

An artifact can declare `requires`. Direct install and update calculate a deterministic transitive
closure before review; an unavailable or conflicting dependency cannot create a partial install.

### Finding an artifact without reading the whole list

`list` prints everything. On a catalog of any size, the way to find one artifact is to type part
of it:

```sh
aart-cli consume search review
aart-cli consume search review python --json
```

Every word must match, so a second word narrows the answer rather than widening it. Matching is
case-insensitive substring over the name, the coordinate, the summary, and collection membership:
`review` finds `code-review`. The best matches come first -- a name that *is* the word, then a
name that starts with it, then a name that holds it, then a coordinate, then a summary -- and rows
that tie keep catalog order, so two runs over one catalog print one order. The coordinate printed
is the one `install` takes.

The TUI searches the same way. In the list of artifacts press `/` and keep typing: the list
narrows as you type, Enter keeps the filter and hands the arrows back, Escape drops it. In the
text fallback the same thing is a line: `/review` shows the matching rows, `/` on its own lists
everything again. A filter only hides rows -- what was ticked stays ticked, and every row keeps
the number it has in the full list.

### What a Marketplace row says

Each row in the TUI's Marketplace is the offer, then: `not installed`, `installed` or
`update available`; where it is installed (`user`, `2 projects`, or `user + 2 projects`); the
detected harnesses that can host it, with `✓` on each that holds it; and how many inputs are still
`AART_NOT_SET`. Installed draws each installation on its own row, with its health, scope, project
and unset inputs. In Installed, More info adds the project's directory and harness.

Marketplace labels its columns Artifact, Status, Scope, Harnesses and Unset. Long values wrap;
narrow windows use the same labels as stacked fields. PgUp/PgDn scroll content in short windows
while the headings and navigation footer remain. Arrows move between logical offers regardless
of how many lines each occupies. `v` shows the focused offer's full provenance, security,
compatibility, digests and declared input guidance in Marketplace; there is no separate Artifact
Details screen. Search, cursor and marked offers stay intact. `i` installs marked offers, or the
focused offer if none is marked. Enter on a Collection still opens its member preview.

### Default or Custom

After Install, the TUI asks for a path. **Default** takes the harnesses, the scope and the Python
installer from Settings and goes straight to what still needs entering, or to Ready. With no
harness chosen in Settings, it uses every detected harness that can host the artifact; when the
chosen ones cannot host it, the harness choice is asked after all. **Custom** asks each choice in
turn. `consume install` names its harnesses with `--profile`, so the CLI has no path choice.

## MCP setup and credentials

A v2 recipe and its package-root `SETUP.md` are compiled before AART plans an installation effect.
Review shows effects, capabilities, entrypoint, trust, and the manual route without secrets.

A human supplies credentials in an approved interactive session. AART never writes them to a
registry, state, JSON output, or logs. Registries may use safe placeholders such as
`${GITHUB_PERSONAL_ACCESS_TOKEN}`; container images should be pinned by digest.

### Checking installed MCPs

`consume mcp test` is a read-only verification command for installations that already exist in one explicit
scope, root and harness set. It does not install, update, repair, configure, synchronize or publish.

To test one exact installed coordinate in this project and harness:

```sh
aart-cli consume mcp test company/mcp/github@1.0.0 --harness opencode --scope project --project "$PWD"
```

To test every installed MCP for two user-scope harnesses:

```sh
aart-cli consume mcp test --all --harness opencode,claude --scope user --json
```

The report gives each installation two stages. `installation-configuration` checks that the
receipt, launcher, configuration file and credential references are usable. Missing credentials
and ordinary or secret `AART_NOT_SET` placeholders yield `NOT CONFIGURED`, the CLI returns
nonzero, and the server never starts. Providers that cannot be inspected remain `BLOCKED`.
When installation configuration does not pass,
`mcp-startup-and-protocol` is `NOT RUN`. `mcp-startup-and-protocol` starts the installed launcher,
checks the protocol, and makes the one declared call. Its `PASS` does not prove the tool reached
its external service. A missing declaration, credential or executable is visible and cannot produce
an aggregate pass. Reports do not retain configuration values, secrets or raw service payloads.

### Testing right after an install

When an install in the interactive application made at least one MCP installation, Success offers
**Test installed MCPs**. Choosing it shows what will run first: each installation, its declared
tool and arguments, and that the call reaches the configured service with that installation's
credentials. Nothing runs until you confirm. The result is the same two stages as `consume mcp test`.
Whatever it says, the install, its receipts and its success are unchanged. Declining the offer is a
complete installation.

The manifest's `read_only: true` is a reviewed server/tool contract; it is not an operating-system
sandbox for arbitrary startup code.

## Reading, checking, and undoing a setup

Every setup run writes a complete account of itself — the plan hash, the installer hash, when it ran,
how it exited, and one receipt per step. Three actions read that account after the run is over.

```sh
# What did the run actually do?
aart-cli consume receipt show company/mcp/github --profile claude --json

# Is any of it still true?
aart-cli consume receipt verify company/mcp/github --profile claude

# Reverse it — review first, then finalize
aart-cli consume receipt undo company/mcp/github --profile claude
aart-cli consume receipt undo company/mcp/github --profile claude --yes
```

`show` renders the persisted record. `verify` asks this machine whether each receipt's claim still
holds: does the image tag exist and still resolve to the recorded id, does the managed block still
carry the text that was installed, does the Keychain item exist **and hold a non-empty value**. A
claim it cannot ask is reported `unknown` rather than `true`, and `verify` exits non-zero when any
claim is false, so it is usable from CI. It reports and never repairs — an orphaned run directory is
named and left where it is.

`undo` is a mutation, so it follows the same boundary as everything else: without `--yes` it prints
the effects it would reverse and changes nothing. `--expect <digest>` binds the decision to the exact
undo that was read.

The review names what it will **not** reverse, and why, before you approve it:

```text
Review undo: company/mcp/github#claude/project
reverses: Keychain item service='aart-github' account='token'
  step    3
  module  macos-keychain.store@1
  reason  deletes the Keychain item this run created
reverses: /Users/you/.zshrc
  step    2
  module  file.managed-block@1
  reason  restores the file to the block it held before this run
keeps: aart/mcp/github:1.0.0
  step    1
  module  docker.build@1
  reason  the tag named an image before this run, so it is not removed — but it now points
          at what this run built, and the receipt never recorded the earlier image id, so
          the undo cannot restore the original binding
Undo: reverses=2, keeps=1
Reviewed only; re-run with --yes to apply this exact undo.
```

Steps are numbered in the order the rollback runs them, which is the reverse of the order they were
applied — so the review reads top to bottom in the order you will watch it happen.

A step whose receipt no longer matches the reviewed plan is reported and skipped, never forced. On
partial success the record is written back as `rollback_incomplete`.

All three are also reachable from `aart-cli` with no arguments, through **Activity** and its receipt details.

### One report for the whole machine

The three commands above each answer a question about one installation. `aart-cli doctor` answers them
for everything at once, and reads only — it resolves no marketplace content and applies nothing.

```sh
# What is the state of everything installed here?
aart-cli doctor
aart-cli doctor --json
```

One run reports measured drift with the smallest policy-permitted repair plan for each item; offline
readiness for every enabled Registry, as three separate answers — cached metadata, cached canonical
payload, cached runtime dependencies — because `--offline` is one flag and those are three different
reasons it can fail; any working copy an interrupted run left behind; the activity trail and what
each entry can still undo; credential health and which installations depend on it; and the
configuration this machine is ignoring, meaning disabled Registry subscriptions and fields your organization's
policy has locked.

Repair follows the same review-then-confirm boundary as everything else, one artifact at a time:

```sh
# Review one artifact's minimal plan — applies nothing
aart-cli doctor --repair company/mcp/github

# Apply exactly the plan that review returned
aart-cli doctor --repair company/mcp/github --yes --expect <digest>
```

`--yes` without `--expect` is refused, and a machine that changed between the review and the
confirmation returns the recomputed plan instead of applying the stale one. There is no flag that
repairs everything.

What it cannot repair, it still reports: an artifact whose payload is missing or divergent is named
with what is wrong, rather than being omitted because no repair for it exists.

## Reset and restore

Run `aart-cli reset` when local AART state is invalid, belongs to another version, or should be
started over. Review the named paths and confirm `RESET AART`, or use `aart-cli reset --yes`.
AART moves the state by rename into `<application-home>-backups/<UTC timestamp>/` and prints
the backup directory. For the default home this is `~/.aart-cli-backups/…`; `AART_CLI_HOME`
selects the corresponding home and sibling backup location. No secret values live in that home.

`aart-cli reset --restore <backup-directory>` backs up the current state first, then moves the
chosen backup back into the home. Restoring a state another version wrote is for running that
version; this build does not migrate it. Projects, organization policy and harness files are
untouched. Installed artifacts remain in their harnesses, but a fresh AART state no longer records
them. Factory reset is separate from uninstalling artifacts.
