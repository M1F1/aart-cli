"""`INV-096`: a release pull request is gated on what it changes, not on everything.

A Release Please pull request rewrites four files -- the version literals and the changelog -- on a
tree that passed the full gate hours earlier. Proving it with 4,338 tests on three interpreters is
what INV-097 and INV-102 already forbid: repeating the complete suite for a tree that has passed it.

So the gate narrows. The half that makes narrowing safe is the scope check: the branch name is not
evidence, because anybody can push a commit onto the release branch. What is evidence is the diff,
so the gate reads it and refuses the narrow path for anything outside release bookkeeping (D-290).
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts import quality, release_pr_scope  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "pr-check.yml"


class SelectableGateTest(unittest.TestCase):
    def test_the_release_bump_gate_can_be_asked_for_by_name(self) -> None:
        self.assertEqual(quality.select_gates(("release-bump",)), ("release-bump",))

    def test_it_is_not_part_of_the_full_run_because_the_full_run_already_holds_it(self) -> None:
        """Every module it names is discovered by `unit`, so running both would prove one thing twice."""

        self.assertNotIn("release-bump", quality.select_gates(()))
        self.assertIn("unit", quality.select_gates(()))

    def test_it_runs_the_modules_that_prove_the_release_bookkeeping(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            gate = next(
                item
                for item in quality.build_gates(pathlib.Path(raw))
                if item.name == "release-bump"
            )

        ((command,),) = (gate.commands,)
        self.assertEqual(command[1:3], ("-m", "unittest"))
        self.assertEqual(
            set(command[3:]),
            {
                "tests.release_policy_test",
                "tests.release_test",
                "tests.packaging_test",
                "tests.install_commands_test",
            },
        )

    def test_an_unknown_gate_is_still_refused(self) -> None:
        with self.assertRaises(ValueError):
            quality.select_gates(("release-bumps",))


class ReleaseScopeTest(unittest.TestCase):
    """The diff decides, not the branch it arrived on."""

    def test_release_bookkeeping_alone_is_in_scope(self) -> None:
        self.assertEqual(
            release_pr_scope.out_of_scope(
                (
                    "pyproject.toml",
                    "aart_cli/__init__.py",
                    ".release-please-manifest.json",
                    "CHANGELOG.md",
                )
            ),
            (),
        )

    def test_anything_else_is_named_and_refused(self) -> None:
        self.assertEqual(
            release_pr_scope.out_of_scope(
                ("CHANGELOG.md", "aart_cli/domain/requirements.py", "tests/fs_test.py")
            ),
            ("aart_cli/domain/requirements.py", "tests/fs_test.py"),
        )

    def test_a_release_pull_request_that_changes_nothing_is_refused(self) -> None:
        """An empty diff means the comparison did not work, and a gate that proves nothing passes."""

        with self.assertRaises(ValueError):
            release_pr_scope.out_of_scope(())

    def test_a_path_that_merely_starts_like_one_in_scope_is_not_in_scope(self) -> None:
        self.assertEqual(
            release_pr_scope.out_of_scope(("CHANGELOG.md.bak", "pyproject.toml.orig")),
            ("CHANGELOG.md.bak", "pyproject.toml.orig"),
        )

    def test_the_script_exits_non_zero_and_names_what_it_found(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "release_pr_scope.py"), "--files"],
            input="CHANGELOG.md\naart_cli/domain/requirements.py\n",
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("aart_cli/domain/requirements.py", completed.stderr)
        self.assertNotIn("CHANGELOG.md\n", completed.stderr.split("aart_cli")[0][-30:])

    def test_the_script_accepts_a_release_bump(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "release_pr_scope.py"), "--files"],
            input="CHANGELOG.md\npyproject.toml\n",
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)


ACTION = ROOT / ".github" / "actions" / "quality" / "action.yml"
RELEASE_BRANCH = "startsWith(github.head_ref, 'release-please--')"
NARROW = "packaging-check validate docs-check release-bump"


def folded() -> str:
    """The workflow with every run of whitespace collapsed to one space.

    The conditions below are long enough to need a folded YAML scalar, and where the line breaks
    fall is the formatter's business rather than the contract's. Folding here asserts the value
    GitHub will evaluate, not the shape it is typed in.
    """

    return re.sub(r"\s+", " ", WORKFLOW.read_text(encoding="utf-8"))


class ReleasePullRequestRunsTheNarrowGateTest(unittest.TestCase):
    """The narrowing lives in the two gate jobs rather than in a third one.

    A third job would need a fourth beside it: `container.credentials` cannot be made conditional,
    which is the whole reason the gate job already appears twice. Two more jobs to express one
    condition is worse than the condition, and a fork with a private image would otherwise lose
    release gating entirely.
    """

    def test_both_gate_jobs_narrow_on_the_release_branch(self) -> None:
        self.assertEqual(
            folded().count(f"gates: >- ${{{{ {RELEASE_BRANCH} && '{NARROW}' || '' }}}}"), 2
        )

    def test_the_release_branch_runs_one_interpreter_rather_than_the_matrix(self) -> None:
        """Three interpreters catch behaviour that differs between them, in code. This changes none."""

        workflow = folded()

        self.assertEqual(
            workflow.count(
                f"python-version: >- ${{{{ fromJSON({RELEASE_BRANCH}"
                " && format('[\"{0}\"]', vars.AART_CLI_RELEASE_PYTHON_VERSION || '3.11')"
                ' || vars.AART_CLI_PYTHON_VERSIONS || \'["3.10", "3.11", "3.14"]\') }}'
            ),
            2,
        )

    def test_the_narrow_path_checks_its_own_scope_before_it_proves_anything(self) -> None:
        """The scope check is what makes a branch-name condition safe, so it runs first."""

        action = ACTION.read_text(encoding="utf-8")

        self.assertLess(
            action.index("scripts/release_pr_scope.py"), action.index("scripts/quality.py")
        )
        # It runs exactly when the job says it is a release pull request, and never otherwise.
        self.assertIn("if: inputs.scope-base != ''", action)

    def test_the_scope_check_is_given_the_base_the_pull_request_is_measured_against(self) -> None:
        workflow = folded()

        self.assertEqual(
            workflow.count(
                f"scope-base: >- ${{{{ {RELEASE_BRANCH}"
                " && github.event.pull_request.base.sha || '' }}"
            ),
            2,
        )

    def test_the_release_branch_is_checked_out_with_the_history_the_diff_needs(self) -> None:
        """Quoted, because `x && 0 || 1` yields 1 either way: 0 is falsy, so the `||` fires."""

        self.assertEqual(
            folded().count(f"fetch-depth: ${{{{ {RELEASE_BRANCH} && '0' || '1' }}}}"), 2
        )

    def test_an_ordinary_pull_request_still_runs_everything(self) -> None:
        """The gate list is empty off the release branch, and empty means the full run."""

        self.assertIn(
            "${{ inputs.python }} scripts/quality.py ${{ inputs.gates }}",
            ACTION.read_text(encoding="utf-8"),
        )
        self.assertEqual(quality.select_gates(()), quality.QUALITY_GATES)

    def test_one_required_check_still_speaks_for_every_shape(self) -> None:
        """Branch protection names `pr-check`, and the narrowing must not have changed that."""

        workflow = WORKFLOW.read_text(encoding="utf-8")
        aggregate = workflow[workflow.index("  pr-check:") :]
        self.assertIn("needs: [gates, gates-private-image]", aggregate)


if __name__ == "__main__":
    unittest.main()
