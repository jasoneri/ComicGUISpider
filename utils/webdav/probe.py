from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from uuid import uuid4

from .client import WebDavClient, WebDavError, WebDavNotFoundError


class ProbeStage(StrEnum):
    """探测状态机的阶段。UI 按它决策，不解析任何文案。"""

    ROOT = "root"
    WRITE = "write"
    READ = "read"
    CLEANUP = "cleanup"
    DONE = "done"


@dataclass(frozen=True)
class ProbeResult:
    """探测结果。失败是状态（stage + error），不是被抛出的消息。"""

    stage: ProbeStage
    remote_path: str
    residual_path: str | None = None
    error: BaseException | None = None

    @property
    def ok(self) -> bool:
        return self.stage is ProbeStage.DONE and self.error is None

    @property
    def stale(self) -> bool:
        return self.stage is not ProbeStage.DONE


class _ProbeSession:
    def __init__(self, client: WebDavClient):
        self.client = client
        self.remote = f".cgs-webdav-probe-{uuid4().hex}.txt"
        self.remote_path = "/" + "/".join([*client.root_segments, self.remote])
        self.payload = f"CGS WebDAV read/write probe {uuid4().hex}\n".encode("utf-8")
        self.readback = None
        self.etag = None
        self.may_exist = False

    def run(self) -> ProbeResult:
        stage = ProbeStage.ROOT
        primary_error = cleanup_error = None
        try:
            nodes = self.client.propfind("", depth=0)
            if len(nodes) != 1 or not nodes[0]["is_dir"]:
                raise WebDavError("上传根必须是已经存在的目录")
            stage = ProbeStage.WRITE
            self.may_exist = True
            try:
                self.client.put_bytes(self.remote, self.payload, content_type="text/plain; charset=utf-8", if_none_match=True)
            except WebDavError as exc:
                if exc.status_code is not None and 400 <= exc.status_code < 500:
                    self.may_exist = False
                raise
            stage = ProbeStage.READ
            self._read_owned()
        except Exception as exc:
            primary_error = exc
        if self.may_exist:
            try:
                stage = ProbeStage.CLEANUP
                self._cleanup()
            except WebDavNotFoundError:
                self.may_exist = False
            except Exception as exc:
                cleanup_error = exc
        if primary_error is not None or cleanup_error is not None:
            errors = [error for error in (primary_error, cleanup_error) if error is not None]
            cause = ExceptionGroup("WebDAV 探测与清理错误", errors) if len(errors) > 1 else errors[0]
            residual = self.remote_path if self.may_exist else None
            return ProbeResult(stage, self.remote_path, residual, cause)
        return ProbeResult(ProbeStage.DONE, self.remote_path)

    def _read_owned(self):
        self.readback, self.etag = self.client.get_bytes_with_etag(self.remote)
        if self.readback != self.payload:
            raise WebDavError("测试文件内容不匹配，不能确认文件归属，未删除")

    def _cleanup(self):
        if self.readback is None:
            self._read_owned()
        if self.readback != self.payload:
            raise WebDavError("测试文件已改变，未删除")
        # GET 头常只给弱 ETag；用 PROPFIND 的 DAV:getetag 补一次，仍拿不到才放弃清理。
        etag = self._strong_etag(self.etag) or self._strong_etag(self.client.get_etag(self.remote))
        if etag is None:
            raise WebDavError("服务器未提供强 ETag，无法安全确认清理目标，测试文件已保留；正常上传不受影响")
        self.client.delete(self.remote, if_match=etag)
        try:
            self.client.get_bytes(self.remote)
        except WebDavNotFoundError:
            self.may_exist = False
        else:
            raise WebDavError("删除请求后测试路径仍然存在，未再次删除")

    @staticmethod
    def _strong_etag(value: str | None) -> str | None:
        return value if value and value.startswith('"') and value.endswith('"') else None


def probe_webdav(config: Mapping[str, object], *, client_factory=WebDavClient) -> ProbeResult:
    snapshot = dict(config)
    with client_factory(snapshot["endpoint"], snapshot["user"], snapshot["password"], root=snapshot["root"]) as client:
        return _ProbeSession(client).run()
