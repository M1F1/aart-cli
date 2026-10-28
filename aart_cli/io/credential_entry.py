"""Another way to enter a credential, used when the provider's own prompt kept the wrong value (§204).

macOS's `security add-generic-password -w` reads its value through libc `getpass`, which keeps at
most 128 characters and drops the rest without a word, so an Atlassian token of about 190 is
stored cut. Nothing about the prompt can be changed, so the value is entered another way.

Each way is an adapter behind one port, tried in order until one can run, so a machine without a
desktop falls through to plain instructions, CI exercises the chain with fakes, and a better way
can replace one later without the interpreter knowing. None of them hands a value to aart-cli:
the dialog's script stores what was typed itself, and the instructions have it typed into
Keychain Access.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from aart_cli.domain.credentials import CredentialReference
from aart_cli.io.credentials import SECURITY_TOOL, _interactive_quoted

OSASCRIPT = "/usr/bin/osascript"


class EntryOutcome(str, Enum):
    """What an entry says happened. Whatever it says, the provider is asked again afterwards."""

    ENTERED = "entered"
    CANCELLED = "cancelled"
    UNAVAILABLE = "unavailable"


class CredentialEntryFallback(Protocol):
    def enter(self, reference: CredentialReference, *, reason: str) -> EntryOutcome: ...


def _keychain_commands(
    reference: CredentialReference, keychain: str | None
) -> tuple[str, str, str]:
    """The `security -i` lines the dialog runs: delete, then add up to and after the hex value."""

    located = (
        "-a",
        _interactive_quoted(reference.provider.account),
        "-s",
        _interactive_quoted(reference.provider.service),
    )
    suffix = "" if keychain is None else " " + _interactive_quoted(keychain)
    delete = " ".join(("delete-generic-password", *located)) + suffix
    add = " ".join(("add-generic-password", *located, "-X", ""))
    return delete, add, suffix


def dialog_script(reference: CredentialReference, reason: str, keychain: str | None = None) -> str:
    """The JavaScript for Automation that asks for the value and stores it, carrying no value.

    What was typed is UTF-8 hex encoded inside the script and written to `security -i` through a
    pipe, as `MacOsKeychainProvider.store` writes a carried value: it is on no argv, in no file and
    never in this process. Everything this process puts into the script is a JSON literal.
    """

    delete, add, suffix = _keychain_commands(reference, keychain)
    prompt = (
        f"{reason}\n\nPaste {reference.input} for {reference.provider.service} "
        f"({reference.provider.account}). It is stored in your Keychain; aart-cli never sees it."
    )
    return f"""ObjC.import("Foundation");
function run() {{
  var app = Application.currentApplication();
  app.includeStandardAdditions = true;
  var answer;
  try {{
    answer = app.displayDialog({json.dumps(prompt)}, {{
      withTitle: "aart-cli", defaultAnswer: "", hiddenAnswer: true,
      buttons: ["Cancel", "Save"], defaultButton: "Save", cancelButton: "Cancel"
    }});
  }} catch (error) {{
    return "cancelled";
  }}
  var bytes = unescape(encodeURIComponent(answer.textReturned));
  if (!bytes.length) {{
    return "cancelled";
  }}
  var hex = "";
  for (var index = 0; index < bytes.length; index++) {{
    hex += ("0" + bytes.charCodeAt(index).toString(16)).slice(-2);
  }}
  var task = $.NSTask.alloc.init;
  task.launchPath = {json.dumps(SECURITY_TOOL)};
  task.arguments = ["-i"];
  var pipe = $.NSPipe.pipe;
  task.standardInput = pipe;
  task.standardOutput = $.NSFileHandle.fileHandleWithNullDevice;
  task.standardError = $.NSFileHandle.fileHandleWithNullDevice;
  task.launch;
  var commands = {json.dumps(delete + chr(10))} + {json.dumps(add)} + hex + {json.dumps(suffix + chr(10))};
  pipe.fileHandleForWriting.writeData($(commands).dataUsingEncoding($.NSUTF8StringEncoding));
  pipe.fileHandleForWriting.closeFile;
  task.waitUntilExit;
  return "entered";
}}
"""


def _run_osascript(script: str, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (OSASCRIPT, "-l", "JavaScript", "-"),
        input=script,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _desktop_available() -> bool:
    return sys.platform == "darwin"


@dataclass(frozen=True, slots=True)
class MacOsDialogEntry:
    """A macOS dialog with a hidden field, whose script stores what was typed in the Keychain."""

    keychain: str | None = None
    run: Callable[[str, float], subprocess.CompletedProcess[str]] = field(default=_run_osascript)
    available: Callable[[], bool] = field(default=_desktop_available)
    timeout_seconds: float = 600.0

    def enter(self, reference: CredentialReference, *, reason: str) -> EntryOutcome:
        if not self.available():
            return EntryOutcome.UNAVAILABLE
        try:
            ran = self.run(dialog_script(reference, reason, self.keychain), self.timeout_seconds)
        except (OSError, subprocess.TimeoutExpired):
            return EntryOutcome.UNAVAILABLE
        said = ran.stdout.strip()
        if ran.returncode != 0 or said not in ("entered", "cancelled"):
            # No window server, or osascript refused: nobody was asked, so the next way is tried.
            return EntryOutcome.UNAVAILABLE
        return EntryOutcome(said)


def _open_keychain_access() -> None:
    subprocess.run(
        ("/usr/bin/open", "-a", "Keychain Access"), capture_output=True, timeout=30, check=False
    )


@dataclass(frozen=True, slots=True)
class KeychainAccessInstructions:
    """Say how to put the value in by hand, open Keychain Access, and wait until it is done."""

    write: Callable[[str], object] = field(default=lambda text: print(text, flush=True))
    read_line: Callable[[], str] = field(default=input)
    open_app: Callable[[], None] = field(default=_open_keychain_access)
    available: Callable[[], bool] = field(default=_desktop_available)

    def enter(self, reference: CredentialReference, *, reason: str) -> EntryOutcome:
        if not self.available():
            return EntryOutcome.UNAVAILABLE
        self.write(
            "\n".join(
                (
                    "",
                    reason,
                    f"Enter {reference.input} in Keychain Access instead:",
                    "  1. In the login keychain, delete the existing item named "
                    f"{reference.provider.service} with account {reference.provider.account}.",
                    "  2. File → New Password Item…",
                    f"       Keychain Item Name: {reference.provider.service}",
                    f"       Account Name:       {reference.provider.account}",
                    "       Password:           paste the whole value",
                    "  3. Click Add. If macOS later asks whether `security` may read the item, "
                    "choose Always Allow.",
                    "Press Enter when it is saved, or type s and Enter to leave it for now.",
                )
            )
        )
        try:
            self.open_app()
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            answered = self.read_line()
        except EOFError:
            return EntryOutcome.CANCELLED
        return EntryOutcome.CANCELLED if answered.strip().lower() == "s" else EntryOutcome.ENTERED


def default_entry_fallbacks() -> tuple[CredentialEntryFallback, ...]:
    """The dialog first, then the instructions for when no dialog can be shown."""

    return (MacOsDialogEntry(), KeychainAccessInstructions())


def enter_another_way(
    fallbacks: tuple[CredentialEntryFallback, ...],
    reference: CredentialReference,
    *,
    reason: str,
) -> EntryOutcome:
    """Try each way in order until one could ask somebody."""

    for fallback in fallbacks:
        outcome = fallback.enter(reference, reason=reason)
        if outcome is not EntryOutcome.UNAVAILABLE:
            return outcome
    return EntryOutcome.UNAVAILABLE


__all__ = [
    "CredentialEntryFallback",
    "EntryOutcome",
    "KeychainAccessInstructions",
    "MacOsDialogEntry",
    "default_entry_fallbacks",
    "dialog_script",
    "enter_another_way",
]
