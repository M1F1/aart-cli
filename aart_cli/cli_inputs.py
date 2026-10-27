"""`consume inputs`: Credentials and variables from the command line (§198, D-483).

The TUI's Credentials and variables without a screen. The application is the TUI's own
composition, every change is prepared and executed by `LocalConsumerActions`, and what an
installation's inputs are is `application.credentials_and_variables`, the module the screens read
too. So the checks, the review digest and what is written are the ones the screens get; this module
only parses, prints, and decides when a person has to be at the terminal.

A credential's value never passes through here. `set-credential` takes none: the credential store
asks for it on the terminal this process lends it, and the answer goes from the person to the store.
"""

from __future__ import annotations

import json
import shlex
import sys
from datetime import date

from . import command_outcome as _common
from .application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEventKind,
)
from .application.credentials_and_variables import (
    InstallationInputs,
    InstallationSelector,
    credential_setting,
    credential_state,
    installation_inputs,
    installation_parts,
    select_installations,
)
from .consumer_actions import LocalConsumerActions
from .domain.installation_owner import describe_installation
from .domain.result import Err
from .io.terminal_briefing import BriefingHandover, terminal_present
from .model import Request
from .redaction import redact_text
from .tui import _canonical_consumer_actions

_REFUSED = "consumer-inputs-refused"


#: Looked up when called, so a test can say whether a person is at the terminal.
_terminal_present = terminal_present


def _command(action: str, key: str, argument: str) -> str:
    """The command line that runs `action` on exactly this installation, ready to copy."""

    coordinate, label, scope, root = installation_parts(key)
    words = ["aart-cli", "consume", "inputs", action, coordinate.partition("@")[0], argument]
    if label:
        words += ["--harness", label]
    if scope:
        words += ["--scope", scope]
    if scope == "project" and root:
        words += ["--project", root]
    return " ".join(shlex.quote(word) for word in words)


class _Refusal(Exception):
    """Why a command stopped before changing anything, and what to run instead."""

    def __init__(self, message: str, *remediation: str, **extra: object) -> None:
        super().__init__(message)
        self.message = message
        self.remediation = remediation
        self.extra = extra


def _emit(request: Request, payload: dict[str, object], lines: tuple[str, ...]) -> None:
    if request.json:
        print(json.dumps(payload, indent=2))
    else:
        for line in lines:
            print(line)


def _refuse(request: Request, operation: str, refusal: _Refusal) -> int:
    message = redact_text(refusal.message)
    remediation = tuple(redact_text(item) for item in refusal.remediation)
    _emit(
        request,
        {
            "schema_version": 1,
            "ok": False,
            "operation": operation,
            "finalized": False,
            "diagnostics": [
                {"code": _REFUSED, "message": message, "remediation": list(remediation)}
            ],
            **refusal.extra,
        },
        (f"error: {message}", *(f"  {item}" for item in remediation)),
    )
    return _common.ERROR


def run(request: Request) -> int:
    action = request.inputs_action or ""
    operation = f"inputs.{action}"
    from .commands import marketplace

    composed = _canonical_consumer_actions(
        project=request.project,
        user_home=request.user_home,
        today=date.today(),
        credential_providers=marketplace._credential_providers(),
        handover=BriefingHandover(stream=sys.stderr),
    )
    try:
        if isinstance(composed, Err):
            raise _Refusal(composed.diagnostics[0].message)
        actions = composed.value
        if action == "list":
            return _list(request, actions)
        inputs = _one_installation(request, actions)
        if action == "set":
            return _set(request, actions, inputs)
        return _set_credential(request, actions, inputs)
    except _Refusal as refusal:
        return _refuse(request, operation, refusal)


def _inputs(actions: LocalConsumerActions, key: str) -> InstallationInputs:
    """One installation's inputs, from the screens the TUI draws Credentials and variables from."""

    screens = actions.source().screens
    return installation_inputs(
        key,
        screens.configurations_for(key),
        screens.credentials_for(key),
        screens.documentation_for(key),
    )


def _one_installation(request: Request, actions: LocalConsumerActions) -> InstallationInputs:
    coordinate = request.names[0]
    if len(request.profiles) > 1:
        raise _Refusal("name one harness: a change is made to one installation")
    selector = InstallationSelector(
        coordinate, request.profiles[0] if request.profiles else "", request.inputs_scope or ""
    )
    chosen = select_installations(actions.source().screens.user_input_artifacts(), selector)
    if not chosen:
        raise _Refusal(
            f"no installation of {coordinate} with inputs matches",
            "aart-cli consume inputs list shows each installation and its inputs",
        )
    if len(chosen) > 1:
        raise _Refusal(
            f"{coordinate} is installed more than once; name one installation",
            *(f"{describe_installation(key)}: {_selection_flags(key)}" for key in chosen),
        )
    return _inputs(actions, chosen[0])


def _selection_flags(key: str) -> str:
    _, label, scope, root = installation_parts(key)
    flags = [f"--harness {label}", f"--scope {scope}"]
    if scope == "project" and root:
        flags.append(f"--project {shlex.quote(root)}")
    return " ".join(flags)


def _list(request: Request, actions: LocalConsumerActions) -> int:
    keys = actions.source().screens.user_input_artifacts()
    named = {
        key
        for name in request.names or ("",)
        for harness in request.profiles or ("",)
        for key in select_installations(
            keys, InstallationSelector(name, harness, request.inputs_scope or "")
        )
    }
    documents: list[dict[str, object]] = []
    lines: list[str] = []
    for key in (item for item in keys if item in named):
        inputs = _inputs(actions, key)
        documents.append(
            {
                "installation": key,
                "coordinate": inputs.coordinate,
                "harness": inputs.harness,
                "scope": inputs.scope,
                "root": inputs.root,
                "documentation": inputs.documentation or None,
                "configuration": [
                    {
                        "input": item.input,
                        "value": item.value,
                        "placeholder": item.placeholder,
                        "path": item.path,
                        "state": item.state,
                        "command": _command("set", key, f"{item.input}=VALUE"),
                    }
                    for item in inputs.configuration
                ],
                "credentials": [
                    {
                        "input": item.input,
                        "provider": item.provider,
                        "reference": item.reference,
                        "state": item.health,
                        "placeholder": item.placeholder,
                        "detail": item.detail,
                        "command": _command("set-credential", key, item.input),
                    }
                    for item in inputs.credentials
                ],
            }
        )
        if lines:
            lines.append("")
        lines.append(describe_installation(key))
        if inputs.root:
            lines.append(f"  Root: {inputs.root}")
        for value in inputs.configuration:
            lines.append(f"  {value.input} = {'not set' if value.value is None else value.value}")
            if value.placeholder or value.value is None:
                lines.append(f"    set it: {_command('set', key, f'{value.input}=VALUE')}")
        for view in inputs.credentials:
            lines.append(
                f"  {view.input}: {credential_state(view)}"
                f" (in {view.provider}; aart-cli never reads or shows it)"
            )
            if view.placeholder or view.health != "present":
                lines.append(
                    f"    set it in a terminal: {_command('set-credential', key, view.input)}"
                )
        if inputs.documentation:
            lines.append(f"  Documentation: {inputs.documentation}")
    _emit(
        request,
        {
            "schema_version": 1,
            "ok": True,
            "operation": "inputs.list",
            "installations": documents,
        },
        tuple(lines) or ("No installed artifact here has configuration values or credentials.",),
    )
    return _common.OK


def _notice(update) -> tuple[str, ...]:
    return tuple(update.source.screens.notice)


def _prepared(update, refusal: str) -> str:
    """The review digest a prepared action established, or the service's reason it did not."""

    digest = update.event.review_digest
    if update.event.kind is not ConsumerUiEventKind.ACTION_PREPARED or not digest:
        raise _Refusal(refusal, *_notice(update))
    return digest


def _confirmed(request: Request, digest: str, review: dict[str, object]) -> None:
    if request.expect is not None and request.expect != digest:
        raise _Refusal(
            f"the change differs from the one reviewed: expected {request.expect}, "
            f"recomputed {digest}",
            "re-read the review, then re-run --expect with its review_digest",
            review_digest=digest,
            review=review,
        )


def _executed(actions: LocalConsumerActions, action: ConsumerActionKind, digest: str):
    update = actions.handle(
        ConsumerUiCommand(ConsumerUiCommandKind.EXECUTE_ACTION, action=action, review_digest=digest)
    )
    if update.event.kind is not ConsumerUiEventKind.ACTION_RECORDED:
        raise _Refusal("nothing was changed", *_notice(update))
    return update


def _set(request: Request, actions: LocalConsumerActions, inputs: InstallationInputs) -> int:
    key = inputs.key
    input_id, separator, value = (request.inputs_argument or "").partition("=")
    if not separator or not input_id:
        raise _Refusal("give the input and its value as INPUT=VALUE")
    if inputs.credential(input_id) is not None:
        # The value is not repeated, in this refusal or anywhere: it was meant to be a secret.
        raise _Refusal(
            f"{input_id} is a credential, and aart-cli never takes one as an argument",
            f"a person runs this in a terminal: {_command('set-credential', key, input_id)}",
        )
    held = [item for item in inputs.configuration if item.input == input_id]
    if not held:
        raise _Refusal(
            f"{describe_installation(key)} has no configuration input {input_id}",
            "aart-cli consume inputs list shows each installation and its inputs",
        )
    update = actions.handle(
        ConsumerUiCommand(
            ConsumerUiCommandKind.PREPARE_ACTION,
            action=ConsumerActionKind.CONFIGURE,
            focus=key,
            config_answers=((input_id, value),),
            targets=tuple(dict.fromkeys(item.harness for item in held)),
        )
    )
    digest = _prepared(update, f"{input_id} cannot be changed to this value")
    review: dict[str, object] = {
        "installation": key,
        "input": input_id,
        "from": held[0].value,
        "to": value,
        "path": held[0].path,
    }
    lines = (
        f"Change {input_id} of {describe_installation(key)}",
        f"  from: {'not set' if held[0].value is None else held[0].value}",
        f"  to:   {value}",
        f"  file: {held[0].path}",
        f"review_digest: {digest}",
    )
    if not request.yes:
        _emit(
            request,
            {
                "schema_version": 1,
                "ok": True,
                "operation": "inputs.set",
                "finalized": False,
                "review_digest": digest,
                **review,
            },
            lines + ("Reviewed only; re-run with --yes to make this exact change.",),
        )
        return _common.OK
    _confirmed(request, digest, review)
    executed = _executed(actions, ConsumerActionKind.CONFIGURE, digest)
    _emit(
        request,
        {
            "schema_version": 1,
            "ok": True,
            "operation": "inputs.set",
            "finalized": True,
            "review_digest": digest,
            "recorded_at": executed.event.text,
            **review,
        },
        (f"Changed {input_id} of {describe_installation(key)} to {value}.",),
    )
    return _common.OK


def _set_credential(
    request: Request, actions: LocalConsumerActions, inputs: InstallationInputs
) -> int:
    key = inputs.key
    input_id = request.inputs_argument or ""
    if "=" in input_id:
        # Whatever followed the `=` was meant to be a secret, so none of it is repeated.
        raise _Refusal(
            "set-credential takes no value: the credential store asks for it on the terminal",
            f"a person runs this in a terminal: "
            f"{_command('set-credential', key, input_id.partition('=')[0])}",
        )
    credential = inputs.credential(input_id)
    if credential is None:
        if inputs.declares_configuration(input_id):
            raise _Refusal(
                f"{input_id} is ordinary configuration, not a credential",
                f"change it with: {_command('set', key, f'{input_id}=VALUE')}",
            )
        raise _Refusal(
            f"{describe_installation(key)} has no credential input {input_id}",
            "aart-cli consume inputs list shows each installation and its inputs",
        )
    setting = credential_setting(credential)
    if setting is None:
        raise _Refusal(
            f"{credential.provider} cannot say whether {input_id} is stored: {credential.detail}"
        )
    intent, action = setting
    update = actions.handle(
        ConsumerUiCommand(
            ConsumerUiCommandKind.PREPARE_ACTION, action=action, focus=credential.reference
        )
    )
    digest = _prepared(update, f"{input_id} cannot be {intent}d here")
    command = f"{_command('set-credential', key, input_id)} --yes --expect {digest}"
    review: dict[str, object] = {
        "installation": key,
        "input": input_id,
        "intent": intent,
        "provider": credential.provider,
        "state": credential.health,
        "placeholder": credential.placeholder,
    }
    lines = (
        f"{intent.title()} {input_id} of {describe_installation(key)} in {credential.provider}",
        f"  now: {credential_state(credential)}",
        f"  {credential.provider} asks for the value itself; "
        "aart-cli never reads, shows or keeps it.",
        f"review_digest: {digest}",
    )
    if not request.yes:
        _emit(
            request,
            {
                "schema_version": 1,
                "ok": True,
                "operation": "inputs.set-credential",
                "finalized": False,
                "review_digest": digest,
                "command": command,
                **review,
            },
            lines + ("Reviewed only. A person runs this in a terminal:", f"  {command}"),
        )
        return _common.OK
    _confirmed(request, digest, review)
    if not _terminal_present():
        # Refused before the store is touched: a replacement removes the old item first, so a
        # prompt nobody can answer would leave the credential absent.
        raise _Refusal(
            "setting a credential needs a terminal: the credential store asks for the value "
            "itself, and aart-cli never takes it",
            f"a person runs this in a terminal: {command}",
            command=command,
            review_digest=digest,
        )
    executed = _executed(actions, action, digest)
    after = installation_inputs(key, (), executed.source.screens.credentials_for(key)).credential(
        input_id
    )
    _emit(
        request,
        {
            "schema_version": 1,
            "ok": True,
            "operation": "inputs.set-credential",
            "finalized": True,
            "review_digest": digest,
            **review,
            "state": None if after is None else after.health,
            "placeholder": None if after is None else after.placeholder,
        },
        _notice(executed),
    )
    return _common.OK


__all__ = ["run"]
