# CivicMesh — Laboratorio 3

Framework P2P de Publish/Subscribe para monitoreo ciudadano distribuido.

**Versión:** `v1.0.0-lab3`
**Curso:** Sistemas Distribuidos — USACH 2026
**Repositorio:** [https://github.com/CesarRodriguezPardo/lab-3-sdyp](https://github.com/CesarRodriguezPardo/lab-3-sdyp)

---

## 1. Equipo y Roles

| Nombre | Rol | Responsabilidades |
| :----- | :-- | :---------------- |
| _(nombre)_ | 1 — Capa de Red / Gossip | Membresía, descubrimiento, tolerancia a fallos. |
| _(nombre)_ | 2 — Capa Pub/Sub | Tópicos geográficos, suscripciones, `should_forward`, fanout. |
| _(nombre)_ | 3 — Datos | Ingesta/cache SINCA/Open-Meteo, generadores estocásticos. |
| _(nombre)_ | 4 — Analítica y Estadística | Métricas convergencia/divergencia, experimentos de fallo, frontend. |
| **César Rodríguez** | 5 — CI/CD, Git y Agentes | Pipeline CI, Docker Compose, agentes de IA, scripts Slurm, README. |

---

## 2. Flujo de trabajo Git

- `main` protegida: sin push directo, merge solo vía Pull Request.
- 1 revisión humana + CI verde requeridos.
- Ramas: `feature/<nombre>` y `fix/<nombre>`.
- Commits convencionales: `feat(scope):`, `fix(scope):`, `docs(scope):`.
- Todo PR debe cerrar un issue: `Closes #N`.
- Documentación completa en [`.github/GIT_FLOW.md`](.github/GIT_FLOW.md).

---

## 3. Agentes de IA

Tres agentes automatizan documentación, revisión de bugs y revisión de PRs.
Scripts en [`.github/agents/`](.github/agents/), workflows en [`.github/workflows/`](.github/workflows/).

| Agente | Herramienta | Frecuencia | Criterio mecánico | Criterio humano |
|---|---|---|---|---|
| Documentador | Python + Gemini 2.5 Flash | Semanal (lunes) + push a `main` | Typo, enlace vacío, sección faltante → PR con fix (`agent:auto-fix`) | Decisiones de diseño → issue "Requiere intervención humana" |
| Revisor de bugs | Python + Gemini 2.5 Flash | Diario (cron 03:00 UTC) | Error común de Python (socket sin timeout, random sin seed) → issue con parche | Toca protocolo o semántica → issue |
| Revisor de MRs | Python + Gemini 2.5 Flash | Al terminar CI en un PR (`workflow_run`) | Solo docs/tests/config, CI verde, issue vinculado → "Mecánico y mergeable" | Cambios en lógica de protocolo → "Requiere revisión humana" |

- Motor: **Gemini 2.5 Flash** (API key en GitHub Secrets).
- Máximo 5 issues automáticos por agente por semana.
- **Nunca** fusionan a `main` sin aprobación humana.

---

## 4. Instalación y uso

### Local

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pytest -q
```

### Docker Compose

```bash
docker compose up --build
```

Levanta 3 peers + 1 publicador. Red interna entre servicios.

---

## 5. Despliegue en el clúster DIINF (Slurm)

```bash
sbatch scripts/slurm/civicmesh.sbatch
```

Convención de shared FS: `$CIVICMESH_RUNS/<id>/metrics/`

---

## 6. Frontend de estadísticas

_(documentar aquí cómo abrir la UI: URL, puerto, tunnel SSH si aplica)_

---

## 7. Tests

```bash
pytest -q                      # unitarios
docker compose -f docker-compose.test.yml up --abort-on-container-exit  # integración
```
