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

# Run as non-root user
USER mcpuser

# Expose the MCP server port
EXPOSE 14002

# Run the server
CMD ["python", "-m", "src.server"]
