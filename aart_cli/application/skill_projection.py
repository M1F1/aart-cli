"""Project a canonical Skill document into the private copy a harness discovers."""

from __future__ import annotations

import json

from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.result import Err, Ok, Result

__all__ = ["SKILL_DOCUMENT", "SKILL_PROJECTION_INVALID", "project_skill_document"]

SKILL_PROJECTION_INVALID = DiagnosticCode("skill-projection-invalid")

#: The one file in a delivered Skill whose own text has to agree with the directory it sits in.
#: A delivery records this path when it carries a projection, so the digest a plan takes and the
#: bytes an executor writes are of the same file rather than of whatever each happened to guess.
SKILL_DOCUMENT = "SKILL.md"


def _error(message: str) -> Err:
    return Err((Diagnostic(SKILL_PROJECTION_INVALID, Severity.ERROR, message),))


def _ending(lines: list[str]) -> str:
    """How this document ends a line: `\r\n` where it is a Windows document, `\n` otherwise.

    Only those two, because only those two are what a harness's frontmatter reader will accept as
    the end of a row. `str.splitlines` also breaks on a lone `\r` and on the Unicode separators,
    and reading one of those off a document that merely contains one -- a stray carriage return in
    the prose -- would write the whole header as a single row no parser can read.
    """

    for line in lines:
        for ending in ("\r\n", "\n"):
            if line.endswith(ending):
                return ending
    return "\n"


def project_skill_document(
    canonical: bytes,
    *,
    installed_name: str,
    summary: str,
) -> Result[bytes]:
    """Return the installed `SKILL.md`, leaving the canonical bytes untouched.

    AART's canonical authoring document may omit harness frontmatter because identity and summary
    live in `artifact.json`. The installed copy cannot: Skill discovery requires a name matching
    its parent directory and a description. Existing frontmatter is retained apart from the name;
    its authored description wins over the manifest summary.
    """

    if (
        not isinstance(canonical, bytes)
        or not isinstance(installed_name, str)
        or not installed_name
        or any(character in installed_name for character in "\r\n")
        or not isinstance(summary, str)
        or not summary
        or any(character in summary for character in "\r\n")
    ):
        raise ValueError("a Skill projection needs bytes, a safe installed name and a summary")
    try:
        text = canonical.decode("utf-8")
    except UnicodeDecodeError:
        return _error("SKILL.md is not UTF-8 text, so its installed name cannot be projected")

    lines = text.splitlines(keepends=True)
    # Rows this adds have to end the way the document's own rows end. A `\n` written into a file
    # an author commits with `\r\n` leaves one frontmatter block spelled two ways, which is a
    # difference a reader sees and a parser is under no obligation to forgive.
    ending = _ending(lines)
    if lines and lines[0].rstrip("\r\n") == "---":
        closing = next(
            (
                index
                for index, line in enumerate(lines[1:], start=1)
                if line.rstrip("\r\n") == "---"
            ),
            None,
        )
        if closing is None:
            return _error("SKILL.md opens frontmatter but never closes it")
        header = list(lines[1:closing])
        name_rows = [index for index, line in enumerate(header) if line.startswith("name:")]
        description_rows = [
            index for index, line in enumerate(header) if line.startswith("description:")
        ]
        if len(name_rows) > 1 or len(description_rows) > 1:
            return _error("SKILL.md frontmatter repeats name or description")
        replacement = f"name: {installed_name}{ending}"
        if name_rows:
            header[name_rows[0]] = replacement
        else:
            header.insert(0, replacement)
        if not description_rows:
            header.append(f"description: {json.dumps(summary, ensure_ascii=False)}{ending}")
        return Ok((lines[0] + "".join(header) + "".join(lines[closing:])).encode("utf-8"))

    frontmatter = (
        f"---{ending}"
        f"name: {installed_name}{ending}"
        f"description: {json.dumps(summary, ensure_ascii=False)}{ending}"
        f"---{ending}{ending}"
    )
    return Ok(frontmatter.encode("utf-8") + canonical)
