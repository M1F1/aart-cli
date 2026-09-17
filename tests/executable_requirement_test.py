"""`QA-087`: an executable requirement names a file, and file names are not slugs.

The owner's container run refused `python3.11` -- the interpreter the image actually ships -- because
`ExecutableRequirement` was validating its name with the identifier pattern `RequirementId` uses. An
identifier is this project's to shape; an executable's name belongs to whoever built the machine,
and `python3.11`, `node20` and `clang-15` are ordinary names there.

So the rule is the one a file name really has: something a shell would look up on `PATH` by that
name alone. Not empty, no path separator, no whitespace, no control character, not a relative
directory. The requirement's own `id` stays a canonical slug, because that one is ours.
"""

from __future__ import annotations

import unittest

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts.application.installation_planning import (
    aggregate_requirements,
    allowed_remediations,
    assess_requirements,
)
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    SourceAlias,
)
from agent_artifacts.domain.inspection import (
    EnvironmentFact,
    EnvironmentFacts,
    FactState,
    RemediationCapability,
    RemediationCapabilityKind,
)
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.remediations import InstallExecutable
from agent_artifacts.domain.requirements import (
    ExecutableRequirement,
    RequirementId,
    requirement_to_data,
)
from agent_artifacts.domain.result import Ok


class ExecutableNameTest(unittest.TestCase):
    def test_a_real_interpreter_name_is_accepted(self) -> None:
        for name in (
            "python3.11",
            "python3",
            "node20",
            "clang-15",
            "git",
            "cmake3",
            "7z",
            "_local",
        ):
            with self.subTest(executable=name):
                requirement = ExecutableRequirement(RequirementId("interpreter"), name)
                self.assertEqual(requirement.executable, name)
                self.assertEqual(requirement_to_data(requirement)["executable"], name)

    def test_a_name_that_is_not_a_name_is_refused(self) -> None:
        """Each of these is something other than a file the shell can find by name."""

        for name in (
            "",
            "/usr/bin/python3.11",  # a path, not a name: the requirement says what, not where
            "bin\\python.exe",
            "python 3.11",
            " python3",
            "python3 ",
            "python\n3",
            "python\t3",
            "python\x003",
            ".",
            "..",
        ):
            with self.subTest(executable=name):
                with self.assertRaises(ValueError):
                    ExecutableRequirement(RequirementId("interpreter"), name)

    def test_the_requirement_id_is_still_ours_to_shape(self) -> None:
        """Widening the executable does not widen the identifier it is filed under."""

        with self.assertRaises(ValueError):
            RequirementId("python3.11")

    @given(
        st.text(
            alphabet=st.characters(blacklist_categories=("Cc", "Cs", "Zs", "Zl", "Zp")),
            min_size=1,
        ).filter(lambda name: "/" not in name and "\\" not in name and name not in {".", ".."})
    )
    def test_any_name_a_shell_could_look_up_is_expressible(self, name: str) -> None:
        self.assertEqual(
            ExecutableRequirement(RequirementId("interpreter"), name).executable,
            name,
        )

    @given(
        st.text(min_size=1).filter(
            lambda name: "/" in name or "\\" in name or name.strip() != name or not name.strip()
        )
    )
    def test_nothing_carrying_a_path_or_padding_gets_through(self, name: str) -> None:
        with self.assertRaises(ValueError):
            ExecutableRequirement(RequirementId("interpreter"), name)


class ExecutableRemediationTest(unittest.TestCase):
    """The remediation names the same executable, so it has to accept the same names.

    Planning derives an `InstallExecutable` whenever the environment advertises an installer
    capability under the requirement's own executable name. Widening only the requirement would
    leave a machine that can install `python3.11` crashing the planner at the moment it offers to.
    """

    def test_a_remediation_may_name_the_executable_it_installs(self) -> None:
        remediation = InstallExecutable(RequirementId("interpreter"), "python3.11")

        self.assertEqual(remediation.executable, "python3.11")
        with self.assertRaises(ValueError):
            InstallExecutable(RequirementId("interpreter"), "/usr/bin/python3.11")

    def test_planning_offers_the_installer_a_machine_says_it_has(self) -> None:
        owner = ArtifactCoordinate(
            SourceAlias("company"), ArtifactIdentity("mcp", "github"), "1.0.0"
        )
        requirement = ExecutableRequirement(RequirementId("interpreter"), "python3.11")
        aggregated = aggregate_requirements(((owner, (requirement,)),))
        assert isinstance(aggregated, Ok), aggregated
        facts = EnvironmentFacts(
            "linux",
            (EnvironmentFact(requirement.id, FactState.UNAVAILABLE),),
            (RemediationCapability(RemediationCapabilityKind.EXECUTABLE_INSTALLER, "python3.11"),),
        )

        options = allowed_remediations(
            assess_requirements(aggregated.value, facts), facts, EffectivePolicy()
        )

        self.assertEqual(
            tuple(option.remediation for option in options),
            (InstallExecutable(requirement.id, "python3.11"),),
        )


if __name__ == "__main__":
    unittest.main()
