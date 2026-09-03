"""Post-install setup an installed artifact declares, and that nothing here has performed.

An artifact declares setup on its *package manifest* -- a `setup` reference naming a recipe inside
the package, and a package-root `SETUP.md` the compiler requires beside it. Nothing an installation
plan carries says so: the plan is about placing bytes, and placing bytes is the whole of what the
configured seam does. So the only way to know that a finished install left work outstanding is to
go back to the immutable object the installation came from, which is what the receipt's
`object_digest` was recorded for (D-122).

This module is the reading of that, and only the reading. It performs no setup, decides no trust
and plans no effect -- those belong to the setup engine. What it does is carry the declarations
from the durable installation record to the completion boundary that prepares that engine.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_artifacts.domain.identifiers import ArtifactCoordinate, ObjectDigest
from agent_artifacts.protocol.native_models import ArtifactManifest

__all__ = [
    "SETUP_MANUAL_FILENAME",
    "DeclaredArtifactSetup",
    "declared_artifact_setup",
    "declared_setup_to_data",
]

#: The document a package carrying setup must also carry, at its root. `compile_native_package`
#: refuses a setup declaration without one, so a promoted artifact that declares setup has it.
SETUP_MANUAL_FILENAME = "SETUP.md"


@dataclass(frozen=True, slots=True)
class DeclaredArtifactSetup:
    """One installed artifact's declared setup, named from the object it was installed from."""

    coordinate: ArtifactCoordinate
    object_digest: ObjectDigest
    recipe: str
    platforms: tuple[str, ...]
    #: The manual route, when the object carries it. `None` says this reader did not find the
    #: document rather than that the artifact has none -- a distinction worth keeping, because a
    #: person who cannot run the recipe is being sent somewhere, and sending them to a file that is
    #: not there is worse than telling them there is nowhere to go.
    manual: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.coordinate, ArtifactCoordinate)
            or self.coordinate.version is None
            or not isinstance(self.object_digest, ObjectDigest)
            or not isinstance(self.recipe, str)
            or not self.recipe.strip()
            or not self.platforms
            or any(not isinstance(item, str) or not item.strip() for item in self.platforms)
            or (self.manual is not None and (not isinstance(self.manual, str) or not self.manual))
        ):
            raise ValueError("a declared artifact setup is invalid")


def declared_artifact_setup(
    coordinate: ArtifactCoordinate,
    object_digest: ObjectDigest,
    manifest: ArtifactManifest,
    *,
    package_paths: frozenset[str],
) -> DeclaredArtifactSetup | None:
    """What this package declares, or nothing at all when it declares no setup."""

    if manifest.setup is None:
        return None
    return DeclaredArtifactSetup(
        coordinate,
        object_digest,
        str(manifest.setup.recipe),
        tuple(manifest.setup.platforms),
        SETUP_MANUAL_FILENAME if SETUP_MANUAL_FILENAME in package_paths else None,
    )


def declared_setup_to_data(setup: DeclaredArtifactSetup) -> dict[str, object]:
    """The payload shape both front ends report, named the way the coordinate is named."""

    return {
        "coordinate": str(setup.coordinate),
        "object_digest": str(setup.object_digest),
        "recipe": setup.recipe,
        "platforms": list(setup.platforms),
        "manual": setup.manual,
    }
