"""CP-48: what a harness hook's payload says was used, and the ranking of uses (§212).

Only names are kept. What a tool was called with can be a secret, so no part of it may reach an
`ArtifactUse` -- that is stated as a property over generated payloads, not over three examples.
"""

from __future__ import annotations

import dataclasses
import json
import re
import unittest

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from aart_cli.domain.artifact_usage import (
    HARNESS_VERSION_PATTERN,
    USAGE_HARNESSES,
    ArtifactUse,
    InstalledName,
    UsageCount,
    UsageKind,
    harness_version_from_hook,
    rank_usage,
    use_from_hook,
)

#: mutmut runs these from another executor than unittest does.
_MUTATION = (HealthCheck.differing_executors,)

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

    def test_an_mcp_call_is_the_server_s_name_and_the_tool_it_called(self) -> None:
        use = use_from_hook(
            "claude",
            {"tool_name": "mcp__github__search_repositories", "tool_input": {"q": "x"}},
        )

        self.assertEqual(
            use, ArtifactUse("claude", UsageKind.MCP, "github", tool="search_repositories")
        )

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

    def test_an_mcp_tool_is_its_server_with_the_tool_beside_it(self) -> None:
        use = use_from_hook("opencode", {"tool": "jira_search_issues", "server": "jira"})

        self.assertEqual(use, ArtifactUse("opencode", UsageKind.MCP, "jira", tool="search_issues"))

    def test_a_server_name_opencode_rewrote_still_names_its_tools(self) -> None:
        use = use_from_hook("opencode", {"tool": "my_jira_search", "server": "my.jira"})

        self.assertEqual(use, ArtifactUse("opencode", UsageKind.MCP, "my.jira", tool="search"))

    def test_a_tool_no_server_is_named_for_is_no_use_underscore_or_not(self) -> None:
        # B-277: a built-in and a plugin's `<file>_<export>` have underscores too.
        for payload in (
            {"tool": "experimental_image_generate"},
            {"tool": "notes_append"},
            {"tool": "jira_search", "server": "github"},
            {"tool": "jira_", "server": "jira"},
            {"tool": "jira_search", "server": 7},
        ):
            with self.subTest(payload=payload):
                self.assertIsNone(use_from_hook("opencode", payload))

    @settings(suppress_health_check=_MUTATION)
    @given(
        server=st.from_regex(r"[a-z][a-z0-9.-]{0,20}", fullmatch=True),
        called=st.from_regex(r"[a-z][a-z0-9_]{0,20}", fullmatch=True),
    )
    def test_any_server_s_tool_is_that_server_s_use(self, server: str, called: str) -> None:
        tool = server.replace(".", "_") + "_" + called

        use = use_from_hook("opencode", {"tool": tool, "server": server})

        self.assertEqual(use, ArtifactUse("opencode", UsageKind.MCP, server, tool=called))

    def test_opencode_s_own_tools_are_no_use(self) -> None:
        for tool in ("bash", "read", "todowrite", "_", "__", "skill"):
            with self.subTest(tool=tool):
                self.assertIsNone(use_from_hook("opencode", {"tool": tool}))

    def test_opencode_2_s_own_namespaced_tools_are_no_use(self) -> None:
        """OpenCode 2 names its own tools `opencode_<tool>`, which an MCP tool's shape fits (D-520);
        measured on 2.1.3, whose `opencode_list_mcp_resources` reached the hook beside an MCP
        call. No server is named for them."""

        for tool in (
            "opencode_list_mcp_resources",
            "opencode_read_mcp_resource",
            "opencode_schedule_create",
            "opencode_worktree_list",
        ):
            with self.subTest(tool=tool):
                self.assertIsNone(use_from_hook("opencode", {"tool": tool}))
        self.assertEqual(
            use_from_hook("opencode", {"tool": "opencodex_search", "server": "opencodex"}),
            ArtifactUse("opencode", UsageKind.MCP, "opencodex", tool="search"),
        )


#: The pattern as the brief and the contract write it, held apart from the code's (D-536).
_CONTRACT_VERSION = r"^[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,6}(?:[-+][0-9A-Za-z.\-]{1,32})?$"
_NOT_VERSIONS = (
    "",
    "latest",
    "v2.3.2",
    "2.3",
    "2",
    "2.x",
    "unknown",
    "/Users/someone/.opencode/bin/opencode-v2.3.2",
    "2.3.2; x",
    "2.3.2\n",
    " 2.3.2",
    "2.3.2-",
    "2.3.2-" + "a" * 33,
    "12345.0.0",
    "2.3.2-beta 1",
    "2" * 200,
)


class HarnessVersionTest(unittest.TestCase):
    def test_the_pattern_is_the_contract_s(self) -> None:
        self.assertEqual(HARNESS_VERSION_PATTERN, _CONTRACT_VERSION)

    def test_a_version_opencode_reported_is_kept(self) -> None:
        for version in ("2.3.2", "2.4.0-beta.1", "2.3.2+build.7", "0.0.0-beta-19271", "1.19.5"):
            with self.subTest(version=version):
                self.assertEqual(
                    harness_version_from_hook("opencode", {"harness_version": version}), version
                )

    def test_anything_else_is_no_version(self) -> None:
        for value in (*_NOT_VERSIONS, None, 232, 2.3, True, ["2.3.2"], {"version": "2.3.2"}):
            with self.subTest(value=value):
                self.assertIsNone(harness_version_from_hook("opencode", {"harness_version": value}))
        self.assertIsNone(harness_version_from_hook("opencode", {}))
        self.assertIsNone(harness_version_from_hook("opencode", "2.3.2"))
        # Claude Code's hook says none; a payload that claims one is not believed.
        self.assertIsNone(harness_version_from_hook("claude", {"harness_version": "2.3.2"}))

    def test_a_use_holds_a_version_or_none(self) -> None:
        use = ArtifactUse("opencode", UsageKind.SKILL, "review", harness_version="2.3.2")
        self.assertEqual(use.harness_version, "2.3.2")
        for value in _NOT_VERSIONS[1:]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                ArtifactUse("opencode", UsageKind.SKILL, "review", harness_version=value)

    @settings(suppress_health_check=_MUTATION, max_examples=300)
    @given(
        value=_JSON
        | st.text(alphabet="0123456789.-+abcVx/ ;", max_size=70)
        | st.from_regex(_CONTRACT_VERSION, fullmatch=True)
    )
    def test_any_value_is_a_contract_version_or_none_and_never_raises(self, value: object) -> None:
        said = harness_version_from_hook("opencode", {"tool": "skill", "harness_version": value})

        expected = (
            isinstance(value, str)
            and len(value) <= 64
            and re.fullmatch(_CONTRACT_VERSION, value) is not None
        )
        self.assertEqual(said, value if expected else None)


class NothingButNamesTest(unittest.TestCase):
    @settings(suppress_health_check=_MUTATION, max_examples=300)
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

    @settings(suppress_health_check=_MUTATION)
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
