# Tutorial: AART with a company registry

A company registry adds reviewed discovery and policy while direct team/private sources remain
possible when organization policy permits them.

1. Install AART locally and open `aart`.
2. Add the approved company registry URL in **Sources**. Mark it as the optional default registry if
   your organization recommends that ranking; default never resolves an identity collision.
3. Add any permitted team source separately. The marketplace keeps coordinates such as
   `company/skill/review` and `team/skill/review`; select the qualified row when names collide.
4. Review the locally derived trust class, registry review/provenance, digest-bound security
   evidence, compatibility, setup capabilities, scope, mode, and destinations before Finalize.
5. Preview any default-No redacted report offered separately to the registries that supplied the
   selected artifacts. User or organization configuration may disable prompts or select one
   central destination. Reporting failure never changes installation success.

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
AART never commits or pushes a maintainer checkout automatically.
