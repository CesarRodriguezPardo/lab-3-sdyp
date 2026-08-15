## 📁 Estructura del proyecto

```text
civicmesh/
│
├── README.md
├── CHANGELOG.md
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .gitignore
│
├── src/
│   └── civicmesh/
│       ├── __init__.py
│       ├── main.py
│       │
│       ├── network/
│       │   ├── __init__.py
│       │   ├── peer.py
│       │   ├── gossip.py
│       │   ├── membership.py
│       │   └── failure_detector.py
│       │
│       ├── pubsub/
│       │   ├── __init__.py
│       │   ├── message.py
│       │   ├── topic.py
│       │   ├── subscription.py
│       │   ├── router.py
│       │   └── forwarding.py
│       │
│       ├── domains/
│       │   ├── crimes/
│       │   │   ├── __init__.py
│       │   │   ├── generator.py
│       │   │   └── perception.py
│       │   │
│       │   └── air_quality/
│       │       ├── __init__.py
│       │       ├── replay.py
│       │       ├── perception.py
│       │       └── dataset.py
│       │
│       ├── aggregation/
│       │   ├── __init__.py
│       │   ├── state.py
│       │   └── metrics.py
│       │
│       └── config/
│           ├── __init__.py
│           └── loader.py
│
├── tests/
│   ├── unit/
│   │   ├── test_message.py
│   │   ├── test_forwarding.py
│   │   ├── test_gossip.py
│   │   ├── test_membership.py
│   │   ├── test_crimes.py
│   │   ├── test_air_quality.py
│   │   └── test_perception.py
│   │
│   └── integration/
│       ├── test_pubsub_network.py
│       └── test_peer_failure.py
│
├── config/
│   ├── config.yaml
│   ├── crimes.yaml
│   └── air_quality.yaml
│
├── data/
│   └── air_quality/
│       ├── README.md
│       └── ... archivos CSV/JSON ...
│
├── frontend/
│   ├── app.py
│   └── ...
│
├── scripts/
│   ├── run_local.sh
│   ├── run_compose.sh
│   │
│   ├── slurm/
│   │   ├── run_civicmesh.sbatch
│   │   ├── start_peers.sh
│   │   └── start_publishers.sh
│   │
│   ├── data/
│   │   └── download_air_quality.py
│   │
│   └── agents/
│       ├── documenter/
│       ├── bug_reviewer/
│       └── mr_reviewer/
│
├── .github/
│   └── workflows/
│       └── ci.yml
│
└── runs/
    └── .gitkeep