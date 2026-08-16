import time
import pytest
from CivicMesh.src.network.gossip import Gossiper


@pytest.fixture
def gossiper():
    """Fixture que provee una instancia limpia de Gossiper para cada prueba."""
    return Gossiper(
        host="127.0.0.1",
        port=8000,
        fanout_in=2,
        timeout_in=3.0,
    )


# ==========================================
# 1. PRUEBAS DE VISTA PARCIAL (Partial View)
# ==========================================

def test_membership_event_partial_view_incorporation(gossiper):
    """Verifica la incorporación de una vista parcial entrante."""
    partial_members = [
        {"node_id": "127.0.0.1:8001", "node_host": "127.0.0.1", "node_port": 8001, "last_seen": time.time()},
        {"node_id": "127.0.0.1:8002", "node_host": "127.0.0.1", "node_port": 8002, "last_seen": time.time()},
    ]

    gossiper.membership_event(partial_members)

    assert len(gossiper.peers_view) == 2
    assert "127.0.0.1:8001" in gossiper.peers_view
    assert "127.0.0.1:8002" in gossiper.peers_view


def test_random_discovery_bounded_by_fanout(gossiper):
    """Verifica que la selección aleatoria respete el límite de fanout."""
    for p in range(8001, 8006):
        pid = f"127.0.0.1:{p}"
        gossiper.peers_view[pid] = {
            "node_host": "127.0.0.1",
            "node_port": p,
            "last_seen": time.time(),
        }

    selected = gossiper.random_discovery()

    assert len(selected) == gossiper.fanout
    for node in selected:
        assert node in gossiper.peers_view


# ==========================================
# 2. PRUEBAS DE TIMEOUT DE FALLO (Failure Detection)
# ==========================================

def test_purge_dead_peers(gossiper):
    """Verifica que se eliminen únicamente los nodos que excedieron el timeout."""
    now = time.time()

    # Nodo activo (hace 1s)
    gossiper.peers_view["127.0.0.1:8001"] = {
        "node_host": "127.0.0.1",
        "node_port": 8001,
        "last_seen": now - 1.0,
    }

    # Nodo caído (hace 10s, timeout es 3.0s)
    gossiper.peers_view["127.0.0.1:8002"] = {
        "node_host": "127.0.0.1",
        "node_port": 8002,
        "last_seen": now - 10.0,
    }

    dead_peers = gossiper.purge_dead_peers()

    assert dead_peers == ["127.0.0.1:8002"]
    assert "127.0.0.1:8002" not in gossiper.peers_view
    assert "127.0.0.1:8001" in gossiper.peers_view


def test_ignore_zombie_peer_on_membership_event(gossiper):
    """Verifica que no se procesen nodos con marcas de tiempo expiradas."""
    now = time.time()
    expired_payload = [
        {
            "node_id": "127.0.0.1:8009",
            "node_host": "127.0.0.1",
            "node_port": 8009,
            "last_seen": now - 15.0,
        }
    ]

    gossiper.membership_event(expired_payload)

    assert "127.0.0.1:8009" not in gossiper.peers_view