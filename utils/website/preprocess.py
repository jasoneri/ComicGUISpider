from __future__ import annotations

import asyncio
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
    from .site_runtime import GuiSiteRuntime


async def run_site_preprocess(
    site_key: int,
    *,
    gui_site_runtime: "GuiSiteRuntime | None" = None,
    conf_state=conf,
    data_client: httpx.AsyncClient | None = None,
    progress_callback=None,
) -> PreprocessResult:
    owns_data_client = data_client is None
    resolved_data_client = data_client
    try:
        if site_key == Spider.MANGA_COPY:
            return await _preprocess_manga_copy(_require_gui_site_runtime(site_key, gui_site_runtime), conf_state=conf_state)
        if site_key == Spider.JM:
            return _preprocess_jm_like(_require_gui_site_runtime(site_key, gui_site_runtime))
        if site_key == Spider.WNACG:
            return _preprocess_wnacg(_require_gui_site_runtime(site_key, gui_site_runtime), conf_state=conf_state)
        if site_key == Spider.EHENTAI:
            return await _preprocess_ehentai(_require_gui_site_runtime(site_key, gui_site_runtime), conf_state=conf_state)
        if site_key == Spider.HITOMI:
            resolved_data_client = _ensure_data_client(resolved_data_client)
            return await _preprocess_hitomi(_require_gui_site_runtime(site_key, gui_site_runtime), conf_state=conf_state,
                data_client=resolved_data_client, progress_callback=progress_callback)
        if site_key == Spider.NHENTAI:
            resolved_data_client = _ensure_data_client(resolved_data_client)
            return await _preprocess_nhentai(_require_gui_site_runtime(site_key, gui_site_runtime),
                data_client=resolved_data_client, progress_callback=progress_callback)
        if site_key == 7:
            resolved_data_client = _ensure_data_client(resolved_data_client)
            return await _preprocess_script(data_client=resolved_data_client, progress_callback=progress_callback)
        if gui_site_runtime is not None:
            return await _preprocess_test_index(_require_gui_site_runtime(site_key, gui_site_runtime))
        return PreprocessResult()
    finally:
        if owns_data_client and resolved_data_client is not None:
            await resolved_data_client.aclose()


def _require_gui_site_runtime(site_key: int, gui_site_runtime: "GuiSiteRuntime | None") -> "GuiSiteRuntime":
    if gui_site_runtime is None:
        raise ValueError(f"site {site_key!r} preprocess requires gui_site_runtime")
    return gui_site_runtime


def _ensure_data_client(data_client: httpx.AsyncClient | None) -> httpx.AsyncClient:
    if data_client is not None:
        return data_client
    return httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(retries=2))


def _message(level: str, text: str, *, channel: str = "text", **kwargs) -> dict[str, t.Any]:
    return {"level": level, "text": text, "channel": channel, **kwargs}


def _action(action_type: str, **kwargs) -> dict[str, t.Any]:
    return {"type": action_type, **kwargs}


def _domain_cache_hit(gui_site_runtime: "GuiSiteRuntime") -> bool:
    return bool(gui_site_runtime.peek_cached_domain())


async def _preprocess_manga_copy(gui_site_runtime: "GuiSiteRuntime", *, conf_state=conf) -> PreprocessResult:
    runtime = gui_site_runtime.create_thread_site_runtime()
    reqer = runtime.reqer
    try:
        reqer.get_aes_key()
        cache_hit = reqer.aes_cache_hit()
    finally:
        await runtime.aclose()
    message = (
        "<br>➖ 缓存处于有效期内，跳过测试"
        if cache_hit else "<br>✅ 拷贝预处理完成"
    )
    return PreprocessResult(ready=True, runtime_ready=True, messages=(_message("success", message),), state_flags={"cache_hit": cache_hit})


def _preprocess_jm_like(gui_site_runtime: "GuiSiteRuntime") -> PreprocessResult:
    cache_hit = _domain_cache_hit(gui_site_runtime)
    try:
        domain = gui_site_runtime.get_domain()
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        return PreprocessResult(ready=False, block_search=True, messages=(_message("error", "<br>❌ 域名获取/测试失效，按内置浏览器引导操作"),),
            actions=(_action("open_publish_flow"),), state_flags={"cache_hit": cache_hit, "domain_ready": False, "error": str(exc)})
    message = ("<br>➖ 缓存处于有效期内，跳过测试" if cache_hit else "<br>✅ 已设置有效域名")
    return PreprocessResult(ready=True, domain=domain, runtime_ready=True, messages=(_message("success", message),),
        state_flags={"cache_hit": cache_hit, "domain_ready": True})


def _preprocess_wnacg(gui_site_runtime: "GuiSiteRuntime", *, conf_state=conf) -> PreprocessResult:
    if conf_state.proxies:
        domain = gui_site_runtime.peek_cached_domain() or gui_site_runtime.provider_cls.domain
        return PreprocessResult(ready=True, domain=domain, runtime_ready=True, messages=(_message("info", "🔔 已设置代理，跳过域名缓存处理"),),
            state_flags={"proxy_configured": True, "domain_ready": True})
    return _preprocess_jm_like(gui_site_runtime)


async def _preprocess_ehentai(gui_site_runtime: "GuiSiteRuntime", *, conf_state=conf) -> PreprocessResult:
    cookies_ready = bool(conf_state.cookies.get("ehentai"))
    if not cookies_ready:
        return PreprocessResult(ready=False, block_search=True,
            messages=(_message("error", res.EHentai.COOKIES_NOT_SET, channel="infobar"),),
            state_flags={"cookies_ready": False, "access_ready": False})

    runtime = gui_site_runtime.create_thread_site_runtime()
    access_ready = bool(runtime.reqer.test_index())
    provider_index = gui_site_runtime.provider_cls.index
    provider_domain = gui_site_runtime.provider_cls.domain
    if not access_ready:
        await runtime.aclose()
        return PreprocessResult(ready=False, block_search=True,
            messages=(_message("error", res.EHentai.ACCESS_FAIL, channel="custom", url=provider_index, url_name=gui_site_runtime.name),),
            state_flags={"cookies_ready": True, "access_ready": False})

    return PreprocessResult(ready=True, domain=provider_domain, runtime_ready=True,
        messages=(_message("success", "<br>✅ exhentai access pass"),), actions=(_action("attach_ehentai_runtime", runtime=runtime),),
        state_flags={"cookies_ready": True, "access_ready": True})

async def _preprocess_hitomi(
    gui_site_runtime: "GuiSiteRuntime",
    *,
    conf_state=conf,
    data_client: httpx.AsyncClient,
    progress_callback=None,
) -> PreprocessResult:
    runtime = gui_site_runtime.create_thread_site_runtime()
    try:
        access_ready = bool(runtime.reqer.test_index())
    finally:
        await runtime.aclose()
    provider_index = gui_site_runtime.provider_cls.index
    messages: list[dict[str, t.Any]] = []
    actions: list[dict[str, t.Any]] = []
    state_flags: dict[str, t.Any] = {"access_ready": access_ready}

    if access_ready:
        messages.append(_message("success", "<br>✅ hitomi access pass"))
    else:
        access_fail_message = _message("error", "", channel="custom", text_key="ACCESS_FAIL", url=provider_index,
            url_name=gui_site_runtime.name)
        messages.append(access_fail_message)

    hitomi_db_path = ori_path.joinpath("__temp/hitomi.db")
    data_ready = hitomi_db_path.exists()
    if not data_ready:
        if callable(progress_callback):
            progress_callback("hitomi db downloading...")
        messages.append(_message("warning", "⚠️ hitomi db not found, downloading..."))
        data_ready, download_errors = await _download_hitomi_db(hitomi_db_path, data_client)
        if download_errors:
            state_flags["hitomi_db_errors"] = tuple(download_errors)
        if data_ready:
            messages.append(_message("success", "<br>✅ hitomi db downloaded"))
        else:
            messages.append(_message("error", "<br>❌ hitomi-db download failed"))
    if data_ready:
        actions.append(_action("add_hitomi_tool"))
    state_flags["data_ready"] = data_ready

    return PreprocessResult(ready=access_ready, block_search=False, runtime_ready=access_ready, messages=tuple(messages),
        actions=tuple(actions), state_flags=state_flags)


async def _preprocess_nhentai(
    gui_site_runtime: "GuiSiteRuntime", *, data_client: httpx.AsyncClient, progress_callback=None
) -> PreprocessResult:
    runtime = gui_site_runtime.create_thread_site_runtime()
    try:
        access_ready = bool(runtime.reqer.test_index())
    finally:
        await runtime.aclose()
    provider_index = gui_site_runtime.provider_cls.index
    messages: list[dict[str, t.Any]] = []
    state_flags: dict[str, t.Any] = {"access_ready": access_ready}

    if access_ready:
        messages.append(_message("success", "<br>\u2705 nhentai access pass"))
    else:
        messages.append(_message("error", "", channel="custom", text_key="ACCESS_FAIL", url=provider_index, url_name=gui_site_runtime.name))

    db_path = ori_path.joinpath("__temp/nhentai.db")
    data_ready = db_path.exists()
    if not data_ready:
        if callable(progress_callback):
            progress_callback("nhentai db downloading...")
        messages.append(_message("warning", "\u26a0\ufe0f nhentai db not found, downloading..."))
        data_ready, download_errors = await _download_nhentai_db(db_path, data_client)
        if download_errors:
            state_flags["nhentai_db_errors"] = tuple(download_errors)
        if data_ready:
            messages.append(_message("success", "<br>\u2705 nhentai db downloaded"))
        else:
            messages.append(_message("error", "<br>\u274c nhentai-db download failed"))
    if data_ready:
        from .nhentai import NhentaiUtils

        try:
            state_flags["nhentai_tag_catalog_counts"] = NhentaiUtils.preload_tag_catalog(db_path)
        except Exception as exc:
            data_ready = False
            state_flags["nhentai_db_preload_error"] = str(exc)
            messages.append(_message("error", f"<br>\u274c nhentai tag catalog preload failed: {exc}"))
        else:
            messages.append(_message("success", "<br>\u2705 nhentai tag catalog preloaded"))
    state_flags["data_ready"] = data_ready

    return PreprocessResult(ready=access_ready and data_ready, block_search=False, runtime_ready=access_ready and data_ready,
        messages=tuple(messages), state_flags=state_flags)


async def _preprocess_test_index(gui_site_runtime: "GuiSiteRuntime") -> PreprocessResult:
    runtime = gui_site_runtime.create_thread_site_runtime()
    try:
        access_ready = bool(runtime.reqer.test_index())
    finally:
        await runtime.aclose()
    if not access_ready:
        return PreprocessResult(
            ready=False, block_search=True,
            messages=(_message("error", "", channel="custom", text_key="ACCESS_FAIL", 
                url=gui_site_runtime.provider_cls.index, url_name=gui_site_runtime.name),),
            state_flags={"access_ready": False},
        )
    return PreprocessResult(ready=True, runtime_ready=True,
        messages=(_message("success", f"<br>✅ {gui_site_runtime.name} 访问检测通过"),), state_flags={"access_ready": True})


async def _download_hitomi_db(db_path: Path, data_client: httpx.AsyncClient) -> tuple[bool, list[str]]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    urls = (
        "https://github.com/jasoneri/ComicGUISpider/releases/download/preset/hitomi.db",
        res.Vars.hitomiDb_tmp_url,
    )
    tmp_path = db_path.with_suffix(".db.tmp")
    errors: list[str] = []
    try:
        for url in urls:
            try:
                async with data_client.stream("GET", url, follow_redirects=True, timeout=30) as resp:
                    resp.raise_for_status()
                    with open(tmp_path, "wb") as file_obj:
                        async for chunk in resp.aiter_bytes(chunk_size=8192):
                            file_obj.write(chunk)
                os.replace(str(tmp_path), str(db_path))
                return True, errors
            except Exception as exc:
                tmp_path.unlink(missing_ok=True)
                errors.append(f"{url}: {exc}")
        return False, errors
    finally:
        tmp_path.unlink(missing_ok=True)


async def _download_nhentai_db(db_path: Path, data_client: httpx.AsyncClient) -> tuple[bool, list[str]]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    urls = ("https://github.com/jasoneri/ComicGUISpider/releases/download/preset/nhentai.db",)
    tmp_path = db_path.with_suffix(".db.tmp")
    errors: list[str] = []
    try:
        for url in urls:
            try:
                async with data_client.stream("GET", url, follow_redirects=True, timeout=30) as resp:
                    resp.raise_for_status()
                    with open(tmp_path, "wb") as file_obj:
                        async for chunk in resp.aiter_bytes(chunk_size=8192):
                            file_obj.write(chunk)
                os.replace(str(tmp_path), str(db_path))
                return True, errors
            except Exception as exc:
                tmp_path.unlink(missing_ok=True)
                errors.append(f"{url}: {exc}")
        return False, errors
    finally:
        tmp_path.unlink(missing_ok=True)


async def _preprocess_script(*, data_client: httpx.AsyncClient, progress_callback=None) -> PreprocessResult:
    script_res = res.GUI.Script
    services_ready = _check_script_services()
    dependencies_result = _check_script_dependencies()
    dependencies_ready = dependencies_result is True

    messages: list[dict[str, t.Any]] = []
    actions: list[dict[str, t.Any]] = []
    state_flags: dict[str, t.Any] = {
        "services_ready": services_ready,
        "dependencies_ready": dependencies_ready,
    }

    if services_ready:
        messages.append(_message("success", script_res.service_check_success))
    else:
        service_fail_message = _message("error", script_res.service_check_failed_content, channel="custom",
            title=script_res.service_check_failed_title, url=f"{CGS_DOC}/script", url_name=script_res.guide_name)
        messages.append(service_fail_message)

    if dependencies_ready:
        messages.append(_message("success", script_res.dependency_check_success))
    else:
        missing = tuple(dependencies_result)
        dependency_fail_message = _message("error", script_res.dependency_check_failed_content, channel="custom",
            title=script_res.dependency_check_failed_title, url=f"{CGS_DOC}/script", url_name=script_res.guide_name)
        messages.append(dependency_fail_message)
        actions.append(_action("launch_update_flow"))
        state_flags["missing_dependencies"] = missing

    if not services_ready or not dependencies_ready:
        return PreprocessResult(ready=False, block_search=True, messages=tuple(messages), actions=tuple(actions), state_flags=state_flags)

    data_ready, data_cache_hit = await _check_kemono_data(data_client, progress_callback=progress_callback)
    state_flags["data_ready"] = data_ready
    state_flags["data_cache_hit"] = data_cache_hit
    if data_ready:
        messages.append(_message("success", script_res.data_cache_check_success))
        actions.append(_action("open_scriptWin"))
    else:
        messages.append(_message("error", script_res.data_cache_check_failed))

    return PreprocessResult(ready=data_ready, block_search=True, runtime_ready=data_ready, messages=tuple(messages),
        actions=tuple(actions), state_flags=state_flags)


def _check_script_services() -> bool:
    running_processes = {proc.info["name"].lower() for proc in psutil.process_iter(["name"]) if proc.info["name"]}
    required = (
        any("motrix" in name for name in running_processes),
        any("redis-server" in name for name in running_processes),
    )
    return all(required)


def _check_script_dependencies() -> bool | list[str]:
    missing = []
    for package in ("redis", "pandas"):
        try:
            importlib.import_module(package)
        except ImportError:
            missing.append(package)
    return True if not missing else missing


async def _check_kemono_data(data_client: httpx.AsyncClient, *, progress_callback=None) -> tuple[bool, bool]:
    def emit_progress(message: str):
        if callable(progress_callback):
            progress_callback(message)

    cache = Cache("kemono_data.pkl")
    await asyncio.to_thread(cache.run, lambda: None, 240)
    if cache.flag == "validate":
        return True, True

    emit_progress("正在更新缓存数据...")
    from utils.script.image.kemono import Api, KemonoAuthor, headers

    async with data_client.stream("GET", Api.creators_txt, headers=headers, follow_redirects=True, timeout=60) as resp:
        resp.raise_for_status()
        content = b"".join([chunk async for chunk in resp.aiter_bytes()])

    json_data = json.loads(content.decode("utf-8"))
    author_dict = {}
    for item in json_data:
        author = KemonoAuthor(id=item["id"], name=item["name"], service=item["service"], updated=item["updated"],
            favorited=item["favorited"])
        author_dict[author.id] = author
    await asyncio.to_thread(cache.run, lambda: author_dict, 240, True)
    return True, False
