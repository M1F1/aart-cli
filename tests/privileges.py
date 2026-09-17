"""Where a test's subject is a permission, root is not a machine that can hold it.

A container job usually runs as root, and root ignores the mode bits a test like "this delete must
fail" depends on. Such a test is not wrong there; it has no subject there. It stands down and says
what it needed, rather than failing on a machine it was never about -- or, worse, being weakened
until it passes on both.

`QA-086`, from the owner's first container run on an Enterprise instance: one sealed-directory test
failed as root while the behaviour it guards was fine. Two files already carried their own copy of
this guard, worded differently; this is the one copy.
"""

from __future__ import annotations

import os
import unittest
from typing import Callable, TypeVar

T = TypeVar("T")


def running_as_root() -> bool:
    """True where this process ignores the permission bits a test might rely on.

    Read through `os` at call time rather than captured at import, so a test can say what it would
    do on a machine it is not running on.
    """

    return hasattr(os, "geteuid") and os.geteuid() == 0


def skip_if_root(relied_on: str) -> Callable[[T], T]:
    """Stand a test down under root, naming the permission it needed to hold.

    Takes what the test relies on rather than a whole sentence, so every skip reason reads the same
    way and names something concrete.
    """

    return unittest.skipIf(running_as_root(), f"root ignores {relied_on}")
