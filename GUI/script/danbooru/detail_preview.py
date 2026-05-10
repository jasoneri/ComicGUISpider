import typing as t
from dataclasses import dataclass

from PySide6 import QtCore
from PySide6.QtGui import QPixmap

from utils.script.image.danbooru.http import DanbooruChallengeRequired
from utils.script.image.danbooru.models import DanbooruPost

from .core import capture_danbooru_request, execute_danbooru_task, fetch_pixmap
from .viewer import DanbooruImageViewer

if t.TYPE_CHECKING:
    from .interface import DanbooruInterface


@dataclass(frozen=True, slots=True)
class _DetailRequestSpec:
    task_prefix: str
    retry_prefix: str
    challenge_placeholder: str = ""
    discard_prefetch: bool = False


_PREFETCH_REQUEST = _DetailRequestSpec(task_prefix="danbooru-detail-prefetch", retry_prefix="detail-prefetch", discard_prefetch=True)
_PREVIEW_REQUEST = _DetailRequestSpec(task_prefix="danbooru-detail-preview", retry_prefix="detail-preview", challenge_placeholder="需要验证")
_SIZE_REQUEST = _DetailRequestSpec(task_prefix="danbooru-detail-size", retry_prefix="detail-size")


class _DetailVideoPreview:
    def __init__(self, controller: "DetailPreviewController"):
        self.controller = controller
        self.viewer = controller.viewer
        self.video_proxy = controller.video_proxy
        self._url_cache: dict[int, str] = {}
        self.video_proxy.challenge_detected.connect(self.handle_challenge)
        self.video_proxy.request_failed.connect(self.handle_error)
        self.video_proxy.cache_progress.connect(self.handle_cache_progress)
        self.video_proxy.cache_ready.connect(self.handle_cache_ready)

    def cached_url(self, post_id: int) -> t.Optional[str]:
        return self._url_cache.get(post_id)

    def apply(self, post_id: int, local_proxy_url: str):
        self._url_cache[post_id] = local_proxy_url
        self.viewer.set_video(post_id, local_proxy_url)
        progress = self.video_proxy.progress_for_post(post_id)
        if progress is not None:
            self.apply_progress(progress)

    def handle_challenge(self, post_id: int, challenge: DanbooruChallengeRequired):
        post = self.controller._post_for_id(post_id)
        if post is None or self.controller.current_tab_id is None:
            return
        if self.controller.matches(post_id=post_id):
            self.viewer.set_placeholder("需要验证")
        tab_id = self.controller.current_tab_id
        self.controller.interface.challenge_controller.submit(
            tab_id, challenge, retry_callback=lambda current_post_id=post_id: self.retry_playback(current_post_id),
            retry_key=f"detail-video-stream:{tab_id}:{post_id}",
        )

    def handle_error(self, post_id: int, error: str):
        post = self.controller._post_for_id(post_id)
        if post is None:
            return
        self.controller.gui.log.error(f"[Danbooru] detail video stream failed post_id={post_id}: {error}")
        if self.controller.matches(post_id=post_id):
            self.viewer.set_placeholder(self.controller._detail_preview_error_message(post, error))

    def retry_playback(self, post_id: int):
        local_proxy_url = self._url_cache.get(post_id)
        if local_proxy_url is None:
            post = self.controller._post_for_id(post_id)
            if post is None:
                raise ValueError(f"Danbooru video retry target not found: post_id={post_id}")
            local_proxy_url = self.video_proxy.register_post(post)
            self._url_cache[post_id] = local_proxy_url
        self.viewer.set_video(post_id, local_proxy_url)

    def handle_cache_progress(self, progress):
        self.apply_progress(progress)

    def handle_cache_ready(self, post_id: int):
        progress = self.video_proxy.progress_for_post(post_id)
        if progress is not None:
            self.apply_progress(progress)

    def apply_progress(self, progress):
        if not self.controller.matches(post_id=progress.post_id):
            return
        self.viewer.video_mgr.set_cache_progress(
            cached_bytes=progress.cached_bytes, total_bytes=progress.total_bytes, cached_ratio=progress.cached_ratio,
            active_segment_index=progress.active_segment_index, complete=progress.complete, play_bar=self.viewer.playBar,
        )


class DetailPreviewController(QtCore.QObject):
    def __init__(self, interface: "DanbooruInterface", viewer: DanbooruImageViewer):
        super().__init__(interface)
        self.interface = interface
        self.gui = interface.gui
        self.viewer = viewer
        self.video_proxy = interface.video_proxy
        self._tab_id: t.Optional[str] = None
        self._pixmap_cache: dict[int, QPixmap] = {}
        self._size_cache: dict[int, QtCore.QSize] = {}
        self._prefetching_post_ids: set[int] = set()
        self.video_preview = _DetailVideoPreview(self)

    @property
    def current_tab_id(self) -> t.Optional[str]:
        return self._tab_id

    def clear_context(self):
        self._tab_id = None

    def matches(self, *, post_id: t.Optional[int] = None, md5: t.Optional[str] = None) -> bool:
        viewer_post = self.viewer.post
        if viewer_post is None:
            return False
        if post_id is not None:
            return viewer_post.post_id == post_id
        if md5 is not None:
            return viewer_post.md5 == md5
        return False

    def open_viewer(self, tab_id: str, post: DanbooruPost):
        tab = self.interface.tabs.get(tab_id)
        card = tab.card_widgets.get(post.md5) if tab is not None else None
        already_downloaded = card.already_downloaded if card is not None else self.interface.sql_recorder.check_dupe(post.md5)
        self._tab_id = tab_id
        self._apply_cached_size(post)
        self.viewer.show_post(post, already_downloaded)
        self.sync_navigation()
        if post.is_video:
            cached_video = self.video_preview.cached_url(post.post_id)
            if cached_video is not None:
                return self.viewer.set_video(post.post_id, cached_video)
                
        cached_pixmap = self._pixmap_cache.get(post.post_id)
        if cached_pixmap is not None and not cached_pixmap.isNull():
            self.viewer.set_image(post.post_id, cached_pixmap)
            return self._preload_next(post)
        if post.is_supported and DanbooruImageViewer._post_size_hint(post) is None:
            self._probe_size(tab_id, post)
        self._load_preview(tab_id, post)

    def sync_navigation(self):
        posts = self._current_posts()
        index = self._current_post_index(posts)
        self.viewer.set_navigation_enabled(index > 0, 0 <= index < len(posts) - 1)

    def open_adjacent(self, step: int):
        posts = self._current_posts()
        index = self._current_post_index(posts)
        target_index = index + step
        if index < 0 or target_index < 0 or target_index >= len(posts):
            return
        assert self._tab_id is not None
        self.open_viewer(self._tab_id, posts[target_index])

    def _current_posts(self) -> list[DanbooruPost]:
        if not self._tab_id:
            return []
        state = self.interface.tab_states.get(self._tab_id)
        return list(state.result_list) if state is not None else []

    def _post_for_id(self, post_id: int) -> t.Optional[DanbooruPost]:
        viewer_post = self.viewer.post
        if viewer_post is not None and viewer_post.post_id == post_id:
            return viewer_post
        return next((post for post in self._current_posts() if post.post_id == post_id), None)

    def _current_post_index(self, posts: t.Sequence[DanbooruPost]) -> int:
        viewer_post = self.viewer.post
        if viewer_post is None:
            return -1
        return next((index for index, post in enumerate(posts) if post.md5 == viewer_post.md5), -1)

    def _preload_next(self, current_post: t.Optional[DanbooruPost] = None):
        if not self._tab_id:
            return
        posts = self._current_posts()
        if not posts:
            return
        anchor = current_post or self.viewer.post
        if anchor is None:
            return
        current_index = next((index for index, post in enumerate(posts) if post.md5 == anchor.md5), -1)
        target_index = current_index + 1
        if current_index < 0 or target_index >= len(posts):
            return
        self._prefetch(self._tab_id, posts[target_index])

    @staticmethod
    def _detail_preview_url(post: DanbooruPost) -> t.Optional[str]:
        return post.large_file_url or post.file_url or post.preview_file_url

    @staticmethod
    def _detail_preview_error_message(post: DanbooruPost, error: str) -> str:
        first_line = (error or "").splitlines()[0].strip()
        ext = DanbooruPost.normalize_file_ext(post.file_ext)
        if post.is_video:
            media_hint = ext.upper() if ext else "VIDEO"
            if first_line:
                return f"{media_hint} 预览失败：{first_line}"
            return f"{media_hint} 预览失败"
        if not post.is_supported:
            media_hint = ext.upper() if ext else "UNKNOWN"
            return f"{media_hint} 无法渲染预览，可下载原文件 / non-renderable preview"
        if not DetailPreviewController._detail_preview_url(post):
            return "当前作品没有可用预览 / non preview"
        if first_line == "invalid image data":
            media_hint = ext.upper() if ext else "未知格式"
            return f"返回内容不是可渲染的图片（{media_hint}）"
        if first_line:
            return f"fail/预览失败：{first_line}"
        return "fail/预览失败"

    def _apply_cached_size(self, post: DanbooruPost):
        cached_size = self._size_cache.get(post.post_id)
        if cached_size is None:
            return
        post.preview_width = cached_size.width()
        post.preview_height = cached_size.height()

    def _prefetch(self, tab_id: str, post: DanbooruPost):
        if not post.is_supported or post.post_id in self._pixmap_cache or \
            post.post_id in self._prefetching_post_ids or not self._detail_preview_url(post):
            return
        self._prefetching_post_ids.add(post.post_id)
        self._execute_request(_PREFETCH_REQUEST, tab_id, post)

    def _load_preview(self, tab_id: str, post: DanbooruPost):
        preview_url = self._detail_preview_url(post)
        if not preview_url:
            if self.matches(post_id=post.post_id):
                self.viewer.set_placeholder(self._detail_preview_error_message(post, "no preview url"))
            return
        if not post.is_supported and not post.is_video:
            if self.matches(post_id=post.post_id):
                self.viewer.set_placeholder(self._detail_preview_error_message(post, "non-renderable preview"))
            return
        self._execute_request(_PREVIEW_REQUEST, tab_id, post)

    def _probe_size(self, tab_id: str, post: DanbooruPost):
        if not post.is_supported or not self._detail_preview_url(post):
            return
        self._execute_request(_SIZE_REQUEST, tab_id, post)

    def _execute_request(self, spec: _DetailRequestSpec, tab_id: str, post: DanbooruPost):
        preview_url = self._detail_preview_url(post)
        if not preview_url:
            raise ValueError(f"Danbooru detail request missing preview url: post_id={post.post_id}")
        request_client = self.interface.request_client
        if spec is _SIZE_REQUEST:
            task = lambda url=preview_url: capture_danbooru_request(request_client.fetch_remote_image_size, url)
        elif post.is_video:
            task = lambda current_post=post: capture_danbooru_request(self.video_proxy.register_post, current_post)
        else:
            task = lambda url=preview_url: capture_danbooru_request(fetch_pixmap, request_client, url, max_width=0)
        execute_danbooru_task(
            self.interface.task_mgr, task,
            success_callback=lambda payload, current_spec=spec, current_tab_id=tab_id, current_post=post, current_url=preview_url: (
                self._handle_request_result(current_spec, current_tab_id, current_post, current_url, payload)
            ),
            error_callback=lambda error, current_spec=spec, current_post=post: self._handle_request_error(
                current_spec, current_post, error,
            ),
            task_id=f"{spec.task_prefix}-{tab_id}-{post.post_id}",
        )

    def _handle_request_result(self, spec: _DetailRequestSpec, tab_id: str, post: DanbooruPost, preview_url: str, payload):
        def _handle_challenge(challenge: DanbooruChallengeRequired):
            if spec.discard_prefetch:
                self._prefetching_post_ids.discard(post.post_id)
            if spec.challenge_placeholder and self.matches(post_id=post.post_id):
                self.viewer.set_placeholder(spec.challenge_placeholder)
            if spec is _PREFETCH_REQUEST:
                retry_callback = lambda current_tab_id=tab_id, current_post=post: self._prefetch(current_tab_id, current_post)
            elif spec is _PREVIEW_REQUEST:
                retry_callback = lambda current_tab_id=tab_id, current_post=post: self._load_preview(current_tab_id, current_post)
            else:
                retry_callback = lambda current_tab_id=tab_id, current_post=post: self._probe_size(current_tab_id, current_post)
            self.interface.challenge_controller.submit(
                tab_id, challenge, retry_callback, retry_key=f"{spec.retry_prefix}:{tab_id}:{post.post_id}",
            )
        if payload.challenge is not None:
            return _handle_challenge(payload.challenge)
        if spec is _SIZE_REQUEST:
            return self._apply_preview_size(post.post_id, payload.value)
        if post.is_video:
            return self.video_preview.apply(post.post_id, payload.value)
        self._apply_preview(post.post_id, payload.value, post if spec is _PREVIEW_REQUEST else None)
        if spec is _PREFETCH_REQUEST:
            self._prefetching_post_ids.discard(post.post_id)

    def _handle_request_error(self, spec: _DetailRequestSpec, post: DanbooruPost, error: str):
        if spec is _PREFETCH_REQUEST:
            self._prefetching_post_ids.discard(post.post_id)
            self.gui.log.warning(f"[Danbooru] detail prefetch failed post_id={post.post_id}: {error}")
            return
        if spec is _PREVIEW_REQUEST:
            self.gui.log.error(f"[Danbooru] detail preview failed post_id={post.post_id}: {error}")
            if self.matches(post_id=post.post_id):
                self.viewer.set_placeholder(self._detail_preview_error_message(post, error))
            return
        self.gui.log.warning(f"[Danbooru] detail size probe failed post_id={post.post_id}: {error}")

    def _apply_preview_size(self, post_id: int, size: t.Optional[tuple[int, int]]):
        if not size:
            return
        qsize = QtCore.QSize(*size)
        self._store_size(post_id, qsize)
        self.viewer.set_placeholder_size(post_id, qsize)

    def _apply_preview(self, post_id: int, raw: bytes, current_post: t.Optional[DanbooruPost] = None):
        pixmap = QPixmap()
        pixmap.loadFromData(raw, "PNG")
        if pixmap.isNull():
            return
        self._pixmap_cache[post_id] = pixmap
        self._store_size(post_id, QtCore.QSize(pixmap.width(), pixmap.height()))
        is_current_post = self.matches(post_id=post_id)
        self.viewer.set_image(post_id, pixmap)
        if is_current_post:
            self._preload_next(current_post)

    def _store_size(self, post_id: int, size: QtCore.QSize):
        cached_size = self._size_cache.get(post_id)
        if cached_size is None or (size.width() * size.height()) > (cached_size.width() * cached_size.height()):
            self._size_cache[post_id] = size
