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

from agent_artifacts import cli
from agent_artifacts.protocol.hashing import sha256_bytes
from tests.maintainer_scan_cli_test import _author_checkout, _git
from tests.marketplace_lifecycle_e2e_test import _FIXTURE, _Environment
from tests.source_sync_command_e2e_test import _source_json

#: The coordinate the author checkout offers and the published registry has never heard of.
_PROMOTED = "reference/mcp/github-mcp"
_EVIDENCE = ("--validation-report", "sha256:" + "7" * 64, "--policy-result", "sha256:" + "8" * 64)


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
    def _workshop(self):
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
            code, scan = _cli("registry", "scan", *common, "--json")
            self.assertEqual(code, 0, scan)
            candidate = scan["candidates"][0]["candidate_id"]
            yield environment, checkout, published, author, common, candidate

    def _promote(self, common, candidate, *extra: str):
        return _cli(
            "registry",
            "promote",
            *common,
            "--candidate",
            candidate,
            *_EVIDENCE,
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
            code, before = _source_json(env, "marketplace", "list")
            self.assertEqual(code, 0, before)
            offered = [item["coordinate"] for item in before["artifacts"]]

            self.assertEqual(self._promote(common, candidate, "--yes")[0], 0)
            synced, report = _source_json(env, "source", "sync")
            self.assertEqual(synced, 0, report)
            code, after = _source_json(env, "marketplace", "list")

            self.assertEqual(code, 0, after)
            self.assertEqual([item["coordinate"] for item in after["artifacts"]], offered)
            self.assertNotIn(_PROMOTED + "@1.0.0", offered)

    def test_installing_the_promoted_artifact_is_refused_on_the_consumer(self) -> None:
        """After a re-synchronization, so the refusal is the boundary and not a stale snapshot."""

        with self._workshop() as (env, _checkout, _published, _author, common, candidate):
            self.assertEqual(self._promote(common, candidate, "--yes")[0], 0)
            self.assertEqual(_source_json(env, "source", "sync")[0], 0)

            code, payload = env.run(
                "marketplace", "install", _PROMOTED, "--profile", "claude", "--yes"
            )

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

    def test_promotion_without_its_evidence_is_refused(self) -> None:
        """INV-238: the evidence a promotion carries comes from the caller's policy run.

        AART neither runs the enterprise's validation nor decides what would satisfy it -- it
        records the digests of what did. Which is why it cannot proceed without them.
        """

        # Each digest is asserted on its own, in its own workshop: supplying one and omitting the
        # other has to be refused too, or "requires its evidence" would still hold with either half
        # made optional -- and a shared checkout would let the first refusal mask the second.
        for omitted, kept in ((_EVIDENCE[:2], _EVIDENCE[2:]), (_EVIDENCE[2:], _EVIDENCE[:2])):
            with (
                self.subTest(omitted=omitted[0]),
                self._workshop() as (
                    _env,
                    checkout,
                    _published,
                    _author,
                    common,
                    candidate,
                ),
            ):
                before = _tree_digest(checkout)

                code, payload = _cli(
                    "registry",
                    "promote",
                    *common,
                    "--candidate",
                    candidate,
                    *kept,
                    "--json",
                    "--yes",
                )

                self.assertNotEqual(code, 0)
                self.assertIsNone(payload)
                self.assertEqual(_tree_digest(checkout), before)

    def test_the_promotion_record_reconstructs_the_decision(self) -> None:
        """INV-240, against 165.26's list rather than against whatever happens to be written."""

        with self._workshop() as (_env, checkout, _published, author, common, candidate):
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
            self.assertEqual(record["validation_report_digest"], _EVIDENCE[1])
            self.assertEqual(record["effective_policy_result"], _EVIDENCE[3])
            self.assertEqual(record["promotion_mode"], "vendored")
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
