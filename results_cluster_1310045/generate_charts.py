#!/usr/bin/env python3
"""Genera gráficos estáticos desde métricas JSONL de CivicMesh."""

import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

METRICS_DIR = Path(__file__).parent / "metrics" / "raw"
OUT_DIR = Path(__file__).parent / "figures"
OUT_DIR.mkdir(exist_ok=True)


def load_jsonl(name):
    fp = METRICS_DIR / name
    if not fp.exists():
        return pd.DataFrame()
    rows = []
    with open(fp) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def plot_gap(df, dominio, label):
    if df.empty:
        print(f"  [SKIP] {label}: sin datos")
        return
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    fig.suptitle(f"Brecha Percepción–Realidad — Dominio {dominio}", fontsize=14)

    for comuna in df["comuna"].unique():
        sub = df[df["comuna"] == comuna]
        for pid in sub["peer_id"].unique():
            s = sub[sub["peer_id"] == pid].sort_values("timestamp")
            tag = f"{comuna}" if len(sub["peer_id"].unique()) == 1 else f"{comuna}/{pid}"
            axes[0].plot(s["timestamp"], s["brecha_abs"], label=tag, linewidth=0.8)
            axes[1].plot(s["timestamp"], s["sesgo"], label=tag, linewidth=0.8)
            axes[2].plot(s["timestamp"], s["brecha_ema"], label=tag, linewidth=0.8)

    axes[0].set_ylabel("|P_c - G_c|")
    axes[0].set_title("Brecha absoluta")
    axes[0].legend(fontsize=6, ncol=2)
    axes[1].set_ylabel("P_c - G_c")
    axes[1].set_title("Sesgo")
    axes[1].legend(fontsize=6, ncol=2)
    axes[2].set_ylabel("|M_c - G_c|")
    axes[2].set_title("Brecha EMA")
    axes[2].legend(fontsize=6, ncol=2)
    axes[2].set_xlabel("Tiempo")
    for a in axes:
        a.grid(True, alpha=0.3)
    fig.tight_layout()
    out = OUT_DIR / f"gap_{dominio.lower()}.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  [OK] {out}")


def plot_convergence(df, dominio):
    if df.empty:
        print(f"  [SKIP] convergence_{dominio}: sin datos")
        return
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    fig.suptitle(f"Convergencia entre Peers — Dominio {dominio}", fontsize=14)

    for comuna in df["comuna"].unique():
        sub = df[df["comuna"] == comuna].sort_values("timestamp")
        axes[0].plot(sub["timestamp"], sub["divergencia_max"], label=f"{comuna} (max)", linewidth=0.8)
        axes[0].plot(sub["timestamp"], sub["divergencia_media"], label=f"{comuna} (media)", linewidth=0.8, linestyle="--")
        axes[1].plot(sub["timestamp"], sub["varianza_inter_peer"], label=comuna, linewidth=0.8)

    axes[0].set_ylabel("Divergencia")
    axes[0].set_title("Divergencia cross-peer (max y media)")
    axes[0].legend(fontsize=6, ncol=2)
    axes[1].set_ylabel("Varianza")
    axes[1].set_title("Varianza inter-peer")
    axes[1].legend(fontsize=6, ncol=2)
    axes[1].set_xlabel("Tiempo")
    for a in axes:
        a.grid(True, alpha=0.3)
    fig.tight_layout()
    out = OUT_DIR / f"convergence_{dominio.lower()}.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  [OK] {out}")


def plot_topic_status():
    conv_a = load_jsonl("convergence_A.jsonl")
    conv_b = load_jsonl("convergence_B.jsonl")
    gap_a = load_jsonl("gap_A.jsonl")
    gap_b = load_jsonl("gap_B.jsonl")

    if conv_a.empty and conv_b.empty:
        print("  [SKIP] topic_status: sin datos de convergencia")
        return

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle("Estado por Tópico × Canal", fontsize=14)

    for idx, (df, dom, chan) in enumerate([
        (conv_a, "A", "objetivo"), (conv_b, "B", "objetivo"),
    ]):
        ax = axes[0][idx]
        if df.empty:
            ax.set_title(f"Dominio {dom} — {chan} (sin datos)")
            continue
        latest = df.sort_values("timestamp").groupby(["comuna", "peer_id"]).last().reset_index()
        pivot = latest.pivot_table(index="comuna", columns="peer_id", values="v_i", aggfunc="last")
        pivot.plot(kind="bar", ax=ax, width=0.8)
        ax.set_title(f"Dominio {dom} — Canal {chan}")
        ax.set_ylabel("Valor")
        ax.tick_params(axis="x", rotation=45)

    for idx, (df, dom, chan) in enumerate([
        (gap_a, "A", "subjetivo"), (gap_b, "B", "subjetivo"),
    ]):
        ax = axes[1][idx]
        if df.empty:
            ax.set_title(f"Dominio {dom} — {chan} (sin datos)")
            continue
        latest = df.sort_values("timestamp").groupby(["comuna", "peer_id"]).last().reset_index()
        pivot = latest.pivot_table(index="comuna", columns="peer_id", values="P_c", aggfunc="last")
        pivot.plot(kind="bar", ax=ax, width=0.8)
        ax.set_title(f"Dominio {dom} — Canal {chan}")
        ax.set_ylabel("P_c")
        ax.tick_params(axis="x", rotation=45)

    fig.tight_layout()
    out = OUT_DIR / "topic_status.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  [OK] {out}")


if __name__ == "__main__":
    print("Generando gráficos desde métricas...\n")

    gap_a = load_jsonl("gap_A.jsonl")
    gap_b = load_jsonl("gap_B.jsonl")
    conv_a = load_jsonl("convergence_A.jsonl")
    conv_b = load_jsonl("convergence_B.jsonl")

    print("1. Brecha percepción–realidad:")
    plot_gap(gap_a, "A", "gap_A")
    plot_gap(gap_b, "B", "gap_B")

    print("\n2. Convergencia:")
    plot_convergence(conv_a, "A")
    plot_convergence(conv_b, "B")

    print("\n3. Estado tópico×canal:")
    plot_topic_status()

    print(f"\nGráficos guardados en: {OUT_DIR}")
