"""CP-47: a newer aart-cli that a Registry runs is announced, with how to install it (§211).

The owner: say when the Registry runs a newer aart-cli than the one in use, and how to upgrade, in
the way the organisation supplies aart-cli -- a package index, a wheel, or a Git checkout -- not
one way that does not work everywhere. The Registry's pin says which version; its committed
`.aart-cli-source` says where from, in the names of its CI's own variables.
"""

from __future__ import annotations

import shlex
import string
import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.aart_cli_update import (
    SOURCE_NAMES,
    Installer,
    RegistryPin,
    RunningAartCli,
    aart_cli_update,
    detect_installer,
    governing_pin,
    parse_aart_cli_source,
    upgrade_guidance,
)
from aart_cli.domain.result import Err, Ok
from aart_cli.protocol.semver import SemVer, parse_semver
from tests.credential_fixtures import credential_url

PYTHON = "/home/someone/.local/pipx/venvs/aart-cli/bin/python"
NEXUS = "https://nexus.example.test/repository/pypi/simple"


def _semver(raw: str) -> SemVer:
    parsed = parse_semver(raw)
    assert isinstance(parsed, Ok), raw
    return parsed.value


def _running(
    version: str = "0.20.0", installer: Installer = Installer.PIPX, checkout: str = ""
) -> RunningAartCli:
    return RunningAartCli(_semver(version), PYTHON, installer, checkout)


def _pin(
    alias: str = "corp",
    pin: str = "0.21.0",
    source: str | None = None,
    origin: str = "https://ghe.example.test/platform/aart-registry.git",
) -> RegistryPin:
    return RegistryPin(alias, pin, origin, None if source is None else source.encode())


def _commands(pins: tuple[RegistryPin, ...], running: RunningAartCli) -> tuple[str, ...]:
    update = aart_cli_update(pins, running, default_alias="")
    assert update is not None
    return tuple(command for step in update.steps for command in step.commands)


_versions = st.tuples(
    st.integers(min_value=0, max_value=3),
    st.integers(min_value=0, max_value=3),
    st.integers(min_value=0, max_value=3),
).map(lambda parts: ".".join(map(str, parts)))


class GoverningPinTest(unittest.TestCase):
    @given(
        st.dictionaries(st.sampled_from("abcde"), _versions, max_size=5),
        _versions,
        st.sampled_from(("", "a", "c", "z")),
    )
    def test_the_default_registry_s_pin_governs_else_the_highest_then_the_first_alias(
        self, pinned: dict[str, str], running: str, default: str
    ) -> None:
        pins = tuple(_pin(alias, version) for alias, version in pinned.items())

        chosen = governing_pin(pins, _semver(running), default_alias=default)

        # An oracle written apart from the code: the default Registry decides when it is here;
        # otherwise the highest pin, the first alias among equals.
        if default in pinned:
            expected_alias = default
        elif pinned:
            highest = max(_semver(version) for version in pinned.values())
            expected_alias = min(a for a, v in pinned.items() if _semver(v) == highest)
        else:
            expected_alias = None
        newer = expected_alias is not None and _semver(pinned[expected_alias]) > _semver(running)
        if not newer:
            self.assertIsNone(chosen)
            return
        assert chosen is not None
        self.assertEqual(
            (chosen[0].alias, str(chosen[1])), (expected_alias, pinned[expected_alias])
        )

    def test_build_metadata_is_not_a_newer_version(self) -> None:
        self.assertIsNone(
            governing_pin((_pin(pin="0.20.0"),), _semver("0.20.0+corp"), default_alias="")
        )

    def test_a_pin_is_read_as_the_ci_reads_it_and_an_unreadable_one_is_nothing(self) -> None:
        chosen = governing_pin(
            (_pin("a", " 0.21.0\r\n"), _pin("b", "v0.30.0"), _pin("c", "")),
            _semver("0.20.0"),
            default_alias="",
        )

        assert chosen is not None
        self.assertEqual((chosen[0].alias, str(chosen[1])), ("a", "0.21.0"))

    def test_an_unreadable_default_pin_leaves_the_choice_to_the_others(self) -> None:
        chosen = governing_pin(
            (_pin("corp", "next"), _pin("team", "0.21.0")), _semver("0.20.0"), default_alias="corp"
        )

        assert chosen is not None
        self.assertEqual(chosen[0].alias, "team")


class DetectInstallerTest(unittest.TestCase):
    def test_each_installer_is_told_apart_by_where_it_put_aart_cli(self) -> None:
        cases = {
            ("/home/someone/.local/pipx/venvs/aart-cli", ""): Installer.PIPX,
            ("/Users/someone/.local/share/uv/tools/aart-cli", ""): Installer.UV,
            ("/home/someone/venv", ""): Installer.PIP,
            ("/home/someone/venv", "/home/someone/aart-cli"): Installer.EDITABLE,
            ("/home/someone/.local/pipx/venvs/aart-cli", "/home/someone/aart-cli"): (
                Installer.EDITABLE
            ),
        }
        for (prefix, checkout), expected in cases.items():
            with self.subTest(prefix=prefix, checkout=checkout):
                self.assertIs(detect_installer(prefix, checkout), expected)

    def test_a_moved_pipx_or_uv_home_is_told_by_the_file_each_leaves(self) -> None:
        """`PIPX_HOME` and `UV_TOOL_DIR` move the environment anywhere; the lab found one."""

        cases = {
            frozenset({"pipx_metadata.json"}): Installer.PIPX,
            frozenset({"uv-receipt.toml"}): Installer.UV,
            frozenset(): Installer.PIP,
        }
        for marks, expected in cases.items():
            with self.subTest(marks=marks):
                self.assertIs(
                    detect_installer("/srv/tools/home/venvs/aart-cli", "", marks), expected
                )


_names = st.sampled_from(SOURCE_NAMES)
_safe_values = st.text(
    alphabet=string.ascii_letters + string.digits + "-_./:=+{}", min_size=1, max_size=30
).filter(lambda value: "://" not in value)


class ParseSourceTest(unittest.TestCase):
    @given(st.dictionaries(_names, _safe_values, min_size=1))
    def test_every_known_name_is_read_back_with_comments_and_blank_lines_ignored(
        self, values: dict[str, str]
    ) -> None:
        text = "# where aart-cli comes from\n\n" + "".join(
            f"{name} = {value}\r\n" for name, value in values.items()
        )

        parsed = parse_aart_cli_source(text.encode())

        assert isinstance(parsed, Ok), parsed
        self.assertEqual(parsed.value, values)

    @given(
        st.dictionaries(_names, _safe_values, max_size=3),
        st.sampled_from(
            (
                "AART_CLI_REF=main",
                "export AART_CLI_PACKAGE=aart-cli",
                "AART_CLI_PACKAGE",
                'AART_CLI_PACKAGE="aart-cli"',
                "AART_CLI_WHEEL_URL=https://someone@files.example.test/aart.whl",
                "AART_CLI_PIP_INDEX_URL=" + credential_url("nexus.example.test", "/simple"),
                "AART_CLI_PACKAGE=aart-cli @ https://someone@files.example.test/aart.whl",
                "AART_CLI_TOOL_URL="
                + credential_url("ghe.example.test", "/platform/aart-cli.git", scheme="ssh"),
                "AART_CLI_TOOL_PATH=/opt/aart\tcli",
            )
        ),
        st.integers(min_value=0, max_value=3),
    )
    def test_one_bad_line_refuses_the_whole_file_with_a_reason(
        self, values: dict[str, str], bad: str, where: int
    ) -> None:
        lines = [f"{name}={value}" for name, value in values.items()]
        lines.insert(min(where, len(lines)), bad)

        parsed = parse_aart_cli_source("\n".join(lines).encode())

        assert isinstance(parsed, Err), (lines, parsed)
        self.assertTrue(parsed.diagnostics[0].message)

    def test_a_repeated_name_is_refused(self) -> None:
        parsed = parse_aart_cli_source(b"AART_CLI_PACKAGE=a\nAART_CLI_PACKAGE=b\n")

        assert isinstance(parsed, Err)
        self.assertIn("AART_CLI_PACKAGE", parsed.diagnostics[0].message)

    def test_an_ssh_user_name_is_not_a_credential(self) -> None:
        parsed = parse_aart_cli_source(b"AART_CLI_TOOL_URL=git@ghe.example.test:platform/aart.git")

        self.assertIsInstance(parsed, Ok)


class RoutesTest(unittest.TestCase):
    def test_the_package_index_route_for_each_installer(self) -> None:
        source = f"AART_CLI_PIP_INDEX_URL={NEXUS}\nAART_CLI_PACKAGE=aart-cli=={{version}}\n"
        expected = {
            Installer.PIPX: (f"pipx install --force --index-url {NEXUS} aart-cli==0.21.0",),
            Installer.UV: (f"uv tool install --force --default-index {NEXUS} aart-cli==0.21.0",),
            Installer.PIP: (
                f"{PYTHON} -m pip install --upgrade --no-deps --index-url {NEXUS} aart-cli==0.21.0",
            ),
        }
        for installer, commands in expected.items():
            with self.subTest(installer=installer):
                self.assertEqual(
                    _commands((_pin(source=source),), _running(installer=installer)), commands
                )

    def test_a_package_with_no_index_comes_from_pypi_as_in_ci(self) -> None:
        commands = _commands((_pin(source="AART_CLI_PACKAGE=aart-cli=={version}"),), _running())

        self.assertEqual(
            commands, ("pipx install --force --index-url https://pypi.org/simple aart-cli==0.21.0",)
        )

    def test_the_wheel_route_expands_every_version_and_offers_a_downloaded_wheel(self) -> None:
        url = "https://files.example.test/v{version}/aart_cli-{version}-py3-none-any.whl"
        update = aart_cli_update(
            (_pin(source=f"AART_CLI_WHEEL_URL={url}"),),
            _running(installer=Installer.UV),
            default_alias="",
        )

        assert update is not None
        expanded = url.replace("{version}", "0.21.0")
        self.assertEqual(update.steps[0].commands, (f"uv tool install --force {expanded}",))
        self.assertEqual(update.steps[1].commands, ("aart-cli upgrade --wheel FILE",))
        self.assertIn("sign-in", update.steps[1].says)

    def test_the_git_route_from_the_registry_s_own_host(self) -> None:
        commands = _commands(
            (_pin(source="AART_CLI_REPOSITORY=platform/aart-cli"),),
            _running(installer=Installer.PIP),
        )

        self.assertEqual(
            commands,
            (
                f"{PYTHON} -m pip install --upgrade --no-deps "
                "git+https://ghe.example.test/platform/aart-cli.git@v0.21.0",
            ),
        )

    def test_an_ssh_registry_gives_an_ssh_address_pip_can_read(self) -> None:
        commands = _commands(
            (
                _pin(
                    source="AART_CLI_REPOSITORY=platform/aart-cli",
                    origin="git@ghe.example.test:platform/aart-registry.git",
                ),
            ),
            _running(),
        )

        self.assertEqual(
            commands,
            ("pipx install --force git+ssh://git@ghe.example.test/platform/aart-cli.git@v0.21.0",),
        )

    def test_a_tool_url_wins_over_a_repository_as_in_ci(self) -> None:
        source = (
            "AART_CLI_REPOSITORY=platform/aart-cli\n"
            "AART_CLI_TOOL_URL=https://git.example.test/tools/aart-cli.git\n"
        )

        self.assertEqual(
            _commands((_pin(source=source),), _running()),
            ("pipx install --force git+https://git.example.test/tools/aart-cli.git@v0.21.0",),
        )

    def test_a_repository_on_a_local_registry_cannot_be_placed(self) -> None:
        update = aart_cli_update(
            (_pin(source="AART_CLI_REPOSITORY=platform/aart-cli", origin="/work/registry"),),
            _running(),
            default_alias="",
        )

        assert update is not None
        self.assertEqual(tuple(c for s in update.steps for c in s.commands), ())
        self.assertIn("AART_CLI_TOOL_URL", "\n".join(s.says for s in update.steps))

    def test_the_first_route_set_wins_in_the_ci_s_order(self) -> None:
        source = (
            "AART_CLI_TOOL_URL=https://git.example.test/tools/aart-cli.git\n"
            "AART_CLI_TOOL_PATH=/opt/aart\n"
            "AART_CLI_WHEEL_URL=https://files.example.test/aart.whl\n"
            "AART_CLI_PACKAGE=aart-cli=={version}\n"
        )

        self.assertIn("--index-url", _commands((_pin(source=source),), _running())[0])

    def test_an_empty_value_is_unset(self) -> None:
        source = "AART_CLI_PACKAGE=\nAART_CLI_WHEEL_URL=https://files.example.test/aart.whl\n"

        self.assertEqual(
            _commands((_pin(source=source),), _running())[0],
            "pipx install --force https://files.example.test/aart.whl",
        )

    def test_a_runner_directory_gives_no_command(self) -> None:
        update = aart_cli_update(
            (_pin(source="AART_CLI_TOOL_PATH=/opt/aart"),), _running(), default_alias=""
        )

        assert update is not None
        self.assertEqual(tuple(c for s in update.steps for c in s.commands), ())
        self.assertIn("maintainers", update.steps[0].says)

    def test_no_file_still_announces_and_says_what_a_maintainer_can_add(self) -> None:
        update = aart_cli_update((_pin(),), _running(), default_alias="")

        assert update is not None
        self.assertEqual((update.available, update.registry), ("0.21.0", "corp"))
        self.assertEqual(tuple(c for s in update.steps for c in s.commands), ())
        self.assertIn(".aart-cli-source", update.steps[0].says)

    def test_a_refused_file_gives_its_reason_and_no_command(self) -> None:
        update = aart_cli_update(
            (
                _pin(
                    source="AART_CLI_PIP_INDEX_URL="
                    + credential_url("nexus.example.test", "/simple")
                    + "\nAART_CLI_PACKAGE=aart-cli"
                ),
            ),
            _running(),
            default_alias="",
        )

        assert update is not None
        self.assertEqual(tuple(c for s in update.steps for c in s.commands), ())
        said = "\n".join(s.says for s in update.steps)
        self.assertIn("credential", said)
        self.assertNotIn("secret", said)

    def test_an_editable_checkout_moves_to_the_tag_whatever_the_file_says(self) -> None:
        for source in (None, f"AART_CLI_PACKAGE=aart-cli\nAART_CLI_PIP_INDEX_URL={NEXUS}"):
            with self.subTest(source=source):
                commands = _commands(
                    (_pin(source=source),),
                    _running(installer=Installer.EDITABLE, checkout="/home/someone/my aart"),
                )
                self.assertEqual(
                    commands,
                    (
                        "git -C '/home/someone/my aart' fetch --tags",
                        "git -C '/home/someone/my aart' checkout v0.21.0",
                    ),
                )

    def test_nothing_is_announced_when_no_pin_is_newer(self) -> None:
        self.assertIsNone(aart_cli_update((_pin(pin="0.20.0"),), _running(), default_alias=""))


_source_values = st.fixed_dictionaries(
    {},
    optional={
        "AART_CLI_PIP_INDEX_URL": st.sampled_from((NEXUS, "https://pypi.example.test/simple")),
        "AART_CLI_PACKAGE": st.sampled_from(("aart-cli=={version}", "aart-cli", "aart-cli>=0.1")),
        "AART_CLI_WHEEL_URL": st.sampled_from(
            ("https://files.example.test/aart_cli-{version}-py3-none-any.whl",)
        ),
        "AART_CLI_TOOL_PATH": st.sampled_from(("/opt/aart", "/srv/tools/aart cli")),
        "AART_CLI_TOOL_URL": st.sampled_from(
            ("https://git.example.test/tools/aart-cli.git", "git@git.example.test:tools/aart.git")
        ),
        "AART_CLI_REPOSITORY": st.sampled_from(("platform/aart-cli", "tools/aart")),
    },
)


class AcceptedFileTest(unittest.TestCase):
    @given(_source_values, st.sampled_from(tuple(Installer)), st.integers(1, 9))
    def test_every_command_is_bare_words_from_the_file_with_the_pin_in_place(
        self, values: dict[str, str], installer: Installer, major: int
    ) -> None:
        pin = f"{major}.0.0"
        source = "".join(f"{name}={value}\n" for name, value in values.items())
        update = aart_cli_update(
            (_pin(pin=pin, source=source),),
            _running(installer=installer, checkout="/home/someone/aart-cli"),
            default_alias="",
        )

        assert update is not None
        commands = tuple(command for step in update.steps for command in step.commands)
        words = tuple(word for command in commands for word in shlex.split(command))
        # Copyable commands carry no comment, and no placeholder is left for the reader to fill.
        self.assertFalse(any(word.startswith("#") for word in words), commands)
        self.assertFalse(any("{version}" in word for word in words), commands)
        package = values.get("AART_CLI_PACKAGE")
        if package and installer is not Installer.EDITABLE:
            self.assertIn(package.replace("{version}", pin), words)


class GuidanceTest(unittest.TestCase):
    def test_the_guidance_names_the_versions_the_registry_and_the_installer(self) -> None:
        update = aart_cli_update(
            (_pin(source="AART_CLI_PACKAGE=aart-cli=={version}"),), _running(), default_alias=""
        )

        assert update is not None
        lines = upgrade_guidance(update)
        self.assertEqual(
            lines[0], "aart-cli 0.21.0 is available: Registry corp runs it, and this is 0.20.0."
        )
        self.assertIn("Installed with pipx.", lines)
        self.assertIn(
            "  pipx install --force --index-url https://pypi.org/simple aart-cli==0.21.0", lines
        )


if __name__ == "__main__":
    unittest.main()
