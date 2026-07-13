from __future__ import annotations

import argparse

from server.mcp import HttpCgsMcpBackend, create_cgs_mcp_server
from utils.server_control import ServerLauncher, auth_headers


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the ComicGUISpider MCP stdio proxy.")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    try:
        endpoint = ServerLauncher(timeout=args.timeout).launch_or_resolve()
        server = create_cgs_mcp_server(
            HttpCgsMcpBackend(endpoint.connect_url, timeout=args.timeout, headers=auth_headers(endpoint))
        )
        server.run(transport="stdio")
        return 0
    except Exception as exc:
        raise RuntimeError("cgs-mcp failed to resolve, launch, or serve CGS Server") from exc


if __name__ == "__main__":
    raise SystemExit(main())
