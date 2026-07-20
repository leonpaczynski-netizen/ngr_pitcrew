"""Repository identity resolution (Program 2, Phase 72).

Resolves the exact Git commit + branch of the running checkout WITHOUT a subprocess, by reading `.git`
directly (HEAD → ref → loose ref or packed-refs). Used to stamp manual UAT observations with the exact
candidate commit so evidence is candidate-scoped (DEF-UAT-072-001) and to identify the release candidate.
Defensive: returns "" for anything it cannot resolve (a packaged/detached/absent-git checkout), never raises.
No network, no subprocess, no mutation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def _git_dir(repo_root) -> Optional[Path]:
    try:
        root = Path(repo_root)
        g = root / ".git"
        if g.is_dir():
            return g
        if g.is_file():
            # a worktree/submodule: ".git" is a file "gitdir: <path>"
            txt = g.read_text(encoding="utf-8").strip()
            if txt.startswith("gitdir:"):
                p = Path(txt.split(":", 1)[1].strip())
                return p if p.is_absolute() else (root / p).resolve()
        return None
    except Exception:  # pragma: no cover - defensive
        return None


def resolve_repo_commit(repo_root) -> str:
    """The 40-char commit SHA of HEAD, or "" if it cannot be resolved. Never raises."""
    try:
        gd = _git_dir(repo_root)
        if gd is None:
            return ""
        head = (gd / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref:"):
            # detached HEAD → HEAD holds the SHA directly
            return head if _looks_like_sha(head) else ""
        ref = head.split(":", 1)[1].strip()
        loose = gd / ref
        if loose.exists():
            sha = loose.read_text(encoding="utf-8").strip()
            return sha if _looks_like_sha(sha) else ""
        # fall back to packed-refs
        packed = gd / "packed-refs"
        if packed.exists():
            for line in packed.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("^"):
                    continue
                parts = line.split(" ", 1)
                if len(parts) == 2 and parts[1].strip() == ref:
                    return parts[0].strip() if _looks_like_sha(parts[0].strip()) else ""
        return ""
    except Exception:  # pragma: no cover - defensive
        return ""


def resolve_repo_branch(repo_root) -> str:
    """The current branch name, or "" if detached/unresolvable. Never raises."""
    try:
        gd = _git_dir(repo_root)
        if gd is None:
            return ""
        head = (gd / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = head.split(":", 1)[1].strip()
            return ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
        return ""
    except Exception:  # pragma: no cover - defensive
        return ""


def _looks_like_sha(s: str) -> bool:
    return len(s) == 40 and all(c in "0123456789abcdef" for c in s.lower())


def short_commit(sha: str, n: int = 7) -> str:
    s = str(sha or "").strip()
    return s[:n] if _looks_like_sha(s) else s
