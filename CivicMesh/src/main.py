import argparse
import asyncio
import os
import sys

# Permite ejecutar el script directamente desde la raíz del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from CivicMesh.src.network.peer import Peer


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
    return parser.parse_args()


async def main():
    args = parse_args()
    node = Peer(
        host=args.host,
        port=args.port,
        hostfile=args.hostfile,
        fanout=args.fanout,
        timeout=args.timeout,
    )

    try:
        await node.start()
    except KeyboardInterrupt:
        print(f"\n[{node.gossiper.node_id}] Apagando nodo...")


if __name__ == "__main__":
    asyncio.run(main())