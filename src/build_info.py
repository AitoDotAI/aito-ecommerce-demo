"""Which commit is this process actually running?

The deployed demo has twice served behaviour that was in no git branch,
and the only way that was noticed was by spotting impossible output in
the UI (two different query shapes from one codebase). A build that
cannot say where it came from can only be diagnosed by inference.

So the app reports its own provenance. `BUILD_SHA` is the authoritative
source — set it at build time, since a deployed image has no `.git`. The
git fallback exists so a local dev run reports something useful too, and
is explicitly NOT trusted in a deployment: if `BUILD_SHA` is unset in
production, that is itself the finding.
"""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def build_info() -> dict[str, str | bool | None]:
    """`{sha, source, dirty}` — never raises, never blocks startup."""
    sha = (os.environ.get("BUILD_SHA") or "").strip()
    if sha:
        return {"sha": sha[:12], "source": "BUILD_SHA", "dirty": None}

    # Local dev fallback. A deployment landing here has no pinned build.
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_PROJECT_ROOT, capture_output=True, text=True, timeout=2,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=_PROJECT_ROOT, capture_output=True, text=True, timeout=2,
        ).stdout.strip())
    except Exception:
        return {"sha": None, "source": "unknown", "dirty": None}

    if not sha:
        return {"sha": None, "source": "unknown", "dirty": None}
    return {"sha": sha[:12], "source": "git", "dirty": dirty}
