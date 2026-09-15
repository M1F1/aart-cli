"""Pure binding of declared runtime inputs to value sources under effective policy.

Nothing here reads a secret. A `SecretInput` resolves to a `CredentialReference` and stops there;
the value is fetched by a provider interpreter at the moment the process is started, which is why
`BoundInputs` is safe to serialize into a plan, a receipt or JSON output.
"""

from __future__ import annotations

from agent_artifacts.domain.credentials import CredentialReference
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import InputId
from agent_artifacts.domain.inputs import (
    BoundInput,
    BoundInputs,
    ConfigInput,
    InputValueSource,
    PersistedConfigValue,
    RuntimeInput,
    SecretInput,
    SecretProviderReference,
    binding_kind,
    validate_config_value,
)
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.result import Err, Ok, Result

INPUT_BINDING_INVALID = DiagnosticCode("input-binding-invalid")
INPUT_POLICY_VIOLATION = DiagnosticCode("input-policy-violation")
INPUT_REQUIRED = DiagnosticCode("input-required")


def _error(
    code: DiagnosticCode,
    message: str,
    *,
    details: tuple[tuple[str, str], ...] = (),
) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message, details=details),))


def _source_by_input(
    sources: tuple[InputValueSource, ...],
) -> Result[dict[InputId, InputValueSource]]:
    by_input: dict[InputId, InputValueSource] = {}
    for source in sources:
        if source.input in by_input:
            return _error(
                INPUT_BINDING_INVALID,
                f"input {source.input} has more than one value source",
                details=(("input", source.input.value),),
            )
        by_input[source.input] = source
    return Ok(by_input)


def _policy_failure(input_id: InputId, message: str) -> Err:
    return _error(INPUT_POLICY_VIOLATION, message, details=(("input", input_id.value),))


def _check_secret(
    declared: SecretInput,
    source: InputValueSource,
    policy: EffectivePolicy,
) -> Err | None:
    if not isinstance(source, SecretProviderReference):
        return _error(
            INPUT_BINDING_INVALID,
            f"secret input {declared.id} must bind to a credential provider reference",
            details=(("input", declared.id.value),),
        )
    provider = source.provider.provider
    if (
        policy.allowed_credential_providers is not None
        and provider not in policy.allowed_credential_providers
    ):
        return _policy_failure(
            declared.id, f"credential provider {provider} is forbidden by effective policy"
        )
    kind = binding_kind(declared.binding)
    if policy.allowed_secret_bindings is not None and kind not in policy.allowed_secret_bindings:
        return _policy_failure(
            declared.id, f"secret binding {kind} is forbidden by effective policy"
        )
    return None


def _check_config(
    declared: ConfigInput,
    source: InputValueSource,
    policy: EffectivePolicy,
) -> Err | None:
    if isinstance(source, SecretProviderReference):
        return _error(
            INPUT_BINDING_INVALID,
            f"config input {declared.id} must not bind to a credential provider reference",
            details=(("input", declared.id.value),),
        )
    if isinstance(source, PersistedConfigValue) and (
        declared.id.value in policy.forbidden_persisted_config
    ):
        return _policy_failure(
            declared.id, f"config input {declared.id} must not be persisted under effective policy"
        )
    failure = validate_config_value(declared.validation, source.value)
    if failure is not None:
        return _error(
            INPUT_BINDING_INVALID,
            f"config input {declared.id} is invalid: {failure}",
            details=(("input", declared.id.value),),
        )
    return None


def bind_runtime_inputs(
    inputs: tuple[RuntimeInput, ...],
    sources: tuple[InputValueSource, ...],
    policy: EffectivePolicy,
) -> Result[BoundInputs]:
    """Resolve every declared input against the sources the environment offers."""

    declared_ids = tuple(item.id for item in inputs)
    if len(set(declared_ids)) != len(declared_ids):
        return _error(INPUT_BINDING_INVALID, "each runtime input may be declared only once")
    by_input = _source_by_input(sources)
    if isinstance(by_input, Err):
        return by_input
    unknown = set(by_input.value) - set(declared_ids)
    if unknown:
        names = ", ".join(sorted(item.value for item in unknown))
        return _error(
            INPUT_BINDING_INVALID,
            f"value sources name inputs this artifact does not declare: {names}",
        )

    bound: list[BoundInput] = []
    for declared in inputs:
        source = by_input.value.get(declared.id)
        if source is None:
            if declared.required:
                return _error(
                    INPUT_REQUIRED,
                    f"required input {declared.id} has no value source",
                    details=(("input", declared.id.value),),
                )
            continue
        failure = (
            _check_secret(declared, source, policy)
            if isinstance(declared, SecretInput)
            else _check_config(declared, source, policy)
        )
        if failure is not None:
            return failure
        bound.append(BoundInput(declared, source))
    try:
        return Ok(BoundInputs(tuple(bound)))
    except ValueError as error:
        return _error(INPUT_BINDING_INVALID, f"bound inputs are invalid: {error}")


def credential_references(bound: BoundInputs) -> tuple[CredentialReference, ...]:
    """The references an installation must configure, deduplicated and canonically ordered."""

    return tuple(sorted(set(bound.credential_references)))
