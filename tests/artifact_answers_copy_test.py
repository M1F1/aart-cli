"""§172.3, D-413: configuration is answered once per artifact and copied into each new installation.

07 asks each artifact once, for all of the harnesses and scopes it is going into. Within that one
operation the answer is copied into every new installation of that artifact, and afterwards each
copy is that installation's own. An answer is never copied into another artifact, and a local and a
remote alias are two artifacts. With Set later, what is unanswered becomes the `AART_NOT_SET` placeholder.
Secrets are not answered here at all; they are 07b's.
"""

from __future__ import annotations

import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.installation_inputs import (
    ArtifactAnswer,
    InstallationInputField,
    copy_artifact_answers,
)
from aart_cli.domain.harness import Scope
from aart_cli.domain.identifiers import ArtifactIdentity, InputId, SourceAlias
from aart_cli.domain.inputs import (
    SKIPPED_INPUT,
    ConfigInput,
    EnvironmentBinding,
    PromptedConfigValue,
    SecretInput,
)
from aart_cli.domain.installation_owner import InstallationOwner

ORG = ConfigInput(InputId("org"), EnvironmentBinding("ORG"))
TOKEN = SecretInput(InputId("token"), EnvironmentBinding("TOKEN"))
GITHUB = ArtifactIdentity("mcp", "github")
JIRA = ArtifactIdentity("mcp", "jira")
COMPANY = SourceAlias("company")
LOCAL = SourceAlias("local")


def _owner(artifact=GITHUB, harness="claude", scope=Scope.PROJECT, source=COMPANY):
    return InstallationOwner(source, artifact, scope, "/root", harness)


def _answers(sources):
    return {(item.owner, item.source.input): item.source.value for item in sources}  # type: ignore[union-attr]


class OneAnswerPerArtifactTest(unittest.TestCase):
    def test_the_answer_reaches_every_harness_and_scope_of_its_artifact(self) -> None:
        owners = (
            _owner(harness="claude", scope=Scope.PROJECT),
            _owner(harness="opencode", scope=Scope.USER),
        )
        fields = tuple(InstallationInputField(owner, ORG) for owner in owners)

        copied = copy_artifact_answers(fields, (ArtifactAnswer(COMPANY, GITHUB, ORG.id, "acme"),))

        self.assertEqual(_answers(copied), {(owner, ORG.id): "acme" for owner in owners})
        self.assertTrue(all(isinstance(item.source, PromptedConfigValue) for item in copied))

    def test_another_artifact_and_another_alias_never_receive_it(self) -> None:
        jira, local = _owner(artifact=JIRA), _owner(source=LOCAL)
        fields = (InstallationInputField(jira, ORG), InstallationInputField(local, ORG))

        copied = copy_artifact_answers(fields, (ArtifactAnswer(COMPANY, GITHUB, ORG.id, "acme"),))

        self.assertEqual(copied, ())

    def test_set_later_leaves_the_placeholder_and_secrets_are_not_answered_here(self) -> None:
        owner = _owner()
        fields = (InstallationInputField(owner, ORG), InstallationInputField(owner, TOKEN))

        copied = copy_artifact_answers(fields, (), skip_unanswered=True)

        self.assertEqual(_answers(copied), {(owner, ORG.id): SKIPPED_INPUT})

    def test_one_artifact_answered_twice_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            copy_artifact_answers(
                (InstallationInputField(_owner(), ORG),),
                (
                    ArtifactAnswer(COMPANY, GITHUB, ORG.id, "acme"),
                    ArtifactAnswer(COMPANY, GITHUB, ORG.id, "other"),
                ),
            )


_OWNERS = st.builds(
    _owner,
    artifact=st.sampled_from((GITHUB, JIRA)),
    harness=st.sampled_from(("claude", "opencode", "tabnine")),
    scope=st.sampled_from(tuple(Scope)),
    source=st.sampled_from((COMPANY, LOCAL)),
)


class TheCopyIsExactTest(unittest.TestCase):
    @given(
        st.lists(_OWNERS, unique=True, max_size=8),
        st.dictionaries(
            st.tuples(st.sampled_from((COMPANY, LOCAL)), st.sampled_from((GITHUB, JIRA))),
            st.text("abc-", min_size=1, max_size=5),
        ),
        st.booleans(),
    )
    def test_each_installation_gets_its_own_artifacts_answer_or_nothing(
        self, owners, given_answers, skip_unanswered
    ) -> None:
        fields = tuple(InstallationInputField(owner, ORG) for owner in owners)
        answers = tuple(
            ArtifactAnswer(source, artifact, ORG.id, value)
            for (source, artifact), value in given_answers.items()
        )

        copied = _answers(copy_artifact_answers(fields, answers, skip_unanswered=skip_unanswered))

        expected = {}
        for owner in owners:
            answer = given_answers.get((owner.source, owner.artifact))
            if answer is not None:
                expected[(owner, ORG.id)] = answer
            elif skip_unanswered:
                expected[(owner, ORG.id)] = SKIPPED_INPUT
        self.assertEqual(copied, expected)


if __name__ == "__main__":
    unittest.main()
