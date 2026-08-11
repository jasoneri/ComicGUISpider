from __future__ import annotations

from .flows import LoginCheck, LoginFlow, LoginTrial, register_login_flow


def _dm5_flow() -> LoginFlow:
    return LoginFlow(
        provider_name="dm5",
        label="dm5 (旋转验证码)",
        domain="www.dm5.com",
        login_url="https://www.dm5.com/login/",
        # dm5 /login/ 已登录也不跳转; 登录态只在首页顶部用户名区显示 (实测/竞品同款)
        member_url="https://www.dm5.com/",
        form_ready_js="document.querySelector('input[name=txt_name]') !== null",
        fill_js=(
            "(function () {"
            "  const user = document.querySelector('input[name=txt_name]');"
            "  const password = document.querySelector('input[name=txt_password]');"
            "  if (!user || !password) return {ok: false, reason: 'txt_name/txt_password not found'};"
            "  user.value = USERNAME;"
            "  password.value = PASSWORD;"
            "  return {ok: true};"
            "})()"
        ),
        submit_js="document.querySelector('#btnLogin').click(); true",
        verify_js="document.cookie.length > 0",
        need_human=True,
        trial=LoginTrial(
            url="https://www.dm5.com/",
            expect_contains=("{USERNAME}",),
        ),
        check_login=LoginCheck(
            url="https://www.dm5.com/",
            success_contains=("{USERNAME}",),
        ),
    )


register_login_flow("dm5", _dm5_flow)
