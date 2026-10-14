from collections import Counter
from dataclasses import dataclass, replace
from enum import StrEnum
from os.path import dirname
from pathlib import Path


REMOTE_NAMESPACE = "cgs-webdav"
MODE_MANGA = "manga"
MODE_DOUJIN = "doujinshi"
MODE_OF_SCAN = {0: MODE_MANGA, 1: MODE_DOUJIN}
SCAN_MODE_OF = {MODE_MANGA: 0, MODE_DOUJIN: 1}


class UploadStatus(StrEnum):
    PENDING = "pending"
    UPLOADING = "uploading"
    PUSHED = "pushed"
    SKIPPED = "skipped"
    FAILED = "failed"
    LOCAL_MISSING = "local_missing"    # 本机外部增删的冲突预演（R-H5）
    LOCAL_MODIFIED = "local_modified"


STATUS_TEXT = {
    UploadStatus.PENDING: "待上传",
    UploadStatus.UPLOADING: "上传中",
    UploadStatus.PUSHED: "✅️已上传",
    UploadStatus.SKIPPED: "同路径同大小，已跳过",
    UploadStatus.FAILED: "上传失败",
    UploadStatus.LOCAL_MISSING: "⚠️本地已删除",
    UploadStatus.LOCAL_MODIFIED: "⚠️本地已修改",
}

# 状态列 tooltip 补充说明（文案单点定义，与枚举一起回退）；结构化 reason 优先。
STATUS_TOOLTIP = {
    UploadStatus.LOCAL_MISSING: "本地文件已被外部删除或移动；推送时将失败",
    UploadStatus.LOCAL_MODIFIED: "本地大小与上传记录不符，下次推送将重传",
    UploadStatus.FAILED: "上传失败，可点「重推失败项」重试",
}


@dataclass(frozen=True)
class UploadState:
    """状态 + 结构化原因。原因只用于提示，不参与任何状态判断。

    `batch` = 状态来源批次号（0 = 无批次上下文，如纯会话内待上传）；
    状态列文本格式 `「batch.N」, {status}`（R-H2），诚实呈现 provenance。
    """

    status: UploadStatus
    reason: str = ""
    batch: int = 0

    def text(self) -> str:
        if self.batch:
            return f"「batch.{self.batch}」, {STATUS_TEXT[self.status]}"
        return STATUS_TEXT[self.status]


ERR_INVALID_PATH = "invalid_relative_path"
ERR_UNSUPPORTED_KIND = "unsupported_kind"
ERR_REMOTE_CONFLICT = "remote_path_conflict"

ENTRY_ERROR_TEXT = {
    ERR_INVALID_PATH: "无效的相对路径",
    ERR_UNSUPPORTED_KIND: "不支持的上传类型",
    ERR_REMOTE_CONFLICT: "远端路径冲突",
}


@dataclass(frozen=True)
class UploadEntry:
    local_path: str
    remote_relative_path: str
    group_key: str
    book: str
    ep: str
    title: str
    kind: str
    library_root: str
    relative_path: str
    error_code: str = ""

    @property
    def is_uploadable(self) -> bool:
        return not self.error_code

    @property
    def error_text(self) -> str:
        return ENTRY_ERROR_TEXT.get(self.error_code, "")

    def payload(self) -> dict:
        keys = ("local_path", "remote_relative_path", "book", "ep", "title", "kind", "library_root", "relative_path")
        return {key: getattr(self, key) for key in keys}


def map_snapshot(snapshot, mode: str) -> tuple[UploadEntry, ...]:
    root = str(snapshot.root)
    scan_mode = SCAN_MODE_OF[mode]
    entries = {}
    for source in snapshot.entries:
        if source.mode != scan_mode:
            continue
        local = str(source.local_path)
        relative = source.relative_path
        parts = relative.parts
        remote = f"{REMOTE_NAMESPACE}/{mode}/{'/'.join(parts)}"
        code = ""
        if relative.anchor or not parts or any(part in (".", "..") for part in parts):
            code = ERR_INVALID_PATH
        elif source.kind not in ("cbz", "dir"):
            code = ERR_UNSUPPORTED_KIND
        group = dirname(local) if len(parts) > 1 else local
        try:
            root_relative = Path(local).relative_to(root).as_posix()
        except ValueError:
            # 本地路径在库根之外（推送时由 pusher _collect 显式拒绝）：键取扫描侧相对路径兜底，
            # 不阻断投影——该条目不落地、无记录可匹配，键值实际惰性。
            root_relative = relative.as_posix()
        entries[local] = UploadEntry(
            local, remote, group, source.book, source.ep or "", source.ep or source.book, source.kind, root,
            root_relative, code,
        )
    counts = Counter(item.remote_relative_path for item in entries.values())
    return tuple(replace(item, error_code=item.error_code or ERR_REMOTE_CONFLICT)
                 if counts[item.remote_relative_path] > 1 else item
                 for item in entries.values())
