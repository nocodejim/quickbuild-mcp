# QuickBuild MCP Server

A Model Context Protocol (MCP) server that provides AI agents and LLMs with standardized access to QuickBuild v14 CI/CD systems.

## Overview

This server acts as a bridge between MCP clients and QuickBuild REST API, enabling AI agents to:
- List build configurations
- Trigger builds with optional variables
- Check build status
- Monitor build agent grid
- Access SCM changes for builds

## Features

### MCP Tools
- `builds.trigger` - Trigger new builds for configurations
- `builds.get_latest_status` - Get latest build status for configurations
- `grid.list_agents` - List all build agents and their status

### MCP Resources
- `configurations://list` - List all build configurations
- `changes://build/{build_id}` - Get SCM changes for specific builds

## Quick Start

### Prerequisites
- Docker and Docker Compose
- QuickBuild v14 instance with REST API enabled
- Valid QuickBuild user credentials

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd quickbuild-mcp-server
```

2. Create environment file:
```bash
cp .env.example .env
```

3. Configure your QuickBuild connection in `.env`:
```env
QB_URL=http://your-quickbuild-host:8810
QB_USER=admin
QB_PASSWORD=your_password
LOG_LEVEL=INFO
MCP_PORT=14002
```

4. Start the server:
```bash
docker-compose up -d
```

The server will be available on port 14002.

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `QB_URL` | QuickBuild server URL | `http://localhost:8810` |
| `QB_USER` | QuickBuild username | `admin` |
| `QB_PASSWORD` | QuickBuild password | *Required* |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARN, ERROR) | `INFO` |
| `MCP_PORT` | MCP server port | `14002` |

## Usage Examples

### Using with MCP Client

Connect your MCP client to `stdio://path/to/server` or configure as needed for your specific MCP client.

### Available Tools

#### builds.trigger
Trigger a new build for a configuration:
```json
{
  "name": "builds.trigger",
  "arguments": {
    "configuration_id": "123",
    "variables": {
      "BRANCH": "main",
      "ENVIRONMENT": "staging"
    }
  }
}
```

#### builds.get_latest_status
Get the latest build status:
```json
{
  "name": "builds.get_latest_status",
  "arguments": {
    "configuration_id": "123"
  }
}
```

#### grid.list_agents
List all build agents:
```json
{
  "name": "grid.list_agents",
  "arguments": {}
}
```

### Available Resources

#### configurations://list
Lists all build configurations with their metadata.

#### changes://build/{build_id}
Gets SCM changes for a specific build ID.

## Development

### Project Structure
```
src/
├── models/           # Data models
├── features/         # Feature modules
│   ├── builds/       # Build operations
│   ├── configurations/ # Configuration management
│   ├── grid/         # Agent grid operations
│   └── changes/      # SCM changes
├── quickbuild_client.py # QuickBuild API client
├── exceptions.py     # Custom exceptions
└── server.py         # Main MCP server
```

### Running in Development Mode

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set environment variables and run:
```bash
python -m src.server
```

### Adding New Features

1. Create a new feature module in `src/features/`
2. Implement the `Feature` base class
3. Register the feature in `src/server.py`

## Error Handling

The server provides comprehensive error handling for:
- Authentication failures
- Network connectivity issues
- Invalid parameters
- QuickBuild API errors
- Resource not found scenarios

All errors are logged and returned as structured JSON responses.

## Security

- Credentials are passed via environment variables only
- No hardcoded secrets in source code
- Stateless operation with QuickBuild as source of truth
- Input validation on all tool parameters

## Troubleshooting

### Common Issues

**Connection refused to QuickBuild**
- Verify `QB_URL` is correct and accessible
- Check QuickBuild server is running
- Ensure REST API is enabled in QuickBuild

**Authentication failed**
- Verify `QB_USER` and `QB_PASSWORD` are correct
- Check user has necessary permissions in QuickBuild

**Tool not found**
- Ensure you're using the correct tool names
- Check server logs for feature loading errors

### Logs

View server logs:
```bash
docker-compose logs -f mcp-quickbuild-server
```

Set debug logging:
```env
LOG_LEVEL=DEBUG
```

## License

[Add your license information here]

## Contributing

[Add contribution guidelines here]