from __future__ import annotations

import typing as t
from dataclasses import dataclass, field

import httpx

from utils import conf as _default_conf


@dataclass(frozen=True, slots=True)
class LoginTrial:
    """登录成功后验证 cookies 实际可用的试用请求。

    参考竞品 (keiyoushi/mihon): cookies 获取后通过 CookieJar 注入请求,
    并借助页面特征 (登录用户名) 或专用检查接口 (如 manhuagui user_check_login) 验证登录态。
    """

    url: str
    method: str = "GET"
    expect_contains: tuple[str, ...] = ()
    expect_not_contains: tuple[str, ...] = ()
    expect_status: int = 200
    timeout_s: float = 30.0
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LoginCheck:
    """运行时登录态静默探测 (竞品 user_check_login 同款)。

    站点切换时由 GUI 异步执行: cookies 有效则静默, 失效则提示重新登录。
    """

    url: str
    method: str = "GET"
    success_contains: tuple[str, ...] = ()
    success_not_contains: tuple[str, ...] = ()
    expect_status: int = 200
    timeout_s: float = 20.0
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LoginOpenTarget:
    """loginBtn 打开目标 (由站点 flow 声明, 消费方只执行不判断)。

    hint: 打开前/不打开时给用户的状态说明 (缺必填 cookies 等);
    blocked: True 时消费方不打开任何页面 (站点声明无可用入口)。
    """

    url: str = ""
    hint: str = ""
    blocked: bool = False


@dataclass(frozen=True, slots=True)
class LoginFlow:
    """单个站点的登录流程定义 (独立模块, 与 provider class 解耦)。

    带状态设计: 站点自身持有 domain/login_url/表单 JS/试用/探测/打开策略定义,
    消费方只需持有 provider_name 状态标识, 由 resolve_login_flow() 解析,
    不再把 provider 对象或域名作为参数链式传递。loginBtn 是各站点各自发挥的
    入口 gateway: 打开目标/必填校验/登录后导航全部由站点 flow 声明。
    """

    provider_name: str
    label: str
    domain: str
    login_url: str
    form_ready_js: str
    fill_js: str
    submit_js: str
    verify_js: str
    need_human: bool = False
    trial: LoginTrial | None = None
    check_login: LoginCheck | None = None
    member_url: str = ""
    # 登录态可感知页: 有已保存 cookies 时 loginBtn 打开此页 (已登录=个人页,
    # 失效=站点自动落到登录页), 无 cookies 时仍打开 login_url。
    # 依据: 8comic /member 已登录显示会员中心; dm5 /login/ 已登录也不跳转,
    # 登录态只在首页用户名区显示 → 打开目标必须按站区分。
    # 登录 cookies 注入/收集候选域: 非空时直接使用, 缺省由消费方推导
    # (flow.domain + 登录页 host)。ehentai 需覆盖 provider 静态域 exhentai.org
    # (里站), 与 flow.domain (e-hentai.org) 不同 → 必须显式声明。
    cookie_domains: tuple[str, ...] = ()
    # 登录态完整性必填 cookies: 保存/打开前校验 (竞品 gallery-dl 官方口径 —
    # exhentai 三件套 ipb_member_id/ipb_pass_hash/igneous 手动提取; 缺失时
    # resolve_login_open_target 提示并回落到登录页)。
    required_cookies: tuple[str, ...] = ()
    # 登录成功后自动导航: 检测到 trigger cookies 任一出现 (登录会话建立)
    # 即导航此 URL, 用于让服务器下发附加令牌 (exhentai: 访问里站下发 igneous)。
    post_login_trigger_cookies: tuple[str, ...] = ()
    post_login_navigate_url: str = ""

    @classmethod
    def current(cls, provider_name: str | None = None) -> "LoginFlow | None":
        """从状态源解析当前登录流: 显式 provider 名或当前 GUI 站点状态。"""
        return resolve_login_flow(provider_name)


_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0"
)


def run_login_trial(
    provider_name: str,
    *,
    conf_state=_default_conf,
    username: str = "",
    timeout_s: float = 30.0,
) -> dict:
    """用 conf.cookies 中已保存的 cookies 发起试用请求, 验证登录态实际生效。

    Args:
        provider_name: 目标站点 provider name
        conf_state: 配置状态源 (cookies / proxies 均从状态读取, 不链式传参)
        username: 期望在页面出现的登录用户名 (替换 {USERNAME} 占位)

    Returns:
        {"status": "pass"|"fail"|"skip", "url", "status_code", ...} 结构化结果
    """
    flow = resolve_login_flow(provider_name)
    if flow is None or flow.trial is None:
        return {"status": "skip", "reason": "no trial spec", "provider": provider_name}
    cookies = _read_site_cookies(conf_state, provider_name)
    if not cookies:
        return {"status": "skip", "reason": "no saved cookies", "provider": provider_name}
    return _execute_trial(flow, cookies, conf_state=conf_state, username=username, timeout_s=timeout_s)


def run_login_check(
    provider_name: str,
    *,
    conf_state=_default_conf,
    username: str = "",
) -> dict:
    """运行时登录态静默探测 (竞品 user_check_login 同款)。

    用 conf.cookies 已保存的 cookies 请求探测接口/页面:
    成功特征满足 → 登录态有效 (静默); 不满足 → 失效 (提示重新登录)。

    Returns:
        {"status": "pass"|"fail"|"skip", "url", "status_code", ...} 结构化结果
    """
    flow = resolve_login_flow(provider_name)
    if flow is None or flow.check_login is None:
        return {"status": "skip", "reason": "no check spec", "provider": provider_name}
    cookies = _read_site_cookies(conf_state, provider_name)
    if not cookies:
        return {"status": "skip", "reason": "no saved cookies", "provider": provider_name}
    check = flow.check_login
    proxies = tuple(str(p) for p in (getattr(conf_state, "proxies", None) or ()) if p)
    transport = None
    if proxies:
        transport = httpx.HTTPTransport(proxy=f"http://{proxies[0]}", retries=1)
    headers = {"User-Agent": _DEFAULT_UA}
    headers.update(check.headers)
    expected = tuple(
        str(item).replace("{USERNAME}", username) for item in check.success_contains
    )
    if check.success_contains and not any(expected):
        return {
            "status": "skip", "provider": flow.provider_name, "url": check.url,
            "reason": "username required for check spec",
        }
    forbidden = tuple(
        str(item).replace("{USERNAME}", username) for item in check.success_not_contains
    )
    try:
        with httpx.Client(
            transport=transport, timeout=check.timeout_s, follow_redirects=True, headers=headers,
        ) as client:
            response = client.request(check.method, check.url, cookies=cookies)
        body = response.text
    except Exception as exc:
        return {
            "status": "fail", "provider": flow.provider_name, "url": check.url,
            "error": f"{type(exc).__name__}: {exc}",
        }
    matched = [item for item in expected if item and item in body]
    found_forbidden = [item for item in forbidden if item and item in body]
    ok = (
        response.status_code == check.expect_status
        and len(matched) == len(expected)
        and not found_forbidden
    )
    return {
        "status": "pass" if ok else "fail",
        "provider": flow.provider_name,
        "url": check.url,
        "status_code": response.status_code,
        "expected": expected,
        "matched": matched,
        "forbidden_found": found_forbidden,
    }


def _read_site_cookies(conf_state, provider_name: str) -> dict[str, str]:
    cookies_owner = getattr(conf_state, "cookies", None)
    if cookies_owner is None:
        return {}
    if isinstance(cookies_owner, dict):
        site_cookies = cookies_owner.get(provider_name)
    else:
        get_site_cookies = getattr(cookies_owner, "get", None)
        site_cookies = get_site_cookies(provider_name) if callable(get_site_cookies) else None
    return {str(name): str(value) for name, value in dict(site_cookies or {}).items()}


def _execute_trial(
    flow: LoginFlow, cookies: dict[str, str], *, conf_state, username: str, timeout_s: float,
) -> dict:
    trial = flow.trial
    proxies = tuple(str(p) for p in (getattr(conf_state, "proxies", None) or ()) if p)
    transport = None
    if proxies:
        transport = httpx.HTTPTransport(proxy=f"http://{proxies[0]}", retries=1)
    headers = {"User-Agent": _DEFAULT_UA}
    headers.update(trial.headers)
    expected = tuple(
        str(item).replace("{USERNAME}", username) for item in trial.expect_contains
    )
    forbidden = tuple(
        str(item).replace("{USERNAME}", username) for item in trial.expect_not_contains
    )
    try:
        with httpx.Client(
            transport=transport, timeout=trial.timeout_s, follow_redirects=True, headers=headers,
        ) as client:
            response = client.request(trial.method, trial.url, cookies=cookies)
        body = response.text
    except Exception as exc:
        return {
            "status": "fail", "provider": flow.provider_name, "url": trial.url,
            "error": f"{type(exc).__name__}: {exc}",
        }
    matched = [item for item in expected if item and item in body]
    found_forbidden = [item for item in forbidden if item and item in body]
    ok = (
        response.status_code == trial.expect_status
        and len(matched) == len(expected)
        and not found_forbidden
    )
    return {
        "status": "pass" if ok else "fail",
        "provider": flow.provider_name,
        "url": trial.url,
        "status_code": response.status_code,
        "expected": expected,
        "matched": matched,
        "forbidden_found": found_forbidden,
        "body_sample": body[:300],
    }


# --- 注册表 (provider_name → LoginFlow 懒加载) ---

_flow_loaders: dict[str, t.Callable[[], LoginFlow]] = {}


def register_login_flow(provider_name: str, loader: t.Callable[[], LoginFlow]) -> None:
    _flow_loaders[provider_name] = loader


def resolve_login_flow(provider_name: str | None) -> LoginFlow | None:
    if not provider_name:
        return None
    loader = _flow_loaders.get(str(provider_name))
    return loader() if loader is not None else None


def resolve_login_open_target(
    flow: LoginFlow | None,
    *,
    saved_cookies: dict[str, str] | None,
) -> LoginOpenTarget:
    """loginBtn gateway: 由站点 flow 声明打开目标, 消费方只执行不判断。

    缺省策略 (未声明 required_cookies 的站点行为不变):
      无 cookies → login_url (登录页);
      有 cookies → member_url (登录态可感知页), 未声明则 login_url。
    声明 required_cookies 的站点 (exhentai): 已存 cookies 缺必填项 → 提示
    缺失项并回落登录页 — 对齐竞品 gallery-dl 官方口径 (igneous 三件套必须
    手动从浏览器提取, 自动化登录拿不到 igneous)。
    """
    if flow is None:
        return LoginOpenTarget(blocked=True)
    saved = {str(name): str(value) for name, value in (saved_cookies or {}).items()}
    missing = tuple(name for name in flow.required_cookies if not saved.get(name))
    if missing:
        return LoginOpenTarget(
            url=flow.login_url,
            hint=(
                f"已保存 cookies 缺少 {', '.join(missing)}，已打开登录页。"
                "若内置浏览器登录无法获得完整登录态，请从浏览器复制完整 cookies"
                "（含以上字段）粘贴到配置对话框"
            ),
        )
    if saved:
        return LoginOpenTarget(url=flow.member_url or flow.login_url)
    return LoginOpenTarget(url=flow.login_url)


def supported_provider_names() -> tuple[str, ...]:
    return tuple(sorted(_flow_loaders))
