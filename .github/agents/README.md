# Agentes de IA — CivicMesh

Tres agentes automatizan trabajo mecánico del repositorio.

| Agente | Herramienta | Frecuencia | Criterio mecánico | Criterio humano |
|---|---|---|---|---|
| **Documentador** | Python + Gemini 2.5 Flash | Semanal (lunes) + push a `main` | Typo, enlace vacío, sección faltante → PR con fix (`agent:auto-fix`) | Decisiones de diseño → "Requiere intervención humana" |
| **Revisor de bugs** | Python + Gemini 2.5 Flash | Diario (cron 03:00 UTC) | Socket sin timeout, random sin seed, except desnudo → issue con parche | Toca protocolo o semántica → issue |
| **Revisor de MRs** | Python + Gemini 2.5 Flash | Al terminar CI en un PR | Solo docs/tests/config, CI verde → "Mecánico y mergeable" | Cambios en lógica de protocolo → "Requiere revisión humana" |

**Guardrails:**
- Permisos mínimos: solo `issues: write` o `pull-requests: write`.
- Máximo 5 issues/PRs por agente por semana.
- Nunca fusionan sin aprobación humana.
- Gemini obligatorio en CI (`GEMINI_API_KEY` como GitHub Secret).
