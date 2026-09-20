# Using an installed AART

## Consumer lifecycle

Every mutation uses the same review and finalize boundary. Without `--yes`, a command renders its
reviewed plan only; `--yes` finalizes that exact plan. `--json` changes only rendering, never
selection, consent, effects, or exit semantics.

```sh
# Explicit source refresh
aart-cli source sync --alias company --json

# Review, then finalize
aart-cli marketplace install company/skill/code-review --profile claude --json
aart-cli marketplace install company/skill/code-review --profile claude --yes --json

aart-cli marketplace status --profile claude --json
aart-cli marketplace update --profile claude --yes --json
aart-cli marketplace update --profile claude --prune --yes --json
aart-cli marketplace uninstall company/skill/code-review --profile claude --yes --json
```

An empty `marketplace update` selects every installed artifact in the given profile and scope.
After `source sync`, status distinguishes `current`, `update_available`, `removed_upstream`,
`source_unavailable`, and `local_drift`. `--prune` removes only the reviewed items outside the
authoritative selected set.

An artifact can declare `requires`. Direct install and update calculate a deterministic transitive
closure before review; an unavailable or conflicting dependency cannot create a partial install.

### Finding an artifact without reading the whole list

`list` prints everything. On a catalog of any size, the way to find one artifact is to type part
of it:

```sh
aart-cli marketplace search review
aart-cli marketplace search review python --json
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

## MCP setup and credentials

A v2 recipe and its package-root `SETUP.md` are compiled before AART plans an installation effect.
Review shows effects, capabilities, entrypoint, trust, and the manual route without secrets.

A human supplies credentials in an approved interactive session. AART never writes them to a
registry, state, JSON output, or logs. Registries may use safe placeholders such as
`${GITHUB_PERSONAL_ACCESS_TOKEN}`; container images should be pinned by digest.

### Checking installed MCPs

`mcp test` is a read-only verification command for installations that already exist in one explicit
scope, root and harness set. It does not install, update, repair, configure, synchronize or publish.

```sh
# One exact installed coordinate in this project and harness
aart-cli mcp test company/mcp/github@1.0.0 \
  --harness opencode --scope project --project "$PWD"

# Every installed MCP for two user-scope harnesses
aart-cli mcp test --all --harness opencode,claude --scope user --json
```

The report keeps installation/configuration, MCP protocol, optional output expectation, external
service, model provider, and harness route as separate stages. `PASS` for a tool invocation does
not prove the tool reached its external service: that stage needs the manifest's `reaches_service`
claim *and* a declared `expect` that holds, and it reports `NOT CONFIGURED` when the manifest makes
no such claim. A missing declaration, credential or executable is also visible and cannot produce
an aggregate pass. Reports do not retain configuration values, secrets, raw service payloads or
harness transcripts.

### Verifying through your harness, which you run yourself

AART does not launch a harness or submit a prompt to one. The harness leg is optional and you run
it:

```sh
# 1. Get the prompt: which installations, which tool per installation, and the report shape
aart-cli mcp test --all --harness claude --scope user --prompt

# 2. Paste it into your own harness session. It writes aart-cli-smoke-report.json.
#    The session can check its own output first:
aart-cli mcp report aart-cli-smoke-report.json

# 3. Grade what came back, alongside the direct checks
aart-cli mcp test --all --harness claude --scope user --report aart-cli-smoke-report.json
```

The report only *carries* the observation. Each tool result it holds is graded by the same
deterministic evaluator the direct route uses, and the model's English assessment stays a separate
stage that cannot establish protocol success or service access. Because AART did not watch the
session, this evidence is declared as coverage `direct-and-attested` and never counts as direct
evidence; what makes it hard to fabricate is the declared `expect`, which asks for a value only the
real service returns. Supplying no report is an honest `NOT RUN`, never a failure of the direct run.

The manifest's `read_only: true` is a reviewed server/tool contract; it is not an operating-system
sandbox for arbitrary startup code, and the prompt's restrictions are instructions to your
assistant rather than something AART enforces.

## Reading, checking, and undoing a setup

Every setup run writes a complete account of itself — the plan hash, the installer hash, when it ran,
how it exited, and one receipt per step. Three actions read that account after the run is over.

```sh
# What did the run actually do?
aart-cli marketplace receipt show company/mcp/github --profile claude --json

# Is any of it still true?
aart-cli marketplace receipt verify company/mcp/github --profile claude

# Reverse it — review first, then finalize
aart-cli marketplace receipt undo company/mcp/github --profile claude
aart-cli marketplace receipt undo company/mcp/github --profile claude --yes
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

All three are also reachable from `aart` with no arguments, under **Action → receipt**.

### One report for the whole machine

The three commands above each answer a question about one installation. `aart-cli doctor` answers them
for everything at once, and reads only — it resolves no marketplace content and applies nothing.

```sh
# What is the state of everything installed here?
aart-cli doctor
aart-cli doctor --json
```

One run reports measured drift with the smallest policy-permitted repair plan for each item; offline
readiness for every enabled source, as three separate answers — cached metadata, cached canonical
payload, cached runtime dependencies — because `--offline` is one flag and those are three different
reasons it can fail; any working copy an interrupted run left behind; the activity trail and what
each entry can still undo; credential health and which installations depend on it; and the
configuration this machine is ignoring, meaning disabled sources and fields your organization's
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

## Accepted smoke revision — implementation pending

D-365 revises the behavior above: harnesses without enforceable allowed tools receive direct MCP
checks only; the excluded harness stage does not fail direct coverage. Eligible harnesses return
a bounded English JSON assessment (`status`, `summary`, `possible_error`) within 120 seconds.
The assessment is separate from protocol and service evidence. Default-off `--show-response` will
permit bounded inspection of the server response in current output, without application persistence.
These revised behaviors are specified in Product Specification §170 and still need implementation.
