# QuickBuild MCP Server & Containerized Infrastructure

A unified repository combining:
1. **QuickBuild MCP Server** (`src/`): A Python **Model Context Protocol (MCP v2)** server enabling AI agents and LLMs to inspect and automate QuickBuild CI/CD workflows.
2. **QuickBuild 14 + Microsoft SQL Server 2022 Stack** (`qb-database/`, `qb-server/`, `qb-agent/`, `kubernetes/`, `scripts/`): Multi-tier containerized QuickBuild infrastructure with Docker Compose and Kubernetes support.

> See [TODO.md](TODO.md) for the full cleanup status and the roadmap for upgrading QuickBuild and MSSQL versions.

---

## 1. QuickBuild MCP Server

### Features

#### MCP Tools
- `builds.trigger` — Trigger a new build for a configuration ID with optional build variables.
- `builds.get_latest_status` — Retrieve the status, version, timestamps, and success flag of the latest build for a configuration.
- `grid.list_agents` — List all build agents and their online/offline status.
- `system.backup_database` — Initiate a server-side QuickBuild database backup (with optional `backup_path`).
- `system.get_version` — Retrieve QuickBuild server version metadata.

#### MCP Resources & Resource Templates
- `configurations://list` — List all build configurations and parent hierarchy.
- `changes://build/{build_id}` — Retrieve SCM changes for a specific build ID (registered as both a resource and a parameterized resource template).

### Running the MCP Server Locally

```bash
# Install dependencies (Python 3.11+ / 3.12 recommended)
pip install -r requirements.txt
# Or with uv:
uv run --no-project --with-requirements requirements.txt python -m src.server
```

Configure `.env` (copied from `.env.example`):

```env
QB_URL=http://localhost:8810
QB_USER=admin
QB_PASSWORD=your_qb_password
LOG_LEVEL=INFO
QB_CACHE_TTL_CONFIGS=300
QB_CACHE_TTL_AGENTS=30
```

### Running Unit Tests

```bash
# Local test run with coverage
uv run --no-project --with-requirements requirements.txt pytest

# Or via Docker test container
python run_tests.py
```

---

## 2. QuickBuild 14 + Microsoft SQL Server 2022 Stack

### Architecture Overview

- **Database Tier (`qb-database/`):** Microsoft SQL Server 2022 (Linux container) with automated `quickbuild` database and `qb_user` initialization (`sqlcmd` supporting both `mssql-tools18` and `mssql-tools`).
- **Application Tier (`qb-server/`):** QuickBuild 14 Server (Eclipse Temurin JDK 8) with dynamic `hibernate.properties` and `wrapper.conf` generation.
- **Agent Tier (`qb-agent/`):** Scalable build agents (`base`, `maven`, `node`, `dotnet`).
- **MCP Integration (`Dockerfile`):** Non-root Python 3.12 container running `mcp-quickbuild-server` on `qb-net`.
- **Orchestration:** `docker-compose.yml` (+ `.dev.yml`, `.prod.yml`, `.scale.yml`) and `kubernetes/` manifests.

### Prerequisites

- Docker Engine 20.10+ and Docker Compose v2+ (`docker compose`)
- 4GB+ available RAM (8GB+ recommended for full stack)
- 20GB+ available disk space
- QuickBuild 14 server distribution placed in `environment/quickbuild-14.0.32/quickbuild-14.0.32/` and QuickBuild agent files in `qb-agent/base/quickbuild-agent/` (gitignored)

### Quick Start

1. Copy and configure environment variables:

```bash
cp .env.example .env
# Update MSSQL_SA_PASSWORD, QB_DB_PASSWORD, and QB_PASSWORD in .env
```

2. Choose your Docker Compose deployment mode:

| Mode | Command | Purpose |
|------|---------|---------|
| **Development** | `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d` | Exposed DB/JVM debug ports, `DEBUG` logging, local bind mounts |
| **Production** | `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d` | Docker secrets (`./secrets/`), TLS, higher resource limits |
| **Scaling** | `docker compose -f docker-compose.yml -f docker-compose.scale.yml up -d` | Replicated build agents with rolling update policies |
| **Base** | `docker compose up -d` | Standard single-file compose stack |

3. Access QuickBuild and validate:

- **Web Interface:** `http://localhost:8810`
- **Validate deployment:** `./scripts/validate-deployment.sh -e docker-compose`
- **Monitor status:** `./scripts/monitor.sh -e docker-compose --once`
- **Scale agents:** `./scripts/scale-agents.sh scale maven 3`

---

## Project Structure

```text
quickbuild-mcp/
├── src/                        # QuickBuild MCP Server (Python + MCP SDK v2)
│   ├── features/               # builds, changes, configurations, grid, system
│   ├── models/                 # Agent, Build, Change, Configuration dataclasses
│   ├── quickbuild_client.py    # Async httpx client with retry & TTL cache
│   └── server.py               # MCP Server core & request dispatch
├── tests/                      # Pytest unit test suite
├── qb-database/                # MSSQL 2022 Dockerfile, entrypoint, healthcheck, SQL init
├── qb-server/                  # QuickBuild 14 Dockerfile, entrypoint, config templates
├── qb-agent/                   # Base, Maven, Node.js, and .NET agent images
├── kubernetes/                 # K8s manifests (Namespace, RBAC, StatefulSets, PVCs, Ingress)
├── scripts/                    # Operational scripts (backup, restore, scale, monitor, validate)
├── docs/                       # Deployment, configuration, and troubleshooting guides
├── docker-compose*.yml         # Compose base and environment overrides
├── Dockerfile                  # MCP server production image (Python 3.12, non-root)
├── Dockerfile.test             # MCP server test runner image
├── pyproject.toml              # Python project & coverage configuration
├── pytest.ini                  # Pytest configuration
└── TODO.md                     # Cleanup summary and upgrade roadmap
```

## Documentation

- [DEPLOYMENT.md](docs/DEPLOYMENT.md) — Docker Compose & Kubernetes deployment procedures
- [CONFIGURATION.md](docs/CONFIGURATION.md) — Environment variables and tuning reference
- [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — Common issues and diagnostics
- [CLOUD-DEPLOYMENT-SPECS.md](docs/CLOUD-DEPLOYMENT-SPECS.md) — AWS, Azure, and GCP guidance
- [STEP-BY-STEP-MANUAL-INSTRUCTIONS.md](docs/STEP-BY-STEP-MANUAL-INSTRUCTIONS.md) — Manual container setup walkthrough
- [QUICK-START-SIMPLIFIED.md](docs/QUICK-START-SIMPLIFIED.md) — Simplified external-DB startup guide
