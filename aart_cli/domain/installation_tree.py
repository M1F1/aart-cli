"""Where one installation's private tree goes, under the harness that selected it.

What this replaced answered the same question the other way round, and said why: one artifact may
register with several harnesses, so its tree is not any one of theirs, and it belongs beside the
manifest that records it. §169.3 rejects the premise rather than the reasoning. The unit that owns
a tree is not the artifact, it is the *installation* -- Registry alias, artifact, scope, concrete
root and harness together -- and installing into a second harness is a second installation with its
own payload, its own runtime, its own launcher and its own separately entered configuration. Once
that is the unit, putting its tree under its harness is what makes that harness's uninstall able to
take its own files and no others.

Two things it therefore must not do. It must not leave the version out of the owner and it must not
leave the alias out: two aliases pointing at the same upstream Registry, even publishing
byte-identical packages, are two installations that never share a runtime, a launcher, a
configuration file or a credential item. Only the immutable canonical object may be shared, and
that lives in the application home, not here.

The version *is* deliberately absent from the path, for the reason the older policy already gave:
an update reconciles the one installation that is there rather than installing a second one beside
it.

The harness root is an argument. Which directory each harness tolerates a private subtree in is a
measured fact per harness and scope, and it lives beside the other measured facts in
`domain/harness.py` as `MANAGED_TREE_TARGETS` (D-346, D-359); inventing those rows here to make
this module self-contained would put a guess where evidence belongs.

Pure path policy: nothing here consults a filesystem, a working directory or the environment.
"""

from __future__ import annotations

import posixpath
import re

from .identifiers import ArtifactCoordinate

__all__ = ["MANAGED_TREE_DIRECTORY", "installation_tree_root"]

#: The one directory name AART owns inside somebody else's harness. Everything it writes that is
#: not a harness-format file of the harness's own is under this, so an operator looking at a
#: harness directory can tell at a glance which subtree is not theirs.
MANAGED_TREE_DIRECTORY = "aart-cli"

#: A path component AART is willing to compose from operator input. It is the slug the
#: configuration and protocol schemas already validate aliases, kinds and names against, repeated
#: here rather than assumed: the alias is typed by a person and the name comes from a Registry, and
#: a `..` that reached this far would place a tree outside the harness that is supposed to own it.
#: Refused rather than encoded, because an encoded component is a path nobody can read back to the
#: installation it belongs to.
_COMPONENT_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


def _component(value: str, label: str) -> str:
    if not isinstance(value, str) or _COMPONENT_RE.fullmatch(value) is None:
        raise ValueError(f"{label} is not a usable path component: {value!r}")
    return value


def _harness_root(path: str) -> str:
    if (
        not isinstance(path, str)
        or not posixpath.isabs(path)
        or posixpath.normpath(path) != path
        or any(character in path for character in "\r\n")
    ):
        raise ValueError("harness root must be a normalized absolute path")
    return path


def installation_tree_root(coordinate: ArtifactCoordinate, *, harness_root: str) -> str:
    """The absolute root of the private tree this installation owns inside `harness_root`.

    `harness_root` is the directory the harness adapter has decided AART may own a subtree in, at
    the scope and profile being installed into -- so two profiles, or two homes, arrive here as two
    different roots and get two different trees without this function knowing why.
    """

    if not isinstance(coordinate, ArtifactCoordinate):
        raise ValueError("an installation tree needs an artifact coordinate")
    return posixpath.join(
        _harness_root(harness_root),
        MANAGED_TREE_DIRECTORY,
        _component(coordinate.artifact.kind, "artifact kind"),
        _component(coordinate.source.value, "registry alias"),
        _component(coordinate.artifact.name, "artifact name"),
    )
