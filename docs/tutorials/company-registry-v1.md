# Tutorial: AART with a company registry

A company Registry offers approved versions and Collections. A consumer connects Registries;
its maintainers connect the author teams' Upstream repositories.

1. Install AART and open `aart-cli` in your project.
2. In **Registries**, choose **Add Registry** and enter the approved Git URL and ref, or a local
   committed Registry checkout. A default Registry never resolves an identity collision.
3. Open **Marketplace**, search with `/`, and inspect the focused offer with `v` / More info.
   Its complete details stay in Marketplace. Columns have headings and wrap; narrow windows
   stack labeled fields. PgUp/PgDn scrolls short windows.
4. Press `i` to install the focused offer, or mark several with Space first. A Collection opens
   a member preview with Enter. Review harnesses, inputs, scope and the resulting plan, then confirm.
5. Use **Installed** for recorded installations, **Updates** after Registry Sync, and the optional
   **Test installed MCPs** action for its two-stage local smoke test. Unset inputs cannot pass.

Enable Registry Maintainer Mode separately in Settings for **Upstream repositories**,
**Candidates** and **Registry**. Author Mode is another independent opt-in for Workspace, Check
and New artifact; it uses `aart-cli author` operations and does not connect an upstream itself.

Maintainers work in an explicit writable registry checkout. Before a PR they run:

```shell
aart-cli maintain registry format --source . --check
aart-cli maintain registry validate --source . --strict --frozen
aart-cli maintain registry lock --source . --check
aart-cli maintain registry build --source . --check
aart-cli maintain registry audit --source .
aart-cli maintain registry test --source . --compatibility all --latest-version 1.0.0
```

Pinned references record the upstream commit and digests without copying the payload; consumers
resolve those packages from the upstream repository. Content enters only by adopting a manifest:
an upstream that is not yet an AART package gets an `aart-cli.yaml` beside each artifact first
([maintaining a registry](../registry/maintaining-a-registry-v1.md#how-content-enters-a-registry)).
Ordinary maintenance stops after reviewed files. Explicit `maintain registry publish --yes`
creates a local commit; explicit `maintain registry push` pushes only a reviewed non-default branch.
