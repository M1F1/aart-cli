"""CP-19 step 7: a safe Registry-baseline refusal names the state behind it.

The exact snapshot comparison is deliberately not under test as something to relax.  These tests
put four different real Git states behind the same mismatch and require the configured promotion
surface to tell an operator which recovery applies.  A generic ``synchronize or restore`` answer
cannot safely distinguish an intentional promotion awaiting publication from disposable drift.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest import TestCase, mock

from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.registry import PromotionMode
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.candidate_store import candidate_history_paths, read_candidate_history
from agent_artifacts.io.maintainer_promotion import prepare_configured_candidate_promotion
from agent_artifacts.io.maintainer_sync import (
    complete_configured_source_sync,
    prepare_configured_source_sync,
)
from agent_artifacts.sources.model import source_instance_id, source_store_paths
from tests.authoring_source_admission_e2e_test import (
    _effective,
    _Environment,
    _environment,
    _git,
)


def _candidate(env: _Environment):
    env.synchronize_registry()
    code, payload = env.add_author_source()
    assert code == 0, payload
    with mock.patch(
        "agent_artifacts.sources.runtime.acquire_git_snapshot",
        side_effect=env._local_transport,
    ):
        prepared = prepare_configured_source_sync(
            _effective(env),
            SourceAlias("superpowers"),
            data_root=env.paths.data_root,
        )
        assert isinstance(prepared, Ok), prepared
        completed = complete_configured_source_sync(
            _effective(env),
            prepared.value,
            reviewed_digest=prepared.value.review_digest,
        )
    assert isinstance(completed, Ok), completed
    source = next(
        item
        for item in _effective(env).configuration.sources
        if item.alias == SourceAlias("superpowers")
    )
    history = read_candidate_history(
        candidate_history_paths(source_store_paths(env.paths.data_root, source_instance_id(source)))
    )
    assert isinstance(history, Ok) and history.value is not None, history
    return history.value.active[0].candidate.id


def _prepare(env: _Environment, candidate_id, root: Path | None = None) -> Err:
    result = prepare_configured_candidate_promotion(
        _effective(env),
        candidate_id,
        data_root=env.paths.data_root,
        registry_root=str(root or env.registry),
        policy=EffectivePolicy(),
        mode=PromotionMode.VENDORED,
    )
    assert isinstance(result, Err), result
    return result


def _words(result: Err) -> str:
    diagnostic = result.diagnostics[0]
    return " ".join((diagnostic.message, *diagnostic.remediation)).casefold()


def _change_registry(root: Path, display_name: str) -> None:
    marker = root / "aart-registry.json"
    document = json.loads(marker.read_text(encoding="utf-8"))
    document["display_name"] = display_name
    marker.write_text(json.dumps(document, sort_keys=True) + "\n", encoding="utf-8")


class RegistryBaselineDiagnosisTest(TestCase):
    def test_a_clean_local_commit_ahead_of_the_approved_revision_is_unpublished_work(self) -> None:
        with _environment() as env:
            candidate_id = _candidate(env)
            _change_registry(env.registry, "Awaiting Review")
            _git(env.registry, "add", "aart-registry.json")
            _git(env.registry, "commit", "-m", "prior registry promotion")

            words = _words(_prepare(env, candidate_id))

            self.assertIn("unpublished", words)
            self.assertIn("review", words)
            self.assertIn("merge", words)
            self.assertIn("update", words)
            self.assertIn("synchronize", words)
            self.assertNotIn("aart ", words)

    def test_a_clean_checkout_behind_the_approved_revision_is_stale(self) -> None:
        with _environment() as env:
            old = _git(env.registry, "rev-parse", "HEAD")
            _change_registry(env.registry, "Published Registry")
            _git(env.registry, "add", "aart-registry.json")
            _git(env.registry, "commit", "-m", "published registry change")
            candidate_id = _candidate(env)
            _git(env.registry, "checkout", "--detach", old)

            words = _words(_prepare(env, candidate_id))

            self.assertIn("behind", words)
            self.assertIn("published", words)
            self.assertIn("update", words)
            self.assertNotIn("aart ", words)

    def test_uncommitted_registry_drift_is_not_described_as_unpublished_work(self) -> None:
        with _environment() as env:
            candidate_id = _candidate(env)
            _change_registry(env.registry, "Uncommitted Registry")

            words = _words(_prepare(env, candidate_id))

            self.assertIn("uncommitted", words)
            self.assertIn("review", words)
            self.assertNotIn("unpublished", words)
            self.assertNotIn("aart ", words)

    def test_a_different_git_repository_is_named_as_the_wrong_workspace(self) -> None:
        with _environment() as env:
            candidate_id = _candidate(env)
            wrong = env.root / "other-registry"
            shutil.copytree(env.registry, wrong, ignore=shutil.ignore_patterns(".git"))
            _git(wrong, "init", "-b", "main")
            _git(wrong, "config", "user.email", "test@example.invalid")
            _git(wrong, "config", "user.name", "AART Test")
            _git(wrong, "remote", "add", "origin", "https://git.example/other.git")
            _change_registry(wrong, "Other Registry")
            _git(wrong, "add", "-A")
            _git(wrong, "commit", "-m", "other registry")

            words = _words(_prepare(env, candidate_id, wrong))

            self.assertIn("different git repository", words)
            self.assertIn("configured registry", words)
            self.assertNotIn("aart ", words)


if __name__ == "__main__":
    import unittest

    unittest.main()
