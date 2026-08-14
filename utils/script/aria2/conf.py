from __future__ import annotations

import ipaddress
import pathlib as p
from typing import Mapping

FROZEN_ARIA2_OPTIONS: dict[str, str] = {
    "enable-rpc": "true",
    "rpc-allow-origin-all": "false",
    "rpc-listen-all": "false",
    "rpc-listen-port": "0",
    "check-certificate": "false",
    "max-connection-per-server": "16",
    "split": "16",
    "max-concurrent-downloads": "32",
    "continue": "true",
    "max-tries": "0",
    "retry-wait": "10",
    "connect-timeout": "10",
    "timeout": "10",
    "http-accept-gzip": "true",
    "content-disposition-default-utf8": "true",
    "min-split-size": "1M",
    "disk-cache": "64M",
    "file-allocation": "falloc",
    "auto-save-interval": "10",
    "save-session-interval": "10",
    "max-file-not-found": "10",
    "remote-time": "true",
    "summary-interval": "0",
}


def normalize_proxy(value: object) -> str:
    """Normalize user-facing proxy string; empty means direct."""
    text = str(value or "").strip()
    if not text:
        return ""
    if "://" not in text:
        return f"http://{text}"
    return text


# Legacy name used only while call sites migrate.
normalize_all_proxy = normalize_proxy


def normalize_dns_server(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        pass
    candidate = text
    if text.startswith("[") and "]:" in text:
        host, port = text[1:].split("]:", 1)
        if port != "53":
            raise ValueError("aria2 async-dns-server only supports DNS service on port 53")
        candidate = host
    elif text.count(":") == 1:
        host, port = text.rsplit(":", 1)
        if port.isdigit():
            if port != "53":
                raise ValueError("aria2 async-dns-server only supports DNS service on port 53")
            candidate = host
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError as exc:
        raise ValueError("aria2 async-dns-server requires an IP address such as 127.0.0.1") from exc


def build_dns_options(*, dns_server: object = "") -> dict[str, str]:
    normalized_server = normalize_dns_server(dns_server)
    if not normalized_server:
        return {}
    return {
        "async-dns": "true",
        "async-dns-server": normalized_server,
    }


def build_aria2_option_map(
    *,
    rpc_port: int,
    proxy: object = "",
    dns_server: object = "",
    secret: object = "",
    session_path: p.Path | None = None,
    extra: Mapping[str, str] | None = None,
    # legacy kw for call sites mid-rename
    all_proxy: object = "",
) -> dict[str, str]:
    options = dict(FROZEN_ARIA2_OPTIONS)
    options["rpc-listen-port"] = str(int(rpc_port))
    # Only aria2 conf wire uses the engine option name "all-proxy".
    resolved_proxy = normalize_proxy(proxy if proxy not in ("", None) else all_proxy)
    if resolved_proxy:
        options["all-proxy"] = resolved_proxy
    secret_text = str(secret or "").strip()
    if secret_text:
        options["rpc-secret"] = secret_text
    if session_path is not None:
        options["save-session"] = str(session_path)
        options["input-file"] = str(session_path)
    options.update(build_dns_options(dns_server=dns_server))
    if extra:
        options.update({str(key): str(value) for key, value in extra.items()})
    return options


def render_aria2_conf(options: Mapping[str, str]) -> str:
    lines = [
        "###############################",
        "# CGS managed aria2 conf",
        "###############################",
        "",
    ]
    for key, value in options.items():
        if value is None or value == "":
            continue
        lines.append(f"{key}={value}")
    lines.append("")
    return "\n".join(lines)


def write_aria2_conf(path: p.Path, options: Mapping[str, str]) -> p.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_aria2_conf(options), encoding="utf-8")
    return path
