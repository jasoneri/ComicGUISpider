"""Provider template for new owner-bound site implementations.

Copy this file, rename the classes, then fill the site-specific plan and parser hooks.
Do not import GUI classes or runtime-only side effects here.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from assets import res
from utils.website.core import Previewer, Req, Utils


class TemplateParser(Previewer):
    @classmethod
    def parse_home_books(cls, text: str) -> list:
        raise NotImplementedError

    @classmethod
    def parse_list_books(cls, text: str) -> list:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class TemplatePreviewPlan:
    kind: str
    first_page_url: str
    parser_name: str
    params: tuple[tuple[str, str], ...] = ()

    def has_page(self, page: int) -> bool:
        return self.kind != "home" or page <= 1

    def url_for_page(self, owner_type: type[TemplateUtils], *, page: int) -> str:
        if page <= 1 or self.kind == "home":
            return self.first_page_url
        return owner_type.build_list_page_url(dict(self.params), page=page)

    def parse_func(self, parser_cls: type[TemplateParser]):
        return getattr(parser_cls, self.parser_name)


class TemplateReqer(Req):
    def __init__(self, _conf):
        self.cli = self.get_cli(_conf)

    async def _fetch_parse(self, url, parse_fn):
        resp = await self.ensure_preview_client().get(url, headers=self._require_preview_owner().headers, follow_redirects=True, timeout=12)
        resp.raise_for_status()
        return await asyncio.to_thread(parse_fn, resp.text)

    async def preview_search(self, keyword: str, *, page: int = 1):
        owner = self._require_preview_owner()
        owner_type = type(owner)
        plan = owner_type.resolve_preview_plan(keyword, custom_map=self.preview_site_kwargs().get("custom_map"))
        page = max(1, int(page or 1))
        if not plan.has_page(page):
            return []
        return await self._fetch_parse(plan.url_for_page(owner_type, page=page), plan.parse_func(owner.parser))


class TemplateUtils(Utils, Previewer):
    name = "template"
    domain = "example.com"
    index = f"https://{domain}/"
    search_url_head = f"https://{domain}/search?q="
    list_url = f"https://{domain}/list"
    headers = {}
    mappings = {res.SPIDER.Completer.index: index}
    parser = TemplateParser
    reqer_cls = TemplateReqer

    def __init__(self, _conf):
        self.reqer = self.reqer_cls(_conf)
        self.parser = self.__class__.parser

    @classmethod
    def preview_client_config(cls, **context):
        return {"headers": cls.headers}

    @classmethod
    def preview_transport_config(cls) -> dict:
        return {}

    @classmethod
    def normalize_site_resource(cls, value: str | None) -> str | None:
        return cls.normalize_preview_resource(value, domain=cls.domain)

    @classmethod
    def build_list_page_url(cls, params: dict[str, str], *, page: int) -> str:
        raise NotImplementedError

    @classmethod
    def plan_from_mapping(cls, mapping_value) -> TemplatePreviewPlan:
        url = cls.normalize_site_resource(str(mapping_value or ""))
        if not url:
            raise ValueError("template mapping URL is required")
        if url.rstrip("/") == cls.index.rstrip("/"):
            return TemplatePreviewPlan(kind="home", first_page_url=cls.index, parser_name="parse_home_books")
        return TemplatePreviewPlan(kind="list", first_page_url=url, parser_name="parse_list_books")

    @classmethod
    def search_plan(cls, keyword: str) -> TemplatePreviewPlan:
        keyword = keyword.strip()
        return TemplatePreviewPlan(
            kind="search", first_page_url=f"{cls.search_url_head}{keyword}", parser_name="parse_list_books",
            params=(("keyword", keyword),),
        )

    @classmethod
    def resolve_preview_plan(cls, keyword: str, *, custom_map: dict | None = None, **_) -> TemplatePreviewPlan:
        keyword = keyword.strip()
        mappings = cls.merge_search_mappings(cls.mappings, custom_map)
        if keyword not in mappings:
            return cls.search_plan(keyword)
        return cls.plan_from_mapping(mappings[keyword])
