#!/usr/bin/env python3
"""CivicMesh Frontend — Streamlit Dashboard.

Lee métricas desde $CIVICMESH_RUNS/<run_id>/metrics/ y muestra:
1. Estado por tópico × canal (objetivo vs subjetivo)
2. Brecha percepción–realidad por comuna
3. Convergencia entre peers (canal objetivo)
"""

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh


def parse_args():
    parser = argparse.ArgumentParser(description="CivicMesh Frontend")
    parser.add_argument("--metrics-dir", type=str, default="",
                        help="Directorio de métricas (ej. /app/runs/local-test/metrics)")
    parser.add_argument("--run-id", type=str, default="",
                        help="Run ID específico (default: el más reciente)")
    return parser.parse_args()


def find_metrics_dirs(base_dir: Path) -> list:
    """Encuentra todos los directorios de métricas válidos."""
    dirs = []
    for run_dir in base_dir.iterdir():
        if run_dir.is_dir():
            metrics_raw = run_dir / "metrics" / "raw"
            if metrics_raw.exists() and any(metrics_raw.glob("*.jsonl")):
                dirs.append((run_dir.name, metrics_raw))
    return sorted(dirs, key=lambda x: x[0], reverse=True)


def load_metrics(metrics_dir: Path) -> dict:
    """Carga todos los archivos JSONL de métricas."""
    data = {
        "convergence_A": [],
        "convergence_B": [],
        "gap_A": [],
        "gap_B": [],
        "robustness": [],
        "network": [],
    }
    for metric_type in data.keys():
        for f in metrics_dir.glob(f"{metric_type}*.jsonl"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            data[metric_type].append(json.loads(line))
            except Exception:
                pass
    
    result = {}
    for k, v in data.items():
        if v:
            df = pd.DataFrame(v)
            # Convert timestamp to datetime
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
            result[k] = df
        else:
            result[k] = pd.DataFrame()
    return result


def get_latest_values(df: pd.DataFrame, value_col: str, group_cols: list) -> pd.DataFrame:
    """Obtiene el último valor por grupo."""
    if df.empty:
        return pd.DataFrame()
    df = df.sort_values("timestamp")
    return df.groupby(group_cols, as_index=False).last()


def render_topic_channel_status(metrics: dict):
    """Tab 1: Estado por tópico × canal."""
    st.header("Estado por Tópico × Canal")

    cols = st.columns(2)

    with cols[0]:
        st.subheader("Canal Objetivo")
        for dominio in ["A", "B"]:
            df = metrics.get(f"convergence_{dominio}", pd.DataFrame())
            if not df.empty:
                latest = get_latest_values(df, "v_i", ["run_id", "dominio", "comuna", "peer_id"])
                if not latest.empty:
                    st.write(f"**Dominio {dominio}**")
                    pivot = latest.pivot_table(
                        index="comuna",
                        columns="peer_id",
                        values="v_i",
                        aggfunc="last"
                    )
                    st.dataframe(pivot, use_container_width=True)

    with cols[1]:
        st.subheader("Canal Subjetivo")
        for dominio in ["A", "B"]:
            df = metrics.get(f"gap_{dominio}", pd.DataFrame())
            if not df.empty:
                latest = get_latest_values(df, "P_c", ["run_id", "dominio", "comuna", "peer_id"])
                if not latest.empty:
                    st.write(f"**Dominio {dominio}**")
                    pivot = latest.pivot_table(
                        index="comuna",
                        columns="peer_id",
                        values="P_c",
                        aggfunc="last"
                    )
                    st.dataframe(pivot, use_container_width=True)


def render_gap(metrics: dict):
    """Tab 2: Brecha percepción–realidad."""
    st.header("Brecha Percepción–Realidad")

    for dominio in ["A", "B"]:
        df = metrics.get(f"gap_{dominio}", pd.DataFrame())
        if df.empty:
            st.info(f"Dominio {dominio}: sin datos de brecha")
            continue

        st.subheader(f"Dominio {dominio}")

        # Serie temporal de brecha_abs por comuna
        fig = px.line(
            df,
            x="timestamp",
            y="brecha_abs",
            color="comuna",
            line_group="peer_id",
            title=f"Brecha absoluta |P_c - G_c| — Dominio {dominio}",
            labels={"brecha_abs": "Brecha absoluta", "timestamp": "Tiempo"},
        )
        st.plotly_chart(fig, use_container_width=True)

        # Sesgo
        fig2 = px.line(
            df,
            x="timestamp",
            y="sesgo",
            color="comuna",
            line_group="peer_id",
            title=f"Sesgo (P_c - G_c) — Dominio {dominio}",
            labels={"sesgo": "Sesgo", "timestamp": "Tiempo"},
        )
        st.plotly_chart(fig2, use_container_width=True)

        # Brecha EMA
        fig3 = px.line(
            df,
            x="timestamp",
            y="brecha_ema",
            color="comuna",
            line_group="peer_id",
            title=f"Brecha EMA |M_c - G_c| — Dominio {dominio}",
            labels={"brecha_ema": "Brecha EMA", "timestamp": "Tiempo"},
        )
        st.plotly_chart(fig3, use_container_width=True)

        # Tabla resumen último valor
        latest = get_latest_values(df, "brecha_abs", ["run_id", "dominio", "comuna", "peer_id"])
        if not latest.empty:
            st.write("**Última brecha por comuna/peer:**")
            st.dataframe(
                latest[["comuna", "peer_id", "G_c", "P_c", "M_c", "brecha_abs", "brecha_rel", "sesgo"]],
                use_container_width=True
            )


def render_convergence(metrics: dict):
    """Tab 3: Convergencia entre peers."""
    st.header("Convergencia entre Peers (Canal Objetivo)")

    for dominio in ["A", "B"]:
        df = metrics.get(f"convergence_{dominio}", pd.DataFrame())
        if df.empty:
            st.info(f"Dominio {dominio}: sin datos de convergencia")
            continue

        st.subheader(f"Dominio {dominio}")

        # Divergencia max y media vs tiempo
        fig = go.Figure()
        for comuna in df["comuna"].unique():
            sub = df[df["comuna"] == comuna].sort_values("timestamp")
            fig.add_trace(go.Scatter(
                x=sub["timestamp"],
                y=sub["divergencia_max"],
                name=f"{comuna} (max)",
                mode="lines",
            ))
            fig.add_trace(go.Scatter(
                x=sub["timestamp"],
                y=sub["divergencia_media"],
                name=f"{comuna} (media)",
                mode="lines",
                line=dict(dash="dot"),
            ))

        fig.update_layout(
            title=f"Divergencia cross-peer — Dominio {dominio}",
            xaxis_title="Tiempo",
            yaxis_title="Divergencia",
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Varianza
        fig2 = px.line(
            df,
            x="timestamp",
            y="varianza_inter_peer",
            color="comuna",
            title=f"Varianza inter-peer — Dominio {dominio}",
            labels={"varianza_inter_peer": "Varianza", "timestamp": "Tiempo"},
        )
        st.plotly_chart(fig2, use_container_width=True)

        # Tiempo de convergencia (estimado: primer punto donde divergencia_max < epsilon)
        epsilon = 0.01
        conv_times = []
        for (run_id, dominio_, comuna), sub in df.groupby(["run_id", "dominio", "comuna"]):
            sub = sub.sort_values("timestamp")
            converged = sub[sub["divergencia_max"] < epsilon]
            if not converged.empty:
                first_conv = converged.iloc[0]["timestamp"]
                conv_times.append({"comuna": comuna, "tiempo_convergencia": first_conv})

        if conv_times:
            conv_df = pd.DataFrame(conv_times)
            st.write("**Tiempo de convergencia estimado (divergencia_max < 0.01):**")
            st.dataframe(conv_df, use_container_width=True)


def render_robustness(metrics: dict):
    """Tab 4: Robustez (si hay datos)."""
    df = metrics.get("robustness", pd.DataFrame())
    if df.empty:
        return

    st.header("Robustez — Caída / Partición")

    # Determinar columnas de hover disponibles
    hover_cols = ["peer_id", "msg_dropped", "stale_ratio", "partition_detected"]
    if "dead_peer" in df.columns:
        hover_cols.append("dead_peer")
    if "recovered_peer" in df.columns:
        hover_cols.append("recovered_peer")

    fig = px.scatter(
        df,
        x="timestamp",
        y="recovery_time_s",
        color="event",
        hover_data=hover_cols,
        title="Tiempo de recuperación tras eventos",
        labels={"recovery_time_s": "Recovery time (s)", "timestamp": "Tiempo"},
    )
    st.plotly_chart(fig, use_container_width=True)

    fig2 = px.line(
        df,
        x="timestamp",
        y="stale_ratio",
        color="peer_id",
        title="Proporción de peers con datos obsoletos",
        labels={"stale_ratio": "Stale ratio", "timestamp": "Tiempo"},
    )
    st.plotly_chart(fig2, use_container_width=True)


def main():
    args = parse_args()

    st.set_page_config(
        page_title="CivicMesh Dashboard",
        page_icon="📊",
        layout="wide",
    )

    st.title("CivicMesh — Dashboard de Métricas")

    # Resolver directorio de métricas
    if args.metrics_dir:
        metrics_dir = Path(args.metrics_dir)
        # Si el directorio no tiene archivos JSONL directamente, buscar en subdirectorio raw/
        if not any(metrics_dir.glob("*.jsonl")):
            raw_dir = metrics_dir / "raw"
            if raw_dir.exists() and any(raw_dir.glob("*.jsonl")):
                metrics_dir = raw_dir
    else:
        civicmesh_runs = os.environ.get("CIVICMESH_RUNS", "./runs")
        base_dir = Path(civicmesh_runs)
        if not base_dir.exists():
            st.error(f"Directorio base no encontrado: {base_dir}")
            st.stop()
        dirs = find_metrics_dirs(base_dir)
        if not dirs:
            st.error(f"No se encontraron corridas con métricas en {base_dir}")
            st.stop()

        # Selector de run_id
        run_names = [d[0] for d in dirs]
        if args.run_id:
            if args.run_id in run_names:
                selected = args.run_id
            else:
                st.error(f"Run ID {args.run_id} no encontrado. Disponibles: {run_names}")
                st.stop()
        else:
            selected = st.sidebar.selectbox("Run ID", run_names, index=0)

        metrics_dir = dict(dirs)[selected]

    st.sidebar.write(f"**Run ID:** {metrics_dir.parent.parent.name}")
    st.sidebar.write(f"**Métricas:** {metrics_dir}")

    # Auto-refresh
    refresh_interval = st.sidebar.slider("Auto-refresh (seg)", 0, 60, 5)
    if refresh_interval > 0:
        st.sidebar.write(f"Refrescando cada {refresh_interval}s...")
        st_autorefresh(interval=refresh_interval * 1000, key="metrics_refresh")

    # Cargar métricas
    with st.spinner("Cargando métricas..."):
        metrics = load_metrics(metrics_dir)

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 Estado Tópico×Canal",
        "📉 Brecha Percepción–Realidad",
        "📈 Convergencia",
        "🛡️ Robustez",
    ])

    with tab1:
        render_topic_channel_status(metrics)

    with tab2:
        render_gap(metrics)

    with tab3:
        render_convergence(metrics)

    with tab4:
        render_robustness(metrics)


if __name__ == "__main__":
    main()