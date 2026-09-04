"""The Enterprise fork contract: every knob is a variable, and every variable is documented.

`docs/ci/enterprise-fork-v1.md` promises two things that prose alone cannot keep true.  First,
that an unconfigured fork behaves exactly like the public run, which is a claim about *defaults*.
Second, that the variable table is complete, which is a claim about the workflows.  A variable
added to a workflow and not to the page fails here, the same way
`tests/git_environment_docs_test.py` guards the Git environment page.
"""

from __future__ import annotations

import pathlib
import re
import unittest

from agent_artifacts.registry_commands.templates import (
    REGISTRY_CI_WORKFLOW,
    USAGE_REPORT_DASHBOARD_WORKFLOW,
    USAGE_REPORT_VALIDATE_WORKFLOW,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "ci" / "enterprise-fork-v1.md"
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
# `registry init` writes three workflows.  Portability that stops at the quality gate leaves the
# usage-reporting half reaching github.com from inside an Enterprise instance.
_SHIPPED = {
    "registry quality": REGISTRY_CI_WORKFLOW,
    "usage validate": USAGE_REPORT_VALIDATE_WORKFLOW,
    "usage dashboard": USAGE_REPORT_DASHBOARD_WORKFLOW,
}
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
            # An unset image must leave the job on the runner's own environment.
            self.assertIn("container: ${{ vars.AART_CI_IMAGE }}", workflow)

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

    def test_setup_python_is_skipped_only_when_an_image_carries_one(self) -> None:
        """The decision still belongs to the variable; only the place it is read moved.

        The steps live in a composite action now, because two jobs that differ solely in how
        their image is pulled must not differ in what they run.  An action cannot read `vars`,
        so the job passes the answer down and the action acts on it.
        """

        for path in WORKFLOWS:
            self.assertIn("setup-python: ${{ vars.AART_CI_IMAGE == '' }}", _read(path))
        for action in ("quality", "release"):
            body = _read(ROOT / ".github" / "actions" / action / "action.yml")
            self.assertIn("if: inputs.setup-python == 'true'", body)


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
        self.assertIn("-m agent_artifacts", template)
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
            self.assertIn("agent_artifacts/__main__.py", body)
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

    def test_gh_is_pointed_at_the_instance_the_job_runs_on(self) -> None:
        """`gh --repo owner/name` defaults to github.com, which on GHES is the wrong server."""

        for label, body in EMITTED.items():
            if "gh issue" not in body and "gh label" not in body:
                continue
            self.assertIn("GH_HOST=${GH_HOST_OVERRIDE:-${GITHUB_SERVER_URL#https://}}", body, label)

    def test_pages_deployment_can_be_switched_off(self) -> None:
        """An Enterprise instance may not offer Pages; the dashboard must still be built."""

        dashboard = EMITTED["usage dashboard"]
        self.assertIn("vars.AART_PAGES != 'false'", dashboard)
        self.assertIn("aart reporting aggregate", dashboard)
        # The build and the publication are separate jobs, so the gate can skip one and keep the
        # other, and so the github-pages environment belongs only to the job that deploys.  It
        # waits on both shapes of the build and tolerates the one that stood down, which is what
        # `!cancelled()` buys: without it, a skipped dependency skips the dependent too.
        self.assertIn("needs: [aggregate, aggregate-private-image]", dashboard)
        self.assertIn("!cancelled() && !failure()", dashboard)
        # Deployment runs no Python and never fetches AART, so it needs no image at all.
        deploy = _job_bodies(dashboard)["deploy"]
        self.assertNotIn("container", deploy)


class RegistryGatesAreCompleteTest(unittest.TestCase):
    def test_the_template_runs_every_registry_gate(self) -> None:
        template = TEMPLATE_TEXT
        for gate in (
            "aart registry format --source . --check",
            "aart registry validate --source . --strict --frozen",
            "aart registry lock --source . --check",
            "aart registry build --source . --check",
            "aart registry audit --source .",
            "aart registry test --source . --compatibility",
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
                    job.count('test -f "$tool/agent_artifacts/__main__.py"'), 1, f"{label}: {name}"
                )


class ThePinIsReadFromTheRepositoryTest(unittest.TestCase):
    """`.aart-version` decides the version; the variables only decide where to get it.

    The split is the point: a registry stood up at two companies runs the same version through
    different supply chains, so a version in a variable would have to be repeated per deployment
    and a supply chain in the repository would have to be edited per deployment.
    """

    def test_every_workflow_reads_the_pin_before_choosing_an_arm(self) -> None:
        for label, body in EMITTED.items():
            self.assertIn("if [ -f .aart-version ]; then PIN=", body, label)
            self.assertLess(body.index(".aart-version"), body.index('if [ -n "$PACKAGE" ]'), label)

    def test_the_index_and_wheel_arms_substitute_the_pin(self) -> None:
        """Otherwise a version would have to be written into a variable as well as the file."""

        for label, body in EMITTED.items():
            self.assertIn(r'requirement="${PACKAGE//\{version\}/$PIN}"', body, label)
            self.assertIn(r'url="${WHEEL_URL//\{version\}/$PIN}"', body, label)

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
    survives, and every containerised job is emitted twice.  `docs/ci/enterprise-fork-v1.md`
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
    #: `TheContainerSwitchTest` holds the two to the same steps. `AART_PAGES` decides whether a
    #: dashboard is *published* on an instance that offers no Pages; the build above it still runs,
    #: which `test_pages_deployment_can_be_switched_off` holds. Neither decides whether anything is
    #: checked. A third name here is a new power over the quality contract and needs its own case.
    INFRASTRUCTURE = frozenset({"AART_IMAGE_USERNAME_SECRET", "AART_PAGES"})

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
        self.assertGreater(sum(len(items) for items in found.values()), 20)
        self.assertEqual(["if: a", "if: b"], self._conditions("    - if: a\n      if: b\n"))
        for label in ("pr-check.yml", "usage dashboard"):
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
        self.assertGreater(found, 8)

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
        """GitHub masks the value it was given -- `user:pass` -- and neither half after a split."""

        # One action assembles the URL for every caller, so this is the only place to look.
        action = _read(ROOT / ".github" / "actions" / "pip-index" / "action.yml")
        self.assertEqual(action.count("::add-mask::"), 2, "pip-index action: one half unmasked")
        # A workflow emits its job once per container shape, so the count is taken per job.
        for label, body in EMITTED.items():
            for name, job in _fetching_jobs(body).items():
                self.assertEqual(
                    job.count("::add-mask::"), 2, f"{label}: {name}: one half left unmasked"
                )

    def test_no_log_line_carries_the_assembled_url(self) -> None:
        for label, body in EMITTED.items():
            self.assertIn('how="index $announce', body, label)
            self.assertNotIn('how="index $INDEX_URL', body, label)


if __name__ == "__main__":
    unittest.main()
