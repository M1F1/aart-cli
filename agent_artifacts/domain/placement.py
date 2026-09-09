"""Where an installed artifact's own tree goes.

An MCP artifact owns a tree: the payload copied out of the object store, the environment built for
it, and the interpreter inside that environment. Something has to decide where that tree lives, and
for a long time nothing did -- the only answer in the repository was a path typed into an end-to-end
test, which is fine for a test and useless to a command.

Two properties decide it.

It cannot live inside a harness's directory. One artifact may register with several harnesses, and
the tree is not any one of theirs; putting it under the first one would make uninstalling that
harness's registration look like it should take the runtime with it.

It belongs beside the manifest that records it -- the same two roots `install_state_paths` already
uses, one per scope -- so an operator who finds one finds the other.

The version is deliberately absent from the path. An update reconciles the one installation that is
there; it does not install a second one beside it and leave somebody to work out which is live.
The source is present, because two sources may publish the same name and they are not the same
artifact.

Pure path policy: nothing here consults a filesystem, a working directory or the environment. A
placement that read the disk could give two answers on two machines for the same install.
"""

from __future__ import annotations

import posixpath

from .harness import Scope
from .identifiers import ArtifactCoordinate

__all__ = ["RUNTIMES_DIRECTORY", "artifact_root"]

#: The one directory an artifact's owned tree lives under, in either scope.
RUNTIMES_DIRECTORY = "runtimes"

#: The project-scope root, matching `install_state_paths`: the manifest and the runtime it records
#: are siblings rather than two places to look.
_PROJECT_STATE_DIRECTORY = ".agent-artifacts"


def _absolute(path: str, label: str) -> str:
    if (
        not isinstance(path, str)
        or not posixpath.isabs(path)
        or posixpath.normpath(path) != path
        or any(character in path for character in "\r\n")
    ):
        raise ValueError(f"{label} must be a normalized absolute path")
    return path


def artifact_root(
    coordinate: ArtifactCoordinate,
    scope: Scope,
    *,
    project_root: str,
    data_root: str,
) -> str:
    """The absolute root of the tree this artifact owns at `scope`."""

    if not isinstance(coordinate, ArtifactCoordinate) or not isinstance(scope, Scope):
        raise ValueError("an artifact root needs a coordinate and a scope")
    base = (
        posixpath.join(_absolute(project_root, "project root"), _PROJECT_STATE_DIRECTORY)
        if scope is Scope.PROJECT
        else _absolute(data_root, "data root")
    )
    return posixpath.join(
        base,
        RUNTIMES_DIRECTORY,
        coordinate.source.value,
        coordinate.artifact.kind,
        coordinate.artifact.name,
    )
