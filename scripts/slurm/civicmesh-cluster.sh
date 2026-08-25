#!/usr/bin/env bash
# civicmesh-cluster.sh — Orquestador completo de despliegue en cluster DIINF
#
# Uso:
#   ./civicmesh-cluster.sh deploy      # Despliega peers + publishers + frontend
#   ./civicmesh-cluster.sh status      # Muestra estado de jobs
#   ./civicmesh-cluster.sh logs <job>  # Muestra logs de un job
#   ./civicmesh-cluster.sh kill        # Cancela todos los jobs del usuario
#   ./civicmesh-cluster.sh robustez peer <job_id> <task_id>     # Mata un peer
#   ./civicmesh-cluster.sh robustez partition <job_id> <node>   # Particiona nodo

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
SLURM_DIR="${SCRIPT_DIR}"

ACTION="${1:-}"

case "${ACTION}" in
    deploy)
        echo "================================================================="
        echo "Desplegando CivicMesh en cluster DIINF (Slurm)"
        echo "================================================================="

        # 1. Bootstrap: crear directorio de corrida
        echo "[1/5] Bootstrap..."
        RUN_ID=$(bash "${SLURM_DIR}/bootstrap.sh")
        echo "    RUN_ID: ${RUN_ID}"

        # 2. Desplegar peers
        echo "[2/5] Desplegando peers (batch)..."
        PEER_JOB=$(sbatch --parsable "${SLURM_DIR}/peers.slurm")
        echo "    Job ID: ${PEER_JOB}"

        # Esperar a que peers se registren en hostfile
        echo "    Esperando registro de peers..."
        sleep 5

        # 3. Desplegar publicadores
        echo "[3/5] Desplegando publicadores (GPU)..."
        PUB_JOB=$(sbatch --parsable "${SLURM_DIR}/publishers.slurm")
        echo "    Job ID: ${PUB_JOB}"

        # 4. Desplegar frontend
        echo "[4/5] Desplegando frontend (GPU)..."
        FE_JOB=$(sbatch --parsable "${SLURM_DIR}/frontend.slurm")
        echo "    Job ID: ${FE_JOB}"

        # 5. Resumen
        echo "[5/5] Despliegue completado"
        echo "================================================================="
        echo "Jobs activos:"
        echo "  Peers:     ${PEER_JOB}"
        echo "  Publishers: ${PUB_JOB}"
        echo "  Frontend:  ${FE_JOB}"
        echo ""
        echo "Métricas en: \${CIVICMESH_RUNS}/${RUN_ID}/metrics/"
        echo "Frontend:    ssh -L 8501:localhost:8501 usuario@xi.diinf.usach.cl"
        echo "================================================================="
        ;;

    status)
        echo "================================================================="
        echo "Estado de jobs CivicMesh (usuario: ${USER})"
        echo "================================================================="
        squeue -u "${USER}" --format="%.8i %.9P %.20j %.8u %.2t %.10M %.6D %R"
        ;;

    logs)
        JOB_ID="${2:-}"
        if [[ -z "${JOB_ID}" ]]; then
            echo "Uso: $0 logs <job_id>"
            exit 1
        fi
        scontrol show job "${JOB_ID}" | grep -E "(JobId|JobName|StdOut|StdErr)"
        cat "$(scontrol show job "${JOB_ID}" | grep StdOut | cut -d= -f2)"
        ;;

    kill)
        echo "Cancelando todos los jobs del usuario ${USER}..."
        scancel -u "${USER}"
        echo "Hecho."
        ;;

    robustez)
        SUB_ACTION="${2:-}"
        shift 2
        bash "${SLURM_DIR}/kill_partition.sh" "${SUB_ACTION}" "$@"
        ;;

    *)
        echo "Uso: $0 {deploy|status|logs|kill|robustez}"
        echo "  deploy          Despliega toda la malla (peers + publishers + frontend)"
        echo "  status          Muestra estado de jobs"
        echo "  logs <job_id>   Muestra logs de un job"
        echo "  kill            Cancela todos los jobs"
        echo "  robustez peer <job_id> <task_id>       Mata un peer"
        echo "  robustez partition <job_id> <node>     Particiona nodo"
        echo "  robustez restore <node>                Restaura nodo"
        exit 1
        ;;
esac