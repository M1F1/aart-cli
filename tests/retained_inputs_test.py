"""§38, INV-196, B-261: what an installation holds is bound again for that installation only.

`retained_input_sources` keeps a stored value for the field of the same complete identity, and for
nothing else. `command_line_sources` orders what one command binds: a flag, then the value held,
then the declared default, then (with Set later) the placeholder. Neither a default nor the
placeholder ever replaces a value an installation holds.
"""

from __future__ import annotations

import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.command_line_inputs import command_line_sources
from aart_cli.application.installation_inputs import (
    ArtifactAnswer,
    InstallationInputField,
    OwnedInputSource,
    retained_input_sources,
    with_retained,
)
from aart_cli.domain.harness import Scope
from aart_cli.domain.identifiers import ArtifactIdentity, InputId, SourceAlias
from aart_cli.domain.inputs import (
    SKIPPED_INPUT,
    ConfigInput,
    EnvironmentBinding,
    InputValidation,
    PromptedConfigValue,
    SecretInput,
)
from aart_cli.domain.installation_owner import InstallationOwner

WORKSPACE = ConfigInput(InputId("workspace"), EnvironmentBinding("WORKSPACE"))
REGION = ConfigInput(InputId("region"), EnvironmentBinding("REGION"), default="westeurope")
NOTE = ConfigInput(InputId("note"), EnvironmentBinding("NOTE"), required=False)
TOKEN = SecretInput(InputId("token"), EnvironmentBinding("TOKEN"))
WAREHOUSE = ArtifactIdentity("mcp", "warehouse")
COMPANY = SourceAlias("company")


def _owner(harness="claude", scope=Scope.PROJECT, root="/work/shop", source=COMPANY):
    return InstallationOwner(source, WAREHOUSE, scope, root, harness)


def _bound(sources) -> dict:
    return {(item.owner, item.source.input): item.source.value for item in sources}


class OnlyTheSameInstallationKeepsItsValueTest(unittest.TestCase):
    def test_a_value_is_kept_for_its_own_installation(self) -> None:
        owner = _owner()
        fields = (InstallationInputField(owner, WORKSPACE),)

        kept = retained_input_sources(fields, ((owner, ((WORKSPACE.id, "analytics"),)),))

        self.assertEqual(_bound(kept), {(owner, WORKSPACE.id): "analytics"})
        self.assertIsInstance(kept[0].source, PromptedConfigValue)

    def test_no_other_installation_receives_it(self) -> None:
        held = _owner()
        for other in (
            _owner(harness="opencode"),
            _owner(scope=Scope.USER),
            _owner(root="/work/other"),
            _owner(source=SourceAlias("local")),
        ):
            with self.subTest(other=other):
                fields = (InstallationInputField(other, WORKSPACE),)

                kept = retained_input_sources(fields, ((held, ((WORKSPACE.id, "analytics"),)),))

                self.assertEqual(kept, ())

    def test_the_placeholder_a_refused_value_a_credential_and_an_undeclared_input_keep_nothing(
        self,
    ) -> None:
        owner = _owner()
        strict = ConfigInput(
            InputId("workspace"),
            EnvironmentBinding("WORKSPACE"),
            validation=InputValidation("pattern", "^ws-[a-z]+$"),
        )
        cases = (
            (WORKSPACE, SKIPPED_INPUT),
            (strict, "analytics"),
            (SecretInput(InputId("workspace"), EnvironmentBinding("WORKSPACE")), "analytics"),
        )
        for declared, value in cases:
            with self.subTest(declared=declared, value=value):
                fields = (InstallationInputField(owner, declared),)
                self.assertEqual(
                    retained_input_sources(fields, ((owner, ((WORKSPACE.id, value),)),)), ()
                )
        fields = (InstallationInputField(owner, REGION),)
        self.assertEqual(
            retained_input_sources(fields, ((owner, ((WORKSPACE.id, "analytics"),)),)), ()
        )

    def test_a_value_the_stricter_rule_still_accepts_is_kept(self) -> None:
        owner = _owner()
        strict = ConfigInput(
            InputId("workspace"),
            EnvironmentBinding("WORKSPACE"),
            validation=InputValidation("pattern", "^ws-[a-z]+$"),
        )

        kept = retained_input_sources(
            (InstallationInputField(owner, strict),), ((owner, ((WORKSPACE.id, "ws-data"),)),)
        )

        self.assertEqual(_bound(kept), {(owner, WORKSPACE.id): "ws-data"})


class WhatOneCommandBindsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.owner = _owner()
        self.fields = tuple(
            InstallationInputField(self.owner, item) for item in (WORKSPACE, REGION, NOTE, TOKEN)
        )

    def _kept(self, **values: str) -> tuple[OwnedInputSource, ...]:
        return tuple(
            OwnedInputSource(self.owner, PromptedConfigValue(InputId(key), value))
            for key, value in values.items()
        )

    def test_a_held_value_beats_the_default_and_the_placeholder(self) -> None:
        bound = command_line_sources(
            self.fields, (), retained=self._kept(region="northeurope"), set_later=True
        )

        self.assertEqual(
            _bound(bound),
            {(self.owner, WORKSPACE.id): SKIPPED_INPUT, (self.owner, REGION.id): "northeurope"},
        )

    def test_a_flag_beats_a_held_value(self) -> None:
        bound = command_line_sources(
            self.fields,
            (ArtifactAnswer(COMPANY, WAREHOUSE, WORKSPACE.id, "finance"),),
            retained=self._kept(workspace="analytics"),
        )

        self.assertEqual(
            _bound(bound),
            {(self.owner, WORKSPACE.id): "finance", (self.owner, REGION.id): "westeurope"},
        )

    def test_without_anything_held_it_is_what_install_always_bound(self) -> None:
        bound = command_line_sources(self.fields, (), set_later=True)

        self.assertEqual(
            _bound(bound),
            {(self.owner, WORKSPACE.id): SKIPPED_INPUT, (self.owner, REGION.id): "westeurope"},
        )

    def test_a_held_optional_value_is_kept(self) -> None:
        bound = command_line_sources(self.fields, (), retained=self._kept(note="read only"))

        self.assertEqual(_bound(bound)[(self.owner, NOTE.id)], "read only")


_VALUES = st.text(alphabet="abcdefghij-", min_size=1, max_size=8)


@given(
    held=st.dictionaries(st.sampled_from(("workspace", "region", "note")), _VALUES),
    flagged=st.dictionaries(st.sampled_from(("workspace", "region", "note")), _VALUES),
    set_later=st.booleans(),
)
def test_each_field_is_bound_once_and_by_the_strongest_source(held, flagged, set_later) -> None:
    """INV-196 over every mix: a flag wins, then what is held; nothing replaces either."""

    owner = _owner()
    fields = tuple(InstallationInputField(owner, item) for item in (WORKSPACE, REGION, NOTE, TOKEN))
    retained = tuple(
        OwnedInputSource(owner, PromptedConfigValue(InputId(key), value))
        for key, value in held.items()
    )
    answers = tuple(
        ArtifactAnswer(COMPANY, WAREHOUSE, InputId(key), value) for key, value in flagged.items()
    )

    bound = command_line_sources(fields, answers, retained=retained, set_later=set_later)

    keys = [(item.owner, item.source.input) for item in bound]
    assert len(keys) == len(set(keys))
    values = {key[1].value: item.source.value for key, item in zip(keys, bound, strict=True)}
    for key in ("workspace", "region", "note"):
        if key in flagged:
            assert values[key] == flagged[key]
        elif key in held:
            assert values[key] == held[key]
    assert "token" not in values
    assert with_retained((), retained) == retained


if __name__ == "__main__":
    unittest.main()
