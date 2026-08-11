"""站点登录私有数据模块 (收藏列表 / 签到), 声明式注册。

带状态设计: 与 login/ 同构 — 站点自身持有收藏/签到定义, 消费方只传
provider_name 状态标识。
"""

from __future__ import annotations

from .flows import (
    CheckinResult,
    CheckinSpec,
    FavoritesSpec,
    register_checkin_spec,
    register_favorites_spec,
    resolve_checkin_spec,
    resolve_favorites_spec,
    run_checkin,
    run_fetch_favorites,
    supported_account_provider_names,
)
from . import jm, ehentai, manhuagui  # noqa: F401  (注册 Tier 1 站点)
from . import comicabc  # noqa: F401  (Tier 2, 内部不注册, 端点待抓包验证)

__all__ = [
    "CheckinResult",
    "CheckinSpec",
    "FavoritesSpec",
    "register_checkin_spec",
    "register_favorites_spec",
    "resolve_checkin_spec",
    "resolve_favorites_spec",
    "run_checkin",
    "run_fetch_favorites",
    "supported_account_provider_names",
]
