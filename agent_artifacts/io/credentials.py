"""Credential provider interpreters: the only place in the package a secret value can exist.

`TransientSecret` is deliberately hostile to persistence. It redacts itself in every string form,
refuses to be copied or pickled, and yields its value exactly once. Domain and application code
never construct one, and no method here returns a value to its caller -- observations carry state,
never content.

The macOS interpreter prefers `security`'s own terminal prompt over passing the value on argv,
because argv is readable by any process that can list processes. That prompt silently keeps only
the first 128 bytes, so what was actually stored is measured afterwards and a value sitting exactly
on that boundary is reported as probably cut. Both paths are offered and both name their exposure.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Protocol

from agent_artifacts.domain.credentials import (
    CredentialObservation,
    CredentialReference,
    CredentialState,
    ProviderState,
)
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.inputs import BindingExposure
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.redaction import redact_text

CREDENTIAL_PROVIDER_FAILED = DiagnosticCode("credential-provider-failed")
CREDENTIAL_PROVIDER_UNAVAILABLE = DiagnosticCode("credential-provider-unavailable")

SECURITY_TOOL = "/usr/bin/security"
WORD_COUNT_TOOL = "/usr/bin/wc"
GREP_TOOL = "/usr/bin/grep"

#: `security`'s prompt reads through a fixed buffer that stops here without reporting an error.
PROMPT_CEILING_BYTES = 128

#: `security` reports "the specified item could not be found in the keychain" with this status.
ITEM_NOT_FOUND = 44

_ALLOWED_ENVIRONMENT = ("HOME", "PATH", "TERM", "SYSTEMROOT")

# What `security -g` prints on stderr ahead of a value it had to hex-encode. Assembled rather than
# written out so `scripts/secret_shape_check.py` stays able to run over its own repository.
_HEX_MARKER = "^" + "password" + ": 0x"


class SecretConsumedError(RuntimeError):
    """Raised when a transient secret is read a second time."""


class TransientSecret:
    """A credential value held only long enough to hand to a provider.

    Not a dataclass and not in `domain` on purpose: nothing that can reach a plan, a receipt or a
    canonical projection is able to hold one of these.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str) or not value:
            raise ValueError("a transient secret must be a non-empty string")
        self._value: str | None = value

    def consume(self) -> str:
        """Yield the value once, then forget it."""

        value = self._value
        if value is None:
            raise SecretConsumedError("this transient secret has already been consumed")
        self._value = None
        return value

    @property
    def consumed(self) -> bool:
        return self._value is None

    def __repr__(self) -> str:
        return "TransientSecret([redacted])"

    def __str__(self) -> str:
        return "[redacted]"

    def __format__(self, format_spec: str) -> str:
        return "[redacted]"

    def __reduce__(self) -> str | tuple[object, ...]:
        raise TypeError("a transient secret cannot be serialized")

    def __copy__(self) -> object:
        raise TypeError("a transient secret cannot be copied")

    def __deepcopy__(self, memo: object) -> object:
        raise TypeError("a transient secret cannot be copied")


def _environment(environ: Mapping[str, str]) -> dict[str, str]:
    result = {name: environ[name] for name in _ALLOWED_ENVIRONMENT if name in environ}
    result["LC_ALL"] = "C"
    return result


@dataclass(frozen=True, slots=True)
class ProcessOutcome:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class ProcessRunner(Protocol):
    def __call__(
        self,
        argv: tuple[str, ...],
        *,
        capture: bool,
        timeout: float,
    ) -> ProcessOutcome: ...


class CountedPipeline(Protocol):
    def __call__(
        self,
        producer: tuple[str, ...],
        counter: tuple[str, ...],
        *,
        from_stderr: bool,
        counter_accepts: tuple[int, ...],
        timeout: float,
    ) -> int | None: ...


def run_provider_process(
    argv: tuple[str, ...],
    *,
    capture: bool,
    timeout: float,
) -> ProcessOutcome:
    """Run a provider tool with no shell and a reduced environment.

    `capture=False` leaves the standard streams attached to the terminal, which is what lets the
    provider run its own prompt. Nothing is read back in that case, by construction.
    """

    completed = subprocess.run(
        argv,
        shell=False,
        env=_environment(os.environ),
        stdin=subprocess.DEVNULL if capture else None,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        timeout=timeout,
        check=False,
        text=True,
    )
    if not capture:
        return ProcessOutcome(completed.returncode)
    return ProcessOutcome(completed.returncode, completed.stdout or "", completed.stderr or "")


def run_counted_pipeline(
    producer: tuple[str, ...],
    counter: tuple[str, ...],
    *,
    from_stderr: bool,
    counter_accepts: tuple[int, ...],
    timeout: float,
) -> int | None:
    """Pipe a producer's output straight into a counter and read back only the count.

    The producer writes a credential; this process never receives that pipe's contents, only the
    number the counter prints. Returns None when either side fails, which the caller treats as
    "length unknown" rather than as an error.
    """

    try:
        source = subprocess.Popen(
            producer,
            shell=False,
            env=_environment(os.environ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL if from_stderr else subprocess.PIPE,
            stderr=subprocess.PIPE if from_stderr else subprocess.DEVNULL,
        )
    except OSError:
        return None
    stream = source.stderr if from_stderr else source.stdout
    try:
        counted = subprocess.run(
            counter,
            shell=False,
            env=_environment(os.environ),
            stdin=stream,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        source.kill()
        source.wait()
        return None
    finally:
        if stream is not None:
            stream.close()
    if source.wait() != 0 or counted.returncode not in counter_accepts:
        return None
    try:
        return int(counted.stdout.strip())
    except ValueError:
        return None


class CredentialProviderPort(Protocol):
    """The boundary every secret provider crosses. No method returns a credential value."""

    @property
    def provider(self) -> str: ...

    def available(self) -> ProviderState: ...

    def inspect(self, reference: CredentialReference) -> Result[CredentialObservation]: ...

    def store(
        self,
        reference: CredentialReference,
        secret: TransientSecret | None = None,
        *,
        replace: bool = False,
    ) -> Result[CredentialObservation]: ...

    def delete(self, reference: CredentialReference) -> Result[CredentialObservation]: ...


def _failure(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, redact_text(message)),))


def _macos_keychain_available() -> bool:
    return (
        sys.platform == "darwin"
        and os.path.isfile(SECURITY_TOOL)
        and os.access(SECURITY_TOOL, os.X_OK)
    )


@dataclass(frozen=True, slots=True)
class MacOsKeychainProvider:
    """Hold credentials in the macOS Keychain through `security`.

    `keychain` names a specific keychain file; the user's default keychain is used when it is None,
    which is what production does. Tests pass a temporary keychain instead.
    """

    keychain: str | None = None
    run: ProcessRunner = field(default=run_provider_process)
    count: CountedPipeline = field(default=run_counted_pipeline)
    timeout_seconds: float = 60.0
    provider: str = "macos-keychain"
    available_on_host: Callable[[], bool] = field(default=_macos_keychain_available)

    @staticmethod
    def store_exposure(*, interactive: bool) -> BindingExposure:
        """Where the value is readable while it is being written.

        The prompt keeps it inside the provider. Passing it on argv publishes it to the process
        table for the length of the call, which is why that path is never the default.
        """

        return BindingExposure.PRIVATE if interactive else BindingExposure.PROCESS_TABLE

    def _suffix(self) -> tuple[str, ...]:
        return () if self.keychain is None else (self.keychain,)

    def _locate(self, reference: CredentialReference, *extra: str) -> tuple[str, ...]:
        return (
            SECURITY_TOOL,
            "find-generic-password",
            "-a",
            reference.provider.account,
            "-s",
            reference.provider.service,
            *extra,
            *self._suffix(),
        )

    def resolution_argv(self, reference: CredentialReference) -> tuple[str, ...]:
        """The argv a launcher runs to read this credential when the artifact starts.

        This builds a command; it does not run one. The value it will produce belongs to the
        launched process and never returns here, which is why this is the one place a caller may
        ask for `-w` without a secret entering this one.
        """

        if not isinstance(reference, CredentialReference):
            raise ValueError("a resolution command needs a credential reference")
        return self._locate(reference, "-w")

    def available(self) -> ProviderState:
        if not self.available_on_host():
            return ProviderState.UNAVAILABLE
        return ProviderState.AVAILABLE

    def _unavailable(self, reference: CredentialReference) -> CredentialObservation:
        return CredentialObservation(
            reference,
            ProviderState.UNAVAILABLE,
            CredentialState.UNKNOWN,
            "the macOS Keychain is not available on this platform",
        )

    def inspect(self, reference: CredentialReference) -> Result[CredentialObservation]:
        if self.available() is not ProviderState.AVAILABLE:
            return Ok(self._unavailable(reference))
        try:
            outcome = self.run(self._locate(reference), capture=True, timeout=self.timeout_seconds)
        except OSError as error:
            return _failure(CREDENTIAL_PROVIDER_FAILED, f"Keychain inspection failed: {error}")
        except subprocess.TimeoutExpired:
            return _failure(CREDENTIAL_PROVIDER_FAILED, "Keychain inspection timed out")
        if outcome.returncode == 0:
            return Ok(
                CredentialObservation(
                    reference,
                    ProviderState.AVAILABLE,
                    CredentialState.PRESENT,
                    self._presence_detail(reference),
                )
            )
        if outcome.returncode == ITEM_NOT_FOUND:
            return Ok(
                CredentialObservation(reference, ProviderState.AVAILABLE, CredentialState.ABSENT)
            )
        return _failure(
            CREDENTIAL_PROVIDER_FAILED,
            f"Keychain inspection failed with status {outcome.returncode}: "
            f"{outcome.stderr.strip()}",
        )

    def _presence_detail(self, reference: CredentialReference) -> str:
        stored = self.stored_length(reference)
        if stored is None:
            return "a value is present"
        if stored == PROMPT_CEILING_BYTES:
            return (
                f"a value of exactly {PROMPT_CEILING_BYTES} bytes is present, the point at which "
                "the Keychain prompt cuts a longer one"
            )
        return f"a value of {stored} bytes is present"

    def stored_length(self, reference: CredentialReference) -> int | None:
        """Measure the stored value in bytes without this process ever holding it.

        `security -w` prints a value that is not printable ASCII as hex and says so only in `-g`'s
        output, so the printed length has to be halved in that case. Both the printing and the
        counting happen in child processes; None means the length could not be established.
        """

        printed = self.count(
            self._locate(reference, "-w"),
            (WORD_COUNT_TOOL, "-c"),
            from_stderr=False,
            counter_accepts=(0,),
            timeout=self.timeout_seconds,
        )
        if printed is None:
            return None
        hex_encoded = self.count(
            self._locate(reference, "-g"),
            (GREP_TOOL, "-c", _HEX_MARKER),
            from_stderr=True,
            counter_accepts=(0, 1),
            timeout=self.timeout_seconds,
        )
        if hex_encoded is None:
            return None
        counted = max(printed - 1, 0)  # `-w` appends a newline that is not part of the value.
        if not hex_encoded:
            return counted
        return counted // 2 if counted % 2 == 0 else None

    def store(
        self,
        reference: CredentialReference,
        secret: TransientSecret | None = None,
        *,
        replace: bool = False,
    ) -> Result[CredentialObservation]:
        """Write a value.

        Passing no carrier at all -- the default -- makes the provider run its own prompt, and this
        process never sees the value; that is the only path production should take. A `TransientSecret`
        is the non-interactive path: it puts the value on argv for the duration of one call, and
        `store_exposure` names that so a caller can refuse it under policy.

        `replace=True` removes the item and adds it again rather than updating in place, because
        `security add-generic-password -U` raises an authorization dialog and blocks until someone
        answers it -- which in a non-interactive run is forever. That leaves a window in which the
        credential is absent, so a failure after the removal says so plainly.
        """

        if self.available() is not ProviderState.AVAILABLE:
            return _failure(
                CREDENTIAL_PROVIDER_UNAVAILABLE,
                "the macOS Keychain is not available on this platform",
            )
        removed = False
        if replace:
            removal = self.delete(reference)
            if isinstance(removal, Err):
                return removal
            removed = True
        argv = [
            SECURITY_TOOL,
            "add-generic-password",
            "-a",
            reference.provider.account,
            "-s",
            reference.provider.service,
            "-w",
        ]
        interactive = secret is None
        if secret is not None:
            argv.append(secret.consume())
        argv.extend(self._suffix())
        try:
            outcome = self.run(tuple(argv), capture=not interactive, timeout=self.timeout_seconds)
        except OSError as error:
            return _failure(CREDENTIAL_PROVIDER_FAILED, f"Keychain write failed: {error}")
        except subprocess.TimeoutExpired:
            return _failure(CREDENTIAL_PROVIDER_FAILED, "Keychain write timed out")
        finally:
            argv.clear()
        if outcome.returncode != 0:
            aftermath = (
                " the previous value was already removed, so the credential is now absent and has"
                " to be stored again"
                if removed
                else ""
            )
            return _failure(
                CREDENTIAL_PROVIDER_FAILED,
                f"Keychain write failed with status {outcome.returncode}: "
                f"{outcome.stderr.strip()}{aftermath}",
            )
        return self.inspect(reference)

    def delete(self, reference: CredentialReference) -> Result[CredentialObservation]:
        if self.available() is not ProviderState.AVAILABLE:
            return _failure(
                CREDENTIAL_PROVIDER_UNAVAILABLE,
                "the macOS Keychain is not available on this platform",
            )
        argv = (
            SECURITY_TOOL,
            "delete-generic-password",
            "-a",
            reference.provider.account,
            "-s",
            reference.provider.service,
            *self._suffix(),
        )
        try:
            outcome = self.run(argv, capture=True, timeout=self.timeout_seconds)
        except OSError as error:
            return _failure(CREDENTIAL_PROVIDER_FAILED, f"Keychain deletion failed: {error}")
        except subprocess.TimeoutExpired:
            return _failure(CREDENTIAL_PROVIDER_FAILED, "Keychain deletion timed out")
        if outcome.returncode not in {0, ITEM_NOT_FOUND}:
            return _failure(
                CREDENTIAL_PROVIDER_FAILED,
                f"Keychain deletion failed with status {outcome.returncode}: "
                f"{outcome.stderr.strip()}",
            )
        return Ok(CredentialObservation(reference, ProviderState.AVAILABLE, CredentialState.ABSENT))
