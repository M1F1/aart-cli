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

Each row in the TUI's Marketplace starts with the offer as `name@version` and its Type: Skill,
MCP, Guideline, Hook, Memory, Plugin or Collection. Those two columns are all it shows until you
press `d` (Details); `d` again hides the rest. The choice lasts until you quit, and it never
changes what is ticked, what a search matches or where the cursor is. The details are: the Registry
that offers it; its upstream as `owner/repository` (More info shows the whole URL, with credentials
redacted); `not installed`, `installed` or `update available`; where it is installed (`user`,
`2 projects`, or `user + 2 projects`); the detected harnesses that can host it, with `✓` on each
that holds it; and its configuration. Configuration is `configured` when every input has a value,
`not configured (2 missing)` while inputs still hold `AART_NOT_SET`, and empty when nothing is
installed. Both screens draw a rule under each heading.

Installed and Updates use the same grid. Each installation is one row. It shows the artifact as
`name@version`, its Type, the harness it is installed in, and its health. Health is followed by
`→ VERSION` when a newer version is offered. A Collection's members are indented under it.

`d` adds Registry, Scope, Project and Configuration, and `d` again hides them. Installed remembers
this separately from Marketplace. `v` (More info) describes the installation under the cursor in
full: its Registry, harness, scope, the whole project directory, health, each configuration value
(or `not set`), each credential's state (never its value), and the artifact's documentation.

Marketplace labels its columns Artifact and Type, and with `d` also Registry, Upstream, Status,
Scope, Harnesses and Configuration. Each offer is always one line, and the headings drawn are
always whole. In a window too narrow for a value, the value is cut and ends in `…`; a column with no
room at all is left off, and a line under the list names it, as in "Widen the window to see:
Harnesses, Configuration." The offer's name is the last thing cut. Widen the window and everything
is shown whole. PgUp/PgDn scroll content in short windows while the headings and navigation footer
remain. `v` shows the focused offer's full provenance, security,
compatibility, digests and declared input guidance in Marketplace; there is no separate Artifact
Details screen. Search, cursor and marked offers stay intact. `i` installs marked offers, or the
focused offer if none is marked. Enter on a Collection still opens its member preview.

An artifact may name its own documentation: a longer manual, how to get its credentials, or how to
configure it. When it does, More info shows the link as `Documentation`, whole on one line so it
can be copied. The same link is printed next to each credential and configuration value the
artifact asks for, in Credentials and variables, and by `consume list` and `consume install`. An
artifact that names none shows no link.

### Default or Custom

After Install, the TUI asks for a path. **Default** takes the harnesses, the scope and the Python
installer from Settings and goes straight to what still needs entering, or to Ready. With no
harness chosen in Settings, it uses every detected harness that can host the artifact. Default
installs exactly what Settings says or nothing: when a Settings harness is not detected or cannot
host a selected artifact, the Settings scope is not offered for it, or the Settings Python
installer cannot be used, the Install Path screen lists each of those values with the artifact and
the reason, and moves the cursor to Custom. **Custom** asks each choice in turn. `consume install` names its harnesses with `--profile`, so the CLI has no path choice.

## MCP setup and credentials

A v2 recipe and its package-root `SETUP.md` are compiled before AART plans an installation effect.
Review shows effects, capabilities, entrypoint, trust, and the manual route without secrets.

A person types each credential into the credential store's own prompt, in the TUI or in a terminal.
An agent never supplies one. AART never writes credentials to a registry, state, JSON output, or
logs. Registries may use safe placeholders such
as `${GITHUB_PERSONAL_ACCESS_TOKEN}`; container images should be pinned by digest.

### Answering inputs on the command line

`consume install` and `consume update` take an artifact's ordinary inputs as flags. Each flag
names the artifact with its Registry alias, and its answer goes into every installation of that
artifact the command creates. An input you leave out takes its declared default.

A credential is never a flag. The review lists each credential the credential store will ask for,
with what it is and where to get it (`review.asked_by_credential_store` in `--json`). When you
apply the review with `--yes` in a terminal, the store's own prompt asks for each one, and AART
never sees what you type.

```sh
aart-cli consume install company/mcp/github --profile claude --input company/mcp/github:github-org=platform-team
aart-cli consume install company/mcp/github --profile claude --input company/mcp/github:github-org=platform-team --yes
```

Without a terminal, for example when an agent runs it, `--yes` refuses and changes nothing. The
agent can install with `--set-later` instead. That stores `AART_NOT_SET` in every required input
nobody answered. You then set each credential yourself with `consume inputs set-credential`
(below), or in the TUI's Credentials and variables.

```sh
aart-cli consume install company/mcp/github --profile claude --input company/mcp/github:github-org=platform-team --set-later --yes
```

`consume update` keeps what the installation already holds. Each value in the configuration file
aart-cli wrote for that installation is used again, if the new version still declares the input
and still accepts the value. A flag replaces it. `--set-later` never writes `AART_NOT_SET` over a
value. An update asks only for an input the new version adds, a value the new version refuses, or
one that was set later. In the TUI, screen 16 asks for these with the same form as screen 07. A
value is kept only for that same installation: another harness, scope or root collects its own.
If you edited the file by hand, aart-cli no longer recognises it as its own, and the update asks
again.

If a required ordinary input is missing and there is no `--set-later`, the command refuses. It
lists the exact flag for each missing input (`inputs[].flag` in `--json`). Credentials need a
credential store, which today is the macOS Keychain.

### Setting values after install, from the command line

`consume inputs` changes an installed artifact's configuration and credentials without the TUI.
It uses the same steps as Credentials and variables. Each command names one installation by the
artifact, the harness, and the scope. For a project installation, `--project` gives its
directory.

`list` shows each installation's values and credential states. It also prints, for each missing
value, the exact command that sets it. Add `--json` for an agent.

```sh
aart-cli consume inputs list company/mcp/github
```

`set` changes one ordinary value. Run it first without `--yes` to review the change and get its
`review_digest`. Then run it again with `--yes --expect` and that digest to apply exactly that
change. Configuration is not a credential, so it may be given on the command line or pasted to an
agent.

```sh
aart-cli consume inputs set company/mcp/github github-org=platform-team --harness claude --scope project
aart-cli consume inputs set company/mcp/github github-org=platform-team --harness claude --scope project --yes --expect DIGEST
```

`set-credential` stores or replaces a credential, and never takes its value. Run it in a terminal.
aart-cli hands the terminal to the credential store, and you type the value into the store's own
prompt. An agent can run it or give it to you, but it can never supply the value. Without a
terminal it changes nothing and prints the command to run.

```sh
aart-cli consume inputs set-credential company/mcp/github github-token --harness claude --scope project
aart-cli consume inputs set-credential company/mcp/github github-token --harness claude --scope project --yes --expect DIGEST
```

When the name matches more than one installation, nothing changes. The command lists each match
with the flags that select it. Run `consume inputs list` again to check a change. Deleting a
credential nothing uses any more is done in the TUI.

### Checking installed MCPs

`consume mcp test` is a read-only verification command for installations that already exist in one explicit
scope, root and harness set. It does not install, update, repair, configure, synchronize or publish.

To test one installed MCP in this project and harness, name it as `consume inputs` does,
`ALIAS/KIND/NAME`, with `@VERSION` when you want only that version to count. A version that is not
the installed one tests nothing and names the installed one:

```sh
aart-cli consume mcp test company/mcp/github --harness opencode --scope project --project "$PWD"
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

### Which skills and MCPs are used

Activity also ranks the skills and MCPs your agents actually use, per harness. A small hook in the
harness records the harness, the skill or MCP server's name, the project and the moment, and never
what a tool was called with, a prompt or an answer. It is kept in `~/.aart-cli/state/activity.sqlite3`,
readable only by you, and nothing is sent anywhere.

Nothing is recorded until you turn it on, unless your organisation's build of aart-cli records in
some harnesses from the start (its release variable `AART_CLI_DEFAULT_USAGE_HARNESSES`); the TUI
then says so on its first start, and Settings turns it off. In opencode the hook is the file
`~/.config/opencode/plugins/aart-cli-usage.js`. In Claude Code it is one entry in
`~/.claude/settings.json`, beside your own hooks, which it leaves in place. Tabnine has no hooks and
cannot record.
**Settings > Artifact usage** has one row per harness, and when the cursor is on a row the screen
says what that row changes.

The same from the command line: show what records and the ranking, turn Claude Code on, then turn it
off and delete what it recorded.

```sh
aart-cli consume usage show
aart-cli consume usage enable --harness claude
aart-cli consume usage disable --harness claude --forget
```

`consume usage forget --harness opencode` deletes what was recorded and keeps recording.

### Telemetry

Telemetry sends your organisation's telemetry server what aart-cli installs, updates and removes,
and each recorded use of an artifact aart-cli installed, so the organisation sees which artifacts
are used, how often and by how many installations. Unless you or your build turn it off, it also
sends each use of a skill or MCP aart-cli did not install, by the name the harness used, so the
organisation sees which other tools people use.

If your organisation's build of aart-cli names a server (its release variable
`AART_CLI_TELEMETRY_ENDPOINT`), telemetry is on from the first `aart-cli` or `consume` command, and
that command says so once. The public build names none, so telemetry is off until you turn it on.
Turning it on, either way, also sends what Activity already holds: each install, update, removal and
recorded use is sent once, however often telemetry is turned on.

```sh
aart-cli consume telemetry enable --endpoint https://telemetry.example.com
aart-cli consume telemetry status
```

Without `--endpoint`, `enable` uses your organisation's server. To keep anything from being sent,
run `aart-cli consume telemetry disable` as your first command; that choice is kept, and no later
start turns telemetry on again. An event holds the
event's kind, the artifact's kind, name and version, the moment, a random installation id drawn when
you turn telemetry on, and aart-cli's version. It never holds a project, path, argument, prompt,
Registry address, user or host name, or credential. A use of something aart-cli did not install is
sent as its own kind of event, with the name the harness used and no version: a skill's name, an
MCP server's name in Claude Code, and in opencode the whole tool name, because opencode does not say
where the server's name ends.

Whether those uses are sent is in Settings, under Telemetry: *Uses of tools aart-cli did not
install*, which you can change at any time. Until you do, your build decides (its release variable
`AART_CLI_TELEMETRY_UNMANAGED_USES`; unset sends them). Turned off, such uses still waiting are never
sent. The same from the command line:

```sh
aart-cli consume telemetry unmanaged off
aart-cli consume telemetry unmanaged on
```

`consume telemetry status` says whether they are sent and whether that is your choice.

Events wait in `~/.aart-cli/state/telemetry.sqlite3`, readable only by you. When something new is
recorded and ten minutes have passed since the last successful send, a short-lived process sends
what waits and exits; there is no background service. A server that cannot be reached is tried
again later, backing off up to 30 minutes, and nothing you do waits for it or fails because of it.

```sh
aart-cli consume telemetry sync
aart-cli consume telemetry disable --forget
```

`--forget` deletes what waits, what was sent and the installation id, and keeps telemetry off.

`sync` sends now. `disable` stops recording and sending and keeps what waits, unsent; `--forget`
also deletes it and the installation id.

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
