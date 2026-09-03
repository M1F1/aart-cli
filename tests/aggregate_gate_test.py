"""CP-18 — INV-077, held by running the aggregate gate rather than by reading it.

Branch protection depends on one job name, and that job's verdict is decided by a shell script
inside workflow YAML. Nothing here can run a GitHub Actions workflow, but INV-076 asks that logic
of this kind stay "runnable/testable outside GitHub Actions when practical", and this is where that
pays: the script takes its inputs from the environment and writes its verdict to an exit code, so it
runs under `bash` exactly as the runner would run it.

That matters more than it looks. INV-077 requires the aggregate to fail "when no valid gate arm ran
or when any selected arm failed", and the failure it guards against is silent by construction:
GitHub counts a *skipped* required check as satisfied, so a broken condition that skips every arm
turns branch protection into a rule that passes precisely when nothing was proven.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import textwrap
import unittest

from agent_artifacts.registry_commands.templates import (
    REGISTRY_CI_WORKFLOW,
    render_registry_readme,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
PR_CHECK = (ROOT / ".github" / "workflows" / "pr-check.yml").read_text(encoding="utf-8")


def _run_script(workflow: str, job: str) -> str:
    """The shell a job's last `run:` block holds, dedented to something `bash` will accept."""

    body = _job_body(workflow, job)
    marker = re.search(r"^(\s+)run: \|\s*$", body, re.M)
    if marker is None:
        raise AssertionError(f"job {job!r} carries no block `run:` script")
    indent = len(marker.group(1)) + 2
    lines = []
    for line in body[marker.end() :].splitlines():
        if line.strip() and len(line) - len(line.lstrip()) < indent:
            break
        lines.append(line)
    return textwrap.dedent("\n".join(lines))


def _job_body(workflow: str, job: str) -> str:
    jobs = workflow.split("\njobs:\n", 1)[1]
    collecting = False
    lines: list[str] = []
    for line in jobs.splitlines(keepends=True):
        match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if match:
            if collecting:
                break
            collecting = match.group(1) == job
            continue
        if collecting:
            lines.append(line)
    if not lines:
        raise AssertionError(f"workflow carries no job named {job!r}")
    return "".join(lines)


def _verdict(script: str, **results: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script],
        env={"PATH": "/usr/bin:/bin", **results},
        capture_output=True,
        text=True,
    )


class TheAggregateGateIsRunnableTest(unittest.TestCase):
    """The guard on everything below: an empty script would pass every verdict test."""

    def test_the_job_and_its_script_are_really_found(self) -> None:
        script = _run_script(PR_CHECK, "pr-check")
        self.assertIn("needs.gates.result", _job_body(PR_CHECK, "pr-check"))
        self.assertIn("exit 1", script)
        self.assertGreater(len(script.splitlines()), 10)

    def test_a_job_that_is_not_there_is_refused_rather_than_answered_empty(self) -> None:
        with self.assertRaises(AssertionError):
            _job_body(PR_CHECK, "no-such-job")

    def test_the_aggregate_carries_the_one_stable_name_branch_protection_can_require(self) -> None:
        """A matrix job's reported name carries its interpreter, so it is not requirable.

        `if: always()` is the other half: without it a skipped or failed dependency skips this
        job too, and GitHub reads a skipped required check as satisfied.
        """

        body = _job_body(PR_CHECK, "pr-check")
        self.assertIn("name: pr-check", body)
        self.assertIn("if: always()", body)
        self.assertIn("needs: [gates, gates-private-image]", body)


class ThePrCheckVerdictTest(unittest.TestCase):
    def setUp(self) -> None:
        self.script = _run_script(PR_CHECK, "pr-check")

    def test_the_arm_that_ran_succeeding_is_a_pass(self) -> None:
        """Exactly one arm runs; the other stands down by its own `if:`, in both directions."""

        for plain, private in (("success", "skipped"), ("skipped", "success")):
            with self.subTest(plain=plain, private=private):
                result = _verdict(self.script, PLAIN=plain, PRIVATE=private)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("all gates passed", result.stdout)

    def test_no_arm_running_at_all_fails_instead_of_looking_like_a_pass(self) -> None:
        """INV-077's "no valid gate arm ran". Both arms skipped means a broken condition.

        Without this branch the aggregate would exit 0 having proven nothing, and GitHub would
        report the required check as satisfied -- the failure mode the invariant exists for.
        """

        result = _verdict(self.script, PLAIN="skipped", PRIVATE="skipped")
        self.assertEqual(1, result.returncode)
        self.assertIn("neither gate job ran", result.stderr)

    def test_any_arm_failing_fails_the_aggregate(self) -> None:
        """INV-077's "any selected arm failed", in every shape a needs-result can take.

        `cancelled` is here because it is neither success nor failure and reads as neither: a run
        cancelled halfway proves nothing, and anything but an allowlist would let it through.
        """

        for plain, private in (
            ("failure", "skipped"),
            ("skipped", "failure"),
            ("cancelled", "skipped"),
            ("skipped", "cancelled"),
            ("success", "failure"),
        ):
            with self.subTest(plain=plain, private=private):
                result = _verdict(self.script, PLAIN=plain, PRIVATE=private)
                self.assertEqual(1, result.returncode, result.stdout)
                self.assertIn("a gate job reported", result.stderr)

    def test_the_verdict_names_both_arms_whatever_it_decides(self) -> None:
        """INV-080: a stood-down arm is visible evidence, not an absence."""

        result = _verdict(self.script, PLAIN="success", PRIVATE="skipped")
        self.assertIn("gates:               success", result.stdout)
        self.assertIn("gates-private-image: skipped", result.stdout)


class TheEmittedRegistryHasAnAggregateTooTest(unittest.TestCase):
    """The same invariant, in the CI `aart registry init` writes for somebody else.

    A registry owner protecting `main` faces exactly the situation `pr-check.yml` documents for
    this repository: the gate job is emitted in two container shapes, only one of which ever runs,
    and each is a matrix whose reported names carry a compatibility arm. There is no name that is
    the same in every configuration, so a branch-protection rule must either name an arm that this
    deployment skips -- satisfied forever, proving nothing -- or be re-edited whenever the image
    variables change.
    """

    def setUp(self) -> None:
        self.template = REGISTRY_CI_WORKFLOW.decode("utf-8")

    def test_the_template_offers_one_requirable_name(self) -> None:
        body = _job_body(self.template, "registry-quality-gate")
        self.assertIn("if: always()", body)
        self.assertIn("needs: [registry-quality, registry-quality-private-image]", body)

    def test_it_fails_when_no_arm_ran(self) -> None:
        script = _run_script(self.template, "registry-quality-gate")
        result = _verdict(script, PLAIN="skipped", PRIVATE="skipped")
        self.assertEqual(1, result.returncode)
        self.assertIn("neither", result.stderr)

    def test_it_fails_when_an_arm_failed_and_passes_when_the_arm_that_ran_succeeded(self) -> None:
        script = _run_script(self.template, "registry-quality-gate")
        self.assertEqual(1, _verdict(script, PLAIN="failure", PRIVATE="skipped").returncode)
        self.assertEqual(1, _verdict(script, PLAIN="skipped", PRIVATE="cancelled").returncode)
        self.assertEqual(0, _verdict(script, PLAIN="success", PRIVATE="skipped").returncode)
        self.assertEqual(0, _verdict(script, PLAIN="skipped", PRIVATE="success").returncode)

    def test_the_registry_readme_names_the_check_the_workflow_actually_emits(self) -> None:
        """A stable name nobody is told about protects nothing (INV-075).

        The README is the only place a registry owner is told what to require, and it is written
        by the same command that writes the workflow, so the two can drift silently. Reading the
        name out of the emitted YAML rather than repeating it here is what makes this a drift test
        instead of a second copy of the same literal.
        """

        readme = render_registry_readme("acme", "Acme").decode("utf-8")
        emitted = re.findall(r"^  ([A-Za-z0-9_-]+-gate):$", self.template, re.M)
        self.assertEqual(["registry-quality-gate"], emitted)
        self.assertIn(f"**`{emitted[0]}`**", readme)
        self.assertIn("Protecting `main`", readme)

    def test_the_gate_needs_no_container_because_it_runs_no_python(self) -> None:
        """It reads two job results. Pulling a private image to do that would make the one job
        branch protection depends on fail for a reason that has nothing to do with the gates.
        """

        body = _job_body(self.template, "registry-quality-gate")
        self.assertNotIn("container", body)
        self.assertNotIn("Provide AART", body)
