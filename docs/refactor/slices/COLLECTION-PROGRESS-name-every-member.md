# COLLECTION-PROGRESS — Installing a Collection names every member while it runs

**Status:** done (released with the PR that carries it). §203 amended; D-524.

## Why

Installing a Collection of MCP servers drew only `Installing (6 of 7 done)` and never named a
member. `project_running_installation` folded the step reports by step number. Every member of a
transaction numbers its own plan from one, so each member's reports overwrote the one before. With
more than one artifact, the heading lost its name too.

## What was done

- `project_running_installation(reports, members)` (`aart_cli/application/consumer_views.py`):
  - keeps a step by artifact and number;
  - attributes each `RunningStepView` to its artifact;
  - holds one `RunningMemberView` per member, with its own done and total. A member is waiting,
    running, or ends as its worst step.
- `ConsumerActions` passes the reviewed transaction's `flow.artifacts`, so a member not reached yet
  is listed.
- `render_running` (`aart_cli/tui_consumer.py`), with more than one member:
  - the heading reads `Installing N artifacts (k of N done)`, and every member is named;
  - the running member shows its count and steps;
  - a member that applied is one line, with its steps under More info;
  - one that failed or was not attempted keeps its steps.
- One artifact is drawn as before.

## Evidence

The new tests:
- `tests/collection_inputs_tui_e2e_test.py`, `test_while_the_collection_installs_each_member_is_named`.
  The real shell installs a Collection of two MCP servers and keeps every frame the heartbeat would
  beat over. The first running frame names `▸ company/mcp/github` and `· company/mcp/jira`. A later
  frame names `▸ company/mcp/jira`, and the last names `✓ company/mcp/github`.
- `tests/installation_progress_test.py` covers the projection:
  - two members with the same step numbers keep their own steps;
  - a member not reached is waiting;
  - a member's status is its worst step;
  - one artifact has no member list.
- `tests/running_installation_screen_test.py`, `CollectionRunningScreenTest`: the exact lines for
  three members, and More info keeping a finished member's steps.

Gates:
- Focused: 950 TUI, consumer, install, progress and Collection tests pass.
- ruff, ruff format, mypy and tach pass.

Targeted mutations:

| Mutation | Result |
|---|---|
| Steps keyed by number alone again | killed (10 tests, the e2e among them) |
| `members` not passed from `ConsumerActions` | killed (the e2e) |
| `render_running` ignores `members` | killed (3 tests) |
| A member is never running | killed (3 tests) |
| `running or` dropped from the steps condition | survived. It was equivalent, because a running member is not `applied`. The condition was removed. |

## Left

The first Installing frame still says "Nothing has run yet." until the first step is reported.
