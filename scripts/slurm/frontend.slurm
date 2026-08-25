#!/usr/bin/env bash
#SBATCH --job-name=civicmesh-frontend
#SBATCH --partition=GPU
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --time=01:00:00
#SBATCH --output=%x-%j.out
#SBATCH --error=%x-%j.err
# Nota: --gres=gpu:A30:0 (solo CPU del host)

# frontend.slurm — Levanta Streamlit frontend en nodo GPU (solo CPU)

set -euo pipefail

source "$(dirname "$0")/bootstrap.sh"

METRICS_DIR="${RUN_DIR}/metrics"

echo "[Frontend] Iniciando Streamlit en ${NODES[0]}"
echo "[Frontend] Métricas: ${METRICS_DIR}"
echo "[Frontend] RUN_ID=${CIVICMESH_RUN_ID}"

export PYTHONPATH=".:CivicMesh"
export PYTHONUNBUFFERED=1

cd "$(dirname "$0")/../.."

# Streamlit en puerto 8501
streamlit run frontend/app.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true \
    -- \
    --metrics-dir "${METRICS_DIR}" \
    2>&1 | tee "${RUN_DIR}/logs/frontend.log"