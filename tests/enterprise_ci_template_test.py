"""The Enterprise fork contract: every knob is a variable, and every variable is documented.

`docs/ci/github-enterprise-rollout.md` promises two things that prose alone cannot keep true.  First,
that an unconfigured fork behaves exactly like the public run, which is a claim about *defaults*.
Second, that the variable table is complete, which is a claim about the workflows.  A variable
added to a workflow and not to the page fails here, the same way
`tests/git_environment_docs_test.py` guards the Git environment page.
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile

from aart_cli.registry_commands.templates import REGISTRY_CI_WORKFLOW
from tests.credential_fixtures import credential_url

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "ci" / "github-enterprise-rollout.md"
ACTION = ROOT / ".github" / "actions" / "aart" / "action.yml"
# The two workflows that run *this repository's* toolchain, and so have to be told where the
# interpreter, the image and the index are.  `release-please.yml` is deliberately not here: it
# runs one pinned action on the runner's own Node, touching neither pip nor Python, so every
# variable below would be a variable it never reads.  `TheReleaseEngineIsPortableToo` states what
# it must satisfy instead.
WORKFLOWS = (
    ROOT / ".github" / "workflows" / "pr-check.yml",
    ROOT / ".github" / "workflows" / "release.yml",
)
RELEASE_ENGINE = ROOT / ".github" / "workflows" / "release-please.yml"
# The workflows are thin by INV-076, so the steps -- and any condition on them -- are here.
ACTIONS = tuple(sorted((ROOT / ".github" / "actions").rglob("action.yml")))
# The registry's workflow has one home: the bytes `registry init` writes.  A second copy under
# docs/ would rot, and `plan_registry_init` refuses a template whose content has drifted.
TEMPLATE_TEXT = REGISTRY_CI_WORKFLOW.decode("utf-8")
_SHIPPED = {"registry quality": REGISTRY_CI_WORKFLOW}
EMITTED = {label: body.decode("utf-8") for label, body in _SHIPPED.items()}
_VARIABLE = re.compile(r"vars\.(AART_[A-Z0-9_]+)")
_SECRET = re.compile(r"secrets(\.[A-Za-z_][A-Za-z0-9_]*|\[[^\]]+\])")
_URL = re.compile(r"https?://([A-Za-z0-9.-]*\.[A-Za-z]{2,})")


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _uncommented(text: str) -> str:
    """The settings only.  A comment naming a tool is the note explaining why it is gone."""

    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


class TheButtonFinishesTheJobTest(unittest.TestCase):
    """A release published with the repository token raises no event, so nothing reacts to it.

    GitHub does not run workflows for anything done with `GITHUB_TOKEN` -- the rule that stops a
    workflow setting itself off in a loop. The release button published a release with that token
    and expected `release.yml` to notice; `release.yml` never ran, and the first release the
    button produced had no wheel attached. The run that publishes a release is the last run there
    will be, so it has to finish the job itself.
    """

    def _action(self, name: str) -> str:
        return _read(ROOT / ".github" / "actions" / name / "action.yml")

    def test_the_release_engine_delegates_to_the_one_thing_that_builds_an_artifact(self) -> None:
        """The button is gone; the wall it hit is not, and the answer it found outlived it.

        `release-please.yml` creates the tag and the release with `GITHUB_TOKEN`, so nothing is
        set off by either. It therefore calls the release workflow, which is `workflow_call`-able
        for exactly this reason -- delegating rather than repeating, because a second builder is a
        second answer to what the wheel is.
        """

        body = _uncommented(_read(ROOT / ".github" / "workflows" / "release-please.yml"))
        self.assertIn("uses: ./.github/workflows/release.yml", body)
        self.assertIn("attach: true", body)
        self.assertNotIn("scripts/build_wheel.py", body)
        self.assertNotIn("scripts/attach_release_asset.py", body)

    def test_attaching_is_asked_for_by_the_caller_not_read_off_the_event(self) -> None:
        body = _uncommented(self._action("release"))
        self.assertIn("if: inputs.attach == 'true'", body)
        self.assertNotIn("github.event_name", body)

    def test_no_step_names_an_artifact_action_either_host_refuses(self) -> None:
        """One host cannot run v4, the other will not resolve v3, and one file cannot do both.

        github.com fails the run while resolving the action, before any `if:` is evaluated, so
        the two-spellings-and-a-condition pattern that worked for the container image does not
        work here. The wheel is attached to the release instead, which is the copy that lasts.
        """

        self.assertNotIn("upload-artifact", _uncommented(self._action("release")))

    def test_every_caller_of_the_release_action_says_whether_to_attach(self) -> None:
        callers = [ROOT / ".github" / "workflows" / "release.yml"]
        for path in callers:
            with self.subTest(caller=str(path.relative_to(ROOT))):
                body = _uncommented(_read(path))
                # `attach: ${{` is the caller's form.  The workflow also *declares* an `attach:`
                # input for its callers, and counting that would make the two sides agree by
                # accident rather than because every `uses:` said what it wanted.
                self.assertEqual(
                    body.count("uses: ./.github/actions/release"), body.count("attach: ${{")
                )


class TheReleaseEngineIsPortableTooTest(unittest.TestCase):
    """`release-please.yml` reads no interpreter, image or index -- but it still reads the runner.

    It is exempt from the plumbing every other workflow carries because it uses none of it: one
    pinned action, running on the runner's Node. What it is not exempt from is the one variable
    that decides *where* a fork's work runs, and from naming its action by an exact tag.
    """

    def test_the_runner_is_the_one_variable_it_still_reads(self) -> None:
        body = _uncommented(_read(RELEASE_ENGINE))
        self.assertIn("runs-on: ${{ fromJSON(vars.AART_RUNNER || '[\"ubuntu-latest\"]') }}", body)

    def test_it_reads_none_of_the_plumbing_it_does_not_use(self) -> None:
        body = _uncommented(_read(RELEASE_ENGINE))
        for unused in ("AART_CI_IMAGE", "AART_PYTHON", "AART_PIP_INDEX_URL", "AART_POETRY"):
            with self.subTest(variable=unused):
                self.assertNotIn(unused, body)

    def test_the_engine_is_pinned_rather_than_followed(self) -> None:
        """A release engine tracking a moving reference is a version calculator that can change
        its mind between two runs of the same repository."""

        body = _uncommented(_read(RELEASE_ENGINE))
        self.assertIn("uses: googleapis/release-please-action@v4", body)
        self.assertNotIn("@main", body)
        self.assertNotIn("@master", body)


class PipReachesTheRightIndexTest(unittest.TestCase):
    """Anything that installs with pip must first be told which index to install from.

    The release button shipped with the install step copied and the index step left behind. On a
    runner that cannot see pypi.org, pip went to pypi.org anyway and failed on a certificate it
    could not verify -- a message naming neither the index nor the step that was missing. The
    action's own description warns that a sequence duplicated is a sequence that drifts; this is
    the test that makes the warning binding.
    """

    def test_every_action_that_installs_with_pip_points_pip_at_the_index_first(self) -> None:
        directory = ROOT / ".github" / "actions"
        # `dev_tools.py install` is a pip install one indirection further in -- it reads the
        # lock and hands the pins to pip -- so it is a subject of this test exactly as a literal
        # `pip install` is.  Matching only the literal would have quietly emptied the test the
        # day the step moved into a script.
        markers = ("-m pip install", "dev_tools.py install")
        installers = [
            (path, marker)
            for path in sorted(directory.glob("*/action.yml"))
            for marker in markers
            if marker in _uncommented(_read(path))
        ]
        self.assertTrue(installers, "no action installs with pip; this test has lost its subject")
        for path, marker in installers:
            with self.subTest(action=str(path.relative_to(ROOT)), marker=marker):
                body = _uncommented(_read(path))
                self.assertIn("uses: ./.github/actions/pip-index", body)
                self.assertLess(
                    body.index("uses: ./.github/actions/pip-index"),
                    body.index(marker),
                    "the index has to be chosen before pip is asked to fetch anything",
                )

    def test_the_shared_step_is_the_only_copy(self) -> None:
        directory = ROOT / ".github" / "actions"
        writers = [
            path
            for path in sorted(directory.glob("*/action.yml"))
            if "PIP_INDEX_URL=" in _read(path)
        ]
        self.assertEqual(writers, [directory / "pip-index" / "action.yml"])


class VariablesAreDocumentedTest(unittest.TestCase):
    def test_every_variable_a_workflow_reads_is_on_the_page(self) -> None:
        page = _read(PAGE)
        sources = [(str(path.relative_to(ROOT)), _read(path)) for path in WORKFLOWS]
        sources.extend(
            (f"registry init's {label} workflow", body) for label, body in EMITTED.items()
        )
        for label, body in sources:
            for name in sorted(set(_VARIABLE.findall(body))):
                self.assertIn(
                    name, page, f"{label} reads {name}, which the fork page does not list"
                )

    def test_the_page_lists_no_variable_that_nothing_reads(self) -> None:
        used: set[str] = set()
        for body in EMITTED.values():
            used.update(_VARIABLE.findall(body))
        for path in WORKFLOWS:
            used.update(_VARIABLE.findall(_read(path)))
        listed = set(re.findall(r"`(AART_[A-Z0-9_]+)`", _read(PAGE)))
        self.assertEqual(
            listed - used,
            set(),
            "the fork page documents a variable no workflow reads",
        )


class DefaultsReproduceThePublicRunTest(unittest.TestCase):
    """An unconfigured fork must run what this repository runs, or the template is a trap."""

    def test_runner_container_and_index_defaults(self) -> None:
        for path in WORKFLOWS:
            workflow = _read(path)
            self.assertIn("fromJSON(vars.AART_RUNNER || '[\"ubuntu-latest\"]')", workflow)
            self.assertIn("vars.AART_PIP_INDEX_URL || 'https://pypi.org/simple'", workflow)
            # An unset image must leave the public run exactly as it was, which now means the
            # official image for the interpreter that job is about rather than the bare runner.
            self.assertIn("container: ${{ vars.AART_CI_IMAGE ||", workflow)

    def test_the_registry_url_is_the_switch_and_carries_no_default(self) -> None:
        """One variable decides whether a release reconciles against a registry at all.

        Every other variable defaults to the public run, because an unconfigured fork should
        behave the way this repository always has.  This one cannot: a default naming a
        github.com repository reproduces nothing on an instance that cannot reach github.com --
        it guarantees a failed clone.  So the default is gone and presence is the switch, the
        same shape `AART_IMAGE_USERNAME_SECRET` already uses.

        Actions cannot tell an unset variable from an empty one, which is why a default and an
        opt-out cannot both exist here.  This repository sets the variable explicitly; clearing
        it is a real change, and the checklist says so on every run that skips.
        """

        workflow = _read(WORKFLOWS[1])
        self.assertIn("REFERENCE_REGISTRY_URL: ${{ vars.AART_REFERENCE_REGISTRY_URL }}", workflow)
        self.assertNotIn("AART_REFERENCE_REGISTRY_URL ||", workflow)
        # And no `GH_HOST` is set here any more -- checked outside the comments, which say why.
        # The wheel is attached through the REST API at `GITHUB_API_URL`, which the runner sets
        # to this instance, so there is no host to configure and none to forget.  `gh` defaulted
        # to github.com, so a fork that missed the variable uploaded to the wrong server.
        self.assertNotIn("GH_HOST", _uncommented(workflow))

        # Neither `gh` nor `curl` may come back: a real Enterprise image had neither, and the
        # attach step failed on each in turn after the wheel was already built.  The interpreter
        # is the only thing the release can assume, because every other step already needs it.
        action = _read(ROOT / ".github" / "actions" / "release" / "action.yml")
        for absent in ("gh release", "curl "):
            self.assertNotIn(absent, _uncommented(action), absent)
        self.assertIn("scripts/attach_release_asset.py", action)
        self.assertIn("if: env.REFERENCE_REGISTRY_URL != ''", action)
        self.assertIn("--without-registry", action)

    def test_no_workflow_and_no_action_names_setup_python(self) -> None:
        """`QA-088`: a step-level `if:` decides whether a step runs, not whether it is fetched.

        Every action a job references is resolved during "Set up job", before any condition is
        read.  So an instance that does not carry `actions/setup-python` could not escape it by
        setting `AART_CI_IMAGE` -- the reference itself had to go, and this is the claim that it
        stays gone.  A comment may still name it; a `uses:` may not.
        """

        for path in (*WORKFLOWS, ROOT / ".github" / "workflows" / "deep-quality.yml", *ACTIONS):
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertNotIn("setup-python", _uncommented(_read(path)))

    def test_every_job_takes_its_interpreter_from_an_image(self) -> None:
        """What replaced it: the interpreter comes from the container, never from a download.

        The public default is an official `python:<version>` image per matrix entry, so the three
        interpreters the gates have always exercised are still three interpreters.  A fork that
        sets `AART_CI_IMAGE` replaces all of them with its own, exactly as before.
        """

        gates = _read(ROOT / ".github" / "workflows" / "pr-check.yml")
        self.assertIn(
            "container: ${{ vars.AART_CI_IMAGE || format('python:{0}', matrix.python-version) }}",
            gates,
        )
        for path in (
            ROOT / ".github" / "workflows" / "release.yml",
            ROOT / ".github" / "workflows" / "deep-quality.yml",
        ):
            with self.subTest(path=path.relative_to(ROOT)):
                body = _read(path)
                self.assertIn(
                    "container: ${{ vars.AART_CI_IMAGE || format('python:{0}',"
                    " vars.AART_RELEASE_PYTHON_VERSION || '3.11') }}",
                    body,
                )

    def test_the_rollout_page_no_longer_promises_an_escape_that_never_worked(self) -> None:
        """The page told a reader to have the action available, and that an image skips it.

        Neither was true once the reference was gone, and the second was never true. Prose may
        still name the action -- the page explains why it left, which is what an operator who read
        the old advice needs -- but nothing the reader acts on may ask for it. The rows are what
        they act on: the prerequisites, the variables, and what a variable cannot change.
        """

        rows = [line for line in _read(PAGE).splitlines() if line.lstrip().startswith("|")]
        for row in rows:
            self.assertNotIn("setup-python", row)


class ToolNeedsNoPackagingTest(unittest.TestCase):
    """The registry gates run from a source tree.  That is the whole portability story."""

    def test_the_default_arm_installs_nothing(self) -> None:
        """Unconfigured, the template still needs no packaging: it clones and sets PYTHONPATH.

        `pip` appears exactly once, inside the arm that exists to use an index, and that arm is
        unreachable unless somebody sets `AART_PACKAGE`.  So the claim this test has always made
        survives the four arms: a fork that configures nothing needs no build backend.
        """

        template = TEMPLATE_TEXT
        self.assertIn("PYTHONPATH=", template)
        self.assertIn("-m aart_cli", template)
        self.assertNotIn("setup-python", template)
        for name, body in _fetching_jobs(template).items():
            self.assertEqual(body.count("pip install"), 1, name)
            self.assertIn('if [ -n "$PACKAGE" ]', body.split("pip install")[0][-200:], name)

    def test_the_template_keeps_one_marketplace_action(self) -> None:
        """`uses:` cannot be a variable, so each one is a hand edit on an instance that lacks it."""

        uses = re.findall(r"^\s*(?:-\s+)?uses:\s*(\S+)", TEMPLATE_TEXT, re.M)
        self.assertEqual(
            set(uses), {"actions/checkout@v4"}, "template grew a marketplace dependency"
        )

    def test_both_resolvers_check_the_package_before_trusting_the_tree(self) -> None:
        for body in (TEMPLATE_TEXT, _read(ACTION)):
            self.assertIn("aart_cli/__main__.py", body)
            self.assertIn('echo "$bin" >> "$GITHUB_PATH"', body)

    def test_a_commit_sha_falls_back_from_the_shallow_clone(self) -> None:
        """`--depth 1 --branch` rejects a sha, and a sha is what an operator pins with."""

        for body in (TEMPLATE_TEXT, _read(ACTION)):
            self.assertIn("--depth 1 --branch", body)
            self.assertIn("checkout --quiet", body)


class EveryEmittedWorkflowIsPortableTest(unittest.TestCase):
    """All three, not just the quality gate."""

    def test_none_of_them_needs_packaging_unless_asked_to(self) -> None:
        for label, body in EMITTED.items():
            self.assertNotIn("setup-python", body, label)
            self.assertIn("PYTHONPATH=", body, label)
            for name, job in _fetching_jobs(body).items():
                self.assertEqual(job.count("pip install"), 1, f"{label}: {name}")

    def test_none_of_them_pins_a_hosted_runner(self) -> None:
        for label, body in EMITTED.items():
            self.assertNotIn("runs-on: ubuntu-latest", body, label)
            self.assertIn("fromJSON(vars.AART_RUNNER", body, label)


class RegistryGatesAreCompleteTest(unittest.TestCase):
    def test_the_template_runs_every_registry_gate(self) -> None:
        template = TEMPLATE_TEXT
        for gate in (
            "aart-cli registry format --source . --check",
            "aart-cli registry validate --source .",
            "aart-cli registry build --source . --check",
            "aart-cli registry audit --source .",
            "aart-cli registry test --source . --compatibility",
        ):
            self.assertIn(gate, template)

    def test_both_compatibility_ends_are_exercised(self) -> None:
        self.assertIn("compatibility: [minimum, latest]", TEMPLATE_TEXT)


class EveryFetchArmIsReachableTest(unittest.TestCase):
    """Four ways in, and an order that has to stay the order the page documents.

    The arms are `elif`s, so one that is always set hides every arm below it.  Git carries the
    only shipped default, which is why it has to be last -- a rule that is invisible in the YAML
    and would be re-broken by anyone reordering the block for readability.
    """

    ARMS = ("PACKAGE", "WHEEL_URL", "TOOL_PATH", "TOOL_URL")

    @staticmethod
    def _chain(body: str) -> str:
        """Only the if/elif/else that selects an arm — the pin is read before it and is not one."""

        return body.split('tool="$RUNNER_TEMP/aart-tool"', 1)[1].split("\n          fi\n", 1)[0]

    def test_the_arms_are_tried_from_the_most_governed_supply_chain_to_the_least(self) -> None:
        for label, body in EMITTED.items():
            found = re.findall(r'\[ -n "\$(\w+)" \]', self._chain(body))
            self.assertEqual(tuple(found) + ("TOOL_URL",), self.ARMS, label)

    def test_the_git_arm_is_the_else_so_it_cannot_be_reordered(self) -> None:
        """The rule that keeps the other three reachable is structural, not a convention."""

        for label, body in EMITTED.items():
            chain = self._chain(body)
            self.assertIn("\n          else\n", chain, label)
            self.assertLess(chain.index('[ -n "$TOOL_PATH" ]'), chain.index("\n          else\n"))

    def test_only_the_git_arm_carries_a_default(self) -> None:
        """Every other arm must be empty unless somebody sets it, or it shadows the ones below."""

        for label, body in EMITTED.items():
            for name in ("AART_PACKAGE", "AART_WHEEL_URL", "AART_TOOL_PATH"):
                self.assertIn(f"${{{{ vars.{name} }}}}", body, label)

    def test_the_run_log_names_which_arm_answered(self) -> None:
        """A variable is not in the file, so the run is the only place the truth can appear."""

        for label, body in EMITTED.items():
            self.assertIn('echo "AART: aart-cli $got  via $how', body, label)

    def test_every_arm_ends_at_the_same_check(self) -> None:
        for label, body in EMITTED.items():
            for name, job in _fetching_jobs(body).items():
                self.assertEqual(
                    job.count('test -f "$tool/aart_cli/__main__.py"'), 1, f"{label}: {name}"
                )


class ThePinIsReadFromTheRepositoryTest(unittest.TestCase):
    """`.aart-cli-version` decides the version; the variables only decide where to get it.

    The split is the point: a registry stood up at two companies runs the same version through
    different supply chains, so a version in a variable would have to be repeated per deployment
    and a supply chain in the repository would have to be edited per deployment.
    """

    def test_every_workflow_reads_the_pin_before_choosing_an_arm(self) -> None:
        for label, body in EMITTED.items():
            self.assertIn("if [ -f .aart-cli-version ]; then PIN=", body, label)
            self.assertLess(
                body.index(".aart-cli-version"), body.index('if [ -n "$PACKAGE" ]'), label
            )

    def test_the_index_and_wheel_arms_substitute_the_pin(self) -> None:
        """Otherwise a version would have to be written into a variable as well as the file.

        Both arms go through one `expand`, which reads `$PIN` itself -- so an arm cannot be given
        a substitution that quietly comes from somewhere else.  `TheStepRunsOnAnImageWithoutBash`
        holds the substitution's behaviour; this holds that both arms are subject to it.
        """

        for label, body in EMITTED.items():
            self.assertIn('requirement=$(expand "$PACKAGE")', body, label)
            self.assertIn('url=$(expand "$WHEEL_URL")', body, label)
            self.assertIn('replace("{version}", sys.argv[2]))\' "$1" "$PIN"', body, label)

    def test_the_git_arm_derives_its_ref_from_the_pin(self) -> None:
        for label, body in EMITTED.items():
            self.assertIn('ref="${PIN:+v$PIN}"', body, label)

    def test_no_variable_carries_a_default_ref_any_more(self) -> None:
        """`AART_REF` with a `main` default would silently outrank the pin on every run."""

        for label, body in EMITTED.items():
            self.assertIn("TOOL_REF: ${{ vars.AART_REF }}", body, label)
            self.assertNotIn("vars.AART_REF || 'main'", body, label)

    def test_the_fetched_version_is_verified_against_the_pin(self) -> None:
        """A pin that is only declared is the stamp again. This one is checked on every arm."""

        for label, body in EMITTED.items():
            self.assertIn(
                'if [ -n "$PIN" ] && [ -z "$override" ] && [ "$got" != "$PIN" ]; then', body, label
            )
            self.assertIn("exit 2", body, label)

    def test_an_override_is_announced_rather_than_silent(self) -> None:
        for label, body in EMITTED.items():
            self.assertIn("overridden by AART_REF", body, label)


def _job_bodies(workflow: str) -> dict[str, str]:
    """Split a workflow into its jobs.

    Every job that runs in a container is emitted twice, once per container shape, so a count
    taken over a whole file now says two where it means one.  The invariants are per job, and
    this is what makes them expressible that way.
    """

    jobs = workflow.split("\njobs:\n", 1)[1]
    bodies: dict[str, str] = {}
    name: str | None = None
    lines: list[str] = []
    for line in jobs.splitlines(keepends=True):
        match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if match:
            if name is not None:
                # A comment block sitting between two jobs explains the one it precedes, so it
                # is handed forward rather than left at the end of the previous job.  Left there
                # it becomes part of that job's "steps", and the drift test between the two
                # container shapes fails on prose -- a trap that costs an afternoon and says
                # nothing true about the workflow.
                bodies[name] = "".join(lines[: len(lines) - _trailing_prose(lines)])
                lines = lines[len(lines) - _trailing_prose(lines) :]
            else:
                lines = []
            name = match.group(1)
        elif name is not None:
            lines.append(line)
    if name is not None:
        bodies[name] = "".join(lines)
    return bodies


def _trailing_prose(lines: list[str]) -> int:
    """How many lines at the end are blank or comment -- that is, belong to what comes next."""

    count = 0
    for line in reversed(lines):
        if line.strip() == "" or line.lstrip().startswith("#"):
            count += 1
            continue
        break
    return count


def _fetching_jobs(workflow: str) -> dict[str, str]:
    return {name: body for name, body in _job_bodies(workflow).items() if "Provide AART" in body}


def _steps_of(body: str) -> str:
    return body.split("    steps:\n", 1)[1] if "    steps:\n" in body else ""


class TheContainerSwitchTest(unittest.TestCase):
    """A private image needs credentials, and a credentials block cannot be conditional.

    Measured on a real instance, not reasoned about: an empty `credentials` block and a `null`
    one are both rejected before the job starts, and filling it with a placeholder makes an
    anonymous pull fail a `docker login` it never needed.  The `secrets` context is not even
    readable at `container:` itself.  So the switch lives at `if:`, the one place a choice
    survives, and every containerised job is emitted twice.  `docs/ci/github-enterprise-rollout.md`
    records the runs that established each of those facts.
    """

    SOURCES = {
        **{str(path.relative_to(ROOT)): _read(path) for path in WORKFLOWS},
        **EMITTED,
    }

    def test_every_containerised_job_comes_in_both_shapes(self) -> None:
        for label, workflow in self.SOURCES.items():
            bodies = _job_bodies(workflow)
            plain = [name for name, body in bodies.items() if "    container:" in body]
            for name in plain:
                if name.endswith("-private-image"):
                    continue
                self.assertIn(f"{name}-private-image", bodies, f"{label}: {name} has one shape")

    def test_the_two_shapes_run_the_same_steps(self) -> None:
        """The one thing duplication can break, held by a test rather than by care."""

        for label, workflow in self.SOURCES.items():
            bodies = _job_bodies(workflow)
            for name, body in bodies.items():
                if not name.endswith("-private-image"):
                    continue
                plain = bodies[name[: -len("-private-image")]]
                self.assertEqual(
                    _steps_of(plain).strip(), _steps_of(body).strip(), f"{label}: {name} drifted"
                )

    def test_the_switch_is_exclusive_so_exactly_one_shape_runs(self) -> None:
        for label, workflow in self.SOURCES.items():
            for name, body in _job_bodies(workflow).items():
                if "    container:" not in body:
                    continue
                expected = "!=" if name.endswith("-private-image") else "=="
                self.assertIn(
                    f"vars.AART_IMAGE_USERNAME_SECRET {expected} ''", body, f"{label}: {name}"
                )

    def test_the_default_shape_carries_no_credentials_block(self) -> None:
        """Naming no secrets must leave the job this project always ran, byte for byte."""

        for label, workflow in self.SOURCES.items():
            for name, body in _job_bodies(workflow).items():
                if name.endswith("-private-image"):
                    continue
                # `persist-credentials: false` on the checkout is a different key at a different
                # depth; what must be absent is the container's own block.
                self.assertNotIn("\n      credentials:\n", body, f"{label}: {name}")
                self.assertNotIn("secrets[vars.AART_IMAGE_", body, f"{label}: {name}")

    def test_the_credentialed_shape_names_both_secrets_through_variables(self) -> None:
        """A secret's *name* is not a secret, so an instance keeps its own naming."""

        for label, workflow in self.SOURCES.items():
            for name, body in _job_bodies(workflow).items():
                if not name.endswith("-private-image"):
                    continue
                where = f"{label}: {name}"
                self.assertIn(
                    "username: ${{ secrets[vars.AART_IMAGE_USERNAME_SECRET] }}", body, where
                )
                self.assertIn(
                    "password: ${{ secrets[vars.AART_IMAGE_PASSWORD_SECRET] }}", body, where
                )


class VariablesCannotWeakenTheGatesTest(unittest.TestCase):
    """INV-072: a repository variable may move the work, never decide whether it is checked.

    Enterprise configuration is allowed to replace runners, images, indexes, tool locations and
    credential references. What it must not be able to do is weaken the semantic quality contract
    "merely by changing repository variables" -- and the shape that would do it is small and easy
    to add by accident: one `if: vars.AART_SKIP_SOMETHING != 'true'` on a gate step, and a fork
    turns a check off from a settings page with nothing in the diff to review.

    So the property is closed rather than sampled. Every conditional in every workflow -- the ones
    this repository runs and the ones it writes for somebody else -- is read, and the repository
    variables appearing in them must be exactly the two that decide infrastructure.
    """

    SOURCES = {
        **{str(path.relative_to(ROOT)): _read(path) for path in WORKFLOWS},
        **{str(path.relative_to(ROOT)): _read(path) for path in ACTIONS},
        **EMITTED,
    }

    #: `AART_IMAGE_USERNAME_SECRET` chooses which of two identical shapes of a job runs, and
    #: `TheContainerSwitchTest` holds the two to the same steps. A second name here is a new power
    #: over the quality contract and needs its own case.
    INFRASTRUCTURE = frozenset({"AART_IMAGE_USERNAME_SECRET"})

    def _conditions(self, text: str) -> list[str]:
        """Every condition, in both spellings.

        A step's condition may be written on its own line or inline as the first key of the list
        item, `- if: ...`. The second form was missed by the first draft of this method, and a
        mutation putting a variable on a gate step in that spelling went straight past it -- it
        was caught only by the documentation test noticing an undeclared variable, which is a
        different claim that a fork writing the variable onto the page would satisfy.
        """

        conditions = []
        for line in _uncommented(text).splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                stripped = stripped[2:]
            if stripped.startswith("if:"):
                conditions.append(stripped)
        return conditions

    def test_the_sources_really_carry_conditions_to_read(self) -> None:
        """The guard: an empty harvest would make every assertion below vacuous."""

        found = {label: self._conditions(text) for label, text in self.SOURCES.items()}
        self.assertGreater(sum(len(items) for items in found.values()), 5)
        self.assertEqual(["if: a", "if: b"], self._conditions("    - if: a\n      if: b\n"))
        # One committed workflow and one emitted template, because the harvest reads both and a
        # guard that only proved the committed half would go quiet if the emitted half stopped
        # being read at all.  `usage dashboard` stood here until CP-25 withdrew that workflow;
        # `registry quality` is the emitted source that outlived it.
        for label in ("pr-check.yml", "registry quality"):
            key = next(name for name in found if name.endswith(label))
            self.assertTrue(found[key], f"{label} yielded no conditions")

    def test_no_variable_outside_the_two_infrastructure_switches_gates_anything(self) -> None:
        offences = []
        for label, text in self.SOURCES.items():
            for condition in self._conditions(text):
                for name in _VARIABLE.findall(condition):
                    if name not in self.INFRASTRUCTURE:
                        offences.append(f"{label}: {condition}")
        self.assertEqual([], offences, "INV-072: a variable decides whether work is checked")

    def test_the_action_that_runs_the_gates_reads_no_variable_at_all(self) -> None:
        """The narrowest place the invariant could break, so it is stated on its own.

        Both gate jobs delegate here, and this file runs `scripts/quality.py` unconditionally. Its
        one condition is a caller input about whether the image already carries an interpreter --
        a question about the machine, settled by the workflow, not a switch a fork can reach.
        """

        action = _read(ROOT / ".github" / "actions" / "quality" / "action.yml")
        self.assertIn("scripts/quality.py", action)
        for condition in self._conditions(action):
            self.assertEqual([], _VARIABLE.findall(condition), condition)
        # The gate *step* itself, not everything after it: the step that follows checks the pull
        # request's title and is conditioned on there being one, which is a fact about the event
        # rather than a switch anybody can set.
        gate = action.split("Run canonical quality gates", 1)[1].split("\n    - name:", 1)[0]
        self.assertNotIn("if:", gate)


class EverySecretIsNamedByAVariableTest(unittest.TestCase):
    """INV-073: variables carry endpoints, labels and the *names* of secrets; never a value.

    The existing tests hold this one job at a time. This closes it: every `secrets.` reference in
    every workflow, shipped or emitted, must be indirected through a variable. A hardcoded secret
    name is not a leak by itself, but it is the thing that makes a fork edit YAML to move -- and a
    fork editing YAML is outside the supported operating model (INV-075).
    """

    SOURCES = {
        **{str(path.relative_to(ROOT)): _read(path) for path in WORKFLOWS},
        **{str(path.relative_to(ROOT)): _read(path) for path in ACTIONS},
        **EMITTED,
    }

    #: The one exception, and it is not a stored credential. GitHub mints `GITHUB_TOKEN` per run
    #: and scopes it to this repository on whatever instance the job is on, so it is already
    #: instance-relative and there is no secret store entry for a variable to name.
    PLATFORM = frozenset({"GITHUB_TOKEN"})

    def test_the_sources_really_carry_secrets_to_read(self) -> None:
        found = sum(len(_SECRET.findall(_uncommented(text))) for text in self.SOURCES.values())
        self.assertGreater(found, 15)

    def test_no_workflow_names_a_secret_it_was_not_told_the_name_of(self) -> None:
        offences = []
        for label, text in self.SOURCES.items():
            for reference in _SECRET.findall(_uncommented(text)):
                if reference.startswith("[vars.") or reference.lstrip(".") in self.PLATFORM:
                    continue
                offences.append(f"{label}: secrets{reference}")
        self.assertEqual([], offences, "INV-073: a secret name is hardcoded into a workflow")


class NoPublicHostIsReachedThatAVariableCannotRetargetTest(unittest.TestCase):
    """INV-078 and INV-074 meet here: the profile must be able to run with no public egress.

    That is not provable by listing the arms that *can* be retargeted -- `EveryFetchArmIsReachable`
    already does that, and an arm nobody thought of would pass it. The provable form is the
    complement: no absolute URL to a public host appears anywhere except as the fallback of a
    variable. Setting that variable then moves every one of them at once, and an air-gapped
    instance has nothing left reaching out.

    github.com is absent for a different reason and a better one: nothing names it. Every reference
    to the instance is derived from `github.server_url`, so a fork is already talking to itself.
    """

    SOURCES = {
        **{str(path.relative_to(ROOT)): _read(path) for path in WORKFLOWS},
        **{str(path.relative_to(ROOT)): _read(path) for path in ACTIONS},
        **EMITTED,
    }

    def test_the_sources_really_carry_urls_to_read(self) -> None:
        found = sum(len(_URL.findall(_uncommented(text))) for text in self.SOURCES.values())
        self.assertGreater(found, 5)

    def test_every_absolute_url_is_a_variable_default(self) -> None:
        """Both spellings of "default": the expression form and the shell form."""

        offences = []
        for label, text in self.SOURCES.items():
            for line in _uncommented(text).splitlines():
                if not _URL.search(line):
                    continue
                retargetable = "vars.AART_" in line or ":-http" in line
                if not retargetable:
                    offences.append(f"{label}: {line.strip()}")
        self.assertEqual([], offences, "INV-078: a public host no variable can retarget")

    def test_the_only_public_host_is_the_package_index(self) -> None:
        """A second one would be a second variable to set, and a second thing to forget."""

        hosts = set()
        for text in self.SOURCES.values():
            hosts.update(_URL.findall(_uncommented(text)))
        self.assertEqual({"pypi.org"}, hosts)

    def test_no_url_names_github_com(self) -> None:
        """Every reference to the instance is derived from `github.server_url`, so a fork talks
        to itself without being told to.

        Stated over URLs rather than over the string, because the string does occur once and it is
        not egress: `cut-release` builds the tagger's email as
        `$GITHUB_ACTOR_ID+$GITHUB_ACTOR@users.noreply.github.com`, which is a committer identity
        written into a commit, not a host anything connects to. Pinning that one occurrence here
        keeps the distinction honest -- a real github.com URL added anywhere fails this -- and
        B-069 records the enterprise wart, which is that an instance has its own noreply domain.
        """

        for label, text in self.SOURCES.items():
            body = _uncommented(text)
            for line in body.splitlines():
                if "github.com" not in line:
                    continue
                self.assertIn("users.noreply.github.com", line, f"{label}: {line.strip()}")
                self.assertNotIn("://", line.split("github.com")[0][-8:], f"{label}: {line}")

    def test_github_com_is_named_nowhere_at_all(self) -> None:
        """It used to be named once, and the once was defensible.

        `cut-release` built the tagger's identity as
        `$GITHUB_ACTOR_ID+$GITHUB_ACTOR@users.noreply.github.com` -- a committer identity written
        into a commit, not a host anything connected to. The release engine writes that commit
        now, with an identity the runner supplies, so the exception went with the button and the
        claim is simply zero. B-069 records the enterprise wart it was hiding: an instance has its
        own noreply domain.
        """

        occurrences = [
            (label, line.strip())
            for label, text in self.SOURCES.items()
            for line in _uncommented(text).splitlines()
            if "github.com" in line
        ]
        self.assertEqual([], occurrences)


class ThisRepositorysWorkflowsStayThinTest(unittest.TestCase):
    """INV-076: workflow YAML selects triggers, permissions and actions. Logic lives elsewhere.

    Held as a closed property over the three workflows this repository runs: every step is either
    a checkout or a composite action, with one exception, and the exception is the aggregate gate's
    own report -- which `tests/aggregate_gate_test.py` runs under `bash`, so the one piece of logic
    left in YAML is also the one piece proven testable outside GitHub Actions.

    The emitted registry workflows are deliberately not held to this. They run in somebody else's
    repository, which has no composite action of this project's to call until it has fetched AART,
    and fetching AART is exactly what their inline step does.
    """

    def test_every_step_is_a_checkout_or_a_composite_action(self) -> None:
        allowed = {"actions/checkout@v4"}
        for path in WORKFLOWS:
            text = _uncommented(_read(path))
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped.startswith("- uses:"):
                    continue
                used = stripped.removeprefix("- uses:").strip()
                self.assertTrue(
                    used in allowed or used.startswith("./.github/actions/"),
                    f"{path.name}: {used}",
                )

    def test_the_one_inline_script_is_the_aggregate_and_it_is_tested_elsewhere(self) -> None:
        inline = {
            path.name: [line for line in _uncommented(_read(path)).splitlines() if "run: |" in line]
            for path in WORKFLOWS
        }
        self.assertEqual(
            {"pr-check.yml": 1, "release.yml": 0},
            {name: len(items) for name, items in inline.items()},
        )
        aggregate = _job_bodies(_read(ROOT / ".github" / "workflows" / "pr-check.yml"))["pr-check"]
        self.assertIn("run: |", aggregate)


class TheIndexCredentialIsAssembledNotStoredTest(unittest.TestCase):
    """A variable cannot hold a credential, so it holds the host and names the secret."""

    def test_both_halves_are_remasked_before_use(self) -> None:
        """GitHub masks the value it was given -- `user:pass` -- and neither half after a split.

        Counted per credential rather than as one total, so a step that later reads a second
        secret has to mask that one too, instead of passing under a number somebody raised once.
        """

        # One action assembles the URL for every caller, so this is the only place to look.
        action = _read(ROOT / ".github" / "actions" / "pip-index" / "action.yml")
        self.assertEqual(action.count("::add-mask::"), 2, "pip-index action: one half unmasked")
        # A workflow emits its job once per container shape, so the count is taken per job.
        for label, body in EMITTED.items():
            for name, job in _fetching_jobs(body).items():
                held = re.findall(r"^\s+(\w*CREDENTIALS): \$\{\{ secrets\[", job, re.M)
                self.assertTrue(held, f"{label}: {name}: no credential read; this test is vacuous")
                self.assertEqual(
                    job.count("::add-mask::"),
                    2 * len(held),
                    f"{label}: {name}: reads {held}, but not two masks each",
                )

    def test_no_log_line_carries_the_assembled_url(self) -> None:
        for label, body in EMITTED.items():
            self.assertIn('how="index $announce', body, label)
            self.assertNotIn('how="index $INDEX_URL', body, label)


def _step_script(body: str, name: str) -> str:
    """One named step's shell script, dedented the way the runner writes it to a file."""

    after = body.split(f"- name: {name}", 1)[1].split("        run: |\n", 1)[1]
    kept = []
    for line in after.splitlines():
        if line.strip() and not line.startswith(" " * 10):
            break
        kept.append(line[10:])
    return "\n".join(kept) + "\n"


def _provide_aart_script(body: str) -> str:
    """The `Provide AART` step's shell script, dedented the way the runner writes it to a file."""

    return _step_script(body, "Provide AART")


def _strict_posix_shell() -> str | None:
    """A POSIX shell that is not bash answering to the name `sh`.

    macOS `/bin/sh` *is* bash, and bash in `sh` mode still accepts `set -o pipefail` and `${v//a/b}`,
    so a developer machine cannot see this class of bug at all.  `dash` is `/bin/sh` on the Linux
    images that CI and a customer's Enterprise runner both use, and it is the oracle here.
    """

    found = shutil.which("dash") or ("/bin/dash" if os.path.exists("/bin/dash") else None)
    if found:
        return found
    probe = subprocess.run(
        ["/bin/sh", "-c", "echo ${BASH_VERSION-}"], capture_output=True, text=True, check=False
    )
    return None if probe.stdout.strip() else "/bin/sh"


POSIX_SHELL = _strict_posix_shell()

# What the fake interpreter answers to `--version`, and what `.aart-cli-version` therefore pins.  A
# number no real build carries, so a passing run cannot be one that reached the real package.
FAKE_VERSION = "4.5.6"
_FAKE_PY = """#!/usr/bin/env python3
import os, pathlib, sys

args = sys.argv[1:]
with pathlib.Path(os.environ["FAKE_PY_LOG"]).open("a", encoding="utf-8") as handle:
    handle.write(" ".join(args) + "\\n")
if args[0] == "-c":
    # `-c` is served for real: the wheel arm's one-liner is the code under test, not a stub.
    sys.argv = ["-c", *args[2:]]
    exec(compile(args[1], "<fake>", "exec"), {"__name__": "__main__"})
elif args[:2] == ["-m", "pip"]:
    target = pathlib.Path(args[args.index("--target") + 1]) / "aart_cli"
    target.mkdir(parents=True, exist_ok=True)
    (target / "__main__.py").write_text("", encoding="utf-8")
elif args[:2] == ["-m", "aart_cli"]:
    print("aart-cli __VERSION__")
"""


@unittest.skipIf(POSIX_SHELL is None, "no POSIX shell here; /bin/sh is bash")
class TheStepRunsOnAnImageWithoutBashTest(unittest.TestCase):
    """The step names no `shell:`, so a runner without bash serves it `sh -e {0}`.

    That is not hypothetical.  A container image with git and Python and no bash sent Actions to
    its documented fallback, and the step died on its own first line with
    `set: Illegal option -o pipefail` -- before it had chosen an arm, so no variable could have
    helped.  The same image would then have met `${PACKAGE//.../...}` and a shim asking for
    `/usr/bin/env bash`.  Every arm below is therefore run under a real POSIX shell.
    """

    def _stage(self, stack: contextlib.ExitStack) -> pathlib.Path:
        home = pathlib.Path(stack.enter_context(tempfile.TemporaryDirectory()))
        (home / "work").mkdir()
        (home / "work" / ".aart-cli-version").write_text(FAKE_VERSION + "\n", encoding="utf-8")
        (home / "runner").mkdir()
        (home / "script.sh").write_text(_provide_aart_script(TEMPLATE_TEXT), encoding="utf-8")
        interpreter = home / "fake-python"
        interpreter.write_text(_FAKE_PY.replace("__VERSION__", FAKE_VERSION), encoding="utf-8")
        interpreter.chmod(0o755)
        return home

    def _run(self, home: pathlib.Path, **arms: str) -> subprocess.CompletedProcess[str]:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "RUNNER_TEMP": str(home / "runner"),
            "GITHUB_PATH": str(home / "github_path"),
            "FAKE_PY_LOG": str(home / "py.log"),
            "PACKAGE": "",
            "WHEEL_URL": "",
            "TOOL_PATH": "",
            "TOOL_URL": "",
            "TOOL_REF": "",
            "INDEX_URL": "https://example.invalid/simple",
            "INDEX_CREDENTIALS": "",
            "GIT_CREDENTIALS": "",
            "PY": str(home / "fake-python"),
        }
        env.update(arms)
        assert POSIX_SHELL is not None
        return subprocess.run(
            [POSIX_SHELL, "-e", str(home / "script.sh")],
            cwd=home / "work",
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def _succeeded(self, done: subprocess.CompletedProcess[str]) -> str:
        self.assertEqual(done.returncode, 0, f"stderr: {done.stderr}\nstdout: {done.stdout}")
        return done.stdout

    def test_the_baked_path_arm_runs_under_a_posix_shell(self) -> None:
        """The arm that touches nothing outside the image, so only the shell can fail it."""

        with contextlib.ExitStack() as stack:
            home = self._stage(stack)
            baked = home / "baked"
            (baked / "aart_cli").mkdir(parents=True)
            (baked / "aart_cli" / "__main__.py").write_text("", encoding="utf-8")
            out = self._succeeded(self._run(home, TOOL_PATH=str(baked)))
            self.assertIn(f"AART: aart-cli {FAKE_VERSION}", out)
            self.assertIn("pinned by .aart-cli-version", out)

    def test_the_index_arm_expands_the_pin_without_bash(self) -> None:
        """`{version}` is substituted by a bash-only expansion that dash answers `Bad substitution`."""

        with contextlib.ExitStack() as stack:
            home = self._stage(stack)
            self._succeeded(self._run(home, PACKAGE="aart-cli=={version}"))
            # The expansion's own source text names `{version}`, so the claim is about what pip
            # was finally asked for, not about the log as a whole.
            asked = [
                line
                for line in (home / "py.log").read_text(encoding="utf-8").splitlines()
                if line.startswith("-m pip ")
            ]
            self.assertEqual(len(asked), 1, asked)
            self.assertTrue(asked[0].endswith(f"aart-cli=={FAKE_VERSION}"), asked[0])

    def test_the_wheel_arm_expands_the_pin_without_bash(self) -> None:
        """A wheel URL names the version twice -- in the path and in the filename -- so whatever
        replaces the bash expansion has to replace every occurrence, not the first."""

        with contextlib.ExitStack() as stack:
            home = self._stage(stack)
            served = home / "served" / f"v{FAKE_VERSION}"
            served.mkdir(parents=True)
            wheel = served / f"aart_cli-{FAKE_VERSION}-py3-none-any.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("aart_cli/__main__.py", "")
            template = (
                f"file://{home / 'served'}/v{{version}}/aart_cli-{{version}}-py3-none-any.whl"
            )
            out = self._succeeded(self._run(home, WHEEL_URL=template))
            self.assertIn(f"AART: aart-cli {FAKE_VERSION}", out)
            self.assertNotIn("{version}", out)

    def test_the_shim_it_writes_needs_no_bash_either(self) -> None:
        """The step can survive the fallback and still hand the job a launcher the image cannot run."""

        with contextlib.ExitStack() as stack:
            home = self._stage(stack)
            baked = home / "baked"
            (baked / "aart_cli").mkdir(parents=True)
            (baked / "aart_cli" / "__main__.py").write_text("", encoding="utf-8")
            self._succeeded(self._run(home, TOOL_PATH=str(baked)))
            shebang = (home / "runner" / "aart-bin" / "aart-cli").read_text(encoding="utf-8")
            self.assertNotIn("bash", shebang.splitlines()[0])


# A git that models the one fact the real failure turned on: an anonymous clone of a private
# repository is refused, with the message a real Enterprise runner produced.
_FAKE_GIT = """#!/usr/bin/env python3
import os, pathlib, sys

args = sys.argv[1:]
with pathlib.Path(os.environ["FAKE_GIT_LOG"]).open("a", encoding="utf-8") as handle:
    handle.write(" ".join(args) + "\\n")

def config(tree):
    return pathlib.Path(tree) / ".git" / "config"

if args[0] == "clone":
    url = next(a for a in args if a.startswith("http"))
    dest = pathlib.Path(args[-1])
    if "@" not in url.split("//", 1)[1].split("/", 1)[0]:
        sys.stderr.write(
            "fatal: could not read Username for '%s': No such device or address\\n" % url
        )
        raise SystemExit(128)
    (dest / "aart_cli").mkdir(parents=True, exist_ok=True)
    (dest / "aart_cli" / "__main__.py").write_text("", encoding="utf-8")
    config(dest).parent.mkdir(parents=True, exist_ok=True)
    config(dest).write_text("url = %s\\n" % url, encoding="utf-8")
elif args[0] == "-C" and "remote" in args:
    config(args[1]).write_text("url = %s\\n" % args[-1], encoding="utf-8")
"""

# The two halves of the credential the tests hand the step, and the host it is for.
GIT_USER = "deploy-bot"
GIT_TOKEN = "s3cr3t-token-value"
GIT_HOST = "ghe.example.org"
GIT_URL = f"https://{GIT_HOST}/platform/aart-cli.git"


@unittest.skipIf(POSIX_SHELL is None, "no POSIX shell here; /bin/sh is bash")
class TheGitArmCanAuthenticateTest(TheStepRunsOnAnImageWithoutBashTest):
    """The arm reached when nothing is set is the arm that could not log in.

    On a company instance the AART copy is private, and the clone carried no credential: the step's
    `env` held none and the registry's own checkout runs with `persist-credentials: false`. A real
    runner answered `could not read Username`, exit 128. The index arm beside it has solved this
    since it was written, so the credential travels the same way here: a *variable* naming a
    *secret*, assembled into the URL at run time, both halves re-masked, and the bare URL -- never
    the assembled one -- is what the log and `how` carry.
    """

    def _stage_git(self, stack: contextlib.ExitStack) -> pathlib.Path:
        home = self._stage(stack)
        binaries = home / "bin"
        binaries.mkdir()
        fake = binaries / "git"
        fake.write_text(_FAKE_GIT, encoding="utf-8")
        fake.chmod(0o755)
        return home

    def _run_git(
        self, home: pathlib.Path, credential: str = ""
    ) -> subprocess.CompletedProcess[str]:
        done = self._run(
            home,
            TOOL_URL=GIT_URL,
            GIT_CREDENTIALS=credential,
            PATH=f"{home / 'bin'}:{os.environ.get('PATH', '')}",
            FAKE_GIT_LOG=str(home / "git.log"),
        )
        return done

    def test_an_anonymous_clone_of_a_private_copy_is_refused(self) -> None:
        """The guard: without it every assertion below could pass against a public repository."""

        with contextlib.ExitStack() as stack:
            home = self._stage_git(stack)
            done = self._run_git(home)
            self.assertEqual(done.returncode, 128, done.stdout)
            self.assertIn("could not read Username", done.stderr)

    def test_a_named_secret_lets_the_same_clone_through(self) -> None:
        with contextlib.ExitStack() as stack:
            home = self._stage_git(stack)
            out = self._succeeded(self._run_git(home, f"{GIT_USER}:{GIT_TOKEN}"))
            self.assertIn(f"AART: aart-cli {FAKE_VERSION}", out)
            asked = (home / "git.log").read_text(encoding="utf-8")
            self.assertIn(
                credential_url(GIT_HOST, "/platform/aart-cli.git", user=GIT_USER, held=GIT_TOKEN),
                asked,
            )

    def test_neither_half_of_the_credential_reaches_the_log(self) -> None:
        """`::add-mask::` lines are excluded: handing GitHub the value is how it learns to hide it.

        Every other line is what a person reads, and what a failure would print -- including the
        announce line, whose `how` must name the repository without naming who fetched it.
        """

        with contextlib.ExitStack() as stack:
            home = self._stage_git(stack)
            done = self._run_git(home, f"{GIT_USER}:{GIT_TOKEN}")
            self._succeeded(done)
            masked = [line for line in done.stdout.splitlines() if "::add-mask::" in line]
            self.assertEqual(
                sorted(masked), sorted([f"::add-mask::{GIT_USER}", f"::add-mask::{GIT_TOKEN}"])
            )
            rest = [
                line
                for line in (done.stdout + done.stderr).splitlines()
                if "::add-mask::" not in line
            ]
            for line in rest:
                self.assertNotIn(GIT_TOKEN, line)
                self.assertNotIn(f"{GIT_USER}:", line)
            self.assertIn(f"via git {GIT_URL}@v{FAKE_VERSION}", "\n".join(rest))

    def test_a_secret_holding_only_a_token_is_taken_as_one(self) -> None:
        """A service account's token is already a secret; asking for `user:token` would mean
        copying it into a second one just to prefix a name."""

        with contextlib.ExitStack() as stack:
            home = self._stage_git(stack)
            done = self._run_git(home, GIT_TOKEN)
            self._succeeded(done)
            asked = (home / "git.log").read_text(encoding="utf-8")
            self.assertIn(
                credential_url(GIT_HOST, "/", user="x-access-token", held=GIT_TOKEN), asked
            )
            # Only the half that came out of the secret; `***` over a public constant would hide
            # nothing and read as though something had been.
            masked = [line for line in done.stdout.splitlines() if "::add-mask::" in line]
            self.assertEqual(masked, [f"::add-mask::{GIT_TOKEN}"])

    def test_the_credential_is_not_left_behind_in_the_clone(self) -> None:
        """`git clone` writes the URL it was given into the checkout's own config, so a credential
        passed this way outlives the step that used it -- in a directory later steps can read."""

        with contextlib.ExitStack() as stack:
            home = self._stage_git(stack)
            self._succeeded(self._run_git(home, f"{GIT_USER}:{GIT_TOKEN}"))
            recorded = (home / "runner" / "aart-tool" / ".git" / "config").read_text(
                encoding="utf-8"
            )
            self.assertNotIn(GIT_TOKEN, recorded)
            self.assertIn(GIT_URL, recorded)


_TRUST_STEP = "Trust the workspace"


class TheWorkspaceIsTrustedBeforeTheGatesTest(unittest.TestCase):
    """Git refuses a checkout it does not own, and a container runner hands it exactly that.

    The workspace is mounted owned by root and the job then runs as another user, so git answers
    `detected dubious ownership` and every AART command that reads the checkout fails -- the
    read-only ones too, because AART proves the target is a real Git checkout before it acts.  A
    customer's Enterprise run died this way on `registry format --check`, the first gate after the
    tool was in place.  Naming this one directory safe is git's own documented remedy, and it
    grants nothing beyond the directory the job just checked out.
    """

    def test_the_step_comes_before_anything_that_reads_the_checkout(self) -> None:
        for label, body in EMITTED.items():
            self.assertIn(_TRUST_STEP, body, label)
            self.assertLess(
                body.index(_TRUST_STEP),
                body.index("- run: aart-cli registry"),
                f"{label}: a gate would read the checkout before git had been told to trust it",
            )

    @unittest.skipIf(POSIX_SHELL is None, "no POSIX shell here; /bin/sh is bash")
    def test_it_records_the_workspace_and_nothing_else_as_safe(self) -> None:
        """Run the emitted line for real against real git.

        Asserting the text would pass on a misspelled config key or a variable the runner never
        sets; only git's own answer afterwards says the step did what its name claims.
        """

        for label, body in EMITTED.items():
            with tempfile.TemporaryDirectory() as raw:
                home = pathlib.Path(raw)
                workspace = home / "__w" / "registry" / "registry"
                workspace.mkdir(parents=True)
                script = home / "trust.sh"
                script.write_text(_step_script(body, _TRUST_STEP), encoding="utf-8")
                env = {
                    "PATH": os.environ.get("PATH", ""),
                    "HOME": str(home),
                    "GITHUB_WORKSPACE": str(workspace),
                }
                assert POSIX_SHELL is not None
                done = subprocess.run(
                    [POSIX_SHELL, "-e", str(script)],
                    cwd=workspace,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(done.returncode, 0, f"{label}: {done.stderr}")
                recorded = subprocess.run(
                    ["git", "config", "--global", "--get-all", "safe.directory"],
                    cwd=workspace,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(recorded.stdout.split(), [str(workspace)], label)


if __name__ == "__main__":
    unittest.main()
