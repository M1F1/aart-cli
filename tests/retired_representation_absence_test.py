"""CP-26.5: the retired authoring workspace has no schema, no producer and no reader left.

Steps 1-4 took the retired representation out of every admission path: canonical maintenance
refuses a workspace carrying it, and both the consumer projection and the Registry source validator
name it rather than compiling it.  What remained was the machinery itself -- a schema that could
still parse `aart.lock.json`, a tree digest defined over `entries/`, and planning halves that could
still write both.  Code that can still produce a representation nothing admits is an invitation to
produce it, so this test is the claim that the machinery is gone rather than merely unrouted.

It is deliberately a literal claim as well as an import claim.  A path reachable only by string is
still a path, and the two retired filenames are exactly the kind of thing that survives a refactor
inside a `files.get(...)`.  The scan reads string *constants* out of the AST rather than the file
text, so a comment or a docstring explaining what was removed is not a violation -- only code that
still addresses those paths is.

Three modules are allowed to name them, because naming them is their job: `legacy_registry_paths`
detects the shape, and `curation/runtime.py` and `commands/registry.py` tell an operator which
shape their checkout is carrying.  Deleting those would delete the diagnosis along with the code.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

import agent_artifacts.protocol as protocol

ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "agent_artifacts"

RETIRED_PROTOCOL_SYMBOLS = (
    "GitArtifactReference",
    "LockedArtifact",
    "RegistryEntry",
    "RegistryIndex",
    "RegistryLock",
    "ResolvedRegistryReference",
    "build_registry_index",
    "parse_registry_entry",
    "parse_registry_index",
    "parse_registry_lock",
    "registry_entry_to_json",
    "registry_index_to_json",
    "registry_inputs_digest",
    "registry_lock_to_json",
    "resolve_locked_references",
)

RETIRED_PATH_LITERALS = ("aart.lock.json", "aart.index.json", "entries/")

# The refusal has to keep saying which shape it found, so the modules that produce those sentences
# are where the retired names are still expected to occur.
NAMES_THE_RETIRED_SHAPE = frozenset(
    {
        PACKAGE / "registry_maintenance" / "promoted.py",
        PACKAGE / "curation" / "runtime.py",
        PACKAGE / "commands" / "registry.py",
        # The reader, for the opposite reason: `legacy_registry_paths` can only name a retired
        # checkout by the paths it was handed, so a root-file list that skipped these two would
        # turn the refusal into silence.
        PACKAGE / "io" / "registry_workspace.py",
    }
)


def _string_constants(path: pathlib.Path) -> tuple[str, ...]:
    """Every string literal in a module except the docstrings, which explain rather than address."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return tuple(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    )


class RetiredRepresentationAbsenceTest(unittest.TestCase):
    def test_the_protocol_package_exports_no_lock_index_or_entry_surface(self) -> None:
        present = tuple(name for name in RETIRED_PROTOCOL_SYMBOLS if hasattr(protocol, name))

        self.assertEqual(present, ())

    def test_no_shipped_module_defines_the_retired_schema(self) -> None:
        self.assertFalse((PACKAGE / "protocol" / "registry_tree.py").exists())

    def test_only_the_refusal_still_names_the_retired_paths(self) -> None:
        offenders = {}
        for path in sorted(PACKAGE.rglob("*.py")):
            if path in NAMES_THE_RETIRED_SHAPE:
                continue
            constants = _string_constants(path)
            found = tuple(
                literal
                for literal in RETIRED_PATH_LITERALS
                if any(literal in constant for constant in constants)
            )
            if found:
                offenders[str(path.relative_to(ROOT))] = found

        self.assertEqual(offenders, {})

    def test_the_exception_list_is_not_vacuous(self) -> None:
        """A list that named a file which no longer exists would excuse nothing and pass anyway."""

        for path in NAMES_THE_RETIRED_SHAPE:
            self.assertTrue(path.exists(), path)
        self.assertTrue(RETIRED_PROTOCOL_SYMBOLS)
        self.assertTrue(RETIRED_PATH_LITERALS)


if __name__ == "__main__":
    unittest.main()
