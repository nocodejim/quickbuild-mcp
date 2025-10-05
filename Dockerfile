FROM python:3.11-slim

WORKDIR /usr/src/app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Expose the MCP server port
EXPOSE 14002

# Run the server
CMD ["python", "-m", "src.server"]