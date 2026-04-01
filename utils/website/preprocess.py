from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import typing as t

import httpx
import psutil

from assets import res
from utils import conf, ori_path
from variables import CGS_DOC, Spider

from .contracts import PreprocessResult
from .core import Cache

if t.TYPE_CHECKING:
    from .gateway import ProviderSiteGateway


def run_site_preprocess(
    site_key: int,
    *,
    gateway: "ProviderSiteGateway | None" = None,
    conf_state=conf,
    data_client: httpx.Client | None = None,
    progress_callback=None,
) -> PreprocessResult:
    if site_key == Spider.MANGA_COPY:
        return _preprocess_manga_copy(_require_gateway(site_key, gateway))
    if site_key == Spider.JM:
        return _preprocess_jm_like(_require_gateway(site_key, gateway))
    if site_key == Spider.WNACG:
        return _preprocess_wnacg(_require_gateway(site_key, gateway), conf_state=conf_state)
    if site_key == Spider.EHENTAI:
        return _preprocess_ehentai(_require_gateway(site_key, gateway), conf_state=conf_state)
    if site_key == Spider.HITOMI:
        return _preprocess_hitomi(
            _require_gateway(site_key, gateway),
            conf_state=conf_state,
            data_client=_ensure_data_client(data_client),
            progress_callback=progress_callback,
        )
    if site_key == 7:
        return _preprocess_kemono(
            data_client=_ensure_data_client(data_client),
            progress_callback=progress_callback,
        )
    if gateway is not None and gateway.supports_test_index:
        return _preprocess_test_index(gateway, conf_state=conf_state)
    return PreprocessResult()


def _require_gateway(site_key: int, gateway: "ProviderSiteGateway | None") -> "ProviderSiteGateway":
    if gateway is None:
        raise ValueError(f"site {site_key!r} preprocess requires a gateway")
    return gateway


def _ensure_data_client(data_client: httpx.Client | None) -> httpx.Client:
    if data_client is not None:
        return data_client
    return httpx.Client(transport=httpx.HTTPTransport(retries=2))


def _message(level: str, text: str, *, channel: str = "text", **kwargs) -> dict[str, t.Any]:
    return {"level": level, "text": text, "channel": channel, **kwargs}


def _action(action_type: str, **kwargs) -> dict[str, t.Any]:
    return {"type": action_type, **kwargs}


def _cache_hit(gateway: "ProviderSiteGateway") -> bool:
    cache = getattr(gateway, "cachef", None)
    if cache is None:
        reqer_cls = getattr(gateway, "reqer_cls", None)
        cache = getattr(reqer_cls, "cachef", None)
    return bool(cache and cache.flag != "new")


def _runtime_reqer(runtime):
    return getattr(runtime, "reqer", runtime)


def _preprocess_manga_copy(gateway: "ProviderSiteGateway") -> PreprocessResult:
    gateway.reqer_cls.get_aes_key()
    cache_hit = _cache_hit(gateway)
    message = (
        "<br>➖ 缓存处于有效期内，跳过测试"
        if cache_hit
        else "<br>✅ 拷贝预处理完成"
    )
    return PreprocessResult(
        ready=True,
        runtime_ready=True,
        messages=(_message("success", message),),
        state_flags={"cache_hit": cache_hit},
    )


def _preprocess_jm_like(gateway: "ProviderSiteGateway") -> PreprocessResult:
    cache_hit = _cache_hit(gateway)
    try:
        domain = gateway.get_domain()
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        return PreprocessResult(
            ready=False,
            block_search=True,
            messages=(
                _message("error", "<br>❌ 域名获取/测试失效，按内置浏览器引导操作"),
            ),
            actions=(_action("open_publish_flow"),),
            state_flags={"cache_hit": cache_hit, "domain_ready": False, "error": str(exc)},
        )

    message = (
        "<br>➖ 缓存处于有效期内，跳过测试"
        if cache_hit
        else "<br>✅ 已设置有效域名"
    )
    return PreprocessResult(
        ready=True,
        domain=domain,
        runtime_ready=True,
        messages=(_message("success", message),),
        state_flags={"cache_hit": cache_hit, "domain_ready": True},
    )


def _preprocess_wnacg(gateway: "ProviderSiteGateway", *, conf_state=conf) -> PreprocessResult:
    if conf_state.proxies:
        return PreprocessResult(
            ready=True,
            domain=getattr(gateway, "domain", None),
            runtime_ready=True,
            messages=(
                _message("info", "🔔 已设置代理，跳过域名缓存处理"),
            ),
            state_flags={"proxy_configured": True, "domain_ready": True},
        )
    return _preprocess_jm_like(gateway)


def _preprocess_ehentai(gateway: "ProviderSiteGateway", *, conf_state=conf) -> PreprocessResult:
    runtime = gateway.create_runtime(conf_state)
    cookies_ready = bool(conf_state.cookies.get("ehentai"))
    if not cookies_ready:
        return PreprocessResult(
            ready=False,
            block_search=True,
            messages=(
                _message("error", res.EHentai.COOKIES_NOT_SET, channel="infobar"),
            ),
            state_flags={"cookies_ready": False, "access_ready": False},
        )

    access_ready = bool(_runtime_reqer(runtime).test_index())
    if not access_ready:
        return PreprocessResult(
            ready=False,
            block_search=True,
            messages=(
                _message(
                    "error",
                    res.EHentai.ACCESS_FAIL,
                    channel="custom",
                    url=gateway.index,
                    url_name=gateway.name,
                ),
            ),
            state_flags={"cookies_ready": True, "access_ready": False},
        )

    return PreprocessResult(
        ready=True,
        domain=getattr(gateway, "domain", None),
        runtime_ready=True,
        messages=(
            _message("success", "<br>✅ exhentai 访问检测通过"),
        ),
        actions=(
            _action("attach_ehentai_runtime", runtime=runtime),
        ),
        state_flags={"cookies_ready": True, "access_ready": True},
    )


def _preprocess_test_index(gateway: "ProviderSiteGateway", *, conf_state=conf) -> PreprocessResult:
    runtime = gateway.create_runtime(conf_state)
    access_ready = bool(_runtime_reqer(runtime).test_index())
    if not access_ready:
        return PreprocessResult(
            ready=False,
            block_search=True,
            messages=(
                _message(
                    "error",
                    "",
                    channel="custom",
                    text_key="ACCESS_FAIL",
                    url=gateway.index,
                    url_name=gateway.name,
                ),
            ),
            state_flags={"access_ready": False},
        )

    return PreprocessResult(
        ready=True,
        runtime_ready=True,
        messages=(
            _message("success", f"<br>✅ {gateway.name} 访问检测通过"),
        ),
        state_flags={"access_ready": True},
    )


def _preprocess_hitomi(
    gateway: "ProviderSiteGateway",
    *,
    conf_state=conf,
    data_client: httpx.Client,
    progress_callback=None,
) -> PreprocessResult:
    runtime = gateway.create_runtime(conf_state)
    access_ready = bool(_runtime_reqer(runtime).test_index())
    messages: list[dict[str, t.Any]] = []
    actions: list[dict[str, t.Any]] = []
    state_flags: dict[str, t.Any] = {"access_ready": access_ready}

    if access_ready:
        messages.append(_message("success", "<br>✅ hitomi 访问检测通过"))
    else:
        messages.append(
            _message(
                "error",
                "",
                channel="custom",
                text_key="ACCESS_FAIL",
                url=gateway.index,
                url_name=gateway.name,
            )
        )

    hitomi_db_path = ori_path.joinpath("assets/hitomi.db")
    data_ready = hitomi_db_path.exists()
    if not data_ready:
        if callable(progress_callback):
            progress_callback("hitomi db downloading...")
        messages.append(_message("warning", "⚠️ hitomi db not found, downloading..."))
        data_ready, download_errors = _download_hitomi_db(hitomi_db_path, data_client)
        if download_errors:
            state_flags["hitomi_db_errors"] = tuple(download_errors)
        if data_ready:
            messages.append(_message("success", "<br>✅ hitomi db downloaded"))
        else:
            messages.append(_message("error", "<br>❌ hitomi-db download failed"))
    if data_ready:
        actions.append(_action("add_hitomi_tool"))
    state_flags["data_ready"] = data_ready

    return PreprocessResult(
        ready=access_ready,
        block_search=False,
        runtime_ready=access_ready,
        messages=tuple(messages),
        actions=tuple(actions),
        state_flags=state_flags,
    )


def _download_hitomi_db(db_path: Path, data_client: httpx.Client) -> tuple[bool, list[str]]:
    urls = (
        "https://github.com/jasoneri/ComicGUISpider/releases/download/preset/hitomi.db",
        res.Vars.hitomiDb_tmp_url,
    )
    tmp_path = db_path.with_suffix(".db.tmp")
    errors: list[str] = []
    try:
        for url in urls:
            try:
                with data_client.stream("GET", url, follow_redirects=True, timeout=30) as resp:
                    resp.raise_for_status()
                    with open(tmp_path, "wb") as file_obj:
                        for chunk in resp.iter_bytes(chunk_size=8192):
                            file_obj.write(chunk)
                os.replace(str(tmp_path), str(db_path))
                return True, errors
            except Exception as exc:
                tmp_path.unlink(missing_ok=True)
                errors.append(f"{url}: {exc}")
        return False, errors
    finally:
        tmp_path.unlink(missing_ok=True)


def _preprocess_kemono(
    *,
    data_client: httpx.Client,
    progress_callback=None,
) -> PreprocessResult:
    services_ready = _check_kemono_services()
    dependencies_result = _check_kemono_dependencies()
    dependencies_ready = dependencies_result is True

    messages: list[dict[str, t.Any]] = []
    actions: list[dict[str, t.Any]] = []
    state_flags: dict[str, t.Any] = {
        "services_ready": services_ready,
        "dependencies_ready": dependencies_ready,
    }

    if services_ready:
        messages.append(_message("success", "✅ 后台服务检测"))
    else:
        messages.append(
            _message(
                "error",
                "Redis 或 Motrix 服务未运行，<br>点击指南查看`前置须知`，安装并运行相关服务",
                channel="custom",
                title="服务检测失败",
                url=f"{CGS_DOC}/feat/script",
                url_name="脚本集指南",
            )
        )

    if dependencies_ready:
        messages.append(_message("success", "✅ 额外依赖检测"))
    else:
        missing = tuple(dependencies_result)
        messages.append(
            _message(
                "error",
                "点击按钮，查看`前置须知`的'uv安装脚本集依赖命令'部分（彻底关闭CGS后执行）",
                channel="custom",
                title="依赖安装失败",
                url=f"{CGS_DOC}/feat/script",
                url_name="脚本集指南",
            )
        )
        actions.append(_action("launch_update_flow"))
        state_flags["missing_dependencies"] = missing

    if not services_ready or not dependencies_ready:
        return PreprocessResult(
            ready=False,
            block_search=True,
            messages=tuple(messages),
            actions=tuple(actions),
            state_flags=state_flags,
        )

    data_ready, data_cache_hit = _check_kemono_data(data_client, progress_callback=progress_callback)
    state_flags["data_ready"] = data_ready
    state_flags["data_cache_hit"] = data_cache_hit
    if data_ready:
        messages.append(_message("success", "✅ 数据缓存检测"))
        actions.append(_action("open_script_window"))
    else:
        messages.append(_message("error", "❌ 数据缓存检测"))

    return PreprocessResult(
        ready=data_ready,
        block_search=True,
        runtime_ready=data_ready,
        messages=tuple(messages),
        actions=tuple(actions),
        state_flags=state_flags,
    )


def _check_kemono_services() -> bool:
    running_processes = {proc.info["name"].lower() for proc in psutil.process_iter(["name"]) if proc.info["name"]}
    required = (
        any("motrix" in name for name in running_processes),
        any("redis-server" in name for name in running_processes),
    )
    return all(required)


def _check_kemono_dependencies() -> bool | list[str]:
    missing = []
    for package in ("redis", "pandas"):
        try:
            importlib.import_module(package)
        except ImportError:
            missing.append(package)
    return True if not missing else missing


def _check_kemono_data(data_client: httpx.Client, *, progress_callback=None) -> tuple[bool, bool]:
    def emit_progress(message: str):
        if callable(progress_callback):
            progress_callback(message)

    def download_kemono_data():
        emit_progress("正在更新缓存数据...")
        from utils.script.image.kemono import Api, KemonoAuthor, headers

        with data_client.stream(
            "GET",
            Api.creators_txt,
            headers=headers,
            follow_redirects=True,
            timeout=60,
        ) as resp:
            resp.raise_for_status()
            content = b"".join(resp.iter_bytes())

        json_data = json.loads(content.decode("utf-8"))
        author_dict = {}
        for item in json_data:
            author = KemonoAuthor(
                id=item["id"],
                name=item["name"],
                service=item["service"],
                updated=item["updated"],
                favorited=item["favorited"],
            )
            author_dict[author.id] = author
        return author_dict

    cache = Cache("kemono_data.pkl")
    cache.run(download_kemono_data, 240, write_in=True)
    return True, cache.flag != "new"
