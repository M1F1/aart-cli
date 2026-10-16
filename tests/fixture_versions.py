"""The versions test fixtures stand in for, now that source manifests carry none (§173.1, D-425).

A Registry assigns versions by counting approved changes; `tests/registry_versions_test.py` and the
adoption and Sync tests hold that rule. Most other tests are about something else and were written
around particular numbers. Their fixtures say which number with a test-only extension key,
`x-fixture-version`, which the parser accepts and compiles nothing from, and `with_fixture_versions`
tells the compiler exactly those numbers. A fixture without the key is `1.0.0`, a first version.
"""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass

from aart_cli.domain.identifiers import ArtifactIdentity, ObjectDigest
from aart_cli.domain.result import Ok
from aart_cli.domain.selection import ArtifactRequest
from aart_cli.protocol.native_tree import SourceSnapshot
from aart_cli.protocol.semver import SemVer, parse_semver
from aart_cli.protocol.yaml import parse_yaml

FIXTURE_VERSION_KEY = "x-fixture-version"


def _declared(path: str, content: bytes) -> tuple[tuple[str, str], str] | None:
    """The (kind, name) and declared fixture version of one manifest, when it declares one."""

    if path.endswith(".json"):
        try:
            document = json.loads(content)
        except ValueError:
            return None
    else:
        parsed = parse_yaml(content)
        if not isinstance(parsed, Ok):
            return None
        document = parsed.value
    artifact = document.get("artifact") if hasattr(document, "get") else None
    declared = artifact.get(FIXTURE_VERSION_KEY) if hasattr(artifact, "get") else None
    if not isinstance(declared, str):
        return None
    return (str(artifact.get("kind")), str(artifact.get("name"))), declared


@dataclass(frozen=True)
class FixtureVersions:
    """Declared numbers for artifacts; a member resolves in `registry` when one is given."""

    declared: tuple[tuple[tuple[str, str], str], ...] = ()
    registry: object | None = None

    def version(self, identity: ArtifactIdentity, input_digest: ObjectDigest) -> SemVer:
        raw = dict(self.declared).get((identity.kind, identity.name), "1.0.0")
        parsed = parse_semver(raw)
        assert isinstance(parsed, Ok), raw
        return parsed.value

    def resolve(self, request: ArtifactRequest) -> str | None:
        return None if self.registry is None else self.registry.resolve(request)  # type: ignore[attr-defined]


def fixture_versions(snapshot: SourceSnapshot) -> FixtureVersions:
    declared = []
    for entry in snapshot.entries:
        name = str(entry.path).rsplit("/", 1)[-1]
        if name in {"aart-cli.json", "aart-cli.yaml"} and entry.content is not None:
            found = _declared(name, entry.content)
            if found is not None:
                declared.append(found)
    return FixtureVersions(tuple(declared))


def with_fixture_versions(compile_function):
    """`compile_function`, told the versions its snapshot's fixtures declare."""

    @functools.wraps(compile_function)
    def compile_with_fixture_versions(snapshot, *args, **kwargs):
        kwargs.setdefault("versions", fixture_versions(snapshot))
        return compile_function(snapshot, *args, **kwargs)

    return compile_with_fixture_versions
