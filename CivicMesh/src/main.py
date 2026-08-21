import argparse
import asyncio
import json
import os
import sys

# Permite ejecutar el script directamente desde la raíz del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from CivicMesh.src.network.peer import Peer
from CivicMesh.src.pubsub.topic import GeographicTopic, TopicLevel


def parse_args():
    parser = argparse.ArgumentParser(description="CivicMesh Node Runner")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host IP")
    parser.add_argument(
        "--port", type=int, required=True, help="Puerto del nodo (ej. 8000)"
    )
    parser.add_argument(
        "--hostfile",
        type=str,
        default="hostfile.txt",
        help="Ruta al archivo hostfile",
    )
    parser.add_argument(
        "--fanout", type=int, default=2, help="Número de peers a contactar"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=6.0,
        help="Timeout para declarar nodo muerto en segundos (recomendado >= 6.0)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help=(
            "Habilita un loop de comandos por terminal para probar "
            "la capa Pub/Sub manualmente (SUBSCRIBE / PUBLISH / "
            "INBOX / PEERS). Sin este flag, el nodo corre en modo "
            "silencioso como antes (compatible con docker-compose, "
            "scripts de slurm, etc.)."
        ),
    )
    return parser.parse_args()


async def _command_loop(node: Peer) -> None:
    """
    Loop interactivo simple para probar la capa Pub/Sub desde la
    terminal — la contraparte de la demo de gossip del README,
    pero para publish()/subscribe().

    Comandos soportados:
        SUBSCRIBE <nivel>:<nombre> <canal>
            Ej: SUBSCRIBE comuna:Maipu objective

        PUBLISH <topic_id> <canal> <payload_json>
            Ej: PUBLISH comuna:maipu objective {"value": 42}

        INBOX
            Lista los mensajes entregados localmente hasta ahora.

        PEERS
            Lista los peers conocidos vía gossip.
    """

    print(
        f"[{node.gossiper.node_id}] Modo interactivo. "
        f"Comandos: SUBSCRIBE, PUBLISH, INBOX, PEERS "
        f"(Ctrl+D o Ctrl+C para salir)"
    )

    # IMPORTANTE: no usar asyncio.to_thread(input, ...) aquí.
    #
    # input() bloquea un hilo real del sistema operativo, no una
    # corrutina. Cuando se cancela la tarea (ej. Ctrl+C), asyncio
    # deja de esperar el resultado, pero el hilo en sí sigue
    # bloqueado indefinidamente en input() — Python no puede
    # forzar su cierre desde afuera. Al salir, asyncio.run()
    # intenta esperar (hasta 300s) a que ese hilo termine antes
    # de cerrar el proceso, lo que produce el hang silencioso /
    # "RuntimeWarning: executor did not finish joining".
    #
    # Leer stdin con las primitivas nativas de asyncio
    # (connect_read_pipe + StreamReader) sí se integra con el
    # event loop y responde correctamente a la cancelación.
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        print("> ", end="", flush=True)

        try:
            raw_line = await reader.readline()
        except asyncio.CancelledError:
            break

        if not raw_line:
            # EOF (Ctrl+D, o stdin cerrado).
            break

        line = raw_line.decode().strip()
        if not line:
            continue

        parts = line.split(maxsplit=2)
        cmd = parts[0].upper()

        try:
            if cmd == "SUBSCRIBE" and len(parts) >= 3:
                topic_spec, channel = parts[1], parts[2]
                level_str, name = topic_spec.split(":", 1)
                topic = GeographicTopic(TopicLevel(level_str), name)

                await node.subscribe(topic, channel)

                print(f"Suscrito a {topic.id}/{channel}")

            elif cmd == "PUBLISH" and len(parts) >= 3:
                topic_id, rest = parts[1], parts[2]
                channel, _, payload_str = rest.partition(" ")
                payload = (
                    json.loads(payload_str) if payload_str.strip() else {}
                )

                msg = await node.publish(
                    topic=topic_id,
                    channel=channel,
                    payload=payload,
                )

                print(f"Publicado {msg.id} (ttl={msg.ttl})")

            elif cmd == "INBOX":
                if not node.local_inbox:
                    print("  (vacío)")
                for m in node.local_inbox:
                    print(f"  {m.id}  {m.topic}/{m.channel}  {m.payload}")

            elif cmd == "PEERS":
                if not node.gossiper.peers_view:
                    print("  (ningún peer conocido todavía)")
                for peer_id in node.gossiper.peers_view:
                    print(f"  {peer_id}")

            else:
                print(
                    "Comando no reconocido. Usa SUBSCRIBE, PUBLISH, "
                    "INBOX o PEERS."
                )

        except Exception as e:
            print(f"Error: {e}")


async def main():
    args = parse_args()
    node = Peer(
        host=args.host,
        port=args.port,
        hostfile=args.hostfile,
        fanout=args.fanout,
        timeout=args.timeout,
    )

    if not args.interactive:
        # Comportamiento original: nodo silencioso, solo gossip.
        try:
            await node.start()
        except KeyboardInterrupt:
            print(f"\n[{node.gossiper.node_id}] Apagando nodo...")
        return

    # Modo interactivo: el servidor/gossip corren en background
    # mientras la terminal queda libre para comandos Pub/Sub.
    server_task = asyncio.create_task(node.start())

    try:
        await _command_loop(node)
    finally:
        server_task.cancel()
        await asyncio.gather(server_task, return_exceptions=True)
        print(f"\n[{node.gossiper.node_id}] Apagando nodo...")


if __name__ == "__main__":
    asyncio.run(main())