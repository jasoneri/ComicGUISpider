from __future__ import annotations

from .flows import LoginCheck, LoginFlow, LoginTrial, register_login_flow


def _ehentai_flow() -> LoginFlow:
    return LoginFlow(
        provider_name="ehentai",
        label="exhentai",
        domain="e-hentai.org",
        login_url="https://forums.e-hentai.org/index.php?act=Login",
        # forums 有 Cloudflare 拦截, 主页顶部用户名区更稳定 (httpx 403 但浏览器可过);
        # member_url 用里站 exhentai.org (登录态可感知页), 与 provider 静态域口径一致
        member_url="https://exhentai.org/",
        # 登录 cookies 注入/收集候选域: 覆盖 flow.domain + 登录页 host + 里站静态域
        cookie_domains=("e-hentai.org", "forums.e-hentai.org", "exhentai.org"),
        # 登录态完整性必填三件套 (竞品 gallery-dl 官方口径): igneous 由服务器
        # 在登录后访问里站时下发, 自动化登录拿不到 → 缺项时 loginBtn 提示并
        # 回落到登录页 (resolve_login_open_target 统一处理)。
        required_cookies=("igneous", "ipb_member_id", "ipb_pass_hash"),
        # 登录成功后自动导航里站: ipb_pass_hash 出现 (会话建立) → 访问
        # exhentai.org 让服务器下发 igneous, 登录模式 cookie 监听即可收集。
        post_login_trigger_cookies=("ipb_pass_hash",),
        post_login_navigate_url="https://exhentai.org/",
        form_ready_js=(
            "document.querySelector('input[name=UserName]') !== null "
            "|| document.querySelector('input[name=username]') !== null"
        ),
        fill_js=(
            "(function () {"
            "  const user = document.querySelector('input[name=UserName], input[name=username]');"
            "  const password = document.querySelector('input[name=PassWord], input[name=password]');"
            "  if (!user || !password) return {ok: false, reason: 'IPB username/password not found'};"
            "  user.value = USERNAME;"
            "  password.value = PASSWORD;"
            "  return {ok: true};"
            "})()"
        ),
        submit_js=(
            "(function () { const f = document.querySelector('form[action*=Login]')"
            " || document.querySelector('form'); if (!f) return false; f.submit(); return true; })()"
        ),
        verify_js="document.cookie.includes('ipb_') || document.cookie.includes('ipb_pass_hash')",
        trial=LoginTrial(
            url="https://forums.e-hentai.org/index.php?act=Profile",
            expect_contains=("{USERNAME}",),
        ),
        check_login=LoginCheck(
            url="https://forums.e-hentai.org/index.php?act=Profile",
            success_contains=("{USERNAME}",),
        ),
    )


register_login_flow("ehentai", _ehentai_flow)
