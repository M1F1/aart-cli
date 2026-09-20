# Registry protocol v1

An AART Registry publishes reviewed, versioned canonical artifacts. Authors maintain manifests and
payloads in a separate Source checkout; scan compiles Candidates, and promotion writes approved
Registry content after validation and policy review. Registry maintenance and consumer acquisition
validate the same representation.

## Canonical layout

```text
aart-cli-registry.json
aart-cli-source.json
registry/
  versions/<kind>/<name>/<version>.json
  promotions/<candidate-id>.json
  index.json
  snapshot.json
artifacts/<kind>/<name>/<version>/
  artifact.json
  payload/
references/<kind>/<name>/<version>.json
```

The root markers identify the Registry and its protocol/compatibility requirements. Each approved
version record binds an artifact coordinate and version to canonical content, provenance and the
approved content snapshot. Promotion records preserve the reviewed Candidate's audit evidence.
`registry/index.json` and `registry/snapshot.json` are derived catalogs rebuilt from those records;
they contain metadata, not artifact payload bytes or credentials.

## Vendored and referenced versions

A vendored version stores its canonical package under `artifacts/<kind>/<name>/<version>/`.
A reference-mode version instead records its pinned source in
`references/<kind>/<name>/<version>.json`. The approved version retains the exact source revision
and content digests; consumer acquisition verifies these rather than following a moving branch.
A reference may therefore require access to the source origin, while a vendored package carries
its payload in the Registry. Neither mode creates an unversioned authoring entry.

Promotion refuses a conflicting package at an already approved coordinate/version. Updating
Registry snapshot metadata does not authorize rewriting that immutable package. Vendoring makes
the Registry the distributor of copied bytes: provenance records their origin, but does not
certify their safety or remove the maintainer's licensing and review responsibilities.

## Validation and derived catalogs

Validation checks canonical records, identities, versions, content/provenance digests, package
boundaries and agreement between approved records and derived catalogs. A missing or changed
catalog cannot silently redefine approved content. Managed symlinks and special files are refused.
Compatibility, dependency and Collection validation remain part of admission; consumer policy
and configured Registry identity remain separate from author-supplied metadata. Content cannot
assign itself effective trust.

`aart-cli registry build` rebuilds `registry/index.json` and `registry/snapshot.json` from approved
version records. `--check` reports drift without applying it. `aart-cli registry lock` remains an
accepted command, but approved records already contain their pins: it is a read-only check with
nothing to resolve, not a producer of a separate lock file. The generated Registry workflow omits
that redundant lock step and checks format, reproducible build, validation, audit and compatibility.

`aart-cli registry publish` prepares the shared publication gate set, applies the reviewed derived
changes and commits the listed Git changes when explicitly finalized. It never pushes. Push is a
separate reviewed action restricted to an eligible review branch.

## Removed representation

Historically, authoring workspaces used `entries/`, `aart.lock.json`, `aart.index.json` and
unversioned packages. CP-26 removed that representation. Those paths are rejected, including in a
mixed checkout; no compatibility reader or automatic migration is provided. They are not inputs
or outputs of current maintenance commands.

See [maintenance planning](../registry/maintenance-planning-v1.md),
[maintainer commands](../registry/maintainer-commands-v1.md) and the canonical
[Product Specification](../product-specification/PRODUCT_SPECIFICATION.md) for review, publication
and installation ownership.
