#!/usr/bin/env bash
#SBATCH --job-name=civicmesh
#SBATCH --output=runs/%j/logs/slurm-%j.out
#SBATCH --error=runs/%j/logs/slurm-%j.err
#SBATCH --nodes=4
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=2
#SBATCH --time=00:30:00

# ==============================================================================
# CivicMesh — Despliegue en Clúster DIINF con Slurm y Shared FS
# Arquitectura: 2 Nodos CPU (Peers Gossip/PubSub) + 2 Nodos GPU (Publicadores/UI)
# Nota: En los nodos GPU se utiliza únicamente la CPU del host (sin CUDA).
# ==============================================================================

set -euo pipefail

RUN_ID="${SLURM_JOB_ID:-local-$(date +%s)}"
CIVICMESH_RUNS="${CIVICMESH_RUNS:-$PWD/runs}"
RUN_DIR="${CIVICMESH_RUNS}/${RUN_ID}"

echo "================================================================="
echo "Iniciando corrida CivicMesh: ${RUN_ID}"
echo "Directorio Shared FS: ${RUN_DIR}"
echo "Nodos asignados: ${SLURM_JOB_NODELIST:-localhost}"
echo "================================================================="

# 1. Preparar directorios de la corrida en Shared FS
mkdir -p "${RUN_DIR}/logs" "${RUN_DIR}/metrics"
touch "${RUN_DIR}/hostfile.txt"

# 2. Copiar configuraciones y fixtures a la corrida
cp CivicMesh/config/config.yaml "${RUN_DIR}/config.yaml"

export PYTHONPATH=".:CivicMesh"
export PYTHONUNBUFFERED=1

# Obtener lista de hosts asignados por Slurm
mapfile -t NODES < <(scontrol show hostnames "${SLURM_JOB_NODELIST:-localhost}")

CPU_NODE_1="${NODES[0]:-localhost}"
CPU_NODE_2="${NODES[1]:-localhost}"
GPU_NODE_1="${NODES[2]:-localhost}"
GPU_NODE_2="${NODES[3]:-localhost}"

echo "[Bootstrap] CPU Nodes (Peers): ${CPU_NODE_1}, ${CPU_NODE_2}"
echo "[Bootstrap] GPU Nodes (Publishers/UI): ${GPU_NODE_1}, ${GPU_NODE_2}"

# 3. Lanzar Peers en nodos CPU vía srun
echo "[Lanzando Peers en Nodos CPU]..."
srun --nodes=1 --nodelist="${CPU_NODE_1}" --ntasks=1 \
    python3 -m CivicMesh.src.main --host "${CPU_NODE_1}" --port 8001 --hostfile "${RUN_DIR}/hostfile.txt" --fanout 2 --timeout 6.0 \
    > "${RUN_DIR}/logs/peer_1.log" 2>&1 &

srun --nodes=1 --nodelist="${CPU_NODE_2}" --ntasks=1 \
    python3 -m CivicMesh.src.main --host "${CPU_NODE_2}" --port 8002 --hostfile "${RUN_DIR}/hostfile.txt" --fanout 2 --timeout 6.0 \
    > "${RUN_DIR}/logs/peer_2.log" 2>&1 &

# Dar tiempo para registro en hostfile y bootstrap inicial
sleep 3

# 4. Lanzar Publicadores en nodos GPU (solo CPU del host)
echo "[Lanzando Publicadores en Nodos GPU]..."
srun --nodes=1 --nodelist="${GPU_NODE_1}" --ntasks=1 \
    python3 scripts/run_publisher.py --domain air_quality --comuna "Las Condes" --host "${GPU_NODE_1}" --port 9001 --hostfile "${RUN_DIR}/hostfile.txt" \
    > "${RUN_DIR}/logs/publisher_air.log" 2>&1 &

srun --nodes=1 --nodelist="${GPU_NODE_2}" --ntasks=1 \
    python3 scripts/run_publisher.py --domain crimes --comuna "Santiago" --host "${GPU_NODE_2}" --port 9002 --hostfile "${RUN_DIR}/hostfile.txt" \
    > "${RUN_DIR}/logs/publisher_crimes.log" 2>&1 &

echo "CivicMesh ejecutándose en clúster. Monitoreando ejecución..."
wait
