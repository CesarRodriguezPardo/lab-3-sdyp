"""MR reviewer agent for CivicMesh Lab 3.

Trigger: after CI completes (workflow_run). Classifies PRs
as mechanical (docs/tests/config) or human (protocol logic).
Never merges.
"""

import os
import re
import sys
from common import (
    comment_on_pr, gemini_enabled, get_gemini_response,
    get_pr, get_pr_files, load_event, require_gemini,
)

HUMAN_PREFIXES = ("src/", "civicmesh/", "gossip/", "pubsub/")
DOC_EXTENSIONS = (".md", ".txt", ".rst")
CONFIG_EXTENSIONS = (".yml", ".yaml", ".toml", ".cfg", ".ini")
ISSUE_REF = re.compile(r"(?:Closes|Fixes|Refs)\s+#\d+", re.IGNORECASE)


def resolve_pr_context() -> tuple[int | None, str | None, str]:
    event = load_event()
    event_name = os.environ.get("GITHUB_EVENT_NAME", "manual")
    if event_name == "workflow_run":
        run = event.get("workflow_run", {})
        prs = run.get("pull_requests", [])
        if not prs:
            return None, None, event_name
        return prs[0]["number"], run.get("conclusion"), event_name
    if event_name == "pull_request":
        pr = event.get("pull_request", {})
        return pr.get("number"), None, event_name
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        return int(sys.argv[1]), None, "manual"
    return None, None, event_name


def classify(files: list[dict]) -> tuple[str, list[str]]:
    human_reasons: list[str] = []
    for f in files:
        name = f["filename"]
        if name.endswith(DOC_EXTENSIONS):
            continue
        if name.endswith(CONFIG_EXTENSIONS) or "tests/" in name or name.startswith((".github/", "scripts/")):
            continue
        if name.endswith(".py"):
            continue
        human_reasons.append(f"archivo no clasificado: `{name}`")
    if not human_reasons:
        return "mechanical", ["solo documentacion, tests, config o .py estandar"]
    return "human", human_reasons


def gemini_second_opinion(files: list[dict], current: str) -> str:
    if not gemini_enabled():
        return current
    listing = "\n".join(f"- {f['filename']}" for f in files[:30])
    prompt = f"""Clasifica este PR como MECANICO o HUMANO.
MECANICO: solo docs/tests/config/.py sin cambios en protocolo.
HUMANO: cambios en logica de gossip, pub/sub, protocolo o semantica.
Responde solo: MECANICO o HUMANO.

{listing}
"""
    text = get_gemini_response(prompt)
    if text and "HUMANO" in text.upper():
        return "human"
    if text and "MECANICO" in text.upper():
        return "mechanical"
    return current


def main() -> int:
    print("== MR reviewer agent ==")
    require_gemini()
    pr_number, ci_conclusion, event_name = resolve_pr_context()
    if pr_number is None:
        return 0
    if not os.environ.get("GH_TOKEN"):
        print("[mr-reviewer] Dry-run mode.")
    pr = get_pr(pr_number) if os.environ.get("GH_TOKEN") else {}
    files = get_pr_files(pr_number) if os.environ.get("GH_TOKEN") else []
    kind_rules, reasons = classify(files)
    kind = gemini_second_opinion(files, kind_rules)
    gemini_note = ""
    if kind != kind_rules:
        gemini_note = f"\n- Gemini: reglas → `{kind_rules}`, Gemini → `{kind}`"
    ci_ok = ci_conclusion == "success"
    ci_line = "CI: :white_check_mark: verde" if ci_ok else f"CI: :x: fallando (`{ci_conclusion}`)" if ci_conclusion else "CI: no disponible"
    issue_ref = ISSUE_REF.search((pr.get("title") or "") + "\n" + (pr.get("body") or ""))
    issue_line = f"Issue vinculado: #{issue_ref.group(0).split('#')[1]}" if issue_ref else "Issue: :warning: no detectado"
    if not ci_ok and ci_conclusion is not None:
        verdict = "No apto para merge: CI fallando."
    elif not issue_ref:
        verdict = "Requiere revision humana: sin issue asociado."
    elif kind == "mechanical":
        verdict = "Mecanico y mergeable tras aprobacion humana."
    else:
        verdict = "Requiere revision humana."
    comment = f"""### :robot: Agente revisor de MR

Ejecutado **despues** del pipeline de CI (`{event_name}`).

- {ci_line}
- {issue_line}
- Clasificacion: **{verdict}**{gemini_note}

"""
    if reasons and kind == "human":
        comment += "Motivos:\n" + "\n".join(f"- {r}" for r in reasons) + "\n\n"
    comment += "---\n_Este agente nunca fusiona a `main`. El merge requiere aprobacion humana._"
    comment_on_pr(pr_number, comment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
