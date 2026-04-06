from __future__ import annotations

import asyncio
from typing import Callable, Iterable, Optional

from loguru import logger as lg

from utils.script.motrix import HTTPX_USER_AGENT, MotrixRPC
from utils.sql import SqlRecorder

from .constants import DANBOORU_SQL_TABLE, MOTRIX_POLL_INTERVAL
from .debug import append_danbooru_debug_event
from .models import DanbooruPost, DanbooruRuntimeConfig, DownloadPlan
from .session import danbooru_browser_session_store


class DanbooruDownloadPlanner:
    def __init__(self, sql_recorder: Optional[SqlRecorder] = None):
        self.sql_recorder = sql_recorder or SqlRecorder(table=DANBOORU_SQL_TABLE)

    def build(self, posts: Iterable[DanbooruPost]) -> DownloadPlan:
        post_list = list(posts)
        plan = DownloadPlan()
        if not post_list:
            return plan
        duplicated = self.sql_recorder.batch_check_dupe([post.md5 for post in post_list if post.md5])
        for post in post_list:
            if not post.file_url or not post.md5 or not post.is_supported:
                plan.failed_pre_submit.append(post)
            elif post.md5 in duplicated:
                plan.deduped_skipped.append(post)
            else:
                plan.to_submit.append(post)
        return plan
class DanbooruDownloadSubmitter:
    def __init__(
        self,
        *,
        runtime_config: Optional[DanbooruRuntimeConfig] = None,
        sql_recorder: Optional[SqlRecorder] = None,
        motrix_client: Optional[MotrixRPC] = None,
    ):
        self.runtime_config = runtime_config or DanbooruRuntimeConfig.from_conf()
        self.planner = DanbooruDownloadPlanner(sql_recorder)
        self.sql_recorder = self.planner.sql_recorder
        self.motrix_client = motrix_client

    async def submit(
        self,
        posts: Iterable[DanbooruPost],
        *,
        completion_callback: Optional[Callable[[str, bool], None]] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> DownloadPlan:
        plan = self.planner.build(posts)
        if not plan.to_submit:
            return plan

        submit_candidates = list(plan.to_submit)
        plan.to_submit = []
        rpc = self.motrix_client or MotrixRPC()
        own_rpc = self.motrix_client is None
        sem = asyncio.Semaphore(self.runtime_config.download_concurrency)
        browser_session = danbooru_browser_session_store.current()
        motrix_options = {
            **self.runtime_config.motrix_add_uri_options(),
            "header": browser_session.motrix_headers(),
        }
        append_danbooru_debug_event(
            "motrix.options",
            header_names=[item.split(":", 1)[0].strip() for item in motrix_options.get("header", []) if ":" in item],
            cookie_names=browser_session.cookie_names,
            referer=browser_session.referer(),
            user_agent=browser_session.resolved_user_agent(HTTPX_USER_AGENT),
            dns_options=dict(self.runtime_config.motrix_add_uri_options()),
        )
        lg.info(
            f"[DanbooruMotrix] submit header_names="
            f"{[item.split(':', 1)[0].strip() for item in motrix_options.get('header', []) if ':' in item]} "
            f"cookie_names={browser_session.cookie_names} "
            f"referer={browser_session.referer() or '<none>'}"
        )
        if self.runtime_config.is_doh_enabled():
            lg.info(
                f"[DanbooruDNS] runtime doh={self.runtime_config.doh_url} stub={self.runtime_config.stub_dns_endpoint()} motrix={self.runtime_config.stub_dns_server()}"
            )
        else:
            lg.info("[DanbooruDNS] runtime doh=disabled motrix=system")

        async def run_rpc_task(post: DanbooruPost) -> tuple[DanbooruPost, Optional[str]]:
            async with sem:
                try:
                    target_path = self.runtime_config.resolve_download_path(post)
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    gid = await rpc.add_uri(
                        post.file_url,
                        target_dir=target_path.parent,
                        out=post.filename,
                        task_id=f"danbooru-{post.post_id}",
                        options=motrix_options,
                    )
                    while True:
                        status_payload = await rpc.tell_status(gid)
                        status = status_payload.get("status")
                        if status == "complete":
                            if completion_callback is not None:
                                completion_callback(post.md5, True)
                            return post, None
                        if status in {"error", "removed"}:
                            error = status_payload.get("errorMessage") or status_payload.get("errorCode") or status or "unknown"
                            return post, error
                        if progress_callback is not None:
                            progress_callback(f"等待 Motrix 完成 {post.post_id}: {status or 'unknown'}")
                        await asyncio.sleep(MOTRIX_POLL_INTERVAL)
                except Exception as exc:
                    return post, str(exc)

        try:
            tasks = [asyncio.create_task(run_rpc_task(post)) for post in submit_candidates]
            for future in asyncio.as_completed(tasks):
                post, error = await future
                if error:
                    plan.failed_pre_submit.append(post)
                    plan.submission_errors.append(f"{post.post_id}: {error}")
                    continue
                plan.to_submit.append(post)
        finally:
            if own_rpc:
                await rpc.aclose()

        if plan.submission_errors and not plan.to_submit:
            raise RuntimeError("Motrix submission failed: " + "; ".join(plan.submission_errors[:3]))
        return plan
