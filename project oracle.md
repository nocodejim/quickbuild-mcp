project oracle.md   

# Requirements

## Problem Statement

  - **What specific problem are we solving?**
      - AI agents and Large Language Models (LLMs) lack a standardized, secure way to interact with the QuickBuild v14 CI/CD system. Currently, any integration requires a custom-built, single-purpose client that speaks directly to the QuickBuild REST API. This project will create a reusable, standards-compliant MCP server to bridge this gap.
  - **Who is the target user?**
      - The primary users are AI agents and developers building AI-powered applications that need to monitor, manage, or automate QuickBuild workflows.
  - **What are the success criteria?**
      - An MCP client can successfully connect to the QuickBuild MCP server.
      - The server accurately exposes core QuickBuild functionalities as MCP tools and resources.
      - An AI agent can successfully use the server to perform high-value actions, such as triggering a build or checking the status of build agents.

## Functional Requirements

  - **Core Features (must-have)**:
      - Expose build configurations as readable resources.
      - Provide a tool to trigger builds for a specific configuration.
      - Provide a tool to retrieve the status of the latest build for a configuration.
      - Provide a tool to list the status of all build agents in the grid.
      - Expose build-specific SCM changes as a resource.
  - **Secondary Features (nice-to-have)**:
      - A tool to create new QuickBuild configurations from a simplified template.
      - A tool to authorize new build agents.
      - A tool to initiate a system-wide database backup.
      - Resources to access detailed build report data (e.g., JUnit test results).
  - **Integration Requirements**:
      - The server must communicate with the QuickBuild v14 instance via its REST API (supporting JSON payloads).
      - The server must adhere to the Model-Context-Protocol specification for all client-facing interactions.
  - **Performance Requirements**:
      - The server must handle multiple concurrent requests from an MCP client without significant delays.
      - API calls to QuickBuild should be efficient, leveraging specific endpoints rather than fetching and filtering large datasets where possible.

## Non-Functional Requirements

  - **Security Considerations**:
      - The server will authenticate with the QuickBuild API using credentials provided via environment variables. These credentials should not be hardcoded.
      - The server will be stateless where possible, relying on the QuickBuild instance as the single source of truth.
  - **Scalability Needs**:
      - The initial design will be for a single-instance server. It should be architected in a modular way to allow for future scaling if necessary.
  - **Deployment Constraints**:
      - The application **must** be developed and run within a Docker container to prevent host contamination.
  - **Technology Preferences**:
      - The technology stack will be based on the provided `spira-mcp-connection` GitHub repository, which utilizes **Python** and the official **`model-context-protocol` Python SDK**. This is the best and fastest technology for this purpose, as confirmed by MCP's official documentation.

## Out of Scope

  - A graphical user interface (GUI) for the MCP server itself.
  - Direct database access to the QuickBuild instance.
  - Support for versions of QuickBuild other than v14.
  - Any features not exposed by the QuickBuild v14 REST API.

-----

# Design

## Architecture Overview

The system will consist of a single, containerized Python application that acts as an MCP server. It will function as a stateless bridge, translating MCP requests from a client into REST API calls to the QuickBuild server and formatting the responses back into the MCP-specified structure. The architecture will follow the modular "features" pattern seen in the `spira-mcp-connection` repository.

## Component Breakdown

  - **MCP Server Core (`server.py`)**: The main entry point, responsible for initializing the MCP server using the SDK and loading the feature modules.
  - **QuickBuild API Client (`quickbuild_client.py`)**: A dedicated module responsible for all communication with the QuickBuild REST API. It will handle authentication, session management, and formatting of HTTP requests.
  - **Features Modules**: Functionality will be grouped into "features," each in its own directory, mirroring the structure of the QuickBuild API and the `spira-mcp-connection` example.
      - `features/configurations/`: Contains tools and resources for managing build configurations.
      - `features/builds/`: Contains tools and resources for build operations.
      - `features/grid/`: Contains tools for interacting with the build agent grid.
      - `features/system/`: Contains tools for system-level administrative tasks.

## Data Models

The MCP server will not have its own persistent database. It will dynamically fetch and transform data from the QuickBuild API. The primary data models will be Pydantic models that represent the JSON structures of the QuickBuild API responses, which will then be converted into MCP `Tool` and `Resource` objects.

## API Design (MCP Tools & Resources)

The server will expose the following high-priority tools and resources:

| Feature          | MCP Primitive | Name                               | Description                                                                 |
| ---------------- | ------------- | ---------------------------------- | --------------------------------------------------------------------------- |
| **Builds** | `Tool`        | `builds.trigger`                   | Triggers a new build for a given configuration ID, optionally with variables. |
| **Builds** | `Tool`        | `builds.get_latest_status`         | Returns the status and version of the latest build for a configuration ID.  |
| **Configurations**| `Resource`    | `configurations.list`              | Lists all available build configurations in the QuickBuild hierarchy.        |
| **Grid** | `Tool`        | `grid.list_agents`                 | Returns a list of all build agents and their connection status.             |
| **System** | `Tool`        | `system.backup_database`           | Initiates a server-side backup of the QuickBuild database.                  |
| **Changes** | `Resource`    | `changes.get_for_build`            | Retrieves the list of SCM changes associated with a specific build ID.      |

## Deployment Strategy

The application will be deployed as a single Docker container managed via a `docker-compose.yml` file. This ensures consistency and isolation. To avoid port conflicts, the service will be mapped to a non-standard port in the `14000` range.

**`docker-compose.yml`:**

```yaml
version: '3.8'

services:
  mcp-quickbuild-server:
    build: .
    ports:
      # Map host port 14002 to the container's port 14002
      - "14002:14002"
    environment:
      - QB_URL=http://your-quickbuild-host:8810
      - QB_USER=admin
      - QB_PASSWORD=your_qb_password
    volumes:
      - ./src:/usr/src/app/src
```

-----

# Implementation Plan

This project will be implemented in three distinct phases, moving from a basic read-only MVP to a feature-complete, production-ready server.

### Phase 1: MVP (1-2 prompts)

  - [x] Set up the project structure based on `spira-mcp-connection`.
  - [x] Create the `docker-compose.yml` with the specified port mapping.
  - [x] Implement the core `quickbuild_client.py` with authentication.
  - [x] Implement the `configurations.list` resource.
  - [x] Implement the `builds.get_latest_status` tool.
  - [x] Add basic logging and error handling.

### Phase 2: Core Functionality (2-3 prompts)

  - [ ] Implement the `builds.trigger` tool, including parameter handling for build variables.
  - [ ] Implement the `grid.list_agents` tool.
  - [ ] Implement the `changes.get_for_build` resource.
  - [ ] Write unit tests for the QuickBuild API client.
  - [ ] Add comprehensive error handling for API failures.

### Phase 3: Production Ready (1-2 prompts)

  - [ ] Implement the `system.backup_database` tool.
  - [ ] Implement the `configurations.create` tool with a simplified parameter set.
  - [ ] Add security hardening, such as input validation on all tool parameters.
  - [ ] Generate comprehensive documentation for all exposed tools and resources in the project's `README.md`.
  - [ ] Finalize the `Dockerfile` for a production build with no mounted volumes.