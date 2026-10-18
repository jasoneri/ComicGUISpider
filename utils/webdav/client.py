# -*- coding: utf-8 -*-
"""RFC 4918 动词封装(CGS013 §4)。

要点:URL 逐段 UTF-8 百分号编码、`mkdir_p` 走逐级 PROPFIND→MKCOL 阶梯、
上传 `content=<iterator>` 且每次重试重新 open 文件句柄。

**所有动词都是幂等的**,所以传输层错误与 5xx 一律可重放:
`PROPFIND / GET / PUT / MKCOL / MOVE / DELETE`(RFC 9110 §9.2.2;RFC 7231 §4.2.2
原文允许"读不到响应即可自动重复"),统一走 `_send` 的退避重试,4xx 不重试。
覆盖异常取 `httpx.TransportError`(它是 `RemoteProtocolError` / `ReadError` /
`WriteError` / `ConnectError` / 各 `TimeoutException` 的公共基类)。

读路径必须重试,原因见 canon claim 7:网盘型 WebDAV 反代在重发 CDN 内容时可能
把 `Content-Length` 分帧写错(RFC 9112 §6.3 违规),客户端只会看到半截 body;
这是**可重试的传输层故障,不是终态**。

**但重试救不了确定性缺陷,所以额外禁用压缩协商**:客户端固定发
`Accept-Encoding: identity`。实测(2026-09-12,OpenList v4.2.6 + 夸克驱动)发现:
一旦客户端广告 `gzip`,OpenList 会把 body 压缩后发出(596B)却**丢掉 `Content-Encoding`**,
并把 `Content-Length` 留成**未压缩**尺寸(1310B);客户端无法解码,且分帧不匹配直接触发
`RemoteProtocolError`。该现象 6/6 必现、静置 15s 后仍必现,而改发 `identity` 立即成功 ——
所以它不是瞬时抖动,而是网盘驱动的 proxy 缺陷。

自签证书请通过 `verify=<CA bundle 路径>` 传入,`verify=False` 被禁止。
"""
import time
import typing as t
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote, unquote

import httpx

CHUNK_SIZE = 64 * 1024
MAX_RETRIES = 3
RETRY_EXCEPTIONS = (httpx.TransportError,)
DAV = "{DAV:}"
PROPFIND_BODY = (
    '<?xml version="1.0" encoding="utf-8"?>'
    f'<propfind xmlns="DAV:"><prop><resourcetype/><getcontentlength/>'
    f'<getlastmodified/><getetag/><displayname/></prop></propfind>'
)


def current_proxy_url() -> str | None:
    """配置(conf.proxies)里当前生效的代理地址;没配代理返回 None。"""
    from utils import conf

    proxies = [str(item) for item in (getattr(conf, "proxies", None) or []) if item]
    if not proxies:
        return None
    first = proxies[0]
    return first if "://" in first else f"http://{first}"


def proxy_kwargs(use_proxy: object) -> dict:
    """勾选走代理时给出 httpx 的 proxy 参数;未勾选返回空 dict(保持直连现状)。"""
    if not use_proxy:
        return {}
    proxy = current_proxy_url()
    return {"proxy": proxy} if proxy else {}


class WebDavError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class WebDavAuthError(WebDavError):
    """401 / 403:凭据或权限不足,整批中止并提示检查 WebDAV 权限。"""


class WebDavNotFoundError(WebDavError):
    """404。"""


class WebDavConflictError(WebDavError):
    """409 / 412。"""


class WebDavLockedError(WebDavError):
    """423:资源锁定,不重试循环。"""


def _split(path) -> list[str]:
    segments = [s for s in str(path).replace("\\", "/").split("/") if s and s != "."]
    if ".." in segments:
        raise ValueError("WebDAV 路径不能包含上级目录")
    return segments


def _backoff(attempt: int) -> float:
    return min(30.0, 2.0 * 1.5 ** attempt)


def build_error(method: str, url: str, resp: httpx.Response) -> WebDavError:
    message = f"{method} {unquote(url)} -> {resp.status_code}"
    if resp.status_code in (401, 403):
        return WebDavAuthError(message, resp.status_code)
    if resp.status_code == 404:
        return WebDavNotFoundError(message, resp.status_code)
    if resp.status_code == 423:
        return WebDavLockedError(message, resp.status_code)
    if resp.status_code in (409, 412):
        return WebDavConflictError(message, resp.status_code)
    return WebDavError(message, resp.status_code)


def parse_multistatus(xml_text: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise WebDavError(f"PROPFIND 响应不是合法 XML: {e}") from e
    result = []
    for resp in root.findall(f"{DAV}response"):
        href_el = resp.find(f"{DAV}href")
        href = unquote(href_el.text or "") if href_el is not None else ""
        node = {"href": href, "name": "", "is_dir": False, "size": None, "modified": None, "etag": None}
        for stat in resp.findall(f"{DAV}propstat"):
            prop = stat.find(f"{DAV}prop")
            if prop is None:
                continue
            node["is_dir"] = node["is_dir"] or prop.find(f"{DAV}resourcetype/{DAV}collection") is not None
            for tag, key in (("getcontentlength", "size"), ("getlastmodified", "modified"),
                             ("getetag", "etag"), ("displayname", "name")):
                el = prop.find(f"{DAV}{tag}")
                if el is None or not el.text:
                    continue
                node[key] = int(el.text) if key == "size" else el.text
        node["name"] = node["name"] or href.rstrip("/").rsplit("/", 1)[-1]
        result.append(node)
    return result


class WebDavClient:
    def __init__(self, endpoint: str, user: str, password: str, root: str = "/", **httpx_kw):
        self.endpoint = str(endpoint).rstrip("/")
        self.root_segments = _split(root)
        self._base = httpx.URL(self.endpoint)
        if self._base.scheme not in ("http", "https") or not self._base.host:
            raise ValueError("WebDAV 地址必须是完整的 HTTP(S) 地址")
        if self._base.userinfo or self._base.query or self._base.fragment:
            raise ValueError("WebDAV 地址不能包含凭据、查询参数或片段；请使用独立账号字段")
        if httpx_kw.get("verify") is False:
            raise ValueError("WebDAV 不允许禁用 TLS 证书校验")
        auth = (user, password) if (user or password) else None
        self.cli = httpx.Client(
            base_url=self.endpoint, auth=auth, timeout=httpx.Timeout(connect=10.0, read=120.0, write=120.0, pool=10.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10), follow_redirects=True,
            headers={"Accept-Encoding": "identity"}, **httpx_kw,
        )

    # ---------- url ----------
    def _url(self, path: str) -> str:
        segments = self.root_segments + _split(path)
        encoded = "/".join(quote(s, safe="") for s in segments).encode("ascii")
        raw_path = self._base.raw_path.rstrip(b"/") + b"/" + encoded
        return str(self._base.copy_with(raw_path=raw_path))

    def _abs(self, path: str) -> str:
        return self._url(path)

    # ---------- 基础请求 ----------
    def _request(self, method: str, url: str, **kw) -> httpx.Response:
        return self.cli.request(method, url, **kw)

    @staticmethod
    def _raise_for(method: str, url: str, resp: httpx.Response, allow: tuple[int, ...]) -> httpx.Response:
        if resp.status_code not in allow:
            raise build_error(method, url, resp)
        return resp

    def _send(self, method: str, url: str, **kw) -> httpx.Response:
        """幂等动词统一入口:传输层异常与 5xx 走指数退避重试(≤3)。

        覆盖 `PROPFIND / GET / PUT / MKCOL / MOVE / DELETE` —— 它们全部幂等
        (RFC 9110 §9.2.2),重放无副作用。**读路径也必须走这里**:网盘型 WebDAV 反代
        可能返回半截 body(`RemoteProtocolError`,RFC 9112 §6.3 违规),那是可重试的
        传输层故障,不是终态。

        注意:这里只兜住**瞬时**故障。夸克驱动那次截断是**确定性**的(重试 4 次、静置
        15s 仍必现),根因是压缩协商 —— 由 `Accept-Encoding: identity` 在客户端层面消除,
        不能指望重试。

        4xx 不重试,直接返回给 `_raise_for` 判定;最后一次尝试不再退避。
        """
        for attempt in range(MAX_RETRIES):
            try:
                resp = self._request(method, url, **kw)
            except RETRY_EXCEPTIONS:
                time.sleep(_backoff(attempt))
                continue
            if resp.status_code < 500:
                return resp
            time.sleep(_backoff(attempt))
        return self._request(method, url, **kw)

    # ---------- 读 ----------
    def propfind(self, path: str, depth: int = 1) -> list[dict]:
        return self._propfind(self._url(path), depth)

    def _propfind(self, url: str, depth: int) -> list[dict]:
        resp = self._send("PROPFIND", url, content=PROPFIND_BODY,
                          headers={"Depth": str(depth), "Content-Type": "application/xml; charset=utf-8"})
        if resp.status_code == 404:
            raise WebDavNotFoundError(f"PROPFIND {unquote(url)} -> 404", 404)
        self._raise_for("PROPFIND", url, resp, (207,))
        return parse_multistatus(resp.text)

    def exists(self, path: str) -> bool:
        return self._exists_url(self._url(path))

    def _exists_url(self, url: str) -> bool:
        try:
            self._propfind(url, 0)
        except WebDavNotFoundError:
            return False
        return True

    def get_bytes(self, remote: str) -> bytes:
        return self._get_response(remote).content

    def get_bytes_with_etag(self, remote: str) -> tuple[bytes, str | None]:
        response = self._get_response(remote)
        return response.content, response.headers.get("ETag")

    def get_etag(self, remote: str) -> str | None:
        """PROPFIND 取 `DAV:getetag`。

        GET 响应头常见弱 ETag(`W/"..."`,如 Apache mod_dav / InfiniCLOUD 实测),
        而 `If-Match` 只接受强校验(RFC 7232 §3.1),此时该属性是强 ETag 的可靠来源。
        """
        nodes = self.propfind(remote, depth=0)
        return nodes[0]["etag"] if nodes else None

    def _get_response(self, remote: str) -> httpx.Response:
        url = self._url(remote)
        resp = self._send("GET", url)
        if resp.status_code == 404:
            raise WebDavNotFoundError(f"GET {unquote(url)} -> 404", 404)
        return self._raise_for("GET", url, resp, (200,))

    # ---------- 写 ----------
    def mkdir_p(self, path: str) -> None:
        segments = _split(path)
        if not segments:
            return
        current = []
        for seg in segments:
            current.append(seg)
            url = self._url("/".join(current))
            if self._exists_url(url):
                continue
            resp = self._send("MKCOL", url)
            if resp.status_code in (201, 405):  # 405:集合已存在 ⇒ 成功(RFC 4918 §9.3)
                continue
            if resp.status_code == 409:  # 父级缺失的竞态:确认已存在则继续,否则抛出
                if self._exists_url(url):
                    continue
            raise build_error("MKCOL", url, resp)

    def put_bytes(
        self, remote: str, data: bytes, content_type: str = "application/json; charset=utf-8", *, if_none_match: bool = False
    ) -> None:
        url = self._url(remote)
        headers = {"Content-Type": content_type, "Content-Length": str(len(data))}
        if if_none_match:
            headers["If-None-Match"] = "*"
        # 条件创建不重放：丢失响应后的 412 无法区分首次创建成功与名称冲突。
        send = self._request if if_none_match else self._send
        resp = send("PUT", url, content=data, headers=headers)
        self._raise_for("PUT", url, resp, (200, 201, 204))

    def put_file(self, local: Path, remote: str, on_progress: t.Callable[[int, int], None] | None = None) -> None:
        """流式上传。`on_progress(sent, total)` 逐 64KiB 分片回调;重试时重新 open 文件。"""
        local = Path(local)
        total = local.stat().st_size
        url = self._url(remote)
        for attempt in range(MAX_RETRIES + 1):
            try:
                with open(local, "rb") as fp:  # 每次重试重新 open:句柄不跨尝试复用
                    resp = self._request("PUT", url, content=self._iter_chunks(fp, total, on_progress),
                                         headers={"Content-Length": str(total)})
            except RETRY_EXCEPTIONS:
                if attempt == MAX_RETRIES:
                    raise
                time.sleep(_backoff(attempt))
                continue
            if resp.status_code < 500 or attempt == MAX_RETRIES:
                self._raise_for("PUT", url, resp, (200, 201, 204))
                return
            time.sleep(_backoff(attempt))

    @staticmethod
    def _iter_chunks(fp, total: int, on_progress):
        sent = 0
        for chunk in iter(lambda: fp.read(CHUNK_SIZE), b""):
            sent += len(chunk)
            if on_progress:
                on_progress(sent, total)
            yield chunk

    def move(self, src: str, dst: str, overwrite: bool = True) -> None:
        url = self._url(src)
        resp = self._send("MOVE", url, headers={"Destination": self._abs(dst), "Overwrite": "T" if overwrite else "F"})
        self._raise_for("MOVE", url, resp, (200, 201, 204))

    def delete(self, remote: str, missing_ok: bool = False, *, if_match: str | None = None) -> None:
        url = self._url(remote)
        if if_match is None:
            resp = self._send("DELETE", url)
        else:
            # 探测的条件删除不重放；不确定结果由探测 owner 显式报告。
            resp = self._request("DELETE", url, headers={"If-Match": if_match})
        if missing_ok and resp.status_code == 404:
            return
        self._raise_for("DELETE", url, resp, (200, 202, 204))

    # ---------- 生命周期 ----------
    def close(self):
        self.cli.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
