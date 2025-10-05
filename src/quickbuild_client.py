import os
import asyncio
import logging
from typing import Dict, List, Optional, Any
import httpx
from datetime import datetime

from .exceptions import (
    QuickBuildError, AuthenticationError, ResourceNotFoundError,
    QuickBuildServerError, QuickBuildUnavailableError, ERROR_MAPPINGS
)
from .models import Configuration, Build, Agent, Change

logger = logging.getLogger(__name__)

class QuickBuildClient:
    """Client for interacting with QuickBuild REST API"""
    
    def __init__(self):
        self.base_url = os.getenv("QB_URL", "http://localhost:8810")
        self.username = os.getenv("QB_USER", "admin")
        self.password = os.getenv("QB_PASSWORD")
        
        if not self.password:
            raise ValueError("QB_PASSWORD environment variable is required")
        
        self.client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )
        self.authenticated = False
        
    async def authenticate(self) -> bool:
        """Authenticate with QuickBuild API"""
        try:
            auth_url = f"{self.base_url}/rest/authentication"
            response = await self.client.post(
                auth_url,
                json={"username": self.username, "password": self.password}
            )
            
            if response.status_code == 200:
                self.authenticated = True
                logger.info("Successfully authenticated with QuickBuild")
                return True
            else:
                logger.error(f"Authentication failed: {response.status_code}")
                raise AuthenticationError(
                    "Failed to authenticate with QuickBuild",
                    ERROR_MAPPINGS.get(response.status_code, "UNKNOWN_ERROR")
                )
                
        except httpx.ConnectError as e:
            logger.error(f"Connection error during authentication: {e}")
            raise QuickBuildUnavailableError(
                "Cannot connect to QuickBuild server",
                ERROR_MAPPINGS["CONNECTION_ERROR"]
            )
        except Exception as e:
            logger.error(f"Unexpected error during authentication: {e}")
            raise QuickBuildError(
                f"Authentication error: {str(e)}",
                "AUTHENTICATION_ERROR"
            )
    
    async def _ensure_authenticated(self):
        """Ensure client is authenticated before making API calls"""
        if not self.authenticated:
            await self.authenticate()
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make authenticated request to QuickBuild API with retry logic"""
        await self._ensure_authenticated()
        
        url = f"{self.base_url}/rest/{endpoint.lstrip('/')}"
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                response = await self.client.request(method, url, **kwargs)
                
                if response.status_code == 401:
                    # Re-authenticate and retry
                    self.authenticated = False
                    await self.authenticate()
                    continue
                elif response.status_code == 404:
                    raise ResourceNotFoundError(
                        f"Resource not found: {endpoint}",
                        ERROR_MAPPINGS[404]
                    )
                elif response.status_code >= 500:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    raise QuickBuildServerError(
                        f"QuickBuild server error: {response.status_code}",
                        ERROR_MAPPINGS[500]
                    )
                elif response.status_code >= 400:
                    raise QuickBuildError(
                        f"API error: {response.status_code} - {response.text}",
                        f"HTTP_{response.status_code}"
                    )
                
                return response.json() if response.content else {}
                
            except httpx.ConnectError as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise QuickBuildUnavailableError(
                    "Cannot connect to QuickBuild server",
                    ERROR_MAPPINGS["CONNECTION_ERROR"]
                )
        
        raise QuickBuildError("Max retries exceeded", "MAX_RETRIES_EXCEEDED")
    
    async def get(self, endpoint: str, params: dict = None) -> dict:
        """Make GET request to QuickBuild API"""
        return await self._make_request("GET", endpoint, params=params)
    
    async def post(self, endpoint: str, data: dict = None) -> dict:
        """Make POST request to QuickBuild API"""
        return await self._make_request("POST", endpoint, json=data)
    
    async def get_configurations(self) -> List[Configuration]:
        """Get all build configurations"""
        try:
            response = await self.get("configurations")
            configurations = []
            
            # Handle both single config and list responses
            config_data = response if isinstance(response, list) else [response]
            
            for config in config_data:
                configurations.append(Configuration(
                    id=str(config.get("id", "")),
                    name=config.get("name", ""),
                    description=config.get("description", ""),
                    parent_id=str(config.get("parentId")) if config.get("parentId") else None,
                    enabled=config.get("enabled", True)
                ))
            
            logger.info(f"Retrieved {len(configurations)} configurations")
            return configurations
            
        except Exception as e:
            logger.error(f"Error retrieving configurations: {e}")
            raise
    
    async def get_latest_build_status(self, config_id: str) -> Optional[Build]:
        """Get latest build status for a configuration"""
        try:
            response = await self.get(f"builds", params={"configuration": config_id, "count": 1})
            
            if not response or (isinstance(response, list) and len(response) == 0):
                return None
            
            build_data = response[0] if isinstance(response, list) else response
            
            return Build(
                id=str(build_data.get("id", "")),
                configuration_id=config_id,
                version=build_data.get("version", ""),
                status=build_data.get("status", ""),
                start_time=datetime.fromisoformat(build_data.get("startTime", "").replace("Z", "+00:00")) if build_data.get("startTime") else datetime.now(),
                end_time=datetime.fromisoformat(build_data.get("endTime", "").replace("Z", "+00:00")) if build_data.get("endTime") else None,
                success=build_data.get("status", "").lower() == "successful"
            )
            
        except Exception as e:
            logger.error(f"Error retrieving build status for config {config_id}: {e}")
            raise
    
    async def get_agents(self) -> List[Agent]:
        """Get all build agents and their status"""
        try:
            response = await self.get("agents")
            agents = []
            
            # Handle both single agent and list responses
            agent_data = response if isinstance(response, list) else [response]
            
            for agent in agent_data:
                agents.append(Agent(
                    name=agent.get("name", ""),
                    status=agent.get("status", "unknown"),
                    last_contact=datetime.fromisoformat(agent.get("lastContact", "").replace("Z", "+00:00")) if agent.get("lastContact") else datetime.now(),
                    ip_address=agent.get("ipAddress", ""),
                    port=int(agent.get("port", 0))
                ))
            
            logger.info(f"Retrieved {len(agents)} agents")
            return agents
            
        except Exception as e:
            logger.error(f"Error retrieving agents: {e}")
            raise
    
    async def get_build_changes(self, build_id: str) -> List[Change]:
        """Get SCM changes for a specific build"""
        try:
            response = await self.get(f"builds/{build_id}/changes")
            changes = []
            
            # Handle both single change and list responses
            change_data = response if isinstance(response, list) else [response]
            
            for change in change_data:
                changes.append(Change(
                    revision=change.get("revision", ""),
                    author=change.get("author", ""),
                    message=change.get("message", ""),
                    timestamp=datetime.fromisoformat(change.get("timestamp", "").replace("Z", "+00:00")) if change.get("timestamp") else datetime.now(),
                    files=change.get("files", [])
                ))
            
            logger.info(f"Retrieved {len(changes)} changes for build {build_id}")
            return changes
            
        except Exception as e:
            logger.error(f"Error retrieving changes for build {build_id}: {e}")
            raise
    
    async def trigger_build(self, config_id: str, variables: dict = None) -> dict:
        """Trigger a new build for a configuration"""
        try:
            endpoint = f"builds"
            data = {
                "configurationId": config_id
            }
            
            if variables:
                data["variables"] = variables
            
            response = await self.post(endpoint, data)
            
            # Extract build information from response
            build_id = response.get("id", "")
            status = response.get("status", "QUEUED")
            
            result = {
                "build_id": str(build_id),
                "configuration_id": config_id,
                "status": status,
                "message": f"Build triggered successfully for configuration {config_id}"
            }
            
            if variables:
                result["variables"] = variables
            
            logger.info(f"Triggered build {build_id} for configuration {config_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error triggering build for config {config_id}: {e}")
            raise
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()