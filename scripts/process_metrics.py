#!/usr/bin/env python3
"""Procesa métricas JSONL crudas y genera figuras + tablas consolidadas."""

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


REQUIRED_FIELDS = ["type", "run_id", "timestamp", "peer_id", "dominio", "comuna", "canal"]


def load_metrics(input_dir: Path, metric_type: str) -> pd.DataFrame:
    records = []
    for f in (input_dir).glob(f"{metric_type}*.jsonl"):
        with open(f, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    return df


def validate_metrics(df: pd.DataFrame, metric_type: str) -> list:
    """Valida métricas según METRICAS.md §5."""
    errors = []
    if df.empty:
        return errors

    # Campos obligatorios
    for field in REQUIRED_FIELDS:
        if field not in df.columns:
            errors.append(f"{metric_type}: falta campo obligatorio '{field}'")

    # Valores numéricos sin NaN en campos críticos
    critical_numeric = {
        "convergence": ["divergencia_max", "divergencia_media", "varianza_inter_peer"],
        "gap": ["brecha_abs", "brecha_rel", "sesgo", "brecha_ema"],
        "robustness": ["msg_dropped", "stale_ratio"],
        "network": ["hops_avg", "fanout_eff", "bw_usage", "ttl_drops"],
    }

    for prefix, fields in critical_numeric.items():
        if metric_type.startswith(prefix):
            for f in fields:
                if f in df.columns and df[f].isna().any():
                    errors.append(f"{metric_type}: campo '{f}' tiene valores NaN")

    # recovery_time_s puede ser NaN para eventos de peer_killed (se llena en peer_recovered)
    if metric_type.startswith("robustness") and "recovery_time_s" in df.columns:
        pass  # Allow NaN for recovery_time_s

    # Rangos
    if "divergencia_max" in df.columns:
        if (df["divergencia_max"] < 0).any():
            errors.append(f"{metric_type}: divergencia_max tiene valores negativos")
    if "brecha_abs" in df.columns:
        if (df["brecha_abs"] < 0).any():
            errors.append(f"{metric_type}: brecha_abs tiene valores negativos")
    if "P_c" in df.columns:
        if (df["P_c"] < 0).any() or (df["P_c"] > 500).any():
            errors.append(f"{metric_type}: P_c fuera de rango [0, 500]")

    return errors


def plot_convergence(df: pd.DataFrame, output_dir: Path, dominio: str):
    if df.empty:
        return
    fig, ax = plt.subplots(figsize=(12, 7))
    for comuna in df["comuna"].unique():
        sub = df[df["comuna"] == comuna].sort_values("timestamp")
        ax.plot(sub["timestamp"], sub["divergencia_max"], label=f"{comuna} (max)", linewidth=1.5)
        ax.plot(sub["timestamp"], sub["divergencia_media"], label=f"{comuna} (media)", linestyle="--", linewidth=1)
    ax.set_xlabel("Tiempo")
    ax.set_ylabel("Divergencia")
    ax.set_title(f"Convergencia canal objetivo — Dominio {dominio}")
    ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / f"convergence_{dominio}.png", dpi=300, bbox_inches="tight")
    plt.close()


def plot_gap(df: pd.DataFrame, output_dir: Path, dominio: str):
    if df.empty:
        return
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    axes = axes.flatten()

    # brecha_abs
    ax = axes[0]
    for comuna in df["comuna"].unique():
        sub = df[df["comuna"] == comuna].sort_values("timestamp")
        ax.plot(sub["timestamp"], sub["brecha_abs"], label=comuna)
    ax.set_xlabel("Tiempo")
    ax.set_ylabel("Brecha |P_c - G_c|")
    ax.set_title(f"Brecha absoluta — Dominio {dominio}")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # brecha_rel
    ax = axes[1]
    for comuna in df["comuna"].unique():
        sub = df[df["comuna"] == comuna].sort_values("timestamp")
        ax.plot(sub["timestamp"], sub["brecha_rel"], label=comuna)
    ax.set_xlabel("Tiempo")
    ax.set_ylabel("Brecha relativa")
    ax.set_title(f"Brecha relativa — Dominio {dominio}")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # sesgo
    ax = axes[2]
    for comuna in df["comuna"].unique():
        sub = df[df["comuna"] == comuna].sort_values("timestamp")
        ax.plot(sub["timestamp"], sub["sesgo"], label=comuna)
    ax.set_xlabel("Tiempo")
    ax.set_ylabel("Sesgo (P_c - G_c)")
    ax.set_title(f"Sesgo — Dominio {dominio}")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # brecha_ema
    ax = axes[3]
    for comuna in df["comuna"].unique():
        sub = df[df["comuna"] == comuna].sort_values("timestamp")
        ax.plot(sub["timestamp"], sub["brecha_ema"], label=comuna)
    ax.set_xlabel("Tiempo")
    ax.set_ylabel("Brecha EMA |M_c - G_c|")
    ax.set_title(f"Brecha EMA — Dominio {dominio}")
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_dir / f"gap_{dominio}.png", dpi=300, bbox_inches="tight")
    plt.close()


def plot_robustness(df: pd.DataFrame, output_dir: Path):
    if df.empty:
        return
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    axes = axes.flatten()

    # recovery_time
    ax = axes[0]
    for event in df["event"].unique():
        sub = df[df["event"] == event].sort_values("timestamp")
        if "recovery_time_s" in sub.columns:
            ax.scatter(sub["timestamp"], sub["recovery_time_s"], label=event, s=50)
    ax.set_xlabel("Tiempo")
    ax.set_ylabel("Recovery time (s)")
    ax.set_title("Tiempo de recuperación")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # msg_dropped
    ax = axes[1]
    for event in df["event"].unique():
        sub = df[df["event"] == event].sort_values("timestamp")
        if "msg_dropped" in sub.columns:
            ax.plot(sub["timestamp"], sub["msg_dropped"], label=event, marker="o")
    ax.set_xlabel("Tiempo")
    ax.set_ylabel("Mensajes perdidos")
    ax.set_title("Mensajes perdidos")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # stale_ratio
    ax = axes[2]
    for peer in df["peer_id"].unique():
        sub = df[df["peer_id"] == peer].sort_values("timestamp")
        if "stale_ratio" in sub.columns:
            ax.plot(sub["timestamp"], sub["stale_ratio"], label=peer)
    ax.set_xlabel("Tiempo")
    ax.set_ylabel("Stale ratio")
    ax.set_title("Proporción peers con datos obsoletos")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # partition_detected
    ax = axes[3]
    if "partition_detected" in df.columns:
        for event in df["event"].unique():
            sub = df[df["event"] == event].sort_values("timestamp")
            ax.scatter(sub["timestamp"], sub["partition_detected"].astype(int), label=event, s=50)
    ax.set_xlabel("Tiempo")
    ax.set_ylabel("Partición detectada (0/1)")
    ax.set_title("Detección de partición")
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_dir / "robustness_partition.png", dpi=300, bbox_inches="tight")
    plt.close()


def plot_comparison_domains(metrics: dict, output_dir: Path):
    """Gráfico comparativo Dominio A vs B."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    axes = axes.flatten()

    # Convergencia: divergencia_max A vs B
    ax = axes[0]
    for dominio in ["A", "B"]:
        df = metrics.get(f"convergence_{dominio}", pd.DataFrame())
        if not df.empty:
            # Promedio cross-comuna y cross-peer por timestamp
            avg = df.groupby("timestamp")["divergencia_max"].mean().reset_index()
            ax.plot(avg["timestamp"], avg["divergencia_max"], label=f"Dominio {dominio}", linewidth=2)
    ax.set_xlabel("Tiempo")
    ax.set_ylabel("Divergencia máxima (promedio)")
    ax.set_title("Convergencia: A vs B")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Brecha: brecha_abs A vs B
    ax = axes[1]
    for dominio in ["A", "B"]:
        df = metrics.get(f"gap_{dominio}", pd.DataFrame())
        if not df.empty:
            avg = df.groupby("timestamp")["brecha_abs"].mean().reset_index()
            ax.plot(avg["timestamp"], avg["brecha_abs"], label=f"Dominio {dominio}", linewidth=2)
    ax.set_xlabel("Tiempo")
    ax.set_ylabel("Brecha absoluta (promedio)")
    ax.set_title("Brecha percepción–realidad: A vs B")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Boxplot convergencia final
    ax = axes[2]
    data = []
    labels = []
    for dominio in ["A", "B"]:
        df = metrics.get(f"convergence_{dominio}", pd.DataFrame())
        if not df.empty:
            last = df.sort_values("timestamp").groupby(["run_id", "comuna", "peer_id"]).last()
            data.append(last["divergencia_max"].values)
            labels.append(f"Dom {dominio}")
    if data:
        ax.boxplot(data, labels=labels)
        ax.set_ylabel("Divergencia máxima final")
        ax.set_title("Distribución divergencia final")
        ax.grid(True, alpha=0.3)

    # Boxplot brecha final
    ax = axes[3]
    data = []
    labels = []
    for dominio in ["A", "B"]:
        df = metrics.get(f"gap_{dominio}", pd.DataFrame())
        if not df.empty:
            last = df.sort_values("timestamp").groupby(["run_id", "comuna", "peer_id"]).last()
            data.append(last["brecha_abs"].values)
            labels.append(f"Dom {dominio}")
    if data:
        ax.boxplot(data, labels=labels)
        ax.set_ylabel("Brecha absoluta final")
        ax.set_title("Distribución brecha final")
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_dir / "comparison_domains.png", dpi=300, bbox_inches="tight")
    plt.close()


def generate_summary(metrics: dict, output_dir: Path, run_id: str, params: dict):
    """Genera summary.json con resumen agregado."""
    summary = {
        "run_id": run_id,
        "parametros": params,
        "dominios": {},
    }

    for dominio in ["A", "B"]:
        df_conv = metrics.get(f"convergence_{dominio}", pd.DataFrame())
        df_gap = metrics.get(f"gap_{dominio}", pd.DataFrame())

        dom_summary = {}

        if not df_conv.empty:
            last = df_conv.sort_values("timestamp").groupby(["comuna", "peer_id"]).last()
            dom_summary["convergencia"] = {
                "divergencia_max_promedio": float(last["divergencia_max"].mean()),
                "divergencia_max_max": float(last["divergencia_max"].max()),
                "divergencia_media_promedio": float(last["divergencia_media"].mean()),
                "varianza_promedio": float(last["varianza_inter_peer"].mean()),
                "n_peers": int(df_conv["peer_id"].nunique()),
                "n_comunas": int(df_conv["comuna"].nunique()),
            }
            # Tiempo de convergencia (primer t donde divergencia_max < 0.01)
            epsilon = 0.01
            conv_times = []
            for (comuna, peer), sub in df_conv.groupby(["comuna", "peer_id"]):
                sub = sub.sort_values("timestamp")
                conv = sub[sub["divergencia_max"] < epsilon]
                if not conv.empty:
                    conv_times.append((conv.iloc[0]["timestamp"] - sub.iloc[0]["timestamp"]).total_seconds())
            if conv_times:
                dom_summary["convergencia"]["tiempo_convergencia_promedio_s"] = float(np.mean(conv_times))

        if not df_gap.empty:
            last = df_gap.sort_values("timestamp").groupby(["comuna", "peer_id"]).last()
            dom_summary["brecha"] = {
                "brecha_abs_promedio": float(last["brecha_abs"].mean()),
                "brecha_abs_max": float(last["brecha_abs"].max()),
                "brecha_rel_promedio": float(last["brecha_rel"].mean()),
                "sesgo_promedio": float(last["sesgo"].mean()),
                "brecha_ema_promedio": float(last["brecha_ema"].mean()),
            }

        summary["dominios"][dominio] = dom_summary

    # Duración total
    all_timestamps = []
    for df in metrics.values():
        if not df.empty and "timestamp" in df.columns:
            all_timestamps.extend(df["timestamp"].dropna().tolist())
    if all_timestamps:
        summary["duracion_total_s"] = float((max(all_timestamps) - min(all_timestamps)).total_seconds())

    with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Directorio raw/ con JSONL")
    parser.add_argument("--output", required=True, help="Directorio de salida para figuras")
    parser.add_argument("--run-id", default="", help="Run ID (para summary)")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Cargar parámetros de config si existe
    config_path = input_dir.parent.parent / "config.yaml"
    params = {}
    if config_path.exists():
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        params = {
            "fanout": config.get("gossip", {}).get("fanout"),
            "timeout": config.get("gossip", {}).get("timeout"),
            "objective_ttl": config.get("pubsub", {}).get("channels", {}).get("objective", {}).get("ttl"),
            "subjective_ttl": config.get("pubsub", {}).get("channels", {}).get("subjective", {}).get("ttl"),
            "alpha": config.get("metrics", {}).get("alpha", 0.8),  # ejemplo
        }

    run_id = args.run_id or input_dir.parent.parent.name

    # Cargar todas las métricas
    metrics = {}
    all_errors = []
    for metric_type in ["convergence_A", "convergence_B", "gap_A", "gap_B", "robustness", "network"]:
        df = load_metrics(input_dir, metric_type)
        metrics[metric_type] = df
        errors = validate_metrics(df, metric_type)
        all_errors.extend(errors)

    if all_errors:
        print(f"[WARN] {len(all_errors)} errores de validación:")
        for e in all_errors[:20]:
            print(f"  - {e}")

    # Generar figuras
    for dominio in ["A", "B"]:
        plot_convergence(metrics[f"convergence_{dominio}"], output_dir, dominio)
        plot_gap(metrics[f"gap_{dominio}"], output_dir, dominio)

    plot_robustness(metrics["robustness"], output_dir)
    plot_comparison_domains(metrics, output_dir)

    # Summary
    generate_summary(metrics, output_dir, run_id, params)

    print(f"[OK] Figuras generadas en {output_dir}")
    print(f"[OK] Summary: {output_dir / 'summary.json'}")


if __name__ == "__main__":
    main()