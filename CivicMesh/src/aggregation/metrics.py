import json
import os
import time
from pathlib import Path
from typing import Dict, Optional


class MetricsWriter:
    def __init__(
        self,
        run_id: Optional[str] = None,
        output_dir: Optional[str] = None,
        flush_interval: int = 3,
    ):
        self.run_id = run_id or os.environ.get("CIVICMESH_RUN_ID") or f"local-{int(time.time())}"
        self.output_dir = Path(output_dir) if output_dir else Path(os.environ.get("CIVICMESH_RUNS", "./runs")) / self.run_id / "metrics" / "raw"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.flush_interval = flush_interval
        self._counters: Dict[str, int] = {}

        self._files = {
            "convergence_A": None,
            "convergence_B": None,
            "gap_A": None,
            "gap_B": None,
            "robustness": None,
            "network": None,
        }

    def _get_file(self, metric_type: str):
        if self._files[metric_type] is None:
            self._files[metric_type] = (self.output_dir / f"{metric_type}.jsonl").open("a", encoding="utf-8")
        return self._files[metric_type]

    def _write(self, metric_type: str, record: dict):
        f = self._get_file(metric_type)
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._counters[metric_type] = self._counters.get(metric_type, 0) + 1
        if self._counters[metric_type] % self.flush_interval == 0:
            f.flush()

    def _base_record(self, peer_id: str, dominio: str, comuna: str, canal: str, timestamp: Optional[float] = None, type_: str = "") -> dict:
        return {
            "type": type_,
            "run_id": self.run_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp or time.time())),
            "peer_id": peer_id,
            "dominio": dominio,
            "comuna": comuna,
            "canal": canal,
        }

    def write_convergence(
        self,
        peer_id: str,
        dominio: str,
        comuna: str,
        timestamp: float,
        v_i: float,
        peer_values: Dict[str, float],
    ):
        if not peer_values:
            return
        values = list(peer_values.values())
        n = len(values)
        divergences = [abs(v_i - v) for v in values]
        divergencia_max = max(divergences)
        divergencia_media = sum(divergences) / n
        varianza = sum((v - (sum(values)/n))**2 for v in values) / n if n > 1 else 0.0

        record = self._base_record(peer_id, dominio, comuna, "objective", timestamp, "convergence")
        record.update({
            "v_i": v_i,
            "divergencia_max": round(divergencia_max, 6),
            "divergencia_media": round(divergencia_media, 6),
            "varianza_inter_peer": round(varianza, 6),
            "n_peers": n,
        })
        self._write(f"convergence_{dominio}", record)

    def write_gap(
        self,
        peer_id: str,
        dominio: str,
        comuna: str,
        timestamp: float,
        G_c: float,
        P_c: float,
        M_c: float,
    ):
        brecha_abs = abs(P_c - G_c)
        brecha_rel = brecha_abs / G_c if G_c > 0 else 0.0
        sesgo = P_c - G_c
        brecha_ema = abs(M_c - G_c)

        record = self._base_record(peer_id, dominio, comuna, "subjective", timestamp, "gap")
        record.update({
            "G_c": G_c,
            "P_c": P_c,
            "M_c": M_c,
            "brecha_abs": round(brecha_abs, 6),
            "brecha_rel": round(brecha_rel, 6),
            "sesgo": round(sesgo, 6),
            "brecha_ema": round(brecha_ema, 6),
        })
        self._write(f"gap_{dominio}", record)

    def write_robustness(
        self,
        peer_id: str,
        event: str,
        timestamp: float,
        recovery_time: Optional[float] = None,
        msg_dropped: int = 0,
        partition_detected: bool = False,
        stale_ratio: float = 0.0,
        **extra,
    ):
        record = self._base_record(peer_id, "unknown", "unknown", "unknown", timestamp, "robustness")
        record.update({
            "event": event,
            "recovery_time_s": recovery_time,
            "msg_dropped": msg_dropped,
            "partition_detected": partition_detected,
            "stale_ratio": round(stale_ratio, 4),
        })
        record.update(extra)
        self._write("robustness", record)

    def write_network(
        self,
        peer_id: str,
        timestamp: float,
        hops_avg: Optional[float] = None,
        fanout_eff: Optional[float] = None,
        bw_usage: Optional[float] = None,
        ttl_drops: int = 0,
        **extra,
    ):
        record = self._base_record(peer_id, "unknown", "unknown", "unknown", timestamp, "network")
        record.update({
            "hops_avg": hops_avg,
            "fanout_eff": fanout_eff,
            "bw_usage": bw_usage,
            "ttl_drops": ttl_drops,
        })
        record.update(extra)
        self._write("network", record)

    def flush_all(self):
        for f in self._files.values():
            if f:
                f.flush()

    def close(self):
        for f in self._files.values():
            if f:
                f.close()
        self._files = {k: None for k in self._files}


_global_writer: Optional[MetricsWriter] = None


def get_metrics_writer(
    run_id: Optional[str] = None,
    output_dir: Optional[str] = None,
    flush_interval: int = 3,
) -> MetricsWriter:
    global _global_writer
    if _global_writer is None:
        _global_writer = MetricsWriter(run_id, output_dir, flush_interval)
    return _global_writer


def set_metrics_writer(writer: MetricsWriter):
    global _global_writer
    _global_writer = writer