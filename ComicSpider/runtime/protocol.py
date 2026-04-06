"""Spider Runtime Protocol - 统一协议定义（从 utils.protocol 导入）"""
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

# 从 utils.protocol 导入共享的协议定义
from utils.protocol import (
    SpiderDownloadJob, SubmitJobCommand, CancelJobCommand, ShutdownCommand,
    JobAcceptedEvent, JobFinishedEvent, BarProgressEvent, LogEvent, ErrorEvent,
    ProcessStateEvent, TasksObjEvent, RuntimeState,
)

__all__ = [
    'SpiderDownloadJob', 'SubmitJobCommand', 'CancelJobCommand', 'ShutdownCommand',
    'JobAcceptedEvent', 'JobFinishedEvent', 'BarProgressEvent', 'LogEvent', 'ErrorEvent',
    'ProcessStateEvent', 'TasksObjEvent', 'RuntimeState',
]
