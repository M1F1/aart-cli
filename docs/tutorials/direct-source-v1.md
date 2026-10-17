# Tutorial: AART with a local Registry

A consumer installs from Registries only. This page retains its old URL for documentation links;
direct author-repository subscriptions are removed. For a path requiring no remote service, use
a committed local Registry checkout.

1. Install AART from a reviewed checkout or wheel. Obtain a Registry checkout containing approved
   artifacts and its committed branch. An author directory with manifests alone is not a Registry.
2. In your project run `aart-cli`, open **Registries**, and choose **Add Registry**, kind **local**.
   Enter the checkout path, branch and a distinct alias. The TUI validates the snapshot before saving.
3. Open **Marketplace**, search with `/`, inspect More info with `v`, and press `i` on an offer or
   mark several with Space. Headings and complete values wrap or stack in narrow windows.
4. Review harnesses, scope, configuration and credentials, and confirm the plan. Inputs may be
   set later; their placeholders remain visible and cannot produce a passing MCP configuration test.
5. Use **Installed**, **Updates**, **Activity** and **Doctor** for recorded installations.

The equivalent connection and explicit refresh are:

```sh
aart-cli consume registry add --alias local-review --kind local --location /path/to/registry --ref main
aart-cli consume registry sync --alias local-review
aart-cli consume list
aart-cli consume status --profile claude
```

A local and a Git Registry keep different aliases even when they contain identical packages.
Sync refreshes the Registry snapshot; `aart-cli consume update` reviews and changes installations
separately. It never promotes unapproved author content. To build the Registry, follow
[the maintainer's route](../registry/maintaining-a-registry-v1.md); to write an artifact, follow
[the authoring guide](../authoring/authoring-an-artifact-v1.md).
