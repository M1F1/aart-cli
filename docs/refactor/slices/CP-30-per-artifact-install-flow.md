# CP-30 — per-artifact installation flow

Status: **in flight**. Step 1 is done on `feat/cp-30-install-flow-per-artifact`.

Date opened: 2026-10-16. Authority: the product owner (D-413, Product Specification §172). Their
requests, in order:
- harnesses chosen per selected artifact, on one screen;
- configuration entered once per artifact for all its harnesses;
- the scope chosen per artifact and harness pair, starting on the Settings default;
- credentials settled before installation, so a missing credential cannot break the install.

Every screen handles one or many artifacts. They then asked for entering inputs during installation
to be optional: skipped values become placeholders, set later one by one in Credentials and
variables.

## Design

- **The pair is the unit.** UI state and commands carry `artifact\tharness` pairs and
  `artifact\tharness\tscope` choices instead of one global harness set and one scope.
- **One draft, one transaction.**
  - The draft places each artifact per scope group, with that scope's root.
  - `McpTarget.scope` already exists, so a registry that routes each target to its scope root lets
    one transaction write both scopes.
  - A composite lock takes both scope leases in sorted order.
- **Answers per artifact.**
  - Config answer rows are `artifact\tinput_id`.
  - `consumer_actions` fans each one out to every owner of that artifact as an
    `OwnedInputSource`, so each installation still stores its own copy.
- **Placeholders.** A skipped input is stored as the literal `SKIP`, for ordinary values and
  secrets alike. Nothing blocks on it: the install completes and the launcher starts. Doctor,
  Installed and Credentials and variables warn about it. A secret is matched through
  `find -w | grep -cx SKIP` in child processes, so this process never reads it.
- **Secrets.**
  - A hidden prompt under terminal handover captures a `TransientSecret` per artifact secret,
    held by `LocalConsumerActions`.
  - The credential interpreter stores it, or the placeholder, per owner through `security -i` on
    stdin with `-X <hex>`, which keeps it off argv. Verified against a temporary keychain.
  - The transaction never prompts.

## Steps

See `plan.json` CP-30. Step 1 (spec and D-413) is done.

## Superseded work

- `stash@{0}`, "scope rows before the form (D-412 draft)", was the narrow fix for the missing scope
  rows. It is reference only; 07a replaces it.
- D-412 is used by the profile rename (PR #68), not by that draft.
