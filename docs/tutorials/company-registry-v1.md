# Tutorial: AART with a company registry

A company Registry offers approved versions and Collections. A consumer connects Registries only;
its maintainers connect the author teams' Upstream repositories. The Registry is a Git repository
on your forge, or a committed local checkout when no remote service is wanted. An author directory
with manifests alone is not a Registry.

1. Install AART and open `aart-cli` in your project.
2. In **Registries**, choose **Add Registry**. For a Git Registry enter the approved URL and ref;
   for kind **local**, the checkout path and branch. Give it a distinct alias. The TUI validates
   the snapshot before saving, and a default Registry never resolves an identity collision.
3. Open **Marketplace**, search with `/`, and inspect the focused offer with `v` / More info.
   Its complete details stay in Marketplace. Columns have headings and wrap; narrow windows
   stack labeled fields. PgUp/PgDn scrolls short windows.
4. Press `i` to install the focused offer, or mark several with Space first. A Collection opens
   a member preview with Enter. Review harnesses, inputs, scope and the resulting plan, then
   confirm. Inputs may be set later; their placeholders stay visible and cannot pass an MCP
   configuration test.
5. Use **Installed** for recorded installations, **Updates** after Registry Sync, **Activity** and
   **Doctor**, and the optional **Test installed MCPs** action for its two-stage local smoke test.

The same connection, refresh and check from the command line, for a local checkout:

```sh
aart-cli consume registry add --alias local-review --kind local --location /path/to/registry --ref main
aart-cli consume registry sync --alias local-review
aart-cli consume list
aart-cli consume status --profile claude
```

A local and a Git Registry keep different aliases even when they contain identical packages.
Sync refreshes the Registry snapshot; `aart-cli consume update` reviews and changes installations
separately, and never promotes unapproved author content.

Enable Registry Maintainer Mode separately in Settings for **Upstream repositories**,
**Candidates** and **Registry**. Author Mode is another independent opt-in for Workspace, Check
and New artifact; it uses `aart-cli author` operations and does not connect an upstream itself.
To build the Registry, follow [the maintainer's route](../registry/maintaining-a-registry-v1.md);
to write an artifact, follow [the authoring guide](../authoring/authoring-an-artifact-v1.md).
