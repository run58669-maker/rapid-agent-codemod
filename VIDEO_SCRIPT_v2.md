# Migration Agent — Demo Script v2 (≤3:00, TTS + captions, no live face/voice)

**What changed from v1**
1. Every "glab CLI" mention → **GitLab Duo MCP server** (the load-bearing, judged integration).
2. Scenes 4–5 ("live run" / "live MR") become a **real screen capture** of an actual
   `python agent/main.py` run that opens a real MR on `web3py-v6-sample`, not an HTML mockup.
3. Tighter persona hook; explicit before/after; MCP framed as "remove it and there is no MR".

Voice: edge-tts (A). Captions burned in (judges watch muted). Target 2:45–3:00.

---

### Scene 1 — Hook (0:00–0:15) · title card
**Narration:** "You maintain a Python project on web3.py. Version 7 just landed —
twelve-plus breaking changes. It's Friday. The renames, the import swaps, the
snake-cased kwargs — all on you, by hand. Migration Agent does that part for you,
and opens a merge request you can actually review."
**Caption:** `web3.py v6 → v7 · 12+ breaking changes · done by hand`

### Scene 2 — What it is (0:15–0:32) · title card
**Narration:** "It's an autonomous agent. Gemini 2.5 Flash drives the loop;
it detects the framework, runs a deterministic codemod, and opens the merge request
through GitLab's own Duo MCP server. Hosted on Cloud Run. No human in the loop."
**Caption:** `Gemini 2.5 Flash · GitLab Duo MCP · Cloud Run`

### Scene 3 — The wall (0:32–0:52) · v6/v7 grid (reuse v1 visual)
**Narration:** "The work is mechanical and boring. Provider classes renamed.
ABI types moved out of web3.types. Whole modules — ethpm, geth.miner — removed.
Every team that upgrades hits the same wall and does the same rewrite."
**Caption:** keep the v6→v7 two-column diff grid.

### Scene 4 — How it works (0:52–1:12) · three-tool diagram (FIX: MCP not glab)
**Narration:** "Three tools. detect_framework reads requirements and imports.
run_codemod calls a deterministic AST rewriter — zero false positives.
open_merge_request commits, pushes, then calls the GitLab Duo MCP server's
create_merge_request tool over JSON-RPC. Gemini decides the order."
**Caption / diagram edit:** Tool 3 box → `open_merge_request → GitLab Duo MCP · create_merge_request (JSON-RPC + OAuth)`. Remove every "glab" string.

### Scene 5 — LIVE run (1:12–2:10) · **REAL SCREEN CAPTURE** (the 60–90s judges want)
**Visual:** actual terminal recording of:
`python agent/main.py --repo ../web3py-v6-sample` →
real `[call] detect_framework` / `run_codemod` / `open_merge_request` lines →
then cut to the **real MR page on gitlab.com** that was just created.
**Narration:** "Here it is on a real repository. Detect picks up web3 v6.
The codemod runs — one file changed. Then open_merge_request pushes a branch and
calls create_merge_request on the GitLab Duo MCP server. That returns a real
merge request URL — and here is the merge request, live on GitLab. No template."
**Caption:** `LIVE · real MR opened via GitLab Duo MCP`

### Scene 6 — The honesty layer (2:10–2:35) · MR "Manual Review" body (reuse v1 visual)
**Narration:** "A codemod can't safely rewrite removed modules. So the agent reads
the codemod's TODO comments and writes a Manual Review section into the merge
request body — telling the reviewer exactly what's still on them. Honest about
what it didn't do."
**Caption:** `Agent-written: what it could NOT migrate`

### Scene 7 — Close (2:35–2:55) · before/after + links
**Narration:** "Three days by hand becomes one reviewed merge request in minutes.
The Duo MCP integration is load-bearing — remove it and there is no merge request.
Open source, MIT. Google Cloud Rapid Agent Hackathon, GitLab track."
**Caption:** `Before: 3 days by hand → After: 1 reviewed MR · github.com/run58669-maker/rapid-agent-codemod`

---

**Implementation notes (builder)**
- Pre-bake the Scene 5 capture: one clean `agent/main.py` run that opens a real MR
  (needs GEMINI_API_KEY + the existing `.mcp-auth` token). Run it 5×, keep the cleanest.
- Keep a fallback recording in case live MCP 401s during the final take.
- Re-record audio for scenes 1,2,4,5,7 (narration text changed); 3 and 6 narration can stay.
- In `build_demo.py`: update SCENES narration/HTML for the MCP fix; splice the real
  Scene-5 capture into the ffmpeg concat instead of a still PNG.
