import typing as t
from dataclasses import dataclass

from PySide6 import QtCore
from PySide6.QtGui import QPixmap

from utils.script.image.danbooru.http import DanbooruChallengeRequired
from utils.script.image.danbooru.models import DanbooruPost

from .core import DanbooruReq, execute_danbooru_task
from .viewer import DanbooruImageViewer

if t.TYPE_CHECKING:
    from .interface import DanbooruInterface


@dataclass(frozen=True, slots=True)
class _DanbooruDetailRequestSpec:
    reason: str
    task_prefix: str
    retry_prefix: str
    challenge_placeholder: str = ""
    discard_prefetch: bool = False


_PREFETCH_REQUEST = _DanbooruDetailRequestSpec(
    reason="大图预取",
    task_prefix="danbooru-detail-prefetch",
    retry_prefix="detail-prefetch",
    discard_prefetch=True,
)
_PREVIEW_REQUEST = _DanbooruDetailRequestSpec(
    reason="大图加载",
    task_prefix="danbooru-detail-preview",
    retry_prefix="detail-preview",
    challenge_placeholder="需要网页验证",
)
_SIZE_REQUEST = _DanbooruDetailRequestSpec(
    reason="尺寸探测",
    task_prefix="danbooru-detail-size",
    retry_prefix="detail-size",
)


class DanbooruDetailPreviewController(QtCore.QObject):
    def __init__(self, interface: "DanbooruInterface", viewer: DanbooruImageViewer):
        super().__init__(interface)
        self.interface = interface
        self.viewer = viewer
        self._tab_id: t.Optional[str] = None
        self._pixmap_cache: dict[int, QPixmap] = {}
        self._size_cache: dict[int, QtCore.QSize] = {}
        self._prefetching_post_ids: set[int] = set()

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
        cached_pixmap = self._pixmap_cache.get(post.post_id)
        if cached_pixmap is not None and not cached_pixmap.isNull():
            self.viewer.set_image(post.post_id, cached_pixmap)
            self._preload_next(post)
            return
        if DanbooruImageViewer._post_size_hint(post) is None:
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
        if DanbooruPost.is_unsupported_file_ext(ext):
            return f"Preview Error\n原因: Viewer 暂不支持 {ext.upper()} 预览，请下载后在外部打开"
        if not DanbooruDetailPreviewController._detail_preview_url(post):
            return "Preview Error\n原因: 当前条目没有可用的预览地址"
        if first_line == "invalid image data":
            media_hint = ext.upper() if ext else "未知格式"
            return f"Preview Error\n原因: 返回内容不是可渲染图片，当前资源格式为 {media_hint}"
        if first_line:
            return f"Preview Error\n原因: {first_line}"
        return "Preview Error\n原因: 未知错误"

    def _apply_cached_size(self, post: DanbooruPost):
        cached_size = self._size_cache.get(post.post_id)
        if cached_size is None:
            return
        post.preview_width = cached_size.width()
        post.preview_height = cached_size.height()

    def _prefetch(self, tab_id: str, post: DanbooruPost):
        if post.post_id in self._pixmap_cache or post.post_id in self._prefetching_post_ids:
            return
        preview_url = self._detail_preview_url(post)
        if not preview_url:
            return
        self._prefetching_post_ids.add(post.post_id)
        self._execute_request(
            _PREFETCH_REQUEST,
            tab_id,
            post,
            lambda: DanbooruReq.fetch_preview(preview_url, max_width=0),
        )

    def _load_preview(self, tab_id: str, post: DanbooruPost):
        preview_url = self._detail_preview_url(post)
        if not preview_url:
            if self.matches(post_id=post.post_id):
                self.viewer.set_placeholder(self._detail_preview_error_message(post, "no preview url"))
            return
        self._execute_request(
            _PREVIEW_REQUEST,
            tab_id,
            post,
            lambda: DanbooruReq.fetch_preview(preview_url, max_width=0),
        )

    def _probe_size(self, tab_id: str, post: DanbooruPost):
        preview_url = self._detail_preview_url(post)
        if not preview_url:
            return
        self._execute_request(
            _SIZE_REQUEST,
            tab_id,
            post,
            lambda: DanbooruReq.fetch_image_size(preview_url),
        )

    def _execute_request(
        self,
        spec: _DanbooruDetailRequestSpec,
        tab_id: str,
        post: DanbooruPost,
        request: t.Callable[[], t.Any],
    ):
        execute_danbooru_task(
            self.interface.task_mgr,
            request,
            success_callback=lambda payload, current_spec=spec, current_tab_id=tab_id, current_post=post: self._handle_request_result(
                current_spec,
                current_tab_id,
                current_post,
                payload,
            ),
            error_callback=lambda error, current_spec=spec, current_post=post: self._handle_request_error(
                current_spec,
                current_post,
                error,
            ),
            task_id=f"{spec.task_prefix}-{tab_id}-{post.post_id}",
        )

    def _handle_request_result(
        self,
        spec: _DanbooruDetailRequestSpec,
        tab_id: str,
        post: DanbooruPost,
        payload,
    ):
        if payload.challenge is not None:
            self._handle_challenge(spec, tab_id, post, payload.challenge)
            return
        if spec is _SIZE_REQUEST:
            self._apply_preview_size(post.post_id, payload.value)
            return
        self._apply_preview(post.post_id, payload.value, post if spec is _PREVIEW_REQUEST else None)
        if spec is _PREFETCH_REQUEST:
            self._prefetching_post_ids.discard(post.post_id)

    def _handle_challenge(
        self,
        spec: _DanbooruDetailRequestSpec,
        tab_id: str,
        post: DanbooruPost,
        challenge: DanbooruChallengeRequired,
    ):
        if spec.discard_prefetch:
            self._prefetching_post_ids.discard(post.post_id)
        if spec.challenge_placeholder and self.matches(post_id=post.post_id):
            self.viewer.set_placeholder(spec.challenge_placeholder)
        self.interface.handle_danbooru_challenge(
            tab_id,
            challenge,
            lambda current_spec=spec, current_tab_id=tab_id, current_post=post: self._retry_request(
                current_spec,
                current_tab_id,
                current_post,
            ),
            reason=spec.reason,
            retry_key=f"{spec.retry_prefix}:{tab_id}:{post.post_id}",
        )

    def _retry_request(self, spec: _DanbooruDetailRequestSpec, tab_id: str, post: DanbooruPost):
        if spec is _PREFETCH_REQUEST:
            self._prefetch(tab_id, post)
            return
        if spec is _PREVIEW_REQUEST:
            self._load_preview(tab_id, post)
            return
        self._probe_size(tab_id, post)

    def _handle_request_error(self, spec: _DanbooruDetailRequestSpec, post: DanbooruPost, error: str):
        logger = self.interface._gui_logger()
        if spec is _PREFETCH_REQUEST:
            self._prefetching_post_ids.discard(post.post_id)
            if logger is not None:
                logger.warning(f"[Danbooru] detail prefetch failed post_id={post.post_id}: {error}")
            return
        if spec is _PREVIEW_REQUEST:
            if logger is not None:
                logger.error(f"[Danbooru] detail preview failed post_id={post.post_id}: {error}")
            if self.matches(post_id=post.post_id):
                self.viewer.set_placeholder(self._detail_preview_error_message(post, error))
            return
        if logger is not None:
            logger.warning(f"[Danbooru] detail size probe failed post_id={post.post_id}: {error}")

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
