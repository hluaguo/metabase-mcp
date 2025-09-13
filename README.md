[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/cheukyin175-metabase-mcp-badge.png)](https://mseep.ai/app/cheukyin175-metabase-mcp)

# Metabase FastMCP Server

A FastMCP (Model Context Protocol) server for Metabase, built with Python. This server provides tools to interact with Metabase databases, execute queries, manage cards, and work with collections.

## Features

- List and manage Metabase databases
- Execute SQL queries and saved questions/cards
- Create and manage cards (questions)
- Work with collections
- List tables and fields
- Full authentication support (API Key or Session-based)

## Installation

### Quick Start with uv (Recommended)

1. **Install uv** if not already installed:
Please refer to uv


2. **Clone and setup**:
```bash
uv sync  # Install dependencies and create virtual environment
```

3. **Configure environment**:
```bash
cp .env.example .env
# Edit .env with your Metabase configuration
```

### Alternative Installation (pip)

```bash
pip install -r requirements.txt
```

## Configuration

Set the following environment variables in your `.env` file:

- `METABASE_URL`: Your Metabase instance URL
- `METABASE_API_KEY`: Your Metabase API key (preferred method)

OR

- `METABASE_USER_EMAIL`: Your Metabase user email
- `METABASE_PASSWORD`: Your Metabase password

## Usage

### Run the Server

```bash
# STDIO transport (default)
uv run python server.py

# SSE transport (uses HOST=0.0.0.0, PORT=8000 by default)
uv run python server.py --sse

# HTTP transport (uses HOST=0.0.0.0, PORT=8000 by default)
uv run python server.py --http

# Custom host and port via environment variables
HOST=localhost PORT=9000 uv run python server.py --sse
HOST=192.168.1.100 PORT=8080 uv run python server.py --http

# Set environment variables persistently
export HOST=localhost
export PORT=9000
uv run python server.py --sse
```

### FastMCP CLI Integration

```bash
# Run with FastMCP CLI
fastmcp run server.py

# Install as Claude Desktop MCP server
fastmcp install server.py -n "Metabase MCP"
```

### Cursor Integration

For Cursor IDE integration:

#### STDIO Transport (Default)
```bash
uv run python scripts/install-cursor.py
```

#### SSE Transport
```bash
# Install with SSE transport
uv run python scripts/install-cursor.py --sse        # Port 8000 (default)
uv run python scripts/install-cursor.py --sse 9000   # Custom port

# Or use the dedicated SSE installer
uv run python scripts/install-cursor-sse.py          # Port 8000
uv run python scripts/install-cursor-sse.py 9000     # Custom port
```

**Important for SSE**: You must start the server before using Cursor:
```bash
uv run python server.py --sse 8000
```

### Claude Integration
After running `uv sync`, you can find the Python executable at `/path/to/repo/.venv/bin/python`.
To integrate with Claude, add or update the configuration file at `~/Library/Application\ Support/Claude/claude_desktop_config.json`:
```json
{
    "mcpServers": {
        "metabase-mcp-server": {
            "command": "/path/to/repo/.venv/bin/python",
            "args": ["/path/to/repo/server.py"]
        }
    }
}
```

## Available Tools

- `list_databases`: List all databases in Metabase
- `list_cards`: List all questions/cards in Metabase  
- `execute_card`: Execute a Metabase question/card and get results
- `execute_query`: Execute a SQL query against a Metabase database
- `create_card`: Create a new question/card in Metabase
- `list_collections`: List all collections in Metabase
- `create_collection`: Create a new collection in Metabase
- `list_tables`: List all tables in a database
- `get_table_fields`: Get all fields/columns in a table

## Transport Methods

The server supports multiple transport methods:

- **STDIO** (default): For IDE integration (Cursor, Claude Desktop)
- **SSE**: Server-Sent Events for web applications
- **HTTP**: Standard HTTP for API access

```bash
uv run python server.py                        # STDIO (default)
uv run python server.py --sse                  # SSE (HOST=0.0.0.0, PORT=8000)
uv run python server.py --http                 # HTTP (HOST=0.0.0.0, PORT=8000)
HOST=localhost PORT=9000 uv run python server.py --sse   # Custom host/port
```

## Development

### Development Setup

```bash
# Install development dependencies (Python 3.12+)
uv sync --group dev

# Run tests
uv run pytest

# Format and lint code
uv run ruff check .          # Lint
uv run ruff format .         # Format
uv run black .               # Alternative formatter
uv run isort .               # Import sorting

# Type checking
uv run mypy server.py
```

### Validation

```bash
# Validate installation
uv run python scripts/validate.py
```

## Examples

Check out the example files for usage patterns:

- `examples/examples.py` - Basic usage examples
- `examples/quick-start.py` - Quick start guide
- `examples/sse-example.py` - SSE transport usage example

## Files Overview

- `server.py` - Main FastMCP server
- `pyproject.toml` - Modern Python project configuration
- `scripts/install-cursor.py` - Cross-platform Cursor installation
- `scripts/install-cursor-sse.py` - SSE-specific Cursor installation
- `scripts/validate.py` - Installation validation
- `examples/` - Usage examples and quick start guides
- `tests/test_server.py` - Basic server tests
- `config/cursor-config.json` - Example Cursor configuration 
