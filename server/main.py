from __future__ import annotations

import os
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

# Parent ServerLauncher sets this so the child never "resolve existing → exit 0"
# without publishing its own tray discovery (that race is what users see as
# "cgs-server exited with code 0; discovery: no tray-hosted record").
_FORCE_HOST_ENV = "CGS_SERVER_FORCE_HOST"


def _env_flag(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().casefold() in {"1", "true", "yes", "on"}


def main() -> int:
    configure_server_launch_logging()
    if len(sys.argv) > 1:
        raise SystemExit("cgs-server does not accept startup parameters")

    force_host = _env_flag(_FORCE_HOST_ENV)
    if not force_host:
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
