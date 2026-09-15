"""What an artifact says an installation of it needs, before anything about a machine.

An author declares three separable things (§107): the runtime the artifact runs on, the packages it
depends on, and the values it is given when it starts. They are separate because they fail
separately -- a missing interpreter, an unresolvable dependency and an unanswered credential are
three different conversations with the person installing -- and because only one of them is ever
confidential.

This value holds all three and nothing else. It says nothing about where the artifact will live,
which interpreter will be found, or what any input's value is: those are facts about a machine and a
person, and they arrive later. Keeping them out is what lets the same description be read from a
package once and reused for an install here, a repair there and a report that touches neither.
"""

from __future__ import annotations

from dataclasses import dataclass

from .inputs import RuntimeInput, SecretInput, input_to_data
from .launch import LaunchContract, launch_contract_to_data
from .python_runtime import PythonDependencySpec, dependency_spec_to_data

__all__ = ["InstallDescription", "install_description_to_data"]


def _line(value: object, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character in value for character in "\r\n\x00")
    ):
        raise ValueError(f"{label} must be one safe non-empty line")


@dataclass(frozen=True, slots=True)
class InstallDescription:
    """The runtime, the dependencies and the inputs one artifact declares."""

    contract: LaunchContract | None = None
    runtime: str | None = None
    runtime_version: str | None = None
    inputs: tuple[RuntimeInput, ...] = ()
    dependencies: PythonDependencySpec | None = None

    def __post_init__(self) -> None:
        if self.contract is not None and not isinstance(self.contract, LaunchContract):
            raise ValueError("an install description holds a launch contract or nothing")
        if self.runtime is not None:
            _line(self.runtime, "runtime")
        if self.runtime_version is not None:
            _line(self.runtime_version, "runtime version")
        if self.runtime is None and self.runtime_version is not None:
            raise ValueError("a runtime version constrains a runtime, which is not declared")
        if not isinstance(self.inputs, tuple) or any(
            not isinstance(item, RuntimeInput) for item in self.inputs
        ):
            raise ValueError("declared inputs are invalid")
        identifiers = [item.id for item in self.inputs]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("each declared input may appear only once")
        if self.dependencies is not None:
            if not isinstance(self.dependencies, PythonDependencySpec):
                raise ValueError("declared dependencies are invalid")
            # A descriptor with no runtime declared has nothing to be installed into, and a
            # reconciler that guessed one would build an environment the author never asked for.
            if self.runtime != "python":
                raise ValueError(
                    "a Python dependency descriptor needs a declared Python runtime to install into"
                )

    @property
    def secrets(self) -> tuple[SecretInput, ...]:
        """The declared inputs whose values are confidential, in declared order."""

        return tuple(item for item in self.inputs if isinstance(item, SecretInput))


def install_description_to_data(description: InstallDescription) -> dict[str, object]:
    return {
        "dependencies": (
            None
            if description.dependencies is None
            else dependency_spec_to_data(description.dependencies)
        ),
        "inputs": [input_to_data(item) for item in description.inputs],
        "launch": (
            None if description.contract is None else launch_contract_to_data(description.contract)
        ),
        "runtime": description.runtime,
        "runtime_version": description.runtime_version,
    }
