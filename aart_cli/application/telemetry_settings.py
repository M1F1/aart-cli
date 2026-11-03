"""What Settings says about telemetry, and the words `consume telemetry` shares with it (§213, B-253).

Settings' row turns telemetry on and off; on it, the status says where it sends, what it sends,
what waits, the last success and whether this machine sends as a person or as automation. What it
sends is said in the same words `consume telemetry enable` prints, so the two never disagree.
"""

from __future__ import annotations

from dataclasses import dataclass

from aart_cli.domain.telemetry import AUTOMATED_VARIABLE, BATCH_PATH

__all__ = ["TelemetryView", "sent_as", "telemetry_status", "what_is_sent"]


@dataclass(frozen=True, slots=True)
class TelemetryView:
    """Telemetry on this machine, as the outbox and the environment say."""

    enabled: bool = False
    #: Where it sends, or where turning it on would: the address kept, else the build's; empty when
    #: neither names one.
    endpoint: str = ""
    client_id: str = ""
    waiting: int = 0
    failures_waiting: int = 0
    #: The last success, as `consume telemetry status` prints it; empty when there was none.
    last_success_at: str = ""
    automated: bool = False


def sent_as(automation: bool) -> str:
    """How this machine's requests are counted (§213, D-511)."""

    if automation:
        return (
            "automation, counted apart from people "
            f"(CI or {AUTOMATED_VARIABLE}; {AUTOMATED_VARIABLE}=off says otherwise)"
        )
    return f"a person's installation ({AUTOMATED_VARIABLE}=on marks automation)"


def what_is_sent(client_id: str, *, unmanaged: bool, failures: bool) -> tuple[str, str]:
    """What telemetry sends from now on, and what it never sends: the consent asked for.

    `client_id` is the installation id, or empty before one is drawn.
    """

    sent = (
        "From now on each install, update and removal aart-cli completes, each recorded use of "
        "an artifact aart-cli installed"
        + (
            ", and each use of a skill or MCP aart-cli did not install, by the name the "
            "harness used (`consume telemetry unmanaged off` stops that),"
            if unmanaged
            else ","
        )
        + (
            " each failure aart-cli meets, by where, the exception's type and its own "
            "frames (`consume telemetry errors off` stops that),"
            if failures
            else ""
        )
        + " is sent at most every ten minutes, when something new is recorded."
    )
    installation = f"the installation id {client_id}" if client_id else "a random installation id"
    never = (
        f"Sent: the event, the artifact's kind, name and version, the moment, {installation} and "
        "aart-cli's version. Never a project, path, argument, prompt, user or host name, or "
        "credential."
    )
    return sent, never


def telemetry_status(view: TelemetryView, *, unmanaged: bool, failures: bool) -> tuple[str, ...]:
    """Settings' status on the telemetry row: what Enter agrees to, before it is pressed."""

    if view.enabled:
        said = [f"On: sends to {view.endpoint}{BATCH_PATH}."]
    elif view.endpoint:
        said = [
            f"Off. Enter turns it on, sending to {view.endpoint}{BATCH_PATH}, with what Activity "
            "already holds."
        ]
    else:
        said = [
            "Off. This aart-cli names no telemetry server; "
            "`aart-cli consume telemetry enable --endpoint URL` gives one."
        ]
    if view.endpoint:
        said.extend(what_is_sent(view.client_id, unmanaged=unmanaged, failures=failures))
    said.append(
        f"Waiting: {view.waiting} event(s), {view.failures_waiting} failure(s); "
        f"last sent {view.last_success_at or 'never'}."
    )
    said.append(f"Sent as: {sent_as(view.automated)}")
    if view.enabled:
        said.append("Enter turns it off; what waits is kept, unsent.")
    return tuple(said)
