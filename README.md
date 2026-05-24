# Migration Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
**Track**: GitLab · [Google Cloud Rapid Agent Hackathon](https://rapid-agent.devpost.com/)

An autonomous agent that migrates Python `web3.py` codebases from v6 → v7
and opens a clean Merge Request on GitLab — diff included, manual-review
TODOs called out, no human in the loop.

- **Live hosted demo**: <https://rapid-agent-codemod-945076065119.us-central1.run.app>
- **Demo target repo** (live, gets new MRs from each agent run): <https://gitlab.com/run58669-maker/web3py-v6-sample>
- **Demo video** (≤3 min): <https://youtu.be/DKPvUp1z7ls>
- **Sibling repo** — deterministic codemod: <https://github.com/run58669-maker/web3py-v6-to-v7-codemod>

## Why

Every Python team that depends on `web3.py` and hasn't moved to v7 hits the
same wall: 12+ mechanical breaking changes (renamed providers, snake-cased
kwargs, ABI types moved out of `web3.types`, whole modules — `ethpm`,
`web3.geth.miner` — removed). The work is boring, still done by hand on a
Friday night, and easy to get wrong. We wanted an agent that does the boring
part **and is honest about the parts it cannot do**.

## How it works

```
┌──────────────┐    detect_framework()      ┌────────────────────┐
│  Git repo    │ ─────────────────────────► │ Gemini 2.5 Flash   │
└──────────────┘                            │ (function calling) │
                                            └─────────┬──────────┘
            run_codemod(web3py-v6-to-v7) ◄────────────┤
                       │                              │
              ┌────────▼─────────┐                    │
              │ codemod-web3py-v7│  (deterministic,   │
              │   via jssg/npx   │   zero false +)    │
              └────────┬─────────┘                    │
                       │                              │
                  diff + TODOs                        │
                       │                              │
            open_merge_request() ◄───────────────────┘
                       │
              ┌────────▼─────────┐
              │ git push +       │
              │ GitLab Duo MCP   │  create_merge_request tool
              │ /api/v4/mcp      │  (OAuth Bearer)
              └────────┬─────────┘
                       ▼
                  Live MR on GitLab
```

The agent has three tools. Gemini decides the order and writes the MR title
and body — including a `Manual Review and Further Steps Needed` section
that surfaces the codemod's `TODO(web3py-v7)` comments to the reviewer.

## Tech stack

| Layer | What we used |
|---|---|
| Agent reasoning | **Gemini 2.5 Flash** via `google-generativeai` function calling |
| Hosted runtime | **Google Cloud Run** (Python 3.12 + Node 20 in one image) |
| Image build | **Cloud Build** → **gcr.io** (Container Registry) |
| Codemod runner | `npx codemod jssg run` on the sibling `codemod-web3py-v7` |
| **Partner MCP server** | **GitLab Duo MCP** at `https://gitlab.com/api/v4/mcp` — we call its `create_merge_request` and `search` tools |
| OAuth | RFC 7591 Dynamic Client Registration via `mcp-remote`; `refresh_token` rotation handled in `tools/gitlab_mr.py` |
| HTTP wrapper | Flask 3 + gunicorn 23 |

## GitLab Duo MCP integration

This is the part that satisfies the hackathon's "use a partner entity's MCP
server" rule. After enabling beta features on a Premium/Ultimate GitLab
group, one-time OAuth registers an MCP-CLI client via `mcp-remote`:

```bash
npx mcp-remote https://gitlab.com/api/v4/mcp
# browser opens, you Authorize, mcp-remote drops tokens into
# ~/.mcp-auth/mcp-remote-*/<server-hash>_tokens.json
```

After that, `tools/gitlab_mr.py` calls MCP directly over HTTP JSON-RPC:

```python
_mcp_call("tools/call", {
    "name": "create_merge_request",
    "arguments": {
        "id": "run58669-maker/web3py-v6-sample",
        "source_branch": branch,
        "target_branch": "main",
        "title": title,
        "description": body,
    },
})
```

`_mcp_call` watches the OAuth bearer's expiry and, within 60 s of timing
out (or on 401), POSTs a `refresh_token` grant to `gitlab.com/oauth/token`
and rotates the cached token. The hosted Cloud Run demo therefore runs
indefinitely off one initial OAuth handshake.

## Repo layout

```
rapid-agent-codemod/
├── agent/main.py             Gemini function-calling loop (171 LOC)
├── tools/
│   ├── detect_framework.py   reads requirements.txt / pyproject / imports
│   ├── run_codemod.py        invokes npx codemod jssg on the sibling repo
│   └── gitlab_mr.py          git push + GitLab Duo MCP create_merge_request
├── server/app.py             Flask wrapper for the Cloud Run demo
├── scripts/build_demo.py     edge-tts + Playwright + ffmpeg → demo.mp4
├── Dockerfile                Python 3.12 + Node 20 + git, runs gunicorn
└── requirements.txt
```

## Run it locally

```bash
git clone https://github.com/run58669-maker/rapid-agent-codemod.git
cd rapid-agent-codemod
pip install -r requirements.txt
npx mcp-remote https://gitlab.com/api/v4/mcp   # one-time OAuth
export GEMINI_API_KEY=...
python agent/main.py --repo /path/to/a/web3py-v6/repo
```

Or run the deterministic flow without spending Gemini quota:

```bash
python agent/main.py --repo /path/to/repo --dry-run
```

## Submission deliverables

- [x] Hosted demo on Cloud Run — <https://rapid-agent-codemod-945076065119.us-central1.run.app>
- [x] Public open-source repos with MIT license (this + the codemod sibling)
- [x] ≤3 min demo video — <https://youtu.be/DKPvUp1z7ls>
- [x] Devpost submission — <https://devpost.com/software/migration-agent>

## License

MIT
