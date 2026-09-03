"""CP-15: `aart source sync` over a real source whose upstream turned invalid.

INV-218 — *invalid fetched registry state cannot replace last-known-good state* — is already held
at two seams below the CLI: `source_store_adapter_test` proves a corrupt convergent snapshot never
becomes `current`, and `source_sync_application_test` proves a validation failure publishes nothing.
Both drive the seam directly. Nothing drove `aart source sync`, the verb an operator actually runs,
over a real source that changed under it — so the invariant was held by the machinery and unproven
at the surface that uses it.

That surface is where the invariant is worth something. A refusal that leaves the store correct and
the *Marketplace* empty would satisfy every seam test above and still take the operator's registry
away; so would one that left an installation half-rebound to a snapshot that was never accepted.
These tests corrupt the upstream the way a publisher actually can — a root `aart-registry.json`
that no longer parses (`RS-08`) — run the public verb, and then ask the other public verbs what
the machine still knows.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_artifacts import cli
from agent_artifacts.io.source_store import read_current_source
from agent_artifacts.sources.model import (
    CurrentSourceRequest,
    source_instance_id,
    source_store_paths,
)
from tests.marketplace_lifecycle_e2e_test import _COORDINATE, _FIXTURE, _Environment


@contextlib.contextmanager
def _environment_over_a_writable_source():
    """The shared fixture, copied so the test can publish invalid content into it mid-run."""

    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw).resolve()
        location = root / "source"
        shutil.copytree(_FIXTURE, location)
        machine = root / "machine"
        machine.mkdir()
        yield _Environment(machine, location), location


def _source(env: _Environment, *argv: str):
    """Run a `source` verb the way an operator does, and return ``(exit_code, stdout)``.

    The lifecycle harness' own ``run`` appends ``--project`` to everything that is not user-scoped,
    because every command it was written for takes one. The source verbs do not: a configured
    source is a property of the machine, not of a project, and the parser rejects the flag. So the
    invocation is spelled out here rather than bent into a runner that assumes otherwise.
    """

    stdout = io.StringIO()
    with (
        mock.patch.dict(os.environ, env.xdg, clear=False),
        contextlib.redirect_stdout(stdout),
        mock.patch("os.getcwd", return_value=str(env.project)),
    ):
        code = cli.main(list(argv))
    return code, stdout.getvalue()


def _source_json(env: _Environment, *argv: str):
    code, raw = _source(env, *argv, "--json")
    return code, (json.loads(raw) if raw.strip() else None)


def _break_upstream(location: Path) -> None:
    """Publish a new revision that is invalid: new payload, unreadable marker (`RS-08`).

    Both halves are deliberate. The marker is what the fetch refuses on; the changed payload is
    what makes the refusal observable at all. An invalid revision that carried the same bytes as
    the good one would pass every assertion below even if it *had* replaced the store, because
    there would be nothing to tell the two snapshots apart.
    """

    (location / "aart-registry.json").write_text("{ not json", encoding="utf-8")
    (location / "artifacts" / "skill" / "code-review" / "payload" / "SKILL.md").write_text(
        "# Code Review\n\nRevision published with an unreadable registry marker.\n",
        encoding="utf-8",
    )


def _offered(payload) -> list:
    """One `marketplace list` payload's artifacts, without the health block each row repeats.

    Every row carries the same nested `source` observation, which is a live measurement rather than
    a property of the artifact. Comparing two listings across a failed sync means comparing what is
    offered; the observation is the subject of its own test below.
    """

    return [
        {key: value for key, value in item.items() if key != "source"}
        for item in payload["artifacts"]
    ]


def _current_digest(env: _Environment) -> str:
    paths = source_store_paths(env.paths.data_root, source_instance_id(env.source))
    current = read_current_source(CurrentSourceRequest(paths, env.source.alias))
    value = getattr(current, "value", None)
    assert value is not None, current
    return str(value.candidate.snapshot_digest)


class RefusedSyncKeepsLastKnownGoodTest(unittest.TestCase):
    def test_a_refused_sync_reports_the_failure_per_source_and_exits_nonzero(self) -> None:
        with _environment_over_a_writable_source() as (env, location):
            _break_upstream(location)

            code, payload = _source_json(env, "source", "sync")

            self.assertEqual(code, 1, payload)
            self.assertFalse(payload["ok"], payload)
            self.assertEqual(len(payload["sources"]), 1, payload)
            entry = payload["sources"][0]
            self.assertEqual(entry["alias"], "reference")
            self.assertFalse(entry["ok"], entry)
            self.assertTrue(entry["diagnostics"], entry)

    def test_the_refusal_carries_the_way_forward_into_the_human_rendering(self) -> None:
        """A refusal an operator cannot act on is a dead end, and `sync` is where they land."""

        with _environment_over_a_writable_source() as (env, location):
            _break_upstream(location)

            code, text = _source(env, "source", "sync")

            self.assertEqual(code, 1, text)
            self.assertIn("reference: failed", text)
            self.assertIn("remediation:", text)

    def test_the_marketplace_still_serves_the_last_good_snapshot(self) -> None:
        """The point of the invariant: a refused fetch must not take the registry away.

        Written to assert the two `marketplace list` payloads were identical, and the machine
        corrected it: they are identical in every artifact -- coordinate, lifecycle, and all three
        digests -- and differ in the health block each row carries about its source. That is the
        better answer, and the next test is the half this one stopped asserting.
        """

        with _environment_over_a_writable_source() as (env, location):
            _, before = _source_json(env, "marketplace", "list")
            good = _current_digest(env)
            _break_upstream(location)

            _source_json(env, "source", "sync")

            self.assertEqual(_current_digest(env), good)
            _, after = _source_json(env, "marketplace", "list")
            self.assertEqual(_offered(after), _offered(before))
            self.assertEqual(after["sources"][0]["snapshot_digest"], good)

    def test_a_source_that_could_not_be_checked_stops_claiming_to_be_healthy(self) -> None:
        """Serving the last-known-good snapshot is right; serving it silently is not.

        `INV-218` is about what may replace the store, and on its own it is satisfied by a machine
        that refuses the fetch and then answers every later question exactly as it did before. That
        machine is wrong in a way an operator cannot see: the content is stale by decision rather
        than by accident, and nothing on the surface says which. So the refusal has to be visible
        where the content is read, not only in the exit code of the run that made it.
        """

        with _environment_over_a_writable_source() as (env, location):
            _, before = _source_json(env, "marketplace", "list")
            self.assertEqual(before["sources"][0]["health"], "healthy")
            self.assertEqual(before["sources"][0]["diagnostics"], [])
            _break_upstream(location)

            _source_json(env, "source", "sync")

            _, after = _source_json(env, "marketplace", "list")
            self.assertEqual(after["sources"][0]["health"], "could-not-check")
            self.assertEqual(after["sources"][0]["diagnostics"], ["source-invalid"])
            # Degraded, not withdrawn: the rows are still there to install from.
            self.assertTrue(after["artifacts"], after)

    def test_an_installation_made_from_the_good_snapshot_is_untouched(self) -> None:
        """INV-210: nothing about a source going bad may secretly mutate what is installed."""

        with _environment_over_a_writable_source() as (env, location):
            env.run("marketplace", "install", _COORDINATE, "--profile", "claude", "--yes")
            installed = env.project / ".claude" / "skills" / "code-review" / "SKILL.md"
            before = installed.read_bytes()
            recorded = json.loads((env.project / ".agent-artifacts" / "manifest.json").read_text())
            _break_upstream(location)

            _source_json(env, "source", "sync")

            self.assertEqual(installed.read_bytes(), before)
            self.assertEqual(
                json.loads((env.project / ".agent-artifacts" / "manifest.json").read_text()),
                recorded,
            )
            code, status = env.run("marketplace", "status", "--profile", "claude")
            self.assertEqual(code, 0, status)
            # Not merely readable: still *current*, because the snapshot it was installed from is
            # still the one the store serves. A sync that had admitted the invalid revision would
            # leave this installation behind a version nothing ever accepted.
            self.assertEqual([item["status"] for item in status["items"]], ["current"])

    def test_installing_after_a_refused_sync_places_the_last_synced_snapshot(self) -> None:
        """Product Specification 165.11: the Marketplace may keep using the last synced snapshot.

        Not merely that the command exits zero -- that the bytes it placed are the accepted
        revision. An install that succeeded by reaching past the refusal to the invalid upstream
        would be the exact failure `INV-218` names, wearing a zero exit code.
        """

        with _environment_over_a_writable_source() as (env, location):
            good = (
                location / "artifacts" / "skill" / "code-review" / "payload" / "SKILL.md"
            ).read_bytes()
            _break_upstream(location)
            _source_json(env, "source", "sync")

            code, payload = env.run(
                "marketplace", "install", _COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, payload)
            placed = env.project / ".claude" / "skills" / "code-review" / "SKILL.md"
            self.assertEqual(placed.read_bytes(), good)

    def test_update_after_a_refused_sync_is_a_no_op_rather_than_a_refusal(self) -> None:
        """The half that hurt: `prepare_update` refused, so there was no way back but uninstall.

        The refusal was not even a diagnostic. The plan for a source in this state could not be
        constructed at all, so the operator got `canonical install plan is not exactly
        review-bound` with no remediation on it.
        """

        with _environment_over_a_writable_source() as (env, location):
            env.run("marketplace", "install", _COORDINATE, "--profile", "claude", "--yes")
            _break_upstream(location)
            _source_json(env, "source", "sync")

            code, payload = env.run("marketplace", "update", "--profile", "claude", "--yes")

            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["session_status"], "no-op")
            self.assertEqual([item["status"] for item in payload["items"]], ["current"])

    def test_a_repaired_upstream_synchronizes_again(self) -> None:
        """The counterpart: the refusal was about the content, not about `sync` being inert."""

        with _environment_over_a_writable_source() as (env, location):
            good = _current_digest(env)
            _break_upstream(location)
            self.assertEqual(_source_json(env, "source", "sync")[0], 1)
            (location / "aart-registry.json").unlink()
            (location / "artifacts" / "skill" / "code-review" / "payload" / "SKILL.md").write_text(
                "# Code Review\n\nSecond revision.\n", encoding="utf-8"
            )

            code, payload = _source_json(env, "source", "sync")

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["ok"], payload)
            self.assertEqual(payload["sources"][0]["disposition"], "published")
            self.assertEqual(payload["sources"][0]["snapshot_digest"], _current_digest(env))
            self.assertNotEqual(_current_digest(env), good)


if __name__ == "__main__":
    unittest.main()
