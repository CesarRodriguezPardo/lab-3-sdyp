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
| `--fanout` | `int` | `2` | Cantidad de peers a contactar por ciclo de gossip (membresía). |
| `--timeout` | `float` | `6.0` | Umbral (en segundos) para declarar un nodo caído. |
| `--interactive` | `flag` | `False` | Habilita un loop de comandos por terminal para probar la capa Pub/Sub manualmente (ver sección 3). |

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

### 3. Probar la Capa Pub/Sub (Modo Interactivo)

Con `--interactive`, el nodo sigue haciendo gossip en segundo plano pero libera la terminal para comandos manuales de publicación/suscripción.

```bash
# Terminal 1
python3 -m CivicMesh.src.main --port 8000 --hostfile hostfile.txt --interactive
> SUBSCRIBE comuna:Maipu objective

# Terminal 2 (mismo --hostfile, para que se descubran)
python3 -m CivicMesh.src.main --port 8001 --hostfile hostfile.txt --interactive
> PUBLISH comuna:maipu objective {"value": 42}
```

Luego, en la Terminal 1, corre `INBOX` para confirmar que el mensaje llegó.

#### Comandos disponibles

| Comando | Sintaxis | Descripción |
| --- | --- | --- |
| `SUBSCRIBE` | `SUBSCRIBE <nivel>:<nombre> <canal>` | Suscribe este nodo a un tópico/canal (ej. `SUBSCRIBE comuna:Maipu objective`). Se anuncia a los peers conocidos, y a cualquier peer que se una después. |
| `PUBLISH` | `PUBLISH <topic_id> <canal> <payload_json>` | Publica un mensaje nuevo (ej. `PUBLISH comuna:maipu objective {"value": 42}`). El `payload_json` es opcional; si se omite, se envía `{}`. |
| `INBOX` | `INBOX` | Lista los mensajes entregados localmente a este nodo hasta ahora (los que coinciden con alguna suscripción propia). |
| `PEERS` | `PEERS` | Lista los peers conocidos actualmente vía gossip. |

Sal del modo interactivo con `Ctrl+D` o `Ctrl+C`; el nodo cierra su servidor y sus loops de gossip de forma limpia.

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
│   │   ├── message.py
│   │   ├── topic.py
│   │   ├── subscription.py
│   │   ├── channel.py
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

Para garantizar la interoperabilidad de la red distribuida, la comunicación se realiza mediante mensajes estructurados en formato JSON a través de TCP. El campo `intent` determina cómo se procesa cada payload en `Peer._handle_client()`.

**`GOSSIP_MEMBERSHIP` / `JOIN`** — intercambio de vista de membresía:

```json
{
  "intent": "GOSSIP_MEMBERSHIP",
  "members": [
    {
      "node_id": "127.0.0.1:8001",
      "node_host": "127.0.0.1",
      "node_port": 8001,
      "last_seen": 1700000000.00
    }
  ]
}
```

**`PUBLISH`** — mensaje de la capa Pub/Sub (ver sección "Diseño de la Capa Pub/Sub" más abajo):

```json
{
  "intent": "PUBLISH",
  "id": "72c9582d-3030-4219-85fd-3a39c0353e08",
  "topic": "comuna:maipu",
  "channel": "objective",
  "payload": {"value": 42},
  "timestamp": 1700000000.00,
  "ttl": 4,
  "priority": 3,
  "source": "127.0.0.1:8001"
}
```

**`SUSCRIBE`** — anuncio de una suscripción:

```json
{
  "intent": "SUSCRIBE",
  "source": "127.0.0.1:8000",
  "topic": "comuna:maipu",
  "channel": "objective"
}
```

#### Tipos de Intenciones (`intent`)

* **`JOIN` / `GOSSIP_MEMBERSHIP`:** Intercambio periódico de la vista de miembros de la red (Anti-Entropy).
* **`PUBLISH`:** Un mensaje Pub/Sub, originado o reenviado (ver flujo de publicación/recepción).
* **`SUSCRIBE`:** Un peer anuncia que está suscrito a un tópico/canal.

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
* **`membership_event(members)`**: Procesa la lista de miembros recibida en un payload, aplicando las reglas de fusión de estado y descarte de nodos obsoletos. Retorna la lista de IDs de peers recién descubiertos en esa llamada (usada por la capa Pub/Sub para re-anunciarles las suscripciones locales, ver más abajo).
* **`random_discovery()`**: Selecciona aleatoriamente una muestra de hasta `fanout` nodos conocidos para enviar el siguiente latido.
* **`export_membership()`**: Convierte la vista local `peers_view` en una lista formateada para el payload JSON.
* **`export_payload()`**: Envuelve la membresía exportada dentro del diccionario final estructurado con su correspondiente `intent`.
* **`purge_dead_peers()`**: Ejecuta el barrido periódico que detecta y remueve del diccionario local a los nodos inconexos.

---

## Diseño de la Capa Pub/Sub

### 1. Tópicos Geográficos (`GeographicTopic`)

Cada tópico combina un **nivel** (`comuna` o `region`) con un **nombre**, normalizado a un `id` en snake_case usado como clave de enrutamiento (ej. `GeographicTopic(TopicLevel.COMUNA, "Las Condes")` → `"comuna:las_condes"`). Esta normalización es la que usan `subscription.py` y `forwarding.py` para hacer *match* entre mensajes y suscripciones, así que `"Las Condes"` y `"las condes"` resuelven al mismo tópico.

> **Nota:** dos `GeographicTopic` con distinta capitalización (`"Santiago"` vs `"santiago"`) generan el mismo `id`, pero **no son el mismo objeto** (la igualdad del dataclass compara `name` tal cual, no el `id` ya normalizado). Ver `test_topics_with_different_case_produce_same_id_but_are_not_equal` en `test_topic.py`.

### 2. Canales: `objective` vs `subjective`

Cada mensaje pertenece a uno de dos canales, cada uno con su propia política (`ChannelPolicy`) de TTL/prioridad/fanout, cargada desde `config.yaml`:

```yaml
pubsub:
  channels:
    objective:
      ttl: 5
      priority: 3
      fanout: 3

    subjective:
      ttl: 3
      priority: 1
      fanout: 2
```

`objective` está pensado para datos verificables (ej. sensores) y se propaga más lejos y a más peers; `subjective` (ej. percepciones ciudadanas) tiene un alcance más conservador. Esto se resuelve enteramente vía configuración — `ChannelPolicy`/`ChannelPolicies` (`channel.py`) no tiene valores hardcodeados en Python.

### 3. Estructura del Mensaje (`Message`)

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `id` | `str` | Identificador único del mensaje (UUID), utilizado junto con `seen_messages` para detectar y evitar el procesamiento de mensajes duplicados en la malla. |
| `topic` | `str` | El `id` del `GeographicTopic` (ej. `"comuna:maipu"`). |
| `channel` | `str` | `"objective"` o `"subjective"`. |
| `payload` | `dict` | Datos arbitrarios del mensaje. |
| `ttl` | `int` | Saltos restantes permitidos; llega en 0 cuando el mensaje ya no debe reenviarse. |
| `hop_count` | `int` | Saltos ya realizados (aumenta cada vez que `ttl` decrece). |
| `priority` | `int` | Escala el fanout efectivo (ver política de fanout). |
| `source` | `str` | `node_id` del peer del que llegó este mensaje (para no reenviárselo de vuelta). |

### 4. Política de Fanout

`select_fanout_peers()` (`forwarding.py`) decide a quién reenviar un mensaje:

1. Prioriza peers **suscritos** al tópico/canal exacto; si faltan destinatarios para completar el fanout, rellena con otros peers conocidos.
2. Nunca se envía al propio nodo, ni de vuelta al `source` inmediato.
3. El fanout base del canal se **escala por prioridad**: `fanout_efectivo = fanout_base × min(priority, 3)` — así, un mensaje `priority=3` en el canal `objective` (`fanout=3`) llega hasta a 9 peers, mientras uno `priority=1` llega solo a 3. El multiplicador está acotado (`DEFAULT_MAX_PRIORITY_MULTIPLIER = 3`) para que una prioridad mal configurada no degenere en flooding.

### 5. Flujo de Publicación y Recepción

* **`Peer.publish(topic, channel, payload, ...)`**: crea el `Message` (con TTL/prioridad por defecto del `ChannelPolicy` del canal, salvo que se pasen explícitos), lo entrega localmente si el propio peer está suscrito, calcula el fanout, y lo envía.
* **`Peer._handle_publish(payload)`**: al recibir un `PUBLISH` por red, deduplica primero (`seen_messages`), **entrega localmente si corresponde — independiente de si el mensaje puede seguir reenviándose** (un TTL agotado no impide que este sea el destino final del mensaje), y solo después decide si continúa el reenvío.

Este orden (dedup → entrega local → forwarding → marcar visto) es deliberado: entrega local y forwarding son decisiones independientes que combinan criterios distintos (suscripción vs. TTL/peers conocidos).

### 6. Integración con Gossip

Las suscripciones se anuncian con un mensaje `SUSCRIBE` dirigido — a diferencia del gossip de membresía, que es periódico y converge solo con el tiempo. Para que esto no rompa la garantía de convergencia eventual del resto del sistema, `Peer` re-anuncia automáticamente todas sus suscripciones locales a cualquier peer que **descubra por primera vez** vía gossip de membresía (`_announce_subscriptions_to()`, disparado desde `_handle_client()` cuando `Gossiper.membership_event()` reporta peers nuevos). Así, un peer que se suscribe cuando la malla tiene 2 nodos y luego ve unirse a un tercero, no necesita volver a llamar `subscribe()` manualmente — el tercero se pone al día solo.
