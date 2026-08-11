from __future__ import annotations

from .flows import LoginCheck, LoginFlow, LoginTrial, register_login_flow


def _manhuagui_flow() -> LoginFlow:
    return LoginFlow(
        provider_name="manhuagui",
        label="manhuagui",
        domain="www.manhuagui.com",
        login_url="https://www.manhuagui.com/user/login",
        # 首页顶部登录区显示登录态 (竞品 manhuagui 同款: 首页右上角用户名)
        member_url="https://www.manhuagui.com/",
        form_ready_js="document.querySelector('#loginform input[name=txtUserName]') !== null",
        fill_js=(
            "(function () {"
            "  const user = document.querySelector('#loginform input[name=txtUserName]');"
            "  const password = document.querySelector('#loginform input[name=txtPassword]');"
            "  if (!user || !password) return {ok: false, reason: 'txtUserName/txtPassword not found'};"
            "  user.value = USERNAME;"
            "  password.value = PASSWORD;"
            "  return {ok: true};"
            "})()"
        ),
        submit_js="document.querySelector('#btnSubmit').click(); true",
        verify_js=(
            "document.cookie.length > 0 && "
            "(document.URL.includes('/user') || document.querySelector('#loginform') === null)"
        ),
        # 竞品 keiyoushi 用 submit_ajax.ashx?action=user_check_login 检查登录态;
        # 这里直接访问用户页并要求页面出现登录用户名 (CookieJar 注入同款)
        trial=LoginTrial(
            url="https://www.manhuagui.com/user/",
            expect_contains=("{USERNAME}",),
        ),
        # 竞品同款探测接口: POST user_check_login, 带 Referer + X-Requested-With
        check_login=LoginCheck(
            url="https://www.manhuagui.com/tools/submit_ajax.ashx?action=user_check_login",
            method="POST",
            success_contains=('"status":1', "login success", "true"),
            headers={
                "Referer": "https://www.manhuagui.com/",
                "X-Requested-With": "XMLHttpRequest",
            },
        ),
    )


register_login_flow("manhuagui", _manhuagui_flow)
