import asyncio, json, time
from CivicMesh.src.network.gossip import Gossiper

class Peer:
    def __init__(self, host: str, port: int, hostfile: str, fanout: int = 2, timeout: float = 3.0):
        self.gossiper = Gossiper(host=host, port=port, fanout_in=fanout, timeout_in=timeout)
        self.hostfile = hostfile

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
            if data:
                payload = json.loads(data.decode())
                intent = payload.get("intent")

                if intent in ("GOSSIP_MEMBERSHIP", "JOIN"):
                    members = payload.get("members", [])
                    self.gossiper.membership_event(members)

                elif intent == "PUBLISH":
                    # TO DO para la capa de pubsub (router.py /forwarding.py)
                    pass
                elif intent == "SUSCRIBE":
                    # TO DO para la capa de suscripciones
                    pass


        except Exception as e:
            print(f"[{self.gossiper.node_id}] Error procesando paquete: {e}")

        finally:
            writer.close()
            await writer.wait_closed()

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

    async def _failure_detector_loop(self):
        """Bucle peródico de detección y purga de fallos"""

        while True:
            await asyncio.sleep(self.gossiper.timeout)
            dead_peers = self.gossiper.purge_dead_peers()
            if dead_peers:
                print(f"[{self.gossiper.node_id}] Nodos detectados como caídos: {dead_peers}")


        