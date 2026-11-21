import asyncio
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union

import httpx
from dotenv import load_dotenv

from .exceptions import (
    AuthenticationError,
    ERROR_MAPPINGS,
    QuickBuildError,
    QuickBuildServerError,
    QuickBuildUnavailableError,
    ResourceNotFoundError,
)
from .models import Agent, Build, Change, Configuration

load_dotenv()

logger = logging.getLogger(__name__)

# Supported authentication modes (QB_AUTH_MODE):
#   basic   - HTTP Basic credentials on every request. This is how the QuickBuild REST API
#             authenticates (QuickBuild 10-16), and the default.
#   session - legacy login via POST /rest/authentication, then rely on the session cookie
#             (only for deployments/proxies that expose such an endpoint).
AUTH_MODES = ("basic", "session")

# Build statuses that indicate a successful build
SUCCESS_STATUSES = {"SUCCESSFUL", "RECOMMENDED"}

# QuickBuild 16 reports some missing resources as HTTP 500 with a plain-text body such as
# "HTTP 404 Not Found" or "Configuration not found".
_NOT_FOUND_BODY = re.compile(r"\b404\b|not found", re.IGNORECASE)


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


class QuickBuildClient:
    """Client for interacting with the QuickBuild REST API (JSON edition)"""

    def __init__(
        self,
        cache_ttl_configs: Optional[int] = None,
        cache_ttl_agents: Optional[int] = None,
    ):
        self.base_url = os.getenv("QB_URL", "http://localhost:8810").rstrip("/")
        self.username = os.getenv("QB_USER", "admin")
        self.password = os.getenv("QB_PASSWORD")

        if not self.password:
            raise ValueError("QB_PASSWORD environment variable is required")

        self.auth_mode = os.getenv("QB_AUTH_MODE", "basic").strip().lower()
        if self.auth_mode not in AUTH_MODES:
            raise ValueError(
                f"QB_AUTH_MODE must be one of {', '.join(AUTH_MODES)} (got '{self.auth_mode}')"
            )

        self.backup_dir = os.getenv("QB_BACKUP_DIR", "/opt/quickbuild/data/backup").rstrip("/")

        self.client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            auth=httpx.BasicAuth(self.username, self.password) if self.auth_mode == "basic" else None,
            # QuickBuild returns XML unless JSON is explicitly requested
            headers={"Accept": "application/json"},
        )
        self.authenticated = False

        self.cache_ttl_configs = (
            cache_ttl_configs
            if cache_ttl_configs is not None
            else int(os.getenv("QB_CACHE_TTL_CONFIGS", "300"))
        )
        self.cache_ttl_agents = (
            cache_ttl_agents
            if cache_ttl_agents is not None
            else int(os.getenv("QB_CACHE_TTL_AGENTS", "30"))
        )
        self._cache: Dict[str, tuple[float, Any]] = {}

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
        if self.auth_mode == "basic":
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

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Make authenticated request to QuickBuild API with retry logic"""
        await self._ensure_authenticated()

        url = f"{self.base_url}/rest/{endpoint.lstrip('/')}"
        max_retries = 3

        for attempt in range(max_retries):
            try:
                response = await self.client.request(method, url, **kwargs)

                if response.status_code == 401:
                    self.authenticated = False
                    if self.auth_mode == "session" and attempt < max_retries - 1:
                        await self.authenticate()
                        continue
                    raise AuthenticationError(
                        "Authentication failed with QuickBuild"
                        + (" after retries" if self.auth_mode == "session" else " (check QB_USER/QB_PASSWORD)"),
                        ERROR_MAPPINGS[401],
                    )
                if response.status_code == 404 or (
                    response.status_code >= 500 and _NOT_FOUND_BODY.search(_response_text(response))
                ):
                    raise ResourceNotFoundError(
                        f"Resource not found: {endpoint}",
                        ERROR_MAPPINGS[404],
                    )
                if response.status_code >= 500:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise QuickBuildServerError(
                        f"QuickBuild server error: {response.status_code}",
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

            except (httpx.ConnectError, httpx.TimeoutException):
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise QuickBuildUnavailableError(
                    "Cannot connect to QuickBuild server",
                    ERROR_MAPPINGS["CONNECTION_ERROR"],
                )

        raise QuickBuildError("Max retries exceeded", "MAX_RETRIES_EXCEEDED")

    async def get(self, endpoint: str, params: Optional[dict] = None) -> Any:
        """Make GET request to QuickBuild API"""
        return await self._make_request("GET", endpoint, params=params)

    async def post(self, endpoint: str, data: Optional[dict] = None) -> Any:
        """Make POST request to QuickBuild API"""
        return await self._make_request("POST", endpoint, json=data)

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
                    )
                )

            self._set_cached("configurations", configurations, self.cache_ttl_configs)
            logger.info(f"Retrieved {len(configurations)} configurations")
            return configurations

        except Exception as e:
            logger.error(f"Error retrieving configurations: {e}")
            raise

    @staticmethod
    def _build_from(build_data: dict, config_id: str) -> Build:
        """Map a QuickBuild build object to the Build model."""
        status = str(build_data.get("status", ""))
        start_value = build_data.get("beginDate", build_data.get("startTime"))
        start_time = _parse_datetime(start_value)

        end_time: Optional[datetime] = None
        if build_data.get("endTime"):
            end_time = _parse_datetime(build_data["endTime"])
        elif build_data.get("duration") is not None and start_value and status.upper() != "RUNNING":
            end_time = start_time + timedelta(milliseconds=int(build_data["duration"]))

        return Build(
            id=str(build_data.get("id", "")),
            configuration_id=str(build_data.get("configuration", config_id)),
            version=build_data.get("version", ""),
            status=status,
            start_time=start_time,
            end_time=end_time,
            success=status.upper() in SUCCESS_STATUSES,
        )

    async def get_latest_build_status(self, config_id: str) -> Optional[Build]:
        """Get latest build of a configuration (GET /rest/latest_builds/{id}; 204 = no builds)"""
        try:
            response = await self.get(f"latest_builds/{config_id}")
            builds = _as_list(response)
            if not builds:
                return None
            return self._build_from(builds[0], config_id)

        except Exception as e:
            logger.error(f"Error retrieving build status for config {config_id}: {e}")
            raise

    @staticmethod
    def _agent_from(agent: dict, default_status: str) -> Agent:
        """Map a QuickBuild grid node object to the Agent model.

        QuickBuild 16 grid nodes carry id/ip/port/hostName (no name or last-contact time;
        "lastPulse" is only reported for unauthorized agents).
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

    async def get_build_changes(self, build_id: str) -> List[Change]:
        """Get SCM changesets of a build (GET /rest/changes/commits/build/{id})"""
        try:
            response = await self.get(f"changes/commits/build/{build_id}")
            changes = []
            for change in _as_list(response):
                modifications = change.get("modifications") or []
                files = [m.get("path", "") for m in modifications if isinstance(m, dict)]
                changes.append(
                    Change(
                        revision=str(change.get("id", change.get("revision", ""))),
                        author=change.get("user", change.get("author", "")),
                        message=change.get("comment", change.get("message", "")),
                        timestamp=_parse_datetime(change.get("date", change.get("timestamp"))),
                        files=files or change.get("files", []),
                    )
                )

            logger.info(f"Retrieved {len(changes)} changes for build {build_id}")
            return changes

        except Exception as e:
            logger.error(f"Error retrieving changes for build {build_id}: {e}")
            raise

    async def trigger_build(self, config_id: str, variables: Optional[dict] = None) -> dict:
        """Request a new build (POST /rest/build_requests)"""
        try:
            data: Dict[str, Any] = {
                "configurationId": _to_id(config_id),
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
