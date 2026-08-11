from __future__ import annotations

from .flows import LoginCheck, LoginFlow, LoginTrial, register_login_flow


def _jm_flow() -> LoginFlow:
    return LoginFlow(
        provider_name="jm",
        label="jm/18comic (图片验证码)",
        domain="18comic.vip",
        login_url="https://18comic.vip/login",
        # /user/ 未登录 301 → /login, 已登录显示用户名 (trial 同款页)
        member_url="https://18comic.vip/user/",
        form_ready_js="document.querySelector('form[name=login_form] input[name=username]') !== null",
        fill_js=(
            "(function () {"
            "  const user = document.querySelector('form[name=login_form] input[name=username]');"
            "  const password = document.querySelector('form[name=login_form] input[name=password]');"
            "  if (!user || !password) return {ok: false, reason: 'jm username/password not found'};"
            "  user.value = USERNAME;"
            "  password.value = PASSWORD;"
            "  return {ok: true};"
            "})()"
        ),
        submit_js=(
            "(function () { const f = document.querySelector('form[name=login_form]');"
            " if (!f) return false; f.submit(); return true; })()"
        ),
        # 官方 jmcomic 库: 登录态只依赖 AVS cookie
        verify_js="document.cookie.includes('AVS') || document.cookie.length > 0",
        need_human=True,
        trial=LoginTrial(
            url="https://18comic.vip/user/",
            expect_contains=("{USERNAME}",),
        ),
        check_login=LoginCheck(
            url="https://18comic.vip/user/",
            success_contains=("{USERNAME}",),
        ),
    )


register_login_flow("jm", _jm_flow)
