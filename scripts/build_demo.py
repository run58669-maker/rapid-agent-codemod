"""Build the demo video for the Migration Agent (Google Cloud Rapid Agent Hackathon).

Pipeline:
  1. edge-tts → per-scene narration MP3
  2. Playwright → per-scene visual PNG
     - scenes with "html": render the HTML headless at 1920x1080
     - scenes with "url":  navigate to the LIVE page and screenshot it (real footage)
  3. ffmpeg image+audio → per-scene MP4
  4. ffmpeg concat → final demo.mp4

v2 changes (2026-06): every "glab CLI" mention corrected to the **GitLab Duo MCP
server** (the load-bearing, hackathon-judged integration); the agent-loop and
merge-request scenes now use the REAL run output (MR !4) and a REAL screenshot of
the live merge request, not hand-authored mockups.

Run:
    cd rapid-agent-codemod
    python scripts/build_demo.py
"""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import edge_tts
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "demo"
VOICE = "en-US-AriaNeural"

LIVE_MR_URL = "https://gitlab.com/run58669-maker/web3py-v6-sample/-/merge_requests/4"


SCENES: list[dict] = [
    {
        "id": "01_hook",
        "narration": (
            "You maintain a Python project on web3.py. Version 7 just landed — "
            "twelve plus breaking changes. It's Friday. The renames, the import "
            "swaps, the snake-cased kwargs — all on you, by hand. Migration Agent "
            "does that part for you, and opens a merge request you can actually review."
        ),
        "html": """<div style="font-family:system-ui;color:#fff;background:#0c1724;height:100vh;display:flex;flex-direction:column;justify-content:center;padding:60px">
            <h1 style="font-size:64px;margin:0;color:#fc6d26">Migration Agent</h1>
            <p style="font-size:32px;margin-top:24px">Autonomous web3.py v6 to v7 migrations on GitLab</p>
            <p style="font-size:22px;margin-top:48px;color:#9aa0a6">Google Cloud Rapid Agent Hackathon &middot; GitLab track</p>
            <p style="font-size:18px;margin-top:24px;color:#9aa0a6">codemod-web3py-v7 &nbsp;+&nbsp; Gemini 2.5 Flash &nbsp;+&nbsp; GitLab Duo MCP</p>
        </div>""",
    },
    {
        "id": "02_whatis",
        "narration": (
            "It's an autonomous agent. Gemini 2.5 Flash drives the loop; it detects "
            "the framework, runs a deterministic codemod, and opens the merge request "
            "through GitLab's own Duo MCP server. Hosted on Cloud Run. No human in the loop."
        ),
        "html": """<div style="font-family:system-ui;color:#fff;background:#0c1724;height:100vh;display:flex;flex-direction:column;justify-content:center;padding:60px">
            <h1 style="font-size:46px;margin:0;color:#fc6d26">An agent, not a script</h1>
            <div style="display:flex;gap:18px;margin-top:40px;flex-wrap:wrap">
                <div style="background:#1e2a3a;padding:18px 26px;border-radius:8px;font-size:22px">🧠 Gemini 2.5 Flash <span style="color:#9aa0a6;font-size:16px">· function calling</span></div>
                <div style="background:#1e2a3a;padding:18px 26px;border-radius:8px;font-size:22px">🔗 GitLab Duo MCP <span style="color:#9aa0a6;font-size:16px">· create_merge_request</span></div>
                <div style="background:#1e2a3a;padding:18px 26px;border-radius:8px;font-size:22px">☁️ Cloud Run <span style="color:#9aa0a6;font-size:16px">· hosted</span></div>
            </div>
            <p style="font-size:24px;margin-top:44px;color:#9aa0a6">Detect → codemod → open a reviewed MR. No human in the loop.</p>
        </div>""",
    },
    {
        "id": "03_problem",
        "narration": (
            "The work is mechanical and boring. Provider classes renamed. "
            "ABI types moved out of web3.types. Whole modules — ethpm, geth.miner — "
            "removed. Every team that upgrades hits the same wall and does the same rewrite."
        ),
        "html": """<div style="font-family:system-ui;color:#0c1724;background:#fff;height:100vh;padding:48px">
            <h1 style="font-size:44px;color:#fc6d26;margin:0">The web3.py v6 → v7 wall</h1>
            <p style="font-size:22px;margin-top:12px;color:#555">12+ breaking changes &middot; same boring rewrites &middot; every team</p>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:36px;font-size:20px;font-family:'Cascadia Code',monospace">
                <div style="background:#f1f3f4;padding:20px;border-radius:6px;border-left:6px solid #ea4335">
                    <div style="color:#777;font-size:14px">v6</div>
                    WebsocketProvider<br>
                    WebsocketProviderV2<br>
                    ABIEventFunctionNotFound<br>
                    BlockNumberOutofRange<br>
                    contract.encodeABI(...)<br>
                    create_filter(fromBlock=, toBlock=)<br>
                    listen_to_websocket()<br>
                    CallOverride
                </div>
                <div style="background:#f1f3f4;padding:20px;border-radius:6px;border-left:6px solid #34a853">
                    <div style="color:#777;font-size:14px">v7</div>
                    LegacyWebSocketProvider<br>
                    WebSocketProvider<br>
                    ABIEventNotFound<br>
                    BlockNumberOutOfRange<br>
                    contract.encode_abi(...)<br>
                    create_filter(from_block=, to_block=)<br>
                    process_subscriptions()<br>
                    StateOverride
                </div>
            </div>
            <p style="margin-top:28px;font-size:18px;color:#555">Plus removed modules: <code>ethpm</code>, <code>web3.geth.miner</code></p>
        </div>""",
    },
    {
        "id": "04_pipeline",
        "narration": (
            "Three tools. detect_framework reads requirements and imports. "
            "run_codemod calls a deterministic AST rewriter — zero false positives. "
            "open_merge_request commits, pushes, then calls the GitLab Duo MCP server's "
            "create_merge_request tool over JSON-RPC. Gemini decides the order."
        ),
        "html": """<div style="font-family:system-ui;color:#fff;background:#0c1724;height:100vh;padding:40px">
            <h1 style="font-size:42px;color:#fc6d26;margin:0">Three tools. One agent loop.</h1>
            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:24px;margin-top:48px">
                <div style="background:#1e2a3a;padding:28px;border-radius:8px;border-top:5px solid #fc6d26">
                    <div style="font-size:14px;color:#9aa0a6">TOOL 1</div>
                    <div style="font-size:24px;font-family:'Cascadia Code',monospace;margin-top:8px;color:#fc6d26">detect_framework</div>
                    <p style="font-size:17px;margin-top:18px;line-height:1.5">Reads requirements.txt, pyproject.toml, *.py imports. Returns suggested codemod.</p>
                </div>
                <div style="background:#1e2a3a;padding:28px;border-radius:8px;border-top:5px solid #fc6d26">
                    <div style="font-size:14px;color:#9aa0a6">TOOL 2</div>
                    <div style="font-size:24px;font-family:'Cascadia Code',monospace;margin-top:8px;color:#fc6d26">run_codemod</div>
                    <p style="font-size:17px;margin-top:18px;line-height:1.5">Calls jssg on the Python AST. Deterministic rewrites, zero false positives. Returns the diff.</p>
                </div>
                <div style="background:#1e2a3a;padding:28px;border-radius:8px;border-top:5px solid #fc6d26">
                    <div style="font-size:14px;color:#9aa0a6">TOOL 3</div>
                    <div style="font-size:24px;font-family:'Cascadia Code',monospace;margin-top:8px;color:#fc6d26">open_merge_request</div>
                    <p style="font-size:17px;margin-top:18px;line-height:1.5">git commit + push, then <b style="color:#fc6d26">GitLab Duo MCP</b> &middot; create_merge_request (JSON-RPC + OAuth).</p>
                </div>
            </div>
            <p style="margin-top:48px;font-size:20px;color:#9aa0a6;text-align:center">Powered by <span style="color:#fc6d26">Gemini 2.5 Flash</span> · function calling</p>
        </div>""",
    },
    {
        "id": "05_agent_loop",
        "narration": (
            "Here it is on a real repository. Detect picks up web3 v6. "
            "The codemod runs — one file changed. Then open_merge_request pushes a "
            "branch and calls create_merge_request on the GitLab Duo MCP server. "
            "It returns a real merge request URL. No human in the loop."
        ),
        "html": """<div style="font-family:system-ui;color:#fff;background:#0c1724;height:100vh;padding:40px">
            <h1 style="font-size:36px;color:#fc6d26;margin:0">Agent loop · live run</h1>
            <pre style="font-size:17px;background:#1e2a3a;padding:24px;border-radius:8px;margin-top:24px;color:#e8eaed;line-height:1.55;font-family:'Cascadia Code',monospace">$ python agent/main.py --repo ../web3py-v6-sample

[call] <span style="color:#fbbc04">detect_framework</span>({"repo_root": "../web3py-v6-sample"})
[result] {"framework": "web3.py", "declared_version": "&gt;=6.0",
         "suggested_codemod": "<span style="color:#34a853">web3py-v6-to-v7</span>"}

[call] <span style="color:#fbbc04">run_codemod</span>({"codemod_name": "web3py-v6-to-v7", ...})
[result] {"ok": true, "changed_files": ["app.py"], "diff": "&lt;...&gt;"}

[call] <span style="color:#fbbc04">open_merge_request</span>({"title": "Migrate web3.py from v6 to v7", ...})
[result] {"ok": true, "mcp_tool": "<span style="color:#fc6d26">create_merge_request</span>",
         "mr_url": "<span style="color:#34a853">https://gitlab.com/.../merge_requests/4</span>"}

I've opened a merge request to migrate web3.py from v6 to v7.</pre>
            <p style="margin-top:18px;font-size:18px;color:#9aa0a6">LIVE · real MR opened via the GitLab Duo MCP server</p>
        </div>""",
    },
    {
        "id": "06_mr_view",
        "narration": (
            "And here is that merge request, live on GitLab. The title and body were "
            "written by Gemini, not a template. The diff is the deterministic codemod "
            "output. The branch was committed, pushed, and the merge request opened "
            "through the GitLab Duo MCP server's create_merge_request tool."
        ),
        # REAL footage: screenshot the live MR page (public, no auth needed).
        "url": LIVE_MR_URL,
        "html": """<div style="font-family:system-ui;color:#0c1724;background:#fff;height:100vh;padding:32px">
            <h1 style="font-size:30px;color:#fc6d26;margin:0">Merge Request &middot; live on GitLab</h1>
            <div style="background:#fafafa;border:1px solid #ddd;border-radius:6px;padding:20px;margin-top:20px">
                <div style="font-size:18px;color:#777">!4 · web3py-v6-to-v7-migration into main</div>
                <h2 style="margin:6px 0 12px;font-size:28px;color:#fc6d26">Migrate web3.py from v6 to v7</h2>
                <pre style="font-size:14px;background:#f1f3f4;padding:14px;border-radius:6px;color:#222;line-height:1.5;overflow:hidden">- from web3.providers.websocket import WebsocketProvider, WebsocketProviderV2
+ from web3.providers.websocket import LegacyWebSocketProvider, WebSocketProvider
- from web3.types import ABI, ABIEvent, ABIFunction
+ from eth_typing import ABI, ABIEvent, ABIFunction
- return contract.encodeABI(fn_name="transfer", args=[recipient, amount])
+ return contract.encode_abi(abi_element_identifier="transfer", args=[recipient, amount])</pre>
            </div>
            <p style="margin-top:18px;font-size:16px;color:#777;font-family:'Cascadia Code',monospace">gitlab.com/run58669-maker/web3py-v6-sample/-/merge_requests/4</p>
        </div>""",
    },
    {
        "id": "07_reasoning",
        "narration": (
            "A codemod can't safely rewrite removed modules. So the agent reads the "
            "codemod's TODO comments and writes a Manual Review section into the merge "
            "request body — telling the reviewer exactly what's still on them. "
            "Honest about what it did not do."
        ),
        "html": """<div style="font-family:system-ui;color:#0c1724;background:#fff;height:100vh;padding:40px">
            <h1 style="font-size:36px;color:#fc6d26;margin:0">The reasoning layer</h1>
            <p style="font-size:20px;margin-top:10px;color:#555">Codemod = mechanical rewrites. Agent = surfacing what's left.</p>
            <div style="margin-top:28px;background:#fff7e6;border-left:6px solid #fc6d26;padding:24px;border-radius:6px">
                <p style="font-size:22px;font-weight:600;margin:0;color:#fc6d26">From the MR body, written by Gemini:</p>
                <pre style="font-size:18px;margin-top:14px;background:#fff;padding:18px;border-radius:6px;line-height:1.6;color:#222">**Manual Review and Further Steps Needed:**
*   The `ethpm` package was removed in web3.py v7.
    A manual rewrite is needed for its usage.
*   `web3.geth.miner` was removed in web3.py v7.
    A manual rewrite is needed for its usage.

Please review the changes and address the manual
rewrite tasks.</pre>
            </div>
            <p style="margin-top:32px;font-size:18px;color:#555">Codemod left TODO comments. Agent read them and wrote a reviewer-facing summary. Honest about what it didn't do.</p>
        </div>""",
    },
    {
        "id": "08_close",
        "narration": (
            "Three days by hand becomes one reviewed merge request in minutes. "
            "The Duo MCP integration is load-bearing — remove it and there is no merge "
            "request. Open source, MIT. Google Cloud Rapid Agent Hackathon, GitLab track."
        ),
        "html": """<div style="font-family:system-ui;color:#fff;background:#0c1724;height:100vh;display:flex;flex-direction:column;justify-content:center;padding:60px">
            <h1 style="font-size:54px;margin:0;color:#fc6d26">Migration Agent</h1>
            <p style="font-size:24px;margin-top:18px;color:#e8eaed">3 days by hand &nbsp;→&nbsp; 1 reviewed MR in minutes</p>
            <p style="font-size:22px;margin-top:18px;font-family:'Cascadia Code',monospace">github.com/run58669-maker/rapid-agent-codemod</p>
            <p style="font-size:18px;margin-top:6px;font-family:'Cascadia Code',monospace;color:#9aa0a6">gitlab.com/run58669-maker/web3py-v6-sample &nbsp;·&nbsp; live demo target</p>
            <p style="font-size:22px;margin-top:44px;color:#9aa0a6">Google Cloud Rapid Agent Hackathon &middot; GitLab track</p>
            <p style="font-size:18px;margin-top:24px;color:#9aa0a6">Gemini 2.5 Flash &middot; GitLab Duo MCP &middot; codemod jssg &middot; Cloud Run</p>
        </div>""",
    },
]


async def gen_audio():
    for scene in SCENES:
        out = OUT / f"{scene['id']}.mp3"
        comm = edge_tts.Communicate(scene["narration"], VOICE, rate="+0%")
        await comm.save(str(out))
        print(f"  audio: {out.name} ({out.stat().st_size//1024}KB)")


def gen_images():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()
        for scene in SCENES:
            out = OUT / f"{scene['id']}.png"
            url = scene.get("url")
            if url:
                # Real footage: navigate to the live page and screenshot it.
                try:
                    page.goto(url, wait_until="networkidle", timeout=60000)
                    page.wait_for_timeout(2500)
                    page.screenshot(path=str(out), full_page=False)
                    print(f"  image: {out.name}  (LIVE {url})")
                    continue
                except Exception as e:
                    print(f"  WARN live capture failed ({e}); falling back to html mock")
            html = f"<!doctype html><html><body style='margin:0'>{scene['html']}</body></html>"
            page.set_content(html)
            page.wait_for_timeout(200)
            page.screenshot(path=str(out), full_page=False)
            print(f"  image: {out.name}")
        browser.close()


def get_duration(audio_path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def render_scenes():
    list_file = OUT / "concat.txt"
    list_lines = []
    for scene in SCENES:
        img = OUT / f"{scene['id']}.png"
        aud = OUT / f"{scene['id']}.mp3"
        mp4 = OUT / f"{scene['id']}.mp4"
        dur = get_duration(aud) + 0.4
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-loop", "1", "-i", str(img),
             "-i", str(aud),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-tune", "stillimage",
             "-c:a", "aac", "-b:a", "192k",
             "-shortest", "-t", str(dur),
             "-vf", "scale=1920:1080",
             str(mp4)],
            check=True,
        )
        list_lines.append(f"file '{mp4.name}'")
        print(f"  scene mp4: {mp4.name} ({dur:.1f}s)")
    list_file.write_text("\n".join(list_lines), encoding="utf-8")
    final = OUT / "demo.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", str(list_file),
         "-c", "copy", str(final)],
        check=True,
    )
    print(f"\nFinal: {final} ({final.stat().st_size // 1024}KB)")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("=== 1. Generating narration audio (edge-tts) ===")
    asyncio.run(gen_audio())
    print("\n=== 2. Generating scene images (Playwright) ===")
    gen_images()
    print("\n=== 3. Rendering scenes + concatenating (ffmpeg) ===")
    render_scenes()


if __name__ == "__main__":
    main()
