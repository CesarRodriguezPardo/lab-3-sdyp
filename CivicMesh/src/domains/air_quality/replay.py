import json
import asyncio
import logging
from CivicMesh.src.pubsub.topic import GeographicTopic, TopicLevel
from src.domains.air_quality.perception import calcular_percepcion_aire

class AirQualityPublisher:
    def __init__(self, comuna, cache_path, pubsub_client, config):
        self.comuna = comuna
        self.cache_path = cache_path
        self.pubsub_client = pubsub_client
        self.config = config
        
        self.m_c = 0.0  
        self.dataset = self._cargar_dataset()

    def _cargar_dataset(self):
        data = []
        try:
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                for line in f:
                    data.append(json.loads(line))
        except Exception as e:
            logging.exception(f"Error cargando caché para {self.comuna}: {e}")
        return data

    async def run(self, delta_t_segundos=1.0):
        logging.info(f"Iniciando publicador (replay) para la comuna: {self.comuna}")
        
        topico_geo = GeographicTopic(level=TopicLevel.COMUNA, name=self.comuna)
        
        # ¡NUEVO!: Nos suscribimos al canal subjetivo para recibir los rumores por la red
        await self.pubsub_client.subscribe(topic=topico_geo, channel='subjective')
        
        for registro in self.dataset:
            timestamp = registro.get("timestamp")
            v_c = registro.get("comunas", {}).get(self.comuna)
            
            if v_c is None:
                continue

            # 1. Publicar objetivo
            mensaje_objetivo = {
                "tipo": "medicion_pm10",
                "valor": v_c,
                "timestamp": timestamp
            }
            await self.pubsub_client.publish(
                topic=topico_geo, 
                channel='objective', 
                payload=mensaje_objetivo
            )
            
            # 2. Leer rumores desde el buzón local (local_inbox) del peer
            rumores_q = []
            mensajes_procesados = []
            
            for msg in self.pubsub_client.local_inbox:
                # Validar que el mensaje sea del canal y tópico correctos
                if msg.channel == 'subjective' and msg.topic == topico_geo.id:
                    # Extraer el valor del payload enviado por otro nodo
                    if isinstance(msg.payload, dict) and "valor" in msg.payload:
                        rumores_q.append(msg.payload["valor"])
                    mensajes_procesados.append(msg)
            
            # Limpiar el buzón para el siguiente ciclo
            for msg in mensajes_procesados:
                self.pubsub_client.local_inbox.remove(msg)
            
            # 3. Utilizar tu lógica de percepción real (adiós warnings del linter)
            p_c, self.m_c = calcular_percepcion_aire(
                v_c=v_c, 
                m_c_prev=self.m_c, 
                rumores_q=rumores_q, 
                config=self.config, 
                comuna=self.comuna, 
                timestamp=timestamp
            )
            
            # 4. Publicar subjetivo
            mensaje_subjetivo = {
                "tipo": "percepcion_pm10",
                "valor": p_c,
                "timestamp": timestamp
            }
            await self.pubsub_client.publish(
                topic=topico_geo, 
                channel='subjective', 
                payload=mensaje_subjetivo
            )

            await asyncio.sleep(delta_t_segundos)