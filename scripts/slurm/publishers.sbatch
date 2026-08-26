#!/usr/bin/env bash
#SBATCH --job-name=civicmesh-pub
#SBATCH --partition=GPU
#SBATCH --nodes=2
#SBATCH --ntasks=2
#SBATCH --cpus-per-task=2
#SBATCH --time=00:25:00
#SBATCH --output=publisher-%j.out
#SBATCH --error=publisher-%j.err

# ==============================================================================
# CivicMesh — Job 2: Publicadores GPU (solo CPU del host)
# Requiere: export CIVICMESH_RUN_ID=<job_id_del_job_1>
# ==============================================================================

set -euo pipefail

RUN_ID="${CIVICMESH_RUN_ID:?Error: CIVICMESH_RUN_ID no definido. Usa: export CIVICMESH_RUN_ID=<job_id>}"
CIVICMESH_RUNS="${CIVICMESH_RUNS:-$PWD/runs}"
RUN_DIR="${CIVICMESH_RUNS}/${RUN_ID}"
REPO_DIR="/home/ceph/scassone/repos/civicmesh"

echo "================================================================="
echo "Publicadores GPU — RUN_ID: ${RUN_ID}"
echo "RUN_DIR: ${RUN_DIR}"
echo "================================================================="

HOSTFILE="${RUN_DIR}/hostfile.txt"
echo "[Publisher] Esperando hostfile en ${HOSTFILE}..."
for i in $(seq 1 30); do
    if [[ -s "${HOSTFILE}" ]]; then
        echo "[Publisher] Hostfile encontrado:"
        cat "${HOSTFILE}"
        break
    fi
    echo "[Publisher] Esperando... (${i}/30)"
    sleep 2
done

if [[ ! -s "${HOSTFILE}" ]]; then
    echo "[Publisher] ERROR: Hostfile vacío tras 60s. Abortando."
    exit 1
fi

mapfile -t GPU_NODES < <(scontrol show hostnames "${SLURM_JOB_NODELIST:-localhost}")
GPU_NODE_1="${GPU_NODES[0]:-localhost}"
GPU_NODE_2="${GPU_NODES[1]:-localhost}"

CONFIG_FILE="${RUN_DIR}/config.yaml"
CACHE_FILE="${REPO_DIR}/CivicMesh/data/air_quality/sinca_cache.jsonl"
INTERVAL=2.0
METRICS_INTERVAL=5.0

export PYTHONPATH="${REPO_DIR}:${REPO_DIR}/CivicMesh"
export PYTHONUNBUFFERED=1
export CIVICMESH_RUNS="${REPO_DIR}/runs"
export CIVICMESH_RUN_ID="${RUN_ID}"

echo "[Publisher] Air Quality → ${GPU_NODE_1}:9001"
srun --nodes=1 --nodelist="${GPU_NODE_1}" --ntasks=1 \
    python3 "${REPO_DIR}/scripts/run_publisher.py" \
        --domain air_quality \
        --comuna "Las Condes" \
        --host "${GPU_NODE_1}" \
        --port 9001 \
        --hostfile "${HOSTFILE}" \
        --interval "${INTERVAL}" \
        --config "${CONFIG_FILE}" \
        --cache-path "${CACHE_FILE}" \
        --metrics-enabled \
        --metrics-interval "${METRICS_INTERVAL}" \
        --run-id "${RUN_ID}" \
    > "${RUN_DIR}/logs/publisher_air.log" 2>&1 &
PID_AIR=$!

echo "[Publisher] Crimes → ${GPU_NODE_2}:9002"
srun --nodes=1 --nodelist="${GPU_NODE_2}" --ntasks=1 \
    python3 "${REPO_DIR}/scripts/run_publisher.py" \
        --domain crimes \
        --comuna "Santiago" \
        --host "${GPU_NODE_2}" \
        --port 9002 \
        --hostfile "${HOSTFILE}" \
        --interval "${INTERVAL}" \
        --config "${CONFIG_FILE}" \
        --metrics-enabled \
        --metrics-interval "${METRICS_INTERVAL}" \
        --run-id "${RUN_ID}" \
    > "${RUN_DIR}/logs/publisher_crimes.log" 2>&1 &
PID_CRIMES=$!

echo "[Publisher] PIDs: air=${PID_AIR}, crimes=${PID_CRIMES}"
echo "[Publisher] Publicadores ejecutándose. Monitoreando..."

wait
