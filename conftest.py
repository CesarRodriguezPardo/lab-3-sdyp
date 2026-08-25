import sys
from pathlib import Path

# Agregar raíz y carpeta CivicMesh a sys.path para imports absolutos y relativos
ROOT_DIR = Path(__file__).resolve().parent
CIVICMESH_DIR = ROOT_DIR / "CivicMesh"

for p in (ROOT_DIR, CIVICMESH_DIR):
    p_str = str(p)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)
