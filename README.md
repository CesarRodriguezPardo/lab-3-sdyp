# CivicMesh — Laboratorio 3

Framework P2P de Publish/Subscribe para monitoreo ciudadano distribuido basado en una capa de comunicación reutilizable (gossip + pub/sub geográfico por comuna/región) sobre dos dominios: Delitos (eventos discretos estocásticos) y Calidad del Aire (series reales continuas de PM2.5/PM10).

**Versión:** `v1.0.0-lab3`  
**Curso:** Sistemas Distribuidos — USACH 2026  
**Repositorio:** [https://github.com/CesarRodriguezPardo/lab-3-sdyp](https://github.com/CesarRodriguezPardo/lab-3-sdyp)

---

## 1. Equipo y Roles

| Nombre                | Rol                         | Responsabilidades                                                                                            |
| :-------------------- | :-------------------------- | :----------------------------------------------------------------------------------------------------------- |
| **Martin Salinas**            | 1 — Capa de Red / Gossip    | Membresía, descubrimiento, tolerancia a fallos, vista parcial.                                               |
| **Sofía Gacitúa**            | 2 — Capa Pub/Sub            | Tópicos geográficos, suscripciones, `should_forward`, fanout, canales objetivo/subjetivo.                    |
| **Nicolás García**            | 3 — Datos                   | Ingesta/cache SINCA/Open-Meteo, replay determinista, generadores Poisson y modelos de percepción.            |
| **Sebastián Cassone** | 4 — Analítica y Estadística | Métricas de convergencia y divergencia, experimentos de fallo/partición, frontend de estadísticas.           |
| **César Rodríguez**   | 5 — CI/CD, Git y Agentes    | Pipeline CI verde con tests, Dockerfile y docker-compose, scripts Slurm/Shared FS, 3 agentes de IA y README. |

---

## 2. Flujo de Trabajo Git

- `main` protegida: sin push directo, merge únicamente mediante Pull Request tras revisión humana y CI verde.
- Ramas de trabajo: `feature/<nombre>` y `fix/<nombre>`.
- Commits convencionales: `feat(scope):`, `fix(scope):`, `docs(scope):`, `test(scope):`, `ci(scope):`.
- Trazabilidad: todo PR debe vincular y cerrar un issue mediante `Closes #N` o `Fixes #N`.
- Guía detallada en [`.github/GIT_FLOW.md`](.github/GIT_FLOW.md).

---

## 3. Agentes de IA en CI/CD

Tres agentes automatizan tareas de mantenimiento, revisión de bugs y control de calidad en PRs utilizando **Gemini 2.5 Flash** (scripts en [`.github/agents/`](.github/agents/), workflows en [`.github/workflows/`](.github/workflows/)):

| Agente              | Herramienta               | Frecuencia / Trigger                      | Criterio mecánico (Auto-fix / Mergeable)                                                                                          | Criterio humano (Escalamiento a Issue)                                                                                       |
| :------------------ | :------------------------ | :---------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------- |
| **Documentador**    | Python + Gemini 2.5 Flash | Semanal (lunes 09:00 UTC) y push a `main` | Typos, enlaces vacíos o secciones faltantes en README/CHANGELOG → abre PR `fix/docs/*` (`agent:auto-fix`).                        | Decisiones arquitectónicas o documentación no estructurada → abre issue `[agent:docs] Requiere intervención humana`.         |
| **Revisor de bugs** | Python + Gemini 2.5 Flash | Diario (cron 03:00 UTC)                   | Sockets sin timeout, uso de `random` sin seed fija, `except:` desnudos, `subprocess` sin timeout → issue con parche.              | Modificaciones en semántica del protocolo o lógica de enrutamiento → issue categorizado para humano.                         |
| **Revisor de MRs**  | Python + Gemini 2.5 Flash | Post-CI (`workflow_run` completado)       | Solo docs, tests o config modificados con CI verde e issue vinculado → veredicto _"Mecánico y mergeable tras aprobación humana"_. | Cambios en código de protocolo (`src/network/`, `src/pubsub/`, etc.) o CI fallando → veredicto _"Requiere revisión humana"_. |

> **Gobernanza:** Los agentes nunca realizan merge automático a `main`. Tienen un límite de seguridad de máximo 5 issues automáticos por agente por semana.

---

## 4. Requisitos e Instalación Local

### Requisitos Previos

- Python 3.10 o superior
- `pip` y `python3-venv`

### Configuración del Entorno

```bash
# Crear y activar entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

### Ejecución de Nodos

#### 1. Iniciar un Nodo Individual

```bash
python3 -m CivicMesh.src.main --port 8000 --hostfile hostfile.txt
```

#### 2. Parámetros Configurables

| Parámetro       | Tipo    | Defecto        | Descripción                                                          |
| :-------------- | :------ | :------------- | :------------------------------------------------------------------- |
| `--host`        | `str`   | `127.0.0.1`    | Dirección IP donde escuchará el servidor del nodo.                   |
| `--port`        | `int`   | _Requerido_    | Puerto TCP local para el nodo.                                       |
| `--hostfile`    | `str`   | `hostfile.txt` | Ruta al archivo con direcciones de nodos semilla conocidos.          |
| `--fanout`      | `int`   | `2`            | Cantidad de peers a contactar por ciclo de gossip (membresía).       |
| `--timeout`     | `float` | `6.0`          | Tiempo límite en segundos para declarar un peer inactivo como caído. |
| `--interactive` | `flag`  | `False`        | Habilita consola interactiva para comandos Pub/Sub manuales.         |

#### 3. Probar la Capa Pub/Sub (Modo Interactivo)

En terminales separadas:

```bash
# Terminal 1 (Nodo A)
python3 -m CivicMesh.src.main --port 8000 --hostfile hostfile.txt --interactive
> SUBSCRIBE comuna:maipu objective

# Terminal 2 (Nodo B)
python3 -m CivicMesh.src.main --port 8001 --hostfile hostfile.txt --interactive
> PUBLISH comuna:maipu objective {"pm2_5": 38.5}
```

En la Terminal 1, ejecuta `INBOX` para verificar la recepción del mensaje propagado por la malla.

---

## 5. Docker Compose

Levanta un despliegue multi-peer con 3 peers y publicadores en una red puente interna aislada:

```bash
# Construir y levantar servicios
docker compose up --build

# Detener servicios
docker compose down
```

---

## 6. Despliegue en el Clúster DIINF (Slurm)

El despliegue en el clúster utiliza 2 hosts CPU (para peers de la malla gossip/pub-sub) y 2 hosts GPU (usando únicamente la CPU del host para publicadores y frontend), comunicándose vía red y coordinándose mediante el Shared Filesystem.

```bash
# Enviar trabajo Slurm
sbatch scripts/slurm/civicmesh.sbatch
```

### Convención de Shared FS

Todas las corridas generan sus artefactos bajo la convención `$CIVICMESH_RUNS/<run_id>/`:

```text
$CIVICMESH_RUNS/<run_id>/
├── hostfile.txt        # Direcciones host:port registradas por peers
├── config.yaml         # Configuración unificada de la corrida
├── metrics/            # Archivos JSONL con métricas de convergencia y percepción
└── logs/               # Salidas stdout/stderr de cada proceso
```

---

## 7. Frontend de Estadísticas

El frontend visualiza el estado por tópico y canal, la convergencia del canal objetivo y la brecha percepción–realidad del canal subjetivo leyendo directamente desde `$CIVICMESH_RUNS/<run_id>/metrics/`.

### Acceso a la UI

- **Local / Docker:** Abrir navegador en `http://localhost:8501`.
- **Clúster DIINF (vía Túnel SSH):**
  ```bash
  ssh -L 8501:<nodo_gpu_host>:8501 <usuario>@ssh.diinf.usach.cl
  ```
  Luego abrir en tu navegador local `http://localhost:8501`.

---

## 8. Suite de Tests

La suite incluye pruebas unitarias para todas las capas y pruebas de integración multi-nodo:

```bash
# Ejecutar suite de pruebas unitarias e integración
pytest -v

# Ejecución silenciosa para CI
pytest -q
```

---

## 9. Diseño Técnico de Protocolos

### Protocolo Gossip y Membresía (`Gossiper`)

- **Transporte y Formato:** Mensajes estructurados JSON sobre TCP con campos `intent`, `members` o `payload`.
- **Gestión de Estado (`peers_view`):** Tabla hash en memoria $O(1)$ indexada por `node_id` (`host:port`). Descarta zombis con marcas `last_seen` antiguas y purga periódicamente nodos inactivos (`ahora - last_seen > timeout`).
- **Descubrimiento y Anti-Entropy:** `bootstrap_from_file()` registra en `hostfile.txt` y contacta hasta 2 semillas; `random_discovery()` selecciona aleatoriamente `fanout` vecinos en cada ronda.

### Capa Pub/Sub Geográfica (`Peer` & `forwarding.py`)

- **Tópicos Geográficos (`GeographicTopic`):** Normalizados a identificadores snake_case (ej. `comuna:las_condes`, `region:metropolitana`).
- **Canales (`objective` vs `subjective`):**
  - Canal `objective`: Datos cuantitativos/sensores. Mayor TTL y prioridad para máxima cobertura.
  - Canal `subjective`: Percepción ciudadana y rumores. Menor TTL y prioridad para alcance acotado.
- **Enrutamiento y Fanout (`should_forward`):** Prioriza peers suscritos al tópico y escala el fanout efectivo según prioridad: $\text{fanout}_{\text{efectivo}} = \text{fanout}_{\text{base}} \times \min(\text{prioridad}, 3)$.
- **Deduplicación:** Registro `seen_messages` (UUID) para evitar bucles y reprocesamiento.

---

## 10. Estructura del Repositorio

```text
lab-3-sdyp/
├── README.md
├── CHANGELOG.md
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .gitignore
├── conftest.py
│
├── CivicMesh/
│   ├── config/
│   │   ├── config.yaml
│   │   ├── crimes.yaml
│   │   └── air_quality.yaml
│   ├── data/
│   │   └── air_quality/
│   │       ├── las_condes.csv
│   │       ├── pudahuel.csv
│   │       ├── puente_alto.csv
│   │       └── sinca_cache.jsonl
│   ├── src/
│   │   ├── main.py
│   │   ├── network/
│   │   │   ├── gossip.py
│   │   │   └── peer.py
│   │   ├── pubsub/
│   │   │   ├── channel.py
│   │   │   ├── forwarding.py
│   │   │   ├── message.py
│   │   │   ├── subscription.py
│   │   │   └── topic.py
│   │   ├── domains/
│   │   │   ├── crimes/
│   │   │   └── air_quality/
│   │   └── aggregation/
│   │       ├── state.py
│   │       └── metrics.py
│   └── tests/
│       ├── unit/
│       │   ├── test_gossip.py
│       │   ├── test_pubsub.py
│       │   ├── test_air_quality.py
│       │   └── test_perception.py
│       └── integration/
│           └── test_pubsub_network.py
│
├── scripts/
│   ├── slurm/
│   │   └── civicmesh.sbatch
│   └── data/
│
└── .github/
    ├── GIT_FLOW.md
    ├── workflows/
    │   ├── ci.yml
    │   ├── agent_documenter.yml
    │   ├── agent_bug_reviewer.yml
    │   └── agent_mr_reviewer.yml
    └── agents/
        ├── common.py
        ├── documenter.py
        ├── bug_reviewer.py
        └── mr_reviewer.py
```
