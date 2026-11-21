"""Container health check: `python -m src.healthcheck` (used by the Dockerfile HEALTHCHECK).

With MCP_TRANSPORT=http it asks the server's own /health endpoint (liveness only; it does not
contact QuickBuild, use /ready for that). With stdio there is nothing to probe, so it succeeds.
"""
import os
import sys
import urllib.request


def check(environ=None, timeout: float = 4.0) -> int:
    env = os.environ if environ is None else environ
    if (env.get("MCP_TRANSPORT") or "stdio").strip().lower() != "http":
        return 0
    port = (env.get("MCP_PORT") or "14002").strip()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as response:
            return 0 if response.status == 200 else 1
    except OSError as exc:
        print(f"health check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(check())
