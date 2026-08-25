from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import yaml


ChannelType = Literal["objective", "subjective"]


@dataclass(frozen=True)
class ChannelPolicy:
    """
    Política de forwarding de un canal Pub/Sub.

    Los valores de TTL, prioridad y fanout se obtienen
    desde config/config.yaml.
    """

    channel: ChannelType
    ttl: int
    priority: int
    fanout: int

    def __post_init__(self) -> None:
        if self.channel not in {"objective", "subjective"}:
            raise ValueError(
                "channel debe ser 'objective' o 'subjective'"
            )

        if self.ttl < 0:
            raise ValueError(
                "ttl no puede ser negativo"
            )

        if self.priority < 0:
            raise ValueError(
                "priority no puede ser negativa"
            )

        if self.fanout < 0:
            raise ValueError(
                "fanout no puede ser negativo"
            )


@dataclass(frozen=True)
class ChannelPolicies:
    """
    Políticas de propagación de los dos canales de CivicMesh.
    """

    objective: ChannelPolicy
    subjective: ChannelPolicy

    def __post_init__(self) -> None:
        if self.objective.channel != "objective":
            raise ValueError(
                "objective debe utilizar el canal 'objective'"
            )

        if self.subjective.channel != "subjective":
            raise ValueError(
                "subjective debe utilizar el canal 'subjective'"
            )

    def get(self, channel: ChannelType) -> ChannelPolicy:
        """
        Obtiene la política correspondiente al canal.
        """

        if channel == "objective":
            return self.objective

        if channel == "subjective":
            return self.subjective

        raise ValueError(
            "channel debe ser 'objective' o 'subjective'"
        )


def load_channel_policies(
    config_path: Optional[str | Path] = None,
) -> ChannelPolicies:
    """
    Carga las políticas de los canales desde config/config.yaml.

    La configuración esperada es:

        pubsub:
          channels:
            objective:
              ttl: 5
              priority: 3
              fanout: 3

            subjective:
              ttl: 3
              priority: 1
              fanout: 2

    Parameters
    ----------
    config_path:
        Ruta opcional al archivo de configuración.

        Si no se proporciona, se utiliza automáticamente:

            <proyecto>/config/config.yaml
    """

    if config_path is None:
        project_root = Path(__file__).resolve().parents[2]
        config_path = project_root / "config" / "config.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(
            f"No se encontró el archivo de configuración: {config_path}"
        )

    with config_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        config = yaml.safe_load(file)

    if not isinstance(config, dict):
        raise ValueError(
            "config.yaml debe contener un objeto YAML válido"
        )

    pubsub = config.get("pubsub")

    if not isinstance(pubsub, dict):
        raise ValueError(
            "Falta la sección 'pubsub' en config.yaml"
        )

    channels = pubsub.get("channels")

    if not isinstance(channels, dict):
        raise ValueError(
            "Falta la sección 'pubsub.channels' en config.yaml"
        )

    objective_config = channels.get("objective")
    subjective_config = channels.get("subjective")

    if not isinstance(objective_config, dict):
        raise ValueError(
            "Falta la configuración del canal 'objective'"
        )

    if not isinstance(subjective_config, dict):
        raise ValueError(
            "Falta la configuración del canal 'subjective'"
        )

    objective = ChannelPolicy(
        channel="objective",
        ttl=objective_config["ttl"],
        priority=objective_config["priority"],
        fanout=objective_config["fanout"],
    )

    subjective = ChannelPolicy(
        channel="subjective",
        ttl=subjective_config["ttl"],
        priority=subjective_config["priority"],
        fanout=subjective_config["fanout"],
    )

    return ChannelPolicies(
        objective=objective,
        subjective=subjective,
    )


def default_channel_policies() -> ChannelPolicies:
    """
    Compatibilidad con el código existente.

    Aunque conserva el nombre de la función, los valores
    YA NO están hardcodeados.

    La configuración real se obtiene desde config/config.yaml.
    """

    return load_channel_policies()