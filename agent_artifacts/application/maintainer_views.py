"""Pure Maintainer Mode screen identities and forward navigation.

The catalog is separate from the consumer catalog because the product makes visibility of the
whole maintainer surface an explicit preference boundary.  Both catalogs still travel through the
same application session and reducer; this module introduces no second UI state machine.
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "MAINTAINER_SCREENS",
    "MaintainerScreen",
    "maintainer_navigation_targets",
]


class MaintainerScreen(str, Enum):
    """The accepted Maintainer Mode screen catalog, numbered 30 through 53."""

    DASHBOARD = "30-maintainer-dashboard"
    SOURCES = "31-sources"
    SOURCE_DETAILS = "32-source-details"
    SOURCE_SYNC = "33-source-sync"
    SOURCE_SYNC_RESULT = "34-source-sync-result"
    CANDIDATES = "35-candidates"
    CANDIDATE_DETAILS = "36-candidate-details"
    CANDIDATE_DIFF = "37-candidate-diff"
    VALIDATION = "38-validation"
    VALIDATION_DETAILS = "39-validation-details"
    POLICY_REVIEW = "40-policy-review"
    PROMOTION_REVIEW = "41-promotion-review"
    PROMOTION_MODE = "42-promotion-mode"
    REGISTRY_DIFF = "43-registry-diff"
    REGISTRY_VALIDATION = "44-registry-validation"
    REGISTRY_COMMIT = "45-registry-commit"
    REGISTRY = "46-registry-maintainer"
    BULK_PROMOTION = "47-bulk-promotion"
    CANDIDATE_LIFECYCLE = "48-candidate-lifecycle"
    PROVENANCE = "49-provenance"
    VERSION_CONFLICT = "50-version-conflict"
    COLLECTION_CANDIDATES = "51-collection-candidates"
    COLLECTION_VALIDATION = "52-collection-validation"
    CANDIDATE_FILTERS = "53-candidate-filters"


MAINTAINER_SCREENS: tuple[MaintainerScreen, ...] = tuple(MaintainerScreen)


_NAVIGATION: dict[MaintainerScreen, tuple[MaintainerScreen, ...]] = {
    MaintainerScreen.DASHBOARD: (
        MaintainerScreen.SOURCES,
        MaintainerScreen.CANDIDATES,
        MaintainerScreen.REGISTRY,
    ),
    MaintainerScreen.SOURCES: (
        MaintainerScreen.SOURCE_DETAILS,
        MaintainerScreen.SOURCE_SYNC,
    ),
    MaintainerScreen.SOURCE_DETAILS: (MaintainerScreen.SOURCE_SYNC,),
    MaintainerScreen.SOURCE_SYNC: (MaintainerScreen.SOURCE_SYNC_RESULT,),
    MaintainerScreen.SOURCE_SYNC_RESULT: (MaintainerScreen.CANDIDATES,),
    MaintainerScreen.CANDIDATES: (
        MaintainerScreen.CANDIDATE_DETAILS,
        MaintainerScreen.BULK_PROMOTION,
        MaintainerScreen.COLLECTION_CANDIDATES,
        MaintainerScreen.CANDIDATE_FILTERS,
    ),
    MaintainerScreen.CANDIDATE_DETAILS: (
        MaintainerScreen.CANDIDATE_DIFF,
        MaintainerScreen.VALIDATION,
        MaintainerScreen.CANDIDATE_LIFECYCLE,
        MaintainerScreen.PROVENANCE,
        MaintainerScreen.VERSION_CONFLICT,
    ),
    MaintainerScreen.CANDIDATE_DIFF: (MaintainerScreen.VALIDATION,),
    MaintainerScreen.VALIDATION: (
        MaintainerScreen.VALIDATION_DETAILS,
        MaintainerScreen.POLICY_REVIEW,
    ),
    MaintainerScreen.VALIDATION_DETAILS: (MaintainerScreen.POLICY_REVIEW,),
    MaintainerScreen.POLICY_REVIEW: (MaintainerScreen.PROMOTION_REVIEW,),
    MaintainerScreen.PROMOTION_REVIEW: (MaintainerScreen.PROMOTION_MODE,),
    MaintainerScreen.PROMOTION_MODE: (MaintainerScreen.REGISTRY_DIFF,),
    MaintainerScreen.REGISTRY_DIFF: (MaintainerScreen.REGISTRY_VALIDATION,),
    MaintainerScreen.REGISTRY_VALIDATION: (MaintainerScreen.REGISTRY_COMMIT,),
    MaintainerScreen.REGISTRY_COMMIT: (MaintainerScreen.REGISTRY,),
    MaintainerScreen.REGISTRY: (),
    MaintainerScreen.BULK_PROMOTION: (MaintainerScreen.REGISTRY_DIFF,),
    MaintainerScreen.CANDIDATE_LIFECYCLE: (MaintainerScreen.PROVENANCE,),
    MaintainerScreen.PROVENANCE: (),
    MaintainerScreen.VERSION_CONFLICT: (),
    MaintainerScreen.COLLECTION_CANDIDATES: (MaintainerScreen.COLLECTION_VALIDATION,),
    MaintainerScreen.COLLECTION_VALIDATION: (MaintainerScreen.VALIDATION,),
    MaintainerScreen.CANDIDATE_FILTERS: (MaintainerScreen.CANDIDATES,),
}


def maintainer_navigation_targets(screen: MaintainerScreen) -> tuple[MaintainerScreen, ...]:
    """Accepted Maintainer forward routes, independent of terminal and machine state."""

    if not isinstance(screen, MaintainerScreen):
        raise ValueError("maintainer navigation needs a maintainer screen")
    return _NAVIGATION[screen]
