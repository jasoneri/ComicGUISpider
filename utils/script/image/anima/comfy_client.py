from __future__ import annotations

import json
from pathlib import Path
import uuid
from urllib.parse import quote, urlsplit

import httpx
import psutil
from loguru import logger
from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkProxy
from PySide6.QtWebSockets import QWebSocket

from utils.script import conf as script_conf

from .danbooru_anima import (
    ANIMA_PRESETS, attach_img2img, attach_wd14, build_workflow, upload_image,
)


# Placeholder / CLI default only. GUI must use configured_comfy_host(); empty conf must not fall back here.
COMFY_HOST = "http://127.0.0.1:8188"
COMFY_UNET_PRESETS = ANIMA_PRESETS
# ComfyUI server.py 硬校验：sort_by 只认这两个，传别的直接 400。
JOB_SORT_KEYS = ("created_at", "execution_duration")
_RECONNECT_DELAYS_MS = (1000, 2000, 4000, 8000, 16000, 30000)


def configured_comfy_host() -> str | None:
    """Script conf `comfy.host` when non-empty; None means Comfy capability is off (no silent 8188)."""
    section = getattr(script_conf, "comfy", None) or {}
    if not isinstance(section, dict):
        return None
    host = str(section.get("host") or "").strip()
    return host or None


def is_comfy_configured() -> bool:
    return configured_comfy_host() is not None


class ComfyJobClient(QObject):
    """在 Qt 事件循环内驱动 ComfyUI 任务 REST/WS 接口。"""

    job_started = Signal(str)
    progress_updated = Signal(str, int, int, str)
    job_completed = Signal(str, object)
    job_failed = Signal(str, str)
    job_cancelled = Signal(str)
    queue_length_changed = Signal(int)
    ws_state_changed = Signal(str, str)

    def __init__(self, host: str = COMFY_HOST, *, client_id: str | None = None,
                 timeout: float = 60.0, http_client: httpx.Client | None = None,
                 auto_connect: bool = True, parent: QObject | None = None):
        super().__init__(parent)
        self._host = host.rstrip("/")
        self._client_id = client_id or str(uuid.uuid4())
        if not self._client_id.strip():
            raise ValueError("client_id must be a non-empty string.")
        if http_client is None:
            self._http = httpx.Client(base_url=self._host, timeout=timeout, trust_env=False)
            self._owns_http = True
        else:
            self._http = http_client
            self._owns_http = False
        self._jobs: dict[str, dict] = {}
        self._progress: dict[str, dict[str, tuple[int, int]]] = {}
        self._current_node_ids: dict[str, str] = {}
        self._current_nodes: dict[str, str] = {}
        self._outputs: dict[str, list[dict]] = {}
        self._cancelled_jobs: set[str] = set()
        self._ws = QWebSocket(parent=self)
        self._ws.textMessageReceived.connect(self.handle_ws_message)
        self._ws.binaryMessageReceived.connect(self._ignore_binary_message)
        self._ws.connected.connect(self._on_ws_connected)
        self._ws.disconnected.connect(self._on_ws_disconnected)
        self._ws.errorOccurred.connect(self._on_ws_error)
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self.connect_websocket)
        self._reconnect_attempt = 0
        self._ws_connecting = False
        self._ws_connected = False
        self._closed = False
        self._last_ws_error = None
        if auto_connect:
            self.connect_websocket()

    @property
    def client_id(self) -> str:
        return self._client_id

    @property
    def websocket_url(self) -> str:
        parts = urlsplit(self._host)
        scheme = "wss" if parts.scheme == "https" else "ws"
        client_id = quote(self._client_id, safe="")
        return f"{scheme}://{parts.netloc}/ws?clientId={client_id}"

    def submit(self, workflow: dict) -> str:
        """提交 API workflow，并将同一 client_id 送入 ComfyUI 的定向事件通道。"""
        if not isinstance(workflow, dict):
            raise TypeError("workflow must be a dict.")
        # 先连 ws 再提交：反过来的话，turbo 这类十几秒就跑完的任务
        # 可能在 ws 握手完成前就发完了 execution_start，面板永远等不到「开始」。
        if not self._ws_connected and not self._ws_connecting:
            self.connect_websocket()
        response = self._http.post("/prompt", json={"prompt": workflow, "client_id": self._client_id})
        response.raise_for_status()
        payload = self._json_payload(response, "/prompt")
        prompt_id = payload.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            raise ValueError("ComfyUI /prompt response has no prompt_id.")
        self._jobs[prompt_id] = {"status": "pending"}
        self._progress.pop(prompt_id, None)
        self._current_node_ids.pop(prompt_id, None)
        self._current_nodes.pop(prompt_id, None)
        self._outputs.pop(prompt_id, None)
        self._cancelled_jobs.discard(prompt_id)
        return prompt_id

    def job_state(self, job_id: str) -> dict:
        """Return the local live state used by GUI progress projections."""
        normalized_job_id = self._require_job_id(job_id)
        state = self._jobs.get(normalized_job_id)
        if state is None:
            raise KeyError(f"Unknown ComfyUI job: {normalized_job_id}")
        return dict(state)

    def output_directory(self) -> Path:
        """Resolve the output directory from the running ComfyUI process.

        ComfyUI does not expose this filesystem path through its HTTP API. The
        local launcher does expose it in its process arguments, so this owner
        resolves the same source instead of guessing from the Python package path.
        """
        host_parts = urlsplit(self._host)
        target_port = str(host_parts.port or (443 if host_parts.scheme == "https" else 80))
        for process in psutil.process_iter(("name", "cmdline")):
            try:
                command_line = list(process.info.get("cmdline") or [])
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
            if not command_line or not self._is_comfy_process(command_line, target_port):
                continue
            output_path = self._argument_value(command_line, "--output-directory")
            if output_path is not None:
                resolved_path = Path(output_path).expanduser().resolve()
                if resolved_path.is_dir():
                    return resolved_path
                raise FileNotFoundError(f"ComfyUI output directory does not exist: {resolved_path}")
            base_directory = self._argument_value(command_line, "--base-directory")
            if base_directory is not None:
                resolved_path = Path(base_directory).expanduser().resolve().joinpath("output")
                if resolved_path.is_dir():
                    return resolved_path
                raise FileNotFoundError(f"ComfyUI output directory does not exist: {resolved_path}")
            main_path = next(
                (
                    Path(self._clean_command_line_value(value))
                    for value in command_line
                    if self._clean_command_line_value(value).casefold().endswith("main.py")
                ),
                None,
            )
            if main_path is not None:
                resolved_path = main_path.resolve().parent.joinpath("output")
                if resolved_path.is_dir():
                    return resolved_path
                raise FileNotFoundError(f"ComfyUI output directory does not exist: {resolved_path}")
        raise RuntimeError(f"Cannot locate the running ComfyUI process on port {target_port}")

    def cancel(self, job_id: str) -> None:
        """调用 ComfyUI 的统一取消入口；pending 和 running 不共用本地猜测逻辑。"""
        normalized_job_id = self._require_job_id(job_id)
        response = self._http.post(f"/api/jobs/{quote(normalized_job_id, safe='')}/cancel")
        response.raise_for_status()
        state = self._jobs.get(normalized_job_id)
        if state and state.get("status") in {"pending", "in_progress"}:
            self._mark_cancelled(normalized_job_id)

    def list_jobs(self, *, status: str = "", sort_by: str = "", sort_order: str = "",
                  limit: int | None = None, offset: int | None = None) -> list[dict]:
        params = {
            key: value for key, value in {
                "status": status,
                "sort_by": sort_by,
                "sort_order": sort_order,
                "limit": limit,
                "offset": offset,
            }.items() if value not in (None, "")
        }
        response = self._http.get("/api/jobs", params=params)
        response.raise_for_status()
        payload = self._json_payload(response, "/api/jobs")
        jobs = payload.get("jobs")
        if not isinstance(jobs, list) or any(not isinstance(job, dict) for job in jobs):
            raise ValueError("ComfyUI /api/jobs response has no jobs list.")
        for job in jobs:
            job_id = job.get("id")
            if isinstance(job_id, str) and job_id:
                self._jobs.setdefault(job_id, {}).update(job)
        return jobs

    def fetch_history(self, job_id: str) -> dict:
        """Comfy /history/{id} 原始任务记录（含提交时 workflow，节点 14 是编辑器原文）。

        history 已被 Comfy 清理或 job 未知时抛 httpx.HTTPStatusError（404）。
        """
        normalized_job_id = self._require_job_id(job_id)
        response = self._http.get(f"/history/{quote(normalized_job_id, safe='')}")
        response.raise_for_status()
        payload = self._json_payload(response, f"/history/{normalized_job_id}")
        if not isinstance(payload, dict):
            raise ValueError("ComfyUI /history response is not a dict.")
        record = payload.get(normalized_job_id)
        if not isinstance(record, dict):
            return {}
        return record

    def output_file_path(self, preview_output: dict) -> Path:
        """Resolve a Comfy output record to its local image file."""
        if not isinstance(preview_output, dict):
            raise TypeError("preview_output must be a dict.")
        filename = preview_output.get("filename")
        if not isinstance(filename, str) or not filename.strip():
            raise ValueError("preview_output.filename must be a non-empty string.")
        output_type = str(preview_output.get("type", "output") or "output")
        if output_type != "output":
            raise ValueError(f"Comfy preview output is not a local output file: {output_type}")
        subfolder = preview_output.get("subfolder", "")
        if not isinstance(subfolder, str):
            raise ValueError("preview_output.subfolder must be a string.")

        output_directory = self.output_directory().resolve()
        output_file = (output_directory / subfolder / filename).resolve()
        try:
            output_file.relative_to(output_directory)
        except ValueError as error:
            raise ValueError("Comfy preview output escapes the output directory") from error
        if not output_file.is_file():
            raise FileNotFoundError(f"Comfy preview output does not exist: {output_file}")
        return output_file

    def fetch_output_bytes(self, preview_output: dict) -> bytes:
        if not isinstance(preview_output, dict):
            raise TypeError("preview_output must be a dict.")
        filename = preview_output.get("filename")
        if not isinstance(filename, str) or not filename:
            raise ValueError("preview_output.filename must be a non-empty string.")
        params = {
            "filename": filename,
            "subfolder": preview_output.get("subfolder", ""),
            "type": preview_output.get("type", "output"),
        }
        response = self._http.get("/view", params=params)
        response.raise_for_status()
        return response.content

    def connect_websocket(self) -> None:
        """建立或重新建立 WS；失败状态和下次重试时间都通过信号公开。"""
        if self._closed or self._ws_connected or self._ws_connecting:
            return
        self._reconnect_timer.stop()
        self._ws_connecting = True
        self._ws.setProxy(QNetworkProxy(QNetworkProxy.NoProxy))
        self._set_ws_state("connecting", self.websocket_url)
        self._ws.open(QUrl(self.websocket_url))

    def close(self) -> None:
        self._closed = True
        self._reconnect_timer.stop()
        self._ws_connecting = False
        self._ws.close()
        if self._owns_http:
            self._http.close()

    def handle_ws_message(self, message: str) -> None:
        """ws 是一秒十几帧的高频通道，异常处理必须按「高频」设计。

        踩过的坑：分发异常直接放行 → 全局异常钩子按帧生成 error InfoBar，
        用户面前堆出关不完的一列错误条，真正的根因反而被淹没。
        故这里的口径是**日志不降级、提示去重**：
          - 完整堆栈每次都进 loguru（禁止隐藏报错堆栈，一条都不少）
          - 面向用户的 ws_state_changed 只在错误内容变化时发一次
        """
        try:
            event = json.loads(message)
            if not isinstance(event, dict) or "type" not in event or "data" not in event:
                # 非事件帧（ComfyUI 也走同一通道推别的东西）不是错误，跳过即可。
                return
            event_type = event["type"]
            data = event["data"]
            if not isinstance(event_type, str) or not isinstance(data, dict):
                return
            self._dispatch_event(event_type, data)
        except Exception as error:
            logger.exception(f"ComfyUI ws 事件处理失败：{message[:400]}")
            detail = f"{type(error).__name__}: {error}"
            if detail != self._last_ws_error:
                self._last_ws_error = detail
                self._set_ws_state("error", f"ComfyUI 事件处理失败：{detail}（完整堆栈见日志）")
        else:
            self._last_ws_error = None

    def _dispatch_event(self, event_type: str, data: dict) -> None:
        if event_type == "status":
            status = data["status"]
            queue_remaining = status["exec_info"]["queue_remaining"]
            if not isinstance(queue_remaining, (int, float)):
                return
            self.queue_length_changed.emit(int(queue_remaining))
        elif event_type == "execution_start":
            prompt_id = self._prompt_id(data)
            self._jobs.setdefault(prompt_id, {})["status"] = "in_progress"
            self.job_started.emit(prompt_id)
        elif event_type == "executing":
            self._handle_executing(data)
        elif event_type == "progress_state":
            self._handle_progress_state(data)
        elif event_type == "executed":
            self._handle_executed(data)
        elif event_type == "execution_success":
            prompt_id = self._prompt_id(data)
            self._jobs.setdefault(prompt_id, {}).update({
                "status": "completed",
                "progress_current": 1,
                "progress_max": 1,
            })
            result = self._collect_result(self._outputs.pop(prompt_id, []))
            self.job_completed.emit(prompt_id, result)
        elif event_type == "execution_error":
            prompt_id = self._prompt_id(data)
            error_text = self._execution_error_text(data)
            self._jobs.setdefault(prompt_id, {}).update({"status": "failed"})
            self.job_failed.emit(prompt_id, error_text)
        elif event_type == "execution_interrupted":
            self._mark_cancelled(self._prompt_id(data))

    def _handle_executing(self, data: dict) -> None:
        # ComfyUI 部分版本/帧只推 {"node": "11"}，不带 prompt_id；硬 raise 会刷爆错误条。
        prompt_id = self._resolve_prompt_id(data, required=False)
        node = data.get("node")
        if node is None:
            return
        if prompt_id is None:
            logger.debug(f"ComfyUI executing without prompt_id ignored: {data!r}")
            return
        node_id = str(node)
        display_node = data.get("display_node") or node_id
        if not isinstance(display_node, str):
            raise ValueError("executing.display_node must be a string or null.")
        self._current_node_ids[prompt_id] = node_id
        self._current_nodes[prompt_id] = display_node
        job_state = self._jobs.setdefault(prompt_id, {})
        job_state["status"] = "in_progress"
        job_state["display_node"] = display_node
        value, maximum = self._progress.get(prompt_id, {}).get(node_id, (0, 0))
        job_state["progress_current"] = value
        job_state["progress_max"] = maximum
        self.progress_updated.emit(prompt_id, value, maximum, display_node)

    def _handle_progress_state(self, data: dict) -> None:
        prompt_id = self._resolve_prompt_id(data, required=False)
        if prompt_id is None:
            logger.debug(f"ComfyUI progress_state without prompt_id ignored: keys={list(data)}")
            return
        nodes = data["nodes"]
        if not isinstance(nodes, dict):
            raise ValueError("progress_state.nodes must be an object.")
        progress = self._progress.setdefault(prompt_id, {})
        for node_id, state in nodes.items():
            if not isinstance(state, dict):
                continue
            # 不做 isinstance(int) 断言：ComfyUI 侧 value/max 是 JSON 数字，
            # 采样器给的是浮点（如 0.0/12.0），断死 int 会让**每一帧**进度都抛异常。
            # 这是一秒十几帧的通道，抛出去等于给用户刷出关不完的错误条——
            # 防御性校验本身成了故障源，按项目规约应当去掉而不是加 try 兜。
            value = state.get("value")
            maximum = state.get("max")
            if not isinstance(value, (int, float)) or not isinstance(maximum, (int, float)):
                continue
            progress[str(node_id)] = (int(value), int(maximum))
        # 只报告 executing 当前节点：逐节点状态不能直接相加，跨节点加权会把排队/缓存阶段伪装成连续进度。
        current_node = self._current_node_id(prompt_id)
        if current_node is None:
            return
        if current_node not in progress:
            return
        value, maximum = progress[current_node]
        job_state = self._jobs.setdefault(prompt_id, {})
        job_state["status"] = "in_progress"
        job_state["progress_current"] = value
        job_state["progress_max"] = maximum
        job_state["display_node"] = self._current_nodes[prompt_id]
        self.progress_updated.emit(prompt_id, value, maximum, self._current_nodes[prompt_id])

    def _handle_executed(self, data: dict) -> None:
        """留下每个节点的完整 output，而不是只挑 images。

        WD14 是 OUTPUT_NODE，它的产出在 `output["tags"]` 里——只留 images
        就把「这次自动补了哪些 tag」整段丢了（R15/AC14 的唯一来源）。
        """
        prompt_id = self._resolve_prompt_id(data, required=False)
        if prompt_id is None:
            logger.debug(f"ComfyUI executed without prompt_id ignored: keys={list(data)}")
            return
        output = data["output"]
        if not isinstance(output, dict):
            raise ValueError("executed.output must be an object.")
        self._outputs.setdefault(prompt_id, []).append({
            "node": str(data.get("node") or ""),
            "display_node": str(data.get("display_node") or data.get("node") or ""),
            "output": output,
        })

    @staticmethod
    def _collect_result(outputs: list[dict]) -> dict:
        """把逐节点 output 摊平成调用方要的三样：图片、WD14 tag、原始清单。

        原始清单保留是因为将来加节点（如 upscale）不该再改一次信号形状。
        """
        images = []
        tags = []
        for entry in outputs:
            node_output = entry.get("output") or {}
            for image in node_output.get("images") or []:
                if isinstance(image, dict):
                    images.append(image)
            for tag in node_output.get("tags") or []:
                if isinstance(tag, str) and tag.strip():
                    tags.append(tag)
        return {"images": images, "tags": tags, "outputs": list(outputs)}

    def _current_node_id(self, prompt_id: str) -> str | None:
        return self._current_node_ids.get(prompt_id)

    def _on_ws_connected(self) -> None:
        self._ws_connecting = False
        self._ws_connected = True
        self._reconnect_attempt = 0
        self._set_ws_state("connected", self.websocket_url)

    def _on_ws_disconnected(self) -> None:
        self._ws_connecting = False
        self._ws_connected = False
        if not self._closed:
            self._set_ws_state("disconnected", "ComfyUI WebSocket 已断开")
            self._schedule_reconnect()

    def _on_ws_error(self, _error) -> None:
        self._ws_connecting = False
        self._ws_connected = False
        detail = self._ws.errorString() or "ComfyUI WebSocket 连接失败"
        self._set_ws_state("error", detail)
        self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        if self._closed or self._reconnect_timer.isActive():
            return
        index = min(self._reconnect_attempt, len(_RECONNECT_DELAYS_MS) - 1)
        delay = _RECONNECT_DELAYS_MS[index]
        self._reconnect_attempt += 1
        self._set_ws_state("reconnecting", f"{delay} ms 后重连：{self.websocket_url}")
        self._reconnect_timer.start(delay)

    def _ignore_binary_message(self, _message: bytes) -> None:
        # ComfyUI 的预览图二进制帧不是任务 JSON；客户端已有 REST 缩略图入口，故安全忽略。
        return

    def _mark_cancelled(self, prompt_id: str) -> None:
        state = self._jobs.setdefault(prompt_id, {})
        state["status"] = "failed"
        if prompt_id not in self._cancelled_jobs:
            self._cancelled_jobs.add(prompt_id)
            self.job_cancelled.emit(prompt_id)

    @staticmethod
    def _prompt_id(data: dict) -> str:
        prompt_id = data.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            raise ValueError("ComfyUI event has no prompt_id.")
        return prompt_id

    def _resolve_prompt_id(self, data: dict, *, required: bool = True) -> str | None:
        """Read prompt_id from the event, or attribute to the sole live local job.

        Some ComfyUI builds emit high-frequency frames (especially ``executing``)
        with only ``node`` and no ``prompt_id``. Raising on those frames floods
        the UI via the global exception hook; terminal events that still lack an
        id after fallback may still require a hard error when ``required=True``.
        """
        prompt_id = data.get("prompt_id")
        if isinstance(prompt_id, str) and prompt_id.strip():
            return prompt_id.strip()
        fallback_prompt_id = self._sole_live_prompt_id()
        if fallback_prompt_id is not None:
            return fallback_prompt_id
        if required:
            raise ValueError("ComfyUI event has no prompt_id.")
        return None

    def _sole_live_prompt_id(self) -> str | None:
        """When exactly one job is pending/running locally, attribute orphan frames to it."""
        live_statuses = {"pending", "in_progress"}
        live_ids = [
            job_id
            for job_id, state in self._jobs.items()
            if isinstance(job_id, str) and job_id and str(state.get("status") or "") in live_statuses
        ]
        if len(live_ids) == 1:
            return live_ids[0]
        return None

    @staticmethod
    def _require_job_id(job_id: str) -> str:
        if not isinstance(job_id, str) or not job_id.strip():
            raise ValueError("job_id must be a non-empty string.")
        return job_id.strip()

    @staticmethod
    def _json_payload(response: httpx.Response, endpoint: str) -> dict:
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"ComfyUI {endpoint} response must be an object.")
        return payload

    @staticmethod
    def _execution_error_text(data: dict) -> str:
        parts = []
        if data.get("exception_message"):
            parts.append(str(data["exception_message"]))
        if data.get("traceback"):
            parts.append(str(data["traceback"]))
        if not parts:
            parts.append(json.dumps(data, ensure_ascii=False))
        return "\n".join(parts)

    def _set_ws_state(self, state: str, detail: str) -> None:
        self.ws_state_changed.emit(state, detail)

    @staticmethod
    def _argument_value(command_line: list[str], argument_name: str) -> str | None:
        normalized_argument_name = argument_name.casefold()
        for argument_index, raw_argument in enumerate(command_line):
            argument = str(raw_argument).strip()
            normalized_argument = argument.casefold()
            if normalized_argument.startswith(f"{normalized_argument_name}="):
                value = argument.split("=", 1)[1]
                return ComfyJobClient._require_command_line_value(value, argument_name)
            if normalized_argument != normalized_argument_name:
                continue
            value_index = argument_index + 1
            if value_index >= len(command_line):
                raise RuntimeError(f"ComfyUI process argument {argument_name} has no value")
            return ComfyJobClient._require_command_line_value(
                command_line[value_index], argument_name
            )
        return None

    @staticmethod
    def _clean_command_line_value(value: object) -> str:
        return str(value).strip().strip('"').strip("'")

    @classmethod
    def _require_command_line_value(cls, value: object, argument_name: str) -> str:
        cleaned_value = cls._clean_command_line_value(value)
        if not cleaned_value:
            raise RuntimeError(f"ComfyUI process argument {argument_name} has no value")
        return cleaned_value

    @classmethod
    def _is_comfy_process(cls, command_line: list[str], target_port: str) -> bool:
        if not any(
            cls._clean_command_line_value(value).casefold().endswith("main.py")
            for value in command_line
        ):
            return False
        port = cls._argument_value(command_line, "--port")
        return port == target_port


__all__ = [
    "ANIMA_PRESETS",
    "COMFY_HOST",
    "COMFY_UNET_PRESETS",
    "ComfyJobClient",
    "configured_comfy_host",
    "is_comfy_configured",
    "attach_img2img",
    "attach_wd14",
    "build_workflow",
    "upload_image",
]
