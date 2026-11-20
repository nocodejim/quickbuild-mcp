import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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


def _parse_datetime(value: Optional[str]) -> datetime:
    """Parse an ISO-8601 datetime string, falling back to current UTC time."""
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class QuickBuildClient:
    """Client for interacting with QuickBuild REST API"""

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

        self.client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
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
                    if attempt < max_retries - 1:
                        await self.authenticate()
                        continue
                    raise AuthenticationError(
                        "Authentication failed with QuickBuild after retries",
                        ERROR_MAPPINGS[401],
                    )
                if response.status_code == 404:
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
                        f"API error: {response.status_code} - {response.text}",
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
        """Get all build configurations"""
        cached = self._get_cached("configurations", self.cache_ttl_configs)
        if cached is not None:
            return cached

        try:
            response = await self.get("configurations")
            if not response:
                return []

            config_data = response if isinstance(response, list) else [response]
            configurations = [
                Configuration(
                    id=str(config.get("id", "")),
                    name=config.get("name", ""),
                    description=config.get("description", ""),
                    parent_id=str(config.get("parentId")) if config.get("parentId") else None,
                    enabled=config.get("enabled", True),
                )
                for config in config_data
            ]

            self._set_cached("configurations", configurations, self.cache_ttl_configs)
            logger.info(f"Retrieved {len(configurations)} configurations")
            return configurations

        except Exception as e:
            logger.error(f"Error retrieving configurations: {e}")
            raise

    async def get_latest_build_status(self, config_id: str) -> Optional[Build]:
        """Get latest build status for a configuration"""
        try:
            response = await self.get("builds", params={"configuration": config_id, "count": 1})

            if not response or (isinstance(response, list) and len(response) == 0):
                return None

            build_data = response[0] if isinstance(response, list) else response

            return Build(
                id=str(build_data.get("id", "")),
                configuration_id=config_id,
                version=build_data.get("version", ""),
                status=build_data.get("status", ""),
                start_time=_parse_datetime(build_data.get("startTime")),
                end_time=_parse_datetime(build_data.get("endTime")) if build_data.get("endTime") else None,
                success=build_data.get("status", "").lower() == "successful",
            )

        except Exception as e:
            logger.error(f"Error retrieving build status for config {config_id}: {e}")
            raise

    async def get_agents(self) -> List[Agent]:
        """Get all build agents and their status"""
        cached = self._get_cached("agents", self.cache_ttl_agents)
        if cached is not None:
            return cached

        try:
            response = await self.get("agents")
            if not response:
                return []

            agent_data = response if isinstance(response, list) else [response]
            agents = [
                Agent(
                    name=agent.get("name", ""),
                    status=agent.get("status", "unknown"),
                    last_contact=_parse_datetime(agent.get("lastContact")),
                    ip_address=agent.get("ipAddress", ""),
                    port=int(agent.get("port", 0)),
                )
                for agent in agent_data
            ]

            self._set_cached("agents", agents, self.cache_ttl_agents)
            logger.info(f"Retrieved {len(agents)} agents")
            return agents

        except Exception as e:
            logger.error(f"Error retrieving agents: {e}")
            raise

    async def get_build_changes(self, build_id: str) -> List[Change]:
        """Get SCM changes for a specific build"""
        try:
            response = await self.get(f"builds/{build_id}/changes")
            if not response:
                return []

            change_data = response if isinstance(response, list) else [response]
            changes = [
                Change(
                    revision=change.get("revision", ""),
                    author=change.get("author", ""),
                    message=change.get("message", ""),
                    timestamp=_parse_datetime(change.get("timestamp")),
                    files=change.get("files", []),
                )
                for change in change_data
            ]

            logger.info(f"Retrieved {len(changes)} changes for build {build_id}")
            return changes

        except Exception as e:
            logger.error(f"Error retrieving changes for build {build_id}: {e}")
            raise

    async def trigger_build(self, config_id: str, variables: Optional[dict] = None) -> dict:
        """Trigger a new build for a configuration"""
        try:
            data: Dict[str, Any] = {"configurationId": config_id}
            if variables:
                data["variables"] = variables

            response = await self.post("builds", data)

            build_id = response.get("id", "") if isinstance(response, dict) else ""
            status = response.get("status", "QUEUED") if isinstance(response, dict) else "QUEUED"

            result: Dict[str, Any] = {
                "build_id": str(build_id),
                "configuration_id": config_id,
                "status": status,
                "message": f"Build triggered successfully for configuration {config_id}",
            }
            if variables:
                result["variables"] = variables

            logger.info(f"Triggered build {build_id} for configuration {config_id}")
            return result

        except Exception as e:
            logger.error(f"Error triggering build for config {config_id}: {e}")
            raise

    async def get_version(self) -> Dict[str, Any]:
        """Get QuickBuild server version information"""
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
        """Initiate a server-side QuickBuild database backup"""
        try:
            data = {"backupPath": backup_path} if backup_path else None
            response = await self.post("backup", data)

            result: Dict[str, Any] = {
                "status": "initiated",
                "message": "Database backup initiated successfully",
            }
            if backup_path:
                result["backup_path"] = backup_path

            if isinstance(response, dict):
                result.update({k: v for k, v in response.items() if k != "raw"})
                if "raw" in response:
                    result["details"] = response["raw"]
            elif response:
                result["details"] = str(response)

            logger.info("Initiated QuickBuild database backup")
            return result

        except Exception as e:
            logger.error(f"Error initiating database backup: {e}")
            raise

    async def close(self) -> None:
        """Close the HTTP client"""
        await self.client.aclose()
