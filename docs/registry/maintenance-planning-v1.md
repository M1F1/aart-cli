# Registry maintenance planning v1

Registry maintenance plans changes over inert snapshots. Filesystem access, Git acquisition,
credentials and publication effects remain behind explicit ports. Authoring takes place in a
separate Source checkout; the Registry stores reviewed canonical versions.

## Candidate review and promotion

Source scan compiles explicit author manifests into Candidates without changing the Registry.
Promotion checks the selected Candidate, source revision, validation evidence and policy against
the reviewed state. The resulting plan writes:

- a versioned canonical package under `artifacts/<kind>/<name>/<version>/` for vendored mode,
  or a pinned document under `references/<kind>/<name>/<version>.json` for reference mode;
- the approved record at `registry/versions/<kind>/<name>/<version>.json`;
- the Candidate audit record under `registry/promotions/`;
- derived `registry/index.json` and `registry/snapshot.json` catalogs.

Existing approved versions remain represented. An already approved coordinate/version cannot be
replaced with different package bytes. Source movement is discovered and reviewed explicitly; it
does not automatically change approved versions or installed artifacts.

## Build and publication

`build` deterministically derives the two catalogs from approved version records. `lock` checks
the approved representation without acquiring moving references or producing another file: the
version records already carry the required pins. `publish` uses the shared publication preparation
to plan derived changes, validate and audit the projected snapshot, list every Git change and,
when finalized, create one local commit. It does not push.

Registry Maintainer exposes Push separately on its local workspace row. Readiness is derived from
the exact committed canonical content and all mandatory gates, not a previous wizard result.
The review shows the target branch; execution rechecks the commit and refuses main/default-branch
publication and force updates. Review/merge and consumer Registry Sync remain separate actions.

## Review and apply boundary

Mutation plans bind the expected snapshot, ordered changes, previous digests and resulting bytes
to a review digest. Finalization rechecks the workspace and applies only the reviewed plan through
the appropriate effect port. Ordinary file maintenance does not acquire implicit commit or push
permissions. Explicit publish and Push actions retain their own review boundaries.

A local Registry connection reads the committed branch selected by the user through the same
admission and consumer path as a remote connection. It does not mutate the checkout, include
uncommitted files or publish the branch remotely. Local test installation is ordinary installation
from that Registry alias.

Retired authoring-workspace layouts are refused; there is no importer or automatic migration.
The canonical representation is specified in [Registry protocol v1](../protocol/registry-v1.md).
