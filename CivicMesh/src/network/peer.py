import asyncio, json, time
from typing import Any, Callable, Dict, List, Optional, Union
from CivicMesh.src.network.gossip import Gossiper
from CivicMesh.src.pubsub.message import Message
from CivicMesh.src.pubsub.topic import GeographicTopic
from CivicMesh.src.pubsub.subscription import (
    SubscriptionManager,
    VALID_CHANNELS,)
from CivicMesh.src.pubsub.forwarding import (
    should_forward,
    select_fanout_peers,
    mark_message_seen,
)
from CivicMesh.src.pubsub.channel import (
    ChannelPolicies,
    default_channel_policies,
)


class Peer:
    def __init__(
        self,
        host: str,
        port: int,
        hostfile: str,
        fanout: int = 2,
        pubsub_fanout: int = 3,
        timeout: float = 3.0,
        channel_policies: Optional[ChannelPolicies] = None,
        on_local_delivery: Optional[Callable[[Message], None]] = None,
    ):
        """
        Inicializa un peer.
        fanout:
            Fanout utilizado exclusivamente por Gossip.

        pubsub_fanout:
            Fanout de respaldo utilizado por Pub/Sub cuando no hay
            una ChannelPolicy aplicable (compatibilidad).

        channel_policies:
            Políticas (ttl/priority/fanout) por canal, cargadas desde
            config.yaml por defecto. Permite inyectar políticas
            personalizadas (por ejemplo, en tests).

        on_local_delivery:
            Callback opcional invocado cada vez que un mensaje se
            entrega localmente (ver _deliver_locally). Permite que
            otra capa (p. ej. Agregación, Rol 4) reaccione a
            mensajes sin acoplar Pub/Sub a su implementación.
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

        # Políticas ttl/priority/fanout por canal (objective/subjective).
        self.channel_policies = (
            channel_policies
            if channel_policies is not None
            else default_channel_policies()
        )

        # -------------------------
        # Entrega local (Task 8)
        # -------------------------

        # Buzón local: mensajes entregados a este peer porque
        # coinciden con alguna de sus propias suscripciones.
        # Sirve como punto de inspección simple (tests, debug)
        # sin necesidad de registrar un callback.
        self.local_inbox: List[Message] = []

        # Callback opcional para que otra capa (p. ej. Agregación)
        # reaccione a cada entrega local sin que Pub/Sub dependa
        # de su implementación concreta.
        self.on_local_delivery = on_local_delivery

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

                new_peer_ids = self.gossiper.membership_event(
                    members
                )

                # Ponemos al día a cualquier peer recién
                # descubierto con nuestras suscripciones
                # locales (ver _announce_subscriptions_to).
                if new_peer_ids:
                    await self._announce_subscriptions_to(
                        new_peer_ids
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
        # PUB/SUB - ENTREGA LOCAL (Task 8)
        # =========================================================

    def _deliver_locally(self, msg: Message) -> bool:
        """
        Entrega un mensaje a este peer si está suscrito al
        tópico y canal del mensaje.

        Importante: la entrega local es INDEPENDIENTE del
        forwarding. should_forward() combina criterios que
        aplican solo al reenvío (TTL restante, si existen peers
        conocidos a los que reenviar). Ninguno de esos criterios
        es relevante para decidir si ESTE peer, como suscriptor,
        debe recibir el mensaje: un mensaje con TTL = 0 puede
        perfectamente haber llegado a su destino final.

        Parameters
        ----------
        msg:
            Mensaje ya validado (topic/channel consistentes).

        Returns
        -------
        bool
            True si el peer estaba suscrito y el mensaje fue
            entregado. False si no había suscripción coincidente.
        """

        subscriptions = (
            self.subscription_manager.serialized_subscriptions()
        )

        if (msg.topic, msg.channel) not in subscriptions:
            return False

        self.local_inbox.append(msg)

        print(
            f"[{self.gossiper.node_id}] "
            f"Entrega local: {msg.id} "
            f"({msg.topic}/{msg.channel})"
        )

        if self.on_local_delivery is not None:
            self.on_local_delivery(msg)

        return True

        # =========================================================
        # PUB/SUB - PUBLISH
        # =========================================================

    async def publish(
        self,
        topic: Union[GeographicTopic, str],
        channel: str,
        payload: Dict[str, Any],
        priority: Optional[int] = None,
        ttl: Optional[int] = None,
    ) -> Message:
        """
        Origina una publicación Pub/Sub desde este peer y la propaga
        a la red mediante gossip.

        Este método es el punto de entrada para roles externos
        (p. ej. el rol de datos) que quieran inyectar un nuevo
        mensaje en CivicMesh.

        Parameters
        ----------
        topic:
            GeographicTopic o su topic_id ya serializado
            (ej. "comuna:maipu").

        channel:
            'objective' o 'subjective'.

        payload:
            Contenido del mensaje (dict serializable a JSON).

        priority:
            Prioridad opcional. Si no se entrega, se usa la
            prioridad por defecto definida en la ChannelPolicy
            del canal (config.yaml).

        ttl:
            TTL opcional. Si no se entrega, se usa el TTL por
            defecto definido en la ChannelPolicy del canal.

        Returns
        -------
        Message
            Si se encontraron peers candidatos, el mensaje se
            reenvía y se retorna con TTL/hop_count ya actualizados
            en un salto (el correspondiente a ese primer envío).

            Si no hay peers candidatos todavía (ej. malla recién
            iniciada), el mensaje se retorna sin modificar: no
            hubo ningún salto real, por lo que TTL y hop_count
            deben reflejar eso.
        """

        if channel not in VALID_CHANNELS:
            raise ValueError(
                f"Canal inválido: {channel}. "
                f"Debe ser uno de {VALID_CHANNELS}."
            )

        topic_id = (
            topic.id
            if isinstance(topic, GeographicTopic)
            else topic
        )

        channel_policy = self.channel_policies.get(channel)

        msg = Message(
            topic=topic_id,
            channel=channel,
            payload=payload,
            timestamp=time.time(),
            ttl=ttl if ttl is not None else channel_policy.ttl,
            priority=(
                priority
                if priority is not None
                else channel_policy.priority
            ),
            # Mensaje propio: no tiene un hop previo del cual venir.
            source="",
        )

        # Entrega local: si este mismo peer está suscrito al
        # tópico/canal que está publicando, también debe recibir
        # su propio mensaje (caso poco común pero válido).
        self._deliver_locally(msg)

        # Vista que utilizará forwarding.py.
        local_view = {
            "peers_view": self.gossiper.peers_view,
            "seen_messages": self.seen_messages,
        }

        # -------------------------------------------------
        # 1. Seleccionar fanout ANTES de marcar el mensaje
        #    como visto. select_fanout_peers() vuelve a
        #    invocar should_forward() internamente, y este
        #    descarta cualquier mensaje que ya figure en
        #    seen_messages. Si marcáramos el mensaje como
        #    visto antes de este paso, jamás se seleccionaría
        #    ningún peer (ver nota al final del archivo).
        # -------------------------------------------------

        selected_peers = select_fanout_peers(
            msg=msg,
            local_peer_id=self.gossiper.node_id,
            local_view=local_view,
            fanout=self.pubsub_fanout,
            channel_policies=self.channel_policies,
        )

        # -------------------------------------------------
        # 2. Marcar el mensaje como procesado por este peer,
        #    para que si vuelve a llegar por otra ruta
        #    (loop de la malla) no se reenvíe de nuevo.
        # -------------------------------------------------

        mark_message_seen(
            msg,
            local_view,
        )

        if not selected_peers:
            print(
                f"[{self.gossiper.node_id}] "
                f"Publish {msg.id} ({topic_id}/{channel}): "
                f"no hay peers candidatos todavía."
            )
            return msg

        print(
            f"[{self.gossiper.node_id}] "
            f"Publish {msg.id} ({topic_id}/{channel}): "
            f"destinos={selected_peers}"
        )

        # -------------------------------------------------
        # 3. Consumir un salto antes de enviar.
        # -------------------------------------------------

        msg.decrement_ttl()

        # -------------------------------------------------
        # 4. Enviar a los peers seleccionados.
        # -------------------------------------------------

        for peer_id in selected_peers:
            await self._send_pubsub_message(
                peer_id,
                msg,
            )

        return msg

    async def _handle_publish(
        self,
        payload: Dict[str, Any],
    ):
        """
        Procesa un mensaje Pub/Sub recibido.
        Aplica:
        deduplicación (seen_messages)
            ↓
        entrega local (Task 8, independiente del forwarding)
            ↓
        should_forward()
            ↓
        select_fanout_peers()
            ↓
        mark_message_seen()
            ↓
        envío a los destinatarios
        """

        try:

            incoming_channel = payload["channel"]

            # Si faltan ttl/priority en el payload, se usan los
            # valores por defecto de la ChannelPolicy del canal
            # (en vez de una constante arbitraria) para respetar
            # la Task 6 también en mensajes entrantes.
            try:
                channel_defaults = self.channel_policies.get(
                    incoming_channel
                )
                default_ttl = channel_defaults.ttl
                default_priority = channel_defaults.priority
            except ValueError:
                default_ttl = 5
                default_priority = 1

            message_kwargs = {
                "topic": payload["topic"],
                "channel": incoming_channel,
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
                    default_ttl,
                ),
                "priority": payload.get(
                    "priority",
                    default_priority,
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
        # 1. Deduplicación explícita: si este mensaje ya fue
        #    procesado por este peer (llegó antes por otra
        #    ruta de la malla), se ignora por completo — ni
        #    entrega local duplicada, ni reenvío duplicado.
        # -------------------------------------------------

        if msg.id in self.seen_messages:

            print(
                f"[{self.gossiper.node_id}] "
                f"Mensaje {msg.id} "
                f"ya fue procesado, se ignora."
            )

            return

        # -------------------------------------------------
        # 2. Entrega local (Task 8).
        #
        #    Se hace ANTES y de forma independiente de
        #    should_forward(): la entrega local depende
        #    únicamente de si este peer está suscrito al
        #    tópico/canal, no de si el mensaje todavía puede
        #    seguir reenviándose (TTL) ni de si existen
        #    peers conocidos a los que reenviarlo. Un mensaje
        #    con TTL agotado puede perfectamente haber
        #    llegado a su destino final.
        # -------------------------------------------------

        self._deliver_locally(msg)

        # -------------------------------------------------
        # 3. Decidir si el mensaje puede continuar
        #    reenviándose a otros peers.
        # -------------------------------------------------

        if not should_forward(
            msg,
            msg.topic,
            local_view,
            channel_policies=self.channel_policies,
        ):

            print(
                f"[{self.gossiper.node_id}] "
                f"Mensaje {msg.id} "
                f"no será reenviado."
            )

            # Aunque no se reenvíe, ya fue procesado
            # (y potencialmente entregado localmente):
            # se marca como visto para no repetir este
            # trabajo si vuelve a llegar por otra ruta.
            mark_message_seen(
                msg,
                local_view,
            )

            return

        # -------------------------------------------------
        # 4. Seleccionar fanout ANTES de marcar el mensaje
        #    como visto.
        #
        #    select_fanout_peers() invoca internamente a
        #    should_forward(), que descarta cualquier
        #    mensaje presente en seen_messages. Si
        #    marcáramos el mensaje como visto antes de
        #    este paso (como ocurría antes de este fix),
        #    select_fanout_peers() siempre habría devuelto
        #    una lista vacía y el mensaje jamás se
        #    reenviaba a nadie.
        # -------------------------------------------------

        selected_peers = (
            select_fanout_peers(
                msg=msg,
                local_peer_id=
                    self.gossiper.node_id,
                local_view=local_view,
                fanout=
                    self.pubsub_fanout,
                channel_policies=self.channel_policies,
            )
        )

        # -------------------------------------------------
        # 5. Marcar mensaje como procesado, ya con el
        #    resultado del fanout calculado.
        # -------------------------------------------------

        mark_message_seen(
            msg,
            local_view,
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
            f"Mensaje {msg.id} ({msg.channel}): "
            f"destinos={selected_peers}"
        )

        # -------------------------------------------------
        # 6. Consumir un salto
        # -------------------------------------------------

        msg.decrement_ttl()

        # -------------------------------------------------
        # 7. Reenviar
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

    async def _send_subscribe_message(
        self,
        peer_id: str,
        topic_id: str,
        channel: str,
    ) -> None:
        """
        Envía un único mensaje SUSCRIBE a un peer específico.

        Helper de bajo nivel: no decide A QUIÉN anunciar (eso lo
        deciden _broadcast_subscription, para todos los peers
        conocidos, y _announce_subscriptions_to, para peers
        recién descubiertos).
        """

        peer_info = self.gossiper.peers_view.get(peer_id)

        if not peer_info:
            return

        payload = {
            "intent": "SUSCRIBE",
            "source": self.gossiper.node_id,
            "topic": topic_id,
            "channel": channel,
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

        except Exception as e:
            print(
                f"[{self.gossiper.node_id}] "
                f"No se pudo anunciar "
                f"la suscripción {topic_id}/{channel} "
                f"a {peer_id}: {e}"
            )

    async def _broadcast_subscription(
        self,
        topic_id: str,
        channel: str,
    ) -> None:
        """
        Anuncia una suscripción local a TODOS los peers conocidos
        actualmente.

        Se invoca una sola vez, en el momento de subscribe().
        Por sí sola NO garantiza convergencia eventual: un peer
        que se une a la malla después de esta llamada nunca
        recibiría este anuncio. Ese caso lo cubre
        _announce_subscriptions_to(), invocado cuando gossip
        descubre un nuevo miembro (ver _handle_client).
        """

        for peer_id in list(
            self.gossiper.peers_view.keys()
        ):
            await self._send_subscribe_message(
                peer_id,
                topic_id,
                channel,
            )

    async def _announce_subscriptions_to(
        self,
        peer_ids: List[str],
    ) -> None:
        """
        Re-anuncia TODAS las suscripciones locales a un conjunto
        específico de peers — normalmente, peers recién
        descubiertos vía gossip de membresía.

        Cierra el hueco de convergencia eventual de
        _broadcast_subscription(): sin este paso, un peer que se
        une a la malla después de que otro ya se suscribió jamás
        se enteraría de esa suscripción, porque nada la vuelve a
        emitir. Con esto, cada vez que aparece un peer nuevo, se
        le ponen al día todas las suscripciones que este peer ya
        tiene registradas localmente.
        """

        if not peer_ids:
            return

        subscriptions = (
            self.subscription_manager.serialized_subscriptions()
        )

        if not subscriptions:
            return

        for peer_id in peer_ids:
            for topic_id, channel in subscriptions:
                await self._send_subscribe_message(
                    peer_id,
                    topic_id,
                    channel,
                )