"""Documenter agent for CivicMesh Lab 3.

Frequency: weekly (Mondays 09:00 UTC) and on every merge to main.
Reviews README.md and CHANGELOG.md. Mechanical findings open PRs
with fix (agent:auto-fix). Human findings create issues.
"""

import os
import re
from common import (
    create_branch, create_github_issue, create_or_update_file,
    create_pull_request, gemini_enabled, get_file_content,
    get_gemini_response, get_main_sha, open_issue_exists,
    rate_limit_ok, repo_full_name, require_gemini, slugify,
)

TITLE_PREFIX = "[agent:docs]"
ISSUE_LABELS = ["agent", "documentation"]
PR_LABELS = ["agent", "agent:auto-fix", "documentation"]
REPO_ROOT = os.environ.get("GITHUB_WORKSPACE", os.getcwd())


def read_file(path: str) -> str | None:
    full = os.path.join(REPO_ROOT, path)
    if not os.path.exists(full):
        return None
    with open(full, encoding="utf-8") as fh:
        return fh.read()


def _repo_url() -> str:
    name = repo_full_name()
    return f"https://github.com/{name}"


def rule_based_findings() -> list[dict]:
    findings: list[dict] = []
    readme = read_file("README.md")
    changelog = read_file("CHANGELOG.md")

    if readme is None:
        findings.append({
            "kind": "mechanical",
            "title": f"{TITLE_PREFIX} README.md no encontrado",
            "body": "No existe README.md. Crees uno con roles, instalacion y flujo Git.",
        })
    else:
        if re.search(r"\|\s*_\(nombre\)_\s*\|\s*1\s*—", readme) or "| _(nombre)_" in readme:
            fixed_readme = re.sub(
                r"\|\s*_\(nombre\)_\s*\|\s*1\s*—\s*Capa de Red / Gossip",
                "| **Nicolás García**     | 1 — Capa de Red / Gossip",
                readme,
            )
            fixed_readme = re.sub(
                r"\|\s*_\(nombre\)_\s*\|\s*2\s*—\s*Capa Pub/Sub",
                "| **Sofía Gacitúa**       | 2 — Capa Pub/Sub",
                fixed_readme,
            )
            fixed_readme = re.sub(
                r"\|\s*_\(nombre\)_\s*\|\s*3\s*—\s*Datos",
                "| **Martín Salinas**     | 3 — Datos",
                fixed_readme,
            )
            findings.append({
                "kind": "mechanical",
                "title": f"{TITLE_PREFIX} auto-fill team members in README.md",
                "body": "Actualización automática de los nombres de los integrantes del equipo en la tabla de roles del README.md.",
                "fix_path": "README.md",
                "fix_content": fixed_readme,
                "fix_commit_msg": "docs(readme): auto-fill team member names",
                "pr_title": "docs(readme): auto-fill team member names (auto-fix)",
            })

    if changelog is None:
        findings.append({
            "kind": "mechanical",
            "title": f"{TITLE_PREFIX} CHANGELOG.md no encontrado",
            "body": "No existe CHANGELOG. Crees uno con Keep a Changelog.",
        })
    else:
        if "1.0.0-lab3" not in changelog:
            findings.append({
                "kind": "mechanical",
                "title": f"{TITLE_PREFIX} CHANGELOG sin entrada para 1.0.0-lab3",
                "body": "Falta la seccion [1.0.0-lab3] en CHANGELOG.",
            })
        missing = [s for s in ("### Added", "### Changed", "### Fixed") if s not in changelog]
        if missing:
            findings.append({
                "kind": "mechanical",
                "title": f"{TITLE_PREFIX} CHANGELOG con secciones incompletas",
                "body": "Faltan: " + ", ".join(missing),
            })

    return findings


def gemini_findings(readme: str | None, changelog: str | None) -> list[dict]:
    if not gemini_enabled():
        return []
    prompt = f"""Eres revisor de documentacion para un laboratorio de sistemas distribuidos
(CivicMesh: P2P gossip + pub/sub geografico, Python, Docker Compose, Slurm, agentes de IA).

Analiza README.md y CHANGELOG.md y responde SOLO con una lista:
MECANICO: <titulo> | <fix en una linea>
HUMANO: <titulo> | <motivo>

Si no hay hallazgos: SIN HALLAZGOS.

=== README.md ===
{(readme or 'no existe')[:6000]}

=== CHANGELOG.md ===
{(changelog or 'no existe')[:3000]}
"""
    text = get_gemini_response(prompt)
    if not text or "SIN HALLAZGOS" in text:
        return []
    findings: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("MECANICO:"):
            parts = line[len("MECANICO:"):].split("|", 1)
            title, fix = parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""
            findings.append({
                "kind": "mechanical",
                "title": f"{TITLE_PREFIX} {title}",
                "body": f"Hallazgo Gemini. Fix: {fix}",
            })
        elif line.startswith("HUMANO:"):
            parts = line[len("HUMANO:"):].split("|", 1)
            title, reason = parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""
            findings.append({
                "kind": "human",
                "title": f"{TITLE_PREFIX} {title}",
                "body": f"Requiere intervencion humana: {reason}",
            })
    return findings


def _open_auto_fix_pr(finding: dict) -> bool:
    if not all(k in finding for k in ("fix_path", "fix_content", "pr_title")):
        return False
    sha = get_main_sha()
    if sha is None:
        return False
    slug = slugify(finding["title"].replace(TITLE_PREFIX, "").strip())
    branch = f"fix/docs/{slug}"[:250]
    current, file_sha = get_file_content(finding["fix_path"], ref="main")
    if current is not None and file_sha is None:
        return False
    if not create_branch(branch, sha):
        return False
    if not create_or_update_file(finding["fix_path"], finding["fix_content"], finding.get("fix_commit_msg", "docs: auto-fix"), branch, file_sha):
        return False
    return create_pull_request(branch, finding["pr_title"], finding["body"] + "\n\n---\n_Abierto por el agente documentador._", labels=PR_LABELS)


def main() -> int:
    print("== Documenter agent ==")
    require_gemini()
    if not rate_limit_ok(TITLE_PREFIX):
        return 0
    findings = rule_based_findings()
    readme = read_file("README.md")
    findings.extend(gemini_findings(readme, read_file("CHANGELOG.md")))
    if not findings:
        print("Documentacion al dia.")
        return 0
    created = 0
    for f in findings:
        if created >= 5:
            print("[documenter] Limite de 5 alcanzado.")
            break
        dedup_title = f.get("pr_title") or f["title"]
        if open_issue_exists(dedup_title):
            continue
        if f["kind"] == "mechanical" and "fix_path" in f and _open_auto_fix_pr(f):
            created += 1
            continue
        if create_github_issue(f["title"], f["body"] + "\n\n---\n_Creado por el agente documentador._", ISSUE_LABELS):
            created += 1
    print(f"[documenter] Hallazgos: {len(findings)}, creados: {created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
