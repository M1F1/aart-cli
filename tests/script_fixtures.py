"""Load a `scripts/` module by path, because `scripts/` is not a package.

This used to live in `tests/versioning_test.py`, which every other test that needed a script
imported from -- a helper hiding inside a suite about versions.  That suite went with the manual
version machinery it characterised, and the helper is nobody's suite, so it is here.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from types import ModuleType

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_script(name: str) -> ModuleType:
    path = ROOT / "scripts" / f"{name}.py"
    if not path.is_file():
        raise AssertionError(f"missing script: {path.relative_to(ROOT)}")
    spec = importlib.util.spec_from_file_location(f"_aart_script_{name}", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {path.relative_to(ROOT)}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
