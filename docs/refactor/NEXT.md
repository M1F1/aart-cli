# AART Refactor — Next Work

## Current objective

Complete **CP-04 Native authoring manifest and canonical compiler** through the existing compiler
seam, preserving explicit discovery and declared payload boundaries.

## Immediate next actions

1. Characterize existing `protocol/native_*` discovery, schema and canonical-tree compilation.
2. Add RED tests for explicit `aart.yaml`/`aart.json` discovery without heuristic crawling.
3. Add an authoring representation that lowers into the canonical Artifact algebra.
4. Prove include/exclude selection cannot escape the manifest root or include undeclared files.
5. Bind manifest bytes, selected payload and relevant metadata into ArtifactInputDigest.
6. Preserve existing public native protocol while routing a complete compiler path through the new
   canonical owner.

## Do not do yet

- no broad package moves;
- no TUI rewrite;
- no switch to Textual/Rich;
- no Docker-first MCP design;
- no changes to old AART repositories;
- no optional artifact families;
- no backlog work unless it becomes a proven critical-path blocker.
