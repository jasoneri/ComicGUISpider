"""站点登录流程模块 (与 provider class 解耦)。

每个目标站点一个独立模块 (comicabc.py / manhuagui.py / ...), 声明式定义
LoginFlow: 登录页 URL、表单填表/提交/验证 JS、以及登录成功后验证 cookies
实际可用的试用请求 (LoginTrial)。

带状态设计: 站点登录信息 (domain / login_url / 表单 / 试用) 全部由登录模块
自身持有, 消费方只传递 provider_name 状态标识, 通过 resolve_login_flow()
解析, 不把 provider 对象或域名作为参数链式传递。

参考竞品 (mihon / Tachiyomi / keiyoushi): WebView 登录 + CookieJar 注入请求,
keiyoushi 部分站点用专用接口 (如 manhuagui user_check_login) 检查登录态。
"""

from __future__ import annotations

from .flows import (
    LoginCheck,
    LoginFlow,
    LoginOpenTarget,
    LoginTrial,
    register_login_flow,
    resolve_login_flow,
    resolve_login_open_target,
    run_login_check,
    run_login_trial,
    supported_provider_names,
)
from . import comicabc, dm5, ehentai, jm, mangabz, manhuagui, nhentai  # noqa: F401  (注册各站点 flow)

__all__ = [
    "LoginCheck",
    "LoginFlow",
    "LoginOpenTarget",
    "LoginTrial",
    "register_login_flow",
    "resolve_login_flow",
    "resolve_login_open_target",
    "run_login_check",
    "run_login_trial",
    "supported_provider_names",
]
