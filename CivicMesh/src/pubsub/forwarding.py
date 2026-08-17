from typing import Any, Dict, List, Tuple

from .message import Message


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

    Las suscripciones remotas utilizan pares:

        (topic_id, channel)

    pero también se acepta el caso simplificado en que
    solo se registra el topic_id (sin distinguir canal).
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

    # Formato simplificado: solo el topic_id, sin canal.
    try:
        return topic in subscriptions
    except TypeError:
        return False


def should_forward(
    msg: Message,
    topic: str,
    local_view: Dict[str, Any],
) -> bool:
    """
    Decide si un mensaje Pub/Sub debe ser reenviado.

    La decisión considera:

    1. El tópico recibido corresponde al tópico del mensaje.
    2. El mensaje todavía tiene TTL disponible.
    3. El mensaje no ha sido procesado anteriormente.
    4. Existe al menos un peer candidato.

    Esta función decide si el forwarding está permitido.

    select_fanout_peers() decide posteriormente a qué peers
    se enviará el mensaje.
    """

    if topic != msg.topic:
        return False

    if not msg.can_forward():
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
) -> List[str]:
    """
    Selecciona los peers a los que se reenviará un mensaje Pub/Sub.

    Política:

    1. No reenviar mensajes con TTL agotado.
    2. No reenviar mensajes ya procesados.
    3. No seleccionar al propio peer.
    4. No devolver inmediatamente el mensaje a su emisor.
    5. Priorizar peers suscritos al mismo tópico y canal.
    6. Limitar la cantidad de destinatarios al valor de fanout.
    7. Si no hay suficientes peers suscritos, completar el fanout
       con otros peers disponibles.
    8. Nunca realizar flooding.

    Parameters
    ----------
    msg:
        Mensaje que se desea reenviar.

    local_peer_id:
        ID del peer que realiza el forwarding.

    local_view:
        Vista local de peers.

    fanout:
        Número máximo de destinatarios.

    Returns
    -------
    List[str]
        IDs de los peers seleccionados.
    """

    if fanout < 0:
        raise ValueError("fanout no puede ser negativo")

    if fanout == 0:
        return []

    if not should_forward(
        msg,
        msg.topic,
        local_view,
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

    return candidates[:fanout]


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