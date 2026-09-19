"""A configured approved artifact becomes a placed screen-07 draft from durable source state."""

from __future__ import annotations

import dataclasses
import json
import pathlib
import tempfile
import unittest
from typing import cast

from aart_cli.application.installation_inputs import OwnedInputSource
from aart_cli.application.maintainer import reconcile_source_scan
from aart_cli.application.promotion import (
    PromotionEvidence,
    load_registry_versions,
    plan_bulk_promotion,
    plan_registry_lifecycle,
    project_lifecycle_update,
    project_promotion,
)
from aart_cli.configuration.model import SourceKind
from aart_cli.domain.candidates import CandidateId, assess_candidate
from aart_cli.domain.credentials import CredentialProviderRef, CredentialReference
from aart_cli.domain.harness import Scope
from aart_cli.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    SourceAlias,
    SourceId,
)
from aart_cli.domain.inputs import PromptedConfigValue, SecretProviderReference
from aart_cli.domain.installation_owner import (
    credential_address,
    installation_owner,
)
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.registry import PromotionMode, publish_registry_version
from aart_cli.domain.result import Ok
from aart_cli.domain.selection import (
    ArtifactRequest,
    ArtifactSelection,
    VersionConstraint,
)
from aart_cli.io.configured_installation import prepare_configured_installation_draft
from aart_cli.io.object_store import read_object
from aart_cli.io.source_store import publish_source_snapshot
from aart_cli.protocol.authoring import CompiledAuthorArtifact, compile_author_snapshot
from aart_cli.protocol.json import canonical_json_bytes
from aart_cli.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
    compile_native_package,
)
from aart_cli.protocol.paths import parse_relative_path
from aart_cli.sources.model import (
    SourcePublishCommand,
    ValidatedSourceCandidate,
    make_source_candidate,
    source_instance_id,
    source_store_paths,
)
from aart_cli.store.model import ObjectReadRequest, object_store_paths
from tests.artifact_installation_e2e_test import MANIFEST, ORG, SERVER_SOURCE, TOKEN
from tests.marketplace_fixtures import configured_source, effective_configuration
from tests.promotion_planning_test import _evidence

KEYCHAIN = CredentialProviderRef("macos-keychain", "aart/mcp/github", "default")


#: One file as its author wrote it: a path, its text, and optionally whether it is executable. The
#: bit travels with the content because a hook's script has to arrive executable or the harness
#: cannot run what was installed.
def _authored(item: tuple[str, str] | tuple[str, str, bool]) -> SnapshotEntry:
    parsed = parse_relative_path(item[0])
    assert isinstance(parsed, Ok), parsed
    return SnapshotEntry(
        parsed.value,
        SnapshotEntryKind.FILE,
        item[1].encode(),
        len(item) == 3 and bool(item[2]),
    )


#: One MCP server, as an author's repository holds it before anything compiles it.
AUTHORED_MCP: tuple[tuple[str, str] | tuple[str, str, bool], ...] = (
    ("github/aart-cli.json", json.dumps(MANIFEST)),
    ("github/server.py", SERVER_SOURCE),
    ("github/requirements.txt", "# no third-party packages\n"),
)


@dataclasses.dataclass(frozen=True, slots=True)
class AuthoredSetup:
    """The setup an artifact declares, as the three files a native package carries it in.

    The authoring format has no setup section -- `aart-cli.json` cannot declare one -- so an artifact
    that needs configuring after placement acquires its declaration when it is packaged, not when
    it is written. Modelling that here as an injection into the compiled package rather than as a
    field on the author manifest is not a shortcut around the compiler; it is where the declaration
    actually enters, and the recipe still goes through the same strict parse every other one does.
    """

    #: The declarative installer, exactly as `setup/installer.json` holds it.
    recipe: dict
    #: The package-root document a person follows when the recipe cannot be run for them.
    manual: str = "Configure it by hand.\n"


def _with_setup(artifact: CompiledAuthorArtifact, setup: AuthoredSetup) -> CompiledAuthorArtifact:
    """Recompile one compiled artifact with its setup declaration added.

    Only the canonical entries change: the payload is untouched, so the payload digest the package
    was built around still describes it, and the recompile is what proves the declaration is valid
    rather than merely well-formed JSON sitting beside a manifest.
    """

    entries = {str(entry.path): entry for entry in artifact.canonical_entries}
    manifest = json.loads(entries["artifact.json"].content)
    manifest["setup"] = {"recipe": "setup/installer.json", "platforms": ["darwin"]}
    entries["artifact.json"] = _packaged("artifact.json", canonical_json_bytes(manifest))
    entries["setup/installer.json"] = _packaged(
        "setup/installer.json", canonical_json_bytes(setup.recipe)
    )
    entries["SETUP.md"] = _packaged("SETUP.md", setup.manual.encode())
    canonical = tuple(entries[key] for key in sorted(entries))
    native = compile_native_package(
        canonical, expected_identity=artifact.package.coordinate.artifact
    )
    assert isinstance(native, Ok), getattr(native, "diagnostics", ())
    return dataclasses.replace(artifact, canonical_entries=canonical, native_package=native.value)


def _packaged(path: str, content: bytes) -> SnapshotEntry:
    """One file as a packager writes it into the compiled tree."""

    parsed = parse_relative_path(path)
    assert isinstance(parsed, Ok), parsed
    return SnapshotEntry(parsed.value, SnapshotEntryKind.FILE, content)


def _promote_one_locally(
    authored: tuple[tuple[str, str] | tuple[str, str, bool], ...],
    *,
    onto: SourceSnapshot,
    revision: str,
    setup: AuthoredSetup | None = None,
    mode: PromotionMode = PromotionMode.VENDORED,
) -> SourceSnapshot:
    """One author tree through one real promotion transaction onto `onto`, and no further.

    This is everything a maintainer's own machine can do: the version record it writes says
    `promoted-local`, because publication is a Git review and merge nothing here performs
    (INV-242).
    """

    approved = load_registry_versions(onto)
    assert isinstance(approved, Ok), approved
    compiled = compile_author_snapshot(
        SourceSnapshot(
            SnapshotOrigin.IMMUTABLE_GIT,
            tuple(_authored(item) for item in authored),
        ),
        source_alias=SourceAlias("authors"),
        source="https://git.example/servers.git",
        revision=revision,
    )
    assert isinstance(compiled, Ok), compiled
    artifacts = compiled.value
    if setup is not None:
        artifacts = tuple(_with_setup(artifact, setup) for artifact in artifacts)
    scanned = reconcile_source_scan(
        SourceAlias("authors"),
        revision,
        artifacts,
        previous=(),
        approved=approved.value,
        target_registry=SourceAlias("company"),
    )
    assert isinstance(scanned, Ok), scanned
    bundle = scanned.value.active[0]
    bundle = dataclasses.replace(bundle, candidate=assess_candidate(bundle.candidate))
    evidence = cast(tuple[tuple[CandidateId, PromotionEvidence], ...], _evidence(bundle))
    promoted = plan_bulk_promotion(
        onto,
        (bundle,),
        evidence=evidence,
        approved=approved.value,
        mode=mode,
    )
    assert isinstance(promoted, Ok), promoted
    projected = project_promotion(onto, promoted.value)
    assert isinstance(projected, Ok), projected
    return SourceSnapshot(SnapshotOrigin.IMMUTABLE_GIT, projected.value.entries)


def _promote_one(
    authored: tuple[tuple[str, str] | tuple[str, str, bool], ...],
    *,
    onto: SourceSnapshot,
    revision: str,
    setup: AuthoredSetup | None = None,
    mode: PromotionMode = PromotionMode.VENDORED,
) -> SourceSnapshot:
    """One author tree promoted onto `onto`, then recorded as published.

    The publication half is written directly because these fixtures need a registry that already
    crossed the boundary, not one that is about to. What the boundary itself does with a
    promoted-local snapshot is `git_publication_transition_e2e_test`'s subject, and that test may
    not use this shortcut.
    """

    projected = _promote_one_locally(authored, onto=onto, revision=revision, setup=setup, mode=mode)
    reloaded = load_registry_versions(projected)
    assert isinstance(reloaded, Ok), reloaded
    after = tuple(publish_registry_version(item, item.registry_snapshot) for item in reloaded.value)
    lifecycle = plan_registry_lifecycle(projected, reloaded.value, after)
    assert isinstance(lifecycle, Ok), lifecycle
    published = project_lifecycle_update(projected, lifecycle.value)
    assert isinstance(published, Ok), published
    return SourceSnapshot(SnapshotOrigin.IMMUTABLE_GIT, published.value.entries)


def _promoted_local_registries(
    *authored: tuple[tuple[str, str] | tuple[str, str, bool], ...],
    setup: AuthoredSetup | None = None,
    mode: PromotionMode = PromotionMode.VENDORED,
) -> SourceSnapshot:
    """Several author trees promoted into one registry, stopping where a maintainer stops."""

    snapshot = SourceSnapshot(SnapshotOrigin.LOCAL, ())
    for index, tree in enumerate(authored):
        snapshot = _promote_one_locally(
            tree,
            onto=snapshot,
            revision=f"{index:x}" * 40,
            setup=setup,
            mode=mode,
        )
    return snapshot


def _published_registries(
    *authored: tuple[tuple[str, str] | tuple[str, str, bool], ...],
    setup: AuthoredSetup | None = None,
    mode: PromotionMode = PromotionMode.VENDORED,
) -> SourceSnapshot:
    """Several author trees taken to a published registry, one promotion transaction each.

    A registry is not written in one transaction: artifacts and versions arrive over time, and each
    promotion rebinds every retained approval to the registry's new content snapshot. Promoting one
    at a time is therefore the realistic shape, not a slower version of the same thing.
    """

    snapshot = SourceSnapshot(SnapshotOrigin.LOCAL, ())
    for index, tree in enumerate(authored):
        snapshot = _promote_one(
            tree,
            onto=snapshot,
            revision=f"{index:x}" * 40,
            setup=setup,
            mode=mode,
        )
    return snapshot


def _published_registry(
    authored: tuple[tuple[str, str] | tuple[str, str, bool], ...] = AUTHORED_MCP,
    *,
    setup: AuthoredSetup | None = None,
    mode: PromotionMode = PromotionMode.VENDORED,
) -> SourceSnapshot:
    """Take an author's files all the way to a published registry snapshot.

    Every step is the real one -- compile, scan, assess, promote, publish -- because the point of
    the fixture is that what an install resolves is what a registry approved, not a value this test
    handed it. `authored` is a parameter so the same path can carry an artifact a harness reads;
    nothing else about the pipeline changes for one.
    """

    return _published_registries(authored, setup=setup, mode=mode)


class ConfiguredInstallationDraftTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name).resolve()
        self.data_root = str(self.root / "data")
        self.project_root = str(self.root / "project")
        self.source = configured_source("company", SourceKind.REGISTRY_GIT)
        self.effective = effective_configuration((self.source,), default_registry="company")
        snapshot = _published_registry()
        candidate = make_source_candidate(
            source_instance_id(self.source), self.source.alias, "a" * 40, snapshot
        )
        assert isinstance(candidate, Ok), candidate
        written = publish_source_snapshot(
            SourcePublishCommand(
                source_store_paths(self.data_root, source_instance_id(self.source)),
                ValidatedSourceCandidate(candidate.value, SourceId("company-registry")),
                90,
            )
        )
        self.assertIsInstance(written, Ok, getattr(written, "diagnostics", ()))
        self.selection = ArtifactSelection(
            (
                ArtifactRequest(
                    ArtifactIdentity("mcp", "github"),
                    VersionConstraint("*"),
                    self.source.alias,
                ),
            )
        )

    def _draft(self, sources=(), profiles=("tabnine",)):
        return prepare_configured_installation_draft(
            self.effective,
            self.selection,
            data_root=self.data_root,
            project_root=self.project_root,
            scope=Scope.PROJECT,
            profiles=profiles,
            sources=sources,
            policy=EffectivePolicy(),
        )

    def _owner(self, harness="tabnine"):
        return installation_owner(
            ArtifactCoordinate(self.source.alias, ArtifactIdentity("mcp", "github"), "1.0.0"),
            scope=Scope.PROJECT,
            root=self.project_root,
            harness=harness,
        )

    def test_verified_registry_content_is_materialized_and_exposes_pending_inputs(self) -> None:
        drafted = self._draft()

        self.assertIsInstance(drafted, Ok, getattr(drafted, "diagnostics", ()))
        assert isinstance(drafted, Ok)
        self.assertFalse(drafted.value.ready)
        self.assertEqual(
            tuple(field.input.id for field in drafted.value.inputs.unanswered),
            (ORG, TOKEN),
        )
        self.assertEqual(drafted.value.inputs.views()[0].default, "acme")
        version = drafted.value.selection.artifacts[0].version
        stored = read_object(
            ObjectReadRequest(object_store_paths(self.data_root), version.object_digest)
        )
        self.assertIsInstance(stored, Ok)
        assert isinstance(stored, Ok)
        self.assertIsNotNone(stored.value)

    def test_submitted_config_and_provider_reference_make_placements_ready(self) -> None:
        owner = self._owner()
        drafted = self._draft(
            (
                OwnedInputSource(owner, PromptedConfigValue(ORG, "acme")),
                OwnedInputSource(owner, SecretProviderReference(TOKEN, KEYCHAIN)),
            )
        )

        self.assertIsInstance(drafted, Ok, getattr(drafted, "diagnostics", ()))
        assert isinstance(drafted, Ok)
        self.assertTrue(drafted.value.ready)
        self.assertEqual((owner,), drafted.value.owners)
        self.assertEqual(drafted.value.placements[0].installed_name, "github-company-project")
        placed = drafted.value.prepared_placements()
        self.assertIsInstance(placed, Ok, getattr(placed, "diagnostics", ()))
        assert isinstance(placed, Ok)
        self.assertEqual(placed.value[0].sources, drafted.value.inputs.sources_for(owner))
        self.assertFalse(any(hasattr(source, "secret") for source in placed.value[0].sources))

    def test_one_artifact_on_two_harnesses_is_two_installations(self) -> None:
        """§169.4-6: the harness is part of who owns the configuration, so it is part of the key."""

        drafted = self._draft(profiles=("tabnine", "claude"))

        self.assertIsInstance(drafted, Ok, getattr(drafted, "diagnostics", ()))
        assert isinstance(drafted, Ok)
        self.assertEqual((self._owner("claude"), self._owner("tabnine")), drafted.value.owners)
        self.assertEqual(4, len(drafted.value.inputs.fields))
        self.assertEqual(
            {
                (self._owner("claude"), ORG),
                (self._owner("claude"), TOKEN),
                (self._owner("tabnine"), ORG),
                (self._owner("tabnine"), TOKEN),
            },
            {(field.owner, field.input.id) for field in drafted.value.inputs.fields},
        )

    def test_two_harnesses_are_two_placements_under_two_trees(self) -> None:
        """§169.3: an installation's private files belong to the harness that selected it.

        One placement spanning two harnesses had one runtime tree, one launcher and one
        configuration file between them, which is the sharing §169.3 removes. Two harnesses are two
        installations, so they are two placements -- each owned by one installation, each rooted
        under that harness's own directory (D-359), and neither able to reach the other's files.
        """

        drafted = self._draft(profiles=("tabnine", "claude"))

        self.assertIsInstance(drafted, Ok, getattr(drafted, "diagnostics", ()))
        assert isinstance(drafted, Ok)
        placements = drafted.value.placements
        self.assertEqual(2, len(placements))
        self.assertEqual(
            {placement.owner for placement in placements},
            {self._owner("claude"), self._owner("tabnine")},
        )
        self.assertEqual(
            {placement.owner.harness: placement.root for placement in placements},
            {
                "claude": f"{self.project_root}/.claude/aart-cli/mcp/company/github",
                "tabnine": f"{self.project_root}/.tabnine/aart-cli/mcp/company/github",
            },
        )

    def test_each_placement_registers_with_the_one_harness_that_owns_it(self) -> None:
        drafted = self._draft(profiles=("tabnine", "claude"))

        assert isinstance(drafted, Ok), getattr(drafted, "diagnostics", ())
        for placement in drafted.value.placements:
            with self.subTest(harness=placement.owner.harness):
                self.assertEqual(
                    tuple(target.harness for target in placement.targets),
                    (placement.owner.harness,),
                )

    def test_a_placement_is_prepared_with_its_own_installation_s_answers(self) -> None:
        """Another installation's answers are not this placement's to carry.

        A Selection installs several artifacts at once and each of them into several harnesses, so
        a draft holds answers for installations this placement is not. Were the filter to let one
        of them through, a value declared for something else would reach this launcher.
        """

        claude = self._owner("claude")
        tabnine = self._owner("tabnine")
        drafted = self._draft(
            (
                OwnedInputSource(claude, PromptedConfigValue(ORG, "for-claude")),
                OwnedInputSource(claude, SecretProviderReference(TOKEN, KEYCHAIN)),
                OwnedInputSource(tabnine, PromptedConfigValue(ORG, "for-tabnine")),
                OwnedInputSource(tabnine, SecretProviderReference(TOKEN, KEYCHAIN)),
            ),
            profiles=("tabnine", "claude"),
        )

        assert isinstance(drafted, Ok), getattr(drafted, "diagnostics", ())
        prepared = drafted.value.prepared_placements()

        assert isinstance(prepared, Ok), getattr(prepared, "diagnostics", ())
        self.assertEqual(
            {
                placement.owner.harness: next(
                    item.value
                    for item in placement.sources
                    if isinstance(item, PromptedConfigValue)
                )
                for placement in prepared.value
            },
            {"claude": "for-claude", "tabnine": "for-tabnine"},
        )

    def test_two_harnesses_answering_differently_is_two_installations_not_a_conflict(self) -> None:
        """What D-354 had to refuse, §169.3 simply installs.

        While one placement spanned both harnesses there was one launcher between them, so two
        different answers to the same question had no single set of values to carry and the draft
        refused by name. Each harness now has its own placement, its own launcher and its own
        configuration, so the disagreement is not one: it is two installations, answered
        separately, which is what §169.4-6 asked for.
        """

        claude = self._owner("claude")
        tabnine = self._owner("tabnine")
        drafted = self._draft(
            (
                OwnedInputSource(claude, PromptedConfigValue(ORG, "acme")),
                OwnedInputSource(claude, SecretProviderReference(TOKEN, KEYCHAIN)),
                OwnedInputSource(tabnine, PromptedConfigValue(ORG, "other")),
                OwnedInputSource(tabnine, SecretProviderReference(TOKEN, KEYCHAIN)),
            ),
            profiles=("tabnine", "claude"),
        )

        assert isinstance(drafted, Ok), getattr(drafted, "diagnostics", ())
        self.assertTrue(drafted.value.ready)
        prepared = drafted.value.prepared_placements()

        assert isinstance(prepared, Ok), getattr(prepared, "diagnostics", ())
        self.assertEqual(
            {
                placement.owner.harness: next(
                    item.value
                    for item in placement.sources
                    if isinstance(item, PromptedConfigValue)
                )
                for placement in prepared.value
            },
            {"claude": "acme", "tabnine": "other"},
        )
        # Two trees, so the two answers never meet: neither launcher can read the other's file.
        self.assertEqual(2, len({placement.root for placement in prepared.value}))

    def test_each_installation_names_the_one_item_it_is_entitled_to(self) -> None:
        """§169.4-6: what a provider is asked for is this installation's own address.

        Composed from the owner rather than taken from what was answered. A reference naming some
        other installation's item is still stored as an ordinary source, but the address this
        placement declares it needs -- what is inspected, stored and recorded -- is its own.
        """

        claude = self._owner("claude")
        tabnine = self._owner("tabnine")
        drafted = self._draft(
            (
                OwnedInputSource(claude, PromptedConfigValue(ORG, "acme")),
                OwnedInputSource(
                    claude, SecretProviderReference(TOKEN, credential_address(claude, TOKEN))
                ),
                OwnedInputSource(tabnine, PromptedConfigValue(ORG, "acme")),
                OwnedInputSource(
                    tabnine, SecretProviderReference(TOKEN, credential_address(tabnine, TOKEN))
                ),
            ),
            profiles=("tabnine", "claude"),
        )

        assert isinstance(drafted, Ok), getattr(drafted, "diagnostics", ())
        prepared = drafted.value.prepared_placements()

        assert isinstance(prepared, Ok), getattr(prepared, "diagnostics", ())
        self.assertEqual(
            {
                placement.owner.harness: placement.credential_addresses
                for placement in prepared.value
            },
            {
                "claude": (CredentialReference(TOKEN, credential_address(claude, TOKEN)),),
                "tabnine": (CredentialReference(TOKEN, credential_address(tabnine, TOKEN)),),
            },
        )

    def test_one_installation_still_names_the_address_it_was_given(self) -> None:
        owner = self._owner()
        drafted = self._draft(
            (
                OwnedInputSource(owner, PromptedConfigValue(ORG, "acme")),
                OwnedInputSource(owner, SecretProviderReference(TOKEN, KEYCHAIN)),
            )
        )

        assert isinstance(drafted, Ok), getattr(drafted, "diagnostics", ())
        prepared = drafted.value.prepared_placements()

        assert isinstance(prepared, Ok), getattr(prepared, "diagnostics", ())
        (placement,) = prepared.value
        self.assertEqual(
            (
                CredentialReference(
                    TOKEN, credential_address(owner, TOKEN, provider="macos-keychain")
                ),
            ),
            placement.credential_addresses,
        )


if __name__ == "__main__":
    unittest.main()
