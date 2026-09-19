# Registry maintainer commands v1

`aart-cli registry` turns a local Git checkout into a canonical, reviewable AART registry. Ordinary
mutations stop after reviewed managed-file writes. The explicit `publish --yes` workflow validates,
audits, and commits every listed Git change. Only `push` touches a remote, and only a review branch.

## Command contract

| Command | Effect | Purpose |
|---|---|---|
| `init` | writes | Add protocol markers, `.aart-cli-version`, a README, and registry CI |
| `format` | writes, or reads with `--check` | Canonicalize every managed JSON document |
| `validate` | reads | Validate protocol, compatibility, lock/index, native packages, and graph |
| `lock` | writes, or reads with `--check` | Resolve every approved native reference to an exact commit and digests |
| `build` | writes, or reads with `--check` | Compile the payload-free marketplace index from owned and locked artifacts |
| `audit` | reads | Check review, provenance, setup, license, and currently available risk evidence |
| `publish` | writes and commits with `--yes` | Plan lock/build, validate/audit the projection, list all Git paths, and create one commit without pushing |
| `push` | pushes | Push the reviewed commit to a named branch; the remote's default branch is refused |
| `test` | reads | Validate the registry at its minimum and/or a supplied latest compatible version |
| `diff` | reads | Show deterministic canonical-format drift without changing the checkout |

The authoring commands that bring content in — `scan`, `promote`, `adopt`, `check-upstream`,
`discover`, `vendor`, `vendor-batch`, `revendor` and `collection` — follow the same
review-then-`--yes` boundary; `aart-cli registry ACTION --help` states
each one's inputs.

Mutation requires a writable real directory containing `.git` (a directory or worktree gitfile).
Managed symlinks and special files are rejected. Writes use exact snapshot and per-file digest
preconditions, atomic replacements, post-write verification, and rollback on a partial failure.
Read-only commands work on a plain snapshot with no `.git` and do not require write permission.

`format --check`, `lock --check`, and `build --check` return `0` when generated content is current
and `1` when drift exists. They never apply their plan. Human output describes every changed path;
`--json` emits a stable operation, changed-path count, review digest, and diagnostics.

## Bootstrap and bring in authored content

Start from an empty Git checkout:

```console
git init company-registry
aart-cli registry init --source company-registry \
  --source-id company-registry --display-name "Company Registry"
```

The generated quality workflow puts the AART version pinned in `.aart-cli-version` on the runner — from
an index, a wheel, a path or a Git clone, chosen by repository variables — and proves the version
it got matches the pin. It then runs format, strict/frozen validation, lock, build, audit, and
minimum/latest compatibility checks. The workflow has read-only repository permissions and contains
no commit or push step. [Rolling out AART on GitHub Enterprise Server](../ci/github-enterprise-rollout.md)
lists the variables.

Artifacts are authored in a separate Source checkout with an explicit `aart.yaml` or `aart.json`
and payload. Commit that clean checkout, then use the Registry's Candidate workflow:

```console
aart-cli registry scan --help
aart-cli registry promote --help
```

`scan` compiles only explicit author manifests and never changes the Registry. `promote` rechecks
the selected Candidate, validation evidence and policy result before writing the canonical package.
The Registry stores that compiled package and provenance; it does not author the Source payload.

## Lock, build, and audit

Registry entries remain authored references to credential-free Git URLs. `lock` acquires each ref
through the bounded, hook-free Git snapshot adapter, verifies the referenced native package, and
records its resolved commit and content digests. `build` reacquires the sources, rejects any lock
mismatch, compiles registry-owned packages and references, and writes no payload bytes into
`aart.index.json`.

An entry whose review status is not `approved` cannot be locked and fails `audit`. Audit warnings
are evidence gaps, not installation-risk conclusions: missing license/provenance and absent
per-object assessment evidence are reported explicitly. When `security/index.json` exists, audit
verifies every canonical attestation byte digest, publisher/registry-input identity, exact compiled
object coverage, and rejects evidence for unknown objects or critical installation risk. High or
unknown risk remains an explicit review warning. The stdlib-only baseline is documented in
[`baseline-v1.md`](../security/baseline-v1.md), and the registry evidence layout is documented in
[`attestations-v1.md`](../security/attestations-v1.md).

## Other catalog formats

Registry commands accept only the native package contract; other catalog layouts are not
translated. Re-author the other repository as a native source and bring its reviewed Candidate in
with `scan` and `promote`, or copy its content in with `vendor`, which records provenance.
