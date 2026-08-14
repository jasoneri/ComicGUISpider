from utils.script.aria2.bootstrap import (
    Aria2BinaryBootstrapError,
    UnsupportedAria2PlatformError,
    ensure_aira2_binary,
)
from utils.script.aria2.conf import (
    FROZEN_ARIA2_OPTIONS,
    build_aria2_option_map,
    normalize_proxy,
    render_aria2_conf,
    write_aria2_conf,
)
from utils.script.aria2.engine import (
    CgsAria2Engine,
    RuntimeEndpoint,
    create_managed_rpc_client,
    ensure_engine,
    get_engine,
    stop_engine,
)
from utils.script.aria2.import_motrix import import_motrix_proxy_once, read_motrix_proxy
from utils.script.aria2.rpc import Aria2RpcClient, HTTPX_USER_AGENT, MotrixRPC
from utils.script.aria2.settings import (
    ensure_motrix_proxy_seed,
    get_cgs_aria2_section,
    get_proxy,
    set_proxy,
)

__all__ = [
    "Aria2BinaryBootstrapError",
    "Aria2RpcClient",
    "CgsAria2Engine",
    "FROZEN_ARIA2_OPTIONS",
    "HTTPX_USER_AGENT",
    "MotrixRPC",
    "RuntimeEndpoint",
    "UnsupportedAria2PlatformError",
    "build_aria2_option_map",
    "create_managed_rpc_client",
    "ensure_aira2_binary",
    "ensure_engine",
    "ensure_motrix_proxy_seed",
    "get_cgs_aria2_section",
    "get_engine",
    "get_proxy",
    "import_motrix_proxy_once",
    "normalize_proxy",
    "read_motrix_proxy",
    "render_aria2_conf",
    "set_proxy",
    "stop_engine",
    "write_aria2_conf",
]
