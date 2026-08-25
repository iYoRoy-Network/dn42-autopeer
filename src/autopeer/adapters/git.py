from __future__ import annotations

import subprocess
from pathlib import Path


class GitClient:
    """Small wrapper around Git commands used by the mutation worker.

    The backend commits only validated peer-file changes. Git remains the audit
    log and handoff point to the existing Bird2-Configuration workflow.
    """

    def __init__(
        self,
        repo_root: Path,
        *,
        author_name: str,
        author_email: str,
        timeout: int = 120,
    ):
        self.repo_root = repo_root
        self.author_name = author_name
        self.author_email = author_email
        self.timeout = timeout

    def run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            text=True,
            capture_output=True,
            timeout=self.timeout,
            check=False,
        )

    def status_porcelain(self) -> str:
        result = self.run(["status", "--porcelain"])
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout)
        return result.stdout

    def pull_ff_only(self) -> str:
        result = self.run(["pull", "--ff-only"])
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout)
        return result.stdout.strip()

    def assert_clean_or_only(self, allowed_paths: list[Path], allow_dirty: bool) -> None:
        if allow_dirty:
            return
        allowed = {
            str(path.relative_to(self.repo_root))
            for path in allowed_paths
            if path.is_relative_to(self.repo_root)
        }
        dirty = []
        for line in self.status_porcelain().splitlines():
            path = line[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            if path not in allowed:
                dirty.append(line)
        if dirty:
            raise RuntimeError("config repository has unrelated dirty files: " + "; ".join(dirty))

    def add_and_commit(self, paths: list[Path], message: str) -> str | None:
        rel_paths = [
            str(path.relative_to(self.repo_root))
            for path in paths
            if path.exists() or path.parent.exists()
        ]
        if not rel_paths:
            return None
        add = self.run(["add", "--", *rel_paths])
        if add.returncode != 0:
            raise RuntimeError(add.stderr or add.stdout)
        diff = self.run(["diff", "--cached", "--quiet"])
        if diff.returncode == 0:
            return None
        commit = self.run(
            [
                "-c",
                f"user.name={self.author_name}",
                "-c",
                f"user.email={self.author_email}",
                "commit",
                "-m",
                message,
            ]
        )
        if commit.returncode != 0:
            raise RuntimeError(commit.stderr or commit.stdout)
        rev = self.run(["rev-parse", "HEAD"])
        if rev.returncode != 0:
            raise RuntimeError(rev.stderr or rev.stdout)
        return rev.stdout.strip()

    def push(self) -> None:
        result = self.run(["push"])
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout)
