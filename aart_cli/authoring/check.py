"""`aart-cli author check`: the Registry's own verdict on a manifest, before anything is committed.

The loop an author or an agent needs is amend, check, amend, and the only verdict worth having in
it is the one `registry scan` will later issue. So nothing here restates a rule: discovery is
`discover_author_manifests` and the verdict is `compile_author_manifests`, which parses each
manifest and then compiles what parsed -- both called rather than copied. A checker that merely
lints is worse than none, because it licenses a manifest the scanner then rejects -- and one that
is stricter is no better, because it makes an author edit a correct file until a wrong one
passes.

This module is pure: it takes a snapshot somebody else read and returns a report.
"""

from __future__ import annotations

from dataclasses import dataclass

from aart_cli.domain.diagnostics import Diagnostic, Severity
from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.protocol.authoring import (
    compile_author_manifests,
    discover_author_manifests,
)
from aart_cli.protocol.codes import AUTHOR_TREE_INVALID
from aart_cli.protocol.native_tree import SourceSnapshot


@dataclass(frozen=True, slots=True)
class ManifestVerdict:
    """One discovered manifest, what AART said about it, and what it would be promoted as.

    `package` is the coordinate the compiler produced, so an author reading it knows the compile
    ran rather than only the parse. `checked` is false for a manifest `registry scan` passes over
    -- a Collection is discovered by the same walk and compiled by a different function -- and
    saying so is the honest answer, since neither claim in §1.4 was tested against it.
    """

    path: str
    diagnostics: tuple[Diagnostic, ...]
    package: str | None = None
    checked: bool = True

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


def check_author_manifests(
    snapshot: SourceSnapshot,
    *,
    source_alias: SourceAlias,
    source: str,
    revision: str,
) -> Result[AuthorCheckReport]:
    """Parse and compile every manifest in the tree, reporting all of them rather than the first.

    A tree that holds no manifest is a refusal rather than an empty pass: an author who has
    mistyped a directory would otherwise read "nothing wrong" as "nothing wrong with my manifest".

    §1.4's two claims are ordered, because the second is worthless if the first fails, and that
    order already lives inside `compile_author_manifests`: it parses, refuses what will not parse,
    and compiles only the rest. Calling `parse_author_manifest` again here would produce the same
    diagnostics a second time and make this module a second place the order could drift.
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
                    "no author manifest found: AART reads only `aart-cli.yaml` and `aart-cli.json`",
                    remediation=(
                        "Run `aart-cli author init --kind mcp --name my-artifact` to write one.",
                    ),
                ),
            )
        )
    compiled = compile_author_manifests(
        snapshot, source_alias=source_alias, source=source, revision=revision
    )
    if isinstance(compiled, Err):
        return compiled
    artifacts, refusals = compiled.value
    promoted = {
        str(artifact.manifest_path): f"{artifact.package.coordinate.artifact}"
        f"@{artifact.package.coordinate.version}"
        for artifact in artifacts
    }
    refused = {str(refusal.manifest_path): refusal.diagnostics for refusal in refusals}
    verdicts: list[ManifestVerdict] = []
    for manifest in discovered.value:
        path = str(manifest.path)
        if path not in promoted and path not in refused:
            # The compiler neither compiled it nor refused it, which is how it says "not mine".
            verdicts.append(ManifestVerdict(path, (), checked=False))
            continue
        verdicts.append(ManifestVerdict(path, refused.get(path, ()), promoted.get(path)))
    return Ok(AuthorCheckReport(tuple(verdicts)))


__all__ = ["AuthorCheckReport", "ManifestVerdict", "check_author_manifests"]
