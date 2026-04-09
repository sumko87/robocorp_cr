"""
RoboCorp Control Room MCP Server
================================
An MCP server that exposes RoboCorp Control Room operations as tools.
Lets you list processes, start/stop runs, manage work items, workers, and more.

Usage:
    uv run server.py                    # stdio transport (for Claude Desktop)
    uv run server.py --transport http   # streamable HTTP (for web clients)
"""

from dotenv import load_dotenv
load_dotenv()

import os
import json
import httpx
from typing import Any, Optional
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

# ---------------------------------------------------------------------------
# Configuration – reads from environment variables
# ---------------------------------------------------------------------------
ROBOCORP_API_KEY = os.environ.get("ROBOCORP_API_KEY", "")
ROBOCORP_WORKSPACE_ID = os.environ.get("ROBOCORP_WORKSPACE_ID", "")

# SSO subdomain support: if you use SSO, set ROBOCORP_DOMAIN to your subdomain
# e.g. "personifyhealth" → https://personifyhealth.robocorp.com/api/v1
ROBOCORP_DOMAIN = os.environ.get("ROBOCORP_DOMAIN", "personifyhealth")

if ROBOCORP_DOMAIN and ROBOCORP_DOMAIN != "cloud":
    BASE_URL = f"https://{ROBOCORP_DOMAIN}.robocorp.com/api/v1"
else:
    BASE_URL = "https://cloud.robocorp.com/api/v1"

IS_RENDER = bool(os.environ.get("PORT"))


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------
def _headers() -> dict[str, str]:
    """Return authorization headers for the RoboCorp API."""
    return {
        "Authorization": f"RC-WSKEY {ROBOCORP_API_KEY}",
        "Content-Type": "application/json",
    }


async def _api_get(path: str, params: dict | None = None) -> dict[str, Any]:
    """Make an authenticated GET request to the RoboCorp API."""
    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        url = f"{BASE_URL}{path}"
        resp = await client.get(url, headers=_headers(), params=params)
        resp.raise_for_status()
        return resp.json()


async def _api_post(path: str, body: dict | None = None) -> dict[str, Any]:
    """Make an authenticated POST request to the RoboCorp API."""
    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        url = f"{BASE_URL}{path}"
        resp = await client.post(url, headers=_headers(), json=body or {})
        resp.raise_for_status()
        return resp.json()


async def _api_delete(path: str) -> dict[str, Any]:
    """Make an authenticated DELETE request to the RoboCorp API."""
    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        url = f"{BASE_URL}{path}"
        resp = await client.delete(url, headers=_headers())
        resp.raise_for_status()
        # Some DELETE endpoints return empty body
        if resp.status_code == 204 or not resp.content:
            return {"status": "deleted"}
        return resp.json()


async def _api_put(path: str, body: dict | None = None) -> dict[str, Any]:
    """Make an authenticated PUT request to the RoboCorp API."""
    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        url = f"{BASE_URL}{path}"
        resp = await client.put(url, headers=_headers(), json=body or {})
        resp.raise_for_status()
        return resp.json()


def _ws(workspace_id: str | None = None) -> str:
    """Return the workspace_id, falling back to the env default."""
    return workspace_id or ROBOCORP_WORKSPACE_ID


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------
_mcp_kwargs = dict(
    name="RoboCorp Control Room",
    instructions=(
        "This server connects to the RoboCorp Control Room REST API. "
        "Use these tools to manage automation processes, runs, workers, "
        "work items, and assets in your RoboCorp workspace."
    ),
)

# On Render: bind to 0.0.0.0 and disable DNS rebinding protection
if IS_RENDER:
    _mcp_kwargs["host"] = "0.0.0.0"
    _mcp_kwargs["transport_security"] = TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    )

mcp = FastMCP(**_mcp_kwargs)


# ── 1. LIST PROCESSES ──────────────────────────────────────────────────────
@mcp.tool()
async def list_processes(workspace_id: str = "") -> str:
    """List all automation processes in the workspace.

    Returns process names, IDs, descriptions, and step configurations.
    Use this to discover available processes before starting a run.

    Args:
        workspace_id: Optional workspace ID (uses default from env if empty).
    """
    ws = _ws(workspace_id)
    data = await _api_get(f"/workspaces/{ws}/processes")
    return json.dumps(data, indent=2)


# ── 2. GET PROCESS DETAILS ────────────────────────────────────────────────
@mcp.tool()
async def get_process(process_id: str, workspace_id: str = "") -> str:
    """Get detailed information about a specific process.

    Returns the process name, description, steps, worker configuration,
    and schedule settings.

    Args:
        process_id: The ID of the process to retrieve.
        workspace_id: Optional workspace ID (uses default from env if empty).
    """
    ws = _ws(workspace_id)
    data = await _api_get(f"/workspaces/{ws}/processes/{process_id}")
    return json.dumps(data, indent=2)


# ── 3. START A PROCESS RUN ────────────────────────────────────────────────
@mcp.tool()
async def start_process(
    process_id: str,
    work_items: str = "[]",
    workspace_id: str = "",
) -> str:
    """Start (trigger) a process run in Control Room.

    This creates a new process run. Optionally supply input work items
    as a JSON array of objects.

    Args:
        process_id: The ID of the process to start.
        work_items: JSON string of input work items, e.g. '[{"key": "value"}]'.
                    Pass '[]' or leave empty for no input data.
        workspace_id: Optional workspace ID (uses default from env if empty).
    """
    ws = _ws(workspace_id)
    items = json.loads(work_items)
    body: dict[str, Any] = {}
    if items:
        body["workItems"] = items
    data = await _api_post(f"/workspaces/{ws}/processes/{process_id}/process-runs", body)
    return json.dumps(data, indent=2)


# ── 4. LIST PROCESS RUNS ──────────────────────────────────────────────────
@mcp.tool()
async def list_process_runs(
    process_id: str,
    workspace_id: str = "",
    limit: int = 10,
) -> str:
    """List recent runs for a specific process.

    Returns run IDs, states, timestamps, and duration for each run.

    Args:
        process_id: The ID of the process.
        workspace_id: Optional workspace ID (uses default from env if empty).
        limit: Maximum number of runs to return (default 10).
    """
    ws = _ws(workspace_id)
    data = await _api_get(
        f"/workspaces/{ws}/process-runs",
        params={"process_id": process_id, "limit": limit},
    )
    return json.dumps(data, indent=2)


# ── 5. GET PROCESS RUN STATUS ─────────────────────────────────────────────
@mcp.tool()
async def get_process_run(
    run_id: str,
    workspace_id: str = "",
) -> str:
    """Get the status and details of a specific process run.

    Use this to check if a run is still in progress, completed, or failed.

    Args:
        run_id: The ID of the process run.
        workspace_id: Optional workspace ID (uses default from env if empty).
    """
    ws = _ws(workspace_id)
    data = await _api_get(
        f"/workspaces/{ws}/process-runs/{run_id}"
    )
    return json.dumps(data, indent=2)


# ── 6. STOP (CANCEL) A PROCESS RUN ────────────────────────────────────────
@mcp.tool()
async def stop_process_run(
    run_id: str,
    set_remaining_work_items_as_done: bool = False,
    terminate_ongoing_activity_runs: bool = False,
    workspace_id: str = "",
) -> str:
    """Stop (cancel) a running process run.

    Sends a cancellation request for the given process run.

    Args:
        run_id: The ID of the process run to cancel.
        set_remaining_work_items_as_done: Mark remaining work items as done (default False).
        terminate_ongoing_activity_runs: Terminate ongoing activity runs (default False).
        workspace_id: Optional workspace ID (uses default from env if empty).
    """
    ws = _ws(workspace_id)
    body = {
        "set_remaining_work_items_as_done": set_remaining_work_items_as_done,
        "terminate_ongoing_activity_runs": terminate_ongoing_activity_runs,
    }
    data = await _api_post(
        f"/workspaces/{ws}/process-runs/{run_id}/stop", body
    )
    return json.dumps(data, indent=2)


# ── 7. LIST WORKERS ───────────────────────────────────────────────────────
@mcp.tool()
async def list_workers(workspace_id: str = "") -> str:
    """List all workers (robots/agents) linked to the workspace.

    Returns worker IDs, names, types, status, and last-seen timestamps.

    Args:
        workspace_id: Optional workspace ID (uses default from env if empty).
    """
    ws = _ws(workspace_id)
    data = await _api_get(f"/workspaces/{ws}/workers")
    return json.dumps(data, indent=2)


# ── 8. LIST WORK ITEMS ────────────────────────────────────────────────────
@mcp.tool()
async def list_work_items(
    process_id: str,
    run_id: str,
    workspace_id: str = "",
    limit: int = 20,
) -> str:
    """List work items for a specific process run.

    Returns work item IDs, states (NEW, IN_PROGRESS, DONE, FAILED),
    and payload summaries.

    Args:
        process_id: The ID of the process.
        run_id: The ID of the process run.
        workspace_id: Optional workspace ID (uses default from env if empty).
        limit: Maximum number of work items to return (default 20).
    """
    ws = _ws(workspace_id)
    data = await _api_get(
        f"/workspaces/{ws}/work-items",
        params={"process_id": process_id, "process_run_id": run_id, "limit": limit},
    )
    return json.dumps(data, indent=2)


# ── 9. RETRY FAILED WORK ITEMS ────────────────────────────────────────────
@mcp.tool()
async def retry_work_items(
    work_item_ids: str,
    workspace_id: str = "",
) -> str:
    """Retry one or more failed work items.

    Sends a batch retry request for the specified work item IDs.

    Args:
        work_item_ids: Comma-separated work item IDs to retry,
                       e.g. 'id1,id2,id3' or a single ID 'id1'.
        workspace_id: Optional workspace ID (uses default from env if empty).
    """
    ws = _ws(workspace_id)
    ids = [wid.strip() for wid in work_item_ids.split(",") if wid.strip()]
    body = {
        "batch_operation": "retry",
        "work_item_ids": ids,
    }
    data = await _api_post(f"/workspaces/{ws}/work-items/batch", body)
    return json.dumps(data, indent=2)


# ── 10. LIST STEP RUNS ────────────────────────────────────────────────────
@mcp.tool()
async def list_step_runs(
    run_id: str,
    workspace_id: str = "",
) -> str:
    """List step runs within a process run.

    Each process run is composed of step runs. This returns the step name,
    state, worker used, duration, and any errors.

    Args:
        run_id: The ID of the process run.
        workspace_id: Optional workspace ID (uses default from env if empty).
    """
    ws = _ws(workspace_id)
    data = await _api_get(
        f"/workspaces/{ws}/step-runs",
        params={"process_run_id": run_id},
    )
    return json.dumps(data, indent=2)


# ── 11. GET STEP RUN ARTIFACTS ─────────────────────────────────────────────
@mcp.tool()
async def list_step_run_artifacts(
    step_run_id: str,
    workspace_id: str = "",
) -> str:
    """List artifacts (output files) produced by a step run.

    Returns artifact IDs, filenames, and sizes.

    Args:
        step_run_id: The ID of the step run.
        workspace_id: Optional workspace ID (uses default from env if empty).
    """
    ws = _ws(workspace_id)
    data = await _api_get(
        f"/workspaces/{ws}/step-runs/{step_run_id}/artifacts"
    )
    return json.dumps(data, indent=2)


# ── 12. LIST ASSETS ───────────────────────────────────────────────────────
@mcp.tool()
async def list_assets(workspace_id: str = "") -> str:
    """List all assets (stored data/files) in the workspace.

    Assets are named key-value stores used by processes.

    Args:
        workspace_id: Optional workspace ID (uses default from env if empty).
    """
    ws = _ws(workspace_id)
    data = await _api_get(f"/workspaces/{ws}/assets")
    return json.dumps(data, indent=2)


# ── 13. GET ASSET ─────────────────────────────────────────────────────────
@mcp.tool()
async def get_asset(
    asset_id: str,
    workspace_id: str = "",
) -> str:
    """Get a specific asset by ID or name.

    Returns the asset metadata and its payload/value.
    You can also pass a name prefixed with 'name:' e.g. 'name:my-asset'.

    Args:
        asset_id: Asset ID or 'name:asset-name'.
        workspace_id: Optional workspace ID (uses default from env if empty).
    """
    ws = _ws(workspace_id)
    data = await _api_get(f"/workspaces/{ws}/assets/{asset_id}")
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    transport = "stdio"
    if "--transport" in sys.argv:
        idx = sys.argv.index("--transport")
        if idx + 1 < len(sys.argv):
            transport = sys.argv[idx + 1]

    # When PORT env var is set (e.g. on Render), run SSE with uvicorn directly
    render_port = os.environ.get("PORT")
    if render_port:
        import uvicorn
        app = mcp.sse_app()
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=int(render_port),
            proxy_headers=True,
            forwarded_allow_ips="*",
        )
    elif transport == "http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
