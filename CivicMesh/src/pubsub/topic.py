from dataclasses import dataclass
from enum import Enum


class TopicLevel(Enum):
    COMUNA = "comuna"
    REGION = "region"


@dataclass(frozen=True)
class GeographicTopic:
    level: TopicLevel
    name: str

    def __post_init__(self):
        if not self.name:
            raise ValueError("El nombre del tópico no puede estar vacío")

    @property
    def id(self) -> str:
        normalized_name = self.name.lower().replace(" ", "_")
        return f"{self.level.value}:{normalized_name}"

    def __str__(self) -> str:
        return self.id