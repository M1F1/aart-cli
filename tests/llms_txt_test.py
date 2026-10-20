"""§177, INV-276: `llms.txt` points an agent at the reference instead of restating it (#47).

It is written by hand, so the only way it stays true is by holding nothing that changes: it names no
command except `aart-cli docs`, which generates the rest, and every link it gives resolves.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_LLMS = (_ROOT / "llms.txt").read_text(encoding="utf-8")


class LlmsTxtTest(unittest.TestCase):
    def test_it_has_the_llmstxt_shape(self) -> None:
        lines = _LLMS.splitlines()

        self.assertTrue(lines[0].startswith("# "), "an H1 first")
        self.assertTrue(any(line.startswith("> ") for line in lines[1:4]), "a summary next")
        self.assertIn("## ", _LLMS)

    def test_it_names_no_command_but_the_one_that_generates_the_reference(self) -> None:
        named = set(re.findall(r"\baart-cli ([a-z][a-z-]+)", _LLMS))

        self.assertEqual(named, {"docs"})

    def test_it_sends_an_agent_to_the_generated_reference(self) -> None:
        self.assertIn("aart-cli docs --json", _LLMS)

    def test_every_link_resolves_to_a_file_in_the_repository(self) -> None:
        links = re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", _LLMS)

        self.assertGreater(len(links), 3)
        for target in links:
            with self.subTest(link=target):
                self.assertFalse(target.startswith(("http:", "https:", "/")), "a relative link")
                self.assertTrue((_ROOT / target).is_file())


if __name__ == "__main__":
    unittest.main()
