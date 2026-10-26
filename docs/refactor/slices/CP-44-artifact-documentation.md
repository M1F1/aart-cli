# CP-44 — An artifact points to its own documentation

Status: **done in its PR**, on `feat/cp-44-artifact-documentation`, stacked on CP-43 (PR #100), at the
owner's request (2026-10-26). Authority: Product Specification §197, INV-298, D-481.

## Steps

See `docs/refactor/plan.json`, epic CP-44.

1. `artifact.documentation` is parsed, approved in the canonical manifest and carried to the index.
   Done.
2. It is shown in Marketplace More info, with every credential and configuration input, in
   Credentials and variables, and by the CLI's listing, review and install result. Done.
3. The author skeleton, the authoring and consumer documents and the manual walkthrough name it.
   Done.
4. Focused verification, targeted mutations and the PR. Done; the PR
   waits for the owner.

## Why

A summary is one line and an input's `help` a few. Neither has room for a longer manual, the steps
to get a credential, or a configuration walkthrough. The owner asked for a manifest field, not a
hardcoded link, shown wherever credentials and configuration are asked or explained, when
installing from the CLI, and in Marketplace, where it can be copied while browsing.

## Change

- `aart_cli/domain/inputs.py`:
  - `documentation_url` is `obtain_from.url`'s rule (D-263) plus "nothing `redact_text` would
    change";
  - `InputGuidance.documentation`;
  - `documented(item, link)` sets the link on an input's guidance, creating guidance for an input
    that has none.
- `aart_cli/domain/install_description.py`: `InstallDescription.documentation`, projected to data.
- `aart_cli/protocol/authoring.py`:
  - the optional `artifact.documentation` field, refused as `artifact.documentation is invalid: …`;
  - the compiler writes it into the native manifest;
  - `read_package_description` and `describe_installation` document every input with it.
- `aart_cli/protocol/native_models.py`, `native_schema.py`: `ArtifactManifest.documentation`,
  serialized only when set, so existing packages keep their digests.
- `aart_cli/protocol/registry_models.py`, `registry_index.py`: `IndexArtifact.documentation`.
  `installation/application.py` and `security/baseline.py` compare it with the manifest like the
  other identity fields.
- `aart_cli/tui_layout.py`: `field_block(..., whole=)` keeps the named fields' values on one line.
- `aart_cli/tui_marketplace.py`, `tui_marketplace_detail.py`: `MarketplaceArtifactRow.documentation`
  and a `Documentation` field after the Description in More info, kept whole.
- `aart_cli/application/credential_guidance.py`: `Documentation: <link>` closes a credential's
  guidance. With no `obtain_from`, the fallback points to the documentation.
- `aart_cli/application/consumer_views.py`: `ConfigInputView` and `CredentialInputView` carry it.
- `aart_cli/tui_consumer.py`:
  - screen 07 prints it under each input;
  - the configuration form prints it once per installation;
  - screen 22 prints it once per installation, from `ConsumerScreens.documentation_for`. That
    method takes the link from the Marketplace entry for the installation's exact `name@version`.
- `aart_cli/commands/marketplace.py`: the refusal for unanswered inputs, the review and the install
  result name it in text and JSON.
- `aart_cli/marketplace/catalog.py`: `consume list` text and JSON.
- `aart_cli/authoring/skeleton.py`: every kind's skeleton carries it commented, with one line saying
  what it is for.
- Documents:
  - `docs/authoring/authoring-an-artifact-v1.md`;
  - `docs/protocol/native-source-v1.md`;
  - `docs/using/consumer-lifecycle-v1.md`;
  - `docs/testing/TUI_MANUAL_WALKTHROUGH.md`;
  - the example manifest `docs/examples/author-source/example-mcp/aart-cli.yaml`.

## Tests

`tests/artifact_documentation_test.py`:

- **The link rule:**
  - every plain `http(s)` link is accepted as written (Hypothesis);
  - every spoiled one is refused (Hypothesis): user information, another scheme, a space, an
    escape sequence, a bidirectional control, a newline, leading whitespace, no scheme, a token in
    the query, a token in the path, and credentials in the URL;
  - a link over 2048 characters is refused.
- **The manifest:**
  - the author manifest reads the link, and an absent one is `None`;
  - an unsafe one is refused naming the field;
  - the approved manifest round-trips it (Hypothesis);
  - an undocumented manifest serializes exactly as before;
  - an unsafe approved link is refused on reading.
- **Inputs:**
  - each declared input is explained with its own artifact's link;
  - documenting changes nothing but the link, with or without existing guidance (Hypothesis);
  - an install description refuses an unsafe link.
- **The words:**
  - a credential names its documentation;
  - one with no `obtain_from` points to the documentation, and an undocumented one keeps the
    honest fallback;
  - owners with different documentation each keep their own;
  - screen 07 shows the link beside a configuration value and a credential;
  - the form names it once per installation;
  - an undocumented input draws no link.
- **Marketplace:**
  - More info shows the link on one line however long (Hypothesis);
  - an offer without one says nothing;
  - a row refuses an unsafe link.
- **Credentials and variables:**
  - an installation finds the link its exact offer carries, and none for a version no longer
    offered;
  - the list names it once under the installation whose offer carries it, and not under one
    whose version is no longer offered;
  - the artifact and value views name it.
- **End to end:**
  - the production TUI's More info shows the approved link;
  - the CLI lists, refuses (configuration and credential), reviews and installs with the link;
  - an undocumented artifact shows no link anywhere.
  The CLI test patches the Keychain provider with the in-memory fakes from
  `credential_guidance_test.py`.

Updated:

- `author_skeleton_test.py`: its anti-drift oracle found the new field. Every skeleton now names
  it.
- `install_description_test.py`: the projection's keys.
- `credential_guidance_test.py`: the CLI JSON's `documentation: null`.
- `author_manifest_example_test.py`: the example declares a link.

Focused runs: the 82 marketplace, credential, authoring, native, registry-index, configuration
and input test files, and the 163 TUI, consume, catalog, screen, guidance, baseline, installation
and registry files. Everything passes except the two `screen_skeleton_test.py` properties that
fail on `main` too (B-226). Lint, format, types, docs, secret shape, validate, packaging and tach
pass.

Lab check: a lab Registry promoted `tracker-mcp`, whose manifest names a link and declares a token
and a user number, and `code-review` with a link.
- `consume list` printed `documentation=…` for exactly those two offers.
- `consume install lab/mcp/tracker-mcp@1.0.0 --profile claude`, without answers, printed the link
  under the token's guidance, whose fallback now says to see the documentation, and under the
  user number.
- The CLI showed that a configuration input in the refusal has no label (B-234).

## Targeted mutations

Run with `PYTHONDONTWRITEBYTECODE=1 python -B`, and each restored file is touched. A first run
reused bytecode compiled from the previous mutation and showed a false red.

| Mutation | Red |
|---|---|
| No redaction check | the refusal property |
| No http(s) host check | the refusal property and the length example |
| Inputs not documented when a package is read | each input carries its artifact's link |
| `documented` returns the input unchanged | eight: the documenting property, the words, screen 07, the form, the CLI end to end |
| `whole` ignored, so the link wraps | More info whole at any length |
| The form repeats the link under every value | once per installation |
| Screen 07 omits it | screen 07 |
| The CLI refusal omits it for a configuration input | the CLI end to end |
| `consume list` omits it | the CLI end to end |
| Credential guidance omits it | the credential words, screen 07, the CLI end to end |
| Screen 22 omits it | the list names it once (this test was added after the mutation survived) |
| `documentation_for` takes any offer's link | exact offer, the list |
| The native manifest writes `documentation: null` when absent | serializes as before, nothing shown for an undocumented artifact |
