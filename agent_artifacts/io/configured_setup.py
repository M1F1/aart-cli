"""Receipt-backed setup-engine ports for configured approved installations."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable, Literal

from agent_artifacts.application.marketplace_resolution import RegistryTrust
from agent_artifacts.application.store import (
    ReferenceUpdatePorts,
    ReferenceUpdateRequest,
    replace_references,
)
from agent_artifacts.configuration.model import SourceKind
from agent_artifacts.configuration.policy import EffectiveConfiguration, redact_text
from agent_artifacts.consumer.model import (
    ConsumerActionRequest,
    ConsumerOutcome,
    ConsumerReview,
    ConsumerReviewEffect,
    ConsumerReviewItem,
    ConsumerSetupDeclaration,
    ConsumerSetupFailure,
    ConsumerSetupQueue,
    ConsumerTerminalItem,
)
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.effects import DeliveryKind
from agent_artifacts.domain.identifiers import ArtifactCoordinate, ObjectDigest
from agent_artifacts.domain.receipts import (
    InstallationReceipt,
    PlacedArtifactReceipt,
    receipt_profiles,
)
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.install_state.model import (
    ArtifactEvidence,
    EffectProof,
    InstallationRecord,
    SourceEvidence,
)
from agent_artifacts.installation.io import LocalInstallAdapter, _lock, _restore, _write_atomic
from agent_artifacts.installation.model import InstallLocation
from agent_artifacts.marketplace.model import TrustClass
from agent_artifacts.model import Err as LegacyErr
from agent_artifacts.model import SetupState, SetupStateRecord
from agent_artifacts.protocol.hashing import sha256_bytes
from agent_artifacts.protocol.native_tree import compile_native_package
from agent_artifacts.protocol.semver import parse_semver
from agent_artifacts.setup import dump_setup_state, parse_setup_state
from agent_artifacts.setup_engine import (
    ApprovedObjectIdentity,
    CanonicalSetupPlan,
    InstalledSubject,
    SetupQueueOutcome,
    SetupRequest,
    SetupSubjectPort,
    execute_setup_queue,
    prepare_setup_attempt,
)
from agent_artifacts.setup_engine.application import Consent
from agent_artifacts.setup_runtime import SetupRuntime, production_runtime
from agent_artifacts.sources.model import (
    CurrentSourceRequest,
    source_instance_id,
    source_store_paths,
)
from agent_artifacts.store.model import (
    ObjectReadRequest,
    ReferenceIndex,
    ReferenceKind,
    ReferenceReadRequest,
    object_store_paths,
)

from .configured_installation_action import CompletedConfiguredInstallation, InstallationHost
from .configured_selection import load_configured_approved_marketplace
from .installed_setup import read_declared_setup
from .object_store import read_object
from .receipt_store import LocalReceiptStore
from .reference_store import read_references, write_references
from .source_store import read_current_source
from .store_lock import acquire_store_lock, release_store_lock

CONFIGURED_SETUP_INVALID = DiagnosticCode("configured-setup-invalid")


def _error(message: str) -> Err:
    return Err((Diagnostic(CONFIGURED_SETUP_INVALID, Severity.ERROR, redact_text(message)),))


def _unversioned(coordinate: ArtifactCoordinate) -> ArtifactCoordinate:
    return ArtifactCoordinate(coordinate.source, coordinate.artifact)


def _relative_destination(path: str, host: InstallationHost) -> str:
    if host.scope.value == "user":
        return path
    try:
        relative = Path(path).relative_to(host.project_root).as_posix()
    except ValueError as error:
        raise ValueError("installed project effect lies outside the project root") from error
    if not relative or relative == ".":
        raise ValueError("installed project effect cannot own the project root")
    return relative


def _source_path(path: str, root: str) -> str:
    try:
        relative = Path(path).relative_to(root).as_posix()
    except ValueError as error:
        raise ValueError("installed effect source lies outside its artifact root") from error
    if not relative or relative == ".":
        raise ValueError("installed effect source cannot be the artifact root")
    return relative


def _effect_proofs(
    receipt: InstallationReceipt | PlacedArtifactReceipt,
    *,
    profile: str,
    host: InstallationHost,
) -> tuple[EffectProof, ...]:
    if isinstance(receipt, InstallationReceipt):
        if profile not in receipt_profiles(receipt):
            return ()
        return (
            EffectProof(
                "write-file",
                _relative_destination(receipt.launcher, host),
                "copy",
                receipt.launcher_digest,
                source_path=_source_path(receipt.launcher, receipt.root),
            ),
        )
    deliveries = tuple(
        EffectProof(
            "copy-tree" if item.kind is DeliveryKind.TREE else "write-file",
            _relative_destination(item.destination, host),
            "copy",
            item.digest,
            source_path=_source_path(item.source, receipt.root),
        )
        for item in receipt.deliveries
        if item.harness == profile
    )
    merges = tuple(
        EffectProof(
            "managed-block",
            _relative_destination(item.destination, host),
            "copy",
            item.digest,
        )
        for item in receipt.merges
        if item.harness == profile
    )
    return (*deliveries, *merges)


def configured_setup_subject(
    effective: EffectiveConfiguration,
    host: InstallationHost,
) -> SetupSubjectPort:
    """Resolve setup evidence from the configured registry and canonical receipt stores."""

    if not isinstance(effective, EffectiveConfiguration) or not isinstance(host, InstallationHost):
        raise ValueError("configured setup needs effective configuration and an installation host")
    receipts = LocalReceiptStore(host.state_root)

    def resolve(request: SetupRequest) -> Result[InstalledSubject]:
        if request.scope != host.scope.value:
            return _error("setup scope does not match the configured installation store")
        installed = receipts.installations()
        if isinstance(installed, Err):
            return installed
        matches = tuple(
            item
            for item in installed.value
            if _unversioned(item.coordinate) == request.coordinate
            and request.profile in receipt_profiles(item.receipt)
        )
        if len(matches) != 1:
            return _error("setup requires one exact configured installation receipt")
        installed_record = matches[0]
        receipt = installed_record.receipt
        if receipt.object_digest is None:
            return _error("configured installation receipt does not name its immutable object")

        marketplace = load_configured_approved_marketplace(effective, data_root=host.data_root)
        if isinstance(marketplace, Err):
            return marketplace
        approved = next(
            (
                item
                for item in marketplace.value.artifacts
                if item.version.coordinate == installed_record.coordinate
            ),
            None,
        )
        registry = next(
            (
                item
                for item in marketplace.value.registries
                if item.alias == installed_record.coordinate.source
            ),
            None,
        )
        if (
            approved is None
            or registry is None
            or registry.trust is not RegistryTrust.REGISTRY_REVIEWED
        ):
            return _error("installed artifact is no longer approved by its configured registry")
        if approved.version.object_digest != receipt.object_digest:
            return _error(
                "installed receipt object no longer matches the approved registry version"
            )

        configured = next(
            (
                item
                for item in effective.configuration.sources
                if item.enabled
                and item.kind is SourceKind.REGISTRY_GIT
                and item.alias == installed_record.coordinate.source
            ),
            None,
        )
        if configured is None:
            return _error("installed artifact has no enabled configured registry")
        current = read_current_source(
            CurrentSourceRequest(
                source_store_paths(host.data_root, source_instance_id(configured)),
                configured.alias,
            )
        )
        if isinstance(current, Err):
            return current
        if current.value is None:
            return _error("configured registry has no synchronized current snapshot")

        loaded = read_object(
            ObjectReadRequest(object_store_paths(host.data_root), receipt.object_digest)
        )
        if isinstance(loaded, Err):
            return loaded
        if loaded.value is None:
            return _error("configured installation object is unavailable")
        package = compile_native_package(
            loaded.value.candidate.entries,
            expected_identity=installed_record.coordinate.artifact,
        )
        if isinstance(package, Err):
            return package
        version = parse_semver(installed_record.coordinate.version or "")
        if isinstance(version, Err):
            return _error("configured installation receipt does not name an exact version")
        effects = _effect_proofs(receipt, profile=request.profile, host=host)
        if not effects:
            return _error("configured installation receipt has no effect for the setup profile")
        try:
            record = InstallationRecord(
                request.coordinate,
                SourceEvidence(
                    configured.alias,
                    current.value.declared_source_id,
                    configured.kind,
                    configured.location,
                    current.value.candidate.resolved_revision,
                    configured.ref,
                ),
                ArtifactEvidence(
                    installed_record.coordinate.artifact,
                    version.value,
                    package.value.manifest_digest,
                    approved.version.payload_digest,
                    receipt.object_digest,
                ),
                request.profile,
                1,
                request.scope,
                "copy",
                effects,
                # Both receipt shapes carry it, so read it rather than probing for it: a
                # shape that stopped carrying one should fail here, not silently read as unset.
                setup_state_ref=receipt.setup_state_ref,
            )
            record_path = receipts.path_for(installed_record.coordinate)
            return Ok(
                InstalledSubject(
                    record_path,
                    record_path + ".lock",
                    record,
                    TrustClass.REGISTRY_REVIEWED,
                    registry.snapshot,
                    ApprovedObjectIdentity(approved.version.object_digest),
                )
            )
        except ValueError as error:
            return _error(f"configured installation cannot become setup evidence: {error}")

    return resolve


def _detail(diagnostics: tuple[Diagnostic, ...]) -> str:
    return "; ".join(item.message for item in diagnostics)


def _absolute_effects(
    subject: InstalledSubject, host: InstallationHost
) -> tuple[ConsumerReviewEffect, ...]:
    effects = []
    for effect in subject.record.effects:
        destination = effect.destination
        if subject.record.scope == "project":
            destination = str(Path(host.project_root) / destination)
        effects.append(ConsumerReviewEffect(effect.kind, destination, effect.actual_mode))
    return tuple(effects)


def configured_consumer_completion(
    completed: CompletedConfiguredInstallation,
    effective: EffectiveConfiguration,
    host: InstallationHost,
    *,
    action: Literal["install", "update"],
) -> Result[tuple[ConsumerReview, ConsumerOutcome, ConfiguredSetupService]]:
    """Project a recorded canonical action into the shared setup/reporting contract.

    This is deliberately a projection, not another planner.  Every setup decision is still made
    by ``prepare_setup_attempt`` below from the receipt-backed subject; the values assembled here
    only give the existing terminal/reporting boundary the exact identities and payload outcome it
    already understands.
    """

    if action not in {"install", "update"}:
        return _error("configured setup completion needs an install or update action")
    subject_port = configured_setup_subject(effective, host)
    pending = {
        (item.coordinate.source, item.coordinate.artifact): item for item in completed.pending_setup
    }
    executions = {
        member.plan.repair.artifact: member for member in completed.action.execution.artifacts
    }
    items = []
    terminal = []
    plan = completed.action.prepared.flow.proposal.plan
    placeholder = sha256_bytes(b"unreviewed-consumer-action")
    for installed in completed.action.prepared.installations:
        exact = installed.coordinate
        member = executions.get(exact)
        changed = bool(
            member is not None and member.outcome is not None and member.outcome.primary.applied
        )
        succeeded = member is not None and member.status in {
            "completed",
            "completed-with-attention",
        }
        for profile in host.profiles:
            setup_request = SetupRequest(
                _unversioned(exact),
                profile,
                host.scope.value,
                platform=plan.platform,
            )
            subject = subject_port(setup_request)
            if isinstance(subject, Err):
                # A failed member has no standing receipt to resolve.  It must still be present in
                # usage reporting, but it cannot truthfully become a setup candidate.
                if succeeded:
                    return subject
                loaded = read_object(
                    ObjectReadRequest(
                        object_store_paths(host.data_root), installed.artifact.version.object_digest
                    )
                )
                if isinstance(loaded, Err) or loaded.value is None:
                    return subject
                package = compile_native_package(
                    loaded.value.candidate.entries,
                    expected_identity=exact.artifact,
                )
                if isinstance(package, Err):
                    return package
                key = f"{exact}#{profile}/{host.scope.value}"
                items.append(
                    ConsumerReviewItem(
                        key,
                        exact,
                        profile,
                        host.scope.value,
                        action,
                        "unavailable-after-failed-install",
                        TrustClass.REGISTRY_REVIEWED.value,
                        str(package.value.manifest_digest),
                        str(installed.artifact.version.payload_digest),
                        str(installed.artifact.version.object_digest),
                        "not-scanned",
                        "unknown",
                        (),
                        None,
                        plan.review_digest,
                        plan,
                    )
                )
                terminal.append(
                    ConsumerTerminalItem(
                        key,
                        "failed",
                        "" if member is None else member.detail,
                        "skipped" if package.value.manifest.setup is not None else "not-required",
                    )
                )
                continue
            declaration = pending.get((exact.source, exact.artifact))
            key = f"{exact}#{profile}/{host.scope.value}"
            review_item = ConsumerReviewItem(
                key,
                exact,
                profile,
                host.scope.value,
                action,
                subject.value.record.source.resolved_commit,
                subject.value.trust.value,
                str(subject.value.record.artifact.manifest_digest),
                str(subject.value.record.artifact.payload_digest),
                str(subject.value.record.artifact.object_digest),
                "not-scanned",
                "unknown",
                _absolute_effects(subject.value, host),
                None
                if declaration is None
                else ConsumerSetupDeclaration(declaration.recipe, declaration.platforms, ()),
                plan.review_digest,
                plan,
            )
            items.append(review_item)
            terminal.append(
                ConsumerTerminalItem(
                    key,
                    "changed" if changed else ("current" if succeeded else "failed"),
                    "" if member is None else member.detail,
                    "pending" if declaration is not None and succeeded else "not-required",
                )
            )
    try:
        consumer_request = ConsumerActionRequest(
            action,
            tuple(sorted({item.coordinate for item in items}, key=str)),
            tuple(sorted(set(item.profile for item in items))),
            host.scope.value,
            "copy",
            plan.platform,
        )
        review = ConsumerReview(consumer_request, tuple(items), placeholder)
        outcome = ConsumerOutcome(action, tuple(terminal))
        return Ok(
            (
                review,
                outcome,
                ConfiguredSetupService(effective, host, subject_port),
            )
        )
    except ValueError as error:
        return _error(f"configured completion cannot be projected for setup: {error}")


class _ConfiguredSetupContext:
    """Only the context attribute the shared reporting adapter reads."""

    def __init__(self, effective: EffectiveConfiguration) -> None:
        self.effective = effective


class ConfiguredSetupService:
    """The existing setup facade, composed with canonical receipt-backed ports."""

    def __init__(
        self,
        effective: EffectiveConfiguration,
        host: InstallationHost,
        subject_port: SetupSubjectPort | None = None,
    ) -> None:
        self.context = _ConfiguredSetupContext(effective)
        self._effective = effective
        self._host = host
        self._subject = subject_port or configured_setup_subject(effective, host)
        self._ports = LocalConfiguredSetupAdapter(host, self._subject)

    def setup_queue(
        self,
        review: ConsumerReview,
        outcome: ConsumerOutcome,
        *,
        authorize_untrusted_source: bool = False,
        authorize_custom_entrypoint: bool = False,
    ) -> ConsumerSetupQueue:
        terminal = {item.key: item for item in outcome.items}
        plans = []
        failures = []
        location = InstallLocation(
            self._host.project_root, self._host.user_home, self._host.data_root
        )
        store = object_store_paths(self._host.data_root)
        for item in review.items:
            result = terminal.get(item.key)
            if item.setup is None or result is None or result.setup_status != "pending":
                continue
            request = SetupRequest(
                _unversioned(item.coordinate),
                item.profile,
                item.scope,
                authorize_untrusted_source=authorize_untrusted_source,
                authorize_custom_entrypoint=authorize_custom_entrypoint,
                platform=review.request.platform,
            )
            attempt = prepare_setup_attempt(
                request,
                self._subject,
                self._effective,
                location,
                store,
                self._ports,
            )
            if isinstance(attempt.result, Err):
                failures.append(
                    ConsumerSetupFailure(
                        item.key, _detail(attempt.result.diagnostics), attempt.manual
                    )
                )
            else:
                plans.append(attempt.result.value)
        return ConsumerSetupQueue(tuple(plans), tuple(failures))

    def finalize_setup_queue(
        self,
        queue: ConsumerSetupQueue,
        *,
        consent: Consent,
        stop_on_failure: bool = False,
        runtime: SetupRuntime | None = None,
        on_item_start: Callable[[int, int, CanonicalSetupPlan], None] | None = None,
    ) -> SetupQueueOutcome:
        return execute_setup_queue(
            queue.plans,
            tuple(plan.review_digest for plan in queue.plans),
            self._subject,
            self._effective,
            self._ports,
            production_runtime() if runtime is None else runtime,
            consent=consent,
            stop_on_failure=stop_on_failure,
            on_item_start=on_item_start,
        )


def configured_installed_setup_completion(
    effective: EffectiveConfiguration,
    host: InstallationHost,
    coordinates: tuple[ArtifactCoordinate, ...],
    *,
    platform: str,
    authorize_untrusted_source: bool = False,
    authorize_custom_entrypoint: bool = False,
) -> Result[tuple[ConsumerReview, ConsumerOutcome, ConfiguredSetupService]]:
    """Project already-recorded canonical installs for the explicit setup command."""

    declared = read_declared_setup(
        coordinates,
        state_root=host.state_root,
        data_root=host.data_root,
    )
    if isinstance(declared, Err):
        return declared
    declarations = {
        (item.coordinate.source, item.coordinate.artifact): item for item in declared.value
    }
    subject_port = configured_setup_subject(effective, host)
    service = ConfiguredSetupService(effective, host, subject_port)
    location = InstallLocation(host.project_root, host.user_home, host.data_root)
    store = object_store_paths(host.data_root)
    items = []
    outcomes = []
    for exact in coordinates:
        declaration = declarations.get((exact.source, exact.artifact))
        if declaration is None:
            continue
        for profile in host.profiles:
            setup_request = SetupRequest(
                _unversioned(exact),
                profile,
                host.scope.value,
                authorize_untrusted_source=authorize_untrusted_source,
                authorize_custom_entrypoint=authorize_custom_entrypoint,
                platform=platform,
            )
            subject = subject_port(setup_request)
            if isinstance(subject, Err):
                return subject
            planned = prepare_setup_attempt(
                setup_request,
                subject_port,
                effective,
                location,
                store,
                service._ports,
            )
            if isinstance(planned.result, Err):
                return planned.result
            key = f"{exact}#{profile}/{host.scope.value}"
            items.append(
                ConsumerReviewItem(
                    key,
                    exact,
                    profile,
                    host.scope.value,
                    "install",
                    subject.value.record.source.resolved_commit,
                    subject.value.trust.value,
                    str(subject.value.record.artifact.manifest_digest),
                    str(subject.value.record.artifact.payload_digest),
                    str(subject.value.record.artifact.object_digest),
                    "not-scanned",
                    "unknown",
                    _absolute_effects(subject.value, host),
                    ConsumerSetupDeclaration(declaration.recipe, declaration.platforms, ()),
                    planned.result.value.review_digest,
                    planned.result.value,
                )
            )
            outcomes.append(ConsumerTerminalItem(key, "current", setup_status="pending"))
    if not items:
        return _error("selected configured installations declare no setup")
    try:
        request = ConsumerActionRequest(
            "install",
            tuple(sorted({item.coordinate for item in items}, key=str)),
            tuple(sorted(set(item.profile for item in items))),
            host.scope.value,
            "copy",
            platform,
        )
        review = ConsumerReview(
            request,
            tuple(items),
            sha256_bytes(b"unreviewed-consumer-action"),
        )
        return Ok((review, ConsumerOutcome("install", tuple(outcomes)), service))
    except ValueError as error:
        return _error(f"configured installations cannot be reviewed for setup: {error}")


def _owner_digests(index: ReferenceIndex, plan: CanonicalSetupPlan) -> tuple[ObjectDigest, ...]:
    return tuple(
        sorted(
            (
                reference.digest
                for reference in index.references
                if reference.kind is ReferenceKind.SETUP
                and reference.owner == plan.setup_reference_owner
            ),
            key=str,
        )
    )


def _replace_setup_reference(
    plan: CanonicalSetupPlan, digests: tuple[ObjectDigest, ...]
) -> Result[ReferenceIndex]:
    return replace_references(
        ReferenceUpdateRequest(
            plan.object_store_paths,
            ReferenceKind.SETUP,
            plan.setup_reference_owner,
            digests,
        ),
        ReferenceUpdatePorts(
            acquire_store_lock,
            release_store_lock,
            read_references,
            write_references,
        ),
    )


class LocalConfiguredSetupAdapter(LocalInstallAdapter):
    """Persist setup evidence on the canonical receipt as one compensated unit."""

    def __init__(self, host: InstallationHost, subject_port: SetupSubjectPort) -> None:
        if not isinstance(host, InstallationHost) or not callable(subject_port):
            raise ValueError("configured setup persistence needs its host and subject port")
        self._subject_port = subject_port
        self._receipts = LocalReceiptStore(host.state_root)

    def read_references(self, request: ReferenceReadRequest) -> Result[ReferenceIndex]:
        return read_references(request)

    def persist_setup(
        self,
        plan: CanonicalSetupPlan,
        record: SetupStateRecord,
        *,
        expected_record: SetupStateRecord | None,
    ) -> Result[None]:
        setup_before = None
        receipt_before = None
        wrote_setup = False
        wrote_receipt = False
        attempted_reference = False
        try:
            with _lock(Path(plan.installation_record_lock_path)):
                current = self._subject_port(plan.request)
                if not isinstance(current, Ok) or current.value.record != plan.installation:
                    return _error("installed payload changed before setup persistence")
                setup_before_result = self.inspect_path(plan.setup_state_path)
                receipt_before_result = self.inspect_path(plan.installation_record_path)
                references = self.read_references(ReferenceReadRequest(plan.object_store_paths))
                if (
                    not isinstance(setup_before_result, Ok)
                    or not isinstance(receipt_before_result, Ok)
                    or not isinstance(references, Ok)
                ):
                    return _error("setup persistence preconditions cannot be inspected")
                setup_before = setup_before_result.value
                receipt_before = receipt_before_result.value
                if expected_record is None:
                    state_matches = setup_before == plan.setup_state_precondition
                else:
                    try:
                        parsed = parse_setup_state(setup_before.content.decode("utf-8"))
                    except UnicodeDecodeError:
                        parsed = None
                    state_matches = (
                        setup_before.kind == "file"
                        and parsed is not None
                        and not isinstance(parsed, LegacyErr)
                        and parsed.value.records == (expected_record,)
                    )
                reference_matches = (
                    _owner_digests(references.value, plan) == plan.setup_reference_precondition
                )
                if not state_matches or not reference_matches:
                    return _error("setup state or object reference changed after Review")

                exact = ArtifactCoordinate(
                    plan.request.coordinate.source,
                    plan.request.coordinate.artifact,
                    str(plan.installation.artifact.version),
                )
                standing = self._receipts.record(exact)
                if (
                    not isinstance(standing, Ok)
                    or self._receipts.path_for(exact) != plan.installation_record_path
                ):
                    return _error("configured installation receipt is unavailable during setup")
                _write_atomic(
                    Path(plan.setup_state_path),
                    (dump_setup_state(SetupState((record,))) + "\n").encode("utf-8"),
                )
                wrote_setup = True
                written = self._receipts.record_installation(
                    exact,
                    replace(standing.value.receipt, setup_state_ref=plan.setup_state_ref),
                    ownership=standing.value.ownership,
                )
                if isinstance(written, Err):
                    raise OSError("cannot attach setup state to the configured receipt")
                wrote_receipt = True
                attempted_reference = True
                referenced = _replace_setup_reference(plan, (plan.object_digest,))
                if isinstance(referenced, Err):
                    raise OSError("cannot retain the configured setup object reference")
            return Ok(None)
        except (OSError, RuntimeError, ValueError) as error:
            rollback: list[str] = []
            if wrote_receipt and receipt_before is not None:
                try:
                    _restore(receipt_before)
                except OSError as rollback_error:
                    rollback.append(f"installation receipt: {rollback_error}")
            if wrote_setup and setup_before is not None:
                try:
                    _restore(setup_before)
                except OSError as rollback_error:
                    rollback.append(f"setup state: {rollback_error}")
            if attempted_reference:
                restored = _replace_setup_reference(plan, plan.setup_reference_precondition)
                if isinstance(restored, Err):
                    rollback.append("object reference: restore failed")
            detail = f"cannot persist canonical setup state: {error}"
            if rollback:
                detail += "; rollback incomplete: " + "; ".join(rollback)
            return _error(detail)


__all__ = [
    "CONFIGURED_SETUP_INVALID",
    "ConfiguredSetupService",
    "LocalConfiguredSetupAdapter",
    "configured_consumer_completion",
    "configured_installed_setup_completion",
    "configured_setup_subject",
]
