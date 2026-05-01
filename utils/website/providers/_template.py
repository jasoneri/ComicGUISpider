"""Provider template for new owner-bound site implementations.

Copy this file, rename the classes, then only fill the site-specific hooks.
Do not import GUI classes or runtime-only side effects here.
"""

from utils.website.core import PreviewRequestSpec, Previewer, Req, Utils


class TemplateParser(Previewer):
    @classmethod
    def parse_preview_search_response(cls, text: str, spec: PreviewRequestSpec) -> list:
        raise NotImplementedError


class TemplateReqer(Req):
    def __init__(self, _conf):
        self.cli = self.get_cli(_conf)

    async def preview_search(self, keyword: str, *, page: int = 1):
        owner = self._require_preview_owner()
        owner_type = type(owner)
        site_kw = self.preview_site_kwargs()
        spec = owner_type.build_preview_search_request(
            keyword,
            page=max(1, int(page or 1)),
            **site_kw,
        )
        resp = await owner_type.perform_preview_request(self.ensure_preview_client(), spec)
        return await owner.parser.parse_preview_search_response(resp.text, spec)


class TemplateUtils(Utils, Previewer):
    name = "template"
    domain = "example.com"
    index = f"https://{domain}"
    search_url_head = f"https://{domain}/search?q="
    headers = {}
    mappings = {}
    turn_page_info = None
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
    def build_preview_search_request(
        cls,
        keyword: str,
        *,
        page: int = 1,
        domain: str,
        custom_map: dict | None = None,
        **_,
    ) -> PreviewRequestSpec:
        return cls.build_basic_search_request(
            keyword,
            page=page,
            domain=domain,
            search_url_head=cls.search_url_head,
            turn_page_info=cls.turn_page_info,
            mappings=cls.mappings,
            custom_map=custom_map,
            headers=cls.headers,
        )
