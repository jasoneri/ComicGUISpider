"""Spider Job 模型相关实现"""
from copy import deepcopy
from typing import Any, Dict, Iterator, List, Union
from dataclasses import dataclass, field

from utils.protocol import SpiderDownloadJob, JobContext
from utils.website import BookInfo, Episode


@dataclass
class DownloadRequest:
    """统一的下载请求结构"""
    url: str
    callback_name: str = "parse_fin_page"
    meta: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    dont_filter: bool = True


def create_job_context(job: SpiderDownloadJob, record_sql, rv_sql, mr) -> JobContext:
    """从 SpiderDownloadJob 创建 JobContext"""
    tasks = {}
    precompiled_task = getattr(job, "tasks_obj", None)
    if precompiled_task is not None:
        if isinstance(precompiled_task, list):
            for task in precompiled_task:
                task_copy = deepcopy(task)
                tasks[task_copy.taskid] = task_copy
        else:
            task_copy = deepcopy(precompiled_task)
            tasks[task_copy.taskid] = task_copy
    return JobContext(
        job_id=job.job_id,
        tasks=tasks,
        tasks_path={},
        total=0,
        record_sql=record_sql,
        rv_sql=rv_sql,
        mr=mr,
    )


def extract_payload_items(payload: Any) -> List[Union[BookInfo, Episode]]:
    """从 job payload 中提取要下载的条目列表

    payload 可能是:
    - BookInfo (单本书)
    - Episode (单话)
    - List[BookInfo] (多本书)
    - List[Episode] (多话)
    """
    if payload is None:
        return []
    if isinstance(payload, (BookInfo, Episode)):
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, (BookInfo, Episode))]
    return []


def iter_download_items(job: SpiderDownloadJob) -> Iterator[Union[BookInfo, Episode]]:
    """迭代 job 中的所有下载条目"""
    yield from extract_payload_items(job.payload)
