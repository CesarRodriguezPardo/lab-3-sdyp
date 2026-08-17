import asyncio, json, time
from typing import Any, Dict
from CivicMesh.src.network.gossip import Gossiper
from CivicMesh.src.pubsub.message import Message
from CivicMesh.src.pubsub.subscription import (
    SubscriptionManager,
    VALID_CHANNELS,)
from CivicMesh.src.pubsub.forwarding import (
    should_forward,
    select_fanout_peers,
    mark_message_seen,
)


class Peer:
    def __init__(self, host: str, port: int, hostfile: str, fanout: int = 2, pubsub_fanout: int = 3, timeout: float = 3.0):
        """
        Inicializa un peer.
        fanout:
            Fanout utilizado exclusivamente por Gossip.

        pubsub_fanout:
            Fanout utilizado exclusivamente por Pub/Sub.
        """

        # -------------------------
        # Capa Gossip
        # -------------------------

        self.gossiper = Gossiper(
            host=host,
            port=port,
            fanout_in=fanout,
            timeout_in=timeout,
        )

        self.hostfile = hostfile

        # -------------------------
        # Capa Pub/Sub
        # -------------------------

        self.pubsub_fanout = pubsub_fanout

        self.subscription_manager = (
            SubscriptionManager()
        )

        # IDs de mensajes que este peer ya procesó.
        self.seen_messages = set()

    async def start(self):
        """Punto de entrada: inicializa el estado y lanza las tareas paralelas."""

        self.gossiper.bootstrap_from_file(self.hostfile)

        #Iniciar servidor
        server = await asyncio.start_server(self._handle_client, self.gossiper.node_host, self.gossiper.node_port)
        print(f"[{self.gossiper.node_id}] Escuchando en {self.gossiper.node_host}:{self.gossiper.node_port}")

        #Lanzar tareas en paralelo
        async with server:
            try:
                await asyncio.gather(
                    self._gossip_loop(),
                    self._failure_detector_loop(),
                    server.serve_forever()
                )
            except asyncio.CancelledError:
                # Captura la cancelación enviada por asyncio.run() al hacer Ctrl+C
                pass

    async def _handle_client(self, reader, writer):
        """Procesa los mensajes JSON entrantes"""

        try:
            data = await reader.read(4096)

            if not data:
                return

            payload = json.loads(
                data.decode()
            )

            intent = payload.get("intent")

            # -------------------------
            # Gossip
            # -------------------------

            if intent in (
                "GOSSIP_MEMBERSHIP",
                "JOIN",
            ):
                members = payload.get(
                    "members",
                    [],
                )

                self.gossiper.membership_event(
                    members
                )

            # -------------------------
            # Pub/Sub: publicación
            # -------------------------

            elif intent == "PUBLISH":

                await self._handle_publish(
                    payload
                )

            # -------------------------
            # Pub/Sub: suscripción
            # -------------------------

            elif intent == "SUSCRIBE":

                await self._handle_subscribe(
                    payload
                )

        except Exception as e:
            print(f"[{self.gossiper.node_id}] Error procesando paquete: {e}")

        finally:
            writer.close()
            await writer.wait_closed()

    # =========================================================
    # PUB/SUB - SUSCRIPCIONES
    # =========================================================

    async def _handle_subscribe(
        self,
        payload: Dict[str, Any],
    ) -> None:
        """
        Registra una suscripción remota recibida mediante
        el protocolo SUSCRIBE.

        Formato:

        {
            "intent": "SUSCRIBE",
            "source": "127.0.0.1:5001",
            "topic": "comuna:maipu",
            "channel": "objective"
        }
        """

        topic = payload.get("topic")
        channel = payload.get("channel")
        source = payload.get("source")

        # -------------------------
        # Validación
        # -------------------------

        if not topic:
            print(
                f"[{self.gossiper.node_id}] "
                "SUSCRIBE rechazado: "
                "falta topic"
            )
            return

        if channel not in VALID_CHANNELS:
            print(
                f"[{self.gossiper.node_id}] "
                "SUSCRIBE rechazado: "
                f"canal inválido: {channel}"
            )
            return

        if not source:
            print(
                f"[{self.gossiper.node_id}] "
                "SUSCRIBE rechazado: "
                "falta source"
            )
            return

        # -------------------------
        # Buscar peer
        # -------------------------

        peer_info = (
            self.gossiper.peers_view.get(
                source
            )
        )

        if peer_info is None:
            print(
                f"[{self.gossiper.node_id}] "
                f"SUSCRIBE recibido desde "
                f"peer desconocido: {source}"
            )
            return

        # -------------------------
        # Registrar suscripción
        # -------------------------

        subscriptions = peer_info.setdefault(
            "subscriptions",
            set(),
        )

        subscriptions.add(
            (
                topic,
                channel,
            )
        )

        print(
            f"[{self.gossiper.node_id}] "
            f"Peer {source} suscrito a "
            f"{topic}/{channel}"
        )

        # =========================================================
        # PUB/SUB - PUBLISH
        # =========================================================

    async def _handle_publish(
        self,
        payload: Dict[str, Any],
    ):
        """
        Procesa un mensaje Pub/Sub recibido.
        Aplica:
        should_forward()
            ↓
        mark_message_seen()
            ↓
        select_fanout_peers()
            ↓
        envío a los destinatarios
        """

        try:

            message_kwargs = {
                "topic": payload["topic"],
                "channel": payload["channel"],
                "payload": payload.get(
                    "payload",
                    {},
                ),
                "timestamp": payload.get(
                    "timestamp",
                    time.time(),
                ),
                "ttl": payload.get(
                    "ttl",
                    5,
                ),
                "priority": payload.get(
                    "priority",
                    1,
                ),
                "source": payload.get(
                    "source",
                    "",
                ),
                "hop_count": payload.get(
                    "hop_count",
                    0,
                ),
            }

            # Si existe ID, mantenerlo.
            # Si no existe, Message generará uno.
            if payload.get("id"):
                message_kwargs["id"] = payload["id"]

            msg = Message(
                **message_kwargs
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ) as e:

            print(
                f"[{self.gossiper.node_id}] "
                f"Mensaje Pub/Sub inválido: {e}"
            )

            return

        # Vista que utilizará forwarding.py.
        local_view = {
            "peers_view":
                self.gossiper.peers_view,

            "seen_messages":
                self.seen_messages,
        }

        # -------------------------------------------------
        # 1. Decidir si el mensaje puede continuar
        # -------------------------------------------------

        if not should_forward(
            msg,
            msg.topic,
            local_view,
        ):

            print(
                f"[{self.gossiper.node_id}] "
                f"Mensaje {msg.id} "
                f"no será reenviado."
            )

            return

        # -------------------------------------------------
        # 2. Marcar mensaje como procesado
        # -------------------------------------------------

        mark_message_seen(
            msg,
            local_view,
        )

        # -------------------------------------------------
        # 3. Seleccionar fanout
        # -------------------------------------------------

        selected_peers = (
            select_fanout_peers(
                msg=msg,
                local_peer_id=
                    self.gossiper.node_id,
                local_view=local_view,
                fanout=
                    self.pubsub_fanout,
            )
        )

        if not selected_peers:

            print(
                f"[{self.gossiper.node_id}] "
                f"Mensaje {msg.id}: "
                f"no hay peers candidatos."
            )

            return

        print(
            f"[{self.gossiper.node_id}] "
            f"Mensaje {msg.id}: "
            f"fanout={self.pubsub_fanout}, "
            f"destinos={selected_peers}"
        )

        # -------------------------------------------------
        # 4. Consumir un salto
        # -------------------------------------------------

        msg.decrement_ttl()

        # -------------------------------------------------
        # 5. Reenviar
        # -------------------------------------------------

        for peer_id in selected_peers:

            await self._send_pubsub_message(
                peer_id,
                msg,
            )

    async def _send_pubsub_message(
        self,
        peer_id: str,
        msg: Message,
    ):
        """
        Envía un mensaje Pub/Sub a un peer específico.
        """

        peer_info = (
            self.gossiper.peers_view.get(
                peer_id
            )
        )

        if not peer_info:
            return

        payload = {
            "intent": "PUBLISH",

            "id": msg.id,

            "topic": msg.topic,

            "channel": msg.channel,

            "payload": msg.payload,

            "timestamp": msg.timestamp,

            "ttl": msg.ttl,

            "priority": msg.priority,

            # Aquí source representa el peer
            # que realizó el envío anterior.
            "source":
                self.gossiper.node_id,

            "hop_count": msg.hop_count,
        }

        message_bytes = json.dumps(
            payload
        ).encode()

        try:

            reader, writer = (
                await asyncio.wait_for(
                    asyncio.open_connection(
                        peer_info["node_host"],
                        peer_info["node_port"],
                    ),
                    timeout=2.0,
                )
            )

            writer.write(
                message_bytes
            )

            await writer.drain()

            writer.close()

            await writer.wait_closed()

            # Peer respondió correctamente.
            if peer_id in self.gossiper.peers_view:

                self.gossiper.peers_view[
                    peer_id
                ]["last_seen"] = time.time()

        except Exception as e:

            print(
                f"[{self.gossiper.node_id}] "
                f"No se pudo enviar "
                f"mensaje {msg.id} "
                f"a {peer_id}: {e}"
            )

    # =========================================================
    # GOSSIP
    # =========================================================

    async def _gossip_loop(self):
        """ Bucle de emisión periodica del gossip """

        while True:
            await asyncio.sleep(1.0) #más frecuente que el timeout

            target_ids = self.gossiper.random_discovery()
            if not target_ids:
                continue

            payload = self.gossiper.export_payload()
            message_bytes = json.dumps(payload).encode()

            for pid in target_ids:
                peer_info = self.gossiper.peers_view.get(pid)
                if not peer_info:
                    continue

                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(peer_info["node_host"], peer_info["node_port"]),
                        timeout = 2.0
                    )
                    writer.write(message_bytes)
                    await writer.drain()
                    writer.close()
                    await writer.wait_closed()

                    # Si el socket respondio, el nodo está vivo
                    if pid in self.gossiper.peers_view:
                        self.gossiper.peers_view[pid]["last_seen"] = time.time()
                except Exception:
                    # La falla lo procesa el purge_dead_peers
                    pass

    # =========================================================
    # FAILURE DETECTOR
    # =========================================================

    async def _failure_detector_loop(self):
        """Bucle periódico de detección y purga de fallos"""

        while True:
            await asyncio.sleep(self.gossiper.timeout)
            dead_peers = self.gossiper.purge_dead_peers()
            if dead_peers:
                print(f"[{self.gossiper.node_id}] Nodos detectados como caídos: {dead_peers}")

    async def subscribe(
        self,
        topic,
        channel: str,
    ) -> None:
        """
        Registra una suscripción local y la anuncia
        a los peers conocidos.

        Parameters
        ----------
        topic:
            Instancia de GeographicTopic.

        channel:
            'objective' o 'subjective'.
        """

        # Registrar localmente.
        subscription = (
            self.subscription_manager.subscribe(
                topic,
                channel,
            )
        )

        print(
            f"[{self.gossiper.node_id}] "
            f"Suscrito a "
            f"{subscription.topic_id}/"
            f"{subscription.channel}"
        )

        # Anunciar la suscripción a los peers conocidos.
        await self._broadcast_subscription(
            subscription.topic_id,
            subscription.channel,
        )

    async def _broadcast_subscription(
        self,
        topic_id: str,
        channel: str,
    ) -> None:
        """
        Anuncia una suscripción local a los peers conocidos.
        """

        payload = {
            "intent": "SUSCRIBE",
            "source": self.gossiper.node_id,
            "topic": topic_id,
            "channel": channel,
        }

        message_bytes = json.dumps(
            payload
        ).encode()

        for peer_id, peer_info in (
            self.gossiper.peers_view.items()
        ):

            try:
                reader, writer = (
                    await asyncio.wait_for(
                        asyncio.open_connection(
                            peer_info["node_host"],
                            peer_info["node_port"],
                        ),
                        timeout=2.0,
                    )
                )

                writer.write(
                    message_bytes
                )

                await writer.drain()

                writer.close()

                await writer.wait_closed()

            except Exception as e:
                print(
                    f"[{self.gossiper.node_id}] "
                    f"No se pudo anunciar "
                    f"la suscripción a {peer_id}: "
                    f"{e}"
                )