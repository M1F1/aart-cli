"""B-094/QA-020: a real authoring Git repository enters the monitored Source flow.

The accepted flow is Product Specification 72.1 and 164.2 read end to end:

```text
Git author repository
        -> explicit aart.yaml/aart.json discovery
        -> Candidate
        -> selected promotion
        -> Registry
        -> later Source Sync reports upstream movement
```

Its public entrance is `aart source add --kind source-git`. Until B-094 that entrance validated
every acquired tree through `load_native_source`, the loader for a *consumer* native package
tree: a root `aart-source.json` plus `<root>/<kind>/<name>/artifact.json` and `payload/`. An
authoring repository declares none of that -- it declares one `aart.yaml` next to the files that
manifest names -- so it was refused before manifest discovery could run, and INV-201's "no
manifest = no candidate" rule never got the chance to say yes to a manifest that was there.

These tests use a real temporary Git repository, the real acquisition adapter and the real public
command. The transport is substituted only *after* the production code has built its own request,
and `_assert_remote_request` fails the test if that request was weakened to get there -- the
refusal being removed is an admission refusal, and no test here may pass by relaxing transport.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from agent_artifacts import cli
from agent_artifacts.configuration.model import (
    ConfiguredSource,
    OrganizationPolicy,
    ReportingSettings,
    SourceAlias,
    SourceKind,
    SyncSettings,
    UserConfiguration,
)
from agent_artifacts.configuration.paths import Platform, resolve_config_paths
from agent_artifacts.configuration.policy import RuntimeOverrides, apply_configuration
from agent_artifacts.configuration.schema import (
    parse_user_configuration,
    user_configuration_bytes,
)
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.registry import PromotionMode
from agent_artifacts.domain.result import Ok
from agent_artifacts.io.candidate_store import candidate_history_paths, read_candidate_history
from agent_artifacts.io.maintainer_promotion import (
    complete_configured_candidate_promotion,
    prepare_configured_candidate_promotion,
)
from agent_artifacts.io.maintainer_sync import (
    complete_configured_source_sync,
    prepare_configured_source_sync,
)
from agent_artifacts.io.registry_promotion import FilesystemPromotionOutput
from agent_artifacts.sources.git import acquire_git_snapshot
from agent_artifacts.sources.model import (
    GitSnapshotRequest,
    source_instance_id,
    source_store_paths,
)
from tests.git_backed_consumer_e2e_test import _materialize, _registry_snapshot

AUTHOR_LOCATION = "https://git.example/superpowers.git"
SKILL_MANIFEST = """schema: aart.dev/skill/v1
artifact:
  name: verification-before-completion
  kind: skill
  version: 1.0.0
payload:
  include:
    - SKILL.md
compatibility:
  harnesses:
    - claude
"""
SKILL_BODY = "# Verification before completion\n\nCheck the work before calling it done.\n"
UPDATED_SKILL_BODY = "# Verification before completion\n\nCheck it twice.\n"


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


class _AuthoringRepository:
    """A real Git repository shaped like the authoring repositories the acceptance run uses.

    Nothing here is an AART package: there is no `aart-source.json`, no `artifact.json` and no
    `payload/` directory. There is one explicit `aart.yaml` inside the directory it describes,
    which is exactly what 72.1 says an author opts in with, plus one unrelated file so that
    "discovery finds only the manifest" is a claim with something to be wrong about.
    """

    def __init__(self, root: Path) -> None:
        self.path = root / "superpowers"
        self.skill = self.path / "skills" / "verification-before-completion"
        self.skill.mkdir(parents=True)
        (self.skill / "aart.yaml").write_text(SKILL_MANIFEST, encoding="utf-8")
        (self.skill / "SKILL.md").write_text(SKILL_BODY, encoding="utf-8")
        (self.path / "README.md").write_text("# Superpowers\n", encoding="utf-8")
        _git(self.path, "init", "-b", "main")
        _git(self.path, "config", "user.email", "test@example.invalid")
        _git(self.path, "config", "user.name", "AART Test")
        _git(self.path, "add", "-A")
        _git(self.path, "commit", "-m", "author the skill")
        self.head = _git(self.path, "rev-parse", "HEAD")

    def publish(self, body: str) -> str:
        """Move the upstream the way an author's later commit does."""

        (self.skill / "SKILL.md").write_text(body, encoding="utf-8")
        _git(self.path, "add", "-A")
        _git(self.path, "commit", "-m", "revise the skill")
        self.head = _git(self.path, "rev-parse", "HEAD")
        return self.head


class _Environment:
    """An isolated machine with one approved registry and one authoring repository to add."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.home = root / "home"
        self.project = root / "project"
        self.home.mkdir()
        self.project.mkdir()
        self.author = _AuthoringRepository(root)

        self.registry = root / "registry"
        _materialize(self.registry, _registry_snapshot())
        _git(self.registry, "init", "-b", "main")
        _git(self.registry, "config", "user.email", "test@example.invalid")
        _git(self.registry, "config", "user.name", "AART Test")
        _git(self.registry, "add", "-A")
        _git(self.registry, "commit", "-m", "approved registry")

        self.xdg = {
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_DATA_HOME": str(self.home / ".local/share"),
            "XDG_CACHE_HOME": str(self.home / ".cache"),
        }
        platform = Platform.DARWIN if sys.platform == "darwin" else Platform.LINUX
        self.paths = resolve_config_paths(
            platform,
            home=str(self.home),
            xdg_config_home=self.xdg["XDG_CONFIG_HOME"],
            xdg_data_home=self.xdg["XDG_DATA_HOME"],
            xdg_cache_home=self.xdg["XDG_CACHE_HOME"],
        )
        self.registry_source = ConfiguredSource(
            SourceAlias("company"),
            SourceKind.REGISTRY_GIT,
            "https://git.example/registry.git",
            "main",
            True,
        )
        config_path = Path(self.paths.user_config_file)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_bytes(
            user_configuration_bytes(
                UserConfiguration(
                    1,
                    (self.registry_source,),
                    self.registry_source.alias,
                    SyncSettings(),
                    ReportingSettings(),
                )
            )
        )
        self.requests: list[GitSnapshotRequest] = []

    def _local_transport(self, request: GitSnapshotRequest):
        """Stand in for the unavailable network, after the production verdict built its request."""

        self.requests.append(request)
        self._assert_remote_request(request)
        repository = self.author.path if request.location == AUTHOR_LOCATION else self.registry
        return acquire_git_snapshot(
            replace(request, location=repository.as_uri(), allow_local_transport=True)
        )

    def _assert_remote_request(self, request: GitSnapshotRequest) -> None:
        if request.allow_local_transport:
            raise AssertionError(f"public path weakened its transport request: {request!r}")

    def run(self, *argv: str):
        output = io.StringIO()
        with (
            mock.patch.dict(os.environ, self.xdg, clear=False),
            contextlib.redirect_stdout(output),
            mock.patch("os.getcwd", return_value=str(self.project)),
            mock.patch(
                "agent_artifacts.sources.runtime.acquire_git_snapshot",
                side_effect=self._local_transport,
            ),
        ):
            code = cli.main([*argv, "--json"])
        raw = output.getvalue()
        return code, (json.loads(raw) if raw.strip() else None)

    def synchronize_registry(self):
        """Source Sync compares Candidates against an approved registry, so give it one."""

        code, payload = self.run("source", "sync")
        assert code == 0, payload
        return payload

    def add_author_source(self, alias: str = "superpowers"):
        return self.run(
            "source",
            "add",
            "--alias",
            alias,
            "--kind",
            "source-git",
            "--location",
            AUTHOR_LOCATION,
            "--ref",
            "main",
        )


def _effective(env: "_Environment"):
    """The configuration the machine really has, read back the way every command reads it."""

    raw = Path(env.paths.user_config_file).read_bytes()
    parsed = parse_user_configuration(raw)
    assert isinstance(parsed, Ok), parsed
    effective = apply_configuration(parsed.value, RuntimeOverrides(), OrganizationPolicy(1))
    assert isinstance(effective, Ok), effective
    return effective.value


@contextlib.contextmanager
def _environment():
    with tempfile.TemporaryDirectory() as raw:
        yield _Environment(Path(raw).resolve())


class AuthoringSourceAdmissionTest(unittest.TestCase):
    """The public entrance to the monitored flow admits an explicit authoring repository."""

    def test_a_repository_whose_only_declaration_is_aart_yaml_is_admitted(self) -> None:
        with _environment() as env:
            code, payload = env.add_author_source()

            self.assertEqual(code, 0, payload)
            assert payload is not None
            self.assertEqual(payload["source"]["alias"], "superpowers")
            self.assertEqual(payload["source"]["kind"], "source-git")
            self.assertEqual(payload["source"]["location"], AUTHOR_LOCATION)

    def test_the_admitted_source_pins_the_real_commit_the_author_repository_is_at(self) -> None:
        with _environment() as env:
            code, payload = env.add_author_source()

            self.assertEqual(code, 0, payload)
            assert payload is not None
            self.assertEqual(payload["source"]["resolved_revision"], env.author.head)

    def test_the_identity_of_a_source_that_declares_none_is_its_alias(self) -> None:
        """An authoring repository declares no identity, so the subscription supplies one.

        This value is not cosmetic: `declared_source_id` is what the identity-transition check
        compares on every later sync, so a value derived from anything that moves would make an
        ordinary upstream commit look like the Source becoming a different Source.
        """

        with _environment() as env:
            code, payload = env.add_author_source(alias="superpowers")

            self.assertEqual(code, 0, payload)
            assert payload is not None
            self.assertEqual(payload["source"]["source_id"], "superpowers")

    def test_a_second_add_of_a_moved_upstream_is_not_read_as_a_changed_identity(self) -> None:
        with _environment() as env:
            self.assertEqual(env.add_author_source()[0], 0)
            env.author.publish(UPDATED_SKILL_BODY)

            code, payload = env.run("source", "sync", "--alias", "superpowers")

            self.assertEqual(code, 0, payload)
            assert payload is not None
            (listed,) = [item for item in payload["sources"] if item["alias"] == "superpowers"]
            self.assertEqual(listed["source_id"], "superpowers")
            self.assertEqual(listed["resolved_revision"], env.author.head)

    def test_the_admitted_source_is_listed_as_a_configured_authoring_source(self) -> None:
        with _environment() as env:
            self.assertEqual(env.add_author_source()[0], 0)

            code, payload = env.run("source", "list")

            self.assertEqual(code, 0, payload)
            assert payload is not None
            listed = {item["alias"]: item for item in payload["sources"]}
            self.assertIn("superpowers", listed)
            self.assertEqual(listed["superpowers"]["kind"], "source-git")

    def test_a_repository_that_declares_no_manifest_at_all_is_still_refused(self) -> None:
        """INV-201 in the direction that keeps it a rule: no manifest, no Source.

        Admission widening is only safe if it widened to *explicit declaration* rather than to
        "any Git repository". Without this the change above would read as "authoring sources are
        never validated", which is a different product.
        """

        with _environment() as env:
            (env.author.skill / "aart.yaml").unlink()
            _git(env.author.path, "add", "-A")
            _git(env.author.path, "commit", "-m", "remove the manifest")

            code, payload = env.add_author_source()

            self.assertNotEqual(code, 0, payload)

    def test_a_committed_symlink_is_refused_by_name_with_a_safe_correction(self) -> None:
        """`QA-019`/`D-183`: the refusal is unchanged; what it says is not.

        The real Superpowers fork had a root `AGENTS.md` committed as a symbolic link, and the
        public refusal was `Git tree contains an unsafe entry: 'AGENTS.md'` — true, fail-closed and
        useless, because the operator could not tell a link from a submodule from a bad path and so
        could not choose a correction. The link target is still never named: it has not passed the
        repository's path-safety rules.
        """

        with _environment() as env:
            (env.author.path / "AGENTS.md").symlink_to("README.md")
            _git(env.author.path, "add", "-A")
            _git(env.author.path, "commit", "-m", "link AGENTS.md at CLAUDE.md")

            code, payload = env.add_author_source()

            self.assertNotEqual(code, 0, payload)
            diagnostic = payload["diagnostics"][0]
            # The message itself has to name the kind: asserting over the whole envelope would
            # pass on the word "symlinks" inside the remediation, which is the mutation that
            # found this test asserting less than it says.
            self.assertIn("symbolic link", diagnostic["message"])
            self.assertIn("AGENTS.md", diagnostic["message"])
            self.assertIn("regular file", " ".join(diagnostic["remediation"]))
            self.assertNotIn("README.md", json.dumps(payload))

    def test_admission_never_weakened_the_transport_it_asked_for(self) -> None:
        with _environment() as env:
            env.add_author_source()

            self.assertTrue(env.requests)
            for request in env.requests:
                self.assertFalse(request.allow_local_transport)
                self.assertEqual(request.location, AUTHOR_LOCATION)


class AuthoringSourceIsNotAMarketplaceTest(unittest.TestCase):
    """INV-199: a Source of Candidates is not consumer-visible Marketplace content.

    An authoring repository holds compiled *Candidates*. Nothing in it is approved, so nothing in
    it may appear in the consumer Marketplace -- and, just as importantly, its presence may not
    take the Marketplace away either. Both halves are one claim about the same projection.
    """

    def test_the_consumer_marketplace_still_answers_after_an_authoring_source_is_added(
        self,
    ) -> None:
        with _environment() as env:
            before_code, before = env.run("marketplace", "list")
            self.assertEqual(before_code, 0, before)

            self.assertEqual(env.add_author_source()[0], 0)
            after_code, after = env.run("marketplace", "list")

            self.assertEqual(after_code, 0, after)
            assert before is not None and after is not None
            self.assertEqual(
                [item["coordinate"] for item in after["artifacts"]],
                [item["coordinate"] for item in before["artifacts"]],
            )


class MonitoredSourceFlowTest(unittest.TestCase):
    """Source -> Candidate -> upstream movement, over the source the public command admitted.

    Admission on its own is not the claim B-094 makes; it is the door the claim walks through.
    These drive the same configured composition the Maintainer Source Sync screens call, over
    the durable store `aart source add` just wrote, so what is proven is the real monitored flow
    rather than a compiled snapshot handed to a fixture.
    """

    def _prepare(self, env: _Environment, alias: str = "superpowers"):
        effective = _effective(env)
        return prepare_configured_source_sync(
            effective,
            SourceAlias(alias),
            data_root=env.paths.data_root,
            offline=False,
        )

    def _sync(self, env: _Environment, alias: str = "superpowers"):
        """One reviewed Source Sync, exactly as the screen performs it: prepare then confirm."""

        with mock.patch(
            "agent_artifacts.sources.runtime.acquire_git_snapshot",
            side_effect=env._local_transport,
        ):
            prepared = self._prepare(env, alias)
            assert isinstance(prepared, Ok), prepared
            completed = complete_configured_source_sync(
                _effective(env),
                prepared.value,
                reviewed_digest=prepared.value.review_digest,
            )
        assert isinstance(completed, Ok), completed
        return completed.value

    def test_sync_compiles_exactly_the_one_declared_manifest_into_a_candidate(self) -> None:
        with _environment() as env:
            env.synchronize_registry()
            self.assertEqual(env.add_author_source()[0], 0)

            result = self._sync(env)

            self.assertEqual(result.scan.manifest_count, 1)
            self.assertEqual(
                [item.candidate.artifact.coordinate.artifact.name for item in result.scan.active],
                ["verification-before-completion"],
            )
            self.assertEqual(result.scan.revision, env.author.head)

    def test_the_unrelated_files_beside_the_manifest_are_not_artifacts(self) -> None:
        """INV-201: README.md and every other file are evidence of nothing on their own."""

        with _environment() as env:
            env.synchronize_registry()
            self.assertEqual(env.add_author_source()[0], 0)

            result = self._sync(env)

            self.assertEqual(len(result.scan.active), 1)
            payload = {
                str(entry.path) for entry in result.scan.active[0].artifact.canonical_entries
            }
            self.assertNotIn("README.md", payload)

    def test_the_candidate_is_durable_and_a_later_upstream_commit_is_reported_as_movement(
        self,
    ) -> None:
        with _environment() as env:
            env.synchronize_registry()
            self.assertEqual(env.add_author_source()[0], 0)
            first = self._sync(env)
            first_digest = first.scan.active[0].candidate.canonical_digest

            moved = env.author.publish(UPDATED_SKILL_BODY)
            second = self._sync(env)

            self.assertNotEqual(moved, first.scan.revision)
            self.assertEqual(second.scan.revision, moved)
            self.assertEqual(len(second.scan.active), 1)
            self.assertNotEqual(second.scan.active[0].candidate.canonical_digest, first_digest)

    def test_the_candidate_history_survives_into_a_freshly_read_store(self) -> None:
        """The Maintainer screens read history from disk, not from the object that wrote it."""

        with _environment() as env:
            env.synchronize_registry()
            self.assertEqual(env.add_author_source()[0], 0)
            self._sync(env)

            source = next(
                item
                for item in _effective(env).configuration.sources
                if item.alias == SourceAlias("superpowers")
            )
            paths = source_store_paths(env.paths.data_root, source_instance_id(source))
            history = read_candidate_history(candidate_history_paths(paths))

            self.assertIsInstance(history, Ok)
            assert isinstance(history, Ok) and history.value is not None
            self.assertEqual(
                [item.candidate.artifact.coordinate.artifact.name for item in history.value.active],
                ["verification-before-completion"],
            )


class PromotionFromAnAdmittedGitSourceTest(unittest.TestCase):
    """The last leg: a Candidate compiled from the admitted repository becomes Registry content.

    Promotion machinery is Candidate-shaped and does not know which source kind produced one, so
    this is not re-proving promotion. It is proving that what a real authoring *Git* repository
    now yields is a Candidate promotion accepts -- the join B-094 broke, checked at the join.
    """

    def test_the_selected_candidate_is_written_into_the_local_approved_registry(self) -> None:
        with _environment() as env:
            env.synchronize_registry()
            self.assertEqual(env.add_author_source()[0], 0)
            with mock.patch(
                "agent_artifacts.sources.runtime.acquire_git_snapshot",
                side_effect=env._local_transport,
            ):
                prepared_sync = prepare_configured_source_sync(
                    _effective(env),
                    SourceAlias("superpowers"),
                    data_root=env.paths.data_root,
                )
                assert isinstance(prepared_sync, Ok), prepared_sync
                synced = complete_configured_source_sync(
                    _effective(env),
                    prepared_sync.value,
                    reviewed_digest=prepared_sync.value.review_digest,
                )
            assert isinstance(synced, Ok), synced
            candidate_id = synced.value.scan.active[0].candidate.id

            checkout = str(env.registry)
            before = FilesystemPromotionOutput(checkout).current()
            assert isinstance(before, Ok), before
            self.assertFalse(
                [
                    entry
                    for entry in before.value.entries
                    if "verification-before-completion" in str(entry.path)
                ],
                "the registry already held the artifact, so writing it proves nothing",
            )

            prepared = prepare_configured_candidate_promotion(
                _effective(env),
                candidate_id,
                data_root=env.paths.data_root,
                registry_root=checkout,
                policy=EffectivePolicy(),
                mode=PromotionMode.VENDORED,
            )
            self.assertIsInstance(prepared, Ok, prepared)
            assert isinstance(prepared, Ok)
            completed = complete_configured_candidate_promotion(
                _effective(env),
                prepared.value,
                reviewed_digest=prepared.value.transaction.review_digest,
                registry_root=checkout,
            )

            self.assertIsInstance(completed, Ok, completed)
            written = FilesystemPromotionOutput(checkout).current()
            assert isinstance(written, Ok), written
            self.assertTrue(
                any(
                    "verification-before-completion" in str(entry.path)
                    for entry in written.value.entries
                ),
                "the promoted artifact is absent from the approved registry it was written into",
            )
