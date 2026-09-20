# CP-26 contract alignment — 2026-09-19

## Authority and readiness

The sole product authority is [Product Specification](../product-specification/PRODUCT_SPECIFICATION.md),
including its accepted §169. Decisions explain that contract; the execution plan, slice and
`plan.json` schedule it; traceability records evidence. Historical implementation, tests and public
guides cannot override it. D-332–D-335 explicitly supersede the earlier installation assumptions.

The reviewed installation contract is ready for implementation. No unresolved product choice was
found that blocks the recorded order. This is documentation readiness, not implementation or
release readiness: CP-26 has **13 of 22 tasks done**, **14 next**, and **18a → 19 → 20** pending
before the final gate at 21. No task status changed during this audit.

## Resolved contradictions

| Surface | Earlier claim | Accepted contract / treatment |
|---|---|---|
| §169 versus runtime invariants and D-071 | Artifact-level runtime could serve several harnesses | Private installed payload, runtime, launcher and ordinary config per complete harness target; immutable objects alone can deduplicate |
| Input UX, INV-057/190/196/243, D-073/263/313 | Reuse or explicitly share provider references/answers across installations | Each new installation enters its own inputs and owns separate provider items; compatible retention only within the same owner's update/repair |
| Collections, INV-129/131/164 | “Shared ownership” and “deduplication” could imply shared mutable inputs | Several reasons can retain the same complete owner; host prerequisite checks/help may aggregate; different owners' fields, values and secrets remain separate |
| Version resolution, INV-212 | One active version per coordinate and scope | One active version per Registry alias + artifact + scope + normalized root + harness/profile; version is not part of owner identity |
| Filesystem and D-130/264/276 | Platform user roots, project receipts and old names | One `~/.aart-cli` / `AART_CLI_HOME` for tool data; central per-owner metadata; actual installed files under the harness; namespace `aart-cli` / `aart_cli` |
| Registration example and multi-Registry grouping | Unqualified entry name/relative launcher; equal digests might hide aliases | Absolute launcher, unambiguous alias-qualified key; Installed rows and lifecycle stay separate for local and remote aliases |
| INV-138/227 | One transaction receipt and scope lock appeared sufficient | Bulk activity links per-owner receipts; shared harness-file mutations preserve all fragments, including across application homes |
| Root execution instructions | Full quality required for every verified slice | D-317/D-334: proportionate focused checks; full quality only at CP-26.21; no compatibility work or test per mechanical rename |
| CODEX_GOAL, slice index, local handoff, old NEXT checkpoints | CP-18/20/12 appeared current | Current CP-26 checkpoint and task 18a recorded; old checkpoints explicitly historical |
| Invariant traceability | Old passing tests appeared to prove new ownership; catalog stopped at 242 | Added 243–247; affected historical claims reclassified PARTIAL/CONFLICT with pending CP-26 proof |
| BACKLOG B-074/076/121/143/144/150 | Shared-reference repair or prompt dedup could reintroduce withdrawn behavior | Historical notes marked; independent input entry required; B-121 absorbed into 19; B-144/B-150 mandatory in 19 and B-143 in 20 |

## Boundaries that are intentional

- Central receipts, activity and immutable content are tool metadata/storage, not global artifact
  configuration. They contain paths/digests/provider references, never artifact input values.
- Administrator policy stays outside the user-writable home. An application-home override cannot
  disable it. OS secret providers and harness formats still need their platform adapters.
- Several installations may edit distinct fragments in one harness settings file. Fragment
  ownership does not mean the entire file belongs to any one installation.
- Four eligible targets require four separately entered input sets. Tests may use eligible test
  profiles; this acceptance does not require implementing a fourth external MCP adapter.
- Shared Git authentication and machine prerequisites are external infrastructure. They do not
  authorize sharing artifact runtime input bindings or provider items.
- Breaking changes remove obligations to old interfaces. They do not remove external harness
  constraints, secret protection, ownership checks or final quality gates.

## Current code and public guidance are not the target implementation

The executable/import package, platform path resolver, placement, receipts and input composition
still implement older behavior. In particular, `configuration/paths.py`, `domain/placement.py` and
`application/installation_inputs.py` are change sites, not architectural authority. The current
matrix names real files/tests using their current spelling so its evidence remains navigable.

CP-26.18a inventories and updates active names, producers/readers, templates, schemas and public
instructions together. CP-26.19 supplies the full ownership/input/lifecycle evidence. CP-26.20
adds local acquisition and exercises it alongside remote Registry aliases. Do not mark these done
because the target examples are documented.

Public protocol guides still include retired native-reference/lock/index descriptions (B-151).
The native-source and registry guides now warn that those portions are historical and point to
the canonical specification. Their rewrite/removal remains required before 21; the warning does
not close B-151. README restructuring stays in 14–16. Current executable examples elsewhere must
be updated with 18a rather than used to restore old names or paths in the target design.

## Verification and limits

This audit reviews product sections/invariants governing installation, namespace, storage, inputs,
Collections, version identity and concurrency, plus current execution instructions, decisions,
backlog, traceability, slice records and handoff. It does not revalidate every unrelated invariant
or external harness contract. Implementation must still measure supported harness destinations.

Passed: `make docs-check`; all five `tests.traceability_matrix_test` cases; a direct check of
247 unique invariant rows; `handoff-plan validate` (27 epics, 160 units, 151 done overall);
comparison of CP-26 with HEAD (13/22 done, existing statuses unchanged, 14 next, 18a before 19,
21 last); and `git diff --check`. The local ignored `.claude/HANDOFF.md` is also refreshed;
tracked NEXT/status/slice records preserve the resumption information independently of it.
No runtime code is changed and no broad quality or mutation campaign is warranted for this segment.
