#!/usr/bin/env bash
#SBATCH --job-name=civicmesh-fe
#SBATCH --partition=GPU
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --time=02:00:00
#SBATCH --output=frontend-%j.out
#SBATCH --error=frontend-%j.err

# ==============================================================================
# CivicMesh — Job 3: Frontend Streamlit (solo CPU del host GPU)
# Requiere: export CIVICMESH_RUN_ID=<job_id_del_job_1>
# ==============================================================================

set -euo pipefail

RUN_ID="${CIVICMESH_RUN_ID:?Error: CIVICMESH_RUN_ID no definido. Usa: export CIVICMESH_RUN_ID=<job_id>}"
CIVICMESH_RUNS="${CIVICMESH_RUNS:-$PWD/runs}"
RUN_DIR="${CIVICMESH_RUNS}/${RUN_ID}"
REPO_DIR="/home/ceph/scassone/repos/civicmesh"

echo "================================================================="
echo "Frontend Streamlit — RUN_ID: ${RUN_ID}"
echo "RUN_DIR: ${RUN_DIR}"
echo "================================================================="

METRICS_DIR="${RUN_DIR}/metrics/raw"

echo "[Frontend] Esperando métricas en ${METRICS_DIR}..."
for i in $(seq 1 30); do
    if [[ -d "${METRICS_DIR}" ]] && ls "${METRICS_DIR}"/*.jsonl &>/dev/null; then
        echo "[Frontend] Métricas encontradas:"
        ls -la "${METRICS_DIR}/"
        break
    fi
    echo "[Frontend] Esperando métricas... (${i}/30)"
    sleep 5
done

export PYTHONPATH="${REPO_DIR}:${REPO_DIR}/CivicMesh"
export PYTHONUNBUFFERED=1

FE_PORT=8501

echo "[Frontend] Iniciando Streamlit en puerto ${FE_PORT}"

~/.local/bin/streamlit run "${REPO_DIR}/frontend/app.py" \
    --server.port "${FE_PORT}" \
    --server.address 0.0.0.0 \
    --server.headless true \
    -- \
    --metrics-dir "${METRICS_DIR}" \
    2>&1 | tee "${RUN_DIR}/logs/frontend.log"
