# CP-31 — Collections end to end, Registry-owned versions, install paths, views and pruning

Status: **in flight** on `feat/cp-31-collections-and-registry-versions`.

Date opened: 2026-10-16. Authority: the product owner (B-067, #72–#75, #53, #54, #41; D-422,
D-423), Product Specification §173. The plan and the implementation land in one PR.

## Steps

See `docs/refactor/plan.json`, epic CP-31. In order:
1. Specification §173 (this document, D-424).
2. Registry-owned versions (#74).
3. `author init --kind collection`.
4. `author check` for Collections.
5. Promotion publishes Collections; the Registry reads them back (B-067 layers 1–2).
6. The Marketplace offers Collections (B-067 layer 3).
7. 05 and 07a treat a Collection as one artifact (D-422).
8. 07 and 07b per member, with Set later.
9. Installed, Doctor and uninstall for Collections (INV-186).
10. Default and custom install paths (#75).
11. Marketplace and Installed columns (#72, #75).
12. Documentation.
13. `RegistryContentMode` rename (#54).
14. Pruning: the vendor family and other legacy routes (#53, #73).
15. Full verification and the PR.

## Step 1 — specification

§173 is accepted, with INV-262–INV-266. D-424 records the implementation choices for versions:
the compiler is told the version by a `VersionAssigner` built from approved state, "unchanged"
means the same input digest, and the number is chosen at Sync and checked at approval.
