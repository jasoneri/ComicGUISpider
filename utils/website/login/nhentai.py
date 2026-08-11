from __future__ import annotations

from .flows import LoginCheck, LoginFlow, LoginTrial, register_login_flow


def _nhentai_flow() -> LoginFlow:
    return LoginFlow(
        provider_name="nhentai",
        label="nhentai (Turnstile)",
        domain="nhentai.net",
        login_url="https://nhentai.net/login/",
        # favorites 未登录 302 → /login, 已登录显示收藏列表 (实测/竞品同款)
        member_url="https://nhentai.net/favorites/",
        form_ready_js="document.querySelector('input[name=username_or_email]') !== null",
        fill_js=(
            "(function () {"
            "  const user = document.querySelector('input[name=username_or_email]');"
            "  const password = document.querySelector('input[name=password]');"
            "  if (!user || !password) return {ok: false, reason: 'username_or_email/password not found'};"
            "  user.value = USERNAME;"
            "  password.value = PASSWORD;"
            "  user.dispatchEvent(new Event('input', {bubbles: true}));"
            "  password.dispatchEvent(new Event('input', {bubbles: true}));"
            "  return {ok: true};"
            "})()"
        ),
        # 登录表单含 Cloudflare Turnstile (cf-turnstile-response), 提交按钮由页面 JS
        # 在验证完成后自动启用; 自动填表后需人工完成验证码并点击提交 (竞品 keiyoushi 同场景)
        submit_js=(
            "(function () {"
            "  const btn = document.querySelector('button[type=submit]');"
            "  if (btn && !btn.disabled) { btn.click(); return true; }"
            "  return false;"
            "})()"
        ),
        verify_js="document.cookie.includes('sessionid')",
        need_human=True,
        # 竞品 keiyoushi Nhentai.kt: CookieManager 全量提取, 登录态用 API favorite_metadata 判断
        # (未登录时 /api/v2/galleries/{id}?include=favorite_metadata 不返回该字段)
        trial=LoginTrial(
            url="https://nhentai.net/api/v2/galleries/177013?include=favorite_metadata",
            expect_contains=("favorite_metadata",),
        ),
        check_login=LoginCheck(
            url="https://nhentai.net/api/v2/galleries/177013?include=favorite_metadata",
            success_contains=("favorite_metadata",),
        ),
    )


register_login_flow("nhentai", _nhentai_flow)
