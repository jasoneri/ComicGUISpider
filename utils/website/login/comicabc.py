from __future__ import annotations

from .flows import LoginCheck, LoginFlow, LoginTrial, register_login_flow


def _comicabc_flow() -> LoginFlow:
    return LoginFlow(
        provider_name="comicabc",
        label="8comic",
        domain="www.8comic.com",
        login_url="https://www.8comic.com/member",
        # /member 已登录显示會員中心, 未登录自动 301 到登录页 (实测)
        member_url="https://www.8comic.com/member",
        form_ready_js="document.querySelector('#Form1 input[name=username]') !== null",
        fill_js=(
            "(function () {"
            "  const user = document.querySelector('#Form1 input[name=username]');"
            "  const password = document.querySelector('#Form1 input[name=password]');"
            "  if (!user || !password) return {ok: false, reason: 'username/password not found'};"
            "  user.value = USERNAME;"
            "  password.value = PASSWORD;"
            "  return {ok: true};"
            "})()"
        ),
        submit_js=(
            "(function () {"
            "  const btn = document.querySelector('#Form1 button[type=submit], #Form1 input[type=submit]');"
            "  if (btn) { btn.click(); return true; }"
            "  const user = document.querySelector('#Form1 input[name=username]');"
            "  const host = user ? user.closest('form, #Form1') : null;"
            "  if (host && host.tagName === 'FORM') { host.submit(); return true; }"
            "  return false;"
            "})()"
        ),
        verify_js=(
            "document.cookie.length > 0 && "
            "(document.URL.includes('/member') || document.querySelector('#Form1') === null)"
        ),
        trial=LoginTrial(
            url="https://www.8comic.com/member/",
            expect_contains=("{USERNAME}",),
        ),
        check_login=LoginCheck(
            url="https://www.8comic.com/member/",
            success_contains=("{USERNAME}",),
        ),
    )


register_login_flow("comicabc", _comicabc_flow)
