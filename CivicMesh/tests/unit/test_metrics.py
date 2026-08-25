#!/usr/bin/env python3
"""Tests unitarios para agregación y métricas."""

import json
import tempfile
import time
from pathlib import Path

import pytest

from CivicMesh.src.aggregation.state import PeerState, ChannelState, get_global_state
from CivicMesh.src.aggregation.metrics import MetricsWriter, get_metrics_writer, set_metrics_writer


class TestChannelState:
    def test_update_basic(self):
        cs = ChannelState()
        cs.update(10.0, 1000.0, alpha=0.5)
        assert cs.latest_value == 10.0
        assert cs.ema == 10.0
        assert cs.sample_count == 1

        cs.update(20.0, 1001.0, alpha=0.5)
        assert cs.latest_value == 20.0
        assert cs.ema == 15.0  # 0.5*10 + 0.5*20
        assert cs.sample_count == 2

    def test_update_ema_initialization(self):
        cs = ChannelState()
        cs.update(5.0, 1.0, alpha=0.8)
        assert cs.ema == 5.0


class TestPeerState:
    @pytest.mark.asyncio
    async def test_update_and_snapshot(self):
        state = PeerState()
        await state.update("Santiago", "objective", 42.0, 1000.0)
        await state.update("Santiago", "subjective", 0.7, 1000.0)
        await state.update("Providencia", "objective", 15.0, 1001.0)

        snap = await state.get_snapshot()
        assert "Santiago" in snap
        assert "objective" in snap["Santiago"]
        assert snap["Santiago"]["objective"]["latest_value"] == 42.0
        assert snap["Santiago"]["subjective"]["latest_value"] == 0.7
        assert "Providencia" in snap

    @pytest.mark.asyncio
    async def test_get_objective_values(self):
        state = PeerState()
        await state.update("Santiago", "objective", 42.0)
        await state.update("Santiago", "subjective", 0.7)
        await state.update("Providencia", "objective", 15.0)

        obj = await state.get_objective_values()
        assert obj == {"Santiago": 42.0, "Providencia": 15.0}

    @pytest.mark.asyncio
    async def test_get_subjective_values(self):
        state = PeerState()
        await state.update("Santiago", "objective", 42.0)
        await state.update("Santiago", "subjective", 0.7)
        await state.update("Providencia", "subjective", 0.5)

        subj = await state.get_subjective_values()
        assert subj == {"Santiago": 0.7, "Providencia": 0.5}

    def test_clear(self):
        state = PeerState()
        state._state["Santiago"] = {"objective": ChannelState()}
        state.clear()
        assert len(state._state) == 0

    def test_set_context(self):
        state = PeerState()
        state.set_context("peer-1", "run-123", "A")
        assert state.peer_id == "peer-1"
        assert state.run_id == "run-123"
        assert state.dominio == "A"


class TestMetricsWriter:
    def test_write_convergence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = MetricsWriter(run_id="test-run", output_dir=tmpdir)
            writer.write_convergence(
                peer_id="peer-1",
                dominio="A",
                comuna="Santiago",
                timestamp=time.time(),
                v_i=10.0,
                peer_values={"peer-1": 10.0, "peer-2": 12.0, "peer-3": 9.0},
            )
            writer.flush_all()

            # Verificar archivo
            f = Path(tmpdir) / "convergence_A.jsonl"
            assert f.exists()
            with open(f) as fh:
                line = fh.readline()
                record = json.loads(line)

            assert record["type"] == "convergence"
            assert record["run_id"] == "test-run"
            assert record["peer_id"] == "peer-1"
            assert record["dominio"] == "A"
            assert record["comuna"] == "Santiago"
            assert record["canal"] == "objective"
            assert record["v_i"] == 10.0
            assert record["divergencia_max"] == 2.0  # max(|10-10|, |10-12|, |10-9|) = 2
            assert record["n_peers"] == 3

    def test_write_gap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = MetricsWriter(run_id="test-run", output_dir=tmpdir)
            writer.write_gap(
                peer_id="peer-1",
                dominio="B",
                comuna="Las Condes",
                timestamp=time.time(),
                G_c=35.0,
                P_c=42.5,
                M_c=38.2,
            )
            writer.flush_all()

            f = Path(tmpdir) / "gap_B.jsonl"
            with open(f) as fh:
                record = json.loads(fh.readline())

            assert record["type"] == "gap"
            assert record["G_c"] == 35.0
            assert record["P_c"] == 42.5
            assert record["M_c"] == 38.2
            assert record["brecha_abs"] == 7.5
            assert record["brecha_rel"] == pytest.approx(round(7.5 / 35.0, 6))
            assert record["sesgo"] == 7.5
            assert record["brecha_ema"] == 3.2  # |38.2 - 35.0|

    def test_write_robustness(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = MetricsWriter(run_id="test-run", output_dir=tmpdir)
            writer.write_robustness(
                peer_id="peer-1",
                event="peer_killed",
                timestamp=time.time(),
                recovery_time=12.4,
                msg_dropped=15,
                partition_detected=False,
                stale_ratio=0.25,
            )
            writer.flush_all()

            f = Path(tmpdir) / "robustness.jsonl"
            with open(f) as fh:
                record = json.loads(fh.readline())

            assert record["type"] == "robustness"
            assert record["event"] == "peer_killed"
            assert record["recovery_time_s"] == 12.4
            assert record["msg_dropped"] == 15
            assert record["stale_ratio"] == 0.25

    def test_write_network(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = MetricsWriter(run_id="test-run", output_dir=tmpdir)
            writer.write_network(
                peer_id="peer-1",
                timestamp=time.time(),
                hops_avg=2.5,
                fanout_eff=1.8,
                bw_usage=1024.0,
                ttl_drops=3,
            )
            writer.flush_all()

            f = Path(tmpdir) / "network.jsonl"
            with open(f) as fh:
                record = json.loads(fh.readline())

            assert record["type"] == "network"
            assert record["hops_avg"] == 2.5
            assert record["fanout_eff"] == 1.8
            assert record["ttl_drops"] == 3

    def test_mandatory_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = MetricsWriter(run_id="test-run", output_dir=tmpdir)
            writer.write_convergence(
                peer_id="peer-1", dominio="A", comuna="Santiago",
                timestamp=time.time(), v_i=10.0, peer_values={"peer-1": 10.0}
            )
            writer.flush_all()

            with open(Path(tmpdir) / "convergence_A.jsonl") as fh:
                record = json.loads(fh.readline())

            for field in ["type", "run_id", "timestamp", "peer_id", "dominio", "comuna", "canal"]:
                assert field in record, f"Falta campo obligatorio: {field}"


class TestProcessMetrics:
    """Tests para scripts/process_metrics.py usando fixtures sintéticos."""

    def test_load_metrics(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "raw"
            input_dir.mkdir()
            # Escribir JSONL de prueba
            with open(input_dir / "convergence_A.jsonl", "w") as f:
                f.write(json.dumps({
                    "type": "convergence", "run_id": "test", "timestamp": "2026-01-01T00:00:00Z",
                    "peer_id": "p1", "dominio": "A", "comuna": "Santiago", "canal": "objective",
                    "v_i": 10.0, "divergencia_max": 2.0, "divergencia_media": 1.0,
                    "varianza_inter_peer": 0.5, "n_peers": 3
                }) + "\n")

            from scripts.process_metrics import load_metrics
            df = load_metrics(input_dir, "convergence_A")
            assert not df.empty
            assert len(df) == 1
            assert df.iloc[0]["v_i"] == 10.0

    def test_validate_metrics_ok(self):
        from scripts.process_metrics import validate_metrics
        df = pd.DataFrame([{
            "type": "convergence", "run_id": "test", "timestamp": "2026-01-01T00:00:00Z",
            "peer_id": "p1", "dominio": "A", "comuna": "Santiago", "canal": "objective",
            "divergencia_max": 2.0, "divergencia_media": 1.0, "varianza_inter_peer": 0.5,
        }])
        errors = validate_metrics(df, "convergence_A")
        assert len(errors) == 0

    def test_validate_metrics_negative_divergence(self):
        from scripts.process_metrics import validate_metrics
        df = pd.DataFrame([{
            "type": "convergence", "run_id": "test", "timestamp": "2026-01-01T00:00:00Z",
            "peer_id": "p1", "dominio": "A", "comuna": "Santiago", "canal": "objective",
            "divergencia_max": -1.0,
        }])
        errors = validate_metrics(df, "convergence_A")
        assert any("negativos" in e for e in errors)


import pandas as pd


if __name__ == "__main__":
    pytest.main([__file__, "-v"])