"""Tests for the Phase 3 MCP tools (feature layer, QuickBuild client mocked)."""
import json
from datetime import datetime, timezone

import pytest

from src.exceptions import QuickBuildError, ResourceNotFoundError
from src.features.base import bounded_int, is_write_tool, read_only_tool, write_tool
from src.features.build_requests.feature import BuildRequestsFeature
from src.features.builds.feature import BuildsFeature
from src.features.changes.feature import ChangesFeature
from src.features.configurations.feature import ConfigurationsFeature
from src.features.grid.feature import GridFeature
from src.models import Agent, Build, BuildRequest, Change, Configuration
from mcp.types import Tool

T0 = datetime(2026, 11, 21, 5, 18, 0, tzinfo=timezone.utc)


def make_build(**overrides):
    values = dict(
        id="4", configuration_id="11", version="1.0.3", status="SUCCESSFUL", start_time=T0,
        end_time=T0, success=True, requester_id="1", duration_ms=818, wait_duration_ms=2,
        scheduled=False, node="qb-server:8810",
        steps=[{"path": "master", "status": "SUCCESSFUL", "node": "qb-server:8810",
                "start_time": T0.isoformat(), "duration_ms": 726}],
        revisions={"e2e-git": "35c2a313"}, variables={"MCP_TEST": "phase2"},
    )
    values.update(overrides)
    return Build(**values)


class TestBaseHelpers:
    def test_annotations(self):
        read = read_only_tool("Read")
        write = write_tool("Write", destructive=True, idempotent=True)
        assert (read.read_only_hint, read.destructive_hint, read.idempotent_hint, read.open_world_hint) == (True, False, True, False)
        assert (write.read_only_hint, write.destructive_hint, write.idempotent_hint) == (False, True, True)

    def test_unannotated_tools_count_as_writes(self):
        plain = Tool(name="x", input_schema={"type": "object"})
        reader = Tool(name="y", input_schema={"type": "object"}, annotations=read_only_tool("Y"))
        assert is_write_tool(plain) is True
        assert is_write_tool(reader) is False

    @pytest.mark.parametrize("value, expected", [(None, 20), ("", 20), (5, 5), ("7", 7), (0, 1), (1000, 100)])
    def test_bounded_int(self, value, expected):
        assert bounded_int({"n": value}, "n", 20, 1, 100) == expected

    def test_bounded_int_rejects_text(self):
        with pytest.raises(ValueError, match="n must be an integer"):
            bounded_int({"n": "many"}, "n", 20, 1, 100)


class TestBuildsTools:
    @pytest.fixture
    def feature(self, mock_qb_client):
        return BuildsFeature(mock_qb_client)

    @pytest.mark.asyncio
    async def test_get_build(self, feature):
        feature.qb_client.get_build.return_value = make_build()
        data = json.loads(await feature.handle_tool_call("builds.get", {"build_id": "4"}))
        feature.qb_client.get_build.assert_awaited_once_with("4")
        assert data["build_id"] == "4" and data["status"] == "SUCCESSFUL" and data["success"] is True
        assert data["duration_ms"] == 818 and data["node"] == "qb-server:8810"
        assert data["steps"][0]["path"] == "master"
        assert data["revisions"] == {"e2e-git": "35c2a313"}
        assert data["variables"] == {"MCP_TEST": "phase2"}
        assert data["end_time"] == T0.isoformat()

    @pytest.mark.asyncio
    async def test_get_running_build_has_no_end_time(self, feature):
        feature.qb_client.get_build.return_value = make_build(status="RUNNING", end_time=None, success=False)
        data = json.loads(await feature.handle_tool_call("builds.get", {"build_id": "2"}))
        assert data["end_time"] is None

    @pytest.mark.asyncio
    async def test_get_build_errors(self, feature):
        assert json.loads(await feature.handle_tool_call("builds.get", {})) == {"error": "build_id is required"}
        feature.qb_client.get_build.side_effect = ResourceNotFoundError("Build 9 not found", "RESOURCE_NOT_FOUND")
        assert json.loads(await feature.handle_tool_call("builds.get", {"build_id": "9"})) == {"error": "Build 9 not found"}

    @pytest.mark.asyncio
    async def test_get_log(self, feature):
        feature.qb_client.get_build_log.return_value = {
            "build_id": "4", "lines": ["a", "b"], "line_count": 2, "log_bytes": 3146, "truncated": True,
        }
        data = json.loads(await feature.handle_tool_call("builds.get_log", {"build_id": "4", "tail_lines": 5000}))
        feature.qb_client.get_build_log.assert_awaited_once_with("4", tail_lines=2000)
        assert data == {"build_id": "4", "line_count": 2, "log_bytes": 3146, "truncated": True, "log": "a\nb"}

    @pytest.mark.asyncio
    async def test_get_log_errors(self, feature):
        assert json.loads(await feature.handle_tool_call("builds.get_log", {})) == {"error": "build_id is required"}
        feature.qb_client.get_build_log.side_effect = QuickBuildError(
            "The log of build 2 is available once the build has finished", "LOG_NOT_AVAILABLE")
        data = json.loads(await feature.handle_tool_call("builds.get_log", {"build_id": "2"}))
        assert "available once the build has finished" in data["error"]

    @pytest.mark.asyncio
    async def test_list_running(self, feature):
        feature.qb_client.search_builds.return_value = [make_build(status="RUNNING", end_time=None)]
        data = json.loads(await feature.handle_tool_call(
            "builds.list_running", {"configuration_id": "root/e2e", "limit": 3}))
        feature.qb_client.search_builds.assert_awaited_once_with(
            status="RUNNING", configuration_id="root/e2e", count=3)
        assert data["count"] == 1
        assert data["builds"][0] == {
            "build_id": "4", "configuration_id": "11", "version": "1.0.3", "status": "RUNNING",
            "start_time": T0.isoformat(), "node": "qb-server:8810", "requester_id": "1",
        }

    @pytest.mark.asyncio
    async def test_list_running_defaults_and_errors(self, feature):
        feature.qb_client.search_builds.return_value = []
        data = json.loads(await feature.handle_tool_call("builds.list_running", {}))
        feature.qb_client.search_builds.assert_awaited_once_with(status="RUNNING", configuration_id=None, count=20)
        assert data == {"builds": [], "count": 0}
        feature.qb_client.search_builds.side_effect = RuntimeError("down")
        assert json.loads(await feature.handle_tool_call("builds.list_running", {})) == {"error": "down"}


class TestBuildRequestsTools:
    @pytest.fixture
    def feature(self, mock_qb_client):
        return BuildRequestsFeature(mock_qb_client)

    def test_tools(self, feature):
        tools = {t.name: t for t in feature.get_tools()}
        assert set(tools) == {"build_requests.list", "build_requests.cancel"}
        assert tools["build_requests.list"].annotations.read_only_hint is True
        cancel = tools["build_requests.cancel"].annotations
        assert (cancel.read_only_hint, cancel.destructive_hint, cancel.idempotent_hint) == (False, True, True)
        assert feature.get_resources() == []

    @pytest.mark.asyncio
    async def test_list(self, feature):
        feature.qb_client.get_build_requests.return_value = [
            BuildRequest(id="r1", configuration_id="10", status="RUNNING_BUILD", requested_at=T0,
                         requester_id="1", priority=5),
            BuildRequest(id="r2", configuration_id="10", status="WAITING_PROCESS", requested_at=T0,
                         variables={"E2E": "second"}),
        ]
        data = json.loads(await feature.handle_tool_call("build_requests.list", {"configuration_id": "10"}))
        feature.qb_client.get_build_requests.assert_awaited_once_with("10")
        assert (data["count"], data["waiting_count"], data["running_count"]) == (2, 1, 1)
        assert data["requests"][0] == {
            "request_id": "r1", "configuration_id": "10", "status": "RUNNING_BUILD",
            "requested_at": T0.isoformat(), "requester_id": "1", "priority": 5,
            "scheduled": False, "variables": {},
        }
        assert data["requests"][1]["variables"] == {"E2E": "second"}

    @pytest.mark.asyncio
    async def test_list_error(self, feature):
        feature.qb_client.get_build_requests.side_effect = RuntimeError("nope")
        assert json.loads(await feature.handle_tool_call("build_requests.list", {})) == {"error": "nope"}
        feature.qb_client.get_build_requests.assert_awaited_once_with(None)

    @pytest.mark.asyncio
    async def test_cancel(self, feature):
        feature.qb_client.cancel_build_request.return_value = {"request_id": "r1", "status": "CANCELLED", "message": "m"}
        data = json.loads(await feature.handle_tool_call("build_requests.cancel", {"request_id": "r1"}))
        assert data["status"] == "CANCELLED"
        assert json.loads(await feature.handle_tool_call("build_requests.cancel", {})) == {"error": "request_id is required"}
        feature.qb_client.cancel_build_request.side_effect = ResourceNotFoundError("gone", "RESOURCE_NOT_FOUND")
        assert json.loads(await feature.handle_tool_call("build_requests.cancel", {"request_id": "r9"})) == {"error": "gone"}

    @pytest.mark.asyncio
    async def test_unknown(self, feature):
        with pytest.raises(ValueError, match="Unknown tool"):
            await feature.handle_tool_call("build_requests.purge", {})
        with pytest.raises(ValueError, match="Unknown resource URI"):
            await feature.handle_resource_request("queue://x")


class TestConfigurationSearch:
    CONFIGS = [
        Configuration("1", "root", "", None, True, "root"),
        Configuration("2", "~maintenance", "", "1", False, "root/~maintenance"),
        Configuration("3", "sync configurations", "Sync settings from a remote server", "2", True,
                      "root/~maintenance/sync configurations"),
        Configuration("10", "e2e-sleep", "long-running build", "1", True, "root/e2e-sleep"),
        Configuration("11", "e2e-git", "git checkout", "1", True, "root/e2e-git"),
        Configuration("12", "app-e2e", "", "1", True, "root/app-e2e"),
    ]

    @pytest.fixture
    def feature(self, mock_qb_client):
        mock_qb_client.get_configurations.return_value = self.CONFIGS
        return ConfigurationsFeature(mock_qb_client)

    async def search(self, feature, **args):
        return json.loads(await feature.handle_tool_call("configurations.search", args))

    @pytest.mark.asyncio
    async def test_ranking_prefix_before_substring(self, feature):
        data = await self.search(feature, query="E2E")
        assert [c["id"] for c in data["configurations"]] == ["11", "10", "12"]
        assert data["total_matches"] == 3 and data["count"] == 3
        assert data["configurations"][0] == {
            "id": "11", "name": "e2e-git", "path": "root/e2e-git", "description": "git checkout",
            "parent_id": "1", "enabled": True,
        }

    @pytest.mark.asyncio
    async def test_exact_id_name_and_path_rank_first(self, feature):
        assert (await self.search(feature, query="10"))["configurations"][0]["id"] == "10"
        assert (await self.search(feature, query="root/e2e-git"))["configurations"][0]["id"] == "11"

    @pytest.mark.asyncio
    async def test_path_and_description_matches(self, feature):
        assert [c["id"] for c in (await self.search(feature, query="maintenance/sync"))["configurations"]] == ["3"]
        assert [c["id"] for c in (await self.search(feature, query="remote server"))["configurations"]] == ["3"]

    @pytest.mark.asyncio
    async def test_disabled_and_limit(self, feature):
        assert "2" in [c["id"] for c in (await self.search(feature, query="maintenance"))["configurations"]]
        data = await self.search(feature, query="maintenance", include_disabled=False)
        assert [c["id"] for c in data["configurations"]] == ["3"]
        data = await self.search(feature, query="root", limit=2)
        assert data["count"] == 2 and data["total_matches"] == 6

    @pytest.mark.asyncio
    async def test_errors(self, feature):
        assert await self.search(feature, query="  ") == {"error": "query is required"}
        feature.qb_client.get_configurations.side_effect = RuntimeError("down")
        assert await self.search(feature, query="x") == {"error": "down"}

    @pytest.mark.asyncio
    async def test_list_resource_includes_path(self, feature):
        data = json.loads(await feature.handle_resource_request("configurations://list"))
        assert data["configurations"][1]["path"] == "root/~maintenance"


class TestGridUnauthorized:
    @pytest.mark.asyncio
    async def test_list_unauthorized(self, mock_qb_client):
        feature = GridFeature(mock_qb_client)
        mock_qb_client.get_unauthorized_agents.return_value = [
            Agent(name="8e56e5791aef", status="unauthorized", last_contact=T0, ip_address="10.221.0.5", port=8811)
        ]
        data = json.loads(await feature.handle_tool_call("grid.list_unauthorized", {}))
        assert data["count"] == 1
        assert data["agents"][0] == {
            "name": "8e56e5791aef", "ip_address": "10.221.0.5", "port": 8811, "last_contact": T0.isoformat(),
        }
        assert "Grid page" in data["note"]
        mock_qb_client.get_unauthorized_agents.side_effect = RuntimeError("down")
        assert json.loads(await feature.handle_tool_call("grid.list_unauthorized", {})) == {"error": "down"}


class TestChangesOutput:
    @pytest.mark.asyncio
    async def test_changes_include_repository_and_actions(self, mock_qb_client):
        feature = ChangesFeature(mock_qb_client)
        mock_qb_client.get_build_changes.return_value = [
            Change(revision="35c2a313", author="Alice Example", message="e2e: add docs", timestamp=T0,
                   files=["README.md", "docs/e2e.txt"], repository="e2e-git",
                   modifications=[{"action": "MODIFY", "path": "README.md"},
                                  {"action": "ADD", "path": "docs/e2e.txt"}])
        ]
        data = json.loads(await feature.handle_resource_request("changes://build/4"))
        change = data["changes"][0]
        assert change["repository"] == "e2e-git"
        assert change["modifications"][1] == {"action": "ADD", "path": "docs/e2e.txt"}
        assert change["files"] == ["README.md", "docs/e2e.txt"]
