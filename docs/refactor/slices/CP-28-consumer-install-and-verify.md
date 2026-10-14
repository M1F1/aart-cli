# CP-28 — the consumer install-and-verify journey

Status: **in flight**. Task 1 is on `fix/mcp-smoke-harness-argument` as PR #52, open and unmerged.
Task 2 is on `fix/configuration-after-harness-choice` (PR #55), stacked on it; task 4 on
`fix/one-row-per-installation`, stacked on that. Task 3 waits on the owner accepting the §170
revision; tasks 5 and 6 are not started.

Date opened: 2026-10-14. Authority: the product owner, asking to ship the package inside their
company and to narrow the work to the person who only wants to install artifacts into a harness --
now opencode -- and know they work. Tracked on GitHub as the epic #51, labelled `critical-path`,
whose ordered list is the same as this slice's steps.

## Goal and scope

One person: a consumer who installs an artifact into a harness and wants to know whether it works.
Every step below is something that person hits. Everything that serves an author, a Registry
maintainer or a rollout is off this slice however ready it looks.

Out of scope, deliberately: authoring, Registry maintenance beyond what a consumer reads, the
Enterprise rollout documents (#43, #44, #45), the CLI reference (#47), the secret-name refactor
(#46), branch protection (#35) and module boundaries (#32).

Also off this slice, with a number of their own in the backlog rather than here: the D-375/D-376
cleanup (#54 then #53). It makes the vocabulary say what may be deleted, which matters, but no
consumer install depends on it.

## Steps

**1. Verification works at all (PR #52).** Two defects found by running `mcp test` against a live
Airflow MCP, both fixed with mutation-proven tests:

- **B-173** -- the route started a generated launcher with no arguments, while a launcher carrying
  configuration opens by reading its harness from `$1` and refuses without it. The refusal went to a
  discarded stderr, so the report said only that the process closed mid-exchange. Every installation
  with configuration was affected, which is the whole class.
- **B-174** -- the tool-schema validator refused `description` and `default`, which a real server
  puts on nearly every property, so the declared call was rejected before invocation.

Both VERIFIED end to end on the owner's machine against a live Airflow MCP under tabnine. This is
step one because until it merges, verification is broken for every artifact with inputs, and an
automatic post-install smoke would have nothing to stand on.

**2. Credentials after the harness choice (#50).** They were collected before it, which asked a
new user to decide something they had no basis for yet, and asked it once per *eligible* harness
-- three fields for one value before anyone said which harnesses they wanted. The first screen a
person could not get past. Fixed per D-377: screen 05 offers the harnesses first, the adapter
builds the 07 form only for the chosen ones, and 07 opens from 05's Continue. Scope still follows
the form, which is B-175 and off this slice.

**3. Two stages and a connectivity heuristic (#31).** The scope is settled and narrower than #31
originally proposed: `installation-configuration` and `mcp-startup-and-protocol` run, and a built-in
heuristic over the response answers the connectivity question. The `expect`-based stages are
replaced by it; the three harness-run stages are dropped, because invoking a harness headless and
supplying every variable it needs costs more than the answer is worth. Nothing is declared per
artifact beyond one read-only tool, and no marker list or expectation is maintained by hand. Stages
3 to 7 are removed, not hidden. What CP-28 adds beyond #31 is the post-install run and the ordering:
the smoke happens right after an MCP is installed, and `doctor` can run it in bulk, opt-in.

**4. The installed view reports every entity, and only those (#48).** Installing for two harnesses
drew three entities in User Variables and Credentials: one per harness installation and a third,
empty one named by the bare artifact coordinate. `user_input_artifacts` keyed configuration by the
coordinate while both lookups that fill a row (`configurations_for`, the credential dependants)
key by installation (§169.3), so the coordinate row could never show anything -- and an
installation with configuration but no credential had no row of its own at all. Fixed by keying
configuration by installation too.

**5. Registry connectedness (#49).** A user cannot currently tell whether their Registry is
connected, nor add another one with confidence.

**6. Verification last.** Per D-317 and the owner's standing rule, implementation tasks carry
proportionate focused checks and the full quality, integration and release-facing suite runs once,
on `pr-check`, after they are all complete -- not after each one, and not locally.

## Open question for the owner

Recorded on #51: **#41 before #50, or not at all on this path.** It depends on whether the company
Registry is filled by `registry vendor` -- in which case #41 blocks everything -- or by the native
adopt/promote route, in which case it does not. D-375 settles the product rule in favour of the
native route, so #41 is currently off the path; the question is only whether the company's existing
Registry content was already produced the old way.

## Evidence

Task 1: see `MIGRATION_STATUS.md` under 2026-10-14 for the mutation evidence and the live run.
Task 2: `tests/install_time_config_form_test.py` -- the adapter offers the harnesses with an
empty draft until a valid choice and then a field per chosen harness only; the reducer keeps an
unready answer on 05; 05 without a plan draws only harness rows and continues only once a choice
has its fields; the full drive from Marketplace to Success answers two fields for two chosen
harnesses where it used to answer three. Targeted mutations: dropping the host narrowing turns the
adapter test and the full drive red; dropping the "no plan reviewed yet" condition on opening the
form turns the reducer test and the full drive red. The 1,555 consumer, TUI, install,
configuration, credential and setup tests pass; mypy and ruff are clean. `make mutants` not run:
the changed modules are large enough that a scoped run is hours, and the targeted mutations cover
the new claims.

Task 4: `tests/user_inputs_area_test.py` -- two harness installations of one artifact are exactly
two rows and no `Configuration: none (0 harness file(s))` row. Red before the fix with the bare
coordinate as the only row; reverting the one-line change reproduces that exactly. 787 consumer,
TUI, configuration and credential tests green. The real reader (`read_configuration_files`)
already sets the installation key, so the fix holds outside the test double.

Tasks 3, 5 and 6: none yet.
