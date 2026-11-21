"""Runtime settings for the QuickBuild MCP server, read and validated from the environment.

Everything that comes from the environment is parsed here, once, so a misconfiguration fails
at startup with a message naming the variable instead of surfacing later as a confusing
HTTP error. Secret values are excluded from repr() and never logged.
"""
import logging
import os
import ssl
from dataclasses import dataclass, field
from typing import Mapping, Optional, Tuple, Union

import certifi

logger = logging.getLogger(__name__)

# Supported QuickBuild authentication modes (QB_AUTH_MODE):
#   basic   - HTTP Basic QB_USER:QB_PASSWORD on every request (the QuickBuild REST API scheme; default)
#   token   - HTTP Basic QB_USER:QB_TOKEN, where QB_TOKEN is the user's QuickBuild access token
#             (My Setting > Access Token). QuickBuild 16 accepts the token in place of the password
#             and rejects it as a Bearer header (verified live on 16.0.37).
#   session - legacy login via POST /rest/authentication, then rely on the session cookie
AUTH_MODES = ("basic", "token", "session")
TRANSPORTS = ("stdio", "http")

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _get(environ: Mapping[str, str], name: str) -> Optional[str]:
    """Return a stripped env value, treating unset and empty the same."""
    value = environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _bool(environ: Mapping[str, str], name: str, default: bool) -> bool:
    value = _get(environ, name)
    if value is None:
        return default
    lowered = value.lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    raise ValueError(f"{name} must be true or false (got '{value}')")


def _number(environ: Mapping[str, str], name: str, default, cast, minimum):
    value = _get(environ, name)
    if value is None:
        return default
    try:
        number = cast(value)
    except ValueError:
        raise ValueError(f"{name} must be a number (got '{value}')") from None
    if number < minimum:
        raise ValueError(f"{name} must be >= {minimum} (got '{value}')")
    return number


def _list(environ: Mapping[str, str], name: str) -> Tuple[str, ...]:
    value = _get(environ, name)
    if value is None:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def read_secret(environ: Mapping[str, str], name: str) -> Optional[str]:
    """Read a secret from NAME_FILE (wins; one trailing newline stripped) or from NAME.

    The *_FILE form is how Docker/Kubernetes secrets are mounted, and keeps the value out of
    the process environment.
    """
    file_path = _get(environ, f"{name}_FILE")
    direct = environ.get(name) or None
    if file_path is None:
        return direct
    if direct:
        logger.warning("%s_FILE and %s are both set; using %s_FILE", name, name, name)
    try:
        with open(file_path, encoding="utf-8") as handle:
            value = handle.read()
    except OSError as exc:
        raise ValueError(f"{name}_FILE cannot be read ({file_path}): {exc.strerror}") from None
    value = value.rstrip("\r\n")
    if not value:
        raise ValueError(f"{name}_FILE is empty ({file_path})")
    return value


@dataclass(frozen=True)
class Settings:
    """Validated configuration of the QuickBuild client and the MCP server."""

    # QuickBuild connection
    qb_url: str = "http://localhost:8810"
    qb_user: str = "admin"
    qb_password: Optional[str] = field(default=None, repr=False)
    qb_token: Optional[str] = field(default=None, repr=False)
    auth_mode: str = "basic"
    verify_ssl: bool = True
    ca_bundle: Optional[str] = None
    timeout: float = 30.0
    backup_dir: str = "/opt/quickbuild/data/backup"
    cache_ttl_configs: int = 300
    cache_ttl_agents: int = 30

    # Safety
    read_only: bool = False

    # MCP transport
    transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = 14002
    http_path: str = "/mcp"
    stateless_http: bool = True
    allowed_hosts: Tuple[str, ...] = ()
    allowed_origins: Tuple[str, ...] = ()

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "Settings":
        env = os.environ if environ is None else environ

        auth_mode = (_get(env, "QB_AUTH_MODE") or "basic").lower()
        if auth_mode not in AUTH_MODES:
            raise ValueError(
                f"QB_AUTH_MODE must be one of {', '.join(AUTH_MODES)} (got '{auth_mode}')"
            )

        token = read_secret(env, "QB_TOKEN") if auth_mode == "token" else None
        password = read_secret(env, "QB_PASSWORD") if auth_mode != "token" else None
        if auth_mode == "token" and not token:
            raise ValueError(
                "QB_TOKEN environment variable is required when QB_AUTH_MODE=token "
                "(or QB_TOKEN_FILE)"
            )
        if auth_mode != "token" and not password:
            raise ValueError(
                "QB_PASSWORD environment variable is required (or QB_PASSWORD_FILE)"
            )

        verify_ssl = _bool(env, "QB_VERIFY_SSL", True)
        ca_bundle = _get(env, "QB_CA_BUNDLE")
        if ca_bundle and not os.path.exists(ca_bundle):
            raise ValueError(f"QB_CA_BUNDLE does not exist: {ca_bundle}")
        if ca_bundle and not verify_ssl:
            logger.warning("QB_CA_BUNDLE is ignored because QB_VERIFY_SSL=false")

        transport = (_get(env, "MCP_TRANSPORT") or "stdio").lower()
        if transport not in TRANSPORTS:
            raise ValueError(
                f"MCP_TRANSPORT must be one of {', '.join(TRANSPORTS)} (got '{transport}')"
            )

        http_path = _get(env, "MCP_HTTP_PATH") or "/mcp"
        if not http_path.startswith("/"):
            http_path = "/" + http_path

        allowed_hosts = _list(env, "MCP_ALLOWED_HOSTS")
        allowed_origins = _list(env, "MCP_ALLOWED_ORIGINS")
        if allowed_origins and not allowed_hosts:
            # With DNS rebinding protection on, an empty host list rejects every request.
            raise ValueError("MCP_ALLOWED_ORIGINS requires MCP_ALLOWED_HOSTS")

        return cls(
            qb_url=(_get(env, "QB_URL") or "http://localhost:8810").rstrip("/"),
            qb_user=_get(env, "QB_USER") or "admin",
            qb_password=password,
            qb_token=token,
            auth_mode=auth_mode,
            verify_ssl=verify_ssl,
            ca_bundle=ca_bundle,
            timeout=_number(env, "QB_TIMEOUT", 30.0, float, 0.1),
            backup_dir=(_get(env, "QB_BACKUP_DIR") or "/opt/quickbuild/data/backup").rstrip("/"),
            cache_ttl_configs=_number(env, "QB_CACHE_TTL_CONFIGS", 300, int, 0),
            cache_ttl_agents=_number(env, "QB_CACHE_TTL_AGENTS", 30, int, 0),
            read_only=_bool(env, "QB_READ_ONLY", False),
            transport=transport,
            host=_get(env, "MCP_HOST") or "127.0.0.1",
            port=_number(env, "MCP_PORT", 14002, int, 1),
            http_path=http_path,
            stateless_http=_bool(env, "MCP_HTTP_STATELESS", True),
            allowed_hosts=allowed_hosts,
            allowed_origins=allowed_origins,
        )

    def ssl_verify(self) -> Union[ssl.SSLContext, bool]:
        """The httpx `verify` value: False, or a context trusting certifi's CAs plus QB_CA_BUNDLE.

        A corporate CA bundle is added to the public roots rather than replacing them, so the
        same image works whether QuickBuild has a public or an internal certificate.
        """
        if not self.verify_ssl:
            return False
        context = ssl.create_default_context(cafile=certifi.where())
        if self.ca_bundle:
            if os.path.isdir(self.ca_bundle):
                context.load_verify_locations(capath=self.ca_bundle)
            else:
                context.load_verify_locations(cafile=self.ca_bundle)
        return context
