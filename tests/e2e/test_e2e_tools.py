"""Every MCP tool and resource against the live QuickBuild 16 harness, over stdio and HTTP."""
import asyncio

import pytest

from tests.e2e.conftest import call, http_session, read, stdio_session

pytestmark = pytest.mark.e2e

READ_TOOLS = {
    "configurations.search", "builds.get_latest_status", "builds.get", "builds.get_log",
    "builds.list_running", "build_requests.list", "grid.list_agents", "grid.list_unauthorized",
    "system.get_version",
}
WRITE_TOOLS = {"builds.trigger", "build_requests.cancel", "system.backup_database"}


async def test_catalog_and_server_info(e2e):
    async with stdio_session(e2e) as session:
        assert session.initialize_result.server_info.name == "quickbuild-mcp-server"
        tools = {t.name: t for t in (await session.list_tools()).tools}
        assert set(tools) == READ_TOOLS | WRITE_TOOLS
        for name, tool in tools.items():
            assert tool.annotations.read_only_hint is (name in READ_TOOLS), name
        resources = {str(r.uri) for r in (await session.list_resources()).resources}
        assert {"configurations://list", "changes://build/{build_id}"} <= resources
        templates = {t.uri_template for t in (await session.list_resource_templates()).resource_templates}
        assert "changes://build/{build_id}" in templates


async def test_version_and_configurations(e2e):
    f = e2e.fixtures
    async with stdio_session(e2e) as session:
        is_error, version = await call(session, "system.get_version")
        assert not is_error and version["version"] == e2e.rest("version", accept="text/plain").strip()

        configs = await read(session, "configurations://list")
        by_path = {c["path"]: c for c in configs["configurations"]}
        assert by_path["root/e2e-git"]["id"] == f["git_config_id"]
        assert by_path["root/~maintenance"]["enabled"] is False

        is_error, found = await call(session, "configurations.search", {"query": "e2e"})
        assert not is_error
        assert {c["path"] for c in found["configurations"]} >= {"root/e2e-git", "root/e2e-sleep"}
        _, exact = await call(session, "configurations.search", {"query": "root/e2e-git"})
        assert exact["configurations"][0]["id"] == f["git_config_id"]


async def test_build_detail_log_and_changes(e2e):
    f = e2e.fixtures
    build_id = f["changes_build_id"]
    async with stdio_session(e2e) as session:
        _, latest = await call(session, "builds.get_latest_status", {"configuration_id": f["git_config_path"]})
        assert latest["build_id"] == build_id and latest["success"] is True

        is_error, build = await call(session, "builds.get", {"build_id": build_id})
        assert not is_error
        assert build["configuration_id"] == f["git_config_id"] and build["status"] == "SUCCESSFUL"
        assert [s["path"] for s in build["steps"]] == ["master", "master>checkout", "master>print-lines"]
        assert all(s["status"] == "SUCCESSFUL" for s in build["steps"])
        assert build["revisions"] == {"e2e-git": f["commit"]["sha"]}

        is_error, log = await call(session, "builds.get_log", {"build_id": build_id, "tail_lines": 2000})
        assert not is_error
        numbered = [line for line in log["log"].splitlines() if f["log_line_prefix"] in line]
        assert len(numbered) == f["log_line_count"]
        assert numbered[-1].endswith(f"{f['log_line_prefix']}060")
        _, tail = await call(session, "builds.get_log", {"build_id": build_id, "tail_lines": 5})
        assert tail["line_count"] == 5 and tail["truncated"] is True

        changes = await read(session, f"changes://build/{build_id}")
        assert changes["count"] == 1
        change = changes["changes"][0]
        assert change["revision"] == f["commit"]["sha"]
        assert change["author"] == f["commit"]["author"]
        assert change["message"] == f["commit"]["message"]
        assert change["repository"] == f["commit"]["repository"]
        assert change["modifications"] == f["commit"]["modifications"]
        assert change["files"] == [m["path"] for m in f["commit"]["modifications"]]

        baseline = await read(session, f"changes://build/{f['baseline_build_id']}")
        assert baseline["count"] == 0


async def test_not_found_errors(e2e):
    async with stdio_session(e2e) as session:
        for name, args in [
            ("builds.get", {"build_id": "999999"}),
            ("builds.get_log", {"build_id": "999999"}),
            ("builds.get_latest_status", {"configuration_id": "root/does-not-exist"}),
            ("build_requests.cancel", {"request_id": "00000000-0000-0000-0000-000000000000"}),
        ]:
            is_error, payload = await call(session, name, args)
            assert is_error, name
            assert "not found" in payload["error"].lower(), (name, payload)


async def test_grid(e2e):
    async with stdio_session(e2e) as session:
        _, agents = await call(session, "grid.list_agents")
        assert agents["online_count"] >= 1
        expected_ip = e2e.fixtures["unauthorized_agent_ip"]
        unauthorized = {}
        for _ in range(30):  # a new agent shows up once it has contacted the server
            _, unauthorized = await call(session, "grid.list_unauthorized")
            if any(a["ip_address"] == expected_ip for a in unauthorized["agents"]):
                break
            await asyncio.sleep(2)
        assert expected_ip in {a["ip_address"] for a in unauthorized["agents"]}
        assert expected_ip not in {a["ip_address"] for a in agents["agents"]}


async def test_trigger_queue_running_and_cancel(e2e):
    f = e2e.fixtures
    async with stdio_session(e2e) as session:
        is_error, first = await call(session, "builds.trigger", {
            "configuration_id": f["sleep_config_path"], "variables": {"E2E_RUN": "first"}})
        assert not is_error and first["request_id"]
        _, second = await call(session, "builds.trigger", {"configuration_id": f["sleep_config_id"]})

        running = queue = None
        for _ in range(30):
            _, queue = await call(session, "build_requests.list", {"configuration_id": f["sleep_config_id"]})
            _, running = await call(session, "builds.list_running", {"configuration_id": f["sleep_config_path"]})
            if queue["running_count"] == 1 and running["count"] == 1:
                break
            await asyncio.sleep(1)
        statuses = {r["request_id"]: r["status"] for r in queue["requests"]}
        assert statuses == {first["request_id"]: "RUNNING_BUILD", second["request_id"]: "WAITING_PROCESS"}
        assert next(r for r in queue["requests"] if r["request_id"] == first["request_id"])["variables"] == {"E2E_RUN": "first"}
        running_build = running["builds"][0]
        assert running_build["status"] == "RUNNING"

        _, detail = await call(session, "builds.get", {"build_id": running_build["build_id"]})
        assert detail["status"] == "RUNNING" and detail["end_time"] is None
        assert detail["variables"] == {"E2E_RUN": "first"}
        is_error, log = await call(session, "builds.get_log", {"build_id": running_build["build_id"]})
        assert is_error and "available once the build has finished" in log["error"]

        for request in (second, first):
            is_error, cancelled = await call(session, "build_requests.cancel", {"request_id": request["request_id"]})
            assert not is_error and cancelled["status"] == "CANCELLED"

        status = None
        for _ in range(30):
            status = e2e.rest(f"builds/{running_build['build_id']}")["status"]
            if status == "CANCELLED":
                break
            await asyncio.sleep(1)
        assert status == "CANCELLED"
        # QuickBuild drops a cancelled running request from the queue shortly after its build
        # reports CANCELLED, so poll instead of checking once.
        after = None
        for _ in range(30):
            _, after = await call(session, "build_requests.list", {"configuration_id": f["sleep_config_id"]})
            if after["count"] == 0:
                break
            await asyncio.sleep(1)
        assert after["count"] == 0
        _, builds = await call(session, "builds.list_running", {"configuration_id": f["sleep_config_id"]})
        assert builds["count"] == 0


async def test_backup(e2e):
    async with stdio_session(e2e) as session:
        is_error, backup = await call(session, "system.backup_database",
                                      {"backup_path": "/opt/quickbuild/data/backup/e2e-mcp.zip"})
        assert not is_error and backup["status"] == "initiated"


async def test_http_transport_from_container(e2e):
    """The containerized server (MCP_TRANSPORT=http) as a gateway reaches it."""
    if not e2e.mcp_url:
        pytest.skip("E2E_MCP_URL not set")
    f = e2e.fixtures
    async with http_session(e2e.mcp_url) as session:
        tools = {t.name for t in (await session.list_tools()).tools}
        assert tools == READ_TOOLS | WRITE_TOOLS
        is_error, version = await call(session, "system.get_version")
        assert not is_error and version["version"].startswith("16.")
        _, build = await call(session, "builds.get", {"build_id": f["changes_build_id"]})
        assert build["revisions"] == {"e2e-git": f["commit"]["sha"]}
        changes = await read(session, f"changes://build/{f['changes_build_id']}")
        assert changes["changes"][0]["revision"] == f["commit"]["sha"]
        _, found = await call(session, "configurations.search", {"query": "e2e-sleep"})
        assert found["configurations"][0]["id"] == f["sleep_config_id"]
