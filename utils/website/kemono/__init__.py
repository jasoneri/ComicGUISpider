from __future__ import annotations

from deploy import Env


# Deploy only owns the environment anchor; the site sub-path belongs to the kemono module.
DEFAULT_SV_PATH = str(Env.default_acggr_path.joinpath("pawchive"))

# Keep banner local: importing utils.script.image.kemono pulls pandas/DoH/motrix (~10s+) on the GUI thread.
KEMONO_TOPIC = """
  ┏┓┏┓┏┓  ┓
  ┃ ┃┓┗┓━━┃┏┏┓┏┳┓┏┓┏┓┏┓
  ┗┛┗┛┗┛  ┛┗┗ ┛┗┗┗┛┛┗┗┛
"""
domain = "pawchive.pw"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0",
    "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    'Accept': 'text/css',
}
base = f"https://{domain}/api/v1"
creator_posts = base + "/{service}/user/{creator_id}/posts"
discord_info = base + "/discord/{kind}/{_id}"
post = base + "/{service}/user/{creator_id}/post/{post_id}"
favorites = base + "/account/favorites"
img_domain = f"img.{domain}"    # thumbnail server: /thumbnail/data/... (direct OK)
file_domain = f"file.{domain}"  # file server: /data/... (proxy required)
creators_txt = base + "/creators"