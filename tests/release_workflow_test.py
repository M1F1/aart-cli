from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ReleaseWorkflowTest(unittest.TestCase):
    def test_the_release_run_proves_only_what_has_the_release_as_its_subject(self) -> None:
        """The ten source gates ran on the pull request; the tag run does not repeat them.

        Nothing reaches `main` except through a pull request that passed all ten gates on the full
        interpreter matrix, so re-running them at the tag proved the same tree a second time.  What
        stays is everything the pull request could not have proven: the tag matches the source
        version, the tagged commit is in `main`, the checklist passes, and the wheel itself is
        sound.
        See docs/ci/pr-check-and-release-split-v1.md.
        """

        workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

        # No source-gate matrix here any more, on either spelling.  These two are what a
        # reinstated quality job would bring back with it, so their absence is the contract.
        self.assertNotIn("AART_PYTHON_VERSIONS", workflow)
        self.assertNotIn("uses: ./.github/actions/quality", workflow)
        # No default here on purpose: the variable's presence is what decides whether the
        # reconciliation runs.  `enterprise_ci_template_test` holds that contract.
        self.assertIn("REFERENCE_REGISTRY_URL: ${{ vars.AART_REFERENCE_REGISTRY_URL }}", workflow)
        # The run reads history: it proves the tagged commit is an ancestor of `main`.
        self.assertIn("fetch-depth: 0", workflow)

        # Each job appears once per container shape, so its steps live in a composite action
        # rather than in two copies that can drift apart.  The checklist is what matters, and
        # this is where it now is.
        actions = ROOT / ".github" / "actions"
        release_steps = (actions / "release" / "action.yml").read_text(encoding="utf-8")
        # Both invocations, because the reconciliation is now a choice the variable makes and a
        # test that saw only one branch would not notice the other disappearing.
        self.assertIn("scripts/release.py check --registry", release_steps)
        self.assertIn("scripts/release.py check --without-registry", release_steps)
        # The subject of a release run is the artifact, not a version somebody maintained: the
        # wheel is checked against the tag it is published under.  See INV-097, INV-098, INV-099.
        self.assertIn("scripts/release_artifact.py --tag", release_steps)
        # And what that replaced is gone rather than deprecated.
        self.assertNotIn("scripts/version.py", release_steps)
        self.assertNotIn("github-release-", release_steps)
        # The one gate that stays.  Its subject is the wheel, not the source, so the pull request
        # that proved the source did not prove it.
        self.assertIn("scripts/packaging_check.py", release_steps)
        # CI calls the canonical runners directly.  The Makefile targets are one-line wrappers
        # around exactly these commands, so going through `make` bought nothing and made GNU Make
        # a thing every CI image had to carry -- which is how a real Enterprise image failed.
        self.assertNotIn("make ", release_steps)
        # No workflow-artifact copy of the wheel, on either spelling.  An Enterprise instance
        # cannot run `upload-artifact@v4` -- `GHESNotSupportedError` at run time -- and github.com
        # refuses `@v3` while *resolving* the action, before any `if:` is evaluated, so naming it
        # failed a run that would never have executed the step.  Measured on both hosts.  The
        # wheel is attached to the release, which is where anyone installing it looks.
        self.assertNotIn("uses: actions/upload-artifact", release_steps)
        self.assertNotIn("inputs.artifact-v4", release_steps)
        self.assertNotIn("AART_ARTIFACT_V4", workflow)
        self.assertIn(
            "git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main",
            release_steps,
        )
        self.assertIn('git merge-base --is-ancestor "$TAG_COMMIT" origin/main', release_steps)

    def test_the_release_run_is_reachable_from_the_release_the_engine_creates(self) -> None:
        """GitHub raises no workflow event for anything done with the repository token.

        So the tag and the release that `release-please.yml` creates start nothing, and a release
        run that waits for an event would wait forever.  The release workflow is therefore
        callable, and the release-please run calls it -- the same answer the retired button
        needed, kept after the button went.
        """

        release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
        please = (ROOT / ".github/workflows/release-please.yml").read_text(encoding="utf-8")

        self.assertIn("  workflow_call:", release)
        self.assertIn("uses: ./.github/workflows/release.yml", please)
        self.assertIn("if: needs.release-please.outputs.released == 'true'", please)
        # Called or triggered, the run has to know which tag it is about.
        self.assertIn(
            "tag: ${{ inputs.tag || github.event.release.tag_name || github.ref_name }}", release
        )

    def test_the_pull_request_title_is_checked_as_the_input_it_becomes(self) -> None:
        """INV-090, INV-092: the squash commit is what the release engine classifies.

        The check runs inside the quality action rather than in a job of its own, because that is
        where a pull request run already has an interpreter and a checked-out tree in either
        container shape.
        """

        quality = (ROOT / ".github/actions/quality/action.yml").read_text(encoding="utf-8")
        self.assertIn("scripts/conventional_title.py", quality)
        self.assertIn("if: github.event_name == 'pull_request'", quality)
        self.assertIn("PR_TITLE: ${{ github.event.pull_request.title }}", quality)

    def test_workflow_follows_the_tag_instead_of_pinning_one_release(self) -> None:
        """A pinned trigger silently builds nothing for the next release.

        The workflow was pinned to ``v1.0.0`` in three places - the tag pattern, the release-job
        condition, and the release-notes filename - so pushing ``v1.1.0`` would have run no job,
        built no wheel, and attached no asset. The pattern stays precise rather than a bare ``v*``
        glob, and ``scripts/release_artifact.py`` is the real gate on what may be published under
        an acceptable tag.
        """

        workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

        self.assertIn('- "v[0-9]+.[0-9]+.[0-9]+"', workflow)
        self.assertNotIn('- "v*"', workflow)
        self.assertNotIn("github-release-v1.0.0.md", workflow)
        self.assertNotIn("tag_name == 'v1.0.0'", workflow)


if __name__ == "__main__":
    unittest.main()


class PublishingToAnIndexIsOptionalTest(unittest.TestCase):
    """Unset means publish nowhere, which is exactly what the public run does.

    The switch is one variable, the same shape `REFERENCE_REGISTRY_URL` uses. A second variable to
    turn the first one on is a thing to forget, and this project has already paid for one of those.
    """

    ACTION = ROOT / ".github" / "actions" / "release" / "action.yml"
    WORKFLOWS = (ROOT / ".github" / "workflows" / "release.yml",)

    def test_the_step_runs_only_for_a_fork_that_asked_for_it(self) -> None:
        action = self.ACTION.read_text(encoding="utf-8")

        self.assertIn("scripts/publish_to_index.py", action)
        # Both halves of the guard matter.  Without the URL test, an unconfigured fork posts a
        # wheel at an empty address; without `attach`, a plain tag push publishes a version the
        # index already holds and fails a run that did nothing wrong.
        self.assertIn(
            "if: inputs.attach == 'true' && env.INDEX_PUBLISH_URL != ''",
            action,
        )

    def test_the_credential_is_named_by_a_variable_and_written_nowhere(self) -> None:
        for path in self.WORKFLOWS:
            workflow = path.read_text(encoding="utf-8")
            with self.subTest(workflow=path.name):
                self.assertIn(
                    "AART_INDEX_PUBLISH_CREDENTIALS: "
                    "${{ secrets[vars.AART_INDEX_PUBLISH_CREDENTIALS_SECRET] }}",
                    workflow,
                )
                self.assertIn("INDEX_PUBLISH_URL: ${{ vars.AART_INDEX_PUBLISH_URL }}", workflow)

    def test_both_halves_of_the_credential_are_remasked(self) -> None:
        """GitHub masks the value it was given -- `user:pass` -- and neither half after a split."""

        action = self.ACTION.read_text(encoding="utf-8")
        publish = action.split("Publish the wheel to the internal index", 1)[1]
        self.assertEqual(publish.count("::add-mask::"), 2)

    def test_no_step_installs_a_publishing_tool(self) -> None:
        """`twine` would be the fourth program assumed present and absent, after make, gh and curl."""

        for path in (self.ACTION, *self.WORKFLOWS):
            settings = "\n".join(
                line
                for line in path.read_text(encoding="utf-8").splitlines()
                if not line.lstrip().startswith("#")
            )
            with self.subTest(file=path.name):
                self.assertNotIn("twine", settings)
                self.assertNotIn("poetry", settings)
