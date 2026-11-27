"""The build's default OpenCode, stamped into the wheel by the release (D-532).

Kept apart from `opencode_runtime_test` because it drives `scripts/`, which a mutation sandbox
does not carry.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile
import unittest
import unittest.mock

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _injector():
    spec = importlib.util.spec_from_file_location(
        "inject_default_opencode", ROOT / "scripts" / "inject_default_opencode.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TheBuildStampTest(unittest.TestCase):
    def test_unset_renders_the_committed_module_byte_for_byte(self) -> None:
        injector = _injector()
        committed = (ROOT / "aart_cli" / "_default_opencode.py").read_text(encoding="utf-8")
        self.assertEqual(committed, injector.render_from("", "test"))
        self.assertEqual(committed, injector.render_from("  ", "test"))

    def test_a_runtime_is_stamped_and_anything_else_stops_the_release(self) -> None:
        injector = _injector()
        self.assertIn('RUNTIME = "2"\n', injector.render_from(" 2 ", "test"))
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / "_default_opencode.py"
            target.write_text("kept\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                injector.write(target, "3")
            self.assertEqual("kept\n", target.read_text(encoding="utf-8"))

    def test_the_release_receipt_records_it(self) -> None:
        spec = importlib.util.spec_from_file_location("release", ROOT / "scripts" / "release.py")
        assert spec is not None and spec.loader is not None
        release = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = release
        spec.loader.exec_module(release)
        with unittest.mock.patch.dict("os.environ", {"AART_CLI_DEFAULT_OPENCODE": "2"}):
            self.assertEqual(2, release.default_opencode_value())
        with unittest.mock.patch.dict("os.environ", {"AART_CLI_DEFAULT_OPENCODE": ""}):
            self.assertEqual(1, release.default_opencode_value())


if __name__ == "__main__":
    unittest.main()
