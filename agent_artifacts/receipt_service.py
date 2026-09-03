"""RR-5: one receipt service, two front-ends.

`VN-9` established that a maintainer action existing only in the CLI is half-shipped.  The way
to ship an action twice without writing it twice is for both skins to call the same functions
and render the same lines — so this module owns resolving an installation to its persisted
record, and projecting that record into the three payloads, and neither front-end owns any of
it.

Emission stays with the front-end: the CLI prints, the text front-end writes through its own
`write` port.  Everything above that line is here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, Tuple

from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import ArtifactCoordinate
from agent_artifacts.domain.receipts import InstalledRecord, receipt_profiles
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.install_state.paths import install_state_paths
from agent_artifacts.install_state.schema import parse_install_state
from agent_artifacts.io import fs
from agent_artifacts.io.receipt_store import LocalReceiptStore
from agent_artifacts.model import InstallScope, SetupState, SetupStateRecord
from agent_artifacts.setup import dump_setup_state
from agent_artifacts.setup_receipt import (
    RECEIPT_INVALID,
    RECEIPT_NOT_INSTALLED,
    ReceiptLocation,
    locate_receipt_setup_record,
    locate_setup_record,
    missing_record,
    read_setup_record,
)
from agent_artifacts.setup_render import receipt_payload
from agent_artifacts.setup_runtime import production_runtime, rollback_record
from agent_artifacts.setup_undo import plan_undo, undo_digest, undo_payload
from agent_artifacts.setup_verify import plan_verification, verification_payload, verify_claims
from agent_artifacts.setup_verify_probes import local_probes

RECEIPT_ACTIONS: Tuple[str, ...] = ("show", "verify", "undo")

_NO_MANIFEST = "this scope has no installation state, so no setup run has been recorded in it"


@dataclass(frozen=True, slots=True)
class LoadedReceipt:
    """One installation's persisted record, and where it and its project live."""

    record: SetupStateRecord
    location: ReceiptLocation
    project_root: str
    data_root: str


def load_receipt(
    *,
    data_root: str,
    project_root: str,
    user_home: str,
    scope: InstallScope,
    selector: str,
    profiles: Sequence[str] = (),
) -> Result[LoadedReceipt]:
    """Resolve one installation to the record a setup run persisted for it.

    Two stores can say an artifact is installed. The canonical receipt store is asked first, for
    the same reason `marketplace setup` resolves canonical receipts before the legacy catalogue
    (D-128): it is the store a configured install writes, and the one the legacy manifest is being
    retired in favour of. An installation the canonical store does not know is then looked for in
    the manifest, so a machine holding only legacy installations answers exactly as before, and a
    machine holding both answers for each from the store that recorded it (B-046).
    """

    recorded = LocalReceiptStore(os.path.join(data_root, "state")).installations()
    if isinstance(recorded, Err):
        # An unreadable receipt is an answer, not an absence: reporting it as "not installed"
        # would present an installation that happened as one that never did.
        return recorded
    located = _locate_canonical(
        recorded.value, scope=scope, selector=selector, profiles=profiles, data_root=data_root
    )
    if located is None:
        located = _locate_legacy(
            data_root=data_root,
            project_root=project_root,
            user_home=user_home,
            scope=scope,
            selector=selector,
            profiles=profiles,
            # Whether "this scope has no installation state" is a true sentence depends on the
            # other store. With configured installations on this machine, the manifest's absence
            # says nothing about the selector, and the honest refusal names the selector instead.
            configured=bool(recorded.value),
        )
    if isinstance(located, Err):
        return located
    location = located.value

    record_file = Path(location.state_path)
    if not record_file.is_file():
        return missing_record(location)
    record = read_setup_record(record_file.read_text(encoding="utf-8"), location=location)
    if isinstance(record, Err):
        return record
    bound = _bound(location, record.value)
    if isinstance(bound, Err):
        return bound
    return Ok(LoadedReceipt(record.value, bound.value, project_root, data_root))


def _bound(location: ReceiptLocation, record: SetupStateRecord) -> Result[ReceiptLocation]:
    """The location a reader is shown, checked against what the record itself claims.

    The canonical store keeps one receipt per coordinate and partitions nothing by scope, so until
    the record is read the scope is only the one the operator asked about. A record belonging to
    the other scope is a refusal rather than a rebinding: the operator asked about a scope, and
    answering with a different one silently is how `receipt show` would print an installation
    somebody is not looking at. The legacy manifest is scope-partitioned and so always agrees --
    if it ever does not, the two documents contradict each other and that is worth saying.

    The profile is the opposite case and is taken from the record. A receipt can serve several
    harnesses while setup ran for exactly one, and which one that was is a fact only the record
    holds.
    """

    if location.scope != record.scope:
        return _error(
            RECEIPT_NOT_INSTALLED,
            f"the setup record for {location.coordinate} belongs to {record.scope} scope, "
            f"not {location.scope}",
            (f"read it with: aart marketplace receipt show <coordinate> --scope {record.scope}",),
        )
    if location.profile == record.profile:
        return Ok(location)
    return Ok(
        ReceiptLocation(
            coordinate=location.coordinate,
            profile=record.profile,
            scope=record.scope,
            setup_state_ref=location.setup_state_ref,
            state_path=location.state_path,
        )
    )


def _locate_canonical(
    installed: Sequence[InstalledRecord],
    *,
    data_root: str,
    scope: InstallScope,
    selector: str,
    profiles: Sequence[str],
) -> Result[ReceiptLocation] | None:
    """Where a configured installation keeps its setup record, or `None` if it has none here.

    `None` rather than a refusal: not finding the selector in this store is not an answer, it is
    the reason to ask the other one.
    """

    chosen = tuple(profiles)
    matches = [
        item
        for item in installed
        if _names_receipt(item.coordinate, selector)
        and (not chosen or receipt_profiles(item.receipt) & set(chosen))
    ]
    if not matches:
        return None
    if len(matches) > 1:
        found = ", ".join(sorted(str(item.coordinate) for item in matches))
        return _error(
            RECEIPT_INVALID,
            f"{selector} names more than one configured installation: {found}",
            ("name one with: aart marketplace receipt show <coordinate>",),
        )
    record = matches[0]
    serves = sorted(receipt_profiles(record.receipt) & set(chosen)) if chosen else []
    return locate_receipt_setup_record(
        record.receipt,
        coordinate=str(record.coordinate),
        # The record replaces this once it is read (`_bound`); until then the operator's own
        # answer is the best one available, because the receipt may serve several harnesses and
        # only one of them ran setup.
        profile=serves[0] if serves else sorted(receipt_profiles(record.receipt) or {""})[0],
        scope=scope,
        data_root=data_root,
    )


def _locate_legacy(
    *,
    data_root: str,
    project_root: str,
    user_home: str,
    scope: InstallScope,
    selector: str,
    profiles: Sequence[str],
    configured: bool = False,
) -> Result[ReceiptLocation]:
    """Where the retiring install-state manifest says this installation keeps its record."""

    state_paths = install_state_paths(
        scope,
        project_root=project_root,
        user_home=user_home,
        data_root=data_root,
    )
    chosen = tuple(profiles)
    missing = _error(
        RECEIPT_NOT_INSTALLED,
        f"no installation of {selector} in {scope} scope"
        + (f" for profile {', '.join(chosen)}" if chosen else ""),
        (
            "list what is installed with: aart marketplace status",
            "install it with: aart marketplace install",
        ),
    )
    manifest = Path(state_paths.destination_path)
    if not manifest.is_file():
        return missing if configured else _error(RECEIPT_NOT_INSTALLED, _NO_MANIFEST)
    parsed = parse_install_state(manifest.read_bytes())
    if isinstance(parsed, Err):
        return parsed

    candidates = _candidates(parsed.value, selector=selector, scope=scope)
    if chosen:
        candidates = [record for record in candidates if record.profile in chosen]
    if not candidates:
        return missing
    if len(candidates) > 1:
        found = ", ".join(sorted(f"{item.coordinate}#{item.profile}" for item in candidates))
        return _error(
            RECEIPT_INVALID,
            f"{selector} names more than one installation in {scope} scope: {found}",
            ("name one with: aart marketplace receipt show <coordinate> --profile <profile>",),
        )

    installation = candidates[0]
    return locate_setup_record(
        parsed.value,
        coordinate=str(installation.coordinate),
        profile=installation.profile,
        scope=scope,
        data_root=data_root,
    )


def show_view(loaded: LoadedReceipt) -> dict:
    return receipt_payload(loaded.record, location=loaded.location)


def verify_view(loaded: LoadedReceipt) -> dict:
    return verification_payload(
        verify_claims(
            plan_verification(loaded.record),
            probes=local_probes(
                project_root=loaded.project_root,
                run_root=loaded.data_root,
            ),
        )
    )


def undo_view(loaded: LoadedReceipt) -> tuple[dict, str]:
    payload = undo_payload(
        plan_undo(loaded.record),
        coordinate=loaded.location.coordinate,
        profile=loaded.location.profile,
        scope=loaded.location.scope,
    )
    return payload, undo_digest(payload)


def apply_undo(loaded: LoadedReceipt) -> SetupStateRecord:
    """Reverse the recorded effects and write the resulting record back over the same file."""

    rolled = rollback_record(loaded.record, production_runtime())
    fs.write_atomic(
        loaded.location.state_path,
        (dump_setup_state(SetupState((rolled,))) + "\n").encode("utf-8"),
    )
    return rolled


def resolved_paths(
    *,
    data_root: str,
    project: str | None,
    user_home: str | None,
) -> tuple[str, str]:
    """The project root and home a receipt operation reads, resolved once and in one place."""

    del data_root
    return (
        os.path.abspath(project or os.getcwd()),
        os.path.abspath(user_home or os.path.expanduser("~")),
    )


def unsupported_action(action: str | None) -> Err:
    return _error(
        RECEIPT_INVALID,
        f"unsupported receipt action {action!r}",
        (
            "read a persisted record with: aart marketplace receipt show <coordinate>",
            "check whether it is still true with: aart marketplace receipt verify <coordinate>",
            "reverse what it recorded with: aart marketplace receipt undo <coordinate>",
        ),
    )


def _candidates(state, *, selector: str, scope: str) -> list:
    """Every installation the operator's selector could mean, in this scope.

    A coordinate may be given fully qualified, with or without a version, or as the
    ``kind/name`` tail. Ambiguity is reported rather than resolved by picking the first, because
    a receipt printed for the wrong installation reads exactly like a correct one.
    """

    return [
        record
        for record in state.installations
        if record.scope == scope and _names(str(record.coordinate), selector)
    ]


def _names(coordinate: str, selector: str) -> bool:
    """Whether one printed coordinate is what this selector means."""

    wanted = selector.split("@", 1)[0]
    return coordinate == wanted or coordinate.endswith(f"/{wanted}")


def _names_receipt(coordinate: ArtifactCoordinate, selector: str) -> bool:
    """The same question of a canonical receipt, whose coordinate carries its version.

    The install-state manifest records a coordinate without one, so a selector written the way
    every remediation in this module spells it -- `source/kind/name`, or the `kind/name` tail --
    would match nothing here. Both printed forms are offered rather than the version being
    stripped from the selector, so `receipt show name@1.0.0` still means that exact version.
    """

    versionless = str(ArtifactCoordinate(coordinate.source, coordinate.artifact))
    return _names(str(coordinate), selector) or _names(versionless, selector)


def _error(code: DiagnosticCode, message: str, remediation: Tuple[str, ...] = ()) -> Err:
    return Err(
        (
            Diagnostic(
                code,
                Severity.ERROR,
                message,
                remediation=remediation
                or ("list what is installed with: aart marketplace status",),
            ),
        )
    )


__all__ = [
    "RECEIPT_ACTIONS",
    "LoadedReceipt",
    "apply_undo",
    "load_receipt",
    "resolved_paths",
    "show_view",
    "undo_view",
    "unsupported_action",
    "verify_view",
]
