from typing import Any, Dict, List, Optional

from .message import Message
from .channel import ChannelPolicies


# Multiplicador máximo de prioridad admitido al calcular el fanout.
# Coincide con el nivel más alto declarado en config.yaml
# (pubsub.priority.high = 3).
# Existe para que una prioridad mal configurada (o maliciosa)
# no pueda degenerar en flooding.
DEFAULT_MAX_PRIORITY_MULTIPLIER = 3


def _effective_fanout(
    base_fanout: int,
    priority: int,
    max_priority_multiplier: int = DEFAULT_MAX_PRIORITY_MULTIPLIER,
) -> int:
    """
    Calcula el fanout efectivo a partir del fanout base y la
    prioridad del mensaje.

    Política:

        fanout_efectivo = base_fanout * priority

    La prioridad se limita mediante max_priority_multiplier
    para evitar que una prioridad excesiva produzca flooding.
    """

    if base_fanout <= 0:
        return base_fanout

    effective_priority = max(1, priority)
    capped_priority = min(
        effective_priority,
        max_priority_multiplier,
    )

    return base_fanout * capped_priority


def _get_peers_view(local_view: Dict[str, Any]) -> Dict[str, Any]:
    """
    Obtiene la vista de peers desde local_view.

    Se aceptan ambas estructuras:

        {
            "peer_id": {...},
            ...
        }

    o:

        {
            "peers_view": {
                "peer_id": {...},
                ...
            },
            "seen_messages": set(...)
        }
    """

    if "peers_view" in local_view:
        return local_view["peers_view"]

    return local_view


def _get_seen_messages(local_view: Dict[str, Any]) -> set:
    """
    Obtiene el conjunto de mensajes ya procesados.
    """

    return local_view.get("seen_messages", set())


def _is_subscribed(
    peer_info: Any,
    topic: str,
    channel: str,
) -> bool:
    """
    Determina si un peer está suscrito al tópico y canal.

    Se acepta:

        (topic_id, channel)

    o solamente:

        topic_id
    """

    if not isinstance(peer_info, dict):
        return False

    subscriptions = peer_info.get("subscriptions")

    if not subscriptions:
        return False

    target = (topic, channel)

    try:
        if target in subscriptions:
            return True
    except TypeError:
        return False

    # Formato simplificado:
    # solo se registra el topic_id.
    try:
        return topic in subscriptions
    except TypeError:
        return False


def should_forward(
    msg: Message,
    topic: str,
    local_view: Dict[str, Any],
    channel_policies: Optional[ChannelPolicies] = None,
) -> bool:
    """
    Decide si un mensaje Pub/Sub debe ser reenviado.

    La decisión considera:

    1. El tópico recibido corresponde al tópico del mensaje.
    2. El canal del mensaje es válido.
    3. El mensaje todavía tiene TTL disponible.
    4. El mensaje no ha sido procesado anteriormente.
    5. Existe al menos un peer candidato.
    6. Si se entrega una ChannelPolicy, el mensaje utiliza
       la configuración correspondiente a su canal.

    channel_policy es opcional para mantener compatibilidad
    con las llamadas existentes.
    """

    if topic != msg.topic:
        return False

    if msg.channel not in {"objective", "subjective"}:
        return False

    if not msg.can_forward():
        return False

    # Si existe una política explícita, verificamos que el canal
    # tenga una configuración válida.
    if channel_policies is not None:
        try:
            channel_policies.get(msg.channel)
        except ValueError:
            return False

    seen_messages = _get_seen_messages(local_view)

    if msg.id in seen_messages:
        return False

    peers_view = _get_peers_view(local_view)

    if not peers_view:
        return False

    return True


def select_fanout_peers(
    msg: Message,
    local_peer_id: str,
    local_view: Dict[str, Any],
    fanout: int = 3,
    max_priority_multiplier: int = DEFAULT_MAX_PRIORITY_MULTIPLIER,
    channel_policies: Optional[ChannelPolicies] = None,
) -> List[str]:
    """
    Selecciona los peers a los que se reenviará un mensaje Pub/Sub.

    Política:

    1. No reenviar mensajes con TTL agotado.
    2. No reenviar mensajes ya procesados.
    3. No seleccionar al propio peer.
    4. No devolver inmediatamente el mensaje a su emisor.
    5. Priorizar peers suscritos al mismo tópico y canal.
    6. Escalar el número de destinatarios según la prioridad.
    7. Limitar la cantidad de destinatarios al fanout efectivo.
    8. Si no hay suficientes peers suscritos, completar con otros.
    9. Nunca realizar flooding.

    channel_policies permite validar que el mensaje pertenezca a
    uno de los dos canales configurados.

    Returns
    -------
    List[str]
        IDs de los peers seleccionados.
    """

    if channel_policies is not None:
        channel_policy = channel_policies.get(msg.channel)
        fanout = channel_policy.fanout

    if fanout < 0:
        raise ValueError(
            "fanout no puede ser negativo"
        )

    if fanout == 0:
        return []

    if not should_forward(
        msg,
        msg.topic,
        local_view,
        channel_policies=channel_policies,
    ):
        return []

    peers_view = _get_peers_view(local_view)

    subscribed_peers: List[str] = []
    other_peers: List[str] = []

    for peer_id, peer_info in peers_view.items():

        # Nunca enviarse el mensaje a sí mismo.
        if peer_id == local_peer_id:
            continue

        # No devolver inmediatamente el mensaje al peer
        # que lo envió.
        if msg.source and peer_id == msg.source:
            continue

        if _is_subscribed(
            peer_info,
            msg.topic,
            msg.channel,
        ):
            subscribed_peers.append(peer_id)
        else:
            other_peers.append(peer_id)

    # Primero peers interesados.
    # Después peers restantes si todavía necesitamos
    # completar el fanout.
    candidates = subscribed_peers + other_peers

    effective_fanout = _effective_fanout(
        base_fanout=fanout,
        priority=msg.priority,
        max_priority_multiplier=max_priority_multiplier,
    )

    return candidates[:effective_fanout]


def mark_message_seen(
    msg: Message,
    local_view: Dict[str, Any],
) -> None:
    """
    Marca un mensaje como procesado por el peer local.

    Esto permite evitar ciclos y procesamiento duplicado.
    """

    seen_messages = local_view.setdefault(
        "seen_messages",
        set(),
    )

    seen_messages.add(msg.id)