# CivicMesh

Red P2P distribuida basada en el protocolo Gossip para descubrimiento de membresía y difusión de eventos Pub/Sub.

## Requisitos e Instalación

### Requisitos Previos

* Python 3.10 o superior
* `pip` y `python3-venv`

### Configuración del Entorno

```bash

# Crear y activar entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

```

---

## Guía de Ejecución

### 1. Iniciar un Nodo Individual

Para ejecutar un nodo local en un puerto específico:

```bash
python3 -m CivicMesh.src.main --port 8000

```

### Parámetros Configurables

| Parámetro | Tipo | Defecto | Descripción |
| --- | --- | --- | --- |
| `--host` | `str` | `127.0.0.1` | Dirección IP donde escuchará el nodo. |
| `--port` | `int` | *Requerido* | Puerto TCP local para el servidor del nodo. |
| `--hostfile` | `str` | `hostfile.txt` | Ruta al archivo con nodos semilla conocidos. |
| `--fanout` | `int` | `2` | Cantidad de peers a contactar por ciclo de gossip. |
| `--timeout` | `float` | `6.0` | Umbral (en segundos) para declarar un nodo caído. |

### 2. Prueba Malla Local (Múltiples Nodos)

Para probar el descubrimiento dinámico y la tolerancia a fallos en una máquina local, abre 3 terminales distintas:

```bash
# Terminal 1 (Nodo Semilla inicial)
python3 -m CivicMesh.src.main --port 8000

# Terminal 2 (Nodo Secundario)
python3 -m CivicMesh.src.main --port 8001

# Terminal 3 (Nodo Secundario)
python3 -m CivicMesh.src.main --port 8002

```

---

## Pruebas Unitarias

La suite de pruebas evalúa el mantenimiento de la vista parcial, la correcta fusión de estados y la detección de nodos caídos por timeout.

```bash
# Ejecutar todas las pruebas unitarias
python3 -m pytest

# Ejecutar con salida detallada
pytest -v

```

> **Nota:** Si ejecutas `pytest` directamente y encuentras errores de importación de módulos, asegúrate de tener un archivo `conftest.py` en la raíz del repositorio o ejecuta con `python3 -m pytest`.

---

## 📁 Estructura del Proyecto

```text
civicmesh/
│
├── README.md
├── CHANGELOG.md
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .gitignore
├── conftest.py
│
├── src/
│   ├── __init__.py
│   ├── main.py
│   │
│   ├── network/
│   │   ├── peer.py
│   │   └── gossip.py
│   │
│   ├── pubsub/
│   │   ├── __init__.py
│   │   ├── message.py
│   │   ├── topic.py
│   │   ├── subscription.py
│   │   ├── router.py
│   │   └── forwarding.py
│   │
│   ├── domains/
│   │   ├── crimes/
│   │   │   ├── __init__.py
│   │   │   ├── generator.py
│   │   │   └── perception.py
│   │   │
│   │   └── air_quality/
│   │       ├── __init__.py
│   │       ├── replay.py
│   │       ├── perception.py
│   │       └── dataset.py
│   │
│   ├── aggregation/
│   │   ├── __init__.py
│   │   ├── state.py
│   │   └── metrics.py
│   │
│   └── config/
│           ├── __init__.py
│           └── loader.py
│
├── tests/
│   ├── unit/
│   │   ├── test_message.py
│   │   ├── test_forwarding.py
│   │   ├── test_gossip.py
│   │   ├── test_membership.py
│   │   ├── test_crimes.py
│   │   ├── test_air_quality.py
│   │   └── test_perception.py
│   │
│   └── integration/
│       ├── test_pubsub_network.py
│       └── test_peer_failure.py
│
├── config/
│   ├── config.yaml
│   ├── crimes.yaml
│   └── air_quality.yaml
│
├── data/
│   └── air_quality/
│       └── README.md
│
└── scripts/
|   ├── run_local.sh
|   └── run_compose.sh
│   ├── slurm/
│   │   ├── run_civicmesh.sbatch
│   │   ├── start_peers.sh
│   │   └── start_publishers.sh
│   │
│   ├── data/
│   │   └── download_air_quality.py
│   │
│   └── agents/
│       ├── documenter/
│       ├── bug_reviewer/
│       └── mr_reviewer/
|
├── .github/
│   └── workflows/
│       └── ci.yml
│
└── runs/
    └── .gitkeep

```

---

## Diseño del Protocolo Gossip y Membresía

### 1. Protocolo de Comunicación (Payload JSON)

Para garantizar la interoperabilidad de la red distribuida, la comunicación se realiza mediante mensajes estructurados en formato JSON a través de TCP:

```json
{
  "intent": "GOSSIP_MEMBERSHIP",
  "sender_id": "127.0.0.1:8000",
  "sender_host": "127.0.0.1",
  "sender_port": 8000,
  "ttl": 3,
  "payload": {
    "members": [
      {
        "node_id": "127.0.0.1:8001",
        "node_host": "127.0.0.1",
        "node_port": 8001,
        "last_seen": 1700000000.00
      }
    ]
  }
}

```

#### Tipos de Intenciones (`intent`)

* **`JOIN` / `GOSSIP_MEMBERSHIP`:** Intercambio periódico de la vista de miembros de la red (Anti-Entropy).
* **`PUBLISH` / `SUBSCRIBE`:** Mensajes dirigidos a la capa Pub/Sub orientada a tópicos.

---

### 2. Gestión de Estado Local (`peers_view`)

El estado de la red se almacena en memoria dentro del diccionario `peers_view`. Utilizar el `node_id` (`host:port`) como clave garantiza búsquedas, actualizaciones y eliminaciones con complejidad constante $O(1)$, previniendo registros duplicados.

#### Reglas de Actualización y Descarte

1. **Auto-exclusión:** Los mensajes que contengan el propio `node_id` son ignorados.
2. **Filtrado de Zombis:** Si la marca de tiempo `last_seen` entrante supera el umbral de `timeout`, el registro se descarta de inmediato para evitar reincorporaciones falsas.
3. **Inserción y Actualización:** Si el nodo es nuevo, se inserta en el diccionario; si ya existe, su `last_seen` solo se actualiza si el valor entrante es estrictamente más reciente.
4. **Purga de Fallos:** Un barrido periódico elimina del diccionario cualquier nodo cuya inactividad cumpla:
`ahora - last_seen > timeout`

---

### 3. Especificación de la Clase `Gossiper`

#### Atributos

| Atributo | Tipo | Descripción |
| --- | --- | --- |
| `node_id` | `str` | Identificador único del nodo (formato `host:port`). |
| `node_host` | `str` | Dirección IP donde escucha el nodo. |
| `node_port` | `int` | Puerto TCP configurado para el servidor local. |
| `fanout` | `int` | Cantidad de nodos seleccionados al azar en cada ciclo de gossip. |
| `timeout` | `float` | Tiempo límite (en segundos) antes de declarar un nodo como caído. |
| `peers_view` | `dict` | Almacén en memoria de los miembros conocidos de la red. |

#### Métodos

* **`bootstrap_from_file(filepath)`**: Registra la dirección del nodo en `hostfile.txt` (si no estaba presente) y selecciona hasta 2 nodos semilla para iniciar el descubrimiento.
* **`membership_event(members)`**: Procesa la lista de miembros recibida en un payload, aplicando las reglas de fusión de estado y descarte de nodos obsoletos.
* **`random_discovery()`**: Selecciona aleatoriamente una muestra de hasta `fanout` nodos conocidos para enviar el siguiente latido.
* **`export_membership()`**: Convierte la vista local `peers_view` en una lista formateada para el payload JSON.
* **`export_payload()`**: Envuelve la membresía exportada dentro del diccionario final estructurado con su correspondiente `intent`.
* **`purge_dead_peers()`**: Ejecuta el barrido periódico que detecta y remueve del diccionario local a los nodos inconexos.
