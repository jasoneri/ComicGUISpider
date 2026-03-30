"""Provider template for new site adapters.

Copy this file, rename the class, then only fill the site-specific hooks.
Do not import GUI classes or runtime-only side effects here.
"""

from utils.website.core import (
    Previewer,
    PreviewRequestSpec,
    Utils,
)


class TemplateUtils(Utils, Previewer):
    name = "template"
    domain = "example.com"
    index = f"https://{domain}"
    headers = {}
    mappings = {}
    turn_page_info = None

    @classmethod
    def preview_client_config(cls, **context):
        return {"headers": cls.headers}

    @classmethod
    def preview_transport_config(cls) -> dict:
        return {}

    @classmethod
    def _build_preview_search_request(
        cls,
        keyword: str,
        *,
        page: int = 1,
        **context,
    ) -> PreviewRequestSpec:
        raise NotImplementedError

    @classmethod
    async def preview_search(
        cls,
        keyword,
        client,
        **kw,
    ):
        page = max(1, int(kw.pop("page", 1) or 1))
        spec = cls._build_preview_search_request(
            keyword,
            page=page,
            **cls.pop_site_kwargs(kw),
        )
        resp = await cls.perform_preview_request(client, spec)
        return await cls.parse_preview_search_response(resp.text, spec)

    @classmethod
    async def parse_preview_search_response(cls, text: str, spec: PreviewRequestSpec) -> list:
        raise NotImplementedError

    @classmethod
    async def preview_fetch_episodes(cls, book, client, **kw):
        raise NotImplementedError

    @classmethod
    async def preview_fetch_pages(cls, episode, client, **kw):
        raise NotImplementedError
