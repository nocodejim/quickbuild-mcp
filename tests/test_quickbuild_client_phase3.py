"""
Contract tests for the Phase 3 QuickBuildClient endpoints.

Payloads were captured from a live QuickBuild 16.0.37 server (the scripts/e2e.sh harness):
build detail with step runtimes and repository revisions, the build request queue, a real Git
changeset, unauthorized agents, and the build log download.
"""
import json
import os
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.exceptions import (
    AuthenticationError,
    QuickBuildError,
    QuickBuildServerError,
    QuickBuildUnavailableError,
    ResourceNotFoundError,
)
from src.quickbuild_client import QuickBuildClient, require_numeric_id, require_request_id
from tests.test_quickbuild_client_qb16 import json_response, make_client, text_response

BUILD_4 = {
    "id": 4, "configuration": 11, "version": "1.0.3", "requester": 1, "scheduled": False,
    "status": "SUCCESSFUL", "statusDate": "2026-11-21T05:18:01.794+00:00",
    "masterNodeAddress": "qb-server:8810", "beginDate": "2026-11-21T05:18:00.976+00:00",
    "duration": 818, "waitDuration": 2,
    "stepRuntimes": {
        "master": {"beginTime": 1795238280983, "status": "SUCCESSFUL",
                   "nodeAddress": "qb-server:8810", "waitDuration": 2, "duration": 726},
        "master>checkout": {"beginTime": 1795238281099, "status": "SUCCESSFUL",
                            "nodeAddress": "qb-server:8810", "duration": 165,
                            "customData": "Checkout revision: 35c2a313948c64dc68c97a995bf7c0008c335e29"},
        "master>print-lines": {"beginTime": 1795238281511, "status": "SUCCESSFUL",
                               "nodeAddress": "qb-server:8810", "duration": 3},
    },
    "repositoryRuntimes": {
        "e2e-git": {"revisionDOM": {"value": "35c2a313948c64dc68c97a995bf7c0008c335e29",
                                    "@class": "com.pmease.quickbuild.plugin.scm.git.GitRevision"},
                    "checkout": True},
    },
    "secretAwareVariableValues": {
        "MCP_TEST": {"string": "phase2", "masked": None},
        "DEPLOY_TOKEN": {"string": "should-never-be-shown", "masked": "******"},
    },
}
RUNNING_BUILD = {
    "@class": "com.pmease.quickbuild.model.Build", "id": 2, "configuration": 10,
    "version": "1.0.0", "requester": 1, "scheduled": False, "status": "RUNNING",
    "masterNodeAddress": "qb-server:8810", "beginDate": "2026-11-21T05:15:24.300+00:00",
    "waitDuration": 25, "stepRuntimes": {}, "repositoryRuntimes": {},
}
BUILD_REQUESTS = [
    {"@class": "com.pmease.quickbuild.BuildRequest", "configurationId": 10,
     "respectBuildCondition": False, "variables": {}, "upstreamRequestIds": [],
     "id": "b23d8c3e-06a7-4c2b-9a59-7464edb8b819", "priority": 5,
     "requestDate": "2026-11-21T05:15:24.226+00:00", "requesterId": 1, "scheduled": False,
     "status": "RUNNING_BUILD"},
    {"@class": "com.pmease.quickbuild.BuildRequest", "configurationId": 10,
     "respectBuildCondition": False, "variables": {"E2E": "second"}, "upstreamRequestIds": [],
     "id": "3b771d2b-4c6b-4e8e-807f-0e7425d14bef", "priority": 5,
     "requestDate": "2026-11-21T05:15:27.242+00:00", "requesterId": 1, "scheduled": False,
     "status": "WAITING_PROCESS"},
]
UNAUTHORIZED = [{
    "@class": "com.pmease.quickbuild.grid.UnauthorizedAgent", "ip": "10.221.0.5", "port": 8811,
    "overSSL": False, "hostName": "8e56e5791aef", "lastPulse": "2026-11-21T05:16:37.234+00:00",
}]
GIT_CHANGESET = [{
    "@class": "com.pmease.quickbuild.plugin.report.changes.rest.RawChangeset",
    "user": "Alice Example", "date": "2026-11-21T05:18:00.000+00:00",
    "id": "35c2a313948c64dc68c97a995bf7c0008c335e29",
    "comment": "e2e: add docs/e2e.txt and touch README",
    "modifications": [
        {"action": "MODIFY", "path": "README.md", "edition": "35c2a313",
         "previousEdition": "147d9826"},
        {"action": "ADD", "path": "docs/e2e.txt", "edition": "35c2a313",
         "previousEdition": "147d9826"},
    ],
    "repositoryName": "e2e-git", "repositoryType": "Git", "buildId": 4,
}]
LOG_LINES = [f"05:18:01,514 INFO  - E2E-LOG-LINE-{i:03d}" for i in range(1, 61)]
LOG_TEXT = "\n".join(LOG_LINES) + "\n"
RUNNING_LOG_ERROR = json.dumps({
    "cause0": "java.lang.RuntimeException: java.io.EOFException",
    "message": "java.lang.RuntimeException: java.io.EOFException", "url": "/download/2/log",
    "status": "500",
})
MISSING_LOG_ERROR = (
    "<html><head><title>Error 500 org.hibernate.ObjectNotFoundException: No row with the given "
    "identifier exists: [com.pmease.quickbuild.model.Build#999999]</title></head></html>"
)


def log_response(text=LOG_TEXT):
    return httpx.Response(
        200, content=text.encode(),
        headers={"Content-Disposition": "attachment;filename=Build-Log.txt"},
    )


class TestIdValidation:
    @pytest.mark.parametrize("value", ["1", " 42 ", 7])
    def test_numeric_ids(self, value):
        assert require_numeric_id(value, "build_id") == str(value).strip()

    @pytest.mark.parametrize("value", ["", None, "1/../users", "../configurations/1", "1.5", "-1", "abc"])
    def test_rejects_non_numeric_ids(self, value):
        with pytest.raises(ValueError, match="build_id must be a numeric QuickBuild id"):
            require_numeric_id(value, "build_id")

    def test_request_ids(self):
        assert require_request_id("cd1131bc-ad0b-4e20-a1ad-bafa1c10c20d") == "cd1131bc-ad0b-4e20-a1ad-bafa1c10c20d"
        for bad in ["", "../configurations/1", "a/b", "x" * 65, None]:
            with pytest.raises(ValueError, match="request_id must be"):
                require_request_id(bad)


class TestBuilds:
    @pytest.mark.asyncio
    async def test_get_build_maps_steps_revisions_and_masks_secrets(self):
        client, recorder = make_client({"GET /rest/builds/4": json_response(BUILD_4)})
        build = await client.get_build("4")
        assert str(recorder.requests[0].url) == "http://qb:8810/rest/builds/4"
        assert (build.id, build.configuration_id, build.version, build.status) == ("4", "11", "1.0.3", "SUCCESSFUL")
        assert build.success is True
        assert (build.duration_ms, build.wait_duration_ms, build.requester_id, build.node) == (818, 2, "1", "qb-server:8810")
        assert [s["path"] for s in build.steps] == ["master", "master>checkout", "master>print-lines"]
        assert build.steps[1] == {
            "path": "master>checkout", "status": "SUCCESSFUL", "node": "qb-server:8810",
            "start_time": "2026-11-21T05:18:01.099000+00:00", "duration_ms": 165,
        }
        assert build.revisions == {"e2e-git": "35c2a313948c64dc68c97a995bf7c0008c335e29"}
        assert build.variables == {"MCP_TEST": "phase2", "DEPLOY_TOKEN": "******"}
        assert "should-never-be-shown" not in json.dumps(build.variables)

    @pytest.mark.asyncio
    async def test_get_build_missing(self):
        client, _ = make_client({})  # unknown routes answer 500 "HTTP 404 Not Found"
        with pytest.raises(ResourceNotFoundError):
            await client.get_build("999999")

    @pytest.mark.asyncio
    async def test_get_build_empty_body_is_not_found(self):
        client, _ = make_client({"GET /rest/builds/5": httpx.Response(204)})
        with pytest.raises(ResourceNotFoundError, match="Build 5 not found"):
            await client.get_build("5")

    @pytest.mark.asyncio
    async def test_get_build_rejects_path_traversal_without_request(self):
        client, recorder = make_client({})
        with pytest.raises(ValueError):
            await client.get_build("4/../../users")
        assert recorder.requests == []

    @pytest.mark.asyncio
    async def test_variables_tolerate_plain_and_null_values(self):
        data = {**BUILD_4, "secretAwareVariableValues": {"A": "x", "B": None, "C": {"string": None}}}
        client, _ = make_client({"GET /rest/builds/4": json_response(data)})
        assert (await client.get_build("4")).variables == {"A": "x", "B": None, "C": None}

    @pytest.mark.asyncio
    async def test_search_running_builds_sends_required_count(self):
        client, recorder = make_client({"GET /rest/builds": json_response([RUNNING_BUILD])})
        builds = await client.search_builds(status="running", count=5)
        params = recorder.requests[0].url.params
        assert dict(params) == {"count": "5", "status": "RUNNING"}
        assert [(b.id, b.status, b.end_time) for b in builds] == [("2", "RUNNING", None)]

    @pytest.mark.asyncio
    async def test_search_builds_by_configuration_path(self):
        client, recorder = make_client({
            "GET /rest/ids": json_response(10),
            "GET /rest/builds": json_response([]),
        })
        assert await client.search_builds(status="RUNNING", configuration_id="root/e2e-sleep") == []
        assert recorder.requests[0].url.params["configuration_path"] == "root/e2e-sleep"
        assert dict(recorder.requests[1].url.params) == {
            "count": "20", "status": "RUNNING", "configuration_id": "10", "recursive": "true",
        }

    @pytest.mark.asyncio
    async def test_search_builds_minimum_count(self):
        client, recorder = make_client({"GET /rest/builds": json_response([])})
        await client.search_builds(count=0, configuration_id="3", recursive=False)
        assert dict(recorder.requests[0].url.params) == {"count": "1", "configuration_id": "3", "recursive": "false"}


class TestConfigurationPaths:
    @pytest.mark.asyncio
    async def test_numeric_id_needs_no_lookup(self):
        client, recorder = make_client({})
        assert await client.resolve_configuration_id(" 12 ") == "12"
        assert recorder.requests == []

    @pytest.mark.asyncio
    async def test_path_is_resolved_and_cached(self):
        client, recorder = make_client({"GET /rest/ids": text_response("11")})
        client.cache_ttl_configs = 60
        assert await client.resolve_configuration_id("root/e2e-git") == "11"
        assert await client.resolve_configuration_id("root/e2e-git") == "11"
        assert len(recorder.requests) == 1

    @pytest.mark.asyncio
    async def test_missing_path(self):
        client, _ = make_client({})
        with pytest.raises(ResourceNotFoundError):
            await client.resolve_configuration_id("root/does-not-exist")

    @pytest.mark.asyncio
    async def test_non_numeric_answer_is_not_found(self):
        client, _ = make_client({"GET /rest/ids": json_response({"unexpected": True})})
        with pytest.raises(ResourceNotFoundError, match="Configuration not found: root/x"):
            await client.resolve_configuration_id("root/x")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("value", ["", None, "root/\nx", "r" * 1001])
    async def test_invalid_paths(self, value):
        client, recorder = make_client({})
        with pytest.raises(ValueError, match="configuration_id must be a numeric id or a configuration path"):
            await client.resolve_configuration_id(value)
        assert recorder.requests == []

    @pytest.mark.asyncio
    async def test_latest_build_by_path(self):
        client, recorder = make_client({
            "GET /rest/ids": json_response(11),
            "GET /rest/latest_builds/11": json_response(BUILD_4),
        })
        build = await client.get_latest_build_status("root/e2e-git")
        assert build.id == "4" and recorder.requests[1].url.path == "/rest/latest_builds/11"


class TestBuildRequests:
    @pytest.mark.asyncio
    async def test_list_queue(self):
        client, recorder = make_client({"GET /rest/build_requests": json_response(BUILD_REQUESTS)})
        requests = await client.get_build_requests()
        assert recorder.requests[0].url.params == httpx.QueryParams()
        assert [(r.id[:8], r.configuration_id, r.status) for r in requests] == [
            ("b23d8c3e", "10", "RUNNING_BUILD"), ("3b771d2b", "10", "WAITING_PROCESS"),
        ]
        assert requests[1].variables == {"E2E": "second"}
        assert (requests[0].requester_id, requests[0].priority, requests[0].scheduled) == ("1", 5, False)
        assert requests[0].requested_at.isoformat() == "2026-11-21T05:15:24.226000+00:00"

    @pytest.mark.asyncio
    async def test_list_queue_for_configuration(self):
        client, recorder = make_client({"GET /rest/build_requests": json_response([])})
        assert await client.get_build_requests("11") == []
        assert recorder.requests[0].url.params["configuration_id"] == "11"

    @pytest.mark.asyncio
    async def test_cancel_sends_delete(self):
        client, recorder = make_client({
            "DELETE /rest/build_requests/cd1131bc-ad0b-4e20-a1ad-bafa1c10c20d": httpx.Response(204),
        })
        result = await client.cancel_build_request("cd1131bc-ad0b-4e20-a1ad-bafa1c10c20d")
        assert recorder.requests[0].method == "DELETE"
        assert result == {
            "request_id": "cd1131bc-ad0b-4e20-a1ad-bafa1c10c20d", "status": "CANCELLED",
            "message": "Build request cd1131bc-ad0b-4e20-a1ad-bafa1c10c20d cancelled",
        }

    @pytest.mark.asyncio
    async def test_cancel_unknown_request_is_not_found_without_retry(self):
        client, recorder = make_client({})
        with pytest.raises(ResourceNotFoundError):
            await client.cancel_build_request("00000000-0000-0000-0000-000000000000")
        assert len(recorder.requests) == 1

    @pytest.mark.asyncio
    async def test_cancel_cannot_be_redirected_to_another_resource(self):
        client, recorder = make_client({})
        with pytest.raises(ValueError):
            await client.cancel_build_request("../configurations/1")
        assert recorder.requests == []


class TestBuildLog:
    @pytest.mark.asyncio
    async def test_tail_lines(self):
        client, recorder = make_client({"GET /download/4/log": log_response()})
        log = await client.get_build_log("4", tail_lines=3)
        request = recorder.requests[0]
        assert str(request.url) == "http://qb:8810/download/4/log"
        assert request.headers["Accept"] == "*/*"
        assert request.headers["Authorization"].startswith("Basic ")
        assert log == {
            "build_id": "4", "lines": LOG_LINES[-3:], "line_count": 3,
            "log_bytes": len(LOG_TEXT.encode()), "truncated": True,
        }

    @pytest.mark.asyncio
    async def test_whole_log_when_short(self):
        client, _ = make_client({"GET /download/4/log": log_response()})
        log = await client.get_build_log("4", tail_lines=500)
        assert log["lines"] == LOG_LINES and log["truncated"] is False

    @pytest.mark.asyncio
    async def test_byte_window_drops_partial_first_line(self):
        long_text = "\n".join(f"line-{i:05d}-" + "x" * 50 for i in range(200)) + "\n"
        client, _ = make_client({"GET /download/9/log": log_response(long_text)})
        log = await client.get_build_log("9", tail_lines=2000, max_bytes=1024)
        assert log["truncated"] is True
        assert log["lines"][-1].startswith("line-00199-")
        assert all(line.startswith("line-") and len(line) == 61 for line in log["lines"])
        assert log["log_bytes"] == len(long_text.encode())

    @pytest.mark.asyncio
    async def test_running_build_log_not_available(self):
        client, recorder = make_client({
            "GET /download/2/log": httpx.Response(500, content=RUNNING_LOG_ERROR.encode(),
                                                  headers={"Content-Type": "application/json"}),
        })
        with pytest.raises(QuickBuildError, match="available once the build has finished") as exc:
            await client.get_build_log("2")
        assert exc.value.error_code == "LOG_NOT_AVAILABLE"
        assert len(recorder.requests) == 1

    @pytest.mark.asyncio
    async def test_missing_build_log(self):
        client, _ = make_client({
            "GET /download/999999/log": text_response(MISSING_LOG_ERROR, status=500, content_type="text/html"),
        })
        with pytest.raises(ResourceNotFoundError, match="Build 999999 not found"):
            await client.get_build_log("999999")

    @pytest.mark.asyncio
    async def test_log_auth_failure(self):
        client, _ = make_client({"GET /download/4/log": httpx.Response(401)})
        with pytest.raises(AuthenticationError, match="QB_USER/QB_PASSWORD"):
            await client.get_build_log("4")

    @pytest.mark.asyncio
    async def test_log_other_server_error(self):
        client, _ = make_client({"GET /download/4/log": text_response("boom", status=502)})
        with pytest.raises(QuickBuildServerError, match="502"):
            await client.get_build_log("4")

    @pytest.mark.asyncio
    async def test_log_connection_error(self):
        def refuse(request):
            raise httpx.ConnectError("refused", request=request)

        client, _ = make_client({"GET /download/4/log": refuse})
        with pytest.raises(QuickBuildUnavailableError):
            await client.get_build_log("4")


class TestGridAndChanges:
    @pytest.mark.asyncio
    async def test_unauthorized_agents(self):
        client, recorder = make_client({"GET /rest/buildagents/unauthorized": json_response(UNAUTHORIZED)})
        agents = await client.get_unauthorized_agents()
        assert recorder.requests[0].url.path == "/rest/buildagents/unauthorized"
        agent = agents[0]
        assert (agent.name, agent.status, agent.ip_address, agent.port) == ("8e56e5791aef", "unauthorized", "10.221.0.5", 8811)
        assert agent.last_contact.isoformat() == "2026-11-21T05:16:37.234000+00:00"

    @pytest.mark.asyncio
    async def test_git_changeset_with_actions(self):
        client, _ = make_client({"GET /rest/changes/commits/build/4": json_response(GIT_CHANGESET)})
        change = (await client.get_build_changes("4"))[0]
        assert change.revision == "35c2a313948c64dc68c97a995bf7c0008c335e29"
        assert (change.author, change.repository) == ("Alice Example", "e2e-git")
        assert change.files == ["README.md", "docs/e2e.txt"]
        assert change.modifications == [
            {"action": "MODIFY", "path": "README.md"}, {"action": "ADD", "path": "docs/e2e.txt"},
        ]

    @pytest.mark.asyncio
    async def test_changes_reject_bad_build_id(self):
        client, recorder = make_client({})
        with pytest.raises(ValueError):
            await client.get_build_changes("1/../../users")
        assert recorder.requests == []


class TestRetrySemantics:
    """POST requests (trigger, backup) must not be repeated once they may have reached QuickBuild."""

    @pytest.mark.asyncio
    async def test_post_not_retried_after_timeout(self):
        calls = []

        def timeout(request):
            calls.append(request)
            raise httpx.ReadTimeout("slow", request=request)

        client, _ = make_client({"POST /rest/build_requests": timeout})
        with patch("src.quickbuild_client.asyncio.sleep", new=AsyncMock()):
            with pytest.raises(QuickBuildUnavailableError, match="did not answer within 30s"):
                await client.trigger_build("1")
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_post_not_retried_after_server_error(self):
        client, recorder = make_client({"POST /rest/build_requests": text_response("boom", status=503)})
        with pytest.raises(QuickBuildServerError, match="503 - boom"):
            await client.trigger_build("1")
        assert len(recorder.requests) == 1

    @pytest.mark.asyncio
    async def test_post_retried_after_connect_error(self):
        calls = []

        def flaky(request):
            calls.append(request)
            if len(calls) == 1:
                raise httpx.ConnectError("refused", request=request)
            return json_response({"requestId": "r-1"})

        client, _ = make_client({"POST /rest/build_requests": flaky})
        with patch("src.quickbuild_client.asyncio.sleep", new=AsyncMock()):
            result = await client.trigger_build("1")
        assert result["request_id"] == "r-1" and len(calls) == 2

    @pytest.mark.asyncio
    async def test_get_retried_after_timeout(self):
        calls = []

        def flaky(request):
            calls.append(request)
            if len(calls) < 3:
                raise httpx.ReadTimeout("slow", request=request)
            return text_response("16.0.37")

        client, _ = make_client({"GET /rest/version": flaky})
        with patch("src.quickbuild_client.asyncio.sleep", new=AsyncMock()):
            assert (await client.get_version())["version"] == "16.0.37"
        assert len(calls) == 3

    @pytest.mark.asyncio
    async def test_untrusted_certificate_is_named_and_not_retried(self):
        calls = []

        def untrusted(request):
            calls.append(request)
            raise httpx.ConnectError(
                "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate",
                request=request,
            )

        client, _ = make_client({"GET /rest/version": untrusted, "GET /download/4/log": untrusted})
        with pytest.raises(QuickBuildUnavailableError, match="Set QB_CA_BUNDLE") as exc:
            await client.get_version()
        assert exc.value.error_code == "TLS_VERIFY_FAILED" and len(calls) == 1
        with pytest.raises(QuickBuildUnavailableError, match="Set QB_CA_BUNDLE"):
            await client.get_build_log("4")

    @pytest.mark.asyncio
    async def test_connect_failure_after_retries(self):
        def refuse(request):
            raise httpx.ConnectError("refused", request=request)

        client, _ = make_client({"GET /rest/version": refuse})
        with patch("src.quickbuild_client.asyncio.sleep", new=AsyncMock()):
            with pytest.raises(QuickBuildUnavailableError, match="Cannot connect to QuickBuild server"):
                await client.get_version()

    @pytest.mark.asyncio
    async def test_log_timeout(self):
        def slow(request):
            raise httpx.ReadTimeout("slow", request=request)

        client, _ = make_client({"GET /download/4/log": slow})
        with pytest.raises(QuickBuildUnavailableError, match="QB_TIMEOUT"):
            await client.get_build_log("4")

    @pytest.mark.asyncio
    async def test_token_mode_auth_failure_hint(self):
        client, _ = make_client(
            {"GET /rest/version": httpx.Response(401)},
            env={"QB_AUTH_MODE": "token", "QB_TOKEN": "t"},
        )
        with pytest.raises(AuthenticationError, match="QB_USER/QB_TOKEN"):
            await client.get_version()

    @pytest.mark.asyncio
    async def test_delete_helper(self):
        client, recorder = make_client({"DELETE /rest/thing/1": httpx.Response(204)})
        assert await client.delete("thing/1") == {}
        assert recorder.requests[0].method == "DELETE"


def test_settings_object_can_be_passed_directly():
    from src.config import Settings

    with patch.dict(os.environ, {}, clear=True):
        client = QuickBuildClient(settings=Settings.from_env({"QB_PASSWORD": "x", "QB_URL": "http://a:1"}))
    assert client.base_url == "http://a:1"
