"""CP-27 task 1: the wheel may carry one default Registry, and the source tree carries none.

A first run in an Enterprise fork should not have to ask for an address the organization already
decided on. The wheel can therefore carry one -- alias and URL -- stamped in at build time the way
``aart_cli/_commit.py`` already carries the source commit.

Two claims are load-bearing here and neither is about convenience. The committed module must stay
empty, because a real address committed to the source tree is one deployment's address becoming
every fork's default, which is exactly what D-309 removed. And a half-filled or malformed pair is a
build mistake rather than something to interpret: an alias is stamped into the path of everything
installed from that Registry (D-359, INV-253), so guessing one is a choice nobody can undo later.
"""

from __future__ import annotations

import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli import _default_registry
from aart_cli.configuration.model import parse_source_alias
from aart_cli.configuration.schema import _ALIAS_RE
from aart_cli.configuration.seed import SeededRegistry, baked_default_registry
from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Err, Ok
from tests.credential_fixtures import credential_url

URL = "https://example.invalid/team/registry.git"


def _value(alias: str, url: str) -> SeededRegistry | None:
    result = baked_default_registry(alias, url)
    assert isinstance(result, Ok), result
    return result.value


def _messages(alias: str, url: str) -> tuple[str, ...]:
    result = baked_default_registry(alias, url)
    assert isinstance(result, Err), result
    return tuple(diagnostic.message for diagnostic in result.diagnostics)


class CommittedSourceBakesNothing(unittest.TestCase):
    def test_the_generated_module_is_empty_in_the_source_tree(self) -> None:
        self.assertEqual((_default_registry.ALIAS, _default_registry.URL), ("", ""))

    def test_an_empty_module_means_no_default_rather_than_an_error(self) -> None:
        self.assertIsNone(_value(_default_registry.ALIAS, _default_registry.URL))

    def test_the_reader_defaults_to_the_module_it_is_generated_beside(self) -> None:
        result = baked_default_registry()
        self.assertIsInstance(result, Ok)
        self.assertIsNone(result.value)


class OneBakedRegistry(unittest.TestCase):
    def test_a_valid_pair_is_read_as_one_registry(self) -> None:
        self.assertEqual(_value("company", URL), SeededRegistry(SourceAlias("company"), URL))

    def test_an_ssh_origin_is_a_registry_too(self) -> None:
        seeded = _value("company", "git@example.invalid:team/registry.git")
        assert seeded is not None
        self.assertEqual(seeded.alias, SourceAlias("company"))

    def test_the_url_is_kept_exactly_as_the_build_stamped_it(self) -> None:
        seeded = _value("company", URL)
        assert seeded is not None
        self.assertEqual(seeded.url, URL)


class HalfASeedIsRefused(unittest.TestCase):
    def test_an_alias_without_a_url_is_an_error(self) -> None:
        self.assertIn("baked default registry alias has no URL", _messages("company", ""))

    def test_a_url_without_an_alias_is_an_error(self) -> None:
        self.assertIn("baked default registry URL has no alias", _messages("", URL))


class MalformedValuesAreRefused(unittest.TestCase):
    def test_an_alias_outside_the_configuration_grammar_is_refused(self) -> None:
        # A trailing newline is the one a release variable actually arrives with -- a shell
        # `echo` adds it -- and `^...$` accepts it where `fullmatch` does not.
        for alias in (
            "Company",
            "-company",
            "company-",
            "com_pany",
            "1company",
            "com pany",
            "company\n",
            "company\t",
        ):
            with self.subTest(alias=alias):
                self.assertIn("baked default registry alias is invalid", _messages(alias, URL))

    def test_a_location_git_cannot_clone_is_refused(self) -> None:
        for url in (
            "not a url",
            "file:///srv/registry",
            "/srv/registry",
            "ftp://example.invalid/team/registry.git",
            " https://example.invalid/team/registry.git",
        ):
            with self.subTest(url=url):
                self.assertIn("baked default registry URL is invalid", _messages("company", url))

    def test_a_url_carrying_credentials_is_refused(self) -> None:
        # The value is printed on first run to say where the Registry came from, and a release
        # variable is not a secret store.
        self.assertIn(
            "baked default registry URL is invalid",
            _messages("company", credential_url("example.invalid", "/team/registry.git")),
        )


class ReaderIsTotal(unittest.TestCase):
    @given(st.text(max_size=40), st.text(max_size=60))
    def test_any_pair_of_strings_produces_a_result_rather_than_an_exception(
        self, alias: str, url: str
    ) -> None:
        result = baked_default_registry(alias, url)
        self.assertIsInstance(result, (Ok, Err))

    @given(
        st.from_regex(r"\A[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z", fullmatch=True).filter(
            lambda value: len(value) <= 40
        ),
        st.from_regex(r"\A[a-z][a-z0-9-]{0,20}\Z", fullmatch=True),
    )
    def test_every_alias_the_configuration_grammar_accepts_is_bakeable(
        self, alias: str, repository: str
    ) -> None:
        seeded = _value(alias, f"https://example.invalid/team/{repository}.git")
        self.assertEqual(seeded, SeededRegistry(SourceAlias(alias), seeded.url))  # type: ignore[union-attr]


class OneAliasGrammar(unittest.TestCase):
    """The seed and the configuration store must accept exactly the same aliases.

    They are spelled twice -- `model.parse_source_alias` for a caller that has no JSON yet, and
    `schema._ALIAS_RE` for the parser that reads `config.json` -- and drift between them would
    surface on the one run that cannot fall back on an existing configuration: a seed accepted at
    build time and refused when it is written.
    """

    @given(st.text(max_size=24))
    def test_the_two_spellings_accept_the_same_strings(self, candidate: str) -> None:
        self.assertEqual(
            parse_source_alias(candidate) is not None,
            _ALIAS_RE.fullmatch(candidate) is not None,
        )


if __name__ == "__main__":
    unittest.main()
