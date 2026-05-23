"""Detect what Python framework version a repo uses.

For v1 we only handle web3.py (v6 → v7 migration target). Returns a small
dict the agent can reason over; never raises — missing files just yield "".
"""
from __future__ import annotations
import re
from pathlib import Path


_WEB3_REQ_RE = re.compile(r"^\s*web3\s*([<>=!~]+)\s*([^\s,;]+)", re.M)
_WEB3_TOML_RE = re.compile(r'^\s*web3\s*=\s*["\']([^"\']+)["\']', re.M)
_WEB3_IMPORT_RE = re.compile(r'^\s*(?:from|import)\s+web3\b', re.M)


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def detect_web3_version(repo_root: str) -> dict:
    """Return {framework, declared_version, source_file, has_imports, suggested_codemod}."""
    root = Path(repo_root)

    req_files = list(root.glob("requirements*.txt")) + list(root.glob("**/requirements*.txt"))
    pyproject = root / "pyproject.toml"
    setup_py = root / "setup.py"

    declared = ""
    source = ""
    for rf in req_files:
        m = _WEB3_REQ_RE.search(_read(rf))
        if m:
            declared = f"{m.group(1)}{m.group(2)}"
            source = str(rf.relative_to(root))
            break
    if not declared and pyproject.exists():
        m = _WEB3_TOML_RE.search(_read(pyproject))
        if m:
            declared = m.group(1)
            source = "pyproject.toml"

    has_imports = False
    for py in root.rglob("*.py"):
        if "site-packages" in py.parts or ".venv" in py.parts:
            continue
        if _WEB3_IMPORT_RE.search(_read(py)):
            has_imports = True
            break

    suggested = ""
    if declared:
        # Crude: anything pinned <7 or ==6.x is a v6→v7 target.
        if re.search(r"^6\.", declared.lstrip("=<>~!")) or "<7" in declared:
            suggested = "web3py-v6-to-v7"

    return {
        "framework": "web3.py" if (declared or has_imports) else "",
        "declared_version": declared,
        "source_file": source,
        "has_imports": has_imports,
        "suggested_codemod": suggested,
    }


if __name__ == "__main__":
    import json, sys
    print(json.dumps(detect_web3_version(sys.argv[1] if len(sys.argv) > 1 else "."), indent=2))
