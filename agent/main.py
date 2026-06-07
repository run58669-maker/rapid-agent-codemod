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

import google.auth
from google.auth.transport.requests import Request
from openai import OpenAI

GCP_PROJECT = os.environ.get("GCP_PROJECT", "project-92324467-359f-463c-bb7")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "us-central1")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "google/gemini-2.5-flash")


def _vertex_client() -> OpenAI:
    """Gemini on the user's GCP quota via Vertex AI's OpenAI-compatible endpoint.

    Auth is ADC (gcloud login locally, or a Cloud Run service account in prod) —
    no API key. The AI Studio key path is intentionally gone: its free quota is 0.
    """
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    base = (f"https://{GCP_LOCATION}-aiplatform.googleapis.com/v1/"
            f"projects/{GCP_PROJECT}/locations/{GCP_LOCATION}/endpoints/openapi")
    return OpenAI(api_key=creds.token, base_url=base)


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
    if dry_run:
        # Fallback: straight-line deterministic flow, no LLM. Useful for CI and
        # when GCP credentials aren't available yet.
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

    # LLM path — Gemini via Vertex AI (OpenAI-compatible), ADC auth, no API key.
    client = _vertex_client()
    tools = [{"type": "function", "function": t} for t in TOOLS]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Repo to migrate: {repo_root}"},
    ]
    while True:
        resp = client.chat.completions.create(
            model=GEMINI_MODEL, messages=messages, tools=tools, temperature=0,
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            print(msg.content or "")
            return
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name,
                              "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            print(f"[call] {tc.function.name}({args})")
            result = _dispatch(tc.function.name, args)
            print(f"[result] {json.dumps(result)[:300]}")
            messages.append({
                "role": "tool", "tool_call_id": tc.id,
                "content": json.dumps(result),
            })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="path to a checked-out git repo")
    ap.add_argument("--dry-run", action="store_true",
                    help="skip Gemini; run the straight-line flow")
    args = ap.parse_args()
    run(args.repo, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
