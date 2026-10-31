"""Read version metadata (commit SHA, tag, dirty state) from a source checkout."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _git(path: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
    return out.stdout.strip() or None


def commit_sha(path: str | Path) -> str | None:
    return _git(Path(path), "rev-parse", "HEAD")


def describe(path: str | Path) -> str | None:
    return _git(Path(path), "describe", "--tags", "--always")


def is_dirty(path: str | Path) -> bool:
    out = _git(Path(path), "status", "--porcelain")
    return bool(out)


def tree_sha256(path: str | Path) -> str | None:
    """SHA-1 of the git tree, useful when a checkout has no commit (e.g. tarball)."""
    return _git(Path(path), "rev-parse", "HEAD^{tree}")
