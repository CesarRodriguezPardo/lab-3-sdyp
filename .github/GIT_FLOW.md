# Flujo de trabajo Git — Laboratorio 3: CivicMesh

## 1. Rama protegida

`main` está protegida en GitHub:
- Sin push directo (incluye administradores).
- Merge solo vía Pull Request con ≥ 1 revisión humana + CI verde.
- Ramas fusionadas se eliminan automáticamente.

## 2. Convención de ramas

| Tipo | Patrón | Uso |
|---|---|---|
| Funcionalidad | `feature/<nombre>` | Nueva funcionalidad |
| Corrección | `fix/<nombre>` | Bugs o ajustes |

## 3. Commits convencionales

```
<tipo>(<scope>): <descripción corta>
```

Tipos: `feat`, `fix`, `docs`, `test`, `ci`, `chore`.
Scopes sugeridos: `gossip`, `pubsub`, `data`, `analytics`, `ci`, `agents`, `docs`.

## 4. Vinculación PR ↔ Issue

Todo PR debe referenciar al menos un issue:
- `Closes #N` — cierra el issue al fusionar.
- `Refs #N` — relacionado, no cierra.

## 5. Flujo

```bash
git checkout main && git pull
git checkout -b feature/<nombre>
# commits
git push -u origin feature/<nombre>
# Abrir PR con Closes #N
# CI pasa → agente MR comenta → revisión humana → merge
```

## 6. Releases

- `CHANGELOG.md` en formato Keep a Changelog.
- Tag de release al entregar: `v1.0.0-lab3`.

## 7. Agentes de IA

Tres agentes en `.github/agents/` y `.github/workflows/`.
Documentación: [`.github/agents/README.md`](agents/README.md).
Nunca fusionan sin aprobación humana.
