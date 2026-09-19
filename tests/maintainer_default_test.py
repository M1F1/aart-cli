"""Nothing a registry generates, and no operational default, names the maintainer.

D-309: the owner found `M1F1/aart-cli` baked into the generated Registry README and workflow and
asked that neither this repository nor the `M1F1` organization be an operational default. A default
is different from a fact -- the Product Specification identifies the target repository and the
package metadata says where the distribution lives, and both are records rather than values another
deployment silently inherits. What is refused here is the inheriting kind: a value a company's
registry picks up because nobody set one.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from agent_artifacts.registry_commands import templates

_ROOT = Path(__file__).resolve().parents[1]
_MAINTAINER = re.compile(rb"M1F1", re.I)


def _provide_aart_script() -> str:
    """The `Provide AART` step's shell body, lifted out of the workflow it is generated into.

    Run rather than read, for the reason step 16 runs the install lines: a refusal that exists as
    text and not as an exit code is a refusal nobody has ever seen happen.
    """

    workflow = templates.REGISTRY_CI_WORKFLOW.decode("utf-8")
    start = workflow.index("      - name: Provide AART")
    body = workflow[start : workflow.index("\n      - name:", start + 1)]
    script = body[body.index("        run: |\n") + len("        run: |\n") :]
    return "\n".join(line[10:] for line in script.splitlines())


class GeneratedRegistryTest(unittest.TestCase):
    def test_no_generated_byte_names_the_maintainer(self) -> None:
        generated = {
            "workflow": templates.REGISTRY_CI_WORKFLOW,
            "readme": templates.render_registry_readme("company-registry", "Company Registry"),
            "gitignore": templates.REGISTRY_GITIGNORE,
        }

        for name, content in generated.items():
            with self.subTest(generated=name):
                self.assertIsNone(_MAINTAINER.search(content))

    def test_the_workflow_stops_when_no_source_of_aart_is_configured(self) -> None:
        """The arm that used to carry the shipped default now has nothing, and says so.

        Before this, a registry created by a company that set no variable cloned the maintainer's
        repository from its own instance -- absent there, so the run failed on a git error naming
        a repository nobody in that company had chosen. The refusal names what to set instead.
        """

        with tempfile.TemporaryDirectory() as raw:
            completed = subprocess.run(
                ["/bin/sh", "-c", _provide_aart_script()],
                cwd=raw,
                env={
                    "PATH": os.environ["PATH"],
                    "RUNNER_TEMP": raw,
                    "PY": "python3",
                    "PACKAGE": "",
                    "WHEEL_URL": "",
                    "TOOL_PATH": "",
                    "TOOL_URL": "",
                    "TOOL_REF": "",
                    "INDEX_URL": "https://pypi.org/simple",
                    "INDEX_CREDENTIALS": "",
                    "GIT_CREDENTIALS": "",
                },
                capture_output=True,
                text=True,
                timeout=120,
            )

        self.assertEqual(completed.returncode, 1)
        said = completed.stdout + completed.stderr
        for variable in (
            "AART_PACKAGE",
            "AART_WHEEL_URL",
            "AART_TOOL_PATH",
            "AART_TOOL_URL",
            "AART_REPOSITORY",
        ):
            with self.subTest(variable=variable):
                self.assertIn(variable, said)

    def test_the_workflow_expression_carries_no_repository_of_its_own(self) -> None:
        workflow = templates.REGISTRY_CI_WORKFLOW.decode("utf-8")
        line = next(item for item in workflow.splitlines() if "TOOL_URL:" in item)

        self.assertIn("vars.AART_REPOSITORY", line)
        # `format` with no fallback literal: an unset variable produces an empty URL, which the
        # script above refuses, rather than a repository the reader never named.
        self.assertNotIn("'M1F1", line)
        self.assertNotIn("aart-cli'", line)


class OperationalDefaultTest(unittest.TestCase):
    def test_the_registry_init_remediation_names_variables_rather_than_a_repository(self) -> None:
        from agent_artifacts.curation import runtime

        source = Path(runtime.__file__).read_bytes()

        self.assertIsNone(_MAINTAINER.search(source))

    def test_the_release_checklist_requires_a_named_reference_registry(self) -> None:
        """A constant cannot be the approved registry: a fork's release would check against it.

        The workflow already clones whatever `REFERENCE_REGISTRY_URL` names, so the checklist reads
        the same variable. With the variable unset there is no approved registry to compare with,
        and saying so is the only answer that is true in both repositories.
        """

        from tests.script_fixtures import load_script

        release = load_script("release")

        with unittest.mock.patch.dict(os.environ, {"REFERENCE_REGISTRY_URL": ""}, clear=False):
            self.assertEqual(release.approved_registry_origin(), "")
        with unittest.mock.patch.dict(
            os.environ, {"REFERENCE_REGISTRY_URL": "https://example.com/company/registry.git"}
        ):
            self.assertEqual(
                release.approved_registry_origin(), "https://example.com/company/registry"
            )

        self.assertIsNone(_MAINTAINER.search((_ROOT / "scripts" / "release.py").read_bytes()))


class PublicSetupExampleTest(unittest.TestCase):
    """The Enterprise guide is a public setup example, so it may not hand one out either."""

    def test_the_rollout_guide_names_no_maintainer_repository(self) -> None:
        guide = (_ROOT / "docs" / "ci" / "github-enterprise-rollout.md").read_bytes()

        self.assertIsNone(_MAINTAINER.search(guide))


if __name__ == "__main__":
    import unittest.mock  # noqa: F401

    unittest.main()
