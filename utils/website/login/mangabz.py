from __future__ import annotations

from .flows import LoginCheck, LoginFlow, LoginTrial, register_login_flow


def _mangabz_flow() -> LoginFlow:
    return LoginFlow(
        provider_name="mangabz",
        label="mangabz (验证码)",
        domain="www.mangabz.com",
        login_url="https://www.mangabz.com/login",
        # 首页顶部登录区显示登录态 (trial 同款页)
        member_url="https://www.mangabz.com/",
        form_ready_js="document.querySelector('#formlogin input[name=txt_username]') !== null",
        fill_js=(
            "(function () {"
            "  const user = document.querySelector('#formlogin input[name=txt_username]');"
            "  const password = document.querySelector('#formlogin input[name=txt_password]');"
            "  if (!user || !password) return {ok: false, reason: 'txt_username/txt_password not found'};"
            "  user.value = USERNAME;"
            "  password.value = PASSWORD;"
            "  return {ok: true};"
            "})()"
        ),
        submit_js=(
            "(function () { const f = document.querySelector('#formlogin');"
            " if (!f) return false; f.submit(); return true; })()"
        ),
        verify_js="document.cookie.length > 0",
        need_human=True,
        trial=LoginTrial(
            url="https://www.mangabz.com/",
            expect_contains=("{USERNAME}",),
        ),
        check_login=LoginCheck(
            url="https://www.mangabz.com/",
            success_contains=("{USERNAME}",),
        ),
    )


register_login_flow("mangabz", _mangabz_flow)
