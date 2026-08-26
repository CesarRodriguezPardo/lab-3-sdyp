#!/usr/bin/env bash
#SBATCH --job-name=civicmesh
#SBATCH --output=civicmesh-%j.out
#SBATCH --error=civicmesh-%j.err
#SBATCH --partition=batch
#SBATCH --nodes=2
#SBATCH --ntasks=2
#SBATCH --cpus-per-task=2
#SBATCH --time=00:30:00

# ==============================================================================
# CivicMesh — Job 1: Peers CPU (Gossip/PubSub)
# ==============================================================================

set -euo pipefail

REPO_DIR="/home/ceph/scassone/repos/civicmesh"
RUN_ID="${SLURM_JOB_ID:-local-$(date +%s)}"
CIVICMESH_RUNS="${CIVICMESH_RUNS:-${REPO_DIR}/runs}"
RUN_DIR="${CIVICMESH_RUNS}/${RUN_ID}"

echo "================================================================="
echo "Iniciando corrida CivicMesh: ${RUN_ID}"
echo "Directorio Shared FS: ${RUN_DIR}"
echo "Nodos asignados: ${SLURM_JOB_NODELIST:-localhost}"
echo "================================================================="

mkdir -p "${RUN_DIR}/logs" "${RUN_DIR}/metrics/raw" "${RUN_DIR}/metrics/figures"
touch "${RUN_DIR}/hostfile.txt"

cp "${REPO_DIR}/CivicMesh/config/config.yaml" "${RUN_DIR}/config.yaml"

export PYTHONPATH="${REPO_DIR}:${REPO_DIR}/CivicMesh"
export PYTHONUNBUFFERED=1
export CIVICMESH_RUNS="${REPO_DIR}/runs"
export CIVICMESH_RUN_ID="${RUN_ID}"

mapfile -t NODES < <(scontrol show hostnames "${SLURM_JOB_NODELIST:-localhost}")

CPU_NODE_1="${NODES[0]:-localhost}"
CPU_NODE_2="${NODES[1]:-localhost}"

echo "[Bootstrap] CPU Nodes (Peers): ${CPU_NODE_1}, ${CPU_NODE_2}"
echo "[Bootstrap] RUN_ID=${RUN_ID}"

echo "${RUN_ID}" > "${RUN_DIR}/run_id.txt"
printf "%s\n" "${NODES[@]}" > "${RUN_DIR}/nodes.txt"

echo "[Lanzando Peers en Nodos CPU]..."
srun --nodes=1 --nodelist="${CPU_NODE_1}" --ntasks=1 \
    python3 -m CivicMesh.src.main --host "${CPU_NODE_1}" --port 8001 --hostfile "${RUN_DIR}/hostfile.txt" --fanout 2 --timeout 6.0 --config "${RUN_DIR}/config.yaml" \
    > "${RUN_DIR}/logs/peer_1.log" 2>&1 &
PID1=$!

srun --nodes=1 --nodelist="${CPU_NODE_2}" --ntasks=1 \
    python3 -m CivicMesh.src.main --host "${CPU_NODE_2}" --port 8002 --hostfile "${RUN_DIR}/hostfile.txt" --fanout 2 --timeout 6.0 --config "${RUN_DIR}/config.yaml" \
    > "${RUN_DIR}/logs/peer_2.log" 2>&1 &
PID2=$!

echo "[Peers] PIDs: ${PID1}, ${PID2}"
sleep 5
echo "[Hostfile]:"
cat "${RUN_DIR}/hostfile.txt" || echo "(vacío aún)"

echo "================================================================="
echo "RUN_ID: ${RUN_ID}"
echo "Para lanzar publishers: export CIVICMESH_RUN_ID=${RUN_ID} && sbatch scripts/slurm/publishers.sbatch"
echo "Para lanzar frontend:   export CIVICMESH_RUN_ID=${RUN_ID} && sbatch scripts/slurm/frontend.slurm"
echo "================================================================="

wait

mv -f civicmesh-${SLURM_JOB_ID}.out "${RUN_DIR}/logs/" 2>/dev/null || true
mv -f civicmesh-${SLURM_JOB_ID}.err "${RUN_DIR}/logs/" 2>/dev/null || true
