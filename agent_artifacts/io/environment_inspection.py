"""Read-only local observations for the canonical planning boundary.

This adapter deliberately performs no network probe and reads no credential value. Unsupported or
provider-owned observations remain explicit Unknown facts for later specialized inspectors.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass

from agent_artifacts.domain.inspection import (
    EnvironmentFact,
    EnvironmentFacts,
    FactState,
    RemediationCapability,
)
from agent_artifacts.domain.requirements import (
    ExecutableRequirement,
    FilesystemRequirement,
    Requirement,
    RuntimeRequirement,
)
from agent_artifacts.domain.result import Ok, Result


def platform_name() -> str:
    """The canonical platform name planning compares facts against."""

    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform.startswith("win"):
        return "windows"
    return sys.platform


@dataclass(frozen=True, slots=True)
class LocalEnvironmentInspector:
    remediation_capabilities: tuple[RemediationCapability, ...] = ()

    def inspect(self, requirements: tuple[Requirement, ...]) -> Result[EnvironmentFacts]:
        facts = []
        for requirement in requirements:
            if isinstance(requirement, RuntimeRequirement) and requirement.runtime == "python":
                facts.append(
                    EnvironmentFact(
                        requirement.id,
                        FactState.AVAILABLE,
                        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                    )
                )
            elif isinstance(requirement, ExecutableRequirement):
                facts.append(
                    EnvironmentFact(
                        requirement.id,
                        FactState.AVAILABLE
                        if shutil.which(requirement.executable) is not None
                        else FactState.UNAVAILABLE,
                    )
                )
            elif isinstance(requirement, FilesystemRequirement):
                mode = {
                    "read": os.R_OK,
                    "write": os.W_OK,
                    "execute": os.X_OK,
                }[requirement.access]
                facts.append(
                    EnvironmentFact(
                        requirement.id,
                        FactState.AVAILABLE
                        if os.path.exists(requirement.path) and os.access(requirement.path, mode)
                        else FactState.UNAVAILABLE,
                    )
                )
            else:
                facts.append(EnvironmentFact(requirement.id, FactState.UNKNOWN))
        return Ok(EnvironmentFacts(platform_name(), tuple(facts), self.remediation_capabilities))
