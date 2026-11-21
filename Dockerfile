FROM python:3.12-slim

WORKDIR /usr/src/app

# Create non-root user for security
RUN groupadd -r mcpuser --gid=1000 && \
    useradd -r -g mcpuser --uid=1000 --home-dir=/usr/src/app --shell=/bin/bash mcpuser

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY --chown=mcpuser:mcpuser src/ ./src/

# Transport: "stdio" (default; attach with `docker run -i`) or "http" (Streamable HTTP on
# MCP_PORT at /mcp, plus /health and /ready, for a gateway). Inside a container the HTTP server
# must listen on all interfaces to be reachable through a published port; restrict who can
# connect with the network (and MCP_ALLOWED_HOSTS), not with the bind address.
ENV MCP_TRANSPORT=stdio \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=14002 \
    PYTHONUNBUFFERED=1

# Run as non-root user
USER mcpuser

# MCP Streamable HTTP port (MCP_TRANSPORT=http)
EXPOSE 14002

# Liveness: GET /health in http mode; always healthy in stdio mode
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-m", "src.healthcheck"]

# Run the server
CMD ["python", "-m", "src.server"]
