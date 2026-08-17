from dataclasses import dataclass, field
from typing import Any, Dict
from uuid import uuid4


@dataclass
class Message:
    """
    Mensaje que circula por la capa Pub/Sub de CivicMesh.
    Un mensaje pertenece a un tópico geográfico y a uno de los
    dos canales definidos por el laboratorio:
        - objective
        - subjective
    TTL controla cuántos saltos adicionales puede realizar el mensaje.
    hop_count registra cuántos saltos ha realizado.
    priority permite diferenciar la importancia del mensaje.
    """

    topic: str
    channel: str
    payload: Dict[str, Any]

    timestamp: float

    ttl: int = 5
    priority: int = 1

    source: str = ""

    id: str = field(default_factory=lambda: str(uuid4()))

    hop_count: int = 0

    def __post_init__(self) -> None:
        """Valida que el mensaje tenga una estructura válida."""

        if not self.topic:
            raise ValueError("topic no puede estar vacío")

        if self.channel not in {"objective", "subjective"}:
            raise ValueError(
                "channel debe ser 'objective' o 'subjective'"
            )

        if self.ttl < 0:
            raise ValueError("ttl no puede ser negativo")

        if self.priority < 0:
            raise ValueError("priority no puede ser negativa")

        if self.hop_count < 0:
            raise ValueError("hop_count no puede ser negativo")

    def decrement_ttl(self) -> None:
        """
        Consume un salto del mensaje.
        Cada vez que el mensaje es reenviado hacia otro peer,
        el TTL disminuye en uno y hop_count aumenta en uno.
        """

        if self.ttl > 0:
            self.ttl -= 1

        self.hop_count += 1

    def can_forward(self) -> bool:
        """
        Indica si el mensaje todavía puede ser reenviado.
        Un mensaje con TTL igual a cero no puede continuar
        propagándose por la malla.
        """
        return self.ttl > 0