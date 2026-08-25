"""Bug reviewer agent for CivicMesh Lab 3.

Frequency: daily (03:00 UTC). Scans Python code for common
distributed systems bugs: sockets without timeout, random
without seed, bare excepts, subprocess without timeout.
"""

import os
import re
from pathlib import Path
from common import (
    create_github_issue, gemini_enabled, get_gemini_response,
    open_issue_exists, rate_limit_ok, require_gemini,
)

TITLE_PREFIX = "[agent:bug]"
LABELS = ["agent", "bug"]
REPO_ROOT = Path(os.environ.get("GITHUB_WORKSPACE", os.getcwd()))


def iter_sources() -> list[Path]:
    src = REPO_ROOT
    exclusions = {".github", ".git", "venv", ".venv", "__pycache__", "runs", "data"}
    return [
        p for p in src.rglob("*.py")
        if p.is_file() and not any(x in p.parts for x in exclusions)
    ]


def check_socket_timeout(path: Path, lines: list[str]) -> list[dict]:
    """Socket connections without timeout."""
    findings = []
    for i, line in enumerate(lines):
        if re.search(r"socket\.(create_connection|connect)\(", line):
            window = "\n".join(lines[max(0, i - 2):i + 5])
            if "timeout" not in window and "settimeout" not in window:
                findings.append({
                    "kind": "mechanical",
                    "title": f"{TITLE_PREFIX} socket sin timeout -- {path.relative_to(REPO_ROOT)}",
                    "body": f"Linea {i+1}: `socket.connect()` sin timeout.\n\n"
                            f"```python\nsock.settimeout(5.0)\n```\n\n"
                            f"En sistemas distribuidos, un socket sin timeout puede "
                            f"bloquear indefinidamente ante caida de un peer.",
                })
    return findings


def check_random_seed(path: Path, content: str) -> list[dict]:
    """random usage without seed → non-deterministic behavior."""
    if "random." in content and "random.seed" not in content and "import random" in content:
        return [{
            "kind": "mechanical",
            "title": f"{TITLE_PREFIX} random sin seed -- {path.relative_to(REPO_ROOT)}",
            "body": f"Se usa `random` sin llamar a `random.seed()`. "
                    f"El enunciado exige seeds reproducibles. Agrega "
                    f"`random.seed(args.seed)` al inicio del modulo.",
        }]
    return []


def check_bare_except(path: Path, lines: list[str]) -> list[dict]:
    """Bare except clauses."""
    findings = []
    for i, line in enumerate(lines):
        if re.match(r"\s*except\s*:", line):
            findings.append({
                "kind": "mechanical",
                "title": f"{TITLE_PREFIX} except desnudo -- {path.relative_to(REPO_ROOT)}",
                "body": f"Linea {i+1}: `except:` sin tipo de excepcion. "
                        f"Usa `except Exception` o una excepcion especifica.",
            })
    return findings


def check_subprocess_timeout(path: Path, lines: list[str]) -> list[dict]:
    """Subprocess without timeout."""
    findings = []
    for i, line in enumerate(lines):
        if re.search(r"subprocess\.(run|call|Popen)\(", line) and "timeout" not in line:
            context = "\n".join(lines[i:i + 3])
            if "timeout" not in context:
                findings.append({
                    "kind": "mechanical",
                    "title": f"{TITLE_PREFIX} subprocess sin timeout -- {path.relative_to(REPO_ROOT)}",
                    "body": f"Linea {i+1}: `subprocess.run()` sin parametro `timeout`.",
                })
    return findings


def gemini_review(findings: list[dict]) -> list[dict]:
    if not gemini_enabled() or not findings:
        return findings
    sample = "\n".join(f"- {f['title']}" for f in findings[:10])
    prompt = f"""Eres revisor de codigo de sistemas distribuidos en Python.
Confirma: REAL o FALSO para cada hallazgo.

{sample}
"""
    text = get_gemini_response(prompt)
    if not text:
        return findings
    confirmed = []
    for f in findings:
        key = f["title"]
        discarded = any(
            line.startswith("FALSO:") and key.split("--")[0].strip() in line
            for line in text.splitlines()
        )
        if not discarded:
            confirmed.append(f)
    return confirmed


def main() -> int:
    print("== Bug reviewer agent ==")
    require_gemini()
    if not rate_limit_ok(TITLE_PREFIX):
        return 0
    findings: list[dict] = []
    for path in iter_sources():
        content = path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        findings.extend(check_socket_timeout(path, lines))
        findings.extend(check_random_seed(path, content))
        findings.extend(check_bare_except(path, lines))
        findings.extend(check_subprocess_timeout(path, lines))
    findings = gemini_review(findings)
    if not findings:
        print("Sin hallazgos.")
        return 0
    created = 0
    for f in findings:
        if created >= 5:
            break
        if open_issue_exists(f["title"]):
            continue
        body = f["body"] + "\n\n---\n_Creado por el agente revisor de bugs._"
        if create_github_issue(f["title"], body, LABELS):
            created += 1
    print(f"[bug-reviewer] Hallazgos: {len(findings)}, creados: {created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
