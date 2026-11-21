import asyncio
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union

import httpx
from dotenv import load_dotenv

from .config import AUTH_MODES, Settings  # noqa: F401  (AUTH_MODES re-exported)
from .exceptions import (
    AuthenticationError,
    ERROR_MAPPINGS,
    QuickBuildError,
    QuickBuildServerError,
    QuickBuildUnavailableError,
    ResourceNotFoundError,
)
from .models import Agent, Build, BuildRequest, Change, Configuration

load_dotenv()

logger = logging.getLogger(__name__)

# Build statuses that indicate a successful build
SUCCESS_STATUSES = {"SUCCESSFUL", "RECOMMENDED"}

# QuickBuild 16 reports missing resources as HTTP 500 with a body such as "HTTP 404 Not Found",
# "Configuration not found" or (download servlet) Hibernate's "No row with the given identifier".
_NOT_FOUND_BODY = re.compile(
    r"\b404\b|not found|No row with the given identifier", re.IGNORECASE
)
# The download servlet cannot serve the log of a build that is still running.
_LOG_IN_PROGRESS_BODY = re.compile(r"EOFException")

# Methods that are safe to repeat after a timeout or server error. A POST (trigger a build,
# start a backup) is only retried when the connection was never established.
_IDEMPOTENT_METHODS = {"GET", "HEAD", "OPTIONS", "DELETE"}

_NUMERIC_ID = re.compile(r"\d{1,19}")
_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,63}")

# Hard limits for builds.get_log
MAX_LOG_TAIL_LINES = 2000
MAX_LOG_TAIL_BYTES = 1024 * 1024


def _parse_datetime(value: Optional[Union[str, int, float]]) -> datetime:
    """Parse an ISO-8601 string or epoch-milliseconds value, falling back to current UTC time."""
    if value is None or value == "":
        return datetime.now(timezone.utc)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    text = str(value)
    if text.isdigit():
        return datetime.fromtimestamp(int(text) / 1000, tz=timezone.utc)
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _response_text(response: Any) -> str:
    """Return the response body as text ("" when unavailable)."""
    text = getattr(response, "text", "")
    return text if isinstance(text, str) else ""


def _as_list(response: Any) -> List[dict]:
    """Normalize an API response into a list of objects."""
    if not response:
        return []
    return response if isinstance(response, list) else [response]


def _to_id(value: Any) -> Union[int, str]:
    """QuickBuild identifiers are numeric; send them as numbers when possible."""
    text = str(value)
    return int(text) if text.isdigit() else text


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _warn_about_cidr_no_proxy() -> None:
    """httpx honours NO_PROXY hosts, domain suffixes and exact IPs, but not CIDR ranges."""
    no_proxy = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    ranges = [entry.strip() for entry in no_proxy.split(",") if "/" in entry]
    if ranges:
        logger.warning(
            "NO_PROXY entries %s are CIDR ranges, which are not supported; requests to those "
            "addresses still use the proxy. List the QuickBuild host name, domain or IP instead.",
            ", ".join(ranges),
        )


def require_numeric_id(value: Any, name: str) -> str:
    """Validate a QuickBuild numeric id before it is placed in a URL path.

    httpx resolves "." and ".." path segments, so an unchecked id such as "../users" would
    address a different REST resource with the server's credentials.
    """
    text = str(value).strip() if value is not None else ""
    if not _NUMERIC_ID.fullmatch(text):
        raise ValueError(f"{name} must be a numeric QuickBuild id (got '{value}')")
    return text


def require_request_id(value: Any) -> str:
    """Validate a build request id (a UUID in QuickBuild 16) before it is placed in a URL path."""
    text = str(value).strip() if value is not None else ""
    if not _REQUEST_ID.fullmatch(text):
        raise ValueError(f"request_id must be a QuickBuild build request id (got '{value}')")
    return text


class QuickBuildClient:
    """Client for interacting with the QuickBuild REST API (JSON edition)"""

    def __init__(
        self,
        cache_ttl_configs: Optional[int] = None,
        cache_ttl_agents: Optional[int] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or Settings.from_env()
        self.base_url = self.settings.qb_url
        self.username = self.settings.qb_user
        self.password = self.settings.qb_password
        self.auth_mode = self.settings.auth_mode
        self.backup_dir = self.settings.backup_dir

        if not self.settings.verify_ssl:
            logger.warning(
                "QB_VERIFY_SSL=false: TLS certificates of %s are NOT verified", self.base_url
            )
        _warn_about_cidr_no_proxy()

        self.client = httpx.AsyncClient(
            timeout=self.settings.timeout,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            auth=self._http_auth(),
            # QuickBuild returns XML unless JSON is explicitly requested
            headers={"Accept": "application/json"},
            verify=self.settings.ssl_verify(),
            # Honour HTTPS_PROXY / HTTP_PROXY / ALL_PROXY / NO_PROXY
            trust_env=True,
        )
        self.authenticated = False

        self.cache_ttl_configs = (
            cache_ttl_configs if cache_ttl_configs is not None else self.settings.cache_ttl_configs
        )
        self.cache_ttl_agents = (
            cache_ttl_agents if cache_ttl_agents is not None else self.settings.cache_ttl_agents
        )
        self._cache: Dict[str, tuple[float, Any]] = {}

    def _http_auth(self) -> Optional[httpx.Auth]:
        if self.auth_mode == "basic":
            return httpx.BasicAuth(self.username, self.password)
        if self.auth_mode == "token":
            # QuickBuild access tokens replace the password in HTTP Basic credentials.
            return httpx.BasicAuth(self.username, self.settings.qb_token)
        return None

    async def __aenter__(self) -> "QuickBuildClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    def clear_cache(self, key: Optional[str] = None) -> None:
        """Clear cached responses for a specific key or all keys."""
        if key is None:
            self._cache.clear()
        else:
            self._cache.pop(key, None)

    def _get_cached(self, key: str, ttl: int) -> Any:
        if ttl <= 0 or key not in self._cache:
            return None
        cached_at, value = self._cache[key]
        if (time.monotonic() - cached_at) < ttl:
            return value
        self._cache.pop(key, None)
        return None

    def _set_cached(self, key: str, value: Any, ttl: int) -> None:
        if ttl > 0:
            self._cache[key] = (time.monotonic(), value)

    async def authenticate(self) -> bool:
        """Authenticate with QuickBuild API"""
        if self.auth_mode in ("basic", "token"):
            # Credentials travel with every request (HTTP Basic); there is no login call.
            self.authenticated = True
            return True

        try:
            auth_url = f"{self.base_url}/rest/authentication"
            response = await self.client.post(
                auth_url,
                json={"username": self.username, "password": self.password},
            )

            if response.status_code == 200:
                self.authenticated = True
                logger.info("Successfully authenticated with QuickBuild")
                return True

            logger.error(f"Authentication failed: {response.status_code}")
            raise AuthenticationError(
                "Failed to authenticate with QuickBuild",
                ERROR_MAPPINGS.get(response.status_code, "UNKNOWN_ERROR"),
            )

        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.error(f"Connection error during authentication: {e}")
            raise QuickBuildUnavailableError(
                "Cannot connect to QuickBuild server",
                ERROR_MAPPINGS["CONNECTION_ERROR"],
            )
        except AuthenticationError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error during authentication: {e}")
            raise QuickBuildError(
                f"Authentication error: {str(e)}",
                "AUTHENTICATION_ERROR",
            )

    async def _ensure_authenticated(self) -> None:
        """Ensure client is authenticated before making API calls"""
        if not self.authenticated:
            await self.authenticate()

    def _auth_failure(self) -> AuthenticationError:
        hint = {
            "basic": " (check QB_USER/QB_PASSWORD)",
            "token": " (check QB_USER/QB_TOKEN)",
            "session": " after retries",
        }[self.auth_mode]
        return AuthenticationError("Authentication failed with QuickBuild" + hint, ERROR_MAPPINGS[401])

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Make authenticated request to QuickBuild API with retry logic"""
        await self._ensure_authenticated()

        url = f"{self.base_url}/rest/{endpoint.lstrip('/')}"
        max_retries = 3
        idempotent = method.upper() in _IDEMPOTENT_METHODS

        for attempt in range(max_retries):
            try:
                response = await self.client.request(method, url, **kwargs)

                if response.status_code == 401:
                    self.authenticated = False
                    if self.auth_mode == "session" and attempt < max_retries - 1:
                        await self.authenticate()
                        continue
                    raise self._auth_failure()
                if response.status_code == 404 or (
                    response.status_code >= 500 and _NOT_FOUND_BODY.search(_response_text(response))
                ):
                    raise ResourceNotFoundError(
                        f"Resource not found: {endpoint}",
                        ERROR_MAPPINGS[404],
                    )
                if response.status_code >= 500:
                    if idempotent and attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise QuickBuildServerError(
                        f"QuickBuild server error: {response.status_code}"
                        + (f" - {_response_text(response)[:200]}" if _response_text(response) else ""),
                        ERROR_MAPPINGS[500],
                    )
                if response.status_code >= 400:
                    raise QuickBuildError(
                        f"API error: {response.status_code} - {_response_text(response)}",
                        f"HTTP_{response.status_code}",
                    )

                if not response.content:
                    return {}
                try:
                    return response.json()
                except ValueError:
                    return {"raw": response.text}

            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                tls_error = self._tls_failure(exc)
                if tls_error is not None:
                    raise tls_error from exc  # retrying cannot fix an untrusted certificate
                # A failed connect never reached QuickBuild, so it is safe to retry any method;
                # a timeout after sending a POST may already have triggered a build.
                retryable = idempotent or isinstance(exc, httpx.ConnectError)
                if retryable and attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise self._connection_failure(exc) from exc

        raise QuickBuildError("Max retries exceeded", "MAX_RETRIES_EXCEEDED")

    def _tls_failure(self, exc: Exception) -> Optional[QuickBuildUnavailableError]:
        """Name certificate problems explicitly; httpx reports them as plain ConnectErrors."""
        detail = str(exc)
        if "CERTIFICATE_VERIFY_FAILED" in detail or "certificate verify failed" in detail.lower():
            return QuickBuildUnavailableError(
                f"TLS certificate of {self.base_url} is not trusted ({detail}). Set QB_CA_BUNDLE "
                "to the CA bundle that signed it (QB_VERIFY_SSL=false only for testing).",
                "TLS_VERIFY_FAILED",
            )
        return None

    def _connection_failure(self, exc: Exception) -> QuickBuildUnavailableError:
        if isinstance(exc, httpx.TimeoutException):
            return QuickBuildUnavailableError(
                f"QuickBuild did not answer within {self.settings.timeout:g}s (QB_TIMEOUT)",
                ERROR_MAPPINGS["CONNECTION_ERROR"],
            )
        return QuickBuildUnavailableError(
            "Cannot connect to QuickBuild server", ERROR_MAPPINGS["CONNECTION_ERROR"]
        )

    async def get(self, endpoint: str, params: Optional[dict] = None) -> Any:
        """Make GET request to QuickBuild API"""
        return await self._make_request("GET", endpoint, params=params)

    async def post(self, endpoint: str, data: Optional[dict] = None) -> Any:
        """Make POST request to QuickBuild API"""
        return await self._make_request("POST", endpoint, json=data)

    async def delete(self, endpoint: str) -> Any:
        """Make DELETE request to QuickBuild API"""
        return await self._make_request("DELETE", endpoint)

    # ------------------------------------------------------------------ configurations

    async def get_configurations(self) -> List[Configuration]:
        """Get all build configurations (GET /rest/configurations?recursive=true)"""
        cached = self._get_cached("configurations", self.cache_ttl_configs)
        if cached is not None:
            return cached

        try:
            response = await self.get("configurations", params={"recursive": "true"})
            configurations = []
            for config in _as_list(response):
                parent = config.get("parent", config.get("parentId"))
                enabled = (
                    not config["disabled"] if "disabled" in config else config.get("enabled", True)
                )
                configurations.append(
                    Configuration(
                        id=str(config.get("id", "")),
                        name=config.get("name", ""),
                        description=config.get("description", ""),
                        parent_id=str(parent) if parent is not None else None,
                        enabled=bool(enabled),
                        path=config.get("pathName", config.get("path", "")) or "",
                    )
                )

            self._set_cached("configurations", configurations, self.cache_ttl_configs)
            logger.info(f"Retrieved {len(configurations)} configurations")
            return configurations

        except Exception as e:
            logger.error(f"Error retrieving configurations: {e}")
            raise

    async def resolve_configuration_id(self, value: Any) -> str:
        """Accept a numeric configuration id or a configuration path such as "root/team/app".

        Paths are resolved with GET /rest/ids?configuration_path= (sent as a query parameter,
        so a path cannot address another REST resource) and cached for QB_CACHE_TTL_CONFIGS.
        """
        text = str(value).strip() if value is not None else ""
        if _NUMERIC_ID.fullmatch(text):
            return text
        if not text or len(text) > 1000 or any(ord(c) < 32 for c in text):
            raise ValueError(
                f"configuration_id must be a numeric id or a configuration path (got '{value}')"
            )
        cache_key = f"configuration-path:{text}"
        cached = self._get_cached(cache_key, self.cache_ttl_configs)
        if cached is not None:
            return cached
        response = await self.get("ids", params={"configuration_path": text})
        resolved = response.get("raw") if isinstance(response, dict) else response
        resolved = str(resolved).strip() if resolved is not None else ""
        if not _NUMERIC_ID.fullmatch(resolved):
            raise ResourceNotFoundError(f"Configuration not found: {text}", ERROR_MAPPINGS[404])
        self._set_cached(cache_key, resolved, self.cache_ttl_configs)
        return resolved

    # ------------------------------------------------------------------ builds

    @staticmethod
    def _steps_from(step_runtimes: Any) -> List[dict]:
        if not isinstance(step_runtimes, dict):
            return []
        steps = []
        for path, runtime in step_runtimes.items():
            if not isinstance(runtime, dict):
                continue
            begin = runtime.get("beginTime")
            steps.append(
                {
                    "path": path,
                    "status": runtime.get("status", ""),
                    "node": runtime.get("nodeAddress"),
                    "start_time": _parse_datetime(begin).isoformat() if begin else None,
                    "duration_ms": _int_or_none(runtime.get("duration")),
                }
            )
        steps.sort(key=lambda step: (step["start_time"] or "", step["path"]))
        return steps

    @staticmethod
    def _variables_from(values: Any) -> Dict[str, Optional[str]]:
        """Build request variables; a value with a mask is reported masked, never in clear text."""
        if not isinstance(values, dict):
            return {}
        variables: Dict[str, Optional[str]] = {}
        for name, value in values.items():
            if isinstance(value, dict):
                masked = value.get("masked")
                variables[name] = str(masked) if masked is not None else value.get("string")
            else:
                variables[name] = None if value is None else str(value)
        return variables

    @classmethod
    def _build_from(cls, build_data: dict, config_id: str) -> Build:
        """Map a QuickBuild build object to the Build model."""
        status = str(build_data.get("status", ""))
        start_value = build_data.get("beginDate", build_data.get("startTime"))
        start_time = _parse_datetime(start_value)

        end_time: Optional[datetime] = None
        if build_data.get("endTime"):
            end_time = _parse_datetime(build_data["endTime"])
        elif build_data.get("duration") is not None and start_value and status.upper() != "RUNNING":
            end_time = start_time + timedelta(milliseconds=int(build_data["duration"]))

        revisions = {}
        for name, runtime in (build_data.get("repositoryRuntimes") or {}).items():
            revision = (runtime or {}).get("revisionDOM") if isinstance(runtime, dict) else None
            if isinstance(revision, dict) and revision.get("value") is not None:
                revisions[name] = str(revision["value"])

        requester = build_data.get("requester")
        return Build(
            id=str(build_data.get("id", "")),
            configuration_id=str(build_data.get("configuration", config_id)),
            version=build_data.get("version", ""),
            status=status,
            start_time=start_time,
            end_time=end_time,
            success=status.upper() in SUCCESS_STATUSES,
            requester_id=str(requester) if requester is not None else None,
            duration_ms=_int_or_none(build_data.get("duration")),
            wait_duration_ms=_int_or_none(build_data.get("waitDuration")),
            scheduled=bool(build_data.get("scheduled", False)),
            node=build_data.get("masterNodeAddress"),
            steps=cls._steps_from(build_data.get("stepRuntimes")),
            revisions=revisions,
            variables=cls._variables_from(build_data.get("secretAwareVariableValues")),
        )

    async def get_latest_build_status(self, config_id: str) -> Optional[Build]:
        """Get latest build of a configuration (GET /rest/latest_builds/{id}; 204 = no builds)"""
        try:
            config_id = await self.resolve_configuration_id(config_id)
            response = await self.get(f"latest_builds/{config_id}")
            builds = _as_list(response)
            if not builds:
                return None
            return self._build_from(builds[0], config_id)

        except Exception as e:
            logger.error(f"Error retrieving build status for config {config_id}: {e}")
            raise

    async def get_build(self, build_id: str) -> Build:
        """Get one build with its steps and revisions (GET /rest/builds/{id})"""
        build_id = require_numeric_id(build_id, "build_id")
        response = await self.get(f"builds/{build_id}")
        if not isinstance(response, dict) or "id" not in response:
            raise ResourceNotFoundError(f"Build {build_id} not found", ERROR_MAPPINGS[404])
        return self._build_from(response, "")

    async def search_builds(
        self,
        status: Optional[str] = None,
        configuration_id: Optional[str] = None,
        recursive: bool = True,
        count: int = 20,
    ) -> List[Build]:
        """Search builds (GET /rest/builds?status=&configuration_id=&recursive=&count=)

        QuickBuild requires `count`; without configuration_id the search spans all configurations.
        """
        params: Dict[str, str] = {"count": str(max(1, int(count)))}
        if status:
            params["status"] = status.upper()
        if configuration_id is not None and str(configuration_id) != "":
            params["configuration_id"] = await self.resolve_configuration_id(configuration_id)
            params["recursive"] = "true" if recursive else "false"
        response = await self.get("builds", params=params)
        return [self._build_from(b, "") for b in _as_list(response) if isinstance(b, dict)]

    @staticmethod
    def _build_request_from(data: dict) -> BuildRequest:
        requester = data.get("requesterId")
        variables = data.get("variables") if isinstance(data.get("variables"), dict) else {}
        return BuildRequest(
            id=str(data.get("id", "")),
            configuration_id=str(data.get("configurationId", "")),
            status=str(data.get("status", "")),
            requested_at=_parse_datetime(data.get("requestDate")),
            requester_id=str(requester) if requester is not None else None,
            priority=_int_or_none(data.get("priority")),
            scheduled=bool(data.get("scheduled", False)),
            variables={str(k): str(v) for k, v in variables.items()},
        )

    async def get_build_requests(self, configuration_id: Optional[str] = None) -> List[BuildRequest]:
        """List queued and running build requests (GET /rest/build_requests[?configuration_id=])"""
        params = None
        if configuration_id is not None and str(configuration_id) != "":
            params = {"configuration_id": await self.resolve_configuration_id(configuration_id)}
        response = await self.get("build_requests", params=params)
        return [self._build_request_from(r) for r in _as_list(response) if isinstance(r, dict)]

    async def cancel_build_request(self, request_id: str) -> Dict[str, Any]:
        """Cancel a queued or running build request (DELETE /rest/build_requests/{id}; 204)

        A running build is stopped and ends as CANCELLED.
        """
        request_id = require_request_id(request_id)
        await self.delete(f"build_requests/{request_id}")
        logger.info(f"Cancelled build request {request_id}")
        return {
            "request_id": request_id,
            "status": "CANCELLED",
            "message": f"Build request {request_id} cancelled",
        }

    async def get_build_log(
        self, build_id: str, tail_lines: int = 200, max_bytes: int = 256 * 1024
    ) -> Dict[str, Any]:
        """Tail the log of a finished build (GET /download/{id}/log).

        QuickBuild 16 serves the whole log (no Range support), so the response is streamed and
        only the last `max_bytes` are kept in memory before the last `tail_lines` are returned.
        """
        build_id = require_numeric_id(build_id, "build_id")
        tail_lines = max(1, min(int(tail_lines), MAX_LOG_TAIL_LINES))
        max_bytes = max(1024, min(int(max_bytes), MAX_LOG_TAIL_BYTES))
        await self._ensure_authenticated()
        url = f"{self.base_url}/download/{build_id}/log"

        try:
            async with self.client.stream("GET", url, headers={"Accept": "*/*"}) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", "replace")
                    self._raise_for_download(response.status_code, body, build_id)
                buffer = bytearray()
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    buffer.extend(chunk)
                    if len(buffer) > max_bytes:
                        del buffer[: len(buffer) - max_bytes]
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise (self._tls_failure(exc) or self._connection_failure(exc)) from exc

        text = buffer.decode("utf-8", "replace")
        lines = text.splitlines()
        if total > len(buffer) and lines:
            lines = lines[1:]  # the first kept line was cut by the byte window
        tail = lines[-tail_lines:]
        return {
            "build_id": build_id,
            "lines": tail,
            "line_count": len(tail),
            "log_bytes": total,
            "truncated": total > len(buffer) or len(lines) > len(tail),
        }

    def _raise_for_download(self, status_code: int, body: str, build_id: str) -> None:
        if status_code == 401:
            self.authenticated = False
            raise self._auth_failure()
        if status_code == 404 or _NOT_FOUND_BODY.search(body):
            raise ResourceNotFoundError(f"Build {build_id} not found", ERROR_MAPPINGS[404])
        if _LOG_IN_PROGRESS_BODY.search(body):
            raise QuickBuildError(
                f"The log of build {build_id} is available once the build has finished",
                "LOG_NOT_AVAILABLE",
            )
        raise QuickBuildServerError(
            f"QuickBuild server error: {status_code}", ERROR_MAPPINGS.get(status_code, ERROR_MAPPINGS[500])
        )

    # ------------------------------------------------------------------ grid

    @staticmethod
    def _agent_from(agent: dict, default_status: str) -> Agent:
        """Map a QuickBuild grid node object to the Agent model.

        QuickBuild 16 grid nodes carry id/ip/port/hostName (no name or last-contact time;
        "lastPulse" is only reported for unauthorized and inactive agents).
        """
        address = agent.get("address") or agent.get("nodeAddress") or ""
        host, _, port = str(address).rpartition(":") if ":" in str(address) else (address, "", "")
        return Agent(
            name=agent.get("name") or agent.get("hostName") or address,
            status=agent.get("status") or default_status,
            last_contact=_parse_datetime(
                agent.get("lastContact") or agent.get("lastPulse") or agent.get("lastPingDate")
            ),
            ip_address=agent.get("ipAddress") or agent.get("ip") or host,
            port=int(agent.get("port") or port or 0),
        )

    async def get_agents(self) -> List[Agent]:
        """Get build agents (GET /rest/buildagents/active and /rest/buildagents/inactive)"""
        cached = self._get_cached("agents", self.cache_ttl_agents)
        if cached is not None:
            return cached

        try:
            active = await self.get("buildagents/active")
            inactive = await self.get("buildagents/inactive")
            agents = [self._agent_from(a, "online") for a in _as_list(active)]
            agents += [self._agent_from(a, "offline") for a in _as_list(inactive)]

            self._set_cached("agents", agents, self.cache_ttl_agents)
            logger.info(f"Retrieved {len(agents)} agents")
            return agents

        except Exception as e:
            logger.error(f"Error retrieving agents: {e}")
            raise

    async def get_unauthorized_agents(self) -> List[Agent]:
        """Agents waiting for authorization (GET /rest/buildagents/unauthorized; not cached)"""
        response = await self.get("buildagents/unauthorized")
        return [self._agent_from(a, "unauthorized") for a in _as_list(response) if isinstance(a, dict)]

    # ------------------------------------------------------------------ changes

    async def get_build_changes(self, build_id: str) -> List[Change]:
        """Get SCM changesets of a build (GET /rest/changes/commits/build/{id})"""
        try:
            build_id = require_numeric_id(build_id, "build_id")
            response = await self.get(f"changes/commits/build/{build_id}")
            changes = []
            for change in _as_list(response):
                modifications = [
                    m for m in (change.get("modifications") or []) if isinstance(m, dict)
                ]
                files = [m.get("path", "") for m in modifications]
                changes.append(
                    Change(
                        revision=str(change.get("id", change.get("revision", ""))),
                        author=change.get("user", change.get("author", "")),
                        message=change.get("comment", change.get("message", "")),
                        timestamp=_parse_datetime(change.get("date", change.get("timestamp"))),
                        files=files or change.get("files", []),
                        repository=change.get("repositoryName", "") or "",
                        modifications=[
                            {"action": m.get("action", ""), "path": m.get("path", "")}
                            for m in modifications
                        ],
                    )
                )

            logger.info(f"Retrieved {len(changes)} changes for build {build_id}")
            return changes

        except Exception as e:
            logger.error(f"Error retrieving changes for build {build_id}: {e}")
            raise

    # ------------------------------------------------------------------ writes

    async def trigger_build(self, config_id: str, variables: Optional[dict] = None) -> dict:
        """Request a new build (POST /rest/build_requests)"""
        try:
            data: Dict[str, Any] = {
                "configurationId": _to_id(await self.resolve_configuration_id(config_id)),
                "respectBuildCondition": False,
            }
            if variables:
                data["variables"] = variables

            response = await self.post("build_requests", data)
            response = response if isinstance(response, dict) else {}

            request_id = response.get("requestId", "")
            build_id = response.get("buildId", response.get("id", ""))
            # QuickBuild answers 204 (no body) when the request is aggregated into an existing one
            status = response.get("status") or ("QUEUED" if response else "AGGREGATED")

            result: Dict[str, Any] = {
                "build_id": str(build_id) if build_id is not None else "",
                "request_id": str(request_id),
                "configuration_id": config_id,
                "status": status,
                "message": f"Build triggered successfully for configuration {config_id}",
            }
            if variables:
                result["variables"] = variables

            logger.info(f"Requested build for configuration {config_id} (request {request_id})")
            return result

        except Exception as e:
            logger.error(f"Error triggering build for config {config_id}: {e}")
            raise

    async def get_version(self) -> Dict[str, Any]:
        """Get QuickBuild server version information (GET /rest/version)"""
        try:
            response = await self.get("version")
            if isinstance(response, dict):
                return {
                    "version": response.get("version") or response.get("raw", "unknown"),
                    **{k: v for k, v in response.items() if k != "raw"},
                }
            return {"version": str(response)}
        except Exception as e:
            logger.error(f"Error retrieving QuickBuild version: {e}")
            raise

    async def backup_database(self, backup_path: Optional[str] = None) -> Dict[str, Any]:
        """Back up the QuickBuild database on the server (POST /rest/backup)

        backup_path is a path on the QuickBuild server; defaults to a timestamped zip in
        QB_BACKUP_DIR (the server container's data volume).
        """
        try:
            target = backup_path or (
                f"{self.backup_dir}/quickbuild-"
                f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.zip"
            )
            data = {
                "backupTo": target,
                "excludeBuilds": False,
                "excludeMeasurements": False,
                "excludeAudits": False,
                "clearPasswords": False,
            }
            response = await self.post("backup", data)

            result: Dict[str, Any] = {
                "status": "initiated",
                "message": "Database backup initiated successfully",
                "backup_path": target,
            }

            if isinstance(response, dict):
                result.update({k: v for k, v in response.items() if k != "raw"})
                if "raw" in response:
                    result["details"] = response["raw"]
            elif response:
                result["details"] = str(response)

            logger.info(f"Initiated QuickBuild database backup to {target}")
            return result

        except Exception as e:
            logger.error(f"Error initiating database backup: {e}")
            raise

    async def close(self) -> None:
        """Close the HTTP client"""
        await self.client.aclose()
