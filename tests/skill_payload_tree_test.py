"""D-405: a payload glob that reaches a directory selects the files under it, not the directory.

Agent Skills carry `scripts/`, `references/`, `examples/` beside `SKILL.md`. Writing
`payload.include: ["**"]` for one was refused with "declared payload selects forbidden directory
entry 'scripts'", because `**` matched the directory's own entry, so a skill tree could only be
declared by naming every file. Found by packaging an enterprise fork of superpowers (CP-29 step 2).

A directory is structure, so it is passed over and its files are still matched one by one. A
symbolic link or special file is content AART will not copy, and stays refused.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from aart_cli.configuration.model import ConfiguredSource, SourceKind
from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Err, Ok
from aart_cli.protocol.authoring import compile_author_snapshot
from aart_cli.sources.local import read_local_snapshot
from aart_cli.sources.model import LocalSnapshotRequest, SnapshotLimits, source_instance_id

_MANIFEST = """schema: aart-cli.dev/skill/v1
artifact:
  kind: skill
  name: tree
  version: 1.0.0
  summary: "A skill with files below its root."
payload:
  include:
    - "{include}"
"""
_SKILL = "---\nname: tree\ndescription: Use when testing.\n---\n\n# Tree\n"


def _compile(root: Path):
    alias = SourceAlias("authors")
    configured = ConfiguredSource(alias, SourceKind.SOURCE_LOCAL, str(root), None, True)
    acquired = read_local_snapshot(
        LocalSnapshotRequest(source_instance_id(configured), alias, str(root), SnapshotLimits())
    )
    assert isinstance(acquired, Ok), getattr(acquired, "diagnostics", ())
    return compile_author_snapshot(
        acquired.value.snapshot,
        source_alias=alias,
        source="https://git.example.test/authors.git",
        revision="c" * 40,
    )


def _skill(root: Path, include: str, files: tuple[str, ...]) -> None:
    (root / "aart-cli.yaml").write_text(_MANIFEST.format(include=include), encoding="utf-8")
    (root / "SKILL.md").write_text(_SKILL, encoding="utf-8")
    for relative in files:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{relative}\n", encoding="utf-8")


def _paths(compiled) -> set[str]:
    return {
        "/".join(entry.path.parts)
        for entry in compiled.canonical_entries
        if entry.kind.value == "file"
    }


class APayloadTreeIsItsFilesTest(unittest.TestCase):
    def test_a_recursive_glob_carries_every_file_of_a_skill_tree(self) -> None:
        files = ("scripts/run.sh", "references/guide.md", "examples/deep/one.md")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _skill(root, "**", files)

            compiled = _compile(root)

            self.assertIsInstance(compiled, Ok, getattr(compiled, "diagnostics", ()))
            carried = _paths(compiled.value[0])
            for relative in ("SKILL.md", *files):
                self.assertTrue(
                    any(path.endswith(relative) for path in carried), (relative, carried)
                )

    def test_a_symbolic_link_the_glob_reaches_is_still_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _skill(root, "**", ("scripts/run.sh",))
            os.symlink(root / "scripts/run.sh", root / "scripts/link.sh")

            alias = SourceAlias("authors")
            configured = ConfiguredSource(alias, SourceKind.SOURCE_LOCAL, str(root), None, True)
            acquired = read_local_snapshot(
                LocalSnapshotRequest(
                    source_instance_id(configured), alias, str(root), SnapshotLimits()
                )
            )

            # Refused where the tree is read; the compiler's own refusal stands behind it.
            self.assertIsInstance(acquired, Err)
            self.assertIn(
                "symlinks are forbidden", " ".join(d.message for d in acquired.diagnostics)
            )

    @settings(max_examples=25, deadline=None)
    @given(
        st.lists(
            st.lists(st.sampled_from(("a", "b", "scripts", "ref")), min_size=1, max_size=3),
            min_size=1,
            max_size=4,
            unique_by=tuple,
        )
    )
    def test_every_nested_file_is_carried_whatever_the_tree(self, trees: list[list[str]]) -> None:
        files = tuple("/".join((*parts, "leaf.md")) for parts in trees)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _skill(root, "**", files)

            compiled = _compile(root)

            self.assertIsInstance(compiled, Ok, getattr(compiled, "diagnostics", ()))
            carried = _paths(compiled.value[0])
            for relative in files:
                self.assertTrue(any(path.endswith(relative) for path in carried), relative)


if __name__ == "__main__":
    unittest.main()
