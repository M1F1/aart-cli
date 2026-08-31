"""Where finished installations and finished actions are kept between processes.

A receipt is only evidence if it outlives the process that wrote it, so this adapter is the whole
of that persistence: canonical JSON, one file per record, staged and renamed into place, readable
only by its owner.

Nothing here interprets a receipt.  Parsing belongs to the domain and to the consumer projections;
this module's single judgement is that a document it cannot read is reported rather than dropped.
A receipt silently skipped would present itself to every later reader as an installation that never
happened, which is exactly the failure a receipt exists to prevent.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
from typing import cast

from agent_artifacts.application.consumer_views import (
    ReceiptDetailView,
    receipt_detail_from_data,
    receipt_detail_to_data,
)
from agent_artifacts.configuration.policy import redact_text
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    ArtifactKind,
    SourceAlias,
)
from agent_artifacts.domain.receipts import (
    ArtifactReceipt,
    InstallationReceipt,
    InstalledRecord,
    PlacedArtifactReceipt,
    installation_receipt_from_data,
    installation_receipt_to_data,
    placed_artifact_receipt_from_data,
    placed_artifact_receipt_to_data,
)
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import OwnershipKind, OwnershipReason
from agent_artifacts.domain.serialization import CanonicalValue, canonical_json_bytes

__all__ = [
    "RECEIPT_ABSENT",
    "RECEIPT_UNREADABLE",
    "RECEIPT_UNWRITABLE",
    "InstalledRecord",
    "LocalReceiptStore",
]

RECEIPT_ABSENT = DiagnosticCode("receipt-absent")
RECEIPT_UNREADABLE = DiagnosticCode("receipt-unreadable")
RECEIPT_UNWRITABLE = DiagnosticCode("receipt-unwritable")

_MAX_RECEIPT_BYTES = 1024 * 1024
_INSTALLATION = "installation"
_PLACED = "placed"
_KINDS: frozenset[str] = frozenset({"skill", "guideline", "mcp", "hook", "memory", "collection"})


def _error(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, redact_text(message)),))


def _coordinate_to_data(coordinate: ArtifactCoordinate) -> dict[str, object]:
    # Structural rather than the printed form: `source/kind/name@version` cannot be split back
    # apart without assuming no part ever contains a separator, and nothing enforces that here.
    return {
        "kind": coordinate.artifact.kind,
        "name": coordinate.artifact.name,
        "source": coordinate.source.value,
        "version": coordinate.version,
    }


def _coordinate_from_data(data: object) -> ArtifactCoordinate:
    if not isinstance(data, dict):
        raise ValueError("a coordinate must be a mapping")
    kind, name, source = data.get("kind"), data.get("name"), data.get("source")
    version = data.get("version")
    if kind not in _KINDS or not isinstance(name, str) or not isinstance(source, str):
        raise ValueError("a stored coordinate is not a coordinate this build understands")
    if version is not None and not isinstance(version, str):
        raise ValueError("a stored coordinate version must be a string or absent")
    identity = cast("ArtifactKind", kind)
    return ArtifactCoordinate(SourceAlias(source), ArtifactIdentity(identity, name), version)


def _ownership_to_data(ownership: tuple[OwnershipReason, ...]) -> list[dict[str, object]]:
    return [{"kind": item.kind.value, "owner": item.owner} for item in ownership]


def _ownership_from_data(data: object) -> tuple[OwnershipReason, ...]:
    if data is None:
        return ()
    if not isinstance(data, list):
        raise ValueError("recorded ownership must be a list")
    reasons = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("an ownership reason must be a mapping")
        try:
            kind = OwnershipKind(str(item["kind"]))
            reasons.append(OwnershipReason(kind, str(item["owner"])))
        except KeyError as error:
            raise ValueError(f"an ownership reason is missing {error.args[0]}") from None
        except ValueError:
            # A kind this build does not know is refused rather than dropped: an owner nobody can
            # name is an owner uninstall would quietly ignore.
            raise ValueError(f"{item['kind']} is not an ownership this build understands") from None
    return tuple(reasons)


def _canonical(document: Mapping[str, object]) -> bytes:
    return canonical_json_bytes(cast("CanonicalValue", document))


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write(path: Path, content: bytes) -> Result[str]:
    stage: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, stage = tempfile.mkstemp(prefix=".aart-receipt-", dir=path.parent)
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(stage, path)
        stage = None
        os.chmod(path, 0o600)
        _fsync_directory(path.parent)
        return Ok(str(path))
    except OSError as error:
        return _error(RECEIPT_UNWRITABLE, f"cannot record {path}: {error}")
    finally:
        if stage is not None:
            try:
                os.unlink(stage)
            except OSError:
                pass


def _read(path: Path) -> Result[dict[str, object]]:
    try:
        if path.stat().st_size > _MAX_RECEIPT_BYTES:
            return _error(RECEIPT_UNREADABLE, f"{path} is too large to be a receipt")
        document = json.loads(path.read_bytes().decode("utf-8"))
    except FileNotFoundError:
        return _error(RECEIPT_ABSENT, f"nothing is recorded at {path}")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return _error(RECEIPT_UNREADABLE, f"cannot read {path}: {error}")
    if not isinstance(document, dict):
        return _error(RECEIPT_UNREADABLE, f"{path} does not hold a record")
    return Ok(document)


def _unreadable(path: Path, failure: Err) -> Err:
    detail = failure.diagnostics[0].message if failure.diagnostics else "it cannot be parsed"
    return _error(RECEIPT_UNREADABLE, f"{path} is not a receipt this build can read: {detail}")


@dataclass(frozen=True, slots=True)
class LocalReceiptStore:
    """Installations and finished actions, under one managed state root."""

    state_root: str

    def __post_init__(self) -> None:
        if not isinstance(self.state_root, str) or not self.state_root:
            raise ValueError("a receipt store needs a state root")

    @property
    def installations_directory(self) -> str:
        return str(Path(self.state_root) / "installations")

    @property
    def actions_directory(self) -> str:
        return str(Path(self.state_root) / "activity")

    def path_for(self, coordinate: ArtifactCoordinate) -> str:
        """The managed file one coordinate's receipt lives in.

        Named by digest rather than by the coordinate itself, so a source alias or artifact name
        can never decide a path on disk.
        """

        if not isinstance(coordinate, ArtifactCoordinate):
            raise ValueError("a receipt path needs an artifact coordinate")
        name = _digest(_canonical(_coordinate_to_data(coordinate)))
        return str(Path(self.installations_directory) / f"{name}.json")

    def record_installation(
        self,
        coordinate: ArtifactCoordinate,
        receipt: ArtifactReceipt,
        *,
        ownership: tuple[OwnershipReason, ...] | None = None,
    ) -> Result[str]:
        """Record what one installation left behind, and optionally who owns it.

        `ownership=None` means this action has no opinion: whatever was already recorded is carried
        forward. An empty tuple is an opinion -- that nobody owns this any more -- and replaces it.
        """

        if not isinstance(receipt, (InstallationReceipt, PlacedArtifactReceipt)):
            return _error(RECEIPT_UNWRITABLE, "an installation record needs a receipt")
        if ownership is not None and any(
            not isinstance(item, OwnershipReason) for item in ownership
        ):
            return _error(RECEIPT_UNWRITABLE, "an installation is owned by ownership reasons")
        if ownership is None:
            standing = self.record(coordinate)
            if isinstance(standing, Err) and standing.diagnostics[0].code is not RECEIPT_ABSENT:
                return standing
            ownership = () if isinstance(standing, Err) else standing.value.ownership
        document = {
            # Which of the two receipts this document holds. A record written before placements
            # existed carries no marker, and every one of those holds an installation.
            "kind": _PLACED if isinstance(receipt, PlacedArtifactReceipt) else _INSTALLATION,
            "coordinate": _coordinate_to_data(coordinate),
            "ownership": _ownership_to_data(ownership),
            "receipt": (
                placed_artifact_receipt_to_data(receipt)
                if isinstance(receipt, PlacedArtifactReceipt)
                else installation_receipt_to_data(receipt)
            ),
        }
        return _write(Path(self.path_for(coordinate)), _canonical(document))

    def _installed_record(self, path: Path) -> Result[InstalledRecord]:
        read = _read(path)
        if isinstance(read, Err):
            return read
        try:
            coordinate = _coordinate_from_data(read.value.get("coordinate"))
            ownership = _ownership_from_data(read.value.get("ownership"))
        except ValueError as error:
            return _error(RECEIPT_UNREADABLE, f"{path} names no artifact: {error}")
        kind = read.value.get("kind", _INSTALLATION)
        if kind not in (_INSTALLATION, _PLACED):
            # Named rather than defaulted. A document claiming a kind this build does not write is
            # not an older record, and reading it as one would answer for an installation whose
            # shape nobody here understands.
            return _error(RECEIPT_UNREADABLE, f"{path} claims to be a {kind!r} record")
        parse = (
            placed_artifact_receipt_from_data if kind == _PLACED else installation_receipt_from_data
        )
        parsed = parse(read.value.get("receipt"))
        if isinstance(parsed, Err):
            return _unreadable(path, parsed)
        return Ok(InstalledRecord(coordinate, parsed.value, ownership))

    def record(self, coordinate: ArtifactCoordinate) -> Result[InstalledRecord]:
        """One recorded installation in full: the receipt and why it is installed."""

        return self._installed_record(Path(self.path_for(coordinate)))

    def installation(self, coordinate: ArtifactCoordinate) -> Result[ArtifactReceipt]:
        record = self._installed_record(Path(self.path_for(coordinate)))
        return record if isinstance(record, Err) else Ok(record.value.receipt)

    def installations(self) -> Result[tuple[InstalledRecord, ...]]:
        """Every recorded installation, or the first reason one of them could not be read."""

        records = []
        for path in self._files(Path(self.installations_directory)):
            record = self._installed_record(path)
            if isinstance(record, Err):
                return record
            records.append(record.value)
        return Ok(tuple(sorted(records, key=lambda item: str(item.coordinate))))

    def forget_installation(self, coordinate: ArtifactCoordinate) -> Result[str]:
        path = Path(self.path_for(coordinate))
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            return _error(RECEIPT_UNWRITABLE, f"cannot forget {path}: {error}")
        return Ok(str(path))

    def record_action(self, receipt: ReceiptDetailView) -> Result[str]:
        """Record one finished action under the moment it finished.

        The filename carries that moment normalized to UTC, so the newest actions can be found
        without opening every file even when they were written in different offsets.
        """

        if not isinstance(receipt, ReceiptDetailView):
            return _error(RECEIPT_UNWRITABLE, "an action record needs a receipt")
        document = receipt_detail_to_data(receipt)
        content = _canonical(document)
        moment = receipt.moment.astimezone(timezone.utc).isoformat()
        name = f"{moment}-{_digest(content)[:12]}.json"
        return _write(Path(self.actions_directory) / name, content)

    def actions(self, *, limit: int | None = None) -> Result[tuple[ReceiptDetailView, ...]]:
        """Finished actions, newest first.

        A limit bounds what is read, not what is reported: records older than the limit are never
        opened, so nothing about them -- including their readability -- is claimed either way.
        """

        if limit is not None and (not isinstance(limit, int) or limit < 0):
            raise ValueError("an action limit must be a whole number of records")
        paths = sorted(self._files(Path(self.actions_directory)), reverse=True)
        receipts = []
        for path in paths if limit is None else paths[:limit]:
            read = _read(path)
            if isinstance(read, Err):
                return read
            parsed = receipt_detail_from_data(read.value)
            if isinstance(parsed, Err):
                return _unreadable(path, parsed)
            receipts.append(parsed.value)
        return Ok(tuple(sorted(receipts, key=lambda item: item.moment, reverse=True)))

    @staticmethod
    def _files(directory: Path) -> tuple[Path, ...]:
        try:
            return tuple(item for item in directory.iterdir() if item.suffix == ".json")
        except (FileNotFoundError, NotADirectoryError):
            return ()
