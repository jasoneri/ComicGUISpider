"""Provider template for new site adapters.

Copy this file, rename the class, then only fill the site-specific hooks.
Do not import GUI classes or runtime-only side effects here.
"""

from utils.website.core import (
    Previewer,
    PreviewRequestSpec,
    ProviderContext,
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
    def preview_client_config(cls, context: ProviderContext):
        return {"headers": cls.headers}

    @classmethod
    def _build_preview_search_request(
        cls,
        keyword: str,
        *,
        page: int = 1,
        context: ProviderContext,
    ) -> PreviewRequestSpec:
        raise NotImplementedError

    @classmethod
    async def preview_search(
        cls,
        keyword,
        client,
        *,
        page=1,
        context: ProviderContext,
    ):
        spec = cls._build_preview_search_request(keyword, page=page, context=context)
        resp = await cls.perform_preview_request(client, spec)
        return await cls.parse_preview_search_response(resp.text, spec)

    @classmethod
    async def parse_preview_search_response(cls, text: str, spec: PreviewRequestSpec) -> list:
        raise NotImplementedError

    @classmethod
    async def preview_fetch_episodes(cls, book, client, *, context: ProviderContext):
        raise NotImplementedError

    @classmethod
    async def preview_fetch_pages(cls, episode, client, *, context: ProviderContext):
        raise NotImplementedError
