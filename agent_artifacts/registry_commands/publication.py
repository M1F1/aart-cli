"""The canonical Registry publication gate names and generated-workflow commands."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RegistryPublicationGateSpec:
    name: str
    commands: tuple[str, ...]
    #: Whether the generated workflow runs this gate at all. `lock` does not, and that is not an
    #: omission: CI reads the approved representation, where a lock resolves nothing, so the step
    #: could only ever report "nothing to resolve" -- CP-26.5 took it out of the workflow. It is
    #: still a real gate over the local workspace, which is why it stays on this list.
    in_generated_workflow: bool = True


REGISTRY_PUBLICATION_GATES = (
    RegistryPublicationGateSpec("format", ("aart registry format --source . --check",)),
    RegistryPublicationGateSpec(
        "lock", ("aart registry lock --source . --check",), in_generated_workflow=False
    ),
    RegistryPublicationGateSpec("build", ("aart registry build --source . --check",)),
    # `--strict --frozen` stood here and in the generated workflow since 0.0.1, and the CLI has
    # never accepted either: a generated registry's CI failed this step with `unrecognized
    # arguments`. It surfaced when this list moved the command into a `.py` file, where the guard
    # that requires every command the package names to be one the parser accepts could see it. The
    # byte template had hidden it from that guard for the whole life of the repository (B-156).
    RegistryPublicationGateSpec("validate", ("aart registry validate --source .",)),
    RegistryPublicationGateSpec("audit", ("aart registry audit --source .",)),
    RegistryPublicationGateSpec(
        "compatibility",
        (
            "aart registry test --source . --compatibility minimum",
            "aart registry test --source . --compatibility latest",
        ),
    ),
)


__all__ = ["REGISTRY_PUBLICATION_GATES", "RegistryPublicationGateSpec"]
