"""CP-48: which harnesses record artifact usage without asking is the build's, from a variable (§212).

The value comes from the repository variable `AART_CLI_DEFAULT_USAGE_HARNESSES`: harness names
separated by commas, or `none`. It is that deployment's decision, the way its Registry is (D-309),
so the source tree carries none and a public build records nothing until a person turns it on.

As with the default Registry, unset must produce the committed file byte for byte, and a value
aart-cli cannot honour must fail the build rather than be ignored on somebody's machine.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hypothesis import given
from hypothesis import strategies as st

from aart_cli import _default_usage
from aart_cli.configuration.seed import baked_usage_harnesses
from aart_cli.domain.artifact_usage import USAGE_HARNESSES, parse_usage_harnesses
from aart_cli.domain.result import Err, Ok

ROOT = Path(__file__).resolve().parent.parent
COMMITTED = ROOT / "aart_cli" / "_default_usage.py"
VARIABLE = "AART_CLI_DEFAULT_USAGE_HARNESSES"


def _load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_aart_test_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _injector():
    return _load("inject_default_usage")


def _baked(rendered: str) -> str:
    namespace: dict[str, object] = {}
    exec(compile(rendered, "<rendered>", "exec"), namespace)  # noqa: S102
    return str(namespace["HARNESSES"])


class TheValueTest(unittest.TestCase):
    def test_unset_and_none_record_nowhere(self) -> None:
        for raw in ("", "  \n", "none", " None ", "NONE"):
            with self.subTest(raw=raw):
                self.assertEqual(parse_usage_harnesses(raw), Ok(()))

    def test_names_are_read_in_order_without_the_shell_s_spaces(self) -> None:
        self.assertEqual(parse_usage_harnesses("opencode"), Ok(("opencode",)))
        self.assertEqual(parse_usage_harnesses(" claude , opencode\n"), Ok(("claude", "opencode")))

    def test_a_name_that_cannot_record_is_refused_and_said(self) -> None:
        for raw, said in (
            ("tabnine", "'tabnine'"),
            ("codex", "'codex'"),
            ("opencode,,claude", "an empty name"),
            ("opencode,opencode", "'opencode' twice"),
            ("opencode;claude", "'opencode;claude'"),
            ("none,opencode", "'none'"),
        ):
            with self.subTest(raw=raw):
                parsed = parse_usage_harnesses(raw)
                self.assertIsInstance(parsed, Err)
                assert isinstance(parsed, Err)
                self.assertIn(said, parsed.diagnostics[0].message)
                self.assertIn("claude, opencode or none", parsed.diagnostics[0].message)

    @given(
        names=st.permutations(USAGE_HARNESSES).flatmap(
            lambda order: st.integers(1, len(order)).map(lambda n: tuple(order[:n]))
        ),
        spaces=st.sampled_from(("", " ", "  ")),
    )
    def test_every_list_of_recording_harnesses_reads_back(
        self, names: tuple[str, ...], spaces: str
    ) -> None:
        raw = ",".join(f"{spaces}{name}{spaces}" for name in names)

        self.assertEqual(parse_usage_harnesses(raw), Ok(names))

    @given(other=st.text(alphabet="abcdefghijklmnopqrstuvwxyz-", min_size=1, max_size=12))
    def test_any_other_name_anywhere_is_refused(self, other: str) -> None:
        if other in USAGE_HARNESSES or other == "none":
            return
        for raw in (other, f"opencode,{other}", f"{other},claude"):
            self.assertIsInstance(parse_usage_harnesses(raw), Err)


class TheBuildBakesItTest(unittest.TestCase):
    def test_unset_and_none_render_the_committed_module_byte_for_byte(self) -> None:
        committed = COMMITTED.read_text(encoding="utf-8")
        for raw in ("", " \n", "none"):
            with self.subTest(raw=raw):
                self.assertEqual(_injector().render_from(raw, "test"), committed)

    def test_the_source_tree_records_nowhere(self) -> None:
        self.assertEqual(_default_usage.HARNESSES, "")
        self.assertEqual(baked_usage_harnesses(), ())

    def test_a_list_is_baked_as_read_and_read_back_by_aart_cli(self) -> None:
        rendered = _injector().render_from(" opencode , claude\n", "test")

        self.assertEqual(_baked(rendered), "opencode,claude")
        self.assertEqual(baked_usage_harnesses(_baked(rendered)), ("opencode", "claude"))

    def test_a_value_aart_cli_cannot_honour_fails_the_build_and_writes_nothing(self) -> None:
        with TemporaryDirectory() as raw:
            target = Path(raw) / "_default_usage.py"
            target.write_text("before\n", encoding="utf-8")
            with self.assertRaises(SystemExit) as refused:
                _injector().write(target, "opencode,tabnine", "test")

            self.assertIn("'tabnine'", str(refused.exception))
            self.assertEqual(target.read_text(encoding="utf-8"), "before\n")

    def test_writing_an_unset_build_leaves_the_checkout_untouched(self) -> None:
        before = COMMITTED.read_bytes()
        with mock.patch.dict(os.environ, {VARIABLE: ""}):
            _injector().stamp(COMMITTED)
        self.assertEqual(COMMITTED.read_bytes(), before)

    def test_a_baked_value_aart_cli_cannot_read_records_nowhere(self) -> None:
        self.assertEqual(baked_usage_harnesses("tabnine"), ())


class TheReleaseCarriesItTest(unittest.TestCase):
    def test_both_release_jobs_pass_the_variable(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

        self.assertEqual(workflow.count(f"{VARIABLE}: ${{{{ vars.{VARIABLE} }}}}"), 2)

    def _receipt_field(self, value: str | None) -> object:
        release = _load("release")
        environment = dict(os.environ)
        environment.pop(VARIABLE, None)
        if value is not None:
            environment[VARIABLE] = value
        with mock.patch.dict(os.environ, environment, clear=True):
            return release.default_usage_harnesses_value()

    def test_the_receipt_records_what_was_baked(self) -> None:
        self.assertIsNone(self._receipt_field(None))
        self.assertIsNone(self._receipt_field("none"))
        self.assertEqual(self._receipt_field(" opencode , claude\n"), "opencode,claude")


if __name__ == "__main__":
    unittest.main()
