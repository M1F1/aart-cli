"""CP-27 task 2: the release stamps the default Registry, and an unset variable stamps nothing.

The value comes from the repository variable `AART_CLI_DEFAULT_REGISTRY_ALIAS_AND_URL`, holding
`<alias>=<url>`, so a fork supplies its own Registry without patching the source tree -- the same
arrangement `AART_CLI_REFERENCE_REGISTRY_URL` already has, and for the reason D-309 gives.

Two claims carry the weight. Unset must produce the file that is already committed, byte for byte,
because that is what "the public wheel is unchanged" means and nothing weaker can be checked. And a
malformed value must fail the *build*: the release is the last moment anyone is watching, while the
first run it would otherwise break is the one moment a person has no configuration to fall back on.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aart_cli.configuration.seed import SeededRegistry, baked_default_registry
from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Ok

ROOT = Path(__file__).resolve().parent.parent
COMMITTED = ROOT / "aart_cli" / "_default_registry.py"
URL = "https://example.invalid/team/registry.git"
VARIABLE = "AART_CLI_DEFAULT_REGISTRY_ALIAS_AND_URL"


def _load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_aart_test_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _module():
    return _load("inject_default_registry")


def _constants(rendered: str) -> tuple[str, str]:
    namespace: dict[str, object] = {}
    exec(compile(rendered, "<rendered>", "exec"), namespace)  # noqa: S102
    return str(namespace["ALIAS"]), str(namespace["URL"])


class UnsetBakesNothing(unittest.TestCase):
    def test_an_unset_variable_renders_the_committed_module_byte_for_byte(self) -> None:
        self.assertEqual(_module().render_from("", "unset"), COMMITTED.read_text(encoding="utf-8"))

    def test_whitespace_only_is_the_same_as_unset(self) -> None:
        self.assertEqual(
            _module().render_from("  \n", "unset"), COMMITTED.read_text(encoding="utf-8")
        )

    def test_writing_an_unset_build_leaves_the_checkout_untouched(self) -> None:
        before = COMMITTED.read_bytes()
        with TemporaryDirectory() as raw:
            target = Path(raw) / "_default_registry.py"
            self.assertEqual(_module().write(target, ""), 0)
            self.assertEqual(target.read_bytes(), before)


class OneValueIsStamped(unittest.TestCase):
    def test_an_alias_and_url_reach_the_module(self) -> None:
        self.assertEqual(
            _constants(_module().render_from(f"company={URL}", VARIABLE)), ("company", URL)
        )

    def test_the_stamped_module_is_read_back_as_that_registry(self) -> None:
        alias, url = _constants(_module().render_from(f"company={URL}", VARIABLE))
        self.assertEqual(
            baked_default_registry(alias, url), Ok(SeededRegistry(SourceAlias("company"), URL))
        )

    def test_surrounding_whitespace_is_the_shell_s_and_is_dropped(self) -> None:
        # A repository variable set from `echo` arrives with a trailing newline; the reader still
        # refuses one *inside* the alias, so trimming here does not widen what is accepted.
        self.assertEqual(
            _constants(_module().render_from(f"  company={URL}\n", VARIABLE)), ("company", URL)
        )

    def test_only_the_first_separator_splits_the_value(self) -> None:
        alias, url = _constants(
            _module().render_from("company=ssh://git@example.invalid/team/registry.git", VARIABLE)
        )
        self.assertEqual((alias, url), ("company", "ssh://git@example.invalid/team/registry.git"))

    def test_rendering_is_deterministic(self) -> None:
        first = _module().render_from(f"company={URL}", VARIABLE)
        self.assertEqual(first, _module().render_from(f"company={URL}", VARIABLE))


class MalformedValueFailsTheBuild(unittest.TestCase):
    def _refused(self, value: str) -> str:
        with self.assertRaises(SystemExit) as raised:
            _module().render_from(value, VARIABLE)
        return str(raised.exception)

    def test_a_value_without_a_separator_is_refused(self) -> None:
        self.assertIn(VARIABLE, self._refused(URL))

    def test_an_empty_alias_is_refused(self) -> None:
        self.assertIn("alias", self._refused(f"={URL}"))

    def test_an_empty_url_is_refused(self) -> None:
        self.assertIn("URL", self._refused("company="))

    def test_an_alias_outside_the_grammar_is_refused(self) -> None:
        self.assertIn("alias", self._refused(f"Company={URL}"))

    def test_a_location_git_cannot_clone_is_refused(self) -> None:
        self.assertIn("URL", self._refused("company=not a url"))

    def test_a_refused_value_writes_no_module(self) -> None:
        with TemporaryDirectory() as raw:
            target = Path(raw) / "_default_registry.py"
            with self.assertRaises(SystemExit):
                _module().write(target, "Company=" + URL)
            self.assertFalse(target.exists())


class EveryInjectorReachesBothBuilds(unittest.TestCase):
    """A build-time stamp is only real if both builds apply it.

    There are two: the release action on a runner, and `release.py wheel_digest`, which builds the
    wheel whose digest is published beside the artifact. A stamp applied by one and not the other
    makes the published digest describe a file nobody has. The set is discovered rather than
    listed, so adding a third injector cannot silently reach only one of them.
    """

    def _injectors(self) -> set[str]:
        return {path.name for path in (ROOT / "scripts").glob("inject_*.py")}

    def test_there_is_more_than_one_injector_to_keep_together(self) -> None:
        self.assertEqual(self._injectors(), {"inject_commit.py", "inject_default_registry.py"})

    def test_the_release_action_runs_every_injector(self) -> None:
        action = (ROOT / ".github" / "actions" / "release" / "action.yml").read_text(
            encoding="utf-8"
        )
        for name in self._injectors():
            with self.subTest(injector=name):
                self.assertIn(f"scripts/{name}", action)

    def test_the_digest_build_applies_every_injector(self) -> None:
        release = _load("release")
        self.assertEqual({path.name for path in release.injectors()}, self._injectors())

    def test_each_injector_stamps_a_module_the_package_carries(self) -> None:
        release = _load("release")
        for path in release.injectors():
            with self.subTest(injector=path.name):
                target = _load(path.stem).TARGET
                self.assertTrue(target.is_relative_to(ROOT / "aart_cli"))
                self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()
