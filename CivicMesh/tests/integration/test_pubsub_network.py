import asyncio
import time

from CivicMesh.src.network.peer import Peer
from CivicMesh.src.pubsub.topic import GeographicTopic, TopicLevel
from CivicMesh.src.pubsub.channel import ChannelPolicy, ChannelPolicies


def _policies():
    return ChannelPolicies(
        objective=ChannelPolicy(
            channel="objective", ttl=5, priority=3, fanout=3
        ),
        subjective=ChannelPolicy(
            channel="subjective", ttl=3, priority=1, fanout=2
        ),
    )


async def _start_mesh(n, base_port, hostfile, timeout=3.0):
    """
    Levanta n peers , cada uno como una task de asyncio,
    compartiendo el mismo hostfile para descubrirse entre
    sí vía bootstrap_from_file().
    """
    peers = []
    tasks = []

    for i in range(n):
        peer = Peer(
            host="127.0.0.1",
            port=base_port + i,
            hostfile=str(hostfile),
            channel_policies=_policies(),
            timeout=timeout,
        )
        peers.append(peer)
        tasks.append(asyncio.create_task(peer.start()))

        await asyncio.sleep(0.15)

    return peers, tasks


async def _stop_mesh(tasks):
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def _wait_until(condition_fn, timeout, poll=0.2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition_fn():
            return True
        await asyncio.sleep(poll)
    return condition_fn()


async def _wait_for_full_convergence(peers, timeout=6.0):
    """Espera hasta que cada peer conozca a los demás n-1 peers."""
    n = len(peers)
    return await _wait_until(
        lambda: all(len(p.gossiper.peers_view) == n - 1 for p in peers),
        timeout=timeout,
    )


# =============================================================
# Convergencia de membresía
# =============================================================


def test_three_peers_converge_via_gossip(tmp_path):
    """
    Tres peers arrancados de forma independiente, comunicándose
    solo por gossip real (sin conocerse de antes salvo por el
    hostfile compartido), deben terminar conociéndose entre sí.
    """

    async def scenario():
        hostfile = tmp_path / "hosts.txt"
        peers, tasks = await _start_mesh(3, 9300, hostfile)
        try:
            converged = await _wait_for_full_convergence(
                peers, timeout=8.0
            )
            assert converged, (
                "Los 3 peers no convergieron a tiempo: "
                f"vistas={[len(p.gossiper.peers_view) for p in peers]}"
            )
        finally:
            await _stop_mesh(tasks)

    asyncio.run(scenario())


# =============================================================
# publish() con red real, entrega local en el suscriptor
# =============================================================


def test_publish_reaches_subscriber_across_real_network(tmp_path):
    """
    Verifica el flujo completo end-to-end: A se suscribe, B
    publica, y el mensaje debe llegar al local_inbox de A
    cruzando sockets TCP reales — sin mocks de por medio. Un
    tercer peer, no suscrito, no debe recibirlo.
    """

    async def scenario():
        hostfile = tmp_path / "hosts.txt"
        peers, tasks = await _start_mesh(3, 9310, hostfile)
        try:
            assert await _wait_for_full_convergence(peers, timeout=8.0)

            publisher, subscriber, bystander = peers

            maipu = GeographicTopic(TopicLevel.COMUNA, "Maipu")
            await subscriber.subscribe(maipu, "objective")

            # Dar tiempo a que el suscribe llegue a los demás.
            await asyncio.sleep(1.0)

            await publisher.publish(
                topic="comuna:maipu",
                channel="objective",
                payload={"value": 42},
            )

            delivered = await _wait_until(
                lambda: len(subscriber.local_inbox) > 0,
                timeout=5.0,
            )

            assert delivered, (
                "El mensaje nunca llegó al suscriptor por red real"
            )
            assert subscriber.local_inbox[0].payload == {"value": 42}
            assert len(bystander.local_inbox) == 0
        finally:
            await _stop_mesh(tasks)

    asyncio.run(scenario())


# =============================================================
# Re-anuncio a peer tardío
# =============================================================


def test_late_joining_peer_learns_existing_subscription(tmp_path):
    """
    Reproduce, con red real (sin mocks), un peer se suscribe cuando
    la malla tiene 2 nodos; luego un tercer peer se une después.
    Debe recibir el re-anuncio de esa suscripción sin que nadie
    vuelva a llamar subscribe() manualmente.
    """

    async def scenario():
        hostfile = tmp_path / "hosts.txt"

        peers, tasks = await _start_mesh(2, 9320, hostfile)
        try:
            assert await _wait_for_full_convergence(peers, timeout=6.0)

            early_subscriber = peers[0]
            maipu = GeographicTopic(TopicLevel.COMUNA, "Maipu")
            await early_subscriber.subscribe(maipu, "objective")
            await asyncio.sleep(0.5)

            # Se une un tercer peer después de que la suscripción ya existía.
            late_peer = Peer(
                host="127.0.0.1",
                port=9322,
                hostfile=str(hostfile),
                channel_policies=_policies(),
            )
            tasks.append(asyncio.create_task(late_peer.start()))
            peers.append(late_peer)

            early_id = early_subscriber.gossiper.node_id

            def learned():
                info = late_peer.gossiper.peers_view.get(early_id)
                if not info:
                    return False
                return (
                    "comuna:maipu",
                    "objective",
                ) in info.get("subscriptions", set())

            ok = await _wait_until(learned, timeout=8.0)

            assert ok, (
                "El peer tardío nunca recibió el re-anuncio de "
                "la suscripción existente"
            )
        finally:
            await _stop_mesh(tasks)

    asyncio.run(scenario())