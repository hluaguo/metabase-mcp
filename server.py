#!/usr/bin/env python3
"""
Metabase FastMCP Server

A FastMCP server that provides tools to interact with Metabase databases,
execute queries, manage cards, and work with collections.
"""

import logging
import os
import sys
from enum import Enum
from typing import Any

import httpx
from dotenv import load_dotenv
from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware
from fastmcp.server.middleware.logging import LoggingMiddleware

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get Metabase configuration from environment variables
METABASE_URL = os.getenv("METABASE_URL")
METABASE_USER_EMAIL = os.getenv("METABASE_USER_EMAIL")
METABASE_PASSWORD = os.getenv("METABASE_PASSWORD")
METABASE_API_KEY = os.getenv("METABASE_API_KEY")

if not METABASE_URL or (
    not METABASE_API_KEY and (not METABASE_USER_EMAIL or not METABASE_PASSWORD)
):
    raise ValueError(
        "METABASE_URL is required, and either METABASE_API_KEY or both METABASE_USER_EMAIL and METABASE_PASSWORD must be provided"
    )


# Authentication method enum
class AuthMethod(Enum):
    SESSION = "session"
    API_KEY = "api_key"


# Initialize FastMCP server with best practices configuration
mcp = FastMCP(
    name="metabase-mcp",
    on_duplicate="error",  # Prevent accidental tool/resource/prompt overwrites
)

# Add middleware for enhanced error handling and logging
mcp.add_middleware(ErrorHandlingMiddleware())  # Handle errors first
mcp.add_middleware(LoggingMiddleware())  # Log all operations


class MetabaseClient:
    """HTTP client for Metabase API operations"""

    def __init__(self):
        self.base_url = METABASE_URL.rstrip("/")
        self.session_token: str | None = None
        self.api_key: str | None = METABASE_API_KEY
        self.auth_method = AuthMethod.API_KEY if METABASE_API_KEY else AuthMethod.SESSION
        self.client = httpx.AsyncClient(timeout=30.0)

        logger.info(f"Using {self.auth_method.value} authentication method")

    async def _get_headers(self) -> dict[str, str]:
        """Get appropriate authentication headers"""
        headers = {"Content-Type": "application/json"}

        if self.auth_method == AuthMethod.API_KEY and self.api_key:
            headers["X-API-KEY"] = self.api_key
        elif self.auth_method == AuthMethod.SESSION:
            if not self.session_token:
                await self._get_session_token()
            if self.session_token:
                headers["X-Metabase-Session"] = self.session_token

        return headers

    async def _get_session_token(self) -> str:
        """Get Metabase session token for email/password authentication"""
        if self.auth_method == AuthMethod.API_KEY and self.api_key:
            return self.api_key

        if not METABASE_USER_EMAIL or not METABASE_PASSWORD:
            raise ValueError("Email and password required for session authentication")

        login_data = {"username": METABASE_USER_EMAIL, "password": METABASE_PASSWORD}

        response = await self.client.post(f"{self.base_url}/api/session", json=login_data)

        if response.status_code != 200:
            error_data = response.json() if response.content else {}
            raise Exception(f"Authentication failed: {response.status_code} - {error_data}")

        session_data = response.json()
        self.session_token = session_data.get("id")
        logger.info("Successfully obtained session token")
        return self.session_token

    async def request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        """Make authenticated request to Metabase API"""
        url = f"{self.base_url}/api{path}"
        headers = await self._get_headers()

        logger.debug(f"Making {method} request to {path}")

        response = await self.client.request(method=method, url=url, headers=headers, **kwargs)

        if not response.is_success:
            error_data = response.json() if response.content else {}
            error_message = (
                f"API request failed with status {response.status_code}: {response.text}"
            )
            logger.warning(f"{error_message} - {error_data}")
            raise Exception(error_message)

        logger.debug(f"Successful response from {path}")
        return response.json()

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


# Global client instance
metabase_client = MetabaseClient()


# =============================================================================
# Tool Definitions - Database Operations
# =============================================================================

@mcp.tool
async def list_databases(ctx: Context) -> dict[str, Any]:
    """
    List all databases configured in Metabase.

    Returns:
        A dictionary containing all available databases with their metadata.
    """
    try:
        await ctx.info("Fetching list of databases from Metabase")
        result = await metabase_client.request("GET", "/database")
        await ctx.info(f"Successfully retrieved {len(result.get('data', []))} databases")
        return result
    except Exception as e:
        error_msg = f"Error listing databases: {e}"
        await ctx.error(error_msg)
        raise ToolError(error_msg) from e


@mcp.tool
async def list_tables(database_id: int, ctx: Context) -> str:
    """
    List all tables in a specific database.

    Args:
        database_id: The ID of the database to query.

    Returns:
        Formatted markdown table showing table details.
    """
    try:
        await ctx.info(f"Fetching tables for database {database_id}")
        result = await metabase_client.request("GET", f"/database/{database_id}/metadata")

        # Extract and format tables
        tables = result.get("tables", [])
        await ctx.debug(f"Found {len(tables)} tables in database {database_id}")

        formatted_tables = [
            {
                "table_id": table.get("id"),
                "display_name": table.get("display_name"),
                "description": table.get("description") or "No description",
                "entity_type": table.get("entity_type")
            }
            for table in tables
        ]

        # Sort for better readability
        formatted_tables.sort(key=lambda x: x.get("display_name", ""))

        # Generate markdown output
        markdown_output = f"# Tables in Database {database_id}\n\n"
        markdown_output += f"**Total Tables:** {len(formatted_tables)}\n\n"

        if not formatted_tables:
            await ctx.warning(f"No tables found in database {database_id}")
            markdown_output += "*No tables found in this database.*\n"
            return markdown_output

        # Create markdown table
        markdown_output += "| Table ID | Display Name | Description | Entity Type |\n"
        markdown_output += "|----------|--------------|-------------|--------------|\n"

        for table in formatted_tables:
            table_id = table.get("table_id", "N/A")
            display_name = table.get("display_name", "N/A")
            description = table.get("description", "No description")
            entity_type = table.get("entity_type", "N/A")

            # Escape pipe characters
            description = description.replace("|", "\\|")
            display_name = display_name.replace("|", "\\|")

            markdown_output += f"| {table_id} | {display_name} | {description} | {entity_type} |\n"

        await ctx.info(f"Successfully formatted {len(formatted_tables)} tables")
        return markdown_output

    except Exception as e:
        error_msg = f"Error listing tables for database {database_id}: {e}"
        await ctx.error(error_msg)
        raise ToolError(error_msg) from e


@mcp.tool
async def get_table_fields(table_id: int, ctx: Context, limit: int = 20) -> dict[str, Any]:
    """
    Get all fields/columns in a specific table.

    Args:
        table_id: The ID of the table.
        limit: Maximum number of fields to return (default: 20).

    Returns:
        Dictionary with field metadata, truncated if necessary.
    """
    try:
        await ctx.info(f"Fetching fields for table {table_id}")
        result = await metabase_client.request("GET", f"/table/{table_id}/query_metadata")

        # Apply field limiting
        if limit > 0 and "fields" in result and len(result["fields"]) > limit:
            total_fields = len(result["fields"])
            result["fields"] = result["fields"][:limit]
            result["_truncated"] = True
            result["_total_fields"] = total_fields
            result["_limit_applied"] = limit
            await ctx.info(f"Truncated {total_fields} fields to {limit} fields")
        else:
            await ctx.info(f"Retrieved {len(result.get('fields', []))} fields")

        return result
    except Exception as e:
        error_msg = f"Error getting table fields for table {table_id}: {e}"
        await ctx.error(error_msg)
        raise ToolError(error_msg) from e


# =============================================================================
# Tool Definitions - Query Operations
# =============================================================================

@mcp.tool
async def execute_query(
    database_id: int,
    query: str,
    ctx: Context,
    native_parameters: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """
    Execute a native SQL query against a Metabase database.

    Args:
        database_id: The ID of the database to query.
        query: The SQL query to execute.
        native_parameters: Optional parameters for the query.

    Returns:
        Query execution results.
    """
    try:
        await ctx.info(f"Executing query on database {database_id}")
        await ctx.debug(f"Query: {query[:100]}...")  # Log first 100 chars

        payload = {
            "database": database_id,
            "type": "native",
            "native": {"query": query}
        }

        if native_parameters:
            payload["native"]["parameters"] = native_parameters
            await ctx.debug(f"Query parameters: {len(native_parameters)} parameters provided")

        result = await metabase_client.request("POST", "/dataset", json=payload)

        row_count = len(result.get("data", {}).get("rows", []))
        await ctx.info(f"Query executed successfully, returned {row_count} rows")

        return result
    except Exception as e:
        error_msg = f"Error executing query: {e}"
        await ctx.error(error_msg)
        raise ToolError(error_msg) from e


@mcp.tool
async def execute_mongodb_query(
    database_id: int,
    collection: str,
    query: Any,
    ctx: Context,
    native_parameters: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """
    Execute a MongoDB native query against a Metabase database.

    Args:
        database_id: The ID of the MongoDB database to query.
        collection: The MongoDB collection name.
        query: The MongoDB query (aggregation pipeline array or query object).
        native_parameters: Optional parameters for the query.

    Returns:
        Query execution results.
    """
    try:
        import json

        await ctx.info(f"Executing MongoDB query on database {database_id}, collection {collection}")

        # Convert query to JSON string if it's not already a string
        if isinstance(query, (list, dict)):
            query_string = json.dumps(query)
            await ctx.debug(f"Converted query object to JSON string")
        else:
            query_string = str(query)

        payload = {
            "database": database_id,
            "type": "native",
            "native": {
                "query": query_string,
                "collection": collection
            }
        }

        if native_parameters:
            payload["native"]["parameters"] = native_parameters
            await ctx.debug(f"Query parameters: {len(native_parameters)} parameters provided")

        result = await metabase_client.request("POST", "/dataset", json=payload)

        row_count = len(result.get("data", {}).get("rows", []))
        await ctx.info(f"MongoDB query executed successfully, returned {row_count} rows")

        return result
    except Exception as e:
        error_msg = f"Error executing MongoDB query: {e}"
        await ctx.error(error_msg)
        raise ToolError(error_msg) from e


# =============================================================================
# Tool Definitions - Card/Question Operations
# =============================================================================

@mcp.tool
async def list_cards(ctx: Context) -> dict[str, Any]:
    """
    List all saved questions/cards in Metabase.

    Returns:
        Dictionary containing all cards with their metadata.
    """
    try:
        await ctx.info("Fetching list of saved cards/questions")
        result = await metabase_client.request("GET", "/card")
        card_count = len(result) if isinstance(result, list) else len(result.get("data", []))
        await ctx.info(f"Successfully retrieved {card_count} cards")
        return result
    except Exception as e:
        error_msg = f"Error listing cards: {e}"
        await ctx.error(error_msg)
        raise ToolError(error_msg) from e


@mcp.tool
async def execute_card(
    card_id: int,
    ctx: Context,
    parameters: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Execute a saved Metabase question/card and retrieve results.

    Args:
        card_id: The ID of the card to execute.
        parameters: Optional parameters for the card execution.

    Returns:
        Card execution results.
    """
    try:
        await ctx.info(f"Executing card {card_id}")
        payload = {}
        if parameters:
            payload["parameters"] = parameters
            await ctx.debug(f"Card parameters: {parameters}")

        result = await metabase_client.request("POST", f"/card/{card_id}/query", json=payload)

        row_count = len(result.get("data", {}).get("rows", []))
        await ctx.info(f"Card {card_id} executed successfully, returned {row_count} rows")

        return result
    except Exception as e:
        error_msg = f"Error executing card {card_id}: {e}"
        await ctx.error(error_msg)
        raise ToolError(error_msg) from e


@mcp.tool
async def create_card(
    name: str,
    database_id: int,
    query: str,
    ctx: Context,
    description: str | None = None,
    collection_id: int | None = None,
    visualization_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create a new question/card in Metabase.

    Args:
        name: Name of the card.
        database_id: ID of the database to query.
        query: SQL query for the card.
        description: Optional description.
        collection_id: Optional collection to place the card in.
        visualization_settings: Optional visualization configuration.

    Returns:
        The created card object.
    """
    try:
        await ctx.info(f"Creating new card '{name}' in database {database_id}")

        payload = {
            "name": name,
            "database_id": database_id,
            "dataset_query": {
                "database": database_id,
                "type": "native",
                "native": {"query": query},
            },
            "display": "table",
            "visualization_settings": visualization_settings or {},
        }

        if description:
            payload["description"] = description
        if collection_id is not None:
            payload["collection_id"] = collection_id
            await ctx.debug(f"Card will be placed in collection {collection_id}")

        result = await metabase_client.request("POST", "/card", json=payload)
        await ctx.info(f"Successfully created card with ID {result.get('id')}")

        return result
    except Exception as e:
        error_msg = f"Error creating card: {e}"
        await ctx.error(error_msg)
        raise ToolError(error_msg) from e


@mcp.tool
async def create_mongodb_card(
    name: str,
    database_id: int,
    collection: str,
    query: str,
    ctx: Context,
    description: str | None = None,
    collection_id: int | None = None,
    visualization_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create a new MongoDB question/card in Metabase.

    Args:
        name: Name of the card.
        database_id: ID of the MongoDB database.
        collection: MongoDB collection name.
        query: MongoDB query string (aggregation pipeline or query).
        description: Optional description.
        collection_id: Optional collection to place the card in.
        visualization_settings: Optional visualization configuration.

    Returns:
        The created MongoDB card object.
    """
    try:
        await ctx.info(f"Creating new MongoDB card '{name}' for collection {collection}")

        payload = {
            "name": name,
            "database_id": database_id,
            "dataset_query": {
                "database": database_id,
                "type": "native",
                "native": {
                    "query": query,
                    "collection": collection
                },
            },
            "display": "table",
            "visualization_settings": visualization_settings or {},
        }

        if description:
            payload["description"] = description
        if collection_id is not None:
            payload["collection_id"] = collection_id
            await ctx.debug(f"MongoDB card will be placed in collection {collection_id}")

        result = await metabase_client.request("POST", "/card", json=payload)
        await ctx.info(f"Successfully created MongoDB card with ID {result.get('id')}")

        return result
    except Exception as e:
        error_msg = f"Error creating MongoDB card: {e}"
        await ctx.error(error_msg)
        raise ToolError(error_msg) from e


@mcp.tool
async def update_card_display(
    card_id: int,
    display: str,
    ctx: Context,
    visualization_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Update the display type of a saved question/card in Metabase.

    Args:
        card_id: The ID of the card to update.
        display: The display type (e.g. "table", "bar", "line", "pie", "scalar", "row", "area", "combo", "pivot", "smartscalar", "funnel", "waterfall", "map").
        visualization_settings: Optional visualization settings to apply with the display change.

    Returns:
        The updated card object.
    """
    try:
        await ctx.info(f"Updating card {card_id} display to '{display}'")

        payload: dict[str, Any] = {"display": display}

        if visualization_settings is not None:
            payload["visualization_settings"] = visualization_settings
            await ctx.debug(f"Applying visualization settings: {visualization_settings}")

        result = await metabase_client.request("PUT", f"/card/{card_id}", json=payload)
        await ctx.info(f"Successfully updated card {card_id} display to '{display}'")

        return result
    except Exception as e:
        error_msg = f"Error updating card {card_id} display: {e}"
        await ctx.error(error_msg)
        raise ToolError(error_msg) from e


# =============================================================================
# Tool Definitions - Dashboard Operations
# =============================================================================

@mcp.tool
async def list_dashboards(ctx: Context) -> list[dict[str, Any]]:
    """
    List all dashboards in Metabase.

    Returns:
        A list of dashboards with their metadata including id, name,
        description, collection_id, and creator info.
    """
    try:
        await ctx.info("Fetching list of dashboards from Metabase")
        result = await metabase_client.request("GET", "/dashboard")
        dashboard_count = len(result) if isinstance(result, list) else len(result.get("data", []))
        await ctx.info(f"Successfully retrieved {dashboard_count} dashboards")
        return result
    except Exception as e:
        error_msg = f"Error listing dashboards: {e}"
        await ctx.error(error_msg)
        raise ToolError(error_msg) from e


@mcp.tool
async def get_dashboard_cards(dashboard_id: int, ctx: Context) -> list[dict[str, Any]]:
    """
    Get the cards and their layout information for a specific dashboard.

    Returns each card's id, name, display type, size, and position on the
    dashboard grid (col, row, size_x, size_y).

    Args:
        dashboard_id: The ID of the dashboard.

    Returns:
        A list of dashboard card objects with layout and card metadata.
    """
    try:
        await ctx.info(f"Fetching cards layout for dashboard {dashboard_id}")
        result = await metabase_client.request("GET", f"/dashboard/{dashboard_id}")

        dashcards = result.get("dashcards", result.get("ordered_cards", []))
        await ctx.info(
            f"Successfully retrieved {len(dashcards)} cards from dashboard {dashboard_id}"
        )

        cards_layout = []
        for dashcard in dashcards:
            card_info: dict[str, Any] = {
                "dashcard_id": dashcard.get("id"),
                "card_id": dashcard.get("card_id"),
                "col": dashcard.get("col"),
                "row": dashcard.get("row"),
                "size_x": dashcard.get("size_x"),
                "size_y": dashcard.get("size_y"),
            }

            card = dashcard.get("card")
            if card:
                card_info["card_name"] = card.get("name")
                card_info["card_display"] = card.get("display")
                card_info["card_description"] = card.get("description")

            cards_layout.append(card_info)

        return cards_layout
    except Exception as e:
        error_msg = f"Error fetching dashboard {dashboard_id} cards: {e}"
        await ctx.error(error_msg)
        raise ToolError(error_msg) from e


@mcp.tool
async def add_card_to_dashboard(
    dashboard_id: int,
    card_id: int,
    ctx: Context,
    col: int = 0,
    row: int = 0,
    size_x: int = 6,
    size_y: int = 4,
) -> dict[str, Any]:
    """
    Add an existing card to a dashboard at a specified position and size.

    Args:
        dashboard_id: The ID of the dashboard to add the card to.
        card_id: The ID of the card to add.
        col: Column position on the dashboard grid (default: 0).
        row: Row position on the dashboard grid (default: 0).
        size_x: Width of the card in grid units (default: 6).
        size_y: Height of the card in grid units (default: 4).

    Returns:
        The created dashboard card object.
    """
    try:
        await ctx.info(f"Adding card {card_id} to dashboard {dashboard_id}")

        # Fetch existing dashboard to get current dashcards
        dashboard = await metabase_client.request("GET", f"/dashboard/{dashboard_id}")
        existing_dashcards = dashboard.get("dashcards", dashboard.get("ordered_cards", []))

        # Preserve existing dashcards with their current layout
        dashcards = [
            {
                "id": dc["id"],
                "card_id": dc.get("card_id"),
                "row": dc.get("row"),
                "col": dc.get("col"),
                "size_x": dc.get("size_x"),
                "size_y": dc.get("size_y"),
            }
            for dc in existing_dashcards
        ]

        # Append new card with id: -1 to indicate a new entry
        dashcards.append({
            "id": -1,
            "card_id": card_id,
            "row": row,
            "col": col,
            "size_x": size_x,
            "size_y": size_y,
        })

        result = await metabase_client.request(
            "PUT", f"/dashboard/{dashboard_id}", json={"dashcards": dashcards}
        )
        await ctx.info(
            f"Successfully added card {card_id} to dashboard {dashboard_id} at ({col}, {row})"
        )

        return result
    except Exception as e:
        error_msg = f"Error adding card {card_id} to dashboard {dashboard_id}: {e}"
        await ctx.error(error_msg)
        raise ToolError(error_msg) from e


# =============================================================================
# Tool Definitions - Collection Operations
# =============================================================================

@mcp.tool
async def list_collections(ctx: Context) -> dict[str, Any]:
    """
    List all collections in Metabase.

    Returns:
        Dictionary containing all collections with their metadata.
    """
    try:
        await ctx.info("Fetching list of collections")
        result = await metabase_client.request("GET", "/collection")
        collection_count = len(result) if isinstance(result, list) else len(result.get("data", []))
        await ctx.info(f"Successfully retrieved {collection_count} collections")
        return result
    except Exception as e:
        error_msg = f"Error listing collections: {e}"
        await ctx.error(error_msg)
        raise ToolError(error_msg) from e


@mcp.tool
async def create_collection(
    name: str,
    ctx: Context,
    description: str | None = None,
    color: str | None = None,
    parent_id: int | None = None,
) -> dict[str, Any]:
    """
    Create a new collection in Metabase.

    Args:
        name: Name of the collection.
        description: Optional description.
        color: Optional color for the collection.
        parent_id: Optional parent collection ID.

    Returns:
        The created collection object.
    """
    try:
        await ctx.info(f"Creating new collection '{name}'")

        payload = {"name": name}

        if description:
            payload["description"] = description
        if color:
            payload["color"] = color
            await ctx.debug(f"Collection color: {color}")
        if parent_id is not None:
            payload["parent_id"] = parent_id
            await ctx.debug(f"Collection parent ID: {parent_id}")

        result = await metabase_client.request("POST", "/collection", json=payload)
        await ctx.info(f"Successfully created collection with ID {result.get('id')}")

        return result
    except Exception as e:
        error_msg = f"Error creating collection: {e}"
        await ctx.error(error_msg)
        raise ToolError(error_msg) from e


def main():
    """
    Main entry point for the Metabase MCP server.

    Supports multiple transport methods:
    - STDIO (default): For IDE integration
    - SSE: Server-Sent Events for web apps
    - HTTP: Standard HTTP for API access
    """
    # Get configuration from environment
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))

    # Parse transport argument
    transport = "stdio"  # default
    if "--sse" in sys.argv:
        transport = "sse"
    elif "--http" in sys.argv:
        transport = "streamable-http"
    elif "--stdio" in sys.argv:
        transport = "stdio"

    logger.info(f"Starting Metabase MCP server with {transport} transport")

    try:
        # Run server with appropriate transport
        if transport in ["sse", "streamable-http"]:
            logger.info(f"Server will be available at http://{host}:{port}")
            mcp.run(transport=transport, host=host, port=port)
        else:
            mcp.run(transport=transport)

    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise


if __name__ == "__main__":
    main()
