from __future__ import annotations

import sys

from utils.server_control import (
    DEFAULT_SERVER_BIND_HOST,
    TRAY_SERVER_SURFACE,
    ServerLauncher,
    bind_tcp_socket,
    configure_server_launch_logging,
    create_server_record,
    socket_port,
    sync_redviewer_server_endpoint,
)
from variables import VER


def main() -> int:
    configure_server_launch_logging()
    if len(sys.argv) > 1:
        raise SystemExit("cgs-server does not accept startup parameters")

    endpoint = ServerLauncher(timeout=1.0).resolve_existing()
    if endpoint is not None:
        sync_redviewer_server_endpoint(endpoint)
        return 0

    from server.tray.host import ServerTrayHost

    sock = bind_tcp_socket(DEFAULT_SERVER_BIND_HOST, 0)
    record = create_server_record(
        bind_host=DEFAULT_SERVER_BIND_HOST,
        port=socket_port(sock),
        surfaces=("http", "mcp", TRAY_SERVER_SURFACE),
        version=VER,
    )
    return ServerTrayHost(sock=sock, record=record).run()


if __name__ == "__main__":
    raise SystemExit(main())
