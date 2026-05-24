"""Open a GitLab Merge Request via the **official GitLab Duo MCP server**.

Flow:
  1. git branch + commit + push to GitLab over HTTPS (uses configured remote)
  2. Call GitLab Duo MCP server's `create_merge_request` tool over HTTP
     with the OAuth bearer token stored by mcp-remote.

Why MCP and not the plain REST API?
  Google Cloud Rapid Agent Hackathon requires the agent to use the partner
  entity's MCP server. GitLab is one of the six listed partners; their MCP
  server lives at https://gitlab.com/api/v4/mcp (Premium/Ultimate tier).

OAuth bootstrap (one-time):
    npx mcp-remote https://gitlab.com/api/v4/mcp
  This opens a browser for OAuth Dynamic Client Registration. The resulting
  bearer token lands in ~/.mcp-auth/mcp-remote-*/<server-hash>_tokens.json
  and we read it from there. Tokens refresh themselves via mcp-remote on its
  next invocation; for unattended Cloud Run runs, pre-bake a long-lived
  refresh_token into a Secret Manager entry.
"""
from __future__ import annotations
import glob
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime
from pathlib import Path

GITLAB_MCP_URL = os.environ.get("GITLAB_MCP_URL", "https://gitlab.com/api/v4/mcp")
GITLAB_PROJECT_DEFAULT = os.environ.get("GITLAB_PROJECT", "run58669-maker/web3py-v6-sample")


def _token_files() -> tuple[Path, Path]:
    """Locate the mcp-remote token + client_info file pair (most recent)."""
    home = Path(os.path.expanduser("~"))
    tokens = list(home.glob(".mcp-auth/mcp-remote-*/*_tokens.json"))
    if not tokens:
        raise RuntimeError(
            "No MCP OAuth token cache found. Run once interactively: "
            "npx mcp-remote https://gitlab.com/api/v4/mcp"
        )
    tokens.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    tok_path = tokens[0]
    info_path = tok_path.parent / tok_path.name.replace("_tokens.json", "_client_info.json")
    return tok_path, info_path


def _refresh_token(tok_path: Path, info_path: Path) -> dict:
    """POST refresh_token grant to GitLab; persist + return the new token blob."""
    with open(tok_path, "r", encoding="utf-8") as f:
        cur = json.load(f)
    with open(info_path, "r", encoding="utf-8") as f:
        info = json.load(f)
    refresh = cur.get("refresh_token")
    client_id = info.get("client_id")
    if not refresh or not client_id:
        raise RuntimeError("Missing refresh_token or client_id; need fresh OAuth")
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": client_id,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://gitlab.com/oauth/token",
        data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        new = json.loads(resp.read().decode("utf-8"))
    # Persist back to the same file. On read-only Cloud Run FS this raises;
    # the in-process cache below still keeps the refreshed token usable for
    # the lifetime of this container instance.
    try:
        with open(tok_path, "w", encoding="utf-8") as f:
            json.dump(new, f)
    except OSError:
        pass
    return new


_token_cache: dict | None = None


def _find_oauth_token(*, force_refresh: bool = False) -> str:
    """Bearer token getter with auto-refresh on near-expiry.

    Caches the live token in process memory so a single Cloud Run container
    avoids re-reading the file on every MCP call.
    """
    global _token_cache
    tok_path, info_path = _token_files()
    if _token_cache is None or force_refresh:
        with open(tok_path, "r", encoding="utf-8") as f:
            _token_cache = json.load(f)
            # Stamp loaded-at if absent (mcp-remote writes created_at unix ts).
            _token_cache.setdefault("loaded_at",
                                    _token_cache.get("created_at",
                                                     int(tok_path.stat().st_mtime)))
    cached = _token_cache
    expires_at = float(cached.get("loaded_at", 0)) + float(cached.get("expires_in", 7200))
    import time as _t
    if force_refresh or _t.time() >= expires_at - 60:
        new = _refresh_token(tok_path, info_path)
        new["loaded_at"] = int(_t.time())
        _token_cache = new
    return _token_cache["access_token"]


def _mcp_call(method: str, params: dict | None = None, *, request_id: int = 1,
              _retry_on_401: bool = True) -> dict:
    """JSON-RPC over HTTP to GitLab Duo MCP server. Auto-refreshes on 401."""
    token = _find_oauth_token()
    body = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        body["params"] = params
    req = urllib.request.Request(
        GITLAB_MCP_URL,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 401 and _retry_on_401:
            _find_oauth_token(force_refresh=True)
            return _mcp_call(method, params, request_id=request_id, _retry_on_401=False)
        raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return {"_http_error": e.code, "_body": raw[:500]}
    # Server-Sent Events or raw JSON depending on response
    if raw.startswith("event:") or raw.startswith("data:"):
        for line in raw.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
    return json.loads(raw)


def _run(cmd, cwd=None):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=cwd)


def open_merge_request(
    repo_root: str,
    branch: str,
    title: str,
    body: str,
    base: str = "main",
    project: str | None = None,
) -> dict:
    """Commit current uncommitted changes onto `branch`, push, open MR via MCP."""
    repo = Path(repo_root).resolve()
    if not (repo / ".git").exists():
        return {"ok": False, "error": f"{repo} is not a git repo"}

    project = project or GITLAB_PROJECT_DEFAULT
    steps = []

    # Avoid clobbering an existing branch.
    r = _run(["git", "-C", str(repo), "rev-parse", "--verify", branch])
    if r.returncode == 0:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        branch = f"{branch}-{ts}"
    steps.append(("checkout -b", _run(["git", "-C", str(repo), "checkout", "-b", branch])))
    steps.append(("add", _run(["git", "-C", str(repo), "add", "-A"])))
    steps.append(("commit", _run(["git", "-C", str(repo), "commit", "-m", title], cwd=str(repo))))
    steps.append(("push", _run(["git", "-C", str(repo), "push", "-u", "origin", branch])))

    failures = [(name, r.returncode, r.stderr.strip()[:300])
                for name, r in steps if r.returncode != 0]
    if failures:
        return {"ok": False, "branch": branch, "git_failures": failures}

    # MR creation via GitLab Duo MCP server.
    mcp_resp = _mcp_call("tools/call", {
        "name": "create_merge_request",
        "arguments": {
            "id": project,
            "source_branch": branch,
            "target_branch": base,
            "title": title,
            "description": body,
        },
    })
    if "_http_error" in mcp_resp:
        return {"ok": False, "branch": branch, "mcp_http_error": mcp_resp}
    if "error" in mcp_resp:
        return {"ok": False, "branch": branch, "mcp_error": mcp_resp["error"]}

    # Extract MR URL from the tool result content.
    result = mcp_resp.get("result", {})
    structured = result.get("structuredContent") or {}
    mr_url = (structured.get("web_url") or structured.get("url") or "")
    if not mr_url:
        # Fallback: parse from text content
        for part in result.get("content", []):
            if part.get("type") == "text":
                txt = part.get("text", "")
                if "merge_requests/" in txt:
                    import re
                    m = re.search(r"https://gitlab\.com/[^\s\"']+merge_requests/\d+", txt)
                    if m: mr_url = m.group(0); break

    return {
        "ok": True,
        "branch": branch,
        "mcp_tool": "create_merge_request",
        "mr_url": mr_url,
        "raw_mcp_result": result if not mr_url else None,
    }


if __name__ == "__main__":
    print(json.dumps(open_merge_request(
        repo_root=sys.argv[1],
        branch=sys.argv[2],
        title=sys.argv[3],
        body=sys.argv[4],
    ), indent=2))
