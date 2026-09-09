# CP-10 — Production MCP stdio vertical slice
Status: VERIFIED

## Goal

Install a real Python MCP server end to end through the canonical path: source-tree payload,
artifact-owned Python environment, declared runtime inputs, a generated launcher that resolves
secrets from the provider at launch, one real harness registration, verification, and a receipt.
Then prove AART is not in the runtime path.

## Product Specification sections/invariants

Sections 6–9, 47, 53–56, 97–100, 113–115, 143; INV-046, INV-058–INV-066 (runtime projection and
harness), INV-100 (runtime independence), and the CP-07/08/09 invariants they build on.

## Legacy/current paths

- `profiles/builtin.py` holds measured harness targets: Tabnine MCP merges into
  `.tabnine/agent/settings.json` under `mcpServers`, Claude into `.mcp.json`. That knowledge is
  real and stays; only the mechanism moves.
- `setup_render.py` and `setup.py` own the current launcher and settings rendering.
- `lifecycle/application.py` owns the current merge behaviour.
- No canonical launch contract exists: `domain/artifacts.py` has no entrypoint or transport.

## Target paths/owners

`domain/launch.py` for the launch contract, transport and POSIX shell quoting; `domain/harness.py`
for the harness registration value; `domain/receipts.py` for what an installation recorded;
`application/runtime_projection.py` for pure launcher generation; `io/harness.py` for the settings
merge interpreter.

## Dependencies

CP-07 planning, CP-08 inputs and credentials, CP-09 environments are verified.

## Non-goals

- No Docker or OCI distribution (B-003).
- No reconciliation, drift or repair (CP-11/12).
- No TUI (CP-13/14).
- No transport other than stdio.
- No harness beyond the first real adapter; the rest follow the same value.

## Characterization / RED evidence

RED covered: a launcher that contains no secret value; a launcher that invokes the artifact-owned
interpreter and nothing else; a config value carrying shell metacharacters that stays data; a
harness registration that leaves every neighbour untouched; and verification that reports drift
rather than passing when nothing could be measured. Both new test modules failed at import before
any implementation existed.

## Implementation steps

1. `domain/launch.py`: `Transport`, `LaunchContract`, `shell_quote`, `launcher_path`.
2. `application/runtime_projection.py`: pure generation behind `CredentialResolutionPort`.
3. `domain/harness.py` and `io/harness.py`: measured targets and a merging interpreter.
4. `domain/receipts.py`: `InstallationReceipt` and `ConfigFingerprint`.
5. `application/installation_verification.py` and `io/runtime_projection.py`: findings and the
   observation they compare against.
6. E2E: a real stdio MCP server installed and spoken to through its own generated launcher.

## Property tests

`shell_quote` round-trips arbitrary text through a real `/bin/sh` (`printf '%s\0'`, compared
byte-for-byte). No arrangement of secret and config inputs puts a provider value in the file.

## Integration tests

`tests/harness_registration_test.py` merges into real settings files: neighbours preserved,
permissions preserved, unparseable JSON reported, a non-map server map refused, unregister removing
exactly one entry. `tests/installation_verification_test.py` observes real launchers, real
interpreter symlinks and real settings files.

## E2E/live acceptance

`tests/mcp_stdio_e2e_test.py` creates a real virtual environment with `python -m venv`, writes a
real MCP server into the payload, generates and writes the launcher, merges the Tabnine
registration, then reads the command back out of the settings file and executes it with
`env={"PATH": "/usr/bin:/bin"}` — nothing inherited. It exchanges `initialize`, `tools/list` and
`tools/call` as newline-delimited JSON-RPC and asserts on what the server reports about itself. The
macOS test repeats the whole flow against a real temporary Keychain.

## Done

- CP-10 opened from verified commit `5488622`.
- `domain/launch.py` holds the declarative contract and the POSIX quoter. `LaunchContract` names a
  payload-relative entrypoint and literal arguments only, so anything varying per installation has
  to be an input and therefore reviewed.
- `application/runtime_projection.py` generates the launcher purely. A secret becomes a command
  substitution supplied by the provider port (D-022); a config value becomes a quoted assignment; a
  stdin binding is refused because the transport owns stdin (D-023) and a file binding is refused
  rather than written (D-024). An unrecognised binding is refused rather than assumed.
- `io/runtime_projection.py` writes launchers only inside the artifact that runs them, mode 0700,
  and re-digests the file after writing — so what the harness will execute is what was reviewed.
- `domain/harness.py` carries the measured Tabnine and Claude Code targets (D-025); `io/harness.py`
  merges without disturbing anything it did not put there (D-026).
- `domain/receipts.py` records launcher digest, interpreter, credential references and config
  fingerprints (D-027).
- `application/installation_verification.py` names six ways an installation drifts, in a fixed
  order, and treats an unmeasurable launcher as drift (D-028).
- Runtime independence is proven negatively: the launched server reports
  `importlib.util.find_spec("agent_artifacts") is None`, and its `sys.executable` is the
  artifact-owned interpreter.
- The real Keychain path is proven end to end on macOS: a 256-bit token stored in a temporary
  keychain reaches the launched process, and only its SHA-256 is ever asserted on.

## Remaining

- Routing the public install/repair flow through this projection is CP-12, which is where
  reconciliation owns lifecycle. CP-10 delivers and proves the vertical slice; it does not yet
  replace `setup_render.py` as the path a user's command takes.

## Known compromises

- File-bound secrets are refused rather than materialized (D-024, B-019).
- The launcher is POSIX `sh`, so there is no projection on Windows (B-021, pairs with B-017).
- `$(...)` strips trailing newlines from a provider value (B-022).
- Only Tabnine and Claude Code targets are canonical; OpenCode and Vibe stay in the legacy profile
  until measured (B-020).

## Backlog discoveries

- B-019 — file-bound secrets in a generated launcher.
- B-020 — measured MCP targets for OpenCode and Vibe.
- B-021 — a launcher for a platform without a POSIX shell.
- B-022 — provider values whose trailing whitespace is significant.

## Blockers

None.

## Legacy removal criteria

`setup_render.py` and the legacy launcher/settings rendering stay until CP-12 routes install,
repair and uninstall through reconciliation over this projection, with the legacy characterization
tests still green against the new path.

## Handoff

- Current working state: CP-10 verified. Generation, writing, registration, receipt and
  verification are complete and proven against a real running MCP server.
- Exact next action: open CP-11 (desired-state reconciliation engine), starting from
  `VerificationFinding` — it is the drift vocabulary CP-11 turns into a minimal repair plan.
- Do not undo: secrets resolved at launch rather than written; the stdin and file refusals; the
  ownership check in `LocalProjectionWriter`; the post-write digest read-back; harness merging that
  preserves neighbours and permissions; config recorded by fingerprint; an unmeasurable launcher
  counting as drift.
- Tests last run/results: full quality green — all ten gates, 2,126 unit tests, 55 E2E tests,
  83.26% coverage. The four real-Keychain and nine E2E tests ran (not skipped) on darwin and left
  no keychains behind.
- Failure evidence: none outstanding.
