"""The runtime input algebra: what an executable needs, and how it accepts it.

Three axes stay separate here on purpose. `SecretInput` and `ConfigInput` differ in lifecycle and
persistence; `ProcessBinding` says only how the process receives a value; `InputValueSource` says
only where the value comes from. A `SecretInput` can therefore be delivered on stdin, in a file, in
the environment or on the command line without any of those choices implying where it is stored —
and no combination of them produces a domain value holding the secret itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum
from typing import TypeAlias

from agent_artifacts.redaction import contains_credential_shape

from .credentials import CredentialProviderRef, CredentialReference, credential_provider_to_data
from .identifiers import InputId

__all__ = [
    "BindingExposure",
    "BoundInput",
    "BoundInputs",
    "CliArgumentBinding",
    "ConfigInput",
    "EnvironmentBinding",
    "FileBinding",
    "InputGuidance",
    "InputId",
    "InputValidation",
    "InputValueSource",
    "ObtainFrom",
    "PersistedConfigValue",
    "PolicyProvidedValue",
    "ProcessBinding",
    "PromptedConfigValue",
    "RuntimeInput",
    "SecretInput",
    "SecretProviderReference",
    "StdinBinding",
    "binding_kind",
    "bound_inputs_to_data",
    "input_to_data",
    "validate_config_value",
]

_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_ARGUMENT_RE = re.compile(r"^--[a-z0-9]+(?:-[a-z0-9]+)*$")
# Characters a host allow-list must never have to interpret: a backslash or a quote is how a
# lenient parser is talked into reading the authority as something else. DEL joins the control
# characters, which the `<= " "` test covers.
_REFUSED_CHARACTERS = frozenset('\\"<>^`{|}\x7f')
_HOST_CHARACTERS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-.")
_VALIDATION_KINDS = ("identifier", "pattern", "url")


def _line(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character in value for character in "\r\n")
    ):
        raise ValueError(f"{label} must be one safe non-empty line")
    return value


def _safe(value: str, label: str) -> str:
    # Registry guidance is reviewed metadata, but a reviewer is not a scanner: refuse anything
    # credential-shaped so approved help can never carry a usable value (INV-161).
    if contains_credential_shape(value):
        raise ValueError(f"{label} must not contain a credential shape")
    return value


def _input_id(value: object, label: str) -> InputId:
    if not isinstance(value, InputId) or _ID_RE.fullmatch(value.value) is None:
        raise ValueError(f"{label} must be a canonical input id")
    return value


class BindingExposure(IntEnum):
    """How widely the delivered value is observable once the process is running.

    Ordering is the point: a stricter policy caps this, and a plan can say why a binding is
    weaker without the domain having to guess at platform specifics.
    """

    PRIVATE = 0
    OWNED_FILE = 10
    INHERITED_ENVIRONMENT = 20
    PROCESS_TABLE = 30


@dataclass(frozen=True, slots=True)
class CliArgumentBinding:
    """Weakest binding: argv is observable through process inspection on many systems."""

    argument: str
    exposure: BindingExposure = BindingExposure.PROCESS_TABLE

    def __post_init__(self) -> None:
        if _ARGUMENT_RE.fullmatch(_line(self.argument, "cli argument")) is None:
            raise ValueError("cli argument must be a long option")
        if self.exposure is not BindingExposure.PROCESS_TABLE:
            raise ValueError("cli argument exposure is fixed")


@dataclass(frozen=True, slots=True)
class EnvironmentBinding:
    variable: str
    exposure: BindingExposure = BindingExposure.INHERITED_ENVIRONMENT

    def __post_init__(self) -> None:
        if _ENV_RE.fullmatch(_line(self.variable, "environment variable")) is None:
            raise ValueError("environment variable must be a canonical upper-case name")
        if self.exposure is not BindingExposure.INHERITED_ENVIRONMENT:
            raise ValueError("environment exposure is fixed")


@dataclass(frozen=True, slots=True)
class FileBinding:
    path: str
    exposure: BindingExposure = BindingExposure.OWNED_FILE

    def __post_init__(self) -> None:
        _line(self.path, "file binding path")
        if self.exposure is not BindingExposure.OWNED_FILE:
            raise ValueError("file exposure is fixed")


@dataclass(frozen=True, slots=True)
class StdinBinding:
    exposure: BindingExposure = BindingExposure.PRIVATE

    def __post_init__(self) -> None:
        if self.exposure is not BindingExposure.PRIVATE:
            raise ValueError("stdin exposure is fixed")


ProcessBinding: TypeAlias = CliArgumentBinding | EnvironmentBinding | FileBinding | StdinBinding


def binding_kind(binding: ProcessBinding) -> str:
    if isinstance(binding, CliArgumentBinding):
        return "cli-argument"
    if isinstance(binding, EnvironmentBinding):
        return "environment"
    if isinstance(binding, FileBinding):
        return "file"
    return "stdin"


@dataclass(frozen=True, slots=True)
class ObtainFrom:
    label: str
    url: str

    def __post_init__(self) -> None:
        _safe(_line(self.label, "obtain-from label"), "obtain-from label")
        _safe(_line(self.url, "obtain-from url"), "obtain-from url")
        if _url_host(self.url) is None:
            raise ValueError("obtain-from url must be a plain http or https url")


@dataclass(frozen=True, slots=True)
class InputGuidance:
    """Human-facing help. It explains an input; it never decides how one is delivered."""

    label: str
    description: str = ""
    example: str | None = None
    format_hint: str | None = None
    obtain_from: ObtainFrom | None = None
    validation_hint: str = ""

    def __post_init__(self) -> None:
        _safe(_line(self.label, "guidance label"), "guidance label")
        for name in ("description", "validation_hint"):
            value = getattr(self, name)
            if not isinstance(value, str) or any(character in value for character in "\r\n"):
                raise ValueError(f"guidance {name} must be one line")
            _safe(value, f"guidance {name}")
        for name in ("example", "format_hint"):
            value = getattr(self, name)
            if value is not None:
                _safe(_line(value, f"guidance {name}"), f"guidance {name}")
        if self.obtain_from is not None and not isinstance(self.obtain_from, ObtainFrom):
            raise ValueError("guidance obtain-from is invalid")


@dataclass(frozen=True, slots=True)
class InputValidation:
    """The authoritative rule. Guidance may describe it; only this decides."""

    kind: str
    pattern: str | None = None
    allowed_hosts: tuple[str, ...] = ()
    message: str = ""

    def __post_init__(self) -> None:
        if self.kind not in _VALIDATION_KINDS:
            raise ValueError("input validation kind is unsupported")
        if self.kind == "pattern":
            _line(self.pattern, "validation pattern")
            try:
                re.compile(str(self.pattern))
            except re.error as error:
                raise ValueError(f"validation pattern is invalid: {error}") from error
        elif self.pattern is not None:
            raise ValueError("only a pattern validation carries a pattern")
        if self.kind == "url":
            if not self.allowed_hosts:
                raise ValueError("url validation requires at least one allowed host")
        elif self.allowed_hosts:
            raise ValueError("only a url validation carries allowed hosts")
        hosts = tuple(sorted({_line(host, "allowed host").lower() for host in self.allowed_hosts}))
        object.__setattr__(self, "allowed_hosts", hosts)
        if not isinstance(self.message, str) or any(
            character in self.message for character in "\r\n"
        ):
            raise ValueError("validation message must be one line")


def _url_host(value: str) -> str | None:
    """The lowercase host of a plain http(s) URL, or None when the URL is not plainly one.

    Parsed here rather than with `urllib.parse` for two reasons. `domain` imports no module whose
    package can reach the network, and `urlsplit` is lenient in exactly the places a host allow-list
    is attacked: it accepts userinfo, backslashes and control characters, and different consumers
    then disagree about which host was named. Anything unusual is refused instead of interpreted.
    """

    if not isinstance(value, str) or not value or len(value) > 2048:
        return None
    if any(character in _REFUSED_CHARACTERS or character <= " " for character in value):
        return None
    scheme, separator, rest = value.partition("://")
    if not separator or scheme.lower() not in {"http", "https"}:
        return None
    authority = rest
    for delimiter in ("/", "?", "#"):
        authority = authority.partition(delimiter)[0]
    if not authority or "@" in authority or "[" in authority or "]" in authority:
        return None
    host = authority
    if ":" in authority:
        host, _, port = authority.rpartition(":")
        if not host or not port.isdigit():
            return None
    if not host or host.startswith(".") or host.endswith(".") or ".." in host:
        return None
    if any(character not in _HOST_CHARACTERS for character in host.lower()):
        return None
    return host.lower()


def validate_config_value(validation: InputValidation | None, value: str) -> str | None:
    """Return why the value is unacceptable, or None when it satisfies the rule."""

    if validation is None:
        return None
    if validation.kind == "identifier":
        return None if _ID_RE.fullmatch(value) else validation.message or "expected an identifier"
    if validation.kind == "pattern":
        if re.fullmatch(str(validation.pattern), value):
            return None
        return validation.message or f"expected {validation.pattern}"
    host = _url_host(value)
    if host is None:
        return validation.message or "expected an http or https url"
    if host not in validation.allowed_hosts:
        return validation.message or f"host {host} is not an allowed host"
    return None


@dataclass(frozen=True, slots=True)
class SecretInput:
    """Confidential input. It has no value or default field, and never gains one."""

    id: InputId
    binding: ProcessBinding
    required: bool = True
    guidance: InputGuidance | None = None

    def __post_init__(self) -> None:
        _input_id(self.id, "secret input id")
        if not isinstance(self.binding, ProcessBinding) or not isinstance(self.required, bool):
            raise ValueError("secret input is invalid")
        if self.guidance is not None:
            if not isinstance(self.guidance, InputGuidance):
                raise ValueError("secret input guidance is invalid")
            # A plausible example trains people to treat credentials as copyable configuration.
            if self.guidance.example is not None:
                raise ValueError("secret guidance uses a format hint, never an example value")


@dataclass(frozen=True, slots=True)
class ConfigInput:
    id: InputId
    binding: ProcessBinding
    required: bool = True
    validation: InputValidation | None = None
    guidance: InputGuidance | None = None
    default: str | None = None

    def __post_init__(self) -> None:
        _input_id(self.id, "config input id")
        if not isinstance(self.binding, ProcessBinding) or not isinstance(self.required, bool):
            raise ValueError("config input is invalid")
        if self.validation is not None and not isinstance(self.validation, InputValidation):
            raise ValueError("config input validation is invalid")
        if self.guidance is not None and not isinstance(self.guidance, InputGuidance):
            raise ValueError("config input guidance is invalid")
        if self.default is not None:
            _line(self.default, "config default")
            failure = validate_config_value(self.validation, self.default)
            if failure is not None:
                raise ValueError(f"config default is invalid: {failure}")


RuntimeInput: TypeAlias = SecretInput | ConfigInput


@dataclass(frozen=True, slots=True)
class SecretProviderReference:
    """The only source a secret input may bind to."""

    input: InputId
    provider: CredentialProviderRef

    def __post_init__(self) -> None:
        _input_id(self.input, "secret source input")
        if not isinstance(self.provider, CredentialProviderRef):
            raise ValueError("secret provider reference is invalid")

    @property
    def reference(self) -> CredentialReference:
        return CredentialReference(self.input, self.provider)


@dataclass(frozen=True, slots=True)
class PersistedConfigValue:
    input: InputId
    value: str

    def __post_init__(self) -> None:
        _input_id(self.input, "persisted config input")
        _line(self.value, "persisted config value")


@dataclass(frozen=True, slots=True)
class PromptedConfigValue:
    input: InputId
    value: str

    def __post_init__(self) -> None:
        _input_id(self.input, "prompted config input")
        _line(self.value, "prompted config value")


@dataclass(frozen=True, slots=True)
class PolicyProvidedValue:
    input: InputId
    value: str

    def __post_init__(self) -> None:
        _input_id(self.input, "policy provided input")
        _line(self.value, "policy provided value")


InputValueSource: TypeAlias = (
    SecretProviderReference | PersistedConfigValue | PromptedConfigValue | PolicyProvidedValue
)


def _source_kind(source: InputValueSource) -> str:
    if isinstance(source, SecretProviderReference):
        return "secret-provider"
    if isinstance(source, PersistedConfigValue):
        return "persisted"
    if isinstance(source, PromptedConfigValue):
        return "prompted"
    return "policy"


@dataclass(frozen=True, slots=True)
class BoundInput:
    input: RuntimeInput
    source: InputValueSource

    def __post_init__(self) -> None:
        if not isinstance(self.input, RuntimeInput) or not isinstance(
            self.source, InputValueSource
        ):
            raise ValueError("bound input is invalid")
        if self.input.id != self.source.input:
            raise ValueError("bound input and source must name the same input")
        if isinstance(self.input, SecretInput) != isinstance(self.source, SecretProviderReference):
            raise ValueError("only a secret input binds to a secret provider reference")

    @property
    def binding(self) -> ProcessBinding:
        return self.input.binding


@dataclass(frozen=True, slots=True)
class BoundInputs:
    inputs: tuple[BoundInput, ...] = ()

    def __post_init__(self) -> None:
        if any(not isinstance(item, BoundInput) for item in self.inputs):
            raise ValueError("bound inputs are invalid")
        ordered = tuple(sorted(self.inputs, key=lambda item: item.input.id.value))
        if len({item.input.id for item in ordered}) != len(ordered):
            raise ValueError("each input binds exactly once")
        object.__setattr__(self, "inputs", ordered)

    @property
    def credential_references(self) -> tuple[CredentialReference, ...]:
        return tuple(
            item.source.reference
            for item in self.inputs
            if isinstance(item.source, SecretProviderReference)
        )

    @property
    def config_values(self) -> tuple[tuple[InputId, str], ...]:
        return tuple(
            (item.input.id, item.source.value)
            for item in self.inputs
            if not isinstance(item.source, SecretProviderReference)
        )


def _guidance_data(guidance: InputGuidance | None) -> dict[str, object] | None:
    if guidance is None:
        return None
    return {
        "description": guidance.description,
        "example": guidance.example,
        "format_hint": guidance.format_hint,
        "label": guidance.label,
        "obtain_from": (
            None
            if guidance.obtain_from is None
            else {"label": guidance.obtain_from.label, "url": guidance.obtain_from.url}
        ),
        "validation_hint": guidance.validation_hint,
    }


def _binding_data(binding: ProcessBinding) -> dict[str, object]:
    data: dict[str, object] = {
        "exposure": binding.exposure.name.lower().replace("_", "-"),
        "kind": binding_kind(binding),
    }
    if isinstance(binding, CliArgumentBinding):
        data["argument"] = binding.argument
    elif isinstance(binding, EnvironmentBinding):
        data["variable"] = binding.variable
    elif isinstance(binding, FileBinding):
        data["path"] = binding.path
    return data


def input_to_data(value: RuntimeInput) -> dict[str, object]:
    data: dict[str, object] = {
        "binding": _binding_data(value.binding),
        "guidance": _guidance_data(value.guidance),
        "id": value.id.value,
        "kind": "secret" if isinstance(value, SecretInput) else "config",
        "required": value.required,
    }
    if isinstance(value, ConfigInput):
        data["default"] = value.default
        data["validation"] = (
            None
            if value.validation is None
            else {
                "allowed_hosts": list(value.validation.allowed_hosts),
                "kind": value.validation.kind,
                "message": value.validation.message,
                "pattern": value.validation.pattern,
            }
        )
    return data


def _source_data(source: InputValueSource) -> dict[str, object]:
    if isinstance(source, SecretProviderReference):
        return {
            "kind": _source_kind(source),
            "provider": credential_provider_to_data(source.provider),
        }
    return {"kind": _source_kind(source), "value": source.value}


def bound_inputs_to_data(bound: BoundInputs) -> dict[str, object]:
    return {
        "inputs": [
            {
                **input_to_data(item.input),
                "source": _source_data(item.source),
            }
            for item in bound.inputs
        ]
    }
