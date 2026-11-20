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

## Phase 2: QuickBuild & Microsoft SQL Server Version Upgrades (Next Up)

### QuickBuild Server & Agent Upgrade
- [ ] Decide target QuickBuild version (e.g., QuickBuild 15.x / 16.x) and verify official Java runtime requirement (upgrade `eclipse-temurin:8-jdk-focal` in `qb-server/Dockerfile` and `qb-agent/base/Dockerfile` to `eclipse-temurin:17-jdk-noble` or `eclipse-temurin:21-jdk-noble`).
- [ ] Update QuickBuild distribution binaries in `environment/` and `qb-agent/base/quickbuild-agent/`, and update `QB_VERSION` / `LABEL version` across `qb-server/Dockerfile`, `qb-agent/*/Dockerfile`, `kubernetes/*.yaml`, and scripts.
- [ ] Verify QuickBuild REST API endpoints (`/rest/authentication`, `/rest/configurations`, `/rest/builds`, `/rest/agents`, `/rest/builds/{id}/changes`, `/rest/version`, `/rest/backup`) against the target QuickBuild release (especially auth method — Basic Auth / Bearer Token vs `/rest/authentication` session login, and JSON response schemas).
- [ ] Review `qb-server/hibernate.properties.template` Hibernate dialect (`SQLServer2012Dialect` -> `SQLServer2016Dialect` or Hibernate 6 `SQLServerDialect` depending on the QuickBuild release).
- [ ] Decide whether `qb-server/entrypoint.sh` should continue launching `com.pmease.quickbuild.bootstrap.Bootstrap` directly or use `server.sh` / updated Java Service Wrapper.

### Microsoft SQL Server Upgrade
- [ ] Update `qb-database/Dockerfile` base image from `mcr.microsoft.com/mssql/server:2022-latest` to target MSSQL tag (e.g., `mcr.microsoft.com/mssql/server:2025-latest` or pinned `2022-CU*` / `2025-CU*` tag).
- [ ] Update `MSSQL_JDBC_VERSION` in `qb-server/Dockerfile` from `12.4.2.jre8` to the latest JDBC driver matching the upgraded JRE (e.g., `12.8.x.jre17` / `13.x.jre17`), and replace `|| echo "Warning..."` with a strict build failure + checksum verification so a broken JDBC download fails fast at build time.
- [ ] Test `qb-database/init-scripts/*.sql` and `qb-database/healthcheck.sh` against the upgraded SQL Server image (verifying `ACCEPT_EULA`, `MSSQL_SA_PASSWORD`, `mssql-tools18`, and TLS certificate defaults).

### Agent Base OS & Toolchain Upgrades (EOL Cleanup)
- [ ] Upgrade Ubuntu base from `focal` (20.04, EOL) to `noble` (24.04) across `qb-server/Dockerfile` and `qb-agent/base/Dockerfile` (and update `ubuntu:20.04` helper container in `scripts/backup.sh`, `scripts/backup.ps1`, `scripts/restore.sh` to `ubuntu:24.04` or `alpine`).
- [ ] Upgrade Node.js agent (`qb-agent/node/Dockerfile`) from EOL Node `16.20.2` to active LTS (Node `22.x` or `24.x`) and update NVM version.
- [ ] Upgrade .NET agent (`qb-agent/dotnet/Dockerfile` & `qb-agent/dotnet/config/global.json`) from EOL `.NET 6.0` (and `ubuntu/20.04` repo + `libssl1.1`/`libicu66`) to `.NET 8.0` or `.NET 9.0` LTS on Ubuntu 24.04.
- [ ] Upgrade Maven agent (`qb-agent/maven/Dockerfile` & `qb-agent/maven/config/settings.xml`) from Maven `3.8.8` to `3.9.x` and compiler source/target from Java `8` to target JDK.

---

## Phase 3: Further Optimizations & Production Readiness

- [ ] **MCP HTTP/Streamable Transport:** Add optional Streamable HTTP transport (`server.streamable_http_app()` / `uvicorn`) behind an env flag (e.g. `MCP_TRANSPORT=stdio|http`) so `mcp-quickbuild-server` can serve remote clients on port `14002` in addition to `stdio`.
- [ ] **Additional MCP Tools & Resources:** Implement remaining design/oracle items (`configurations.create`, build cancellation, build log streaming/tailing, JUnit test report resource, agent authorization).
- [ ] **Auth & Config Hardening:** Support QuickBuild API tokens / Basic Auth in `QuickBuildClient` alongside session auth, and add explicit TLS verification options (`QB_VERIFY_SSL`).
- [ ] **Kubernetes Hardening:** Update `kubernetes/` manifests (`busybox:1.35` -> `1.36+`, replace placeholder secrets/images, add `mcp-quickbuild-server` Deployment/Service if desired, check `ReadWriteMany` PVC requirements).
- [ ] **CI/CD Automation:** Add `.github/workflows/ci.yml` running `pytest`, `ruff`/`mypy`, `docker compose config`, `bash -n` / `shellcheck`, and Trivy image scanning on PRs.
- [ ] **Live End-to-End Test Suite:** Add an integration test suite verifying MSSQL init -> QuickBuild server startup -> agent registration -> MCP tool & resource calls against the live stack.
