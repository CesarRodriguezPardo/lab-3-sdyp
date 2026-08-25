import argparse
import asyncio
import json
import os
import sys
import yaml
from pathlib import Path

# Permite ejecutar el script directamente desde la raíz del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from CivicMesh.src.network.peer import Peer
from CivicMesh.src.pubsub.topic import GeographicTopic, TopicLevel
from CivicMesh.src.pubsub.channel import load_channel_policies


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
        "--config",
        type=str,
        default="",
        help="Ruta al archivo config.yaml",
    )
    parser.add_argument(
        "--metrics-enabled",
        action="store_true",
        default=True,
        help="Habilitar generación de métricas JSONL",
    )
    parser.add_argument(
        "--metrics-interval",
        type=float,
        default=5.0,
        help="Intervalo en segundos entre volcados de métricas",
    )
    parser.add_argument(
        "--metrics-dominio",
        type=str,
        default="unknown",
        help="Dominio asociado (A, B, unknown)",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default="",
        help="ID de la corrida (override CIVICMESH_RUN_ID)",
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


def load_config(config_path: str) -> dict:
    if not config_path:
        project_root = Path(__file__).resolve().parents[2]
        config_path = str(project_root / "config" / "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


async def _command_loop(node: Peer) -> None:
    """
    Loop interactivo simple para probar la capa Pub/Sub desde la
    terminal.

    Comandos:
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
    config = load_config(args.config)

    channel_policies = load_channel_policies(args.config) if args.config else load_channel_policies()

    metrics_config = config.get("metrics", {})
    metrics_enabled = args.metrics_enabled and metrics_config.get("enabled", True)
    metrics_interval = metrics_config.get("interval_dt", args.metrics_interval)
    metrics_flush_interval = metrics_config.get("flush_interval", 3)
    metrics_output_dir = metrics_config.get("output_dir", None)
    metrics_run_id = args.run_id or os.environ.get("CIVICMESH_RUN_ID") or ""

    node = Peer(
        host=args.host,
        port=args.port,
        hostfile=args.hostfile,
        fanout=args.fanout,
        timeout=args.timeout,
        channel_policies=channel_policies,
        metrics_enabled=metrics_enabled,
        metrics_interval=metrics_interval,
        metrics_run_id=metrics_run_id or None,
        metrics_output_dir=metrics_output_dir,
        metrics_flush_interval=metrics_flush_interval,
        metrics_dominio=args.metrics_dominio,
    )

    # Auto-suscribir a todos los tópicos configurados para métricas de convergencia
    if not args.interactive and metrics_enabled:
        geography = config.get("geography", {})
        topics = geography.get("topics", [])
        for topic_name in topics:
            topic = GeographicTopic(TopicLevel.COMUNA, topic_name)
            await node.subscribe(topic, "objective")
            await node.subscribe(topic, "subjective")
            print(f"[{node.gossiper.node_id}] Auto-suscrito a {topic.id}/objective y {topic.id}/subjective")

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