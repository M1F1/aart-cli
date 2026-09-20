"""AART strict protocol primitives."""

from .capabilities import Capability, CapabilityDecision, negotiate_capabilities, parse_capability
from .hashing import TreeEntry, json_digest, parse_sha256, sha256_bytes, tree_digest
from .json import JsonArray, JsonObject, JsonValue, canonical_json_bytes, parse_json
from .native_models import (
    ArtifactManifest,
    CollectionManifest,
    Provenance,
    SourceManifest,
)
from .native_schema import (
    parse_artifact_manifest,
    parse_collection_manifest,
    parse_provenance,
    parse_source_manifest,
)
from .native_tree import (
    NativeArtifactPackage,
    NativeSource,
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
    load_native_source,
)
from .paths import SafeRelativePath, parse_relative_path
from .registry_index import index_artifact_from_package, validate_registry_graph
from .registry_models import (
    IndexArtifact,
    RegistryManifest,
    ReviewRecord,
    ServiceAdvertisement,
)
from .registry_schema import parse_registry_manifest, registry_manifest_to_json
from .semver import SemVer, VersionBounds, parse_semver, version_bounds

__all__ = [
    "ArtifactManifest",
    "Capability",
    "CapabilityDecision",
    "CollectionManifest",
    "IndexArtifact",
    "JsonArray",
    "JsonObject",
    "JsonValue",
    "NativeArtifactPackage",
    "NativeSource",
    "Provenance",
    "RegistryManifest",
    "ReviewRecord",
    "SafeRelativePath",
    "SemVer",
    "ServiceAdvertisement",
    "SnapshotEntry",
    "SnapshotEntryKind",
    "SnapshotOrigin",
    "SourceManifest",
    "SourceSnapshot",
    "TreeEntry",
    "VersionBounds",
    "canonical_json_bytes",
    "index_artifact_from_package",
    "json_digest",
    "load_native_source",
    "negotiate_capabilities",
    "parse_artifact_manifest",
    "parse_capability",
    "parse_collection_manifest",
    "parse_json",
    "parse_provenance",
    "parse_relative_path",
    "parse_registry_manifest",
    "parse_semver",
    "parse_sha256",
    "parse_source_manifest",
    "registry_manifest_to_json",
    "sha256_bytes",
    "tree_digest",
    "validate_registry_graph",
    "version_bounds",
]
