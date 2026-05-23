"""Run a registered codemod on a checked-out repo and return the diff.

v1 only knows about web3py-v6-to-v7 (path is hardcoded — the sibling repo).
Returns a dict the agent can summarize; never mutates anything outside the
target repo's worktree.
"""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
from pathlib import Path

_CODEMOD_REGISTRY = {
    # name → absolute path to the codemod source (jssg index.ts)
    "web3py-v6-to-v7": Path(__file__).resolve().parents[2] / "codemod-web3py-v7",
}


def run_codemod(codemod_name: str, repo_root: str) -> dict:
    """Apply the codemod in-place to repo_root; return {changed_files, diff, ok}."""
    cm_dir = _CODEMOD_REGISTRY.get(codemod_name)
    if cm_dir is None:
        return {"ok": False, "error": f"unknown codemod: {codemod_name}"}
    if not cm_dir.exists():
        return {"ok": False, "error": f"codemod dir missing: {cm_dir}"}

    repo = Path(repo_root).resolve()
    if not (repo / ".git").exists():
        return {"ok": False, "error": f"{repo} is not a git repo"}

    # Use codemod jssg to apply in-place.
    src_ts = cm_dir / "src" / "index.ts"
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if npx is None:
        return {"ok": False, "error": "npx not on PATH"}
    cmd = [
        npx, "--yes", "codemod", "jssg", "run",
        "--language", "python",
        "--target", str(repo),
        "--allow-dirty", "--no-interactive",
        str(src_ts),
    ]
    # shell=True on Windows so .cmd shims resolve; safe — args are list, no user input.
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(cm_dir),
        shell=(sys.platform == "win32"),
    )
    if proc.returncode != 0:
        return {"ok": False, "error": f"codemod run failed: {proc.stderr.strip()[:500]}"}

    # Capture diff via git.
    diff = subprocess.run(
        ["git", "-C", str(repo), "diff", "--unified=3"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout
    changed = subprocess.run(
        ["git", "-C", str(repo), "diff", "--name-only"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout.strip().splitlines()

    return {"ok": True, "codemod": codemod_name, "changed_files": changed, "diff": diff[:50000]}


if __name__ == "__main__":
    import json, sys
    print(json.dumps(run_codemod(sys.argv[1], sys.argv[2]), indent=2))
