"""The adapters that carry out one repair step each, and nothing else.

An effect says what must become true, not how. `WriteFile` carries a digest rather than content so
a plan stays reviewable without embedding payloads in it, and `ConfigureHarness` names a harness
rather than a settings entry. The missing half is supplied when an interpreter is constructed: the
content it is allowed to write, the registration it is allowed to record, the artifact it is
allowed to touch. An interpreter asked for something it was not given refuses loudly instead of
improvising, because an installer that improvises is one that writes something nobody reviewed.

Storing a credential is the boundary case. The value has to be typed by a person -- CP-08 keeps it
out of this process entirely -- so a non-interactive executor cannot do it and says so, rather than
failing somewhere deeper with a message about a provider.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
from typing import Mapping

from agent_artifacts.domain.credentials import CredentialReference
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.effects import (
    ConfigureHarness,
    CopyTree,
    CreatePythonEnvironment,
    DeleteCredential,
    DeliverArtifact,
    DeliveryKind,
    Effect,
    InstallPythonDependencies,
    RemoveOwnedPath,
    ReplaceCredential,
    StoreCredential,
    UnconfigureHarness,
    VerifyCredential,
    WithdrawArtifact,
    WriteFile,
)
from agent_artifacts.domain.harness import McpRegistration
from agent_artifacts.domain.python_runtime import ArtifactEnvironment
from agent_artifacts.domain.receipts import ArtifactDelivery
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.io.credentials import CredentialProviderPort
from agent_artifacts.io.fs import write_atomic
from agent_artifacts.io.harness import LocalHarnessRegistry
from agent_artifacts.io.python_runtime import LocalPythonRuntime
from agent_artifacts.io.store_lock import acquire_store_lock, release_store_lock
from agent_artifacts.protocol.hashing import sha256_bytes
from agent_artifacts.store.model import StoreLockLease, StoreLockRequest

EXECUTION_REFUSED = DiagnosticCode("execution-refused")
EXECUTION_FAILED = DiagnosticCode("execution-failed")
EXECUTION_NEEDS_A_PERSON = DiagnosticCode("execution-needs-a-person")

__all__ = [
    "EXECUTION_FAILED",
    "EXECUTION_NEEDS_A_PERSON",
    "EXECUTION_REFUSED",
    "CredentialEffectInterpreter",
    "DeliveryEffectInterpreter",
    "FileEffectInterpreter",
    "HarnessEffectInterpreter",
    "LocalMutationLock",
    "RuntimeEffectInterpreter",
]


def _restrict(path: str) -> None:
    """Take away group and world access from what was just delivered, owner bits intact.

    The owner's bits are kept rather than a mode imposed, because a delivered hook script has to
    stay executable and a blanket 0o600 would leave the harness unable to run what it was given.
    """

    def own(target: str) -> None:
        os.chmod(target, os.stat(target).st_mode & 0o700)

    if not os.path.isdir(path):
        own(path)
        return
    for current, _directories, files in os.walk(path):
        for name in files:
            own(os.path.join(current, name))
        own(current)


def _make_tree_removable(path: str) -> None:
    """Restore owner access only inside one exact tree immediately before removal.

    Installed and delivered trees may intentionally be read-only. Recursive removal still needs
    owner write and search permission on each directory. Directory symlinks are never followed or
    changed: they remain leaves for ``shutil.rmtree``.
    """

    os.chmod(path, os.lstat(path).st_mode | stat.S_IRWXU)
    for current, directories, _files in os.walk(path, followlinks=False):
        for name in directories:
            child = os.path.join(current, name)
            if not os.path.islink(child):
                os.chmod(child, os.lstat(child).st_mode | stat.S_IRWXU)


def _error(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message),))


class LocalMutationLock:
    """A filesystem lease derived from one relevant installation scope.

    The scope key is hashed before it becomes a path, so project roots and profile names cannot
    escape the managed lock directory. Different scopes intentionally get different leases.
    """

    def __init__(
        self,
        state_root: str,
        scope_key: str,
        *,
        timeout_seconds: float = 30.0,
        stale_after_seconds: int = 300,
    ) -> None:
        if (
            not os.path.isabs(state_root)
            or not scope_key
            or any(character in scope_key for character in "\r\n")
        ):
            raise ValueError("mutation lock scope is invalid")
        digest = hashlib.sha256(scope_key.encode("utf-8")).hexdigest()
        self.lock_directory = os.path.join(
            os.path.normpath(state_root), "locks", "mutations", f"{digest}.lock"
        )
        self.request = StoreLockRequest(
            self.lock_directory,
            timeout_seconds=timeout_seconds,
            stale_after_seconds=stale_after_seconds,
        )

    def acquire(self) -> Result[str]:
        acquired = acquire_store_lock(self.request)
        if isinstance(acquired, Err):
            return acquired
        return Ok(acquired.value.token)

    def release(self, token: str) -> Result[None]:
        return release_store_lock(StoreLockLease(self.lock_directory, token))


class FileEffectInterpreter:
    """Writes files and copies trees, only inside the artifact that owns them.

    `contents` maps a canonical digest to the bytes it names. A `WriteFile` whose digest is not in
    it is refused: the effect proves what should be written, and this is where that proof is
    checked against something real rather than trusted.
    """

    def __init__(
        self,
        environment: ArtifactEnvironment,
        contents: Mapping[str, bytes] | None = None,
    ) -> None:
        if not isinstance(environment, ArtifactEnvironment):
            raise ValueError("a file interpreter belongs to one artifact environment")
        self.environment = environment
        self.contents = dict(contents or {})

    def offer(self, content: bytes) -> str:
        """Register content this interpreter may write, keyed by its own digest."""

        digest = str(sha256_bytes(content))
        self.contents[digest] = content
        return digest

    def supports(self, effect: Effect) -> bool:
        """Whether this interpreter may carry out `effect`, not merely recognize its kind.

        One Selection is one transaction, so a bulk install hands the executor one tuple of
        interpreters holding one of these per artifact. Dispatch takes the first that says yes. If
        that answer ignored ownership, the first file interpreter would claim every write in the
        transaction, including the other artifact's, and then refuse them for being outside the
        environment it owns -- failing closed on an effect that was perfectly legitimate and had an
        owner sitting later in the same tuple.
        """

        return isinstance(effect, (WriteFile, CopyTree, RemoveOwnedPath)) and self.environment.owns(
            effect.destination
        )

    def apply(self, effect: Effect) -> Result[str]:
        if isinstance(effect, WriteFile):
            return self._write(effect)
        if isinstance(effect, CopyTree):
            return self._copy(effect)
        if isinstance(effect, RemoveOwnedPath):
            return self._remove(effect)
        return _error(EXECUTION_REFUSED, f"{type(effect).__name__} is not a file effect")

    def _write(self, effect: WriteFile) -> Result[str]:
        if not self.environment.owns(effect.destination):
            return _error(
                EXECUTION_REFUSED,
                f"{effect.destination} is outside {self.environment.artifact}",
            )
        content = self.contents.get(effect.content_digest)
        if content is None:
            return _error(
                EXECUTION_REFUSED,
                f"nothing here holds the content {effect.content_digest} names, so writing "
                f"{effect.destination} would write something nobody planned",
            )
        try:
            write_atomic(effect.destination, content)
            os.chmod(effect.destination, 0o700 if effect.executable else 0o600)
        except OSError as error:
            return _error(EXECUTION_FAILED, f"cannot write {effect.destination}: {error.strerror}")
        return Ok(f"wrote {len(content)} bytes to {effect.destination}")

    def _copy(self, effect: CopyTree) -> Result[str]:
        if not self.environment.owns(effect.destination):
            return _error(
                EXECUTION_REFUSED,
                f"{effect.destination} is outside {self.environment.artifact}",
            )
        if not os.path.isdir(effect.source):
            return _error(EXECUTION_FAILED, f"{effect.source} is not a directory to copy")
        try:
            shutil.copytree(effect.source, effect.destination, dirs_exist_ok=True)
        except OSError as error:
            return _error(
                EXECUTION_FAILED, f"cannot copy into {effect.destination}: {error.strerror}"
            )
        return Ok(f"copied {effect.source} into {effect.destination}")

    def _remove(self, effect: RemoveOwnedPath) -> Result[str]:
        if not self.environment.owns(effect.destination):
            return _error(
                EXECUTION_REFUSED,
                f"{effect.destination} is outside {self.environment.artifact}",
            )
        if not os.path.lexists(effect.destination):
            return Ok(f"{effect.destination} was already absent")
        try:
            if (
                effect.recursive
                and os.path.isdir(effect.destination)
                and not os.path.islink(effect.destination)
            ):
                _make_tree_removable(effect.destination)
                shutil.rmtree(effect.destination)
            elif os.path.isdir(effect.destination) and not os.path.islink(effect.destination):
                os.rmdir(effect.destination)
            else:
                os.unlink(effect.destination)
        except OSError as error:
            return _error(
                EXECUTION_FAILED,
                f"cannot remove {effect.destination}: {error.strerror or error}",
            )
        return Ok(f"removed {effect.destination}")


class RuntimeEffectInterpreter:
    """Creates artifact-owned environments and installs into them, via the CP-09 interpreter."""

    def __init__(self, runtime: LocalPythonRuntime) -> None:
        if not isinstance(runtime, LocalPythonRuntime):
            raise ValueError("a runtime interpreter wraps a local Python runtime")
        self.runtime = runtime

    def supports(self, effect: Effect) -> bool:
        """Whether this interpreter owns the environment `effect` names (see the file effects)."""

        if isinstance(effect, CreatePythonEnvironment):
            return self.runtime.environment.owns(effect.destination)
        if isinstance(effect, InstallPythonDependencies):
            return self.runtime.environment.owns(effect.environment)
        return False

    def apply(self, effect: Effect) -> Result[str]:
        if isinstance(effect, CreatePythonEnvironment):
            created = self.runtime.create_environment(effect)
            if isinstance(created, Err):
                return created
            return Ok(f"created {effect.destination}")
        if isinstance(effect, InstallPythonDependencies):
            installed = self.runtime.install_dependencies(effect)
            if isinstance(installed, Err):
                return installed
            return Ok(f"installed {effect.descriptor} with {effect.installer}")
        return _error(EXECUTION_REFUSED, f"{type(effect).__name__} is not a runtime effect")


class HarnessEffectInterpreter:
    """Records one artifact with the harnesses it was registered against.

    The registrations are supplied here rather than read off the effect, because `ConfigureHarness`
    names a harness and this is what tells it which server, at which command.

    `artifact` is which artifact those registrations belong to, and it is required. A
    `ConfigureHarness` names the artifact and never the server, so with two artifacts registering
    with the same harness there is nothing else that separates their steps: without it this
    interpreter would answer for the other artifact's step and write its own server under it.
    """

    def __init__(
        self,
        registry: LocalHarnessRegistry,
        registrations: tuple[McpRegistration, ...] = (),
        *,
        artifact: str,
    ) -> None:
        if not isinstance(registry, LocalHarnessRegistry):
            raise ValueError("a harness interpreter needs a registry")
        if (
            not isinstance(artifact, str)
            or not artifact.strip()
            or any(character in artifact for character in "\r\n")
        ):
            raise ValueError("a harness interpreter registers one named artifact")
        self.registry = registry
        self.registrations = tuple(registrations)
        self.artifact = artifact

    def _matching(self, effect: Effect) -> tuple[McpRegistration, ...]:
        if not isinstance(effect, (ConfigureHarness, UnconfigureHarness)):
            return ()
        if isinstance(effect, ConfigureHarness) and effect.artifact != self.artifact:
            return ()
        return tuple(
            registration
            for registration in self.registrations
            if registration.target.harness == effect.harness
            and (
                isinstance(effect, ConfigureHarness)
                or (
                    registration.server == effect.server
                    and registration.target.settings_file == effect.destination
                )
            )
        )

    def supports(self, effect: Effect) -> bool:
        """Whether this interpreter holds the registration `effect` needs, not merely its kind.

        A bulk install puts one of these per artifact in the executor's tuple, and dispatch takes
        the first that says yes. Answering on the effect's type alone would let the first one claim
        every harness effect in the transaction: the ones it has no registration for it would then
        refuse, and the ones for another artifact at the same harness it would carry out wrongly.
        """

        return bool(self._matching(effect))

    def apply(self, effect: Effect) -> Result[str]:
        if not isinstance(effect, (ConfigureHarness, UnconfigureHarness)):
            return _error(EXECUTION_REFUSED, f"{type(effect).__name__} is not a harness effect")
        if isinstance(effect, ConfigureHarness) and effect.artifact != self.artifact:
            return _error(
                EXECUTION_REFUSED,
                f"this interpreter registers {self.artifact}, not {effect.artifact}",
            )
        matching = self._matching(effect)
        if not matching:
            return _error(
                EXECUTION_REFUSED,
                f"nothing here says what to register with {effect.harness}",
            )
        recorded = []
        for registration in matching:
            result = (
                self.registry.register(registration)
                if isinstance(effect, ConfigureHarness)
                else self.registry.unregister(registration.target, registration.server)
            )
            if isinstance(result, Err):
                return result
            verb = "registered" if isinstance(effect, ConfigureHarness) else "unregistered"
            recorded.append(f"{verb} {registration.server} -> {result.value.path}")
        return Ok("; ".join(recorded))


class DeliveryEffectInterpreter:
    """Puts one artifact where a harness reads it, and takes back only what it put there.

    This is the one interpreter that writes outside AART's own tree, so it cannot prove ownership
    structurally the way `FileEffectInterpreter` does -- the destination belongs to the harness.
    It proves it the way the harness interpreter does instead: it is handed the deliveries it may
    make, and a delivery it was not given is refused rather than carried out. With two artifacts
    delivering to the same harness that is the only thing separating their steps.

    Delivering replaces the destination rather than merging into it, so a file the previous version
    shipped and this one dropped does not linger where the harness would still read it. That is
    safe because CP-12 compares the desired state against a real inspection before the first effect
    runs: a destination already occupied by something this installation did not put there is a
    conflict the review reports, not a surprise the executor discovers.
    """

    def __init__(self, artifact: str, deliveries: tuple[ArtifactDelivery, ...]) -> None:
        if (
            not isinstance(artifact, str)
            or not artifact.strip()
            or any(character in artifact for character in "\r\n")
        ):
            raise ValueError("a delivery interpreter delivers one named artifact")
        deliveries = tuple(deliveries)
        if not deliveries or any(
            not isinstance(delivery, ArtifactDelivery) for delivery in deliveries
        ):
            raise ValueError("a delivery interpreter needs the deliveries it may make")
        self.artifact = artifact
        self.deliveries = deliveries

    def _matching(self, effect: Effect) -> ArtifactDelivery | None:
        if not isinstance(effect, (DeliverArtifact, WithdrawArtifact)):
            return None
        if effect.artifact != self.artifact:
            return None
        for delivery in self.deliveries:
            if delivery.harness == effect.harness and delivery.destination == effect.destination:
                return delivery
        return None

    def supports(self, effect: Effect) -> bool:
        """Whether this interpreter holds the delivery `effect` names, not merely its kind."""

        return self._matching(effect) is not None

    def apply(self, effect: Effect) -> Result[str]:
        if not isinstance(effect, (DeliverArtifact, WithdrawArtifact)):
            return _error(EXECUTION_REFUSED, f"{type(effect).__name__} is not a delivery effect")
        if effect.artifact != self.artifact:
            return _error(
                EXECUTION_REFUSED,
                f"this interpreter delivers {self.artifact}, not {effect.artifact}",
            )
        if self._matching(effect) is None:
            return _error(
                EXECUTION_REFUSED,
                f"nothing here says {self.artifact} is delivered to {effect.destination}",
            )
        if isinstance(effect, DeliverArtifact):
            return self._deliver(effect)
        return self._withdraw(effect)

    def _deliver(self, effect: DeliverArtifact) -> Result[str]:
        tree = effect.delivery is DeliveryKind.TREE
        present = os.path.isdir(effect.source) if tree else os.path.isfile(effect.source)
        if not present:
            shape = "directory" if tree else "file"
            return _error(
                EXECUTION_FAILED,
                f"{effect.source} is not a {shape} to deliver, so {effect.destination} is "
                f"left as it was",
            )
        removed = self._remove(effect.destination)
        if isinstance(removed, Err):
            return removed
        try:
            os.makedirs(os.path.dirname(effect.destination) or "/", exist_ok=True)
            if tree:
                shutil.copytree(effect.source, effect.destination)
            else:
                with open(effect.source, "rb") as handle:
                    write_atomic(effect.destination, handle.read())
                shutil.copymode(effect.source, effect.destination)
            _restrict(effect.destination)
        except OSError as error:
            return _error(
                EXECUTION_FAILED,
                f"cannot deliver to {effect.destination}: {error.strerror or error}",
            )
        return Ok(f"delivered {self.artifact} to {effect.harness} at {effect.destination}")

    def _withdraw(self, effect: WithdrawArtifact) -> Result[str]:
        if not os.path.lexists(effect.destination):
            return Ok(f"{effect.destination} was already absent")
        removed = self._remove(effect.destination)
        if isinstance(removed, Err):
            return removed
        return Ok(f"withdrew {self.artifact} from {effect.harness} at {effect.destination}")

    def _remove(self, destination: str) -> Result[None]:
        if not os.path.lexists(destination):
            return Ok(None)
        try:
            if os.path.isdir(destination) and not os.path.islink(destination):
                _make_tree_removable(destination)
                shutil.rmtree(destination)
            else:
                os.unlink(destination)
        except OSError as error:
            return _error(
                EXECUTION_FAILED, f"cannot remove {destination}: {error.strerror or error}"
            )
        return Ok(None)


class CredentialEffectInterpreter:
    """Verifies and removes credentials, and says plainly when a person has to be present.

    Storing or replacing a value needs somebody to type it. CP-08 keeps the value out of this
    process on purpose -- `MacOsKeychainProvider.store` delegates to the provider's own prompt --
    so there is no unattended path to offer and none is invented here. The honest report is that
    the repair is waiting for a person, not that a provider failed.

    References are supplied at construction, like the harness registrations are, so an effect that
    names a credential this executor was not given is refused rather than resolved by guesswork.
    """

    def __init__(
        self,
        provider: CredentialProviderPort,
        references: tuple[CredentialReference, ...] = (),
    ) -> None:
        self.provider = provider
        self.references = tuple(references)

    def supports(self, effect: Effect) -> bool:
        """Whether this interpreter was given the reference `effect` names (see the harness one)."""

        return (
            isinstance(
                effect, (StoreCredential, ReplaceCredential, DeleteCredential, VerifyCredential)
            )
            and self._reference(effect.reference) is not None
        )

    def _reference(self, raw: str) -> CredentialReference | None:
        return next((candidate for candidate in self.references if str(candidate) == raw), None)

    def apply(self, effect: Effect) -> Result[str]:
        if isinstance(effect, (StoreCredential, ReplaceCredential)):
            return _error(
                EXECUTION_NEEDS_A_PERSON,
                f"{effect.reference} has to be entered by someone through the credential flow; "
                "this repair cannot run unattended",
            )
        if not isinstance(effect, (DeleteCredential, VerifyCredential)):
            return _error(EXECUTION_REFUSED, f"{type(effect).__name__} is not a credential effect")
        reference = self._reference(effect.reference)
        if reference is None:
            return _error(
                EXECUTION_REFUSED,
                f"nothing here knows the credential reference {effect.reference}",
            )
        if isinstance(effect, VerifyCredential):
            observed = self.provider.inspect(reference)
            if isinstance(observed, Err):
                return observed
            return Ok(f"{effect.reference} is {observed.value.state.value}")
        removed = self.provider.delete(reference)
        if isinstance(removed, Err):
            return removed
        return Ok(f"removed {effect.reference}")
