"""
QuickBuild 16 REST API contract tests for QuickBuildClient.

Requests go through a real httpx client (MockTransport), so auth headers, URLs, query
params and request bodies are asserted exactly. Response payloads were captured from a
live QuickBuild 16.0.37 server (Java 21, SQL Server 2025) during the Phase 2 upgrade.
"""
import base64
import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.exceptions import AuthenticationError, ResourceNotFoundError
from src.quickbuild_client import QuickBuildClient, _parse_datetime

BASE_ENV = {"QB_URL": "http://qb:8810", "QB_USER": "admin", "QB_PASSWORD": "s3cret!"}

# --- Payloads captured from QuickBuild 16.0.37 (trimmed to the fields that matter) ---
CONFIGURATIONS = [
    {"@class": "com.pmease.quickbuild.model.Configuration", "id": 1, "disabled": False,
     "name": "root", "pathName": "root", "order": 100},
    {"@class": "com.pmease.quickbuild.model.Configuration", "id": 2, "disabled": True,
     "parent": 1, "name": "~maintenance", "pathName": "root/~maintenance", "order": 100},
    {"@class": "com.pmease.quickbuild.model.Configuration", "id": 3, "disabled": False,
     "parent": 2, "name": "sync configurations",
     "description": "This configuration is created to demonstrate ...",
     "pathName": "root/~maintenance/sync configurations", "order": 100},
]
LATEST_BUILD = {
    "id": 1, "configuration": 1, "version": "1.0.0", "scheduled": False,
    "status": "SUCCESSFUL", "statusDate": "2026-11-21T01:06:50.716+00:00",
    "masterNodeAddress": "qb-server:8810", "beginDate": "2026-11-21T01:06:50.575+00:00",
    "duration": 127,
}
BUILD_REQUEST_RESULT = {"requestId": "1018abb7-9c48-4a80-a0e2-74375d3fb01c", "loopedRequest": False}
ACTIVE_AGENTS = [{
    "@class": "com.pmease.quickbuild.grid.GridNode", "id": "6409fc40-18e8-496a-b823-3abeff46d5bb",
    "ip": "10.221.0.4", "port": 8811, "hostName": "9f05969a2055", "isServer": False,
    "overSSL": False, "benchmark": 580, "stopping": False,
}]
INACTIVE_AGENTS = [{
    "@class": "com.pmease.quickbuild.grid.GridNode", "ip": "10.221.0.9", "port": 8811,
    "hostName": "old-agent", "lastPulse": "2026-11-21T01:22:28.702+00:00",
}]
# Changeset structure from the QuickBuild "Interact with Changes" REST documentation
CHANGESETS = [{
    "user": "steve", "date": "2011-06-03T15:11:40.000+08:00",
    "id": "913fcbcdbe8f80d6c1fe5fce3bb49e1f0040a943", "comment": "Fix TST-23: 2-phase load components",
    "repositoryName": "hg", "repositoryType": "Mercurial", "additional": "14", "buildId": 321,
    "modifications": [
        {"action": "MODIFY", "path": "Test.java", "edition": "913fcbcd"},
        {"action": "MODIFY", "path": "big.java", "edition": "913fcbcd"},
    ],
}]


def json_response(payload, status=200):
    return httpx.Response(status, content=json.dumps(payload).encode(),
                          headers={"Content-Type": "application/json"})


def text_response(text, status=200, content_type="text/plain"):
    return httpx.Response(status, content=text.encode(), headers={"Content-Type": content_type})


class Recorder:
    """MockTransport handler that records requests and replays canned responses by path."""

    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = f"{request.method} {request.url.path}"
        route = self.routes.get(key)
        if route is None:
            return text_response("HTTP 404 Not Found", status=500)
        return route(request) if callable(route) else route


def make_client(routes, env=None):
    """Build a QuickBuildClient whose HTTP calls are served by a Recorder."""
    with patch.dict(os.environ, {**BASE_ENV, **(env or {})}, clear=True):
        client = QuickBuildClient(cache_ttl_configs=0, cache_ttl_agents=0)
    recorder = Recorder(routes)
    client.client = httpx.AsyncClient(
        transport=httpx.MockTransport(recorder),
        auth=client.client.auth,
        headers=client.client.headers,
    )
    return client, recorder


class TestAuthModes:
    def test_default_auth_mode_is_basic(self):
        with patch.dict(os.environ, BASE_ENV, clear=True):
            client = QuickBuildClient()
        assert client.auth_mode == "basic"
        assert isinstance(client.client.auth, httpx.BasicAuth)
        assert client.client.headers["Accept"] == "application/json"

    def test_session_mode_has_no_basic_auth(self):
        with patch.dict(os.environ, {**BASE_ENV, "QB_AUTH_MODE": "Session"}, clear=True):
            client = QuickBuildClient()
        assert client.auth_mode == "session"
        assert client.client.auth is None

    def test_invalid_auth_mode_raises(self):
        with patch.dict(os.environ, {**BASE_ENV, "QB_AUTH_MODE": "token"}, clear=True):
            with pytest.raises(ValueError, match="QB_AUTH_MODE"):
                QuickBuildClient()

    @pytest.mark.asyncio
    async def test_basic_authenticate_makes_no_network_call(self):
        client, recorder = make_client({})
        assert await client.authenticate() is True
        assert client.authenticated is True
        assert recorder.requests == []

    @pytest.mark.asyncio
    async def test_basic_credentials_and_json_accept_header_sent(self):
        client, recorder = make_client({"GET /rest/version": text_response("16.0.37")})
        await client.get_version()
        request = recorder.requests[0]
        expected = base64.b64encode(b"admin:s3cret!").decode()
        assert request.headers["Authorization"] == f"Basic {expected}"
        assert request.headers["Accept"] == "application/json"
        assert all("/rest/authentication" not in str(r.url) for r in recorder.requests)

    @pytest.mark.asyncio
    async def test_basic_401_fails_fast_without_reauthentication(self):
        unauthorized = json_response({"message": "User not found or password incorrect.", "status": "401"}, 401)
        client, recorder = make_client({"GET /rest/configurations": unauthorized})
        with patch.object(client, "authenticate", wraps=client.authenticate) as auth_spy:
            with pytest.raises(AuthenticationError, match="QB_USER"):
                await client.get_configurations()
        assert len(recorder.requests) == 1
        assert auth_spy.call_count == 1  # initial _ensure_authenticated only, no retry


class TestEndpoints:
    @pytest.mark.asyncio
    async def test_get_configurations_recursive(self):
        client, recorder = make_client({"GET /rest/configurations": json_response(CONFIGURATIONS)})
        configs = await client.get_configurations()

        assert recorder.requests[0].url.params["recursive"] == "true"
        assert [c.id for c in configs] == ["1", "2", "3"]
        assert configs[0].parent_id is None and configs[0].enabled is True
        assert configs[1].parent_id == "1" and configs[1].enabled is False
        assert configs[2].description.startswith("This configuration")

    @pytest.mark.asyncio
    async def test_latest_build_maps_begin_date_and_duration(self):
        client, recorder = make_client({"GET /rest/latest_builds/1": json_response(LATEST_BUILD)})
        build = await client.get_latest_build_status("1")

        assert recorder.requests[0].url.path == "/rest/latest_builds/1"
        assert build.id == "1"
        assert build.configuration_id == "1"
        assert build.version == "1.0.0"
        assert build.success is True
        assert build.start_time == datetime(2026, 11, 21, 1, 6, 50, 575000, tzinfo=timezone.utc)
        assert build.end_time == build.start_time + timedelta(milliseconds=127)

    @pytest.mark.asyncio
    async def test_latest_build_204_means_no_builds(self):
        client, _ = make_client({"GET /rest/latest_builds/7": httpx.Response(204)})
        assert await client.get_latest_build_status("7") is None

    @pytest.mark.asyncio
    async def test_running_build_has_no_end_time(self):
        running = {**LATEST_BUILD, "status": "RUNNING"}
        client, _ = make_client({"GET /rest/latest_builds/1": json_response(running)})
        build = await client.get_latest_build_status("1")
        assert build.end_time is None
        assert build.success is False

    @pytest.mark.asyncio
    async def test_recommended_build_counts_as_success(self):
        recommended = {**LATEST_BUILD, "status": "RECOMMENDED"}
        client, _ = make_client({"GET /rest/latest_builds/1": json_response(recommended)})
        assert (await client.get_latest_build_status("1")).success is True

    @pytest.mark.asyncio
    async def test_trigger_build_posts_build_request(self):
        client, recorder = make_client({"POST /rest/build_requests": json_response(BUILD_REQUEST_RESULT)})
        result = await client.trigger_build("1", {"MCP_TEST": "phase2"})

        body = json.loads(recorder.requests[0].content)
        assert body == {"configurationId": 1, "respectBuildCondition": False,
                        "variables": {"MCP_TEST": "phase2"}}
        assert recorder.requests[0].headers["Content-Type"] == "application/json"
        assert result["request_id"] == BUILD_REQUEST_RESULT["requestId"]
        assert result["build_id"] == ""
        assert result["status"] == "QUEUED"
        assert result["variables"] == {"MCP_TEST": "phase2"}

    @pytest.mark.asyncio
    async def test_trigger_build_aggregated_request(self):
        client, recorder = make_client({"POST /rest/build_requests": httpx.Response(204)})
        result = await client.trigger_build("root/app")
        assert json.loads(recorder.requests[0].content)["configurationId"] == "root/app"
        assert result["status"] == "AGGREGATED"
        assert "variables" not in result

    @pytest.mark.asyncio
    async def test_get_agents_merges_active_and_inactive(self):
        client, recorder = make_client({
            "GET /rest/buildagents/active": json_response(ACTIVE_AGENTS),
            "GET /rest/buildagents/inactive": json_response(INACTIVE_AGENTS),
        })
        agents = await client.get_agents()

        assert [r.url.path for r in recorder.requests] == ["/rest/buildagents/active", "/rest/buildagents/inactive"]
        assert [(a.name, a.status, a.ip_address, a.port) for a in agents] == [
            ("9f05969a2055", "online", "10.221.0.4", 8811),
            ("old-agent", "offline", "10.221.0.9", 8811),
        ]
        assert agents[1].last_contact == datetime(2026, 11, 21, 1, 22, 28, 702000, tzinfo=timezone.utc)

    @pytest.mark.asyncio
    async def test_get_agents_address_fallback(self):
        client, _ = make_client({
            "GET /rest/buildagents/active": json_response([{"address": "build-7:8812"}]),
            "GET /rest/buildagents/inactive": json_response([]),
        })
        agent = (await client.get_agents())[0]
        assert (agent.name, agent.ip_address, agent.port) == ("build-7:8812", "build-7", 8812)

    @pytest.mark.asyncio
    async def test_get_version_plain_text(self):
        # QuickBuild 16 answers "16.0.37" even when JSON is requested
        client, _ = make_client({"GET /rest/version": text_response("16.0.37", content_type="application/json")})
        assert (await client.get_version())["version"] == "16.0.37"

    @pytest.mark.asyncio
    async def test_build_changes_from_changesets(self):
        client, recorder = make_client({"GET /rest/changes/commits/build/321": json_response(CHANGESETS)})
        changes = await client.get_build_changes("321")

        assert recorder.requests[0].url.path == "/rest/changes/commits/build/321"
        assert len(changes) == 1
        change = changes[0]
        assert change.revision == "913fcbcdbe8f80d6c1fe5fce3bb49e1f0040a943"
        assert change.author == "steve"
        assert change.message.startswith("Fix TST-23")
        assert change.files == ["Test.java", "big.java"]
        assert change.timestamp == datetime(2011, 6, 3, 7, 11, 40, tzinfo=timezone.utc)

    @pytest.mark.asyncio
    async def test_backup_with_default_server_path(self):
        client, recorder = make_client(
            {"POST /rest/backup": text_response("/srv/qb/backup/x.zip", content_type="application/json")},
            env={"QB_BACKUP_DIR": "/srv/qb/backup/"},
        )
        result = await client.backup_database()

        body = json.loads(recorder.requests[0].content)
        assert body["backupTo"].startswith("/srv/qb/backup/quickbuild-")
        assert body["backupTo"].endswith(".zip")
        assert body["excludeBuilds"] is False and body["clearPasswords"] is False
        assert result["backup_path"] == body["backupTo"]
        assert result["details"] == "/srv/qb/backup/x.zip"


class TestErrorMapping:
    @pytest.mark.asyncio
    async def test_500_not_found_body_maps_to_resource_not_found_without_retry(self):
        client, recorder = make_client({"GET /rest/latest_builds/999": text_response("Configuration not found", 500)})
        with patch("src.quickbuild_client.asyncio.sleep", new_callable=AsyncMock) as sleep:
            with pytest.raises(ResourceNotFoundError):
                await client.get_latest_build_status("999")
        assert len(recorder.requests) == 1
        sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_500_http_404_body_maps_to_resource_not_found(self):
        client, _ = make_client({})  # unknown routes answer 500 "HTTP 404 Not Found" like QB16
        with pytest.raises(ResourceNotFoundError):
            await client.get_build_changes("1")


class TestParseDatetime:
    def test_epoch_milliseconds(self):
        assert _parse_datetime(1795223210592) == datetime(2026, 11, 21, 1, 6, 50, 592000, tzinfo=timezone.utc)

    def test_epoch_milliseconds_string(self):
        assert _parse_datetime("1795223210592").year == 2026

    def test_iso_offset(self):
        assert _parse_datetime("2026-11-21T01:06:50.575+00:00").microsecond == 575000

    def test_empty_falls_back_to_now(self):
        assert _parse_datetime(None).tzinfo is timezone.utc
