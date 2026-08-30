"""Deterministic JSON encoding for secret-free domain projections."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import TypeAlias

CanonicalScalar: TypeAlias = None | bool | int | float | str
CanonicalValue: TypeAlias = (
    CanonicalScalar | Mapping[str, "CanonicalValue"] | Sequence["CanonicalValue"]
)


def canonical_json_bytes(value: CanonicalValue) -> bytes:
    """Encode a JSON-shaped value with stable keys and no insignificant whitespace."""

    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
