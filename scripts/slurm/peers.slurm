#!/usr/bin/env bash
#SBATCH --job-name=civicmesh-peers
#SBATCH --partition=batch
#SBATCH --nodes=2
#SBATCH --ntasks=2
#SBATCH --cpus-per-task=2
#SBATCH --time=01:00:00
#SBATCH --output=%x-%j.out
#SBATCH --error=%x-%j.err

# peers.slurm — Job array para peers Gossip/PubSub en nodos CPU (partición batch)
# Ejecuta 2 peers (uno por task) que forman la malla distribuida.
# Cada peer se suscribe a todos los tópicos y genera métricas de convergencia.

set -euo pipefail

# Cargar bootstrap (define RUN_ID, RUN_DIR, CIVICMESH_RUNS, NODES)
source "$(dirname "$0")/bootstrap.sh"

# Configuración de peers
CONFIG_FILE="${RUN_DIR}/config.yaml"
HOSTFILE="${RUN_DIR}/hostfile.txt"
FANOUT=2
TIMEOUT=6.0
METRICS_INTERVAL=5.0

# Asignar nodos: task 0 -> NODES[0], task 1 -> NODES[1]
NODE_IDX=$((SLURM_PROCID))
HOST="${NODES[NODE_IDX]}"
PORT=$((8001 + NODE_IDX))

echo "[Peer ${SLURM_PROCID}] Iniciando en ${HOST}:${PORT}"
echo "[Peer ${SLURM_PROCID}] RUN_ID=${CIVICMESH_RUN_ID}"
echo "[Peer ${SLURM_PROCID}] RUN_DIR=${RUN_DIR}"

# Registrar en hostfile (formato: host:port)
echo "${HOST}:${PORT}" >> "${HOSTFILE}"

# Esperar a que todos los peers se registren
sleep 3

# Lanzar peer
export PYTHONPATH=".:CivicMesh"
export PYTHONUNBUFFERED=1

cd "$(dirname "$0")/../.."

python3 -m CivicMesh.src.main \
    --host "${HOST}" \
    --port "${PORT}" \
    --hostfile "${HOSTFILE}" \
    --fanout "${FANOUT}" \
    --timeout "${TIMEOUT}" \
    --config "${CONFIG_FILE}" \
    --metrics-enabled \
    --metrics-interval "${METRICS_INTERVAL}" \
    --metrics-dominio "unknown" \
    --run-id "${CIVICMESH_RUN_ID}" \
    2>&1 | tee "${RUN_DIR}/logs/peer_${SLURM_PROCID}.log"