"""Compatibility facade: DNS helpers + legacy MotrixRPC name over cgs-aria2."""

from __future__ import annotations

import pathlib as p
from typing import Optional

from loguru import logger

from utils.script.aria2.conf import build_dns_options, normalize_dns_server
from utils.script.aria2.engine import create_managed_rpc_client
from utils.script.aria2.rpc import Aria2RpcClient, HTTPX_USER_AGENT, create_aria2_http_client

_MOTRIX_DNS_OPTION_KEYS = ("async-dns", "async-dns-server")

# Deprecated: do not use for new code. Managed engine picks a free port at ensure().
MOTRIX_RPC_URL = "http://127.0.0.1:0/jsonrpc"

create_motrix_http_client = create_aria2_http_client
normalize_motrix_dns_server = normalize_dns_server
build_motrix_dns_options = build_dns_options


def sync_motrix_dns_config(conf_path: object, *, dns_server: object = "") -> str:
    """Legacy helper kept for callers; CGS engine injects DNS via managed conf."""
    path = p.Path(str(conf_path or "").strip()).expanduser()
    if not str(path) or not path.exists():
        logger.info("[ScriptDoH] sync skipped (managed cgs-aria2 engine owns conf)")
        return "DNS 由 CGS 托管引擎注入，无需改外置 conf"
    dns_options = build_motrix_dns_options(dns_server=dns_server)
    original_lines = path.read_text(encoding="utf-8").splitlines()
    filtered_lines = []
    for line in original_lines:
        stripped = line.strip()
        if any(stripped.startswith(f"{key}=") for key in _MOTRIX_DNS_OPTION_KEYS):
            continue
        filtered_lines.append(line)
    if filtered_lines and filtered_lines[-1] != "":
        filtered_lines.append("")
    filtered_lines.extend(f"{key}={value}" for key, value in dns_options.items())
    path.write_text("\n".join(filtered_lines).rstrip() + "\n", encoding="utf-8")
    mode = f"async-dns-server={dns_options['async-dns-server']}" if dns_options else "清空 DNS 覆写"
    return f"已同步 DNS 配置（{mode}）"


class MotrixRPC(Aria2RpcClient):
    """Legacy name: auto-ensure managed engine when url is omitted."""

    def __init__(
        self,
        *,
        url: Optional[str] = None,
        secret: str = "",
        timeout: float = 15.0,
        session=None,
    ):
        if url:
            super().__init__(url=url, secret=secret, timeout=timeout, session=session)
            return
        client = create_managed_rpc_client(timeout=timeout)
        super().__init__(url=client.url, secret=client.secret, timeout=timeout, session=session or client.session)
