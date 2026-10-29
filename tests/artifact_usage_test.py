"""CP-48: what a harness hook's payload says was used, and the ranking of uses (§212).

Only names are kept. What a tool was called with can be a secret, so no part of it may reach an
`ArtifactUse` -- that is stated as a property over generated payloads, not over three examples.
"""

from __future__ import annotations

import dataclasses
import json
import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

from aart_cli.domain.artifact_usage import (
    USAGE_HARNESSES,
    ArtifactUse,
    InstalledName,
    UsageCount,
    UsageKind,
    rank_usage,
    use_from_hook,
)

_JSON = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(max_size=20),
    lambda children: (
        st.lists(children, max_size=4) | st.dictionaries(st.text(max_size=10), children, max_size=4)
    ),
    max_leaves=12,
)


class ClaudeCodeHookTest(unittest.TestCase):
    def test_a_skill_call_is_the_skill_s_name(self) -> None:
        use = use_from_hook(
            "claude",
            {
                "tool_name": "Skill",
                "tool_input": {"skill": "code-review", "args": "the diff"},
                "cwd": "/work/shop",
            },
        )

        self.assertEqual(use, ArtifactUse("claude", UsageKind.SKILL, "code-review", "/work/shop"))

    def test_an_mcp_call_is_the_server_s_name(self) -> None:
        use = use_from_hook(
            "claude",
            {"tool_name": "mcp__github__search_repositories", "tool_input": {"q": "x"}},
        )

        self.assertEqual(use, ArtifactUse("claude", UsageKind.MCP, "github"))

    def test_any_other_tool_is_no_use(self) -> None:
        for tool in ("Bash", "Read", "mcp__", "Skills", "skill"):
            with self.subTest(tool=tool):
                self.assertIsNone(
                    use_from_hook("claude", {"tool_name": tool, "tool_input": {"skill": "x"}})
                )

    def test_a_relative_or_missing_directory_is_no_project(self) -> None:
        use = use_from_hook(
            "claude", {"tool_name": "Skill", "tool_input": {"skill": "s"}, "cwd": "work"}
        )

        self.assertEqual(use, ArtifactUse("claude", UsageKind.SKILL, "s", ""))


class OpencodePluginTest(unittest.TestCase):
    def test_the_skill_tool_is_the_skill_s_name(self) -> None:
        use = use_from_hook(
            "opencode", {"tool": "skill", "skill": "git-release", "directory": "/w"}
        )

        self.assertEqual(use, ArtifactUse("opencode", UsageKind.SKILL, "git-release", "/w"))

    def test_a_tool_with_an_underscore_is_kept_whole_as_an_mcp_tool(self) -> None:
        use = use_from_hook("opencode", {"tool": "jira_search_issues"})

        self.assertEqual(use, ArtifactUse("opencode", UsageKind.MCP, "jira_search_issues"))

    def test_opencode_s_own_tools_are_no_use(self) -> None:
        for tool in ("bash", "read", "todowrite", "_", "__", "skill"):
            with self.subTest(tool=tool):
                self.assertIsNone(use_from_hook("opencode", {"tool": tool}))


class NothingButNamesTest(unittest.TestCase):
    @settings(max_examples=300)
    @given(
        harness=st.sampled_from((*USAGE_HARNESSES, "tabnine", "")),
        payload=_JSON,
        arguments=_JSON,
    )
    def test_what_a_tool_was_called_with_never_reaches_a_use(
        self, harness: str, payload: object, arguments: object
    ) -> None:
        held = "argument-value-never-kept"
        if isinstance(payload, dict):
            payload = {**payload, "tool_input": {"skill": "s", "token": held, "x": arguments}}
            payload.setdefault("args", {"token": held})
        use = use_from_hook(harness, payload)

        if use is not None:
            self.assertIn(use.harness, USAGE_HARNESSES)
            self.assertNotIn(held, json.dumps(dataclasses.astuple(use), default=str))


class RecordingHarnessesTest(unittest.TestCase):
    def test_tabnine_cannot_record_usage(self) -> None:
        self.assertNotIn("tabnine", USAGE_HARNESSES)


_NAMES = (
    InstalledName("claude", UsageKind.SKILL, "code-review", "company/skill/code-review"),
    InstalledName("claude", UsageKind.MCP, "github", "company/mcp/github"),
    InstalledName("opencode", UsageKind.MCP, "jira", "company/mcp/jira"),
    InstalledName("opencode", UsageKind.MCP, "jira_cloud", "company/mcp/jira-cloud"),
)


class RankingTest(unittest.TestCase):
    def test_most_used_first_and_names_resolved_to_what_is_installed(self) -> None:
        ranking = rank_usage(
            (
                UsageCount(
                    "claude", UsageKind.SKILL, "code-review", 3, "2026-10-28T10:00:00+00:00"
                ),
                UsageCount("claude", UsageKind.MCP, "github", 7, "2026-10-27T10:00:00+00:00"),
                UsageCount(
                    "claude", UsageKind.MCP, "someone-elses", 1, "2026-10-28T11:00:00+00:00"
                ),
            ),
            _NAMES,
        )

        self.assertEqual(
            [(item.artifact, item.uses, item.installed) for item in ranking],
            [
                ("company/mcp/github", 7, True),
                ("company/skill/code-review", 3, True),
                ("someone-elses", 1, False),
            ],
        )

    def test_an_opencode_tool_is_its_longest_installed_server(self) -> None:
        ranking = rank_usage(
            (
                UsageCount("opencode", UsageKind.MCP, "jira_cloud_search", 2, "2026-10-28T10:00Z"),
                UsageCount("opencode", UsageKind.MCP, "jira_search", 1, "2026-10-28T09:00Z"),
            ),
            _NAMES,
        )

        self.assertEqual(
            [(item.artifact, item.uses) for item in ranking],
            [("company/mcp/jira-cloud", 2), ("company/mcp/jira", 1)],
        )

    def test_tools_of_one_server_add_up_to_one_line(self) -> None:
        ranking = rank_usage(
            (
                UsageCount("opencode", UsageKind.MCP, "jira_search", 2, "2026-10-27T10:00Z"),
                UsageCount("opencode", UsageKind.MCP, "jira_get", 3, "2026-10-28T10:00Z"),
            ),
            _NAMES,
        )

        self.assertEqual(
            [(item.artifact, item.uses, item.last_used) for item in ranking],
            [("company/mcp/jira", 5, "2026-10-28T10:00Z")],
        )

    def test_one_artifact_in_two_harnesses_is_two_lines(self) -> None:
        names = (
            *_NAMES,
            InstalledName("opencode", UsageKind.SKILL, "code-review", "company/skill/code-review"),
        )
        ranking = rank_usage(
            (
                UsageCount("claude", UsageKind.SKILL, "code-review", 1, "2026-10-28T10:00Z"),
                UsageCount("opencode", UsageKind.SKILL, "code-review", 1, "2026-10-28T10:00Z"),
            ),
            names,
        )

        self.assertEqual(sorted(item.harness for item in ranking), ["claude", "opencode"])

    @given(
        st.lists(
            st.builds(
                UsageCount,
                st.sampled_from(USAGE_HARNESSES),
                st.sampled_from(tuple(UsageKind)),
                st.sampled_from(("code-review", "github", "jira_search", "other_x", "x")),
                st.integers(min_value=1, max_value=50),
                st.sampled_from(("2026-10-27T10:00Z", "2026-10-28T10:00Z")),
            ),
            max_size=12,
        )
    )
    def test_the_ranking_keeps_every_use_and_never_rises(self, counts: list[UsageCount]) -> None:
        ranking = rank_usage(tuple(counts), _NAMES)

        self.assertEqual(sum(item.uses for item in ranking), sum(item.uses for item in counts))
        self.assertEqual(
            [item.uses for item in ranking], sorted((item.uses for item in ranking), reverse=True)
        )


if __name__ == "__main__":
    unittest.main()
