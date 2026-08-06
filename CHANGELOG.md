# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0-lab3] - 2026-08-XX

### Added

- Protocolo de membresía gossip: vista parcial, intercambio periódico, detección de fallos por timeout.
- Capa pub/sub geográfico con `should_forward`, TTL y prioridad configurables por canal.
- Separación de canales objetivo y subjetivo con políticas distintas de fanout.
- Dominio A: generador estocástico de delitos simulados por comuna.
- Dominio B: replay determinista de series reales PM2.5/PM10 (SINCA/Open-Meteo).
- Generadores de percepción para ambos dominios con fórmulas de la Sección 4.3.
- Métricas de convergencia (objetivo) y divergencia (percepción vs realidad).
- Experimento de caída de peers / partición de red con evidencia en logs.
- Frontend mínimo de estadísticas alimentado desde shared FS.
- Pipeline CI con tests unitarios en cada PR (pytest).
- Dockerfile y docker-compose.yml (3+ peers + 1 publicador).
- Tres agentes de IA en CI: documentador, revisor de bugs, revisor de MRs.
- Scripts sbatch para despliegue multi-host en el clúster DIINF (2 CPU + 2 GPU).
- Protección de `main` con flujo `feature/*` y `fix/*`, PRs vinculados a issues.
- CHANGELOG.md en formato Keep a Changelog.

### Changed

- Separación de infraestructura (gossip + pub/sub) de los dominios de aplicación.
- Mediciones y métricas centralizadas en shared FS con convención `$CIVICMESH_RUNS`.

### Fixed

- _(pendiente según desarrollo)_
