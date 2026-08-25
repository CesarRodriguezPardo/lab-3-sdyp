#!/usr/bin/env python3
"""CivicMesh Publisher Runner.

Ejecuta un publicador del Dominio A (Delitos) o Dominio B (Calidad del Aire)
conectado a la malla distribuida de CivicMesh.
"""

import argparse
import asyncio
import os
import sys
import time
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
    from CivicMesh.src.domains.air_quality.perception import calcular_percepcion_aire
    from CivicMesh.src.aggregation.metrics import get_metrics_writer
except ModuleNotFoundError:
    from src.network.peer import Peer
    from src.pubsub.topic import GeographicTopic, TopicLevel
    from src.domains.air_quality.replay import AirQualityPublisher
    from src.domains.crimes.generator import generar_delitos
    from src.domains.crimes.perception import calcular_inseguridad
    from src.domains.air_quality.perception import calcular_percepcion_aire
    from src.aggregation.metrics import get_metrics_writer


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
    parser.add_argument("--metrics-enabled", action="store_true", default=True,
                        help="Habilitar generación de métricas de brecha")
    parser.add_argument("--metrics-interval", type=float, default=5.0,
                        help="Intervalo en segundos entre volcados de métricas")
    parser.add_argument("--run-id", type=str, default="",
                        help="ID de la corrida (override CIVICMESH_RUN_ID)")
    return parser.parse_args()


async def run_crimes_publisher(peer: Peer, comuna: str, config: dict, interval: float, metrics_writer=None):
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

        # 4. Escribir métrica de brecha (G_c = r_c, P_c = p_c, M_c = m_c)
        if metrics_writer:
            metrics_writer.write_gap(
                peer_id=peer.gossiper.node_id,
                dominio="A",
                comuna=comuna,
                timestamp=time.time(),
                G_c=float(r_c),
                P_c=p_c,
                M_c=m_c,
            )

        # 5. Publicar en canal subjetivo
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

    metrics_config = config.get("metrics", {})
    metrics_enabled = args.metrics_enabled and metrics_config.get("enabled", True)
    metrics_interval = metrics_config.get("interval_dt", args.metrics_interval)
    metrics_flush_interval = metrics_config.get("flush_interval", 3)
    metrics_output_dir = metrics_config.get("output_dir", None)
    metrics_run_id = args.run_id or os.environ.get("CIVICMESH_RUN_ID") or ""

    dominio = "A" if args.domain == "crimes" else "B"

    peer = Peer(
        host=args.host,
        port=args.port,
        hostfile=args.hostfile,
        metrics_enabled=metrics_enabled,
        metrics_interval=metrics_interval,
        metrics_run_id=metrics_run_id or None,
        metrics_output_dir=metrics_output_dir,
        metrics_flush_interval=metrics_flush_interval,
        metrics_dominio=dominio,
    )

    metrics_writer = None
    if metrics_enabled:
        metrics_writer = get_metrics_writer(
            run_id=metrics_run_id or None,
            output_dir=metrics_output_dir,
            flush_interval=metrics_flush_interval,
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
            # Wrap publisher.run to write gap metrics
            await run_air_quality_with_metrics(publisher, args.comuna, args.interval, metrics_writer)
        else:
            await run_crimes_publisher(peer, args.comuna, config, args.interval, metrics_writer)
    finally:
        peer_task.cancel()
        await asyncio.gather(peer_task, return_exceptions=True)
        if metrics_writer:
            metrics_writer.flush_all()
            metrics_writer.close()


async def run_air_quality_with_metrics(publisher, comuna: str, interval: float, metrics_writer):
    """Wrapper que escribe métricas de brecha para air_quality."""
    import json
    import logging
    from CivicMesh.src.pubsub.topic import GeographicTopic, TopicLevel

    logging.info(f"Iniciando publicador (replay) para la comuna: {comuna}")

    topico_geo = GeographicTopic(level=TopicLevel.COMUNA, name=comuna)

    # ¡NUEVO!: Nos suscribimos al canal subjetivo para recibir los rumores por la red
    await publisher.pubsub_client.subscribe(topic=topico_geo, channel='subjective')

    for registro in publisher.dataset:
        timestamp = registro.get("timestamp")
        v_c = registro.get("comunas", {}).get(comuna)

        if v_c is None:
            continue

        # 1. Publicar objetivo
        mensaje_objetivo = {
            "tipo": "medicion_pm10",
            "valor": v_c,
            "timestamp": timestamp
        }
        await publisher.pubsub_client.publish(
            topic=topico_geo,
            channel='objective',
            payload=mensaje_objetivo
        )

        # 2. Leer rumores desde el buzón local (local_inbox) del peer
        rumores_q = []
        mensajes_procesados = []

        for msg in publisher.pubsub_client.local_inbox:
            # Validar que el mensaje sea del canal y tópico correctos
            if msg.channel == 'subjective' and msg.topic == topico_geo.id:
                # Extraer el valor del payload enviado por otro nodo
                if isinstance(msg.payload, dict) and "valor" in msg.payload:
                    rumores_q.append(msg.payload["valor"])
                mensajes_procesados.append(msg)

        # Limpiar el buzón para el siguiente ciclo
        for msg in mensajes_procesados:
            publisher.pubsub_client.local_inbox.remove(msg)

        # 3. Utilizar tu lógica de percepción real
        p_c, publisher.m_c = calcular_percepcion_aire(
            v_c=v_c,
            m_c_prev=publisher.m_c,
            rumores_q=rumores_q,
            config=publisher.config,
            comuna=comuna,
            timestamp=timestamp
        )

        # 4. Escribir métrica de brecha
        if metrics_writer:
            metrics_writer.write_gap(
                peer_id=publisher.pubsub_client.gossiper.node_id,
                dominio="B",
                comuna=comuna,
                timestamp=time.time(),
                G_c=v_c,
                P_c=p_c,
                M_c=publisher.m_c,
            )

        # 5. Publicar subjetivo
        mensaje_subjetivo = {
            "tipo": "percepcion_pm10",
            "valor": p_c,
            "timestamp": timestamp
        }
        await publisher.pubsub_client.publish(
            topic=topico_geo,
            channel='subjective',
            payload=mensaje_subjetivo
        )

        await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(main())
