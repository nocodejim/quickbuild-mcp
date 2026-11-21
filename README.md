# QuickBuild MCP Server & Containerized Infrastructure

A unified repository combining:
1. **QuickBuild MCP Server** (`src/`): A Python **Model Context Protocol (MCP v2)** server enabling AI agents and LLMs to inspect and automate QuickBuild CI/CD workflows.
2. **QuickBuild 16 + Microsoft SQL Server 2025 Stack** (`qb-database/`, `qb-server/`, `qb-agent/`, `kubernetes/`, `scripts/`): Multi-tier containerized QuickBuild infrastructure with Docker Compose and Kubernetes support.

> See [TODO.md](TODO.md) for the full cleanup status and the roadmap for upgrading QuickBuild and MSSQL versions.

---

## 1. QuickBuild MCP Server

### Features

#### MCP Tools

Read tools (always available):

- `configurations.search` — Find configurations by id, name, path (`root/team/app`) or description; best matches first.
- `builds.get_latest_status` — Status, version, timestamps and success flag of a configuration's latest build.
- `builds.get` — One build: status, timing, node, each step's status and duration, checked-out revisions, request variables (secret values stay masked).
- `builds.get_log` — The last lines of a finished build's log (`tail_lines`, default 200, max 2000).
- `builds.list_running` — Builds that are running now (optionally under one configuration).
- `build_requests.list` — The build queue: waiting and running build requests.
- `grid.list_agents` — Build agents and their online/offline status.
- `grid.list_unauthorized` — Agents waiting to be authorized on the Grid page.
- `system.get_version` — QuickBuild server version.

Write tools (hidden and refused when `QB_READ_ONLY=true`):

- `builds.trigger` — Request a build of a configuration, with optional variables; returns the `request_id`.
- `build_requests.cancel` — Cancel a queued or running build request (a running build ends `CANCELLED`).
- `system.backup_database` — Start a server-side QuickBuild database backup (optional `backup_path`).

Configuration arguments accept a numeric id or a path such as `root/team/app`. Every tool carries
MCP annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`), and failures are returned
with `isError: true`.

#### MCP Resources & Resource Templates
- `configurations://list` — All build configurations with their path and parent.
- `changes://build/{build_id}` — SCM changesets of a build: revision, author, message, repository and per-file actions (registered as both a resource and a resource template).

### Running the MCP Server

```bash
# stdio (an MCP client starts the server as a subprocess)
uv run --no-project --with-requirements requirements.txt python -m src.server

# Streamable HTTP for a gateway: http://127.0.0.1:14002/mcp, plus /health and /ready
MCP_TRANSPORT=http uv run --no-project --with-requirements requirements.txt python -m src.server

# Container (compose runs it in HTTP mode on port 14002)
docker compose up -d mcp-quickbuild-server
```

Configure `.env` (copied from `.env.example`) or the environment:

```env
QB_URL=http://localhost:8810
QB_USER=admin
QB_PASSWORD=your_qb_password      # or QB_PASSWORD_FILE=/run/secrets/qb_password
QB_AUTH_MODE=basic                # basic | token (QB_TOKEN / QB_TOKEN_FILE) | session
QB_READ_ONLY=false                # true: no trigger / cancel / backup
LOG_LEVEL=INFO
```

For a corporate QuickBuild: `QB_CA_BUNDLE` (corporate CA), `QB_VERIFY_SSL`, `QB_TIMEOUT`,
`HTTPS_PROXY`/`NO_PROXY`, access-token auth, read-only mode, and the HTTP transport settings
(`MCP_HOST`, `MCP_ALLOWED_HOSTS`, ...) are described in
[docs/CONFIGURATION.md](docs/CONFIGURATION.md#mcp-server-configuration), with a complete example.
Inbound authentication of MCP clients is planned for the hardening phase; until then expose the
HTTP port only to the gateway.

The client talks to the QuickBuild REST API (JSON edition, `Accept: application/json`). Every
endpoint and JSON shape it uses was verified live against QuickBuild 16.0.37 by the e2e suite.

### Tests

```bash
# Unit and contract tests with the 90% coverage gate (the e2e tests are excluded by default)
uv run --no-project --with-requirements requirements.txt pytest

# End-to-end: build and start an isolated QuickBuild 16 + SQL Server 2025 stack, run the setup
# wizard, authorize an agent, create fixture configurations (incl. a Git repository), run every
# MCP tool and resource over stdio, check the HTTP container (catalog, calls, /health, /ready,
# Host allow-list) and TLS/proxy/token/read-only behaviour, then tear down
scripts/e2e.sh                 # or: up | setup | test | down | status, --keep to debug

# Or via the Docker test container
python run_tests.py
```

`scripts/e2e.sh` uses compose project `qbe2e`, subnet `10.221.0.0/16` and loopback-only ports
(18810, 14012, 18843); it generates its own passwords and removes only what it created.

CI (`.github/workflows/ci.yml`) runs pytest with the coverage gate, `docker compose config -q`
for the base/dev/prod/scale files, `bash -n` and `shellcheck` on every script, and gitleaks on
the full history on each push and pull request; the e2e suite runs on demand
(*Actions > CI > Run workflow*).

---

## 2. QuickBuild 16 + Microsoft SQL Server 2025 Stack

### Architecture Overview

| Component | Version (pinned via Dockerfile build args) |
|-----------|---------------------------------------------|
| QuickBuild server & agents | 16.0.37 (`QB_VERSION`, `QB_DOWNLOAD_URL`, `QB_DOWNLOAD_SHA256`) |
| Java | Eclipse Temurin 21 JDK on Ubuntu 24.04 (`JDK_IMAGE=eclipse-temurin:21-jdk-noble`) |
| SQL Server | 2025 CU11 Express on Ubuntu 24.04 (`MSSQL_IMAGE`) |
| SQL Server JDBC driver | 13.6.2.jre11 (`MSSQL_JDBC_VERSION`, `MSSQL_JDBC_SHA256`) |
| Maven agent | Maven 3.9.16, compiles for Java 21 |
| Node.js agent | Node.js 24.22.3 LTS via NVM v0.41.0 |
| .NET agent | .NET SDK 10.0 LTS |

- **Database Tier (`qb-database/`):** Microsoft SQL Server 2025 (Linux container) with automated `quickbuild` database and `qb_user` initialization (`sqlcmd` supporting both `mssql-tools18` and `mssql-tools`).
- **Application Tier (`qb-server/`):** QuickBuild 16 Server (Temurin JDK 21) run by the bundled Java Service Wrapper, with `hibernate.properties` rendered from a template (Hibernate 5.4 `SQLServer2012Dialect`, HikariCP).
- **Agent Tier (`qb-agent/`):** Scalable build agents (`base`, `maven`, `node`, `dotnet`); the base image assembles the build agent package from the QuickBuild distribution exactly like the server's own agent download.
- **MCP Integration (`Dockerfile`):** Non-root Python 3.12 container running `mcp-quickbuild-server` on `qb-net`.
- **Orchestration:** `docker-compose.yml` (+ `.dev.yml`, `.prod.yml`, `.scale.yml`) and `kubernetes/` manifests.

### Prerequisites

- Docker Engine 20.10+ and Docker Compose v2+ (`docker compose`); BuildKit is not required
- 4GB+ available RAM (8GB+ recommended for full stack)
- 20GB+ available disk space
- Internet access at build time (the QuickBuild 16 zip is downloaded and SHA-256 verified). For offline builds,
  place `quickbuild-16.0.37.zip` or its unpacked folder in `environment/` (gitignored).

### Quick Start

1. Copy and configure environment variables:

```bash
cp .env.example .env
# Update MSSQL_SA_PASSWORD, QB_DB_PASSWORD, and QB_PASSWORD in .env
```

2. Build the images (the toolchain agents build `FROM qb-agent-base:latest`, so build it first):

```bash
docker compose build qb-agent-base && docker compose build
```

> If `docker compose up` fails with `Pool overlaps with other one on this address space`, set
> `QB_NETWORK_SUBNET` (default `172.20.0.0/16`) to a free range in `.env`.

3. Choose your Docker Compose deployment mode:

| Mode | Command | Purpose |
|------|---------|---------|
| **Development** | `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d` | Exposed DB/JVM debug ports, `DEBUG` logging, local bind mounts |
| **Production** | `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d` | Docker secrets (`./secrets/`), TLS, higher resource limits |
| **Scaling** | `docker compose -f docker-compose.yml -f docker-compose.scale.yml up -d` | Replicated build agents with rolling update policies |
| **Base** | `docker compose up -d` | Standard single-file compose stack |

4. Complete the QuickBuild first-run setup wizard at `http://localhost:8810` (REST returns 404 until it is done):
   - **Administrator:** create the account the MCP server uses (`QB_USER` / `QB_PASSWORD`).
   - **URL to Access QuickBuild:** `http://qb-server:8810` (agents connect over the compose network).
   - **Global Storage Directory:** `/var/lib/quickbuild/storage` (its own volume; QuickBuild rejects paths under its install dir `/opt/quickbuild`).
   - **SMTP:** your mail host (required by the wizard).

5. Authorize the build agents (QuickBuild 16 agents join the grid as *unauthorized*): use **Grid → Unauthorized Nodes**
   in the web UI, or `curl -u admin:<password> "http://localhost:8810/rest/tokens/authorize?ip=<agent ip>&port=8811"`.
   Set `QB_AGENT_TOKEN` per agent to keep an authorized identity when containers are recreated.

6. Access QuickBuild and validate:

- **Web Interface:** `http://localhost:8810`
- **Validate deployment:** `./scripts/validate-deployment.sh -e docker-compose`
- **Monitor status:** `./scripts/monitor.sh -e docker-compose --once`
- **Scale agents:** `./scripts/scale-agents.sh scale maven 3`

---

## Project Structure

```text
quickbuild-mcp/
├── src/                        # QuickBuild MCP Server (Python + MCP SDK v2)
│   ├── features/               # builds, build_requests, changes, configurations, grid, system
│   ├── models/                 # Agent, Build, BuildRequest, Change, Configuration dataclasses
│   ├── config.py               # Environment settings (auth, TLS, proxy, read-only, transport)
│   ├── quickbuild_client.py    # Async httpx client with retry & TTL cache
│   ├── healthcheck.py          # Container health check (HTTP transport)
│   └── server.py               # MCP Server core, read-only policy, stdio/HTTP transports
├── tests/                      # Pytest unit and contract tests
│   └── e2e/                    # Live harness suite (pytest -m e2e), wizard, fixtures, compose override
├── .github/workflows/ci.yml    # CI: pytest, compose config, bash -n/shellcheck, gitleaks, e2e
├── qb-database/                # MSSQL 2025 Dockerfile, entrypoint, healthcheck, SQL init
├── qb-server/                  # QuickBuild 16 Dockerfile, entrypoint, dist fetcher, hibernate template
├── qb-agent/                   # Base, Maven, Node.js, and .NET agent images
├── kubernetes/                 # K8s manifests (Namespace, RBAC, StatefulSets, PVCs, Ingress)
├── scripts/                    # Operational scripts (backup, restore, scale, monitor, validate, e2e)
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
