from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import os
from pathlib import Path
import socket
import typing as t

import httpx

from assets import res
from utils import conf, ori_path
from utils.network.doh import build_http_transport
from variables import CGS_DOC, Spider

from .contracts import PreprocessResult
from .core import Cache

if t.TYPE_CHECKING:
    from .site_runtime import GuiSiteRuntime


DB_CACHE_TTL_HOURS = 480
SCRIPT_SERVICE_WARNING_DELAY_MS = 7000
SCRIPT_SERVICE_PROBE_TIMEOUT_S = 0.15
# Redis 约定见 conf_sample_script.yml；aria2 由 CGS 托管引擎动态端口
SCRIPT_REDIS_DEFAULT_HOST = "127.0.0.1"
SCRIPT_REDIS_DEFAULT_PORT = 6379
KEMONO_ASSET_URL = "https://github.com/jasoneri/ComicGUISpider/releases/download/preset/kemono.db"
NHENTAI_ASSET_URL = "https://github.com/jasoneri/ComicGUISpider/releases/download/preset/nhentai.db"
HITOMI_ASSET_URL = "https://github.com/jasoneri/ComicGUISpider/releases/download/preset/hitomi.db"


async def run_site_preprocess(
    gui_site_runtime: "GuiSiteRuntime", *, conf_state=conf, data_client: httpx.AsyncClient | None = None, progress_callback=None
) -> PreprocessResult:
    owns_data_client = data_client is None
    resolved_data_client = data_client
    site_key = gui_site_runtime.site_index
    try:
        if site_key == Spider.MANGA_COPY:
            return await _preprocess_manga_copy(gui_site_runtime)
        if site_key == Spider.JM:
            return _preprocess_jm_like(gui_site_runtime)
        if site_key == Spider.WNACG:
            return _preprocess_wnacg(gui_site_runtime, conf_state=conf_state)
        if site_key == Spider.EHENTAI:
            return await _preprocess_ehentai(gui_site_runtime, conf_state=conf_state)
        if site_key == Spider.HITOMI:
            resolved_data_client = _ensure_data_client(resolved_data_client, gui_site_runtime=gui_site_runtime, conf_state=conf_state)
            return await _preprocess_hitomi(gui_site_runtime, data_client=resolved_data_client, progress_callback=progress_callback)
        if site_key == Spider.NHENTAI:
            resolved_data_client = _ensure_data_client(resolved_data_client, gui_site_runtime=gui_site_runtime, conf_state=conf_state)
            return await _preprocess_nhentai(gui_site_runtime, data_client=resolved_data_client, progress_callback=progress_callback)
        return await _preprocess_test_index(gui_site_runtime)
    finally:
        if owns_data_client and resolved_data_client is not None:
            await resolved_data_client.aclose()


async def run_script_preprocess(
    *, conf_state=conf, data_client: httpx.AsyncClient | None = None, progress_callback=None
) -> PreprocessResult:
    owns_data_client = data_client is None
    resolved_data_client = data_client

    def ensure_data_client() -> httpx.AsyncClient:
        nonlocal resolved_data_client
        if resolved_data_client is None:
            resolved_data_client = _ensure_data_client(None, conf_state=conf_state)
        return resolved_data_client

    try:
        return await _preprocess_script(
            ensure_data_client=ensure_data_client,
            progress_callback=progress_callback,
        )
    finally:
        if owns_data_client and resolved_data_client is not None:
            await resolved_data_client.aclose()


def _ensure_data_client(
    data_client: httpx.AsyncClient | None,
    *,
    gui_site_runtime: "GuiSiteRuntime | None" = None,
    conf_state=conf,
) -> httpx.AsyncClient:
    if data_client is not None:
        return data_client
    if gui_site_runtime is not None:
        transport_config = gui_site_runtime.runtime_context.transport
        proxies = list(transport_config.proxies)
        doh_url = transport_config.doh_url
    else:
        proxies = list(getattr(conf_state, "proxies", None) or ())
        doh_url = str(getattr(conf_state, "doh_url", "") or "")
    transport, trust_env = build_http_transport("proxy", proxies, doh_url=doh_url, is_async=True, retries=2)
    return httpx.AsyncClient(transport=transport, trust_env=trust_env)


def _message(level: str, text: str, *, channel: str = "text", **kwargs) -> dict[str, t.Any]:
    return {"level": level, "text": text, "channel": channel, **kwargs}


def _action(action_type: str, **kwargs) -> dict[str, t.Any]:
    return {"type": action_type, **kwargs}


@dataclass(frozen=True, slots=True)
class ReleaseAssetResult:
    ready: bool
    cache_hit: bool
    cache_expired: bool
    db_path: Path
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScriptServiceStatus:
    aria2_ready: bool
    redis_server_running: bool

    @property
    def motrix_running(self) -> bool:
        """Backward-compatible alias: download engine readiness (cgs-aria2)."""
        return self.aria2_ready

    @classmethod
    def from_process_names(cls, process_names: t.Iterable[str]) -> "ScriptServiceStatus":
        normalized_process_names = {process_name.lower() for process_name in process_names}
        return cls(
            aria2_ready=any(
                name in process_name
                for process_name in normalized_process_names
                for name in ("aria2c", "motrix")
            ),
            redis_server_running=any("redis-server" in process_name for process_name in normalized_process_names),
        )

    @property
    def all_required_services_running(self) -> bool:
        # Soft gate only covers external Redis. aria2 is CGS-managed and must
        # already have been ensured (hard fail) before this status is built.
        return self.redis_server_running

    @property
    def missing_services(self) -> tuple[str, ...]:
        if self.redis_server_running:
            return ()
        return ("redis-server",)

    def to_payload(self) -> dict[str, bool]:
        return {
            "aria2_ready": self.aria2_ready,
            "motrix_running": self.motrix_running,
            "redis_server_running": self.redis_server_running,
            "all_required_services_running": self.all_required_services_running,
        }


@dataclass(frozen=True, slots=True)
class ScriptEntryState:
    service_status: ScriptServiceStatus
    kemono_data_ready: bool | None = None
    kemono_data_cache_hit: bool | None = None
    kemono_data_errors: tuple[str, ...] = ()

    @property
    def danbooru_visible(self) -> bool:
        return self.service_status.motrix_running

    @property
    def kemono_service_ready(self) -> bool:
        return self.service_status.motrix_running and self.service_status.redis_server_running

    @property
    def should_check_kemono_data(self) -> bool:
        return self.kemono_service_ready

    @property
    def kemono_visible(self) -> bool:
        return self.kemono_service_ready and self.kemono_data_ready is True

    @property
    def cbg_visible(self) -> bool:
        return True

    @property
    def jsoneri_palaces_probe_visible(self) -> bool:
        return True

    @property
    def settings_visible(self) -> bool:
        return True

    @property
    def hidden_entries(self) -> tuple[str, ...]:
        hidden_entries: list[str] = []
        if not self.danbooru_visible:
            hidden_entries.append("Danbooru")
        if not self.kemono_visible:
            hidden_entries.append("Kemono")
        return tuple(hidden_entries)

    def with_kemono_asset_result(self, kemono_asset: ReleaseAssetResult) -> "ScriptEntryState":
        return ScriptEntryState(
            service_status=self.service_status, kemono_data_ready=kemono_asset.ready,
            kemono_data_cache_hit=kemono_asset.cache_hit, kemono_data_errors=kemono_asset.errors,
        )

    def to_payload(self) -> dict[str, t.Any]:
        return {
            "services": self.service_status.to_payload(),
            "motrix_running": self.service_status.motrix_running,
            "redis_server_running": self.service_status.redis_server_running,
            "missing_services": self.service_status.missing_services,
            "kemono_data_ready": self.kemono_data_ready,
            "kemono_data_cache_hit": self.kemono_data_cache_hit,
            "kemono_data_errors": self.kemono_data_errors,
            "danbooru_visible": self.danbooru_visible,
            "kemono_visible": self.kemono_visible,
            "cbg_visible": self.cbg_visible,
            "jsoneri_palaces_probe_visible": self.jsoneri_palaces_probe_visible,
            "settings_visible": self.settings_visible,
            "hidden_entries": self.hidden_entries,
            "should_check_kemono_data": self.should_check_kemono_data,
        }


class ReleaseAssetCache:
    def __init__(
        self, *, name: str, db_path: Path, download_urls: tuple[str, ...], data_client: httpx.AsyncClient,
        progress_callback=None, label: str | None = None, timeout: int = 30, cache_ttl_hours: int = DB_CACHE_TTL_HOURS,
    ):
        self.name = name
        self.db_path = db_path
        self.download_urls = download_urls
        self.data_client = data_client
        self.progress_callback = progress_callback
        self.label = label or f"{name} db"
        self.timeout = timeout
        self.cache_ttl_hours = cache_ttl_hours
        self.cache = Cache(f"{name}.db")

    async def ensure(self) -> ReleaseAssetResult:
        cached_db_path = self.cache.run(lambda: None, self.cache_ttl_hours)
        if cached_db_path:
            return ReleaseAssetResult(True, True, False, t.cast(Path, cached_db_path))
        self._emit_legacy_download_start()
        ready, errors = await self._download()
        return ReleaseAssetResult(ready, False, self.cache.state == "expired", self.db_path, tuple(errors))

    def _emit_legacy_download_start(self) -> None:
        progress_start = getattr(self.progress_callback, "download_start", None)
        if callable(self.progress_callback) and not callable(progress_start):
            self.progress_callback(f"{self.label} dling...")

    async def _download(self) -> tuple[bool, list[str]]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.db_path.with_suffix(".db.tmp")
        errors: list[str] = []
        progress_reset = getattr(self.progress_callback, "download_reset", None)
        progress_start = getattr(self.progress_callback, "download_start", None)
        progress_advance = getattr(self.progress_callback, "download_advance", None)
        progress_finish = getattr(self.progress_callback, "download_finish", None)
        try:
            for url in self.download_urls:
                try:
                    if callable(progress_reset):
                        progress_reset(label=self.label)
                    async with self.data_client.stream("GET", url, follow_redirects=True, timeout=self.timeout) as resp:
                        resp.raise_for_status()
                        total_header = resp.headers.get("Content-Length", "").strip()
                        total_bytes = int(total_header) if total_header.isdigit() else None
                        if callable(progress_start):
                            progress_start(label=self.label, total_bytes=total_bytes)
                        with open(tmp_path, "wb") as file_obj:
                            async for chunk in resp.aiter_bytes(chunk_size=8192):
                                file_obj.write(chunk)
                                if callable(progress_advance):
                                    progress_advance(len(chunk), label=self.label, total_bytes=total_bytes)
                    os.replace(str(tmp_path), str(self.db_path))
                    if callable(progress_finish):
                        progress_finish(label=self.label)
                    return True, errors
                except Exception as exc:
                    tmp_path.unlink(missing_ok=True)
                    errors.append(f"{url}: {exc}")
            return False, errors
        finally:
            tmp_path.unlink(missing_ok=True)


class PreprocessRuntimeProbe:
    def __init__(self, gui_site_runtime: "GuiSiteRuntime"):
        self.gui_site_runtime = gui_site_runtime

    async def manga_copy_cache_hit(self) -> bool:
        runtime = self.gui_site_runtime.create_thread_site_runtime()
        try:
            reqer = runtime.reqer
            await reqer.ensure_preview_aes_key()
            return reqer.aes_cache_hit()
        finally:
            await runtime.aclose()

    async def access_ready(self) -> bool:
        runtime = self.gui_site_runtime.create_thread_site_runtime()
        try:
            test_index = getattr(runtime.reqer, "test_index", None)
            if not callable(test_index):
                raise RuntimeError(f"{self.gui_site_runtime.name} preprocess access probe requires reqer.test_index()")
            return bool(test_index())
        finally:
            await runtime.aclose()

    async def verified_runtime(self):
        runtime = self.gui_site_runtime.create_thread_site_runtime()
        try:
            test_index = getattr(runtime.reqer, "test_index", None)
            if not callable(test_index):
                raise RuntimeError(f"{self.gui_site_runtime.name} preprocess access probe requires reqer.test_index()")
            if test_index():
                return runtime
        except Exception:
            await runtime.aclose()
            raise
        await runtime.aclose()
        return None


def _domain_cache_hit(gui_site_runtime: "GuiSiteRuntime") -> bool:
    return bool(gui_site_runtime.peek_cached_domain())


async def _preprocess_manga_copy(gui_site_runtime: "GuiSiteRuntime") -> PreprocessResult:
    cache_hit = await PreprocessRuntimeProbe(gui_site_runtime).manga_copy_cache_hit()
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
        domain = gui_site_runtime.provider_cls.domain  # remark wnacg 代理下不能锁 国内域名 前置
        return PreprocessResult(ready=True, domain=domain, runtime_ready=True, messages=(_message("info", "🔔 已设置代理，跳过域名缓存处理"),),
            state_flags={"proxy_configured": True, "domain_ready": True})
    return _preprocess_jm_like(gui_site_runtime)


async def _preprocess_ehentai(gui_site_runtime: "GuiSiteRuntime", *, conf_state=conf) -> PreprocessResult:
    cookies_ready = bool(conf_state.cookies.get("ehentai"))
    if not cookies_ready:
        return PreprocessResult(ready=False, block_search=True,
            messages=(_message("error", res.EHentai.COOKIES_NOT_SET, channel="infobar"),),
            state_flags={"cookies_ready": False, "access_ready": False})

    verified_runtime = await PreprocessRuntimeProbe(gui_site_runtime).verified_runtime()
    provider_index = gui_site_runtime.provider_cls.index
    provider_domain = gui_site_runtime.provider_cls.domain
    if verified_runtime is None:
        return PreprocessResult(ready=False, block_search=True,
            messages=(_message("error", res.EHentai.ACCESS_FAIL, channel="custom", url=provider_index, url_name=gui_site_runtime.name),),
            state_flags={"cookies_ready": True, "access_ready": False})

    attach_runtime_action = _action("attach_ehentai_runtime", runtime=verified_runtime)
    return PreprocessResult(ready=True, domain=provider_domain, runtime_ready=True,
        messages=(_message("success", "<br>✅ exhentai access pass"),), actions=(attach_runtime_action,),
        state_flags={"cookies_ready": True, "access_ready": True})

async def _preprocess_hitomi(
    gui_site_runtime: "GuiSiteRuntime", *, data_client: httpx.AsyncClient, progress_callback=None,
) -> PreprocessResult:
    return await HitomiDatabasePreprocess(gui_site_runtime, data_client, progress_callback).run()


async def _preprocess_nhentai(
    gui_site_runtime: "GuiSiteRuntime", *, data_client: httpx.AsyncClient, progress_callback=None
) -> PreprocessResult:
    return await NhentaiDatabasePreprocess(gui_site_runtime, data_client, progress_callback).run()


async def _preprocess_test_index(gui_site_runtime: "GuiSiteRuntime") -> PreprocessResult:
    access_ready = await PreprocessRuntimeProbe(gui_site_runtime).access_ready()
    if not access_ready:
        return PreprocessResult(
            ready=False, block_search=True,
            messages=(_message("error", "", channel="custom", text_key="ACCESS_FAIL", 
                url=gui_site_runtime.provider_cls.index, url_name=gui_site_runtime.name),),
            state_flags={"access_ready": False},
        )
    return PreprocessResult(ready=True, runtime_ready=True,
        messages=(_message("success", f"<br>✅ {gui_site_runtime.name} 访问检测通过"),), state_flags={"access_ready": True})


class SiteDatabasePreprocess:
    CACHE_TTL_HOURS = DB_CACHE_TTL_HOURS

    name: str
    download_urls: tuple[str, ...]
    data_required = True
    data_ready_action: str | None = None

    def __init__(self, gui_site_runtime: "GuiSiteRuntime", data_client: httpx.AsyncClient, progress_callback=None):
        self.gui_site_runtime = gui_site_runtime
        self.runtime_probe = PreprocessRuntimeProbe(gui_site_runtime)
        self.asset_cache = ReleaseAssetCache(
            name=self.name, db_path=ori_path.joinpath(f"__temp/{self.name}.db"), download_urls=self.download_urls,
            data_client=data_client, progress_callback=progress_callback, timeout=30, cache_ttl_hours=self.CACHE_TTL_HOURS,
        )
        self.db_path = self.asset_cache.db_path
        self.messages: list[dict[str, t.Any]] = []
        self.actions: list[dict[str, t.Any]] = []
        self.state_flags: dict[str, t.Any] = {}

    async def run(self) -> PreprocessResult:
        access_ready = await self.runtime_probe.access_ready()
        self.state_flags["access_ready"] = access_ready
        if access_ready:
            self.messages.append(_message("success", f"<br>✅ {self.name} access pass"))
        else:
            self.messages.append(_message("error", "", channel="custom", text_key="ACCESS_FAIL",
                url=self.gui_site_runtime.provider_cls.index, url_name=self.gui_site_runtime.name))

        asset_result = await self.asset_cache.ensure()
        data_ready = asset_result.ready
        self.db_path = asset_result.db_path
        self.state_flags["cache_hit"] = asset_result.cache_hit
        self.state_flags["cache_expired"] = asset_result.cache_expired
        if asset_result.errors:
            self.state_flags[f"{self.name}_db_errors"] = asset_result.errors
        if self.state_flags["cache_hit"]:
            self.messages.append(_message("info", f"➖ {self.name} db 缓存有效，跳过下载"))
        elif data_ready:
            self.messages.append(_message("success", f"<br>✅ {self.name} db downloaded"))
        else:
            self.messages.append(_message("error", f"<br>❌ {self.name}-db download failed"))
        if data_ready:
            data_ready = await self.after_data_ready()
        if data_ready and self.data_ready_action is not None:
            self.actions.append(_action(self.data_ready_action))
        self.state_flags["data_ready"] = data_ready

        ready = access_ready and data_ready if self.data_required else access_ready
        return PreprocessResult(ready=ready, block_search=False, runtime_ready=ready, messages=tuple(self.messages),
            actions=tuple(self.actions), state_flags=self.state_flags)

    async def after_data_ready(self) -> bool:
        return True


class HitomiDatabasePreprocess(SiteDatabasePreprocess):
    name = "hitomi"
    download_urls = (HITOMI_ASSET_URL, res.Vars.hitomiDb_tmp_url,)
    data_required = False
    data_ready_action = "add_hitomi_tool"


class NhentaiDatabasePreprocess(SiteDatabasePreprocess):
    name = "nhentai"
    download_urls = (NHENTAI_ASSET_URL,)

    async def after_data_ready(self) -> bool:
        from .nhentai import NhentaiUtils

        try:
            self.state_flags["nhentai_tag_catalog_counts"] = NhentaiUtils.preload_tag_catalog(self.db_path)
        except Exception as exc:
            self.state_flags["nhentai_db_preload_error"] = str(exc)
            self.messages.append(_message("error", f"<br>❌ nhentai tag catalog preload failed: {exc}"))
            return False
        return True


class KemonoReleaseAsset(ReleaseAssetCache):
    def __init__(self, data_client: httpx.AsyncClient, progress_callback=None):
        super().__init__(
            name="kemono", db_path=ori_path.joinpath("__temp/kemono.db"), download_urls=(KEMONO_ASSET_URL,),
            data_client=data_client, progress_callback=progress_callback, label="kemono db", timeout=60,
        )


def _format_script_service_warning(script_entry_state: ScriptEntryState) -> str:
    script_res = res.GUI.Script
    missing_services = "、".join(script_entry_state.service_status.missing_services)
    hidden_entries = "、".join(script_entry_state.hidden_entries)
    return (
        f"{script_res.service_check_failed_content}"
        f"<br>缺少服务：{missing_services}"
        f"<br>受影响入口：{hidden_entries}"
        f"<br>{SCRIPT_SERVICE_WARNING_DELAY_MS // 1000} 秒后将打开可用入口。"
    )


def _format_kemono_data_warning() -> str:
    script_res = res.GUI.Script
    return f"{script_res.data_cache_check_failed}<br>⚠️ Kemono 入口已隐藏，其他脚本入口仍可使用。"


async def _preprocess_script(
    *,
    ensure_data_client: t.Callable[[], httpx.AsyncClient],
    progress_callback=None,
) -> PreprocessResult:
    script_res = res.GUI.Script
    service_status = _check_script_services()
    script_entry_state = ScriptEntryState(service_status=service_status)
    dependencies_result = _check_script_dependencies()
    dependencies_ready = dependencies_result is True

    messages: list[dict[str, t.Any]] = []
    open_delay_ms = 0
    state_flags: dict[str, t.Any] = {
        "services_ready": service_status.all_required_services_running,
        "service_status": service_status.to_payload(),
        "missing_services": service_status.missing_services,
        "dependencies_ready": dependencies_ready,
    }

    if service_status.all_required_services_running:
        messages.append(_message("success", script_res.service_check_success))
    else:
        open_delay_ms = SCRIPT_SERVICE_WARNING_DELAY_MS
        service_fail_message = _message(
            "warning", _format_script_service_warning(script_entry_state), channel="custom", title=script_res.service_check_failed_title,
            url=f"{CGS_DOC}/script", url_name=script_res.guide_name, duration=SCRIPT_SERVICE_WARNING_DELAY_MS,
        )
        messages.append(service_fail_message)

    if not dependencies_ready:
        missing = tuple(t.cast(list[str], dependencies_result))
        dependency_fail_message = _message(
            "warning", script_res.dependency_check_failed_content, channel="custom", title=script_res.dependency_check_failed_title,
            url=f"{CGS_DOC}/script", url_name=script_res.guide_name, duration=SCRIPT_SERVICE_WARNING_DELAY_MS,
        )
        messages.append(dependency_fail_message)
        state_flags["missing_dependencies"] = missing

    if script_entry_state.should_check_kemono_data:
        data_client = ensure_data_client()
        kemono_asset = await KemonoReleaseAsset(data_client, progress_callback).ensure()
        script_entry_state = script_entry_state.with_kemono_asset_result(kemono_asset)
        state_flags["data_ready"] = kemono_asset.ready
        state_flags["data_cache_hit"] = kemono_asset.cache_hit
        if kemono_asset.errors:
            state_flags["kemono_db_errors"] = kemono_asset.errors
        if kemono_asset.ready:
            messages.append(_message("success", script_res.data_cache_check_success))
        else:
            messages.append(_message("warning", _format_kemono_data_warning()))
    else:
        state_flags["kemono_data_check_skipped"] = True

    script_entry_state_payload = script_entry_state.to_payload()
    state_flags["script_entry_state"] = script_entry_state_payload
    state_flags["hidden_script_entries"] = script_entry_state.hidden_entries
    actions = (_action("open_scriptWin", script_entry_state=script_entry_state_payload, delay_ms=open_delay_ms),)

    return PreprocessResult(ready=True, block_search=False, runtime_ready=False, messages=tuple(messages), actions=actions, state_flags=state_flags)


def _probe_local_port(host: str, port: int, *, timeout_s: float = SCRIPT_SERVICE_PROBE_TIMEOUT_S) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def _check_script_services() -> ScriptServiceStatus:
    # aria2 is CGS-managed: ensure or raise (no soft "engine failed" product path).
    # Redis remains an external service → soft probe for Kemono entry only.
    from utils.script.aria2 import ensure_engine

    ensure_engine()
    return ScriptServiceStatus(
        aria2_ready=True,
        redis_server_running=_probe_local_port(SCRIPT_REDIS_DEFAULT_HOST, SCRIPT_REDIS_DEFAULT_PORT),
    )


def _check_script_dependencies() -> bool | list[str]:
    missing = [
        package
        for package in ("redis", "pandas")
        if importlib.util.find_spec(package) is None
    ]
    return True if not missing else missing
