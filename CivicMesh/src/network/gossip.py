import time, random

class Gossiper:
    """Clase que utiliza el patrón Gossip"""
    # Es arbitrario el timeout es para evitar problemas si no se asigna
    def __init__(self, host: str, port: int, fanout_in: int = 2, timeout_in: float = 3.0, peer_id: str = None):
        self.node_host = host
        self.node_port = port
        
        # Si no pasan un ID explícito, usamos "host:port"
        self.node_id = peer_id if peer_id else f"{host}:{port}"

        self.fanout = fanout_in
        self.timeout = timeout_in
        self.peers_view = {}

    def membership_event(self, members):
        """
        Fusiona la lista recibida en el payload con el diccionario
        peers_view.

        Returns
        -------
        list
            IDs de los peers que NO se conocían previamente
            (recién descubiertos en esta llamada). Permite que
            capas superiores (p. ej. Pub/Sub) reaccionen a nuevos
            miembros de la malla — por ejemplo, reanunciándoles
            las suscripciones locales existentes.
        """

        now = time.time()
        new_peer_ids = []

        for member in members:

            m_id = member.get("node_id")
            m_host = member.get("node_host")
            m_port = member.get("node_port")
            m_last_seen = member.get("last_seen", time.time())

            if m_id == self.node_id:
                continue

            if (now - m_last_seen) > self.timeout:
                continue

            if m_id in self.peers_view:
                if m_last_seen > self.peers_view[m_id]["last_seen"]:
                    self.peers_view[m_id]["last_seen"] = m_last_seen

            else:
                self.peers_view[m_id] = {
                    "node_host": m_host,
                    "node_port": m_port,
                    "last_seen": m_last_seen
                }
                new_peer_ids.append(m_id)
                print(f"[{self.node_id}] ==|== ¡Nuevo peer descubierto!: {m_id} (Total: {len(self.peers_view)})")

        return new_peer_ids

    def random_discovery(self):
        """Selecciona hasta 'fanout' nodos al azar de la vista local."""

        nodes = list(self.peers_view.keys())
    
        # Si no conocemos a nadie todavía, retornamos lista vacía
        if not nodes:
            return []

        # Ajusta el número de nodos a tomar según los disponibles
        k = min(self.fanout, len(nodes))
        return random.sample(nodes, k)

    def export_membership(self):
        """Exporta la vista local en formato de lista para el payload JSON."""

        members = [
            {
                "node_id": self.node_id,
                "node_host": self.node_host,
                "node_port": self.node_port,
                "last_seen": time.time()
            }
        ]
        
        # 2. Agregar los peers conocidos de self.peers_view
        for p_id, info in self.peers_view.items():
            members.append({
                "node_id": p_id,
                "node_host": info["node_host"],
                "node_port": info["node_port"],
                "last_seen": info["last_seen"]
            })
            
        return members

    def export_payload(self):
        """Genera el diccionario final listo para enviarse por la red"""

        return {
            "intent": "GOSSIP_MEMBERSHIP",
            "members": self.export_membership()
        }

    def purge_dead_peers(self):
        """ método para hacer el barrido periodico para encontrar nodos muertos """

        now = time.time()
        dead_peers = []

        nodes_ids = list(self.peers_view.keys())

        for pid in nodes_ids:
            last_seen = self.peers_view[pid]["last_seen"]

            if (now - last_seen) > self.timeout:
                dead_peers.append(pid)
                del self.peers_view[pid]

        #Para logs
        return dead_peers

    def bootstrap_from_file(self, filepath):
        """Registra la presencia del nodo y descubre semillas iniciales en formato host:port"""

        own_addr = f"{self.node_host}:{self.node_port}"
        lines = []

        # 1. Leer el archivo primero si ya existe
        try:
            with open(filepath, "r") as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]

        except FileNotFoundError:
            pass  # El archivo se creará en el paso 2 si no existe

        except Exception as e:
            print(f"[{self.node_id}] Error al leer hostfile: {e}")

        # 2. Registrarse en el hostfile SOLO si no estaba inscrito previamente
        if own_addr not in lines:
            try:
                with open(filepath, "a") as f:
                    f.write(f"{own_addr}\n")

            except Exception as e:
                print(f"[{self.node_id}] Error al escribir en hostfile: {e}")

        # 3. Filtrar candidatos y seleccionar hasta 2 semillas al azar
        candidates = [addr for addr in lines if addr != own_addr]
        if candidates:
            k = min(len(candidates), 2)
            selected_seeds = random.sample(candidates, k)
            
            for addr in selected_seeds:
                host, port = addr.split(":")
                self.peers_view[addr] = {
                    "node_host": host,
                    "node_port": int(port),
                    "last_seen": time.time()
                }

            print(f"[{self.node_id}] ==|== Semillas cargadas desde hostfile: {selected_seeds}")