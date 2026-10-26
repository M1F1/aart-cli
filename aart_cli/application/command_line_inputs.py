"""Answer an installation's inputs on the command line (§169.4, §172.4, §186, §201, D-486).

`consume install` prepared with no input sources and refused whenever an artifact required one,
so an agent without a terminal could not install it at all. §169.4 allows non-interactive channels
when every binding names its installation target and nothing reads a generic input id from the
environment. These flags name the artifact with its Registry alias, the key 07 asks by, and §172.4
copies one answer into each of that artifact's new installations within the operation.

A credential is never answered here. It is pointed at its own provider item, and the credential
store's own prompt fills it when the reviewed run is applied in a terminal, or `--set-later` stores
the placeholder there. No value of a credential passes through aart-cli (§201).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.identifiers import InputId
from aart_cli.domain.inputs import (
    ConfigInput,
    RuntimeInput,
    SecretInput,
    SecretProviderReference,
    is_input_id,
)
from aart_cli.domain.installation_owner import InstallationOwner, credential_address
from aart_cli.domain.result import Err, Ok, Result

from .installation_inputs import (
    ArtifactAnswer,
    InstallationInputField,
    OwnedInputSource,
    artifact_answer_key,
)

__all__ = [
    "COMMAND_LINE_INPUT_INVALID",
    "CREDENTIAL_REMEDIATION",
    "CommandLineAnswers",
    "CommandLineInput",
    "declared_defaults",
    "missing_input_flags",
    "parse_command_line_input",
    "resolve_command_line_inputs",
    "secret_references",
]

COMMAND_LINE_INPUT_INVALID = DiagnosticCode("command-line-input-invalid")

_SHAPES = {"--input": "--input ALIAS/KIND/NAME:INPUT=VALUE"}


@dataclass(frozen=True, slots=True)
class CommandLineInput:
    """One flag: the artifact it answers for, the declared input, and what it gives.

    `value` is the answer. A credential is never a command-line argument, where `ps` could read it.
    """

    artifact: str
    input: InputId
    value: str


@dataclass(frozen=True, slots=True)
class CommandLineAnswers:
    answers: tuple[ArtifactAnswer, ...]


def _refusal(*messages: str, remediation: tuple[str, ...] = ()) -> Err:
    return Err(
        tuple(
            Diagnostic(COMMAND_LINE_INPUT_INVALID, Severity.ERROR, message, remediation=remediation)
            for message in messages
        )
    )


def parse_command_line_input(text: str, *, flag: str) -> Result[CommandLineInput]:
    """Split `ALIAS/KIND/NAME:INPUT=VALUE` at its first `=` and that target's last `:`.

    A refusal shows the target, never the value: someone who misplaced a `:` may still have typed a
    credential into the wrong flag.
    """

    target, separator, value = text.partition("=")
    artifact, colon, identifier = target.rpartition(":")
    if (
        not separator
        or not colon
        or len(artifact.split("/")) != 3
        or not all(artifact.split("/"))
        or not is_input_id(identifier)
    ):
        shown = target if separator else "the argument"
        return _refusal(
            f"{flag} needs ALIAS/KIND/NAME:INPUT=..., and {shown} is not that",
            remediation=(f"write it as {_SHAPES[flag]}",),
        )
    return Ok(CommandLineInput(artifact, InputId(identifier), value))


#: What to do instead when a credential is given to `--input`. The value is not repeated.
CREDENTIAL_REMEDIATION = (
    "run the command with --yes in a terminal: the credential store asks for it, and aart-cli "
    "never sees it",
    "pass --set-later instead, then set it with aart-cli consume inputs set-credential",
)


def resolve_command_line_inputs(
    fields: Iterable[InstallationInputField],
    values: Iterable[CommandLineInput],
) -> Result[CommandLineAnswers]:
    """Check every flag against what this operation installs, and say every mistake at once."""

    declared: dict[str, tuple[InstallationOwner, dict[InputId, RuntimeInput]]] = {}
    for field in fields:
        owner, inputs = declared.setdefault(artifact_answer_key(field.owner), (field.owner, {}))
        inputs.setdefault(field.input.id, field.input)
    problems: list[str] = []
    credential = False
    seen: set[tuple[str, InputId]] = set()
    answers: list[ArtifactAnswer] = []
    for item in values:
        held = declared.get(item.artifact)
        if held is None:
            installs = ", ".join(sorted(declared)) or "nothing that takes inputs"
            problems.append(
                f"--input names {item.artifact}, which this operation does not install; "
                f"it installs {installs}"
            )
            continue
        owner, inputs = held
        runtime = inputs.get(item.input)
        if runtime is None:
            problems.append(
                f"{item.artifact} declares no input {item.input}; it declares "
                + ", ".join(sorted(str(key) for key in inputs))
            )
        elif isinstance(runtime, SecretInput):
            credential = True
            problems.append(
                f"{item.artifact}:{item.input} is a credential, and a credential is never an "
                "argument"
            )
        elif (item.artifact, item.input) in seen:
            problems.append(f"{item.artifact}:{item.input} was answered twice")
        else:
            seen.add((item.artifact, item.input))
            answers.append(ArtifactAnswer(owner.source, owner.artifact, item.input, item.value))
    if problems:
        return _refusal(*problems, remediation=CREDENTIAL_REMEDIATION if credential else ())
    return Ok(CommandLineAnswers(tuple(answers)))


def declared_defaults(
    fields: Iterable[InstallationInputField],
    answers: Iterable[ArtifactAnswer],
) -> tuple[ArtifactAnswer, ...]:
    """The declared default of each ordinary input no flag answered (§172.4).

    07 pre-fills a default and Continue submits it; an input left at its default is an answer,
    not a skip. The command line has no form, so the same default stands unless a flag replaces it.
    """

    answered = {(item.source, item.artifact, item.input) for item in answers}
    defaults: dict[tuple[object, object, InputId], ArtifactAnswer] = {}
    for field in fields:
        declared = field.input
        if not isinstance(declared, ConfigInput) or declared.default is None:
            continue
        key = (field.owner.source, field.owner.artifact, declared.id)
        if key not in answered:
            defaults.setdefault(
                key,
                ArtifactAnswer(
                    field.owner.source, field.owner.artifact, declared.id, declared.default
                ),
            )
    return tuple(defaults.values())


def secret_references(
    unanswered: Iterable[InstallationInputField],
    *,
    provider: str,
) -> tuple[OwnedInputSource, ...]:
    """Point each unanswered credential of each installation at its own provider item (§169.4-6).

    The item is filled when the reviewed run is applied: by the credential store's own prompt, or
    with the placeholder under `--set-later`. Each address carries the whole owner, so two harnesses
    never share one.
    """

    return tuple(
        OwnedInputSource(
            field.owner,
            SecretProviderReference(
                field.input.id,
                credential_address(field.owner, field.input.id, provider=provider),
            ),
        )
        for field in unanswered
        if isinstance(field.input, SecretInput)
    )


def missing_input_flags(unanswered: Iterable[InstallationInputField]) -> tuple[str, ...]:
    """The flag that answers each missing ordinary input, once per artifact and input.

    A credential has none: the credential store asks for it (§201).
    """

    lines: dict[str, None] = {}
    for field in unanswered:
        if not isinstance(field.input, SecretInput):
            lines[f"--input {artifact_answer_key(field.owner)}:{field.input.id}=VALUE"] = None
    return tuple(lines)
