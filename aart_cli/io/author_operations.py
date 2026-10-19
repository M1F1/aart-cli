"""Author Mode uses the same skeleton, reader and checker as the author CLI."""

from pathlib import Path

from aart_cli.authoring.check import AuthorCheckReport, check_author_manifests
from aart_cli.authoring.skeleton import author_skeleton
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.io.author_workspace import (
    WORKING_TREE_ALIAS,
    read_author_workspace,
    write_author_skeleton,
)


def _error(message: str) -> Err:
    return Err((Diagnostic(DiagnosticCode("author-workspace-invalid"), Severity.ERROR, message),))


def select_workspace(value: str, *, application_home: str | None) -> Result[str]:
    if not value.strip():
        return _error("Choose the directory of your Upstream repository.")
    try:
        root = Path(value).expanduser().resolve(strict=True)
        if not root.is_dir():
            return _error("An author workspace must be a directory.")
        if application_home is not None and root.is_relative_to(Path(application_home).resolve()):
            return _error("An author workspace must be outside the AART application home.")
    except (OSError, RuntimeError, ValueError) as error:
        return _error(f"The author workspace could not be opened: {error}")
    return Ok(str(root))


def check_workspace(root: str) -> Result[AuthorCheckReport]:
    read = read_author_workspace(root)
    if isinstance(read, Err):
        return read
    return check_author_manifests(
        read.value.snapshot,
        source_alias=WORKING_TREE_ALIAS,
        source=read.value.root,
        revision=read.value.revision,
    )


def new_artifact(
    root: str, *, kind: str, name: str, into: str, application_home: str | None = None
) -> Result[str]:
    generated = author_skeleton(kind, name)
    if isinstance(generated, Err):
        return generated
    try:
        workspace = Path(root).resolve(strict=True)
        destination = (workspace / into).resolve()
        if not destination.is_relative_to(workspace):
            return _error("The artifact directory must be inside the author workspace.")
        if application_home is not None and destination.is_relative_to(
            Path(application_home).resolve()
        ):
            return _error("An artifact must be created outside the AART application home.")
    except (OSError, RuntimeError, ValueError) as error:
        return _error(f"The artifact directory could not be opened: {error}")
    written = write_author_skeleton(generated.value, into=str(destination))
    if isinstance(written, Err):
        return written
    return Ok(str((destination / "aart-cli.yaml").relative_to(workspace)))
