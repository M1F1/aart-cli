"""Where one consumer's screen-28 preferences are kept between sessions.

A Settings screen whose choices vanish when the terminal closes is not a settings screen, and
Maintainer Mode in particular has to survive a restart to be an opt-in at all: it is the boundary
that decides whether Sources, Candidates, Promotion and Publish are reachable.

These are preferences, not machine state. Nothing here names an artifact, a registry, a credential
or a path, so this file says nothing about what somebody has installed. It is read strictly --
a stored value AART cannot mean is refused rather than quietly replaced with a default, because
falling back to Fast after somebody chose Verbose is the frontend deciding for them.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import cast

from agent_artifacts.application.consumer_views import (
    CONSUMER_SETTINGS_INVALID,
    ConsumerSettings,
    settings_from_data,
    settings_to_data,
)
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.serialization import CanonicalValue, canonical_json_bytes

__all__ = [
    "CONSUMER_SETTINGS_UNWRITABLE",
    "consumer_settings_path",
    "read_consumer_settings",
    "write_consumer_settings",
]

CONSUMER_SETTINGS_UNWRITABLE = DiagnosticCode("consumer-settings-unwritable")


def consumer_settings_path(data_root: str) -> str:
    """The one file this machine's consumer preferences live in."""

    if not isinstance(data_root, str) or not data_root:
        raise ValueError("consumer settings need a data root")
    return str(Path(data_root) / "state" / "consumer-settings.json")


def read_consumer_settings(data_root: str) -> Result[ConsumerSettings]:
    """Preferences as they were last chosen. Never having chosen any is not a failure."""

    path = Path(consumer_settings_path(data_root))
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        return Ok(ConsumerSettings())
    except OSError as error:
        return _error(CONSUMER_SETTINGS_UNWRITABLE, f"cannot read {path}: {error}")
    try:
        parsed = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _error(CONSUMER_SETTINGS_INVALID, f"{path} is not readable JSON")
    return settings_from_data(parsed)


def write_consumer_settings(settings: ConsumerSettings, *, data_root: str) -> Result[str]:
    """Keep one choice, atomically, so an interrupted write never leaves half a preference."""

    if not isinstance(settings, ConsumerSettings):
        raise ValueError("keeping consumer settings needs consumer settings")
    path = Path(consumer_settings_path(data_root))
    content = canonical_json_bytes(cast("CanonicalValue", settings_to_data(settings)))
    stage: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, stage = tempfile.mkstemp(prefix=".aart-settings-", dir=path.parent)
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(stage, path)
        stage = None
        os.chmod(path, 0o600)
        return Ok(str(path))
    except OSError as error:
        return _error(CONSUMER_SETTINGS_UNWRITABLE, f"cannot keep {path}: {error}")
    finally:
        if stage is not None:
            try:
                os.unlink(stage)
            except OSError:
                pass


def _error(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message),))
