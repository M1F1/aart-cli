"""Credential-free author form values; filesystem operations belong to the adapter."""

from dataclasses import dataclass
from pathlib import PurePath

from aart_cli.authoring.check import ManifestVerdict
from aart_cli.authoring.skeleton import GENERATED_KINDS


def normalized_workspace(value: object) -> bool:
    """Stored workspace paths are absolute and already normalized by the IO boundary."""

    return isinstance(value, str) and (
        not value
        or (
            not any(character in value for character in "\r\n\x00")
            and PurePath(value).is_absolute()
            and str(PurePath(value)) == value
            and ".." not in PurePath(value).parts
        )
    )


def manifest_lines(verdict: ManifestVerdict) -> tuple[str, ...]:
    """Keep complete errors, with recovery prose appropriate to the interactive author area."""

    if verdict.accepted:
        return (verdict.path, "ok", *((verdict.package,) if verdict.package else ()))
    lines = [verdict.path]
    for diagnostic in verdict.diagnostics:
        lines.append(f"{diagnostic.code}: {diagnostic.message}")
        if diagnostic.interactive:
            lines.extend(diagnostic.interactive)
        else:
            steps = tuple(
                step
                for step in diagnostic.remediation
                if not any(marker in step for marker in ("aart-cli ", "`", "$ ", "git "))
            )
            lines.extend(steps or ("Edit this manifest in your workspace, then run Check again.",))
    return tuple(part for line in lines for part in line.replace("\r", "\n").split("\n"))


@dataclass(frozen=True, slots=True)
class AuthorDraft:
    workspace: str = ""
    kind: str = "skill"
    name: str = ""
    into: str = "."

    def __post_init__(self) -> None:
        if self.kind not in GENERATED_KINDS or any(
            not isinstance(value, str) or any(character in value for character in "\r\n\x00")
            for value in (self.workspace, self.name, self.into)
        ):
            raise ValueError("author form is invalid")
