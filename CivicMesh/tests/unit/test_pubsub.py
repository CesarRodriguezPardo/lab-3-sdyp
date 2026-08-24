from CivicMesh.src.pubsub.message import Message
from CivicMesh.src.pubsub.forwarding import (
    should_forward,
    select_fanout_peers,
    mark_message_seen,
    _effective_fanout,
)
from CivicMesh.src.pubsub.channel import default_channel_policies


def create_message(
    topic="santiago-centro",
    channel="objective",
    ttl=5,
    priority=1,
    source="",
    message_id=None,
):
    """
    Crea un mensaje de prueba. Los parámetros son configurables
    para permitir probar distintos escenarios de forwarding.
    """

    return Message(
        topic=topic,
        channel=channel,
        payload={"value": 1},
        timestamp=1.0,
        ttl=ttl,
        priority=priority,
        source=source,
        id=message_id if message_id is not None else "msg-test",
    )


def create_peers_view():
    """
    Vista simple de peers (sin suscripciones) usada por los tests
    de should_forward que no dependen de interés por tópico.
    """

    return {
        "peer-2": {
            "node_host": "127.0.0.1",
            "node_port": 5002,
            "last_seen": 1000.0,
        },
        "peer-3": {
            "node_host": "127.0.0.1",
            "node_port": 5003,
            "last_seen": 1000.0,
        },
    }


def peers_subscribed_to(topic, n):
    """
    Vista de n peers, todos suscritos a `topic`, usada por los
    tests de escalado de fanout por prioridad.
    """

    return {
        f"peer-{i}": {"subscriptions": {topic}}
        for i in range(1, n + 1)
    }


# =========================================================
# _effective_fanout: la prioridad escala el fanout base
# =========================================================


def test_effective_fanout_low_priority():
    assert _effective_fanout(base_fanout=3, priority=1) == 3


def test_effective_fanout_normal_priority():
    assert _effective_fanout(base_fanout=3, priority=2) == 6


def test_effective_fanout_high_priority():
    assert _effective_fanout(base_fanout=3, priority=3) == 9


def test_effective_fanout_priority_is_capped():
    """
    Una prioridad fuera de escala (ej. 100) no debe escalar el
    fanout indefinidamente: se acota a max_priority_multiplier,
    para que la política nunca degenere en flooding.
    """

    assert _effective_fanout(
        base_fanout=3,
        priority=100,
        max_priority_multiplier=3,
    ) == 9


def test_effective_fanout_zero_base():
    assert _effective_fanout(base_fanout=0, priority=3) == 0


# =========================================================
# should_forward: decisión básica (tópico, seen, sin peers)
# =========================================================


def test_should_forward_with_valid_message_and_known_peers():
    message = create_message()
    local_view = create_peers_view()

    assert should_forward(message, "santiago-centro", local_view) is True


def test_should_not_forward_when_message_was_already_seen():
    message = create_message(message_id="msg-1")

    local_view = {
        "peers_view": create_peers_view(),
        "seen_messages": {"msg-1"},
    }

    assert should_forward(message, "santiago-centro", local_view) is False


def test_should_not_forward_when_topic_does_not_match():
    message = create_message(topic="santiago-centro")
    local_view = create_peers_view()

    assert should_forward(message, "providencia", local_view) is False


def test_should_not_forward_without_peers():
    message = create_message()
    local_view = {}

    assert should_forward(message, "santiago-centro", local_view) is False


def test_should_forward_with_peers_view_wrapper():
    """
    should_forward debe aceptar tanto una vista de peers plana
    como una envuelta en {"peers_view": ..., "seen_messages": ...}.
    """

    message = create_message()

    local_view = {
        "peers_view": create_peers_view(),
        "seen_messages": set(),
    }

    assert should_forward(message, "santiago-centro", local_view) is True


# =========================================================
# TTL
# =========================================================


def test_expired_message_is_not_forwarded():
    """
    Un mensaje con TTL agotado no debe ser reenviado, ni por
    should_forward ni al seleccionar peers de fanout.
    """

    msg = create_message(topic="comuna:maipu", ttl=0)

    local_view = {
        "peers_view": {
            "peer-1": {"subscriptions": {"comuna:maipu"}},
        }
    }

    assert should_forward(msg, "comuna:maipu", local_view) is False

    selected = select_fanout_peers(
        msg,
        local_peer_id="peer-0",
        local_view=local_view,
        fanout=3,
    )

    assert selected == []


def test_message_with_ttl_can_be_forwarded():
    msg = create_message(topic="comuna:maipu", ttl=2)

    local_view = {
        "peers_view": {
            "peer-1": {"subscriptions": {"comuna:maipu"}},
        }
    }

    assert should_forward(msg, "comuna:maipu", local_view) is True


# =========================================================
# should_forward + select_fanout_peers respetan "seen"
# =========================================================


def test_select_fanout_respects_seen_messages():
    message = create_message(message_id="msg-1")

    local_view = {
        "peers_view": create_peers_view(),
        "seen_messages": {"msg-1"},
    }

    selected = select_fanout_peers(
        msg=message,
        local_peer_id="peer-1",
        local_view=local_view,
        fanout=3,
    )

    assert selected == []


def test_mark_message_seen():
    """
    mark_message_seen() registra el ID del mensaje: es el
    mecanismo del que depende should_forward para no reenviar
    dos veces el mismo mensaje.
    """

    message = create_message(message_id="msg-1")
    local_view = create_peers_view()

    mark_message_seen(message, local_view)

    assert "seen_messages" in local_view
    assert "msg-1" in local_view["seen_messages"]


# =========================================================
# should_forward + ChannelPolicies reales (TTL/prioridad por canal)
# =========================================================


def test_should_forward_with_channel_policies():
    message = create_message(channel="objective")
    local_view = create_peers_view()
    policies = default_channel_policies()

    assert should_forward(
        message,
        "santiago-centro",
        local_view,
        channel_policies=policies,
    ) is True


def test_should_forward_subjective_with_channel_policies():
    message = create_message(channel="subjective", ttl=3, priority=1)
    local_view = create_peers_view()
    policies = default_channel_policies()

    assert should_forward(
        message,
        "santiago-centro",
        local_view,
        channel_policies=policies,
    ) is True


# =========================================================
# Prioridad: escalado del fanout efectivo end-to-end
# =========================================================


def test_higher_priority_increases_fanout():
    """
    Prioridad 2 debe llegar al doble de peers que 1, dado el
    mismo fanout base.
    """

    local_view = {"peers_view": peers_subscribed_to("comuna:maipu", 10)}

    selected_low = select_fanout_peers(
        create_message(topic="comuna:maipu", priority=1),
        local_peer_id="peer-0",
        local_view=local_view,
        fanout=3,
    )

    selected_normal = select_fanout_peers(
        create_message(topic="comuna:maipu", priority=2),
        local_peer_id="peer-0",
        local_view=local_view,
        fanout=3,
    )

    assert len(selected_low) == 3
    assert len(selected_normal) == 6


def test_high_priority_multiplies_fanout_by_three():
    """
    Prioridad 3 debe llegar a tres veces el fanout base.
    """

    local_view = {"peers_view": peers_subscribed_to("comuna:maipu", 10)}

    selected = select_fanout_peers(
        create_message(topic="comuna:maipu", priority=3),
        local_peer_id="peer-0",
        local_view=local_view,
        fanout=3,
    )

    assert len(selected) == 9


def test_priority_is_capped_to_avoid_flooding():
    """
    Una prioridad fuera de la escala declarada (ej. 100) no debe
    seguir escalando el fanout indefinidamente.
    """

    local_view = {"peers_view": peers_subscribed_to("comuna:maipu", 10)}

    selected_high = select_fanout_peers(
        create_message(topic="comuna:maipu", priority=3),
        local_peer_id="peer-0",
        local_view=local_view,
        fanout=3,
    )

    selected_extreme = select_fanout_peers(
        create_message(topic="comuna:maipu", priority=100),
        local_peer_id="peer-0",
        local_view=local_view,
        fanout=3,
    )

    assert len(selected_high) == len(selected_extreme) == 9


def test_effective_fanout_never_exceeds_available_peers():
    """
    Aunque la prioridad escale el fanout efectivo por encima de la
    cantidad de peers conocidos, select_fanout_peers nunca debe
    devolver más destinatarios de los que existen en la vista local.
    """

    local_view = {"peers_view": peers_subscribed_to("comuna:maipu", 2)}

    selected = select_fanout_peers(
        create_message(topic="comuna:maipu", priority=3),
        local_peer_id="peer-0",
        local_view=local_view,
        fanout=3,
    )

    assert len(selected) == 2


def test_zero_or_negative_priority_falls_back_to_base_fanout():
    """
    Una prioridad inválida no debe reducir el fanout ni silenciar
    el mensaje.
    """

    local_view = {"peers_view": peers_subscribed_to("comuna:maipu", 5)}

    msg = create_message(topic="comuna:maipu", priority=1)
    msg.priority = 0  # simula un dato corrupto post-construcción

    selected = select_fanout_peers(
        msg,
        local_peer_id="peer-0",
        local_view=local_view,
        fanout=3,
    )

    assert len(selected) == 3


# =========================================================
# Prioridad acotada por la política del canal (ChannelPolicy)
# =========================================================


def test_subjective_channel_caps_priority_at_its_own_configured_value():
    """
    subjective tiene priority=1 en config.yaml. Aunque el mensaje
    traiga una prioridad corrupta/extrema, el techo debe ser el de
    su propio canal (1).
    """

    message = create_message(channel="subjective", priority=100)
    local_view = {"peers_view": peers_subscribed_to("santiago-centro", 10)}
    policies = default_channel_policies()

    selected = select_fanout_peers(
        msg=message,
        local_peer_id="peer-0",
        local_view=local_view,
        channel_policies=policies,
    )

    # subjective: fanout base = 2, techo de prioridad = 1 -> sin escalación.
    assert len(selected) == 2


def test_objective_channel_still_allows_escalation_up_to_its_own_priority():
    """
    objective tiene priority=3 en config.yaml, así que sigue
    escalando hasta 3x su propio techo con una prioridad extrema.
    """

    message = create_message(channel="objective", priority=100)
    local_view = {"peers_view": peers_subscribed_to("santiago-centro", 10)}
    policies = default_channel_policies()

    selected = select_fanout_peers(
        msg=message,
        local_peer_id="peer-0",
        local_view=local_view,
        channel_policies=policies,
    )

    # objective: fanout base = 3, techo = 3 -> hasta 9, acotado por los
    # 10 peers disponibles (9 <= 10).
    assert len(selected) == 9