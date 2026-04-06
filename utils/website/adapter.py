from __future__ import annotations

from dataclasses import dataclass, field
import typing as t

from utils import conf


@dataclass(slots=True)
class SpiderAdapterSession:
    adapter: "ProviderSpiderAdapter"
    conf_state: t.Any = field(default_factory=lambda: conf)
    _runtime: t.Any = field(default=None, init=False, repr=False)

    @property
    def runtime(self):
        if self._runtime is None:
            self._runtime = self.adapter.create_runtime(self.conf_state)
        return self._runtime

    @property
    def provider_cls(self):
        return self.adapter.provider_cls

    @property
    def reqer(self):
        return getattr(self.runtime, "reqer", self.runtime)

    @property
    def parser(self):
        return getattr(self.runtime, "parser", self.runtime)

    @property
    def reqer_cls(self):
        return getattr(self.provider_cls, "reqer_cls", None)

    def get_uuid(self, *args, **kwargs):
        return self.adapter.get_uuid(*args, **kwargs)

    def get_cli(self, conf_state=None, *, is_async: bool = False, **kwargs):
        conf_state = self.conf_state if conf_state is None else conf_state
        return self.reqer.get_cli(conf_state, is_async=is_async, **kwargs)

    def build_search_url(self, keyword):
        return self.reqer.build_search_url(keyword)

    def parse_search(self, resp_text):
        return self.parser.parse_search(resp_text)

    def parse_book(self, resp_text):
        return self.parser.parse_book(resp_text)

    def resolve_domain(self):
        if hasattr(self.reqer, "get_domain"):
            return self.reqer.get_domain()
        return self.adapter.resolve_domain()


class ProviderSpiderAdapter:
    def __init__(self, provider_cls):
        self.provider_cls = provider_cls

    @property
    def name(self) -> str:
        return getattr(self.provider_cls, "name", "")

    @property
    def index(self):
        return getattr(self.provider_cls, "index", None)

    def create_runtime(self, conf_state=conf):
        return self.provider_cls(conf_state)

    def create_session(self, conf_state=conf) -> SpiderAdapterSession:
        return SpiderAdapterSession(self, conf_state)

    def get_uuid(self, *args, **kwargs):
        return self.provider_cls.get_uuid(*args, **kwargs)

    def resolve_domain(self):
        if hasattr(self.provider_cls, "get_domain"):
            return self.provider_cls.get_domain()
        return getattr(self.provider_cls, "domain", None)

    def build_search_request(self, keyword, *, conf_state=conf):
        return self.create_session(conf_state).build_search_url(keyword)

    def build_search_url(self, keyword, *, conf_state=conf):
        return self.build_search_request(keyword, conf_state=conf_state)

    def parse_search(self, resp_text, *, conf_state=conf):
        return self.create_session(conf_state).parse_search(resp_text)

    def parse_book(self, resp_text, *, conf_state=conf):
        return self.create_session(conf_state).parse_book(resp_text)
