"""Spider Runtime Package"""
from .thread_runner import SpiderRuntimeThread

__all__ = [
    "SpiderRuntimeThread",
]

# 以下模块按需导入，避免在主线程阻塞
def get_job_models():
    from .job_models import (
        create_job_context,
        iter_download_items,
        extract_payload_items,
        DownloadRequest,
    )
    return create_job_context, iter_download_items, extract_payload_items, DownloadRequest
