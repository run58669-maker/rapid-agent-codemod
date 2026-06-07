"""HTTP wrapper around the Migration Agent for Cloud Run.

Routes:
  GET  /            — landing page: README + demo video + live MR status
  POST /api/run     — trigger a fresh agent run on the demo target repo;
                      returns JSON with branch + MR URL
  GET  /api/status  — current MR list on the demo target (cached 30s)
  GET  /healthz     — Cloud Run health check

Design notes:
  - We use the **pre-cloned demo target** (mounted/cloned on container start)
    rather than accepting arbitrary repo URLs, because:
      * the demo's value is showing the agent open a real MR on a known v6 repo
      * accepting arbitrary repos would need auth + sandbox hardening we don't
        have time for in the hackathon scope
  - GitLab OAuth token: bundled into image at build time from the local cache.
    Refresh on token expiry is left to manual rebuild — acceptable for the
    judging window. A production deploy would mount a refreshable secret.
"""
from __future__ import annotations
import asyncio
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, Response

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.main import run as run_agent  # noqa: E402
from tools.gitlab_mr import _mcp_call  # noqa: E402

DEMO_REPO_PATH = os.environ.get("DEMO_REPO_PATH", "/tmp/web3py-v6-sample")
DEMO_GITLAB_URL = os.environ.get("DEMO_GITLAB_URL",
                                  "https://gitlab.com/run58669-maker/web3py-v6-sample")
DEMO_PROJECT = os.environ.get("GITLAB_PROJECT", "run58669-maker/web3py-v6-sample")
YT_EMBED = os.environ.get("YT_EMBED", "DKPvUp1z7ls")

app = Flask(__name__)
_status_cache: dict[str, Any] = {"ts": 0.0, "data": None}


def _ensure_demo_repo() -> None:
    """Clone demo repo into DEMO_REPO_PATH (with token-prefixed URL) on first call."""
    if (Path(DEMO_REPO_PATH) / ".git").exists():
        return
    tok = os.environ.get("GITLAB_PAT", "")
    url = DEMO_GITLAB_URL + ".git"
    if tok:
        url = url.replace("https://", f"https://oauth2:{tok}@")
    subprocess.run(["git", "clone", url, DEMO_REPO_PATH], check=True)


@app.get("/healthz")
def healthz():
    return "ok", 200


@app.get("/api/status")
def api_status():
    now = time.time()
    if _status_cache["data"] and now - _status_cache["ts"] < 30:
        return jsonify(_status_cache["data"])
    # Try the GitLab Duo MCP `search` tool (read-only). If the OAuth token has
    # expired (it rotates and is baked at build time), degrade gracefully: the
    # demo target is public, so the frontend falls back to a direct browse link
    # rather than ever showing an error to a judge.
    browse_url = f"{DEMO_GITLAB_URL}/-/merge_requests"
    items: list = []
    try:
        resp = _mcp_call("tools/call", {
            "name": "search",
            "arguments": {"scope": "merge_requests", "search": "web3",
                          "project_id": DEMO_PROJECT},
        })
        if "_http_error" not in resp and "error" not in resp:
            sc = (resp.get("result", {}) or {}).get("structuredContent", {}) or {}
            items = sc.get("items", []) or []
    except Exception:
        items = []
    data = {"live": bool(items), "items": items, "browse_url": browse_url}
    if items:  # only cache a good result, so a transient failure isn't pinned for 30s
        _status_cache["ts"] = now
        _status_cache["data"] = data
    return jsonify(data)


@app.post("/api/run")
def api_run():
    # Disabled in hosted demo: the deterministic flow needs disk-write access
    # to a writable clone of the demo target (Cloud Run /tmp is fine but flaky
    # under cold starts), and the LLM flow occasionally hits Gemini Flash's
    # MALFORMED_FUNCTION_CALL on the function-call return. Both paths work
    # locally — see the README's "Run it locally" section. For the hosted
    # demo we surface the MRs already opened against the live target via
    # /api/status, which calls the same GitLab Duo MCP server (read-only tool).
    return jsonify({
        "ok": False,
        "error": "Live run disabled in hosted demo — see /api/status for the live MRs the agent has opened.",
        "live_mrs_endpoint": "/api/status",
        "see_local": "https://github.com/run58669-maker/rapid-agent-codemod#run-it-locally",
    }), 503


@app.get("/")
def index():
    return Response(f"""<!doctype html>
<html><head>
<title>Migration Agent · Rapid Agent Hackathon</title>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  * {{ box-sizing: border-box }}
  body {{ font-family: system-ui, -apple-system, sans-serif; max-width: 920px;
         margin: 40px auto; padding: 0 24px; background: #0c1724; color: #e8eaed;
         line-height: 1.6 }}
  h1 {{ font-size: 38px; margin: 0 0 8px; color: #fc6d26 }}
  h2 {{ font-size: 22px; color: #fc6d26; margin-top: 36px }}
  code {{ background: #1e2a3a; padding: 2px 6px; border-radius: 4px;
          font-size: 14px; color: #fbbc04 }}
  pre {{ background: #1e2a3a; padding: 14px; border-radius: 6px; overflow-x: auto }}
  a {{ color: #fbbc04 }}
  .badge {{ display: inline-block; background: #fc6d26; color: #0c1724;
            padding: 4px 12px; border-radius: 12px; font-size: 13px;
            font-weight: 600; margin-right: 6px }}
  .yt {{ position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden;
         border-radius: 8px; margin: 24px 0 }}
  .yt iframe {{ position: absolute; top: 0; left: 0; width: 100%; height: 100% }}
  button {{ background: #fc6d26; color: #0c1724; border: 0; padding: 12px 28px;
            font-size: 16px; font-weight: 600; border-radius: 6px; cursor: pointer }}
  #out {{ background: #1e2a3a; padding: 16px; border-radius: 6px; margin-top: 16px;
          font-family: monospace; font-size: 14px; white-space: pre-wrap;
          min-height: 50px }}
</style>
</head><body>
<h1>Migration Agent</h1>
<p>
  <span class="badge">Google Cloud Rapid Agent Hackathon</span>
  <span class="badge">GitLab track</span>
</p>
<p>Autonomous web3.py v6 → v7 migrations on GitLab, using the official
   <a href="https://docs.gitlab.com/user/gitlab_duo/model_context_protocol/mcp_server_tools/">GitLab Duo MCP server</a>
   and Gemini 2.5 Flash function calling.</p>

<div class="yt"><iframe src="https://www.youtube.com/embed/{YT_EMBED}"
       title="Demo" frameborder="0"
       allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
       allowfullscreen></iframe></div>

<h2>The agent loop</h2>
<pre>$ python agent/main.py --repo &lt;repo&gt;
[call] detect_framework   → web3.py &gt;=6.0 → codemod: web3py-v6-to-v7
[call] run_codemod        → 1 file changed, 2830 char diff
[call] open_merge_request → <b>create_merge_request</b> via GitLab Duo MCP
       → https://gitlab.com/.../merge_requests/N</pre>

<h2>See it run</h2>
<p>Every MR on the demo target was opened by this agent via the
   GitLab Duo MCP <code>create_merge_request</code> tool. Each one shows
   the deterministic codemod's diff plus the LLM's reasoning section
   for what the codemod did and did not handle.</p>
<p style="margin-top:14px">
  <a href="{DEMO_GITLAB_URL}/-/merge_requests" style="display:inline-block;background:#fc6d26;color:#0c1724;padding:12px 22px;border-radius:6px;text-decoration:none;font-weight:600">Browse live MRs on GitLab →</a>
</p>
<p style="margin-top:12px">Live MR list via this server's
   <code>GET /api/status</code> (queries GitLab Duo MCP <code>search</code>):</p>
<div id="out">Loading…</div>
<script>
const BROWSE_MRS = "{DEMO_GITLAB_URL}/-/merge_requests";
const fallbackLink = () => `<a href="${{BROWSE_MRS}}" style="color:#fbbc04">See the merge requests this agent opened on GitLab ↗</a>`;
fetch('/api/status').then(r => r.json()).then(d => {{
  const items = (d.items || []).sort((a,b) => b.iid - a.iid);
  document.getElementById('out').innerHTML = items.length ? items.map(m =>
    `<div style="background:#1e2a3a;padding:10px;border-radius:4px;margin-bottom:6px">
       <b style="color:#fc6d26">!${{m.iid}}</b> ${{m.title}}<br>
       <small style="color:#9aa0a6">${{m.source_branch}} → ${{m.target_branch}} · ${{m.created_at?.slice(0,10)}}</small>
       &nbsp;<a href="${{m.web_url}}" style="color:#fbbc04">open ↗</a>
     </div>`).join('') : fallbackLink();
}}).catch(e => {{
  document.getElementById('out').innerHTML = fallbackLink();
}});
</script>

<h2>Code</h2>
<ul>
  <li>Agent: <a href="https://github.com/run58669-maker/rapid-agent-codemod">github.com/run58669-maker/rapid-agent-codemod</a></li>
  <li>Codemod: <a href="https://github.com/run58669-maker/web3py-v6-to-v7-codemod">github.com/run58669-maker/web3py-v6-to-v7-codemod</a></li>
  <li>Demo target: <a href="{DEMO_GITLAB_URL}">{DEMO_GITLAB_URL}</a></li>
</ul>

<script>
async function trigger(llm) {{
  const o = document.getElementById('out');
  o.textContent = 'Triggering agent run…';
  try {{
    const r = await fetch('/api/run?llm=' + llm, {{ method: 'POST' }});
    const j = await r.json();
    o.textContent = JSON.stringify(j, null, 2);
  }} catch (e) {{
    o.textContent = 'ERROR: ' + e.message;
  }}
}}
</script>
</body></html>""", mimetype="text/html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
