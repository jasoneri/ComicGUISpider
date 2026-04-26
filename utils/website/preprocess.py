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


class SitePreprocessRuntime(t.Protocol):
    reqer: t.Any


class SitePreprocessRuntimeOwner(t.Protocol):
    name: str
    index: t.Any
    domain: str | None

    def get_domain(self): ...
    def create_runtime(self, conf_state=conf) -> SitePreprocessRuntime: ...


def run_site_preprocess(
    site_key: int,
    *,
    runtime_owner: "SitePreprocessRuntimeOwner | None" = None,
    conf_state=conf,
    data_client: httpx.Client | None = None,
    progress_callback=None,
) -> PreprocessResult:
    if site_key == Spider.MANGA_COPY:
        return _preprocess_manga_copy(_require_runtime_owner(site_key, runtime_owner), conf_state=conf_state)
    if site_key == Spider.JM:
        return _preprocess_jm_like(_require_runtime_owner(site_key, runtime_owner))
    if site_key == Spider.WNACG:
        return _preprocess_wnacg(_require_runtime_owner(site_key, runtime_owner), conf_state=conf_state)
    if site_key == Spider.EHENTAI:
        return _preprocess_ehentai(_require_runtime_owner(site_key, runtime_owner), conf_state=conf_state)
    if site_key == Spider.HITOMI:
        return _preprocess_hitomi(
            _require_runtime_owner(site_key, runtime_owner),
            conf_state=conf_state,
            data_client=_ensure_data_client(data_client),
            progress_callback=progress_callback,
        )
    if site_key == 7:
        return _preprocess_script(data_client=_ensure_data_client(data_client), progress_callback=progress_callback)
    if runtime_owner is not None:
        raise NotImplementedError(
            f"TODO(site-runtime-owner): preprocess site {site_key!r} must define an explicit runtime-owner flow "
            "instead of using legacy supports_test_index probing."
        )
    return PreprocessResult()


def _require_runtime_owner(site_key: int, runtime_owner: "SitePreprocessRuntimeOwner | None") -> "SitePreprocessRuntimeOwner":
    if runtime_owner is None:
        raise ValueError(f"site {site_key!r} preprocess requires a runtime owner")
    return runtime_owner


def _ensure_data_client(data_client: httpx.Client | None) -> httpx.Client:
    if data_client is not None:
        return data_client
    return httpx.Client(transport=httpx.HTTPTransport(retries=2))


def _message(level: str, text: str, *, channel: str = "text", **kwargs) -> dict[str, t.Any]:
    return {"level": level, "text": text, "channel": channel, **kwargs}


def _action(action_type: str, **kwargs) -> dict[str, t.Any]:
    return {"type": action_type, **kwargs}


def _preprocess_manga_copy(runtime_owner: "SitePreprocessRuntimeOwner", *, conf_state=conf) -> PreprocessResult:
    runtime = runtime_owner.create_runtime(conf_state)
    reqer = runtime.reqer
    try:
        reqer.get_aes_key()
        cache_hit = reqer.aes_cache_hit()
    finally:
        reqer.cli.close()
    message = (
        "<br>➖ 缓存处于有效期内，跳过测试"
        if cache_hit
        else "<br>✅ 拷贝预处理完成"
    )
    return PreprocessResult(ready=True, runtime_ready=True, messages=(_message("success", message),), state_flags={"cache_hit": cache_hit})


def _preprocess_jm_like(runtime_owner: "SitePreprocessRuntimeOwner") -> PreprocessResult:
    try:
        domain = runtime_owner.get_domain()
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        return PreprocessResult(
            ready=False,
            block_search=True,
            messages=(_message("error", "<br>❌ 域名获取/测试失效，按内置浏览器引导操作"),),
            actions=(_action("open_publish_flow"),),
            state_flags={"domain_ready": False, "error": str(exc)},
        )

    return PreprocessResult(
        ready=True,
        domain=domain,
        runtime_ready=True,
        messages=(_message("success", "<br>✅ 已设置有效域名"),),
        state_flags={"domain_ready": True},
    )


def _preprocess_wnacg(runtime_owner: "SitePreprocessRuntimeOwner", *, conf_state=conf) -> PreprocessResult:
    if conf_state.proxies:
        return PreprocessResult(
            ready=True,
            domain=runtime_owner.domain,
            runtime_ready=True,
            messages=(_message("info", "🔔 已设置代理，跳过域名缓存处理"),),
            state_flags={"proxy_configured": True, "domain_ready": True},
        )
    return _preprocess_jm_like(runtime_owner)


def _preprocess_ehentai(runtime_owner: "SitePreprocessRuntimeOwner", *, conf_state=conf) -> PreprocessResult:
    runtime = runtime_owner.create_runtime(conf_state)
    cookies_ready = bool(conf_state.cookies.get("ehentai"))
    if not cookies_ready:
        return PreprocessResult(
            ready=False,
            block_search=True,
            messages=(_message("error", res.EHentai.COOKIES_NOT_SET, channel="infobar"),),
            state_flags={"cookies_ready": False, "access_ready": False},
        )

    access_ready = bool(runtime.reqer.test_index())
    if not access_ready:
        return PreprocessResult(
            ready=False,
            block_search=True,
            messages=(_message("error", res.EHentai.ACCESS_FAIL, channel="custom", url=runtime_owner.index, url_name=runtime_owner.name),),
            state_flags={"cookies_ready": True, "access_ready": False},
        )

    return PreprocessResult(
        ready=True,
        domain=runtime_owner.domain,
        runtime_ready=True,
        messages=(_message("success", "<br>✅ exhentai access pass"),),
        actions=(_action("attach_ehentai_runtime", runtime=runtime),),
        state_flags={"cookies_ready": True, "access_ready": True},
    )

def _preprocess_hitomi(
    runtime_owner: "SitePreprocessRuntimeOwner",
    *,
    conf_state=conf,
    data_client: httpx.Client,
    progress_callback=None,
) -> PreprocessResult:
    runtime = runtime_owner.create_runtime(conf_state)
    access_ready = bool(runtime.reqer.test_index())
    messages: list[dict[str, t.Any]] = []
    actions: list[dict[str, t.Any]] = []
    state_flags: dict[str, t.Any] = {"access_ready": access_ready}

    if access_ready:
        messages.append(_message("success", "<br>✅ hitomi access pass"))
    else:
        access_fail_message = _message(
            "error",
            "",
            channel="custom",
            text_key="ACCESS_FAIL",
            url=runtime_owner.index,
            url_name=runtime_owner.name,
        )
        messages.append(access_fail_message)

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


def _preprocess_script(*, data_client: httpx.Client, progress_callback=None) -> PreprocessResult:
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
        service_fail_message = _message(
            "error",
            script_res.service_check_failed_content,
            channel="custom",
            title=script_res.service_check_failed_title,
            url=f"{CGS_DOC}/script",
            url_name=script_res.guide_name,
        )
        messages.append(service_fail_message)

    if dependencies_ready:
        messages.append(_message("success", script_res.dependency_check_success))
    else:
        missing = tuple(dependencies_result)
        dependency_fail_message = _message(
            "error",
            script_res.dependency_check_failed_content,
            channel="custom",
            title=script_res.dependency_check_failed_title,
            url=f"{CGS_DOC}/script",
            url_name=script_res.guide_name,
        )
        messages.append(dependency_fail_message)
        actions.append(_action("launch_update_flow"))
        state_flags["missing_dependencies"] = missing

    if not services_ready or not dependencies_ready:
        return PreprocessResult(ready=False, block_search=True, messages=tuple(messages), actions=tuple(actions), state_flags=state_flags)

    data_ready, data_cache_hit = _check_kemono_data(data_client, progress_callback=progress_callback)
    state_flags["data_ready"] = data_ready
    state_flags["data_cache_hit"] = data_cache_hit
    if data_ready:
        messages.append(_message("success", script_res.data_cache_check_success))
        actions.append(_action("open_script_window"))
    else:
        messages.append(_message("error", script_res.data_cache_check_failed))

    return PreprocessResult(
        ready=data_ready,
        block_search=True,
        runtime_ready=data_ready,
        messages=tuple(messages),
        actions=tuple(actions),
        state_flags=state_flags,
    )


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


def _check_kemono_data(data_client: httpx.Client, *, progress_callback=None) -> tuple[bool, bool]:
    def emit_progress(message: str):
        if callable(progress_callback):
            progress_callback(message)

    def download_kemono_data():
        emit_progress("正在更新缓存数据...")
        from utils.script.image.kemono import Api, KemonoAuthor, headers

        with data_client.stream("GET", Api.creators_txt, headers=headers, follow_redirects=True, timeout=60) as resp:
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
