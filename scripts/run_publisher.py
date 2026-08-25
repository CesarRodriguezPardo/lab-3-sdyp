#!/usr/bin/env python3
"""CivicMesh Publisher Runner.

Ejecuta un publicador del Dominio A (Delitos) o Dominio B (Calidad del Aire)
conectado a la malla distribuida de CivicMesh.
"""

import argparse
import asyncio
import os
import sys
import yaml
from pathlib import Path

# Configurar sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
for p in (ROOT_DIR, ROOT_DIR / "CivicMesh"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    from CivicMesh.src.network.peer import Peer
    from CivicMesh.src.pubsub.topic import GeographicTopic, TopicLevel
    from CivicMesh.src.domains.air_quality.replay import AirQualityPublisher
    from CivicMesh.src.domains.crimes.generator import generar_delitos
    from CivicMesh.src.domains.crimes.perception import calcular_inseguridad
except ModuleNotFoundError:
    from src.network.peer import Peer
    from src.pubsub.topic import GeographicTopic, TopicLevel
    from src.domains.air_quality.replay import AirQualityPublisher
    from src.domains.crimes.generator import generar_delitos
    from src.domains.crimes.perception import calcular_inseguridad


def parse_args():
    parser = argparse.ArgumentParser(description="CivicMesh Publisher Runner")
    parser.add_argument("--domain", choices=["air_quality", "crimes"], default="air_quality",
                        help="Dominio a publicar: air_quality o crimes")
    parser.add_argument("--comuna", type=str, default="Santiago",
                        help="Nombre de la comuna (ej. Santiago, Maipú, Las Condes)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host IP")
    parser.add_argument("--port", type=int, default=9000, help="Puerto del publicador")
    parser.add_argument("--hostfile", type=str, default="hostfile.txt",
                        help="Ruta al hostfile de la malla")
    parser.add_argument("--config", type=str, default="", help="Ruta a archivo de configuracion")
    parser.add_argument("--cache-path", type=str, default="",
                        help="Ruta al archivo cache JSONL para air_quality")
    parser.add_argument("--interval", type=float, default=2.0,
                        help="Intervalo en segundos entre publicaciones")
    return parser.parse_args()


async def run_crimes_publisher(peer: Peer, comuna: str, config: dict, interval: float):
    print(f"[{peer.gossiper.node_id}] Iniciando publicador de Delitos para: {comuna}")
    topic = GeographicTopic(level=TopicLevel.COMUNA, name=comuna)
    await peer.subscribe(topic=topic, channel="subjective")

    m_c = 0.0
    t = 0

    while True:
        timestamp_str = f"t_{t}"
        eventos, r_c = generar_delitos(comuna=comuna, config=config, timestamp=timestamp_str, delta_t=interval)

        # 1. Publicar eventos en canal objetivo
        for ev in eventos:
            await peer.publish(topic=topic, channel="objective", payload=ev)

        # 2. Recolectar rumores subjetivos del buzon
        rumores_q = []
        procesados = []
        for msg in peer.local_inbox:
            if msg.channel == "subjective" and msg.topic == topic.id:
                if isinstance(msg.payload, dict) and "indice_inseguridad" in msg.payload:
                    rumores_q.append(msg.payload["indice_inseguridad"])
                procesados.append(msg)

        for msg in procesados:
            peer.local_inbox.remove(msg)

        # 3. Calcular percepcion subjetiva
        p_c, m_c = calcular_inseguridad(
            r_c=r_c,
            m_c_prev=m_c,
            rumores_q=rumores_q,
            config=config.get("perception", {}),
            comuna=comuna,
            timestamp=timestamp_str,
        )

        # 4. Publicar en canal subjetivo
        payload_subjetivo = {
            "tipo": "sensacion_inseguridad",
            "indice_inseguridad": round(p_c, 4),
            "delitos_locales": r_c,
            "timestamp": timestamp_str,
        }
        await peer.publish(topic=topic, channel="subjective", payload=payload_subjetivo)
        print(f"[{comuna}] t={t} Delitos={r_c} Inseguridad={p_c:.4f}")

        t += 1
        await asyncio.sleep(interval)


async def main():
    args = parse_args()

    # Cargar configuracion
    config_path = args.config
    if not config_path:
        default_cfg = ROOT_DIR / "CivicMesh" / "config" / f"{args.domain}.yaml"
        if default_cfg.exists():
            config_path = str(default_cfg)
        else:
            config_path = str(ROOT_DIR / "CivicMesh" / "config" / "config.yaml")

    config = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    peer = Peer(
        host=args.host,
        port=args.port,
        hostfile=args.hostfile,
    )
    peer_task = asyncio.create_task(peer.start())

    try:
        if args.domain == "air_quality":
            cache_file = args.cache_path or str(ROOT_DIR / "CivicMesh" / "data" / "air_quality" / "sinca_cache.jsonl")
            publisher = AirQualityPublisher(
                comuna=args.comuna,
                cache_path=cache_file,
                pubsub_client=peer,
                config=config.get("perception", config),
            )
            await publisher.run(delta_t_segundos=args.interval)
        else:
            await run_crimes_publisher(peer, args.comuna, config, args.interval)
    finally:
        peer_task.cancel()
        await asyncio.gather(peer_task, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
