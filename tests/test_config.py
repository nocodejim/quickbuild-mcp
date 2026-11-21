"""Tests for environment-driven settings (src/config.py) and how the client applies them."""
import logging
import os
import ssl
from unittest.mock import patch

import certifi
import httpx
import pytest

from src.config import Settings, read_secret
from src.quickbuild_client import QuickBuildClient

BASE = {"QB_PASSWORD": "pw"}


def settings(**env):
    return Settings.from_env({**BASE, **env})


class TestDefaults:
    def test_defaults(self):
        s = settings()
        assert s.qb_url == "http://localhost:8810"
        assert s.qb_user == "admin"
        assert s.auth_mode == "basic"
        assert s.verify_ssl is True and s.ca_bundle is None
        assert s.timeout == 30.0
        assert s.read_only is False
        assert s.transport == "stdio"
        assert (s.host, s.port, s.http_path, s.stateless_http) == ("127.0.0.1", 14002, "/mcp", True)
        assert s.allowed_hosts == () and s.allowed_origins == ()

    def test_secrets_are_not_in_repr(self):
        s = settings(QB_AUTH_MODE="basic")
        assert "pw" not in repr(s)

    def test_url_trailing_slash_and_whitespace(self):
        assert settings(QB_URL=" https://qb.corp:8443/ ").qb_url == "https://qb.corp:8443"

    def test_empty_values_fall_back_to_defaults(self):
        s = settings(QB_USER="", QB_TIMEOUT="  ", MCP_TRANSPORT="")
        assert (s.qb_user, s.timeout, s.transport) == ("admin", 30.0, "stdio")

    def test_reads_os_environ_by_default(self):
        with patch.dict(os.environ, {"QB_PASSWORD": "from-env", "QB_READ_ONLY": "yes"}, clear=True):
            s = Settings.from_env()
        assert s.qb_password == "from-env" and s.read_only is True


class TestSecrets:
    def test_password_required(self):
        with pytest.raises(ValueError, match="QB_PASSWORD environment variable is required"):
            Settings.from_env({})

    def test_password_file_wins_and_strips_newline(self, tmp_path, caplog):
        secret = tmp_path / "pw"
        secret.write_text("from-file\n")
        with caplog.at_level(logging.WARNING):
            s = Settings.from_env({"QB_PASSWORD": "direct", "QB_PASSWORD_FILE": str(secret)})
        assert s.qb_password == "from-file"
        assert "QB_PASSWORD_FILE and QB_PASSWORD are both set" in caplog.text

    def test_password_file_keeps_inner_whitespace(self, tmp_path):
        secret = tmp_path / "pw"
        secret.write_text(" a b \r\n")
        assert Settings.from_env({"QB_PASSWORD_FILE": str(secret)}).qb_password == " a b "

    def test_unreadable_password_file(self, tmp_path):
        with pytest.raises(ValueError, match="QB_PASSWORD_FILE cannot be read"):
            Settings.from_env({"QB_PASSWORD_FILE": str(tmp_path / "missing")})

    def test_empty_password_file(self, tmp_path):
        secret = tmp_path / "pw"
        secret.write_text("\n")
        with pytest.raises(ValueError, match="QB_PASSWORD_FILE is empty"):
            Settings.from_env({"QB_PASSWORD_FILE": str(secret)})

    def test_read_secret_without_file(self):
        assert read_secret({"X": "v"}, "X") == "v"
        assert read_secret({}, "X") is None


class TestTokenMode:
    def test_token_mode_needs_no_password(self):
        s = Settings.from_env({"QB_AUTH_MODE": "token", "QB_TOKEN": "t" * 40})
        assert s.auth_mode == "token" and s.qb_token == "t" * 40 and s.qb_password is None
        assert "t" * 40 not in repr(s)

    def test_token_from_file(self, tmp_path):
        token = tmp_path / "token"
        token.write_text("abc\n")
        s = Settings.from_env({"QB_AUTH_MODE": "TOKEN", "QB_TOKEN_FILE": str(token)})
        assert s.qb_token == "abc"

    def test_token_required_in_token_mode(self):
        with pytest.raises(ValueError, match="QB_TOKEN environment variable is required"):
            Settings.from_env({"QB_AUTH_MODE": "token", "QB_PASSWORD": "pw"})

    def test_client_sends_token_as_basic_password(self):
        with patch.dict(os.environ, {"QB_AUTH_MODE": "token", "QB_USER": "svc", "QB_TOKEN": "tok"}, clear=True):
            client = QuickBuildClient()
        request = httpx.Request("GET", "http://qb/rest/version")
        flow = client.client.auth.auth_flow(request)
        assert next(flow).headers["Authorization"] == httpx.BasicAuth("svc", "tok")._auth_header


class TestValidation:
    @pytest.mark.parametrize(
        "env, message",
        [
            ({"QB_AUTH_MODE": "kerberos"}, "QB_AUTH_MODE must be one of basic, token, session"),
            ({"QB_VERIFY_SSL": "maybe"}, "QB_VERIFY_SSL must be true or false"),
            ({"QB_READ_ONLY": "2"}, "QB_READ_ONLY must be true or false"),
            ({"QB_TIMEOUT": "fast"}, "QB_TIMEOUT must be a number"),
            ({"QB_TIMEOUT": "0"}, "QB_TIMEOUT must be >= 0.1"),
            ({"QB_CACHE_TTL_AGENTS": "-1"}, "QB_CACHE_TTL_AGENTS must be >= 0"),
            ({"MCP_PORT": "0"}, "MCP_PORT must be >= 1"),
            ({"MCP_TRANSPORT": "sse"}, "MCP_TRANSPORT must be one of stdio, http"),
            ({"MCP_ALLOWED_ORIGINS": "https://gw"}, "MCP_ALLOWED_ORIGINS requires MCP_ALLOWED_HOSTS"),
            ({"QB_CA_BUNDLE": "/nonexistent/ca.pem"}, "QB_CA_BUNDLE does not exist"),
        ],
    )
    def test_invalid_values(self, env, message):
        with pytest.raises(ValueError, match=message):
            settings(**env)

    @pytest.mark.parametrize("value, expected", [("true", True), ("ON", True), ("1", True), ("no", False), ("False", False)])
    def test_booleans(self, value, expected):
        assert settings(QB_READ_ONLY=value).read_only is expected

    def test_http_settings(self):
        s = settings(
            MCP_TRANSPORT="HTTP", MCP_HOST="0.0.0.0", MCP_PORT="15000", MCP_HTTP_PATH="gw/mcp",
            MCP_HTTP_STATELESS="false", MCP_ALLOWED_HOSTS="mcp.corp:*, localhost:*",
            MCP_ALLOWED_ORIGINS="https://gw.corp",
        )
        assert (s.transport, s.host, s.port, s.http_path, s.stateless_http) == (
            "http", "0.0.0.0", 15000, "/gw/mcp", False,
        )
        assert s.allowed_hosts == ("mcp.corp:*", "localhost:*")
        assert s.allowed_origins == ("https://gw.corp",)

    def test_timeout_and_ttls(self):
        s = settings(QB_TIMEOUT="7.5", QB_CACHE_TTL_CONFIGS="0", QB_CACHE_TTL_AGENTS="5")
        assert (s.timeout, s.cache_ttl_configs, s.cache_ttl_agents) == (7.5, 0, 5)


class TestTls:
    def test_verify_disabled(self, caplog):
        s = settings(QB_VERIFY_SSL="false")
        assert s.ssl_verify() is False
        with caplog.at_level(logging.WARNING):
            with patch.dict(os.environ, {**BASE, "QB_VERIFY_SSL": "false"}, clear=True):
                QuickBuildClient()
        assert "certificates of http://localhost:8810 are NOT verified" in caplog.text

    def test_bundle_ignored_when_verification_disabled(self, caplog):
        with caplog.at_level(logging.WARNING):
            s = settings(QB_VERIFY_SSL="false", QB_CA_BUNDLE=certifi.where())
        assert s.ssl_verify() is False
        assert "QB_CA_BUNDLE is ignored" in caplog.text

    def test_default_context_trusts_public_roots(self):
        context = settings().ssl_verify()
        assert isinstance(context, ssl.SSLContext)
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname is True
        assert context.cert_store_stats()["x509_ca"] > 0

    def test_ca_bundle_file_is_added(self):
        with patch.object(ssl.SSLContext, "load_verify_locations") as load:
            settings(QB_CA_BUNDLE=certifi.where()).ssl_verify()
        assert load.call_args_list[-1].kwargs == {"cafile": certifi.where()}

    def test_ca_bundle_directory_is_added(self, tmp_path):
        with patch.object(ssl.SSLContext, "load_verify_locations") as load:
            settings(QB_CA_BUNDLE=str(tmp_path)).ssl_verify()
        assert load.call_args_list[-1].kwargs == {"capath": str(tmp_path)}

    def test_client_uses_context_and_timeout(self):
        with patch.dict(os.environ, {**BASE, "QB_TIMEOUT": "12"}, clear=True), \
                patch("src.quickbuild_client.httpx.AsyncClient") as async_client:
            QuickBuildClient()
        kwargs = async_client.call_args.kwargs
        assert isinstance(kwargs["verify"], ssl.SSLContext)
        assert kwargs["timeout"] == 12.0
        assert kwargs["trust_env"] is True


class TestProxyEnvironment:
    """httpx (trust_env=True) routes requests through HTTPS_PROXY unless NO_PROXY matches."""

    def client(self, **env):
        with patch.dict(os.environ, {**BASE, **env}, clear=True):
            return QuickBuildClient().client

    @staticmethod
    def proxied(client, url):
        return isinstance(client._transport_for_url(httpx.URL(url)), httpx.AsyncHTTPTransport) and \
            client._transport_for_url(httpx.URL(url)) is not client._transport

    def test_https_proxy_used(self):
        client = self.client(HTTPS_PROXY="http://proxy.corp:3128")
        assert self.proxied(client, "https://qb.corp:8443/rest/version")
        assert not self.proxied(client, "http://qb.corp:8810/rest/version")  # http:// not covered

    def test_no_proxy_domain_suffix_ip_and_localhost(self):
        client = self.client(
            HTTPS_PROXY="http://proxy.corp:3128", HTTP_PROXY="http://proxy.corp:3128",
            NO_PROXY="corp.example,10.1.2.3,localhost",
        )
        assert not self.proxied(client, "https://qb.corp.example/rest/version")
        assert not self.proxied(client, "https://corp.example/rest/version")
        assert not self.proxied(client, "http://10.1.2.3:8810/rest/version")
        assert not self.proxied(client, "http://localhost:8810/rest/version")
        assert self.proxied(client, "https://qb.other.example/rest/version")

    def test_no_proxy_cidr_is_not_supported_and_warned(self, caplog):
        # httpx 0.28 does not match addresses against CIDR ranges in NO_PROXY
        with caplog.at_level(logging.WARNING):
            client = self.client(HTTP_PROXY="http://proxy.corp:3128", NO_PROXY="192.168.0.0/16")
        assert self.proxied(client, "http://192.168.7.9:8810/rest/version")
        assert "NO_PROXY entries 192.168.0.0/16 are CIDR ranges" in caplog.text
