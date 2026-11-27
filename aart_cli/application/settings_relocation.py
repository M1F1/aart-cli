"""A recorded installation, moved to the settings file its harness reads on this machine (§218).

A receipt records which settings file an MCP server or a plugin was written into. For OpenCode's
user scope that was `opencode.json` until D-530, and an OpenCode 2 a launcher starts reads only
`opencode.jsonc` once that file exists -- which OpenCode 1.x creates the first time it runs. Such
an installation is installed, and invisible to the harness.

So a recorded installation is judged against the file its harness reads now, not the one it was
written into. The receipt this returns names that file; measured against it, the entry is missing
there, the repair writes it there (and out of the file it was in), and the repair records this
receipt. Nothing is moved by reading: only a reviewed repair, update or install writes.

Pure: which files exist is asked through `exists`, with absolute paths.
"""

from __future__ import annotations

import posixpath
from collections.abc import Callable
from dataclasses import dataclass, replace

from aart_cli.domain.harness import McpRegistration, preferred_settings_path
from aart_cli.domain.receipts import (
    ArtifactReceipt,
    ArtifactSettingsEntry,
    InstallationReceipt,
    PlacedArtifactReceipt,
)

__all__ = ["SettingsMove", "relocated_receipt", "settings_moves"]


@dataclass(frozen=True, slots=True)
class SettingsMove:
    """One entry recorded in a settings file its harness no longer reads, and the one it does."""

    harness: str
    recorded: str
    read: str


def settings_moves(
    original: ArtifactReceipt, relocated: ArtifactReceipt
) -> tuple[SettingsMove, ...]:
    """What `relocated_receipt` moved, in absolute paths, for saying so where it is reviewed."""

    moves: list[SettingsMove] = []
    if isinstance(original, InstallationReceipt) and isinstance(relocated, InstallationReceipt):
        base = original.owner.root if original.owner is not None else ""
        for before, after in zip(original.registrations, relocated.registrations, strict=True):
            if before.target.settings_file != after.target.settings_file:
                moves.append(
                    SettingsMove(
                        before.target.harness,
                        posixpath.join(base, before.target.settings_file),
                        posixpath.join(base, after.target.settings_file),
                    )
                )
    if isinstance(original, PlacedArtifactReceipt) and isinstance(relocated, PlacedArtifactReceipt):
        for entry_before, entry_after in zip(original.settings, relocated.settings, strict=True):
            if entry_before.destination != entry_after.destination:
                moves.append(
                    SettingsMove(
                        entry_before.harness, entry_before.destination, entry_after.destination
                    )
                )
    return tuple(moves)


def _registration(
    registration: McpRegistration, root: str, exists: Callable[[str], bool]
) -> McpRegistration:
    target = registration.target
    recorded = posixpath.join(root, target.settings_file)
    preferred = preferred_settings_path(target.harness, recorded, exists)
    if preferred == recorded:
        return registration
    moved = replace(target, settings_file=posixpath.relpath(preferred, root))
    return replace(registration, target=moved)


def _entry(entry: ArtifactSettingsEntry, exists: Callable[[str], bool]) -> ArtifactSettingsEntry:
    preferred = preferred_settings_path(entry.harness, entry.destination, exists)
    return entry if preferred == entry.destination else replace(entry, destination=preferred)


def relocated_receipt(
    receipt: ArtifactReceipt, *, root: str, exists: Callable[[str], bool]
) -> ArtifactReceipt:
    """`receipt` with every settings file its harness no longer reads replaced by the one it does.

    `root` is the scope root the receipt's relative settings files are under: the installation's
    own (`owner.root`) when it records one, which is where it was made (D-479).
    """

    if isinstance(receipt, InstallationReceipt):
        base = receipt.owner.root if receipt.owner is not None else root
        registrations = tuple(_registration(item, base, exists) for item in receipt.registrations)
        if registrations == receipt.registrations:
            return receipt
        return replace(receipt, registrations=registrations)
    if isinstance(receipt, PlacedArtifactReceipt):
        settings = tuple(_entry(item, exists) for item in receipt.settings)
        if settings == receipt.settings:
            return receipt
        return replace(receipt, settings=settings)
    return receipt
