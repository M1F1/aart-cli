"""Read what the installed objects on this machine declare about their own setup.

The receipt says which immutable object an installation came from; the object says whether that
artifact declares post-install setup. Putting the two together is this module, and it is the whole
of the effect boundary: a receipt store to read the records, an object store to read the packages.

A coordinate whose receipt names no object yields nothing rather than an error. Receipts written
before `object_digest` existed genuinely do not know which package they came from (D-122), and an
honest reader says nothing about an artifact it cannot look up rather than guessing which package
on this machine the installation probably meant.
"""

from __future__ import annotations

from agent_artifacts.application.installed_setup import (
    DeclaredArtifactSetup,
    declared_artifact_setup,
)
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import ArtifactCoordinate
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.protocol.authoring import PACKAGE_MANIFEST_FILENAME
from agent_artifacts.protocol.native_schema import parse_artifact_manifest
from agent_artifacts.protocol.native_tree import SnapshotEntryKind
from agent_artifacts.store.model import ObjectReadRequest, object_store_paths

from .object_store import read_object
from .receipt_store import LocalReceiptStore

__all__ = ["INSTALLED_SETUP_UNREADABLE", "read_declared_setup"]

INSTALLED_SETUP_UNREADABLE = DiagnosticCode("installed-setup-unreadable")


def _error(message: str) -> Err:
    return Err((Diagnostic(INSTALLED_SETUP_UNREADABLE, Severity.ERROR, message),))


def read_declared_setup(
    coordinates: tuple[ArtifactCoordinate, ...],
    *,
    state_root: str,
    data_root: str,
) -> Result[tuple[DeclaredArtifactSetup, ...]]:
    """What each of these installed artifacts declares, in the order they were named.

    An object a receipt names and the store cannot produce is an error rather than an omission: a
    receipt naming an object that is not there is precisely the dangling identity the optional
    `object_digest` was shaped to avoid creating, and quietly reporting "no setup declared" for it
    would turn a broken store into a clean bill of health.
    """

    store = LocalReceiptStore(state_root)
    paths = object_store_paths(data_root)
    declared: list[DeclaredArtifactSetup] = []
    for coordinate in coordinates:
        record = store.record(coordinate)
        if isinstance(record, Err):
            return record
        digest = record.value.receipt.object_digest
        if digest is None:
            continue
        loaded = read_object(ObjectReadRequest(paths, digest))
        if isinstance(loaded, Err):
            return loaded
        if loaded.value is None:
            return _error(f"the object {coordinate} was installed from is not in the store")
        entries = loaded.value.candidate.entries
        manifest_entry = next(
            (
                entry
                for entry in entries
                if str(entry.path) == PACKAGE_MANIFEST_FILENAME
                and entry.kind is SnapshotEntryKind.FILE
            ),
            None,
        )
        if manifest_entry is None:
            return _error(f"the object {coordinate} was installed from describes no artifact")
        manifest = parse_artifact_manifest(manifest_entry.content, path=PACKAGE_MANIFEST_FILENAME)
        if isinstance(manifest, Err):
            return manifest
        found = declared_artifact_setup(
            coordinate,
            digest,
            manifest.value,
            package_paths=frozenset(str(entry.path) for entry in entries),
        )
        if found is not None:
            declared.append(found)
    return Ok(tuple(declared))
