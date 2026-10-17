"""End to end: what a local promotion does, and the two things it deliberately does not do.

Product Specification 165.27 draws the line and 165.28 names it. AART owns artifact and registry
validation and preparation; existing Git hosting owns branch protection, review and merge
authorization. A local promotion or commit is *not* yet Published -- publication is presence on the
canonical consumer-visible registry branch, which a human or CI puts it there by pushing and
merging. INV-241 and INV-242 are the two halves of that, and INV-238 and INV-240 are what a
promotion has to carry to be reviewable when it gets there.

The arrangement is the real one: a maintainer's writable registry checkout, and -- separately -- the
published registry a consumer is actually subscribed to. Those are two directories because in
production they are two states of one repository separated by a push and a merge, and a test that
promoted straight into the consumer's source would be measuring a workflow nobody runs.

What is *not* measured here is the Git hop itself: no test in this repository has a Git host to push
to, which is what CP-17 exists for. So this file proves the property that makes the hop necessary --
AART leaves the maintainer's checkout with nothing committed, no branch, and no remote, and the
consumer's view does not move -- rather than the hop's outcome.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from aart_cli import cli
from aart_cli.application.maintainer_promotion import effective_policy_digest
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.protocol.hashing import sha256_bytes
from tests.maintainer_scan_cli_test import _author_checkout, _git
from tests.marketplace_lifecycle_e2e_test import _FIXTURE, _Environment
from tests.source_sync_command_e2e_test import _source_json

#: The coordinate the author checkout offers and the published registry has never heard of.
_PROMOTED = "reference/mcp/github-mcp"
#: The digests the old flags took. Nothing on the command line may stand in for the run (D-387).
_SUPPLIED = ("--validation-report", "sha256:" + "7" * 64, "--policy-result", "sha256:" + "8" * 64)


def _add_second_artifact(author: Path) -> None:
    """A second MCP beside the first, committed, so one promotion carries two Candidates."""

    package = author / "jira"
    package.mkdir()
    manifest = {
        "schema": "aart-cli.dev/mcp/v1",
        "artifact": {"name": "jira-mcp", "kind": "mcp"},
        "payload": {"include": ["server.py"]},
        "transport": {"type": "stdio"},
        "runtime": {"type": "python", "version": ">=3.11"},
        "launch": {"type": "python", "entrypoint": "server.py"},
    }
    (package / "aart-cli.json").write_text(json.dumps(manifest), encoding="utf-8")
    (package / "server.py").write_text("print('jira')\n", encoding="utf-8")
    _git(author, "add", ".")
    _git(author, "commit", "-qm", "second artifact")


def _cli(*argv: str):
    """Run the real CLI, returning ``(exit_code, parsed_json_or_text)``.

    ``SystemExit`` is caught rather than allowed to abort the test: a refusal by the argument parser
    is one of the answers this file asks for, and it arrives that way.
    """

    stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(list(argv))
    except SystemExit as exit_request:
        return int(exit_request.code or 0), None
    raw = stdout.getvalue()
    return code, (json.loads(raw) if raw.strip().startswith("{") else raw)


def _tree_digest(root: Path) -> str:
    """One digest over every tracked byte, so "unchanged" is asserted rather than sampled."""

    payload = b"".join(
        path.relative_to(root).as_posix().encode("utf-8") + b"\0" + path.read_bytes() + b"\0"
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    )
    return sha256_bytes(payload).value


def _git_text(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", "-C", str(root), *arguments), capture_output=True, text=True, check=True
    ).stdout


class PromotionPublicationBoundaryE2ETest(unittest.TestCase):
    @contextlib.contextmanager
    def _workshop(self, *, second_artifact: bool = False):
        """An author checkout, a maintainer's empty registry checkout, and a consumer's registry."""

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            author = root / "author"
            checkout = root / "checkout"
            published = root / "published"
            machine = root / "machine"
            author.mkdir()
            checkout.mkdir()
            machine.mkdir()
            _author_checkout(author)
            if second_artifact:
                _add_second_artifact(author)
            _git(checkout, "init", "-q")
            _git(checkout, "config", "user.name", "AART Test")
            _git(checkout, "config", "user.email", "aart@example.invalid")
            shutil.copytree(_FIXTURE, published)
            environment = _Environment(machine, published)
            common = [
                "--source",
                str(checkout),
                "--checkout",
                str(author),
                "--source-alias",
                "authors",
                "--source-url",
                "https://git.example/authors.git",
                "--target-registry",
                "company",
            ]
            code, scan = _cli("maintain", "upstream", "scan", *common, "--json")
            self.assertEqual(code, 0, scan)
            candidate = scan["candidates"][0]["candidate_id"]
            yield environment, checkout, published, author, common, candidate

    def _promote(self, common, candidate, *extra: str):
        return _cli(
            "maintain",
            "candidate",
            "promote",
            *common,
            "--candidate",
            candidate,
            "--json",
            *extra,
        )

    def test_a_local_promotion_says_it_neither_committed_nor_pushed(self) -> None:
        with self._workshop() as (_env, _checkout, _published, _author, common, candidate):
            code, promoted = self._promote(common, candidate, "--yes")

            self.assertEqual(code, 0, promoted)
            self.assertEqual(promoted["phase"], "promoted-local")
            self.assertTrue(promoted["applied"])
            self.assertFalse(promoted["commit"])
            self.assertFalse(promoted["push"])

    def test_it_leaves_git_with_nothing_decided(self) -> None:
        """165.27: branch protection, review and merge stay with the Git host.

        The three facts together are the boundary. No commit means no history was written; no branch
        means nothing was named for anyone to fetch; and no remote means AART did not even arrange a
        place to push -- so nothing it did can reach a consumer without a person doing it.
        """

        with self._workshop() as (_env, checkout, _published, _author, common, candidate):
            self.assertEqual(self._promote(common, candidate, "--yes")[0], 0)

            self.assertEqual(_git_text(checkout, "log", "--oneline", "--all"), "")
            self.assertEqual(_git_text(checkout, "branch", "--list"), "")
            self.assertEqual(_git_text(checkout, "remote"), "")
            # Untracked, which is what leaves the whole change for a human to stage and review.
            changed = _git_text(checkout, "status", "--porcelain").splitlines()
            self.assertTrue(changed)
            self.assertTrue(all(line.startswith("?? ") for line in changed), changed)

    def test_the_published_registry_a_consumer_reads_is_untouched(self) -> None:
        with self._workshop() as (_env, _checkout, published, _author, common, candidate):
            before = _tree_digest(published)

            self.assertEqual(self._promote(common, candidate, "--yes")[0], 0)

            self.assertEqual(_tree_digest(published), before)

    def test_the_consumer_is_offered_exactly_what_it_was_before(self) -> None:
        """The invariant an operator would notice: promoting does not publish.

        Asserted after a real re-synchronization, because "not yet visible" that only holds until
        the next sync is not a boundary at all.
        """

        with self._workshop() as (env, _checkout, _published, _author, common, candidate):
            code, before = _source_json(env, "consume", "list")
            self.assertEqual(code, 0, before)
            offered = [item["coordinate"] for item in before["artifacts"]]

            self.assertEqual(self._promote(common, candidate, "--yes")[0], 0)
            synced, report = _source_json(env, "consume", "registry", "sync")
            self.assertEqual(synced, 0, report)
            code, after = _source_json(env, "consume", "list")

            self.assertEqual(code, 0, after)
            self.assertEqual([item["coordinate"] for item in after["artifacts"]], offered)
            self.assertNotIn(_PROMOTED + "@1.0.0", offered)

    def test_installing_the_promoted_artifact_is_refused_on_the_consumer(self) -> None:
        """After a re-synchronization, so the refusal is the boundary and not a stale snapshot."""

        with self._workshop() as (env, _checkout, _published, _author, common, candidate):
            self.assertEqual(self._promote(common, candidate, "--yes")[0], 0)
            self.assertEqual(_source_json(env, "consume", "registry", "sync")[0], 0)

            code, payload = env.run("consume", "install", _PROMOTED, "--profile", "claude", "--yes")

            self.assertNotEqual(code, 0)
            self.assertEqual(payload["diagnostics"][0]["code"], "artifact-not-found")

    def test_a_review_without_yes_writes_nothing_at_all(self) -> None:
        with self._workshop() as (_env, checkout, _published, _author, common, candidate):
            before = _tree_digest(checkout)

            code, review = self._promote(common, candidate)

            self.assertEqual(code, 0, review)
            self.assertEqual(review["phase"], "review")
            self.assertFalse(review["applied"])
            self.assertEqual(_tree_digest(checkout), before)

    def test_evidence_cannot_be_supplied_on_the_command_line(self) -> None:
        """#62: any well-formed digest was accepted and written into provenance unverified.

        The evidence is the run AART does itself, exactly as the Maintainer screens do (D-387), so
        there is no flag left through which a made-up value could reach the audit record.
        """

        with self._workshop() as (_env, checkout, _published, _author, common, candidate):
            before = _tree_digest(checkout)

            code, payload = _cli(
                "maintain",
                "candidate",
                "promote",
                *common,
                "--candidate",
                candidate,
                *_SUPPLIED,
                "--json",
                "--yes",
            )

            self.assertNotEqual(code, 0)
            self.assertIsNone(payload)
            self.assertEqual(_tree_digest(checkout), before)

    def test_the_review_states_the_evidence_it_will_record(self) -> None:
        """#62: no command emitted the digests, so a CLI-only promotion had to invent them."""

        with self._workshop() as (_env, _checkout, _published, _author, common, candidate):
            code, review = self._promote(common, candidate)

            self.assertEqual(code, 0, review)
            (evidence,) = review["evidence"]
            self.assertEqual(evidence["candidate_id"], candidate)
            self.assertEqual(evidence["artifact"], "authors/mcp/github-mcp@1.0.0")
            self.assertEqual(
                evidence["effective_policy_digest"], str(effective_policy_digest(EffectivePolicy()))
            )
            self.assertRegex(evidence["validation_report_digest"], r"^sha256:[0-9a-f]{64}$")

    def test_each_candidate_records_the_run_that_judged_it(self) -> None:
        """#62: one digest pair was written into every promoted Candidate's provenance."""

        with self._workshop(second_artifact=True) as (
            _env,
            checkout,
            _published,
            _author,
            common,
            _candidate,
        ):
            code, scan = _cli("maintain", "upstream", "scan", *common, "--json")
            self.assertEqual(code, 0, scan)
            candidates = [item["candidate_id"] for item in scan["candidates"]]
            self.assertEqual(len(candidates), 2)
            selected = [argument for item in candidates for argument in ("--candidate", item)]

            code, review = _cli("maintain", "candidate", "promote", *common, *selected, "--json")
            self.assertEqual(code, 0, review)
            code, promoted = _cli(
                "maintain", "candidate", "promote", *common, *selected, "--json", "--yes"
            )
            self.assertEqual(code, 0, promoted)

            reviewed = {
                item["candidate_id"]: item["validation_report_digest"]
                for item in review["evidence"]
            }
            self.assertEqual(len(set(reviewed.values())), 2, reviewed)
            for candidate, digest in reviewed.items():
                record = json.loads(
                    (checkout / "registry" / "promotions" / f"{candidate}.json").read_text("utf-8")
                )
                self.assertEqual(record["validation_report_digest"], digest)

    def test_the_promotion_record_reconstructs_the_decision(self) -> None:
        """INV-240, against 165.26's list rather than against whatever happens to be written."""

        with self._workshop() as (_env, checkout, _published, author, common, candidate):
            _, review = self._promote(common, candidate)
            self.assertEqual(self._promote(common, candidate, "--yes")[0], 0)

            record = json.loads(
                (checkout / "registry" / "promotions" / f"{candidate}.json").read_text("utf-8")
            )

            self.assertEqual(
                record["source_provenance"],
                {
                    "git_revision": _git_text(author, "rev-parse", "HEAD").strip(),
                    "kind": "git-revision",
                },
            )
            (evidence,) = review["evidence"]
            self.assertEqual(
                record["validation_report_digest"], evidence["validation_report_digest"]
            )
            self.assertEqual(record["effective_policy_result"], evidence["effective_policy_digest"])
            self.assertEqual(record["content_mode"], "self-contained")
            self.assertNotEqual(
                record["registry_snapshot_before"], record["registry_snapshot_after"]
            )
            self.assertEqual(record["warnings"], [])

    def test_the_recorded_before_snapshot_is_the_one_the_transaction_started_from(self) -> None:
        """The chain D-104 walks backwards is only walkable if each link is the real one."""

        with self._workshop() as (_env, checkout, _published, _author, common, candidate):
            code, promoted = self._promote(common, candidate, "--yes")
            self.assertEqual(code, 0, promoted)

            record = json.loads(
                (checkout / "registry" / "promotions" / f"{candidate}.json").read_text("utf-8")
            )

            self.assertEqual(record["registry_snapshot_after"], promoted["registry_snapshot"])


if __name__ == "__main__":  # pragma: no cover - unittest entry point
    unittest.main()
