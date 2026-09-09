"""Every measured harness must be able to read back the registration it was written.

`registration_entry` writes one harness's spelling and `registered_command` reads it. Nothing
forces the two to agree, and disagreement is quiet in the worst way: the settings file is correct,
the harness starts the server, and AART still observes the registration as missing -- so status
reports drift forever and repair rewrites a file that was already right.

That is not hypothetical. It is what `opencode.json` did the moment a second spelling existed, and
it went unnoticed because the reader had only ever been given the one shape it understood. The
claim is universal over harnesses, shapes, launchers and arguments, so it is stated that way.
"""

from __future__ import annotations

import unittest

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts.domain.harness import (
    MCP_TARGETS,
    McpEntryShape,
    McpRegistration,
    registered_command,
    registration_entry,
)

_TARGETS = sorted(MCP_TARGETS.values(), key=lambda target: (target.harness, target.scope.value))

#: Absolute, no NUL and no newline -- what `McpRegistration` already refuses anything else for.
_COMMANDS = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00\r\n/"),
    min_size=1,
    max_size=40,
).map(lambda tail: f"/{tail}")

_ARGUMENTS = st.lists(
    st.text(
        alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
        min_size=1,
        max_size=20,
    ),
    max_size=4,
).map(tuple)


class RegistrationRoundTripTest(unittest.TestCase):
    @given(target=st.sampled_from(_TARGETS), command=_COMMANDS, arguments=_ARGUMENTS)
    def test_every_harness_reads_back_the_launcher_it_was_written(self, target, command, arguments):
        registration = McpRegistration(target, "probe", command, arguments)

        entry = registration_entry(registration)

        self.assertEqual(command, registered_command(target, entry))

    @given(target=st.sampled_from(_TARGETS), command=_COMMANDS, arguments=_ARGUMENTS)
    def test_the_arguments_survive_the_shape_that_carries_them(self, target, command, arguments):
        """Whichever spelling, everything the launcher is given has to still be there."""

        entry = registration_entry(McpRegistration(target, "probe", command, arguments))

        if target.entry_shape is McpEntryShape.TYPED_COMMAND_VECTOR:
            self.assertEqual([command, *arguments], entry["command"])
        else:
            self.assertEqual(command, entry["command"])
            self.assertEqual(list(arguments), list(entry.get("args", ())))

    def test_an_entry_that_is_not_the_shape_this_harness_writes_reads_as_nothing(self) -> None:
        """A file somebody hand-edited into another harness's spelling is drift, not a launcher."""

        for target in _TARGETS:
            wrong = (
                {"command": "/opt/server"}
                if target.entry_shape is McpEntryShape.TYPED_COMMAND_VECTOR
                else {"command": ["/opt/server"], "type": "local"}
            )
            self.assertIsNone(registered_command(target, wrong), target.harness)

    def test_an_empty_vector_names_no_launcher(self) -> None:
        vector = next(
            target
            for target in _TARGETS
            if target.entry_shape is McpEntryShape.TYPED_COMMAND_VECTOR
        )

        self.assertIsNone(registered_command(vector, {"command": [], "type": "local"}))

    def test_an_entry_that_is_not_an_object_names_no_launcher(self) -> None:
        for target in _TARGETS:
            self.assertIsNone(registered_command(target, "/opt/server"))
            self.assertIsNone(registered_command(target, None))


if __name__ == "__main__":
    unittest.main()
