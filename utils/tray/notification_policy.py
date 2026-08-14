from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScheduleNotification:
    title: str
    message: str
    level: str
    context: str = "Schedule"


def notification_for_schedule_result(summary, *, trigger: str) -> ScheduleNotification | None:
    pending = int(getattr(summary, "pending_episodes", 0) or 0)
    jobs = int(getattr(summary, "submitted_jobs", 0) or 0)
    book_errors = int(getattr(summary, "book_errors", 0) or 0)
    feature_errors = int(getattr(summary, "feature_errors", 0) or 0)
    mode = str(getattr(summary, "mode", "") or "subscription")
    manual = _is_manual(trigger)
    if book_errors or feature_errors:
        return ScheduleNotification(
            title="追更部分完成",
            message=(
                f"{mode} 完成：pending={pending} jobs={jobs} "
                f"book_errors={book_errors} feature_errors={feature_errors}。"
            ),
            level="warning",
        )
    if pending <= 0 and jobs <= 0 and not manual:
        return None
    if pending > 0 or jobs > 0:
        return ScheduleNotification(
            title="追更发现更新",
            message=f"{mode} 扫描到 {pending} 个待下载章节，已提交 {jobs} 个下载任务。",
            level="info",
        )
    return ScheduleNotification(
        title="追更检查完成",
        message=f"{mode} 手动检查完成，未发现待下载章节。",
        level="info",
    )


def notification_for_schedule_error(exc: BaseException, *, trigger: str) -> ScheduleNotification:
    return ScheduleNotification(
        title="追更需要处理",
        message=explain_schedule_error(exc),
        level="error",
    )


def notification_for_schedule_blocker(blocker: str, *, trigger: str) -> ScheduleNotification | None:
    if not blocker:
        return None
    return ScheduleNotification(
        title="追更暂时无法运行",
        message=explain_schedule_blocker(blocker),
        level="warning",
    )


def explain_schedule_error(exc: BaseException) -> str:
    text = str(exc)
    normalized = text.lower()
    if "discord_share_user_token" in normalized or _looks_like_token_error(normalized):
        return "缺少 Discord share user token。请在主窗口配置 token 后重试。"
    if "publish_bid" in normalized:
        return "分享链尚未发布，后台元数据发布会被阻塞。请在追更配置里发布分享链生成 publish_bid。"
    if "cgs_metadata_channel_id" in normalized:
        return "缺少 metadata channel 配置。请设置 CGS_METADATA_CHANNEL_ID 后重试。"
    if "subscription download job timed out" in normalized:
        return "下载任务提交超时。请检查 Server runtime 是否可用，并查看 Schedule Debug/Server 错误详情。"
    if "worker" in normalized and ("404" in normalized or "not found" in normalized or "missing" in normalized):
        return "订阅源索引不存在或已失效。请检查 follow bid 是否正确。"
    return text


def explain_schedule_blocker(blocker: str) -> str:
    text = str(blocker)
    normalized = text.lower()
    if "already in progress" in normalized:
        return "已有订阅检查正在运行，请等待当前任务结束后再执行。"
    if "not idle" in normalized:
        return "CGS Server 正在处理其他任务，请等待空闲后再执行追更检查。"
    if "unavailable" in normalized:
        return "CGS Server runtime 当前不可用，请检查 Server 状态。"
    if "not ready" in normalized:
        return "CGS Server 尚未就绪，请等待启动完成后再执行。"
    return text


def _is_manual(trigger: str) -> bool:
    return "manual" in str(trigger or "").lower() or "立刻" in str(trigger or "")


def _looks_like_token_error(text: str) -> bool:
    if "token" not in text:
        return False
    return any(marker in text for marker in ("missing", "required", "invalid", "expired", "unauthorized", "401", "403"))
