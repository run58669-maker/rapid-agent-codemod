# Migration Agent for GitLab CI

**Track**: GitLab · Google Cloud Rapid Agent Hackathon

An autonomous agent that migrates Python web3 codebases from web3.py v6 → v7
and opens a clean Merge Request on GitLab — diff, before/after summary, and a
regression-test pipeline already wired up.

## Why

Every team upgrading web3.py 6 → 7 hits the same 12+ boring breaking changes:
renamed providers, snake_cased kwargs, moved ABI types, removed `personal` /
`geth.miner` / `ethpm`. We already shipped a deterministic codemod that
automates **86%** of it with **zero false positives**
([codemod-web3py-v7](../codemod-web3py-v7)). This agent wraps that codemod in a
Gemini reasoning loop and a GitLab integration so a maintainer can trigger one
command and walk away.

## How it works

```
┌─────────────┐    detect_framework_version()    ┌──────────────┐
│  Repo URL   │ ───────────────────────────────► │ Gemini agent │
└─────────────┘                                  └──────┬───────┘
                                                        │
                run_codemod(web3py_v6_to_v7)            │
                          ▼                             │
                ┌──────────────────┐                    │
                │ codemod-web3py-v7│                    │
                │   (deterministic)│                    │
                └────────┬─────────┘                    │
                         │                              │
                  diff + summary                        │
                         ▼                              │
                ┌──────────────────┐                    │
                │ open_merge_req() │ ◄──────────────────┘
                │   via glab CLI   │
                └──────────────────┘
                         │
                         ▼
                  GitLab MR + CI runs
```

## Tech stack

- **Gemini 2.5 Pro** — agent reasoning, function calling, MR description writing
- **Google Cloud Agent Builder / Vertex AI** — deployment target (Cloud Run)
- **GitLab MCP server** — exposes `create_merge_request`, `get_pipeline`,
  `list_issues` to the agent as MCP tools
- **codemod-web3py-v7** — deterministic AST rewrite layer (jssg / ast-grep)

## Quick start

```bash
pip install -r requirements.txt
export GEMINI_API_KEY=...
export GITLAB_TOKEN=...
python agent/main.py --repo https://gitlab.com/example/old-dapp
```

## Demo flow

1. Agent receives a GitLab repo URL
2. Clones, inspects `requirements.txt` / `pyproject.toml` → finds `web3==6.x`
3. Picks the matching codemod (web3py v6→v7)
4. Runs codemod, captures the diff
5. Opens a Merge Request:
   - Title: `chore: web3.py v6 → v7 migration`
   - Body: Gemini-written summary of what changed + manual review TODOs
   - CI: existing GitLab CI pipeline runs the project's tests on the new branch
6. Pings the maintainer

## Submission deliverables

- [ ] Hosted demo on Cloud Run
- [ ] This repo (MIT)
- [ ] ~3 min demo video
- [ ] Devpost form (GitLab track)

## License

MIT
