"""Effect port for one exact, reviewed registry workspace plan."""

from __future__ import annotations

from typing import Protocol

from aart_cli.domain.result import Result
from aart_cli.protocol.native_tree import SourceSnapshot

from .model import RegistryApplyCommand, RegistryApplyReceipt


class RegistryWorkspacePort(Protocol):
    def current(self) -> Result[SourceSnapshot]: ...

    def apply(self, command: RegistryApplyCommand) -> Result[RegistryApplyReceipt]: ...
