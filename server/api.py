from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any, Iterable, Literal

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from server.errors import ServerRuntimeError
from server.runtime import runtime
from server.subscription import (
    add_broadcaster_book,
    add_subscriber_follow,
    load_subscription_config,
    publish_subscription_share_card,
    remove_broadcaster_book,
    remove_subscriber_follow,
    save_subscription_config,
    switch_subscription_mode,
    update_broadcaster_book,
    update_subscriber_follow,
)
from server.surfaces import ServerSurface, mount_server_surfaces, server_surface_lifespan
from utils import conf, exc_p, temp_p
from utils.config.rule import CgsRuleMgr
from utils.server_control import is_authorized_header
from utils.subscription import DEFAULT_CUSTOMNAME, MODE_BROADCASTER, MODE_SUBSCRIBER, SubscriptionStore


class SearchRequest(BaseModel):
    site: int = Field(ge=0)
    keyword: str = Field(min_length=1)
    page: int = Field(default=1, ge=1)


class EpisodeSelectRequest(BaseModel):
    mode: Literal["latest", "first", "all"] = Field(
        default="first", description="Episode selection mode for manga books: 'first', 'latest', or 'all'."
    )
    num: int = Field(default=1, ge=1, description="Number of episodes for 'first' or 'latest'; clamped to available episodes.")


class BookEpisodesRequest(BaseModel):
    session_id: str = Field(min_length=1)
    book_key: str = Field(min_length=1)


class EpisodeSelectionRequest(BaseModel):
    book_key: str = Field(min_length=1)
    episode_keys: list[str] = Field(min_length=1)


class SubmitBooksRequest(BaseModel):
    session_id: str = Field(min_length=1)
    book_keys: list[str] = Field(default_factory=list)
    episode_selections: list[EpisodeSelectionRequest] = Field(default_factory=list)
    episode_select: EpisodeSelectRequest | None = None


class RepairMissingPagesRequest(BaseModel):
    job_id: str | None = None


class CgsConfigRequest(BaseModel):
    downloaded_handle: str = Field(min_length=1)
    proxies: list[str] | str | None = None
    sv_path: str = Field(min_length=1)


class SubscriptionConfigRequest(BaseModel):
    customname: str = DEFAULT_CUSTOMNAME
    mode: Literal["broadcaster", "subscriber"] = MODE_BROADCASTER
    broadcaster: dict[str, Any] = Field(default_factory=dict)
    subscriber: dict[str, Any] = Field(default_factory=dict)


class SubscriptionModeRequest(BaseModel):
    customname: str = DEFAULT_CUSTOMNAME
    mode: Literal["broadcaster", "subscriber"]


class SubscriptionBookRequest(BaseModel):
    customname: str = DEFAULT_CUSTOMNAME
    site: str = Field(min_length=1)
    url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    enabled: bool = True


class SubscriptionBookPatchRequest(BaseModel):
    site: str | None = None
    url: str | None = None
    title: str | None = None
    enabled: bool | None = None


class SubscriptionFollowRequest(BaseModel):
    customname: str = DEFAULT_CUSTOMNAME
    bid: str = Field(min_length=1)
    alias: str = ""


class SubscriptionFollowPatchRequest(BaseModel):
    bid: str | None = None
    alias: str | None = None


def create_app(surfaces: Iterable[ServerSurface] = (), *, auth_token: str | None = None) -> FastAPI:
    mounted_surfaces = tuple(surfaces)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with server_surface_lifespan(mounted_surfaces):
            yield

    app = FastAPI(title="ComicGUISpider Server", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    cover_dir = temp_p.joinpath("cover")
    cover_dir.mkdir(exist_ok=True)
    app.mount("/cover", StaticFiles(directory=str(cover_dir)), name="cover")
    mount_server_surfaces(app, mounted_surfaces)

    @app.exception_handler(HTTPException)
    async def cgs_http_exception_handler(request: Request, exc: HTTPException):
        if exc.status_code >= 500:
            _record_http_exception(request, exc)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)

    @app.middleware("http")
    async def require_surface_auth(request: Request, call_next):
        def _is_cover_request(path: str) -> bool:
            normalized = "/" + path.strip("/")
            return normalized == "/cover" or normalized.startswith("/cover/")
        def _is_surface_request(path: str, surfaces: tuple[ServerSurface, ...]) -> bool:
            normalized = "/" + path.strip("/")
            for surface in surfaces:
                mount_path = "/" + surface.mount_path.strip("/")
                if normalized == mount_path or normalized.startswith(f"{mount_path}/"):
                    return True
            return False
        started = time.perf_counter()
        if auth_token and (_is_surface_request(request.url.path, mounted_surfaces) or _is_cover_request(request.url.path)):
            authorization = request.headers.get("authorization")
            if not is_authorized_header(authorization, auth_token):
                response = JSONResponse(status_code=401, content={"detail": {"code": "invalid_token", "message": "invalid CGS Server token"}})
                _record_request_diagnostic(request, started, response.status_code)
                return response
        try:
            response = await call_next(request)
        except Exception as exc:
            _record_request_diagnostic(request, started, 500, error=exc)
            _record_unhandled_exception(request, exc)
            raise
        _record_request_diagnostic(request, started, response.status_code)
        return response

    def require_auth(authorization: str | None):
        if auth_token and not is_authorized_header(authorization, auth_token):
            raise HTTPException(401, {"code": "invalid_token", "message": "invalid CGS Server token"})

    @app.get("/health")
    async def health(authorization: str | None = Header(default=None)):
        payload = runtime.health()
        payload["authenticated"] = bool(auth_token)
        payload["authorized"] = bool(auth_token and is_authorized_header(authorization, auth_token))
        return payload

    @app.get("/sites")
    async def sites(authorization: str | None = Header(default=None)):
        require_auth(authorization)
        return {"sites": runtime.list_supported_sites()}

    @app.get("/conf")
    async def get_conf(authorization: str | None = Header(default=None)):
        require_auth(authorization)
        return _conf_response()

    @app.post("/conf")
    async def update_conf(req: CgsConfigRequest, authorization: str | None = Header(default=None)):
        require_auth(authorization)
        next_conf = _normalize_conf_request(req)
        previous_sv_path = Path(getattr(conf, "sv_path", "") or "")
        previous_downloaded_handle = str(getattr(conf, "downloaded_handle", "") or "")
        conf.update(**next_conf)
        if previous_sv_path != next_conf["sv_path"] or previous_downloaded_handle != next_conf["downloaded_handle"]:
            runtime.reset_spider_runtime()
        return _conf_response()

    @app.get("/subscription/config")
    async def get_subscription_config(
        customname: str = Query(default=DEFAULT_CUSTOMNAME),
        authorization: str | None = Header(default=None),
    ):
        require_auth(authorization)
        try:
            return load_subscription_config(SubscriptionStore(customname))
        except (TypeError, ValueError) as exc:
            _raise_subscription_error(exc)

    @app.put("/subscription/config")
    async def put_subscription_config(req: SubscriptionConfigRequest, authorization: str | None = Header(default=None)):
        require_auth(authorization)
        try:
            return save_subscription_config(SubscriptionStore(req.customname), req.model_dump())
        except (TypeError, ValueError) as exc:
            _raise_subscription_error(exc)

    @app.post("/subscription/mode")
    async def post_subscription_mode(req: SubscriptionModeRequest, authorization: str | None = Header(default=None)):
        require_auth(authorization)
        try:
            return switch_subscription_mode(SubscriptionStore(req.customname), req.mode)
        except (TypeError, ValueError) as exc:
            _raise_subscription_error(exc)

    @app.post("/subscription/broadcaster/books")
    async def post_subscription_broadcaster_book(
        req: SubscriptionBookRequest,
        authorization: str | None = Header(default=None),
    ):
        require_auth(authorization)
        try:
            return add_broadcaster_book(SubscriptionStore(req.customname), req.model_dump())
        except (TypeError, ValueError) as exc:
            _raise_subscription_error(exc)

    @app.patch("/subscription/broadcaster/books/{index}")
    async def patch_subscription_broadcaster_book(
        index: int,
        req: SubscriptionBookPatchRequest,
        customname: str = Query(default=DEFAULT_CUSTOMNAME),
        authorization: str | None = Header(default=None),
    ):
        require_auth(authorization)
        try:
            return update_broadcaster_book(SubscriptionStore(customname), index, req.model_dump(exclude_none=True))
        except IndexError as exc:
            _raise_subscription_error(exc)
        except (TypeError, ValueError) as exc:
            _raise_subscription_error(exc)

    @app.delete("/subscription/broadcaster/books/{index}")
    async def delete_subscription_broadcaster_book(
        index: int,
        customname: str = Query(default=DEFAULT_CUSTOMNAME),
        authorization: str | None = Header(default=None),
    ):
        require_auth(authorization)
        try:
            return remove_broadcaster_book(SubscriptionStore(customname), index)
        except IndexError as exc:
            _raise_subscription_error(exc)
        except (TypeError, ValueError) as exc:
            _raise_subscription_error(exc)

    @app.post("/subscription/broadcaster/share-card")
    async def post_subscription_share_card(
        customname: str = Query(default=DEFAULT_CUSTOMNAME),
        authorization: str | None = Header(default=None),
    ):
        require_auth(authorization)
        try:
            return await publish_subscription_share_card(SubscriptionStore(customname))
        except (TypeError, ValueError, RuntimeError) as exc:
            _raise_subscription_error(exc)

    @app.post("/subscription/subscriber/follows")
    async def post_subscription_subscriber_follow(
        req: SubscriptionFollowRequest,
        authorization: str | None = Header(default=None),
    ):
        require_auth(authorization)
        try:
            return add_subscriber_follow(SubscriptionStore(req.customname), req.model_dump())
        except (TypeError, ValueError) as exc:
            _raise_subscription_error(exc)

    @app.patch("/subscription/subscriber/follows/{index}")
    async def patch_subscription_subscriber_follow(
        index: int,
        req: SubscriptionFollowPatchRequest,
        customname: str = Query(default=DEFAULT_CUSTOMNAME),
        authorization: str | None = Header(default=None),
    ):
        require_auth(authorization)
        try:
            return update_subscriber_follow(SubscriptionStore(customname), index, req.model_dump(exclude_none=True))
        except IndexError as exc:
            _raise_subscription_error(exc)
        except (TypeError, ValueError) as exc:
            _raise_subscription_error(exc)

    @app.delete("/subscription/subscriber/follows/{index}")
    async def delete_subscription_subscriber_follow(
        index: int,
        customname: str = Query(default=DEFAULT_CUSTOMNAME),
        authorization: str | None = Header(default=None),
    ):
        require_auth(authorization)
        try:
            return remove_subscriber_follow(SubscriptionStore(customname), index)
        except IndexError as exc:
            _raise_subscription_error(exc)
        except (TypeError, ValueError) as exc:
            _raise_subscription_error(exc)

    @app.post("/search")
    async def search(req: SearchRequest, authorization: str | None = Header(default=None)):
        require_auth(authorization)
        try:
            return await runtime.search(req.site, req.keyword, req.page)
        except ServerRuntimeError as exc:
            raise HTTPException(_error_status(exc.code), exc.to_dict()) from exc

    @app.post("/book-episodes")
    async def book_episodes(req: BookEpisodesRequest, authorization: str | None = Header(default=None)):
        require_auth(authorization)
        try:
            return await runtime.book_episodes(req.session_id, req.book_key)
        except ServerRuntimeError as exc:
            raise HTTPException(_error_status(exc.code), exc.to_dict()) from exc

    @app.post("/submit-books")
    async def submit_books(req: SubmitBooksRequest, authorization: str | None = Header(default=None)):
        require_auth(authorization)
        try:
            episode_select = req.episode_select.model_dump() if req.episode_select is not None else None
            episode_selections = [selection.model_dump() for selection in req.episode_selections]
            return runtime.submit(req.session_id, req.book_keys, episode_select=episode_select, episode_selections=episode_selections)
        except ServerRuntimeError as exc:
            raise HTTPException(_error_status(exc.code), exc.to_dict()) from exc

    @app.post("/repair-missing-pages")
    async def repair_missing_pages(req: RepairMissingPagesRequest, authorization: str | None = Header(default=None)):
        require_auth(authorization)
        try:
            return runtime.repair_missing_pages(req.job_id)
        except ServerRuntimeError as exc:
            raise HTTPException(_error_status(exc.code), exc.to_dict()) from exc

    @app.get("/status")
    async def status(authorization: str | None = Header(default=None)):
        require_auth(authorization)
        return runtime.status()

    @app.get("/events")
    async def events(authorization: str | None = Header(default=None)):
        require_auth(authorization)
        return runtime.events()

    @app.get("/diagnostics")
    async def diagnostics(authorization: str | None = Header(default=None)):
        require_auth(authorization)
        return runtime.diagnostics()

    @app.post("/work/reset")
    async def reset_work_state(authorization: str | None = Header(default=None)):
        require_auth(authorization)
        try:
            return runtime.reset_work_state(origin="http")
        except ServerRuntimeError as exc:
            raise HTTPException(_error_status(exc.code), exc.to_dict()) from exc

    @app.post("/foreground/enter")
    async def foreground_enter(authorization: str | None = Header(default=None)):
        require_auth(authorization)
        try:
            return runtime.enter_foreground()
        except ServerRuntimeError as exc:
            raise HTTPException(_error_status(exc.code), exc.to_dict()) from exc

    @app.post("/foreground/leave")
    async def foreground_leave(authorization: str | None = Header(default=None)):
        require_auth(authorization)
        return runtime.leave_foreground()

    return app


def _error_status(code: str) -> int:
    normalized = code.lower().replace(" ", "_").replace("-", "_")
    if normalized in {"unsupported_site", "invalid_site", "invalid_page", "invalid_keyword", "foreground_active"}:
        return 400
    if normalized in {
        "missing_session",
        "invalid_session",
        "session_not_found",
        "expired_session",
        "empty_result",
        "missing_job",
        "invalid_job",
    }:
        return 404
    if normalized in {
        "invalid_book_key",
        "book_key_not_found",
        "unsupported_book",
        "invalid_episode_select",
        "invalid_episode_selection",
        "invalid_episode_key",
        "chapters_required",
        "chapters_not_supported",
        "episodes_not_loaded",
        "invalid_payload",
        "no_repair_records",
        "no_missing_pages",
    }:
        return 422
    if normalized == "job_running":
        return 409
    if normalized == "queue_full":
        return 429
    if normalized in {"search_failed", "episodes_fetch_failed", "pages_fetch_failed", "download_submit_failed"}:
        return 502
    return 400


def _raise_subscription_error(exc: Exception) -> None:
    message = str(exc)
    if isinstance(exc, IndexError):
        raise HTTPException(404, {"code": "subscription_not_found", "message": message}) from exc
    if isinstance(exc, RuntimeError):
        raise HTTPException(502, {"code": "subscription_publish_failed", "message": message}) from exc
    raise HTTPException(422, {"code": "invalid_subscription", "message": message}) from exc


def _record_request_diagnostic(request: Request, started: float, status_code: int, *, error: Exception | None = None) -> None:
    if not _should_record_request(request.url.path):
        return
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "method": request.method.upper(),
        "path": request.url.path,
        "status_code": int(status_code),
        "duration_ms": max(0, int(round((time.perf_counter() - started) * 1000))),
        "client": request.client.host if request.client is not None else None,
    }
    if error is not None:
        entry["error_type"] = type(error).__name__
        entry["message"] = str(error)
    runtime.record_request_diagnostic(entry)


def _record_http_exception(request: Request, exc: HTTPException) -> None:
    code = None
    message = str(exc.detail)
    if isinstance(exc.detail, dict):
        code = exc.detail.get("code")
        message = str(exc.detail.get("message") or exc.detail)
    summary = f"HTTP {exc.status_code} {request.method.upper()} {request.url.path}"
    if code:
        summary = f"{summary} {code}"
    runtime.record_server_error(
        summary, message,
        source="http", code=code, method=request.method.upper(), path=request.url.path, status_code=exc.status_code, exc=exc,
    )


def _record_unhandled_exception(request: Request, exc: Exception) -> None:
    runtime.record_server_error(
        f"Unhandled HTTP exception {request.method.upper()} {request.url.path}", str(exc),
        source="http", method=request.method.upper(), path=request.url.path, status_code=500, exc=exc,
    )


def _should_record_request(path: str) -> bool:
    return path != "/diagnostics" and not path.startswith("/cover/")


def _conf_response() -> dict:
    return {
        "downloaded_handle": str(getattr(conf, "downloaded_handle", "-") or "-"),
        "downloaded_handle_options": ["-", ".cbz"],
        "proxies": _normalize_proxies(getattr(conf, "proxies", None)),
        "sv_path": str(getattr(conf, "sv_path", "") or ""),
    }


def _normalize_conf_request(req: CgsConfigRequest) -> dict:
    downloaded_handle = str(req.downloaded_handle or "").strip()
    if downloaded_handle not in {"-", ".cbz"}:
        raise HTTPException(400, {"code": "invalid_downloaded_handle", "message": "downloaded_handle must be '-' or '.cbz'"})
    sv_path = _normalize_sv_path(req.sv_path, downloaded_handle)
    return {
        "downloaded_handle": downloaded_handle,
        "proxies": _normalize_proxies(req.proxies),
        "sv_path": str(sv_path),
    }


def _normalize_proxies(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = value.replace(" ", "").split(",")
    else:
        raw_items = [str(item).replace(" ", "") for item in value]
    return [item for item in raw_items if item]


def _normalize_sv_path(value: str, downloaded_handle: str) -> Path:
    def _is_relative_to(path: Path, parent: Path) -> bool:
        try:
            path.relative_to(parent)
        except ValueError:
            return False
        return True
    raw = str(value or "").strip()
    if not raw:
        raise HTTPException(400, {"code": "invalid_sv_path", "message": "sv_path is required"})
    sv_path = Path(raw).expanduser()
    if bool(sv_path.drive and len(sv_path.parts) == 1):
        raise HTTPException(400, {"code": "invalid_sv_path", "message": "sv_path cannot be a drive root"})
    resolved = sv_path.resolve(strict=False)
    cgs_root = Path(exc_p).resolve(strict=False)
    if _is_relative_to(resolved, cgs_root):
        raise HTTPException(400, {"code": "invalid_sv_path", "message": "sv_path cannot be inside CGS project"})
    is_valid, message = CgsRuleMgr.validate(resolved, downloaded_handle)
    if not is_valid:
        raise HTTPException(400, {"code": "invalid_cgs_rule", "message": message})
    try:
        resolved.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(400, {"code": "invalid_sv_path", "message": f"sv_path cannot be created: {exc}"}) from exc
    return resolved


app = create_app()
