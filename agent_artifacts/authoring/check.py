"""`aart author check`: the Registry's own verdict on a manifest, before anything is committed.

The loop an author or an agent needs is amend, check, amend, and the only verdict worth having in
it is the one `registry scan` will later issue. So nothing here restates a rule: discovery is
`discover_author_manifests` and acceptance is `parse_author_manifest`, both called rather than
copied. A checker that merely lints is worse than none, because it licenses a manifest the scanner
then rejects -- and one that is stricter is no better, because it makes an author edit a correct
file until a wrong one passes.

This module is pure: it takes a snapshot somebody else read and returns a report.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_artifacts.domain.diagnostics import Diagnostic, Severity
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.protocol.authoring import (
    discover_author_manifests,
    parse_author_manifest,
)
from agent_artifacts.protocol.codes import AUTHOR_TREE_INVALID
from agent_artifacts.protocol.native_tree import SourceSnapshot


@dataclass(frozen=True, slots=True)
class ManifestVerdict:
    """One discovered manifest and what the parser said about it."""

    path: str
    diagnostics: tuple[Diagnostic, ...]

    @property
    def accepted(self) -> bool:
        return not self.diagnostics


@dataclass(frozen=True, slots=True)
class AuthorCheckReport:
    """Every manifest found under one root, in the order they were discovered."""

    verdicts: tuple[ManifestVerdict, ...]

    @property
    def accepted(self) -> bool:
        return all(verdict.accepted for verdict in self.verdicts)


def check_author_manifests(snapshot: SourceSnapshot) -> Result[AuthorCheckReport]:
    """Parse every manifest in the tree, reporting all of them rather than the first refusal.

    A tree that holds no manifest is a refusal rather than an empty pass: an author who has
    mistyped a directory would otherwise read "nothing wrong" as "nothing wrong with my manifest".
    """

    discovered = discover_author_manifests(snapshot)
    if isinstance(discovered, Err):
        return discovered
    if not discovered.value:
        return Err(
            (
                Diagnostic(
                    AUTHOR_TREE_INVALID,
                    Severity.ERROR,
                    "no author manifest found: AART reads only `aart.yaml` and `aart.json`",
                    remediation=(
                        "Run `aart author init --kind mcp --name my-artifact` to write one.",
                    ),
                ),
            )
        )
    verdicts: list[ManifestVerdict] = []
    for manifest in discovered.value:
        parsed = parse_author_manifest(manifest)
        diagnostics = parsed.diagnostics if isinstance(parsed, Err) else ()
        verdicts.append(ManifestVerdict(str(manifest.path), tuple(diagnostics)))
    return Ok(AuthorCheckReport(tuple(verdicts)))


__all__ = ["AuthorCheckReport", "ManifestVerdict", "check_author_manifests"]
