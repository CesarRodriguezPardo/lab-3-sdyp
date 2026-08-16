from dataclasses import dataclass
from typing import Iterable

from .topic import GeographicTopic


VALID_CHANNELS = {"objective", "subjective"}


@dataclass(frozen=True)
class Subscription:
    """
    Representa una suscripción a un tópico geográfico y un canal.
    """

    topic: GeographicTopic
    channel: str

    def __post_init__(self) -> None:
        if self.channel not in VALID_CHANNELS:
            raise ValueError(
                f"Canal inválido: {self.channel}. "
                f"Debe ser uno de {VALID_CHANNELS}."
            )


class SubscriptionManager:
    """
    Administra las suscripciones de un peer.

    Un peer puede estar suscrito a múltiples tópicos geográficos
    y a uno o ambos canales de cada tópico.
    """

    def __init__(self) -> None:
        self._subscriptions: set[Subscription] = set()

    def subscribe(
        self,
        topic: GeographicTopic,
        channel: str,
    ) -> Subscription:
        """
        Suscribe el peer a un tópico y canal.

        Si la suscripción ya existe, no se duplica.
        """
        subscription = Subscription(
            topic=topic,
            channel=channel,
        )

        self._subscriptions.add(subscription)

        return subscription

    def unsubscribe(
        self,
        topic: GeographicTopic,
        channel: str,
    ) -> bool:
        """
        Elimina una suscripción.

        Retorna True si existía y fue eliminada.
        Retorna False si no existía.
        """
        subscription = Subscription(
            topic=topic,
            channel=channel,
        )

        if subscription in self._subscriptions:
            self._subscriptions.remove(subscription)
            return True

        return False

    def is_subscribed(
        self,
        topic: GeographicTopic,
        channel: str,
    ) -> bool:
        """
        Indica si el peer está suscrito al tópico y canal indicados.
        """
        subscription = Subscription(
            topic=topic,
            channel=channel,
        )

        return subscription in self._subscriptions

    def subscriptions(self) -> set[Subscription]:
        """
        Retorna una copia de las suscripciones actuales.
        """
        return set(self._subscriptions)

    def clear(self) -> None:
        """
        Elimina todas las suscripciones.
        """
        self._subscriptions.clear()

    def subscribe_to_topic(
        self,
        topic: GeographicTopic,
        channels: Iterable[str] = ("objective", "subjective"),
    ) -> None:
        """
        Suscribe el peer a uno o ambos canales de un tópico.
        """
        for channel in channels:
            self.subscribe(topic, channel)

    def subscribed_topics(self) -> set[GeographicTopic]:
        """
        Retorna los tópicos geográficos a los que está suscrito
        el peer.
        """
        return {
            subscription.topic
            for subscription in self._subscriptions
        }