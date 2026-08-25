#!/usr/bin/env bash
# bootstrap.sh — Inicializa directorio de corrida en Shared FS
# Uso: source bootstrap.sh  (para exportar RUN_ID y CIVICMESH_RUNS)

set -euo pipefail

# Run ID: usar SLURM_JOB_ID si existe, sino timestamp
RUN_ID="${SLURM_JOB_ID:-local-$(date +%s)}"

# Directorio base de corridas (puede sobreescribirse con env var)
CIVICMESH_RUNS="${CIVICMESH_RUNS:-$PWD/runs}"
RUN_DIR="${CIVICMESH_RUNS}/${RUN_ID}"

echo "================================================================="
echo "Iniciando corrida CivicMesh: ${RUN_ID}"
echo "Directorio Shared FS: ${RUN_DIR}"
echo "Nodos asignados: ${SLURM_JOB_NODELIST:-localhost}"
echo "================================================================="

# 1. Preparar directorios de la corrida en Shared FS
mkdir -p "${RUN_DIR}/logs" "${RUN_DIR}/metrics/raw" "${RUN_DIR}/metrics/figures"
touch "${RUN_DIR}/hostfile.txt"

# 2. Copiar configuraciones a la corrida
cp CivicMesh/config/config.yaml "${RUN_DIR}/config.yaml"

# 3. Exportar variables para jobs hijos
export CIVICMESH_RUNS
export CIVICMESH_RUN_ID="${RUN_ID}"
export RUN_DIR

# 4. Generar lista de nodos asignados por Slurm
if [[ -n "${SLURM_JOB_NODELIST:-}" ]]; then
    mapfile -t NODES < <(scontrol show hostnames "${SLURM_JOB_NODELIST}")
else
    NODES=("localhost")
fi

# Guardar lista de nodos para referencia
printf "%s\n" "${NODES[@]}" > "${RUN_DIR}/nodes.txt"

echo "[Bootstrap] Nodos totales: ${#NODES[@]}"
echo "[Bootstrap] Nodos: ${NODES[*]}"
echo "[Bootstrap] RUN_ID=${RUN_ID}"
echo "[Bootstrap] RUN_DIR=${RUN_DIR}"

# Output para que el job padre pueda capturar
echo "${RUN_ID}"