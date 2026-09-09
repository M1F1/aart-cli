"""agent-artifacts — install a team's AI artifacts into multiple agentic harnesses.

Zero runtime dependencies, functional core / imperative shell. See docs/design/DESIGN.md / docs/plan/PLAN.md.
"""

from __future__ import annotations

# The one place this package writes its own version down, and the release engine writes it
# here: `release-please-config.json` lists this file, and the annotation is the line it
# rewrites.  Nothing else in the tree declares a version -- `runtime_contract` reads this one.
__version__ = "0.0.1"  # x-release-please-version
