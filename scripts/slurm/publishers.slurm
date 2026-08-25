#!/usr/bin/env bash
#SBATCH --job-name=civicmesh-publishers
#SBATCH --partition=GPU
#SBATCH --nodes=2
#SBATCH --ntasks=2
#SBATCH --cpus-per-task=2
#SBATCH --time=01:00:00
#SBATCH --output=%x-%j.out
#SBATCH --error=%x-%j.err
# Nota: --gres=gpu:A30:0 (solo CPU del host, sin CUDA)

# publishers.slurm — Job array para publicadores en nodos GPU (solo CPU del host)
# Task 0: air_quality (Dominio B, Las Condes)
# Task 1: crimes (Dominio A, Santiago)

set -euo pipefail

source "$(dirname "$0")/bootstrap.sh"

CONFIG_FILE="${RUN_DIR}/config.yaml"
HOSTFILE="${RUN_DIR}/hostfile.txt"
INTERVAL=2.0
METRICS_INTERVAL=5.0
CACHE_FILE="CivicMesh/data/air_quality/sinca_cache.jsonl"

# Task 0: air_quality, Task 1: crimes
if [[ ${SLURM_PROCID} -eq 0 ]]; then
    DOMAIN="air_quality"
    COMUNA="Las Condes"
    DOMINIO_LETRA="B"
    PORT=9001
else
    DOMAIN="crimes"
    COMUNA="Santiago"
    DOMINIO_LETRA="A"
    PORT=9002
fi

HOST="${NODES[SLURM_PROCID]}"

echo "[Publisher ${SLURM_PROCID}] Dominio: ${DOMAIN}, Comuna: ${COMUNA}"
echo "[Publisher ${SLURM_PROCID}] Host: ${HOST}:${PORT}"
echo "[Publisher ${SLURM_PROCID}] RUN_ID=${CIVICMESH_RUN_ID}"

export PYTHONPATH=".:CivicMesh"
export PYTHONUNBUFFERED=1

cd "$(dirname "$0")/../.."

python3 scripts/run_publisher.py \
    --domain "${DOMAIN}" \
    --comuna "${COMUNA}" \
    --host "${HOST}" \
    --port "${PORT}" \
    --hostfile "${HOSTFILE}" \
    --interval "${INTERVAL}" \
    --config "${CONFIG_FILE}" \
    --cache-path "${CACHE_FILE}" \
    --metrics-enabled \
    --metrics-interval "${METRICS_INTERVAL}" \
    --run-id "${CIVICMESH_RUN_ID}" \
    2>&1 | tee "${RUN_DIR}/logs/publisher_${DOMAIN}.log"