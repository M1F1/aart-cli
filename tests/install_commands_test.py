"""The install commands name the repository they are printed for, and never a written-down one."""

from __future__ import annotations

import unittest
from unittest import mock

from tests.script_fixtures import ROOT
from tests.script_fixtures import load_script as _load_script

install_commands = _load_script("install_commands")
github_api = _load_script("github_api")


class LinesTest(unittest.TestCase):
    def test_the_commands_name_the_instance_they_were_asked_about(self) -> None:
        block = install_commands.lines("https://ghe.example.org/platform/aart", "2.9.0")

        pin = '"git+https://ghe.example.org/platform/aart.git@v2.9.0"'
        for command in (
            f"pipx install {pin}",
            f"python -m pip install --no-deps {pin}",
            f"uv tool install {pin}",
        ):
            with self.subTest(command=command):
                self.assertIn(command, block)
        self.assertIn("aart_cli-2.9.0-py3-none-any.whl", block)
        # github.com must not leak into a block asked for about somewhere else.
        self.assertNotIn("github.com", block)

    def test_the_url_row_carries_the_warning_that_belongs_with_it(self) -> None:
        """The failure it prevents names neither its cause nor its fix.

        `pip`, `pipx` and `uv` send no token when they fetch a URL, so a release asset on a private
        instance answers with a sign-in page and the installer reports a corrupt archive.
        """

        block = install_commands.lines("https://ghe.example.org/platform/aart", "2.9.0")
        self.assertIn("send no token", block)
        self.assertIn("sign-in page", block)

    def test_the_wheel_can_be_installed_from_the_clipboard_by_every_installer(self) -> None:
        """The reader is already on the page holding the link; typing the version is the only work
        left, and it is the only step that can go wrong silently."""

        block = install_commands.lines("https://ghe.example.org/platform/aart", "2.9.0")

        for command in (
            'uv tool install --force "$(pbpaste)"',
            'pipx install --python "$(command -v python3)" --force "$(pbpaste)"',
            'python -m pip install --no-deps --force-reinstall "$(pbpaste)"',
        ):
            with self.subTest(command=command):
                self.assertIn(command, block)

    def test_the_clipboard_form_says_what_to_copy_and_what_breaks_it(self) -> None:
        """A command that reads the clipboard is only correct if the clipboard is. The two ways it
        is not -- a non-macOS reader and a clipboard holding something else -- are named where the
        command is, not in a page somebody would have to already suspect."""

        block = install_commands.lines("https://ghe.example.org/platform/aart", "2.9.0")

        self.assertIn("Copy link address", block)
        self.assertIn("wl-paste", block)
        self.assertIn("pbpaste` is macOS", block)


class RepositoryUrlTest(unittest.TestCase):
    def test_an_instance_and_github_com_are_told_apart(self) -> None:
        with mock.patch.object(
            github_api, "origin", return_value=("https://api.github.com", "M1F1/agent-artifacts")
        ):
            self.assertEqual(github_api.repository_url(), "https://github.com/M1F1/agent-artifacts")
        with mock.patch.object(
            github_api, "origin", return_value=("https://ghe.example.org/api/v3", "platform/aart")
        ):
            self.assertEqual(github_api.repository_url(), "https://ghe.example.org/platform/aart")


class ReleasedVersionTest(unittest.TestCase):
    """Which version the commands name, when nobody says.

    `cut_release.py` used to compose this block into the release body it wrote, and read the
    version out of `scripts/version.py`.  Both are gone: the release body is generated, and the
    version is the release engine's.  So the default is read from the engine's own manifest --
    a reader of that record, never a second opinion about it.
    """

    def test_the_default_version_is_the_one_the_release_engine_recorded(self) -> None:
        import json

        manifest = json.loads((ROOT / ".release-please-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(install_commands.released_version(), manifest["."])


if __name__ == "__main__":
    unittest.main()
