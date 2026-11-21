# Project Review & Modernization TODO List

This checklist tracks all issues uncovered during the deep repository review on branch `modernize/qb14-mssql2022`, what has been cleaned up in the current baseline, and what remains for the upcoming QuickBuild & Microsoft SQL Server version upgrades.

---

## Phase 1: Baseline Review, Cleanup & Modernization (Done on `modernize/qb14-mssql2022`)

### Git & Branch Reconciliation
- [x] Create clean modernization branch `modernize/qb14-mssql2022` from `main`.
- [x] Incorporate unmerged fixes from `origin/claude/fix-docker-compose-docs-011CUtmBEzBNBZmXu8f8Eh2T` (removed obsolete `version: '3.8'` from all `docker-compose*.yml` files, replaced broken heredocs/`echo` config blocks in `qb-agent/{maven,node,dotnet}/Dockerfile` with external `config/` files and `COPY`).
- [x] Reconcile the Nov 2025 containerization merge collision in `docker-compose.yml`, `.env.example`, and `README.md` so both the **QuickBuild MCP Server** (`mcp-quickbuild-server`, `test`) and the **QuickBuild + MSSQL stack** coexist cleanly.

### Python MCP Server Modernization (`src/`, `tests/`)
- [x] Upgrade dependencies in `requirements.txt` to MCP Python SDK v2 (`mcp>=2.0.0,<3.0.0`), `httpx>=0.27.0`, `pydantic>=2.7.0`, `pytest>=8.0.0`, `pytest-asyncio>=0.24.0`, `pytest-cov>=5.0.0`, `pytest-mock>=3.14.0`, and add `pyproject.toml`.
- [x] Fix `pytest.ini` section header (`[tool:pytest]` -> `[pytest]`), configure `asyncio_mode = auto` and `asyncio_default_fixture_loop_scope = function`, remove hardcoded `/coverage` write path from default `pytest.ini`, and remove obsolete `fix_async_tests.py`.
- [x] Migrate `src/server.py` from removed MCP v1 decorators (`@self.server.call_tool()`, `@self.server.read_resource()`, etc.) to MCP SDK v2 `Server.add_request_handler(...)` (`tools/list`, `tools/call`, `resources/list`, `resources/templates/list`, `resources/read`) and pass `create_initialization_options()` to `self.server.run(...)`.
- [x] Fix broken resource template routing in `src/server.py` so parameterized URIs like `changes://build/456` route cleanly to `ChangesFeature` (via `ResourceTemplate` and prefix matching).
- [x] Update all `Tool` (`input_schema`) and `Resource` (`mime_type`) definitions across `src/features/*` and `tests/*` for MCP SDK v2 Pydantic models.
- [x] Implement the missing `SystemFeature` (`src/features/system/feature.py`) with `system.backup_database` and `system.get_version`, registered in `src/server.py` with dedicated unit tests (`tests/test_features_system.py`).
- [x] Optimize `src/quickbuild_client.py`:
  - Call `load_dotenv()` and strip trailing slash on `QB_URL`.
  - Fix empty response bug (`{}`/`[]` previously became `[{}]`).
  - Add `(httpx.ConnectError, httpx.TimeoutException)` handling and 401 retry exhaustion `AuthenticationError`.
  - Add plain-text response fallback (`{"raw": response.text}`), timezone-aware UTC datetimes, async context manager (`__aenter__`/`__aexit__`), `get_version()`, `backup_database()`, and configurable TTL caching (`QB_CACHE_TTL_CONFIGS`, `QB_CACHE_TTL_AGENTS`, `clear_cache()`).
- [x] Rename functions in root CLI verification script `test_server.py` (`check_*` instead of `test_*`) so pytest does not mistakenly collect it.
- [x] Upgrade `Dockerfile` and `Dockerfile.test` from `python:3.11-slim` to `python:3.12-slim` and run `Dockerfile` as non-root `mcpuser` (UID 1000).

### QuickBuild 14 + MSSQL 2022 Container & Script Fixes
- [x] Fix `qb-database/docker-entrypoint.sh` and `qb-database/healthcheck.sh`:
  - Auto-detect `/opt/mssql-tools18/bin/sqlcmd` (`-C` flag) with fallback to `/opt/mssql-tools/bin/sqlcmd`.
  - Support `SA_PASSWORD` or `MSSQL_SA_PASSWORD` and Docker secret `*_FILE` env vars (`SA_PASSWORD_FILE`, `QB_DB_PASSWORD_FILE`).
  - Replace fragile `sed` password substitution with native `sqlcmd -v QB_DB_PASSWORD="$QB_DB_PASSWORD"`.
  - Support `/opt/mssql/bin/launch_sqlservr.sh` with fallback to `/opt/mssql/bin/sqlservr`.
- [x] Support `QB_DB_PASSWORD_FILE` in `qb-server/entrypoint.sh` and remove duplicate `hibernate.hbm2ddl.auto=update` in `qb-server/hibernate.properties.template`.
- [x] Fix `qb-agent/base/Dockerfile` `COPY` paths for root build context (`.`) and `bin/agent.sh` permissions.
- [x] Remove obsolete `-XX:MaxPermSize=...` JVM flags (removed in modern JVMs) from `qb-agent/maven/Dockerfile`, `docker-compose*.yml`, `kubernetes/configmap.yaml`, and `docs/CONFIGURATION.md`.
- [x] Uncomment database persistence volumes (`qb-db-data`, `qb-db-logs`) and align `SA_PASSWORD` / `QB_DB_PASSWORD` variable wiring in `docker-compose.yml`.
- [x] Fix `scripts/restore.sh` tarball paths (`/backup/database/...`, `/backup/server/...`) and bash glob checks (`[[ -f ...* ]]`), fix `scripts/scale-agents.sh` & `scripts/scale-agents.ps1` missing `"set"` operation for `scale all`, fix `scripts/migrate-from-existing.sh` `MIGRATION_DIR` ordering bug, guard zero-division in `scripts/validate-deployment.sh`, and add `docker compose` v2/v5 detection across scripts and `run_tests.py`.
- [x] Remove system-wide destructive `docker system prune` / `docker volume prune` recommendations from `docs/QUICK-START-SIMPLIFIED.md` and `docs/TROUBLESHOOTING.md` to comply with `.kiro/steering/safety-rules.md`.

---

## Phase 2: QuickBuild & Microsoft SQL Server Version Upgrades (Done on `upgrade/qb-mssql-phase2`)

Verified live in an isolated compose project: SQL Server 2025 CU11 init + healthcheck, QuickBuild 16.0.37 on
JDK 21 (35 `QB_*` tables created by Hibernate), first-run setup wizard, base/maven/node/dotnet agents authorized
and online, and every MCP tool/resource over the stdio wire protocol against the live server.

### QuickBuild Server & Agent Upgrade
- [x] Decide target QuickBuild version: **16.0.37** (released 2026-11-19; QB 15+ requires Java 11+, QB 16 supports up to Java 25). Base images moved from `eclipse-temurin:8-jdk-focal` to `eclipse-temurin:21-jdk-noble` (`ARG JDK_IMAGE`).
- [x] Distribution sourcing: `qb-server/fetch-quickbuild-dist.sh` uses `environment/quickbuild-${QB_VERSION}/`, then `environment/quickbuild-${QB_VERSION}.zip`, then downloads `QB_DOWNLOAD_URL` (SHA-256 verified via `QB_DOWNLOAD_SHA256`). Multi-stage builds keep the copied/downloaded archive out of the final image.
- [x] Base agent image assembles the build agent package from the server distribution, file-for-file identical to the server's own `/download/buildagent.tar.gz` (or uses an extracted package in `qb-agent/base/quickbuild-agent/`).
- [x] `QB_VERSION` / `LABEL version` updated across `qb-server/Dockerfile`, `qb-agent/*/Dockerfile`, `kubernetes/*.yaml`, scripts, and compose files.
- [x] Verify QuickBuild REST API against 16.0.37: no `/rest/authentication` (HTTP Basic on every request; `/rest/version` also needs auth in QB16); JSON requires `Accept: application/json`; endpoints are `configurations?recursive=true`, `latest_builds/{id}` (204 = no builds), `POST build_requests` (returns `requestId`), `buildagents/active|inactive`, `changes/commits/build/{id}`, `version` (text), `POST backup` (`BackupNowOption`). Missing resources come back as HTTP 500 with a "not found" body.
- [x] Hibernate dialect: QuickBuild 16 bundles Hibernate 5.4, where `SQLServer2012Dialect` is the newest SQL Server dialect (and what QB ships). Template now mirrors QB16's shipped settings (HikariCP pool, EhCache provider) instead of the old c3p0/Hibernate 3 settings.
- [x] Launch method: entrypoints now `exec` the bundled Java Service Wrapper with the distribution's own `conf/wrapper.conf` (equivalent to `bin/server.sh console`) as PID 1 for graceful `docker stop`; the hand-built classpath launch and the incorrect `wrapper.conf.template` were removed. `wrapper.conf`/`wrapper-license.conf` are refreshed from the image on every start (they reference versioned jars).
- [x] QuickBuild 16 requires a Global Storage Directory outside its install dir: added `/var/lib/quickbuild/storage` (`qb-server-storage` volume, k8s `subPath`, backup/restore scripts).
- [x] QuickBuild 16 agents require a `token` in `node.properties`: agent entrypoint uses `QB_AGENT_TOKEN`, keeps an existing token across restarts, or generates one; new agents are authorized via Grid page or `GET /rest/tokens/authorize?ip=&port=`.

### Microsoft SQL Server Upgrade
- [x] `qb-database/Dockerfile` base image is `ARG MSSQL_IMAGE=mcr.microsoft.com/mssql/server:2025-CU11-ubuntu-24.04` (2025 Express on Ubuntu 24.04; 2022 tags still work via the build arg).
- [x] JDBC: `mssql-jdbc-13.6.2.jre11` from Maven Central with `MSSQL_JDBC_SHA256` verification and no silent fallback. The driver now replaces the bundled `mssql-jdbc-7.4.1.jre8.jar` in the `com.pmease.quickbuild.libs` OSGi bundle (and its `Bundle-ClassPath`); the old Dockerfile wrote to a `/opt/quickbuild/lib/` directory QuickBuild never loads.
- [x] `qb-database/init-scripts/*.sql` and `healthcheck.sh` tested on SQL Server 2025 CU11 (`mssql-tools18 -C`, `MSSQL_SA_PASSWORD`/`SA_PASSWORD`, TLS defaults): healthy in ~15s, `qb_user` connects.

### Agent Base OS & Toolchain Upgrades (EOL Cleanup)
- [x] Ubuntu `focal` -> `noble` (24.04) for server and agents (removes the stock `ubuntu` UID 1000 user, `netcat` -> `netcat-openbsd`); backup/restore helper image `ubuntu:20.04` -> `ubuntu:24.04`.
- [x] Node.js agent: Node `24.22.3` LTS via NVM `v0.41.0` (Node 22 is maintenance-only until Apr 2027); removed deprecated `create-react-app` and `@vue/cli`; removed the npm `prefix` setting in `.npmrc`, which NVM refuses to work with (it broke the image build and the agent entrypoint).
- [x] .NET agent: .NET SDK **10.0** LTS (.NET 8/9 reached end of support 2026-11-10) copied from `mcr.microsoft.com/dotnet/sdk:10.0-noble`; noble runtime deps (`libicu74`, `libssl3t64`); `global.json` -> `10.0.100` + `latestFeature`.
- [x] Maven agent: Maven `3.9.16` (SHA-512 verified), compiler `release`/`source`/`target` 21.
- [x] Replaced BuildKit-only `COPY --chmod` (classic builder is used on hosts without buildx); toolchain agents build `FROM ${BASE_IMAGE:-qb-agent-base:latest}` and compose tags the base image accordingly.
- [x] Kubernetes: `busybox:1.35` -> `1.37.0`, version labels -> `16.0`.
- [x] Operational scripts: `validate-deployment.sh` / `health-check.sh` follow QuickBuild 16's `/` -> `/dashboard` redirect; `/rest/version` checks send `QB_USER`/`QB_PASSWORD` (required by QB16) and parse the plain-text version; `migrate-from-existing.sh` reads the version from `asset/release`.

### MCP Server API Compatibility
- [x] `QB_AUTH_MODE=basic|session` (default `basic`, `httpx.BasicAuth`); `session` keeps the legacy `/rest/authentication` flow. Basic-mode 401s fail fast without re-authentication loops.
- [x] Client remapped to the QuickBuild 16 endpoints and JSON shapes above (models and MCP tool output shapes unchanged; `builds.trigger` adds `request_id`). New contract tests in `tests/test_quickbuild_client_qb16.py` replay payloads captured from the live server.

### Follow-ups found during Phase 2
- [ ] Default `QB_NETWORK_SUBNET=172.20.0.0/16` collides with existing Docker networks on some hosts; hard-coded `container_name`s and the `qb-bridge` bridge name prevent running two stacks side by side.
- [ ] `qb-node-global` volume / `/opt/qb-agent/.npm-global` PATH entry are now unused (npm `prefix` removed for NVM compatibility).
- [ ] Changeset JSON mapping (`changes/commits/build/{id}`) follows the documented structure; verify against a build with real SCM changes.
- [ ] `kubernetes/configmap.yaml` `JAVA_OPTS` is not consumed by the server image (use `QB_JAVA_MAX_MEMORY_MB` or extend the entrypoint).
- [ ] Persistent custom JVM flags: `conf/wrapper.conf` is refreshed from the image on start; consider an env hook for extra `wrapper.java.additional.N` flags.
- [ ] Optional: QuickBuild access-token REST authentication (QB 12+) as a third `QB_AUTH_MODE`.

---

## Phase 3: Further Optimizations & Production Readiness

- [ ] **MCP HTTP/Streamable Transport:** Add optional Streamable HTTP transport (`server.streamable_http_app()` / `uvicorn`) behind an env flag (e.g. `MCP_TRANSPORT=stdio|http`) so `mcp-quickbuild-server` can serve remote clients on port `14002` in addition to `stdio`.
- [ ] **Additional MCP Tools & Resources:** Implement remaining design/oracle items (`configurations.create`, build cancellation, build log streaming/tailing, JUnit test report resource, agent authorization).
- [ ] **Auth & Config Hardening:** Basic auth is done (Phase 2); add QuickBuild access-token auth and explicit TLS verification options (`QB_VERIFY_SSL`).
- [ ] **Kubernetes Hardening:** Update `kubernetes/` manifests (busybox bumped to 1.37.0 in Phase 2; replace placeholder secrets/images, add `mcp-quickbuild-server` Deployment/Service if desired, check `ReadWriteMany` PVC requirements).
- [ ] **CI/CD Automation:** Add `.github/workflows/ci.yml` running `pytest`, `ruff`/`mypy`, `docker compose config`, `bash -n` / `shellcheck`, and Trivy image scanning on PRs.
- [ ] **Live End-to-End Test Suite:** Add an integration test suite verifying MSSQL init -> QuickBuild server startup -> agent registration -> MCP tool & resource calls against the live stack.
