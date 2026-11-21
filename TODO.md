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
- [ ] Default `QB_NETWORK_SUBNET=172.20.0.0/16` collides with existing Docker networks on some hosts; hard-coded `container_name`s and the `qb-bridge` bridge name prevent running two stacks side by side. (The e2e harness works around this with `tests/e2e/compose.e2e.yml`; the base file is unchanged.)
- [ ] `qb-node-global` volume / `/opt/qb-agent/.npm-global` PATH entry are now unused (npm `prefix` removed for NVM compatibility).
- [x] Changeset JSON mapping (`changes/commits/build/{id}`) verified in Phase 3 against a real Git commit (e2e fixture `root/e2e-git`); `RawChangeset` adds `previousEdition`, and the MCP output now includes the repository and per-file actions.
- [ ] `kubernetes/configmap.yaml` `JAVA_OPTS` is not consumed by the server image (use `QB_JAVA_MAX_MEMORY_MB` or extend the entrypoint).
- [ ] Persistent custom JVM flags: `conf/wrapper.conf` is refreshed from the image on start; consider an env hook for extra `wrapper.java.additional.N` flags.
- [x] QuickBuild access-token REST authentication: `QB_AUTH_MODE=token` (Phase 3; QuickBuild 16 takes the token as the HTTP Basic password).

---

## Phase 3: MCP Readiness (Done on `improve/phase3-mcp-readiness`)

Every new endpoint and JSON shape below was confirmed against a live QuickBuild 16.0.37 (the e2e
harness) before it was coded; payloads captured there back the contract tests
(`tests/test_quickbuild_client_phase3.py`).

### Test harness in the repo
- [x] `scripts/e2e.sh [all|up|setup|test|down|status] [--keep] [--rmi]`: isolated compose project `qbe2e`
  (subnet `10.221.0.0/16`, loopback-only ports 18810/14012/18843, per-run generated passwords),
  first-run wizard (`tests/e2e/qb_setup.py`), agent authorization, fixtures, `pytest -m e2e`, and a
  teardown that removes only the project's containers, network, labelled volumes and state dir.
  `up` refuses to start unless every volume name carries the e2e project prefix (the base compose
  file names volumes `${COMPOSE_PROJECT_NAME:-quickbuild}_*`).
- [x] Fixtures created over REST (`tests/e2e/qb_fixtures.py`, `tests/e2e/fixtures/*.xml`): `root/e2e-sleep`
  (long build for queue/cancel) and `root/e2e-git` (local bare Git repo + checkout + 60 log lines),
  a baseline build, a commit by a second author, and a build that records it. `git` added to the
  harness `qb-server` image. HTTPS front (`nginxinc/nginx-unprivileged:1.27-alpine`) with a
  throwaway CA; MCP container in HTTP mode.
- [x] `pytest` marker `e2e` (excluded by default via `pytest.ini`); 18 e2e tests over real MCP
  sessions (stdio subprocess and the HTTP container).

### Corporate readiness
- [x] `src/config.py`: one validated settings object; `QB_PASSWORD_FILE`, `QB_TOKEN`/`QB_TOKEN_FILE`,
  `QB_TIMEOUT`, `QB_VERIFY_SSL`, `QB_CA_BUNDLE` (added to certifi's roots), proxy variables via httpx
  `trust_env` (CIDR entries in `NO_PROXY` are not supported by httpx and are warned about).
- [x] `QB_READ_ONLY=true` hides and refuses `builds.trigger`, `build_requests.cancel`,
  `system.backup_database`; all tools carry MCP annotations; tool failures return `isError: true`.
- [x] `QB_AUTH_MODE=token`: QuickBuild 16 access tokens are the HTTP Basic password (`Bearer` is
  rejected with 401; verified live).
- [x] Untrusted certificates are reported as `TLS_VERIFY_FAILED` naming `QB_CA_BUNDLE` and are not retried.
- [x] Ids are validated before they are placed in URL paths (httpx resolves `..` segments, so an
  unchecked `request_id` could have redirected a DELETE); POSTs are retried only when the connection
  was never established (a timeout after sending could already have queued a build).

### Streamable HTTP transport
- [x] `MCP_TRANSPORT=stdio|http` on `MCP_HOST:MCP_PORT` (14002) at `MCP_HTTP_PATH` (`/mcp`), stateless by
  default; `GET /health` (liveness) and `GET /ready` (QuickBuild reachable); `MCP_ALLOWED_HOSTS` /
  `MCP_ALLOWED_ORIGINS` for DNS-rebinding protection. Dockerfile `HEALTHCHECK` (`python -m src.healthcheck`);
  the compose service runs HTTP with a healthcheck.

### New tools (verified live)
- [x] `builds.get` (`GET /rest/builds/{id}`: steps, revisions, masked request variables)
- [x] `builds.get_log` (`GET /download/{id}/log`, tail kept in memory; finished builds only)
- [x] `builds.list_running` (`GET /rest/builds?status=RUNNING&count=N[&configuration_id=]`; `count` is mandatory)
- [x] `build_requests.list` (`GET /rest/build_requests[?configuration_id=]`)
- [x] `build_requests.cancel` (`DELETE /rest/build_requests/{id}` -> 204; running build ends `CANCELLED`)
- [x] `configurations.search` (client-side over the cached configuration list, ranked)
- [x] `grid.list_unauthorized` (`GET /rest/buildagents/unauthorized`)
- [x] Configuration arguments accept ids or paths (`GET /rest/ids?configuration_path=`)

### CI
- [x] `.github/workflows/ci.yml`: pytest with the 90% gate (`fail_under = 90`), `docker compose config -q`
  for base/dev/prod/scale, per-file `bash -n` + `shellcheck -S warning`, gitleaks on the full history
  (`.gitleaksignore` lists the two `kubernetes/secrets.yaml` placeholders), and `scripts/e2e.sh` as a
  `workflow_dispatch` job (container logs uploaded on failure). Actions pinned to commit SHAs.
- [x] Shell warnings fixed (unused variables, quoting); `SC2155` is disabled in `.shellcheckrc` because the
  scripts run with `set -e` and rely on `local var=$(probe)` tolerating failed probes.

### Follow-ups found during Phase 3
- [ ] Parsed-but-unused script options: `health-check.sh --continue`, `monitor.sh --memory-threshold/--disk-threshold`,
  `migrate-from-existing.sh -e/-n/-p` (annotated for shellcheck, behaviour unchanged).
- [ ] Live build logs: QuickBuild 16's download servlet fails (`EOFException`) while a build runs; find
  another source if live tailing is needed.
- [ ] Tool names contain dots (`builds.get`); check the FastMCP gateway and Claude clients accept them, or add an
  underscore alias scheme.
- [ ] `gitleaks dir` (working tree) still reports the two placeholders (its fingerprints differ from the history scan CI runs).

---

## Hardening Phase (next)

- [ ] **Inbound MCP authentication (deferred from Phase 3):** OAuth 2.1 resource-server mode for the HTTP
  transport per the MCP authorization spec: validate bearer JWTs from the corporate IdP (issuer, audience =
  this server, expiry, JWKS signature), publish Protected Resource Metadata, map scopes to tools
  (`quickbuild:read` / `quickbuild:write`), log the caller's identity per tool call. Never pass the caller's
  token through to QuickBuild. Needs: IdP (issuer/audience/scopes) and how the FastMCP gateway obtains or
  forwards the backend token. The MCP SDK already provides `AuthSettings`/`TokenVerifier`, and `pyjwt[crypto]`
  comes with it.
- [ ] **Network controls:** Kubernetes `NetworkPolicy` (only the gateway reaches port 14002) or mTLS.
- [ ] **Kubernetes Hardening:** `mcp-quickbuild-server` Deployment/Service (HTTP transport, `/ready` readiness,
  `/health` liveness, secrets via `QB_TOKEN_FILE`/`QB_PASSWORD_FILE`, `QB_CA_BUNDLE` from a ConfigMap);
  replace placeholder secrets/images; check `ReadWriteMany` PVC requirements.
- [ ] **Additional MCP Tools & Resources:** `configurations.create`, JUnit test report resource, agent authorization.
- [ ] **CI additions:** `ruff`/`mypy`, Trivy image scanning.
