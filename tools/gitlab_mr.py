"""Open a GitLab Merge Request via the `glab` CLI.

Assumes:
  - GITLAB_TOKEN is set in the env (or `glab auth login` has been run)
  - The repo at repo_root has a configured remote pointing to gitlab.com
"""
from __future__ import annotations
import os
import subprocess
from pathlib import Path
from datetime import datetime

# Resolve once — on Windows the winget install lands here and may not be on PATH yet.
GLAB = (
    os.environ.get("GLAB_BIN")
    or r"C:\Users\86150\AppData\Local\Programs\glab\glab.exe"
)


def _run(cmd, cwd=None):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=cwd)


def open_merge_request(
    repo_root: str,
    branch: str,
    title: str,
    body: str,
    base: str = "main",
) -> dict:
    """Commit current uncommitted changes onto `branch`, push, open MR."""
    repo = Path(repo_root).resolve()
    if not (repo / ".git").exists():
        return {"ok": False, "error": f"{repo} is not a git repo"}

    steps = []

    # Stash branch (don't overwrite existing).
    r = _run(["git", "-C", str(repo), "rev-parse", "--verify", branch])
    if r.returncode == 0:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        branch = f"{branch}-{ts}"
    steps.append(("checkout -b", _run(["git", "-C", str(repo), "checkout", "-b", branch])))
    steps.append(("add", _run(["git", "-C", str(repo), "add", "-A"])))
    steps.append(("commit", _run(
        ["git", "-C", str(repo), "commit", "-m", title], cwd=str(repo))))
    steps.append(("push", _run(
        ["git", "-C", str(repo), "push", "-u", "origin", branch])))

    failures = [(name, r.returncode, r.stderr.strip()[:300])
                for name, r in steps if r.returncode != 0]
    if failures:
        return {"ok": False, "branch": branch, "git_failures": failures}

    mr_cmd = [GLAB, "mr", "create",
              "--title", title,
              "--description", body,
              "--source-branch", branch,
              "--target-branch", base,
              "--yes"]
    r = _run(mr_cmd, cwd=str(repo))
    if r.returncode != 0:
        return {"ok": False, "branch": branch, "glab_stderr": r.stderr.strip()[:500]}

    return {"ok": True, "branch": branch, "glab_stdout": r.stdout.strip()}


if __name__ == "__main__":
    import json, sys
    print(json.dumps(open_merge_request(
        repo_root=sys.argv[1],
        branch=sys.argv[2],
        title=sys.argv[3],
        body=sys.argv[4],
    ), indent=2))
