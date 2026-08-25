import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class ChannelState:
    latest_value: Optional[float] = None
    ema: Optional[float] = None
    sample_count: int = 0
    last_ts: Optional[float] = None
    values_history: list = field(default_factory=list)

    def update(self, value: float, ts: float, alpha: float = 0.8):
        self.latest_value = value
        self.sample_count += 1
        self.last_ts = ts
        self.values_history.append((ts, value))
        if self.ema is None:
            self.ema = value
        else:
            self.ema = alpha * self.ema + (1.0 - alpha) * value
        if len(self.values_history) > 1000:
            self.values_history = self.values_history[-500:]


class PeerState:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._state: Dict[str, Dict[str, ChannelState]] = {}
        self.peer_id: Optional[str] = None
        self.run_id: Optional[str] = None
        self.dominio: Optional[str] = None

    def set_context(self, peer_id: str, run_id: str, dominio: str):
        self.peer_id = peer_id
        self.run_id = run_id
        self.dominio = dominio

    def _get_channel_state(self, comuna: str, canal: str) -> ChannelState:
        if comuna not in self._state:
            self._state[comuna] = {}
        if canal not in self._state[comuna]:
            self._state[comuna][canal] = ChannelState()
        return self._state[comuna][canal]

    async def update(self, comuna: str, canal: str, value: float, ts: Optional[float] = None, alpha: float = 0.8):
        async with self._lock:
            cs = self._get_channel_state(comuna, canal)
            cs.update(value, ts or time.time(), alpha)

    async def get_snapshot(self) -> Dict:
        async with self._lock:
            snapshot = {}
            for comuna, canals in self._state.items():
                snapshot[comuna] = {}
                for canal, cs in canals.items():
                    snapshot[comuna][canal] = {
                        "latest_value": cs.latest_value,
                        "ema": cs.ema,
                        "sample_count": cs.sample_count,
                        "last_ts": cs.last_ts,
                    }
            return snapshot

    async def get_objective_values(self) -> Dict[str, float]:
        async with self._lock:
            return {
                comuna: cs.latest_value
                for comuna, canals in self._state.items()
                if "objective" in canals
                and (cs := canals["objective"]).latest_value is not None
            }

    async def get_subjective_values(self) -> Dict[str, float]:
        async with self._lock:
            return {
                comuna: cs.latest_value
                for comuna, canals in self._state.items()
                if "subjective" in canals
                and (cs := canals["subjective"]).latest_value is not None
            }

    def clear(self):
        self._state.clear()


_global_state = PeerState()


def get_global_state() -> PeerState:
    return _global_state