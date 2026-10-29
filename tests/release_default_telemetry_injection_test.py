"""CP-50: the telemetry server a build offers is the build's, from a variable (§213, D-503).

The value comes from the repository variable `AART_CLI_TELEMETRY_ENDPOINT`: a server's base
address. Where an organisation's server is, is that deployment's, the way its Registry is (D-309),
so the source tree carries none. Offering is all a baked address does: telemetry stays off until
a person turns it on.

As with the default Registry, unset must produce the committed file byte for byte, and an address
aart-cli would refuse must fail the build rather than be ignored on somebody's machine.
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

from aart_cli import _default_telemetry
from aart_cli.configuration.seed import baked_telemetry_endpoint
from aart_cli.domain.result import Err, Ok
from aart_cli.domain.telemetry import parse_telemetry_endpoint
from tests.credential_fixtures import credential_url

ROOT = Path(__file__).resolve().parent.parent
COMMITTED = ROOT / "aart_cli" / "_default_telemetry.py"
VARIABLE = "AART_CLI_TELEMETRY_ENDPOINT"


def _load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_aart_test_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _injector():
    return _load("inject_default_telemetry")


def _baked(rendered: str) -> str:
    namespace: dict[str, object] = {}
    exec(compile(rendered, "<rendered>", "exec"), namespace)  # noqa: S102
    return str(namespace["ENDPOINT"])


_HOSTS = st.from_regex(r"[a-z][a-z0-9-]{0,10}(\.[a-z][a-z0-9-]{0,10}){0,2}", fullmatch=True)
_PATHS = st.lists(st.from_regex(r"[0-9A-Za-z._~%!$&'()*+,;=:@-]{0,8}", fullmatch=True), max_size=3)


class TheBuildBakesItTest(unittest.TestCase):
    def test_unset_renders_the_committed_module_byte_for_byte(self) -> None:
        committed = COMMITTED.read_text(encoding="utf-8")
        for raw in ("", " \n"):
            with self.subTest(raw=raw):
                self.assertEqual(_injector().render_from(raw, "test"), committed)

    def test_the_source_tree_offers_no_server(self) -> None:
        self.assertEqual(_default_telemetry.ENDPOINT, "")
        self.assertIsNone(baked_telemetry_endpoint())

    def test_an_address_is_baked_as_read_and_read_back_by_aart_cli(self) -> None:
        rendered = _injector().render_from(" https://telemetry.example.com/aart/\n", "test")

        self.assertEqual(_baked(rendered), "https://telemetry.example.com/aart")
        self.assertEqual(
            baked_telemetry_endpoint(_baked(rendered)), "https://telemetry.example.com/aart"
        )

    @given(
        host=_HOSTS,
        port=st.none() | st.integers(1, 65535),
        segments=_PATHS,
    )
    def test_every_accepted_address_survives_being_baked(
        self, host: str, port: int | None, segments: list[str]
    ) -> None:
        raw = f"https://{host}{'' if port is None else f':{port}'}" + "".join(
            f"/{segment}" for segment in segments
        )
        accepted = parse_telemetry_endpoint(raw)
        assert isinstance(accepted, Ok), accepted

        rendered = _injector().render_from(raw, "test")

        self.assertEqual(_baked(rendered), accepted.value)
        self.assertEqual(baked_telemetry_endpoint(_baked(rendered)), accepted.value)

    def test_an_address_aart_cli_would_refuse_fails_the_build_and_writes_nothing(self) -> None:
        for raw in (
            "http://telemetry.example.com",
            credential_url("telemetry.example.com", held="pw"),
            "https://telemetry.example.com/?token=x",
            "https://telemetry.example.com/#x",
            'https://telemetry.example.com/"; import os',
        ):
            with self.subTest(raw=raw), TemporaryDirectory() as directory:
                target = Path(directory) / "_default_telemetry.py"
                target.write_text("before\n", encoding="utf-8")
                with self.assertRaises(SystemExit) as refused:
                    _injector().write(target, raw, "test")

                self.assertNotIn(raw.strip(), str(refused.exception))
                self.assertEqual(target.read_text(encoding="utf-8"), "before\n")

    def test_writing_an_unset_build_leaves_the_checkout_untouched(self) -> None:
        before = COMMITTED.read_bytes()
        with mock.patch.dict(os.environ, {VARIABLE: ""}):
            _injector().stamp(COMMITTED)
        self.assertEqual(COMMITTED.read_bytes(), before)

    def test_a_baked_value_aart_cli_cannot_read_offers_nothing(self) -> None:
        self.assertIsNone(baked_telemetry_endpoint("http://telemetry.example.com"))
        self.assertIsInstance(parse_telemetry_endpoint("ftp://x"), Err)


class TheReleaseCarriesItTest(unittest.TestCase):
    def test_both_release_jobs_pass_the_variable(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

        self.assertEqual(workflow.count(f"{VARIABLE}: ${{{{ vars.{VARIABLE} }}}}"), 2)

    def test_the_build_action_runs_the_injector(self) -> None:
        action = (ROOT / ".github" / "actions").rglob("action.yml")
        steps = "\n".join(path.read_text(encoding="utf-8") for path in action)

        self.assertIn("scripts/inject_default_telemetry.py", steps)

    def _receipt_field(self, value: str | None) -> object:
        release = _load("release")
        environment = dict(os.environ)
        environment.pop(VARIABLE, None)
        if value is not None:
            environment[VARIABLE] = value
        with mock.patch.dict(os.environ, environment, clear=True):
            return release.telemetry_endpoint_value()

    def test_the_receipt_records_what_was_offered(self) -> None:
        self.assertIsNone(self._receipt_field(None))
        self.assertIsNone(self._receipt_field("  "))
        self.assertEqual(
            self._receipt_field(" https://telemetry.example.com/\n"),
            "https://telemetry.example.com",
        )


if __name__ == "__main__":
    unittest.main()
