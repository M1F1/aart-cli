"""Shared imperative composition for commands over configured AART sources.

This module deliberately owns only process-environment path resolution and configuration IO.
Individual commands retain their own domain operation and output contracts.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from aart_cli.application.configuration import (
    ConfigurationPorts,
    ConfigurationRequest,
    LoadedConfiguration,
    load_configuration,
)
from aart_cli.configuration.paths import (
    APPLICATION_HOME_VARIABLE,
    ConfigPaths,
    Platform,
    resolve_config_paths,
)
from aart_cli.configuration.policy import RuntimeOverrides, redact_text
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.io.config_cas import checked_config_writer
from aart_cli.io.config_store import (
    read_configuration,
    recover_configuration,
    write_configuration,
)
from aart_cli.model import Request


@dataclass(frozen=True, slots=True)
class ConfiguredRuntime:
    """Resolved private paths, IO ports, and one configuration read for a command."""

    paths: ConfigPaths
    ports: ConfigurationPorts
    loaded: LoadedConfiguration


def load_runtime_configuration(
    request: Request,
    *,
    content_required: bool,
) -> Result[ConfiguredRuntime]:
    """Load the user configuration without making an implicit source or config mutation."""

    platform = Platform.DARWIN if sys.platform == "darwin" else Platform.LINUX
    home = os.path.abspath(request.user_home or os.path.expanduser("~"))
    try:
        paths = resolve_config_paths(
            platform,
            home=home,
            application_home=os.environ.get(APPLICATION_HOME_VARIABLE) or None,
        )
    except ValueError as error:
        return Err(
            (
                Diagnostic(
                    DiagnosticCode("config-invalid"),
                    Severity.ERROR,
                    redact_text(f"configuration path environment is invalid: {error}"),
                    remediation=(
                        f"set {APPLICATION_HOME_VARIABLE} to a normalized absolute path, or unset it",
                    ),
                ),
            )
        )
    ports = ConfigurationPorts(
        read_configuration,
        write_configuration,
        recover_configuration,
        checked_config_writer,
    )
    loaded = load_configuration(
        ConfigurationRequest(paths, RuntimeOverrides(), content_required=content_required),
        ports,
    )
    if isinstance(loaded, Err):
        return loaded
    return Ok(ConfiguredRuntime(paths, ports, loaded.value))


__all__ = ["ConfiguredRuntime", "load_runtime_configuration"]
