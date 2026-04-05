"""Git integration for document edits — all operations are local and non-fatal."""

import os
import subprocess
from pathlib import Path


def _git_enabled() -> bool:
    """Return False if GIT_INTEGRATION env var is set to 'false'."""
    return os.environ.get("GIT_INTEGRATION", "true").lower() not in ("false", "0", "no")


def _run(cmd: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
    """Run a git command, capturing output."""
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=10,
    )


def is_git_repo(path: str) -> bool:
    """Return True if path is inside a Git repository."""
    if not _git_enabled():
        return False
    try:
        result = _run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(Path(path).resolve().parent),
        )
        return result.returncode == 0
    except Exception:
        return False


def stage_file(file_path: str) -> bool:
    """Run git add on file_path. Return True on success."""
    if not _git_enabled():
        return False
    try:
        p = Path(file_path).resolve()
        result = _run(["git", "add", str(p)], cwd=str(p.parent))
        return result.returncode == 0
    except Exception:
        return False


def commit(repo_path: str, message: str, author: str = "office-mcp") -> str | None:
    """
    Run git commit with message.

    Return commit SHA on success, None on failure.
    Never raises — Git failures are non-fatal for document editing.
    """
    if not _git_enabled():
        return None
    try:
        result = _run(
            [
                "git",
                "commit",
                f"--author={author} <office-mcp@local>",
                "-m",
                message,
            ],
            cwd=repo_path,
        )
        if result.returncode != 0:
            return None
        # Extract SHA from output like "[branch abc1234] message"
        for line in result.stdout.splitlines():
            if line.startswith("["):
                parts = line.split()
                if len(parts) >= 2:
                    return parts[1].rstrip("]")
        return None
    except Exception:
        return None


def get_log(
    repo_path: str, file_path: str, max_entries: int = 20
) -> list[dict]:
    """Return Git log for file_path as list of dicts, newest first."""
    if not _git_enabled():
        return []
    try:
        result = _run(
            [
                "git",
                "log",
                f"--max-count={max_entries}",
                "--pretty=format:%H|%s|%ai|%an",
                "--",
                file_path,
            ],
            cwd=repo_path,
        )
        if result.returncode != 0:
            return []
        entries = []
        for line in result.stdout.splitlines():
            if not line:
                continue
            parts = line.split("|", 3)
            if len(parts) == 4:
                entries.append(
                    {
                        "sha": parts[0][:7],
                        "message": parts[1],
                        "timestamp": parts[2],
                        "author": parts[3],
                    }
                )
        return entries
    except Exception:
        return []


def create_branch(repo_path: str, branch_name: str) -> bool:
    """Create and checkout a new branch. Return True on success."""
    if not _git_enabled():
        return False
    try:
        result = _run(
            ["git", "checkout", "-b", branch_name],
            cwd=repo_path,
        )
        return result.returncode == 0
    except Exception:
        return False


def current_branch(repo_path: str) -> str:
    """Return current branch name, or 'HEAD' if detached."""
    if not _git_enabled():
        return "HEAD"
    try:
        result = _run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return "HEAD"
    except Exception:
        return "HEAD"


def diff_staged(repo_path: str) -> str:
    """Return git diff --staged output as string."""
    if not _git_enabled():
        return ""
    try:
        result = _run(["git", "diff", "--staged"], cwd=repo_path)
        return result.stdout if result.returncode == 0 else ""
    except Exception:
        return ""
