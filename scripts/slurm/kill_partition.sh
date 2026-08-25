#!/usr/bin/env bash
# kill_partition.sh — Script para experimentos de robustez (caída de peers / partición)
#
# Uso:
#   ./kill_partition.sh peer <job_id> <task_id>     # Mata un peer específico (scancel step)
#   ./kill_partition.sh partition <job_id> <node>   # Particiona red en un nodo (iptables)
#   ./kill_partition.sh restore <node>              # Restaura conectividad
#
# Requiere: permisos sudo en nodos para iptables, o acceso a slurm para scancel

set -euo pipefail

ACTION="${1:-}"
JOB_ID="${2:-}"
TARGET="${3:-}"

if [[ -z "${ACTION}" ]]; then
    echo "Uso: $0 {peer|partition|restore} <job_id> [task_id|node]"
    echo "  peer      JOB_ID TASK_ID    Mata un peer específico (scancel job.task)"
    echo "  partition JOB_ID NODE       Particiona red en nodo (iptables DROP)"
    echo "  restore   NODE              Restaura conectividad en nodo"
    exit 1
fi

case "${ACTION}" in
    peer)
        if [[ -z "${JOB_ID}" || -z "${TARGET}" ]]; then
            echo "Error: peer requiere JOB_ID y TASK_ID"
            exit 1
        fi
        echo "[Robustez] Matando peer: job ${JOB_ID}.${TARGET}"
        scancel "${JOB_ID}.${TARGET}"
        echo "[Robustez] Peer ${JOB_ID}.${TARGET} cancelado"
        ;;

    partition)
        if [[ -z "${JOB_ID}" || -z "${TARGET}" ]]; then
            echo "Error: partition requiere JOB_ID y NODE"
            exit 1
        fi
        echo "[Robustez] Particionando red en nodo ${TARGET} (job ${JOB_ID})"
        # Bloquear tráfico entrante/saliente en puertos CivicMesh (8000-9000)
        ssh "${TARGET}" "sudo iptables -I INPUT -p tcp --dport 8000:9000 -j DROP"
        ssh "${TARGET}" "sudo iptables -I OUTPUT -p tcp --dport 8000:9000 -j DROP"
        echo "[Robustez] Nodo ${TARGET} particionado (puertos 8000-9000 bloqueados)"
        ;;

    restore)
        if [[ -z "${TARGET}" ]]; then
            echo "Error: restore requiere NODE"
            exit 1
        fi
        echo "[Robustez] Restaurando conectividad en nodo ${TARGET}"
        ssh "${TARGET}" "sudo iptables -D INPUT -p tcp --dport 8000:9000 -j DROP 2>/dev/null || true"
        ssh "${TARGET}" "sudo iptables -D OUTPUT -p tcp --dport 8000:9000 -j DROP 2>/dev/null || true"
        echo "[Robustez] Conectividad restaurada en ${TARGET}"
        ;;

    *)
        echo "Acción desconocida: ${ACTION}"
        exit 1
        ;;
esac