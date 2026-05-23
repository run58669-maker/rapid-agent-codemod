"""Migration Agent — Gemini function-calling loop.

Tools exposed to the model:
  - detect_framework(repo_root): which framework + version is this repo on?
  - run_codemod(name, repo_root): apply a registered codemod; return diff.
  - open_merge_request(repo_root, branch, title, body): push + create MR.

The model decides the order. v1 path is straight-line:
  detect → run_codemod (web3py-v6-to-v7) → open_merge_request.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

# Make tools/ importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.detect_framework import detect_web3_version  # noqa: E402
from tools.run_codemod import run_codemod              # noqa: E402
from tools.gitlab_mr import open_merge_request         # noqa: E402

try:
    import google.generativeai as genai
except ImportError:
    genai = None


TOOLS = [
    {
        "name": "detect_framework",
        "description": "Inspect a checked-out repo and report which framework + version it uses.",
        "parameters": {
            "type": "object",
            "properties": {"repo_root": {"type": "string"}},
            "required": ["repo_root"],
        },
    },
    {
        "name": "run_codemod",
        "description": "Apply a registered codemod in place to a repo. Returns the diff.",
        "parameters": {
            "type": "object",
            "properties": {
                "codemod_name": {"type": "string"},
                "repo_root": {"type": "string"},
            },
            "required": ["codemod_name", "repo_root"],
        },
    },
    {
        "name": "open_merge_request",
        "description": "Stage current changes onto a new branch, push to GitLab, open MR.",
        "parameters": {
            "type": "object",
            "properties": {
                "repo_root": {"type": "string"},
                "branch": {"type": "string"},
                "title": {"type": "string"},
                "body": {"type": "string"},
                "base": {"type": "string"},
            },
            "required": ["repo_root", "branch", "title", "body"],
        },
    },
]


def _dispatch(name: str, args: dict) -> dict:
    if name == "detect_framework":
        return detect_web3_version(args["repo_root"])
    if name == "run_codemod":
        return run_codemod(args["codemod_name"], args["repo_root"])
    if name == "open_merge_request":
        return open_merge_request(
            repo_root=args["repo_root"],
            branch=args["branch"],
            title=args["title"],
            body=args["body"],
            base=args.get("base", "main"),
        )
    return {"ok": False, "error": f"unknown tool: {name}"}


SYSTEM_PROMPT = """You are a migration agent. Given a checked-out Python repo,
your job is to:
  1. detect_framework on it
  2. if it uses an outdated framework version we have a codemod for, run that
     codemod
  3. open a Merge Request with a clear before/after summary in the body.

Stop after the MR is open or you determine no migration is needed. Be terse in
your final answer to the user; the value is in the MR body, not in chat."""


def run(repo_root: str, dry_run: bool = False) -> None:
    if dry_run or genai is None:
        # Fallback: straight-line deterministic flow, no LLM. Useful for CI and
        # when the API key isn't set yet.
        det = detect_web3_version(repo_root)
        print("[detect]", json.dumps(det, indent=2))
        if not det.get("suggested_codemod"):
            print("no migration needed")
            return
        diff = run_codemod(det["suggested_codemod"], repo_root)
        print(f"[codemod] changed={len(diff.get('changed_files', []))} files, "
              f"diff={len(diff.get('diff',''))} chars")
        if not diff.get("ok"):
            print("[codemod] FAILED:", diff.get("error"))
            return
        mr = open_merge_request(
            repo_root=repo_root,
            branch=f"chore/{det['suggested_codemod']}",
            title=f"chore: {det['framework']} migration ({det['suggested_codemod']})",
            body=f"Automated migration.\n\nFiles touched: {len(diff['changed_files'])}\n",
        )
        print("[mr]", json.dumps(mr, indent=2))
        return

    # LLM path
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: set GEMINI_API_KEY (or pass --dry-run)", file=sys.stderr)
        sys.exit(2)
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=SYSTEM_PROMPT,
        tools=[{"function_declarations": TOOLS}],
    )
    chat = model.start_chat()
    prompt = f"Repo to migrate: {repo_root}"
    resp = chat.send_message(prompt)

    while True:
        fc = None
        for part in resp.candidates[0].content.parts:
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                break
        if fc is None:
            print(resp.text)
            return
        args = {k: v for k, v in fc.args.items()}
        print(f"[call] {fc.name}({args})")
        result = _dispatch(fc.name, args)
        print(f"[result] {json.dumps(result)[:300]}")
        resp = chat.send_message(
            genai.protos.Content(
                role="function",
                parts=[genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=fc.name, response={"result": json.dumps(result)},
                    ),
                )],
            )
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="path to a checked-out git repo")
    ap.add_argument("--dry-run", action="store_true",
                    help="skip Gemini; run the straight-line flow")
    args = ap.parse_args()
    run(args.repo, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
