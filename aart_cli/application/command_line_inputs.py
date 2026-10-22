"""Answer an installation's inputs on the command line (§169.4, §172.4, §186, D-468).

`consume install` prepared with no input sources and refused whenever an artifact required one,
so an agent without a terminal could not install it at all. §169.4 allows non-interactive channels
when every binding names its installation target and nothing reads a generic input id from the
environment. These flags name the artifact with its Registry alias, the key 07 asks by, and §172.4
copies one answer into each of that artifact's new installations within the operation.

Only the pieces that decide something live here. Reading an environment variable and holding the
secret it yields stay in the command, because a `TransientSecret` must never reach `application`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
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
    "CommandLineAnswers",
    "CommandLineInput",
    "declared_defaults",
    "missing_input_flags",
    "parse_command_line_input",
    "resolve_command_line_inputs",
    "secret_references",
    "secret_variables",
]

COMMAND_LINE_INPUT_INVALID = DiagnosticCode("command-line-input-invalid")

_SHAPES = {
    "--input": "--input ALIAS/KIND/NAME:INPUT=VALUE",
    "--secret-env": "--secret-env ALIAS/KIND/NAME:INPUT=ENVIRONMENT_VARIABLE",
}


@dataclass(frozen=True, slots=True)
class CommandLineInput:
    """One flag: the artifact it answers for, the declared input, and what it gives.

    `value` is the answer for `--input` and the name of an environment variable for
    `--secret-env`; a credential itself is never a command-line argument, where `ps` could read it.
    """

    artifact: str
    input: InputId
    value: str


@dataclass(frozen=True, slots=True)
class CommandLineAnswers:
    answers: tuple[ArtifactAnswer, ...]
    secrets: tuple[CommandLineInput, ...]


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


def _kind(declared: RuntimeInput) -> str:
    return "credential" if isinstance(declared, SecretInput) else "configuration value"


def resolve_command_line_inputs(
    fields: Iterable[InstallationInputField],
    values: Iterable[CommandLineInput],
    secrets: Iterable[CommandLineInput],
) -> Result[CommandLineAnswers]:
    """Check every flag against what this operation installs, and say every mistake at once."""

    declared: dict[str, tuple[InstallationOwner, dict[InputId, RuntimeInput]]] = {}
    for field in fields:
        owner, inputs = declared.setdefault(artifact_answer_key(field.owner), (field.owner, {}))
        inputs.setdefault(field.input.id, field.input)
    problems: list[str] = []
    seen: set[tuple[str, InputId]] = set()
    answers: list[ArtifactAnswer] = []
    named: list[CommandLineInput] = []
    for flag, items, wanted in (
        ("--input", tuple(values), ConfigInput),
        ("--secret-env", tuple(secrets), SecretInput),
    ):
        for item in items:
            held = declared.get(item.artifact)
            if held is None:
                installs = ", ".join(sorted(declared)) or "nothing that takes inputs"
                problems.append(
                    f"{flag} names {item.artifact}, which this operation does not install; "
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
            elif not isinstance(runtime, wanted):
                other = "--secret-env" if flag == "--input" else "--input"
                problems.append(
                    f"{item.artifact}:{item.input} is a {_kind(runtime)}; give it with {other}"
                )
            elif (item.artifact, item.input) in seen:
                problems.append(f"{item.artifact}:{item.input} was answered twice")
            else:
                seen.add((item.artifact, item.input))
                if flag == "--input":
                    answers.append(
                        ArtifactAnswer(owner.source, owner.artifact, item.input, item.value)
                    )
                else:
                    named.append(item)
    if problems:
        return _refusal(*problems)
    return Ok(CommandLineAnswers(tuple(answers), tuple(named)))


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
    fields: Iterable[InstallationInputField],
    unanswered: Iterable[InstallationInputField],
    secrets: Iterable[CommandLineInput],
    *,
    set_later: bool,
    provider: str,
) -> tuple[OwnedInputSource, ...]:
    """Point each installation's credential at its own provider item (§169.4-6).

    A credential named by `--secret-env` gets an item on every installation of its artifact; with
    `set_later`, so does every required credential nobody named, and the install stores the
    placeholder there. Each address carries the whole owner, so two harnesses never share one.
    """

    named = {(item.artifact, item.input) for item in secrets}
    waiting = {field.key for field in unanswered} if set_later else set()
    references: list[OwnedInputSource] = []
    for field in fields:
        if not isinstance(field.input, SecretInput):
            continue
        if (artifact_answer_key(field.owner), field.input.id) in named or field.key in waiting:
            references.append(
                OwnedInputSource(
                    field.owner,
                    SecretProviderReference(
                        field.input.id,
                        credential_address(field.owner, field.input.id, provider=provider),
                    ),
                )
            )
    return tuple(references)


def secret_variables(
    bound: Iterable[tuple[InstallationOwner, object]],
    secrets: Iterable[CommandLineInput],
) -> Mapping[str, str]:
    """Each bound credential reference a `--secret-env` names, with the variable that holds it."""

    by_input = {(item.artifact, item.input): item.value for item in secrets}
    variables: dict[str, str] = {}
    for owner, value in bound:
        for item in getattr(value, "inputs", ()):
            source = item.source
            if not isinstance(item.input, SecretInput) or not isinstance(
                source, SecretProviderReference
            ):
                continue
            variable = by_input.get((artifact_answer_key(owner), item.input.id))
            if variable is not None:
                variables[str(source.reference)] = variable
    return variables


def missing_input_flags(unanswered: Iterable[InstallationInputField]) -> tuple[str, ...]:
    """The flag that answers each missing binding, once per artifact and input."""

    lines: dict[str, None] = {}
    for field in unanswered:
        target = f"{artifact_answer_key(field.owner)}:{field.input.id}"
        lines[
            f"--secret-env {target}=ENVIRONMENT_VARIABLE"
            if isinstance(field.input, SecretInput)
            else f"--input {target}=VALUE"
        ] = None
    return tuple(lines)
