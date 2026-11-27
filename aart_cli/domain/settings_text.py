"""A harness settings file as text: read in the harness's syntax, written back without damage.

Two writers edit settings files a harness owns -- the MCP registry and the settings-entry
interpreter -- and both used to read with `json.loads` and write with `json.dumps`. That is right
for a harness that reads strict JSON, and wrong for OpenCode, whose files may carry comments the
person wrote (§218, D-530): `json.loads` refuses them and `json.dumps` would drop them. So both
writers come here, and the harness's `SettingsSyntax` decides.

Pure: text in, text out.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from .harness import SettingsSyntax, annotates, is_settings_note
from .jsonc import JsoncError, Path, rewrite
from .jsonc import document as jsonc_document

__all__ = ["JsoncError", "Path", "parse_settings_text", "render_settings_text"]


def parse_settings_text(raw: str, syntax: SettingsSyntax) -> object:
    """The document `raw` holds, or `ValueError` saying why it holds none.

    JSON with comments holding only comments is a file nobody has configured yet, read as `{}` --
    the same as an empty file, which every caller already reads that way.
    """

    if syntax is SettingsSyntax.JSONC:
        parsed = jsonc_document(raw)
        return {} if parsed is None else parsed
    return json.loads(raw)


def render_settings_text(
    raw: str | None,
    document: dict[str, object],
    syntax: SettingsSyntax,
    *,
    path: str,
    note: str | None = None,
    ours: Callable[[Path, object], bool] | None = None,
) -> str:
    """The text `path` should hold to say `document`, changed from `raw` as little as it can be.

    Strict JSON is written whole, as it always was. JSON with comments is edited in place, and in a
    `.jsonc` file each member or item `ours` claims gets `note` as a comment above it; removing one
    removes that comment with it. Raises `JsoncError` when an edit could only be made by losing a
    comment, so the caller leaves the file as it is.
    """

    if syntax is SettingsSyntax.JSON:
        return json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    annotate = None
    if note and ours is not None and annotates(path):

        def annotate(where: Path, value: object) -> str | None:
            return note if ours(where, value) else None

    return rewrite(raw or "", document, annotate=annotate, owned=is_settings_note)
