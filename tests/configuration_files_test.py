"""The per-harness configuration file: its place, its one format and what it refuses (D-264)."""

from __future__ import annotations

import unittest

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts.domain.configuration_files import (
    ConfigurationFileRecord,
    configuration_file_path,
    configuration_value_problem,
    parse_configuration_file,
    render_configuration_file,
)
from agent_artifacts.domain.identifiers import InputId, ObjectDigest
from agent_artifacts.domain.result import Err, Ok

ROOT = "/home/someone/.aart/installations/mcp/github"
DIGEST = ObjectDigest("sha256", "a" * 64)
# Assembled so the source never holds a literal credential shape.
TOKEN_SHAPED = "ghp" + "_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"

identifiers = st.from_regex(r"\A[a-z][a-z0-9]{0,8}(-[a-z0-9]{1,4}){0,2}\Z")
values = st.text(
    st.characters(codec="utf-8", exclude_categories=("Cc", "Cf", "Cs", "Zl", "Zp")),
    min_size=1,
    max_size=40,
).filter(lambda value: configuration_value_problem(value) is None)


class WhereConfigurationLivesTest(unittest.TestCase):
    def test_each_harness_has_its_own_file_under_the_artifact_root(self):
        self.assertEqual(configuration_file_path(ROOT, "claude"), f"{ROOT}/config/claude.conf")
        self.assertNotEqual(
            configuration_file_path(ROOT, "claude"), configuration_file_path(ROOT, "opencode")
        )

    def test_a_harness_name_cannot_climb_out_of_the_artifact(self):
        for harness in ("../state", "claude/../../x", "", "Claude", "a b"):
            with self.subTest(harness=harness), self.assertRaises(ValueError):
                configuration_file_path(ROOT, harness)

    def test_a_relative_root_is_refused(self):
        with self.assertRaises(ValueError):
            configuration_file_path("installations/github", "claude")

    def test_a_record_names_its_own_harness_file_and_knows_its_root(self):
        record = ConfigurationFileRecord("claude", f"{ROOT}/config/claude.conf", DIGEST)
        self.assertEqual(record.root, ROOT)
        with self.assertRaises(ValueError):
            ConfigurationFileRecord("claude", f"{ROOT}/config/opencode.conf", DIGEST)


class TheFormatTest(unittest.TestCase):
    def test_the_file_reads_as_plain_settings_and_says_what_it_never_holds(self):
        content = render_configuration_file(
            "mcp/github",
            "claude",
            ((InputId("site"), "https://forge.example"), (InputId("org"), "acme")),
        )
        self.assertEqual(content.splitlines()[-2:], ["org=acme", "site=https://forge.example"])
        self.assertIn("credentials stay with their provider", content)
        self.assertIn("mcp/github when claude starts it", content)

    def test_a_value_that_would_be_a_shell_command_is_just_text(self):
        hostile = "acme; echo $(id) `id` 'x'"
        content = render_configuration_file("mcp/github", "claude", ((InputId("org"), hostile),))
        self.assertEqual(parse_configuration_file(content), Ok(((InputId("org"), hostile),)))

    def test_an_equals_sign_inside_a_value_stays_in_the_value(self):
        content = "org=a=b\n"
        self.assertEqual(parse_configuration_file(content), Ok(((InputId("org"), "a=b"),)))

    @given(
        st.dictionaries(identifiers, values, max_size=6),
        st.sampled_from(("claude", "codex", "opencode", "tabnine")),
    )
    def test_whatever_is_written_is_read_back_exactly(self, chosen, harness):
        pairs = tuple((InputId(key), value) for key, value in chosen.items())
        parsed = parse_configuration_file(render_configuration_file("mcp/x", harness, pairs))
        self.assertEqual(parsed, Ok(tuple(sorted(pairs, key=lambda item: item[0].value))))

    @given(st.dictionaries(identifiers, values, min_size=1, max_size=4))
    def test_equal_values_give_one_file_whatever_order_they_came_in(self, chosen):
        pairs = tuple((InputId(key), value) for key, value in chosen.items())
        self.assertEqual(
            render_configuration_file("mcp/x", "claude", pairs),
            render_configuration_file("mcp/x", "claude", tuple(reversed(pairs))),
        )


class WhatIsRefusedTest(unittest.TestCase):
    def test_a_credential_shaped_value_is_never_written(self):
        self.assertIsNotNone(configuration_value_problem(TOKEN_SHAPED))
        with self.assertRaises(ValueError):
            render_configuration_file("mcp/x", "claude", ((InputId("user"), TOKEN_SHAPED),))

    @given(st.text(min_size=1, max_size=20), st.text(min_size=1, max_size=20))
    def test_no_credential_shaped_value_survives_rendering(self, before, after):
        value = f"{before}{TOKEN_SHAPED}{after}"
        try:
            content = render_configuration_file("mcp/x", "claude", ((InputId("user"), value),))
        except ValueError:
            return
        self.fail(f"a credential-shaped value was rendered: {content!r}")

    def test_values_that_are_not_one_clean_line_are_refused(self):
        for value in ("", " acme", "acme ", "ac\nme", "ac\rme", "ac\x1b[2Jme", "ac‮me"):
            with self.subTest(value=value):
                self.assertIsNotNone(configuration_value_problem(value))

    def test_a_file_edited_into_another_shape_is_reported_not_guessed(self):
        for content, reason in (
            ("org acme\n", "is not input-id=value"),
            ("org=acme\norg=other\n", "a second time"),
            ("Org=acme\n", "is not input-id=value"),
            ("org=acme", "ends with a newline"),
            ("org= acme\n", "start or end with a space"),
            ("org=acme\r\n", "one line"),
            (f"user={TOKEN_SHAPED}\n", "looks like a credential"),
        ):
            with self.subTest(content=content):
                parsed = parse_configuration_file(content)
                self.assertIsInstance(parsed, Err)
                self.assertIn(reason, parsed.diagnostics[0].message)

    def test_comments_and_blank_lines_are_ignored(self):
        self.assertEqual(
            parse_configuration_file("# note\n\norg=acme\n"), Ok(((InputId("org"), "acme"),))
        )
        self.assertEqual(parse_configuration_file(""), Ok(()))


if __name__ == "__main__":
    unittest.main()
