from __future__ import annotations

import pathlib as p
from dataclasses import dataclass, field
from typing import Optional

from utils.config.qc import cgs_cfg
from utils.network.doh import dns_stub_endpoint, dns_stub_server, normalize_doh_url
from utils.script import conf as script_conf, folder_sub
from utils.script.motrix import build_motrix_dns_options

from .constants import (
    DANBOORU_OFFICIAL_ORDER_VALUES,
    DANBOORU_PAGE_SIZE,
    DANBOORU_SAVE_TYPE_SEARCH_TAG,
    DEFAULT_DANBOORU_SAVE_PATH,
    DEFAULT_DOWNLOAD_CONCURRENCY,
    SUPPORTED_MEDIA_EXTENSIONS,
    UNSUPPORTED_MEDIA_EXTENSIONS,
    _ORDER_TOKEN_CAPTURE_RE,
    _ORDER_TOKEN_STRIP_RE,
    _WHITESPACE_RE,
)


@dataclass(frozen=True, slots=True)
class DanbooruSearchQuery:
    term: str = ""
    order: str = ""

    @staticmethod
    def normalize(value: object) -> str:
        return _WHITESPACE_RE.sub(" ", str(value or "").strip())

    @classmethod
    def _extract_order_token(cls, term: str) -> str:
        matches = _ORDER_TOKEN_CAPTURE_RE.findall(cls.normalize(term))
        return matches[-1] if matches else ""

    @classmethod
    def _strip_order_tokens(cls, term: str) -> str:
        return cls.normalize(_ORDER_TOKEN_STRIP_RE.sub(" ", cls.normalize(term)))

    @classmethod
    def is_official_order_value(cls, order: object) -> bool:
        normalized = cls.normalize(order).removeprefix("order:")
        return normalized in DANBOORU_OFFICIAL_ORDER_VALUES

    @property
    def canonical_term(self) -> str:
        return self.normalize(self.term)

    @property
    def canonical_order(self) -> str:
        return self.normalize(self.order)

    @property
    def effective_order(self) -> str:
        return self.canonical_order or self._extract_order_token(self.canonical_term)

    @property
    def base_term(self) -> str:
        return self._strip_order_tokens(self.canonical_term)

    @property
    def folder_term(self) -> str:
        return self.base_term

    @property
    def tags(self) -> str:
        if not self.effective_order:
            return self.base_term
        order_token = self.effective_order if self.effective_order.startswith("order:") else f"order:{self.effective_order}"
        return " ".join(part for part in (self.base_term, order_token) if part)

    def params(self, *, page: int = 1, limit: Optional[int] = None) -> dict:
        return {
            "tags": self.tags,
            "page": page,
            "limit": limit or DANBOORU_PAGE_SIZE,
        }


@dataclass(slots=True)
class DanbooruPost:
    post_id: int
    md5: str
    canonical_term: str = ""
    file_url: Optional[str] = None
    large_file_url: Optional[str] = None
    preview_file_url: Optional[str] = None
    source: Optional[str] = None
    rating: Optional[str] = None
    file_ext: str = ""
    tag_string: str = ""
    tag_string_general: str = ""
    tag_string_character: str = ""
    tag_string_copyright: str = ""
    tag_string_artist: str = ""
    tag_string_meta: str = ""
    image_width: int = 0
    image_height: int = 0
    preview_width: int = 0
    preview_height: int = 0
    score: int = 0

    @staticmethod
    def normalize_file_ext(file_ext: Optional[str]) -> str:
        return str(file_ext or "").strip().lower().lstrip(".")

    @classmethod
    def is_supported_file_ext(cls, file_ext: Optional[str]) -> bool:
        return cls.normalize_file_ext(file_ext) in SUPPORTED_MEDIA_EXTENSIONS

    @classmethod
    def is_unsupported_file_ext(cls, file_ext: Optional[str]) -> bool:
        return cls.normalize_file_ext(file_ext) in UNSUPPORTED_MEDIA_EXTENSIONS

    @property
    def is_supported(self) -> bool:
        return self.is_supported_file_ext(self.file_ext)

    @property
    def filename(self) -> str:
        ext = self.normalize_file_ext(self.file_ext)
        if not ext:
            raise ValueError("file_ext is required for filename derivation")
        return f"{self.post_id}_{self.md5}.{ext}"

    @classmethod
    def from_api_payload(cls, payload: dict, canonical_term: str = "") -> "DanbooruPost":
        return cls(
            post_id=int(payload["id"]),
            md5=payload.get("md5") or "",
            canonical_term=canonical_term,
            file_url=payload.get("file_url"),
            large_file_url=payload.get("large_file_url"),
            preview_file_url=payload.get("preview_file_url"),
            source=payload.get("source"),
            rating=payload.get("rating"),
            file_ext=cls.normalize_file_ext(payload.get("file_ext")),
            tag_string=payload.get("tag_string") or "",
            tag_string_general=payload.get("tag_string_general") or "",
            tag_string_character=payload.get("tag_string_character") or "",
            tag_string_copyright=payload.get("tag_string_copyright") or "",
            tag_string_artist=payload.get("tag_string_artist") or "",
            tag_string_meta=payload.get("tag_string_meta") or "",
            image_width=int(payload.get("image_width") or 0),
            image_height=int(payload.get("image_height") or 0),
            preview_width=int(payload.get("preview_width") or 0),
            preview_height=int(payload.get("preview_height") or 0),
            score=int(payload.get("score") or 0),
        )

    def with_canonical_term(self, canonical_term: str) -> "DanbooruPost":
        self.canonical_term = DanbooruSearchQuery.normalize(canonical_term)
        return self


@dataclass(frozen=True, slots=True)
class DanbooruRuntimeConfig:
    save_path: str
    save_type: Optional[str] = None
    download_concurrency: int = DEFAULT_DOWNLOAD_CONCURRENCY
    doh_url: str = ""
    motrix_aria2_conf_path: str = ""

    def __post_init__(self):
        if self.save_type not in {None, DANBOORU_SAVE_TYPE_SEARCH_TAG}:
            raise ValueError(f"Unsupported Danbooru save_type: {self.save_type}")
        object.__setattr__(self, "save_path", str(self.save_path or DEFAULT_DANBOORU_SAVE_PATH))
        object.__setattr__(self, "download_concurrency", int(self.download_concurrency or DEFAULT_DOWNLOAD_CONCURRENCY))
        raw_doh_url = str(self.doh_url or "").strip()
        object.__setattr__(self, "doh_url", normalize_doh_url(raw_doh_url) if raw_doh_url else "")
        object.__setattr__(self, "motrix_aria2_conf_path", str(self.motrix_aria2_conf_path or "").strip())

    @classmethod
    def from_mapping(cls, raw: Optional[dict], *, doh_url: object = None) -> "DanbooruRuntimeConfig":
        data = raw or {}
        return cls(
            save_path=data.get("save_path", DEFAULT_DANBOORU_SAVE_PATH),
            save_type=data.get("save_type"),
            download_concurrency=data.get("download_concurrency", DEFAULT_DOWNLOAD_CONCURRENCY),
            doh_url=cgs_cfg.get_doh_url() if doh_url is None else doh_url,
            motrix_aria2_conf_path=data.get("motrix_aria2_conf_path", ""),
        )

    @classmethod
    def from_conf(cls) -> "DanbooruRuntimeConfig":
        return cls.from_mapping(
            getattr(script_conf, "danbooru", {}) or {},
            doh_url=cgs_cfg.get_doh_url(),
        )

    def is_doh_enabled(self) -> bool:
        return bool(self.doh_url)

    def motrix_add_uri_options(self) -> dict[str, str]:
        return build_motrix_dns_options(dns_server=self.stub_dns_server())

    def stub_dns_server(self) -> str:
        return dns_stub_server(self.doh_url)

    def stub_dns_endpoint(self) -> str:
        return dns_stub_endpoint(self.doh_url)

    def request_dns_summary(self) -> str:
        return f"DoH -> {self.doh_url}" if self.is_doh_enabled() else "系统 DNS"

    def motrix_dns_summary(self) -> str:
        return f"Motrix: async-dns-server={self.stub_dns_server()}" if self.is_doh_enabled() else "Motrix: 默认 DNS"

    def network_label(self) -> str:
        return f"请求 {self.request_dns_summary()} | {self.motrix_dns_summary()}"

    def network_tooltip(self) -> str:
        if self.is_doh_enabled():
            request_text = f"Danbooru 请求通过 dnspython DoH resolver 解析，当前端点为 {self.doh_url}。"
            motrix_text = f"Danbooru 会启动本地 DNS stub {self.stub_dns_endpoint()}，Motrix 通过 async-dns-server={self.stub_dns_server()} 使用同一上游。"
            if self.motrix_aria2_conf_path:
                motrix_text += " 设置页保存时还会同步 aria2.conf。"
            return f"{request_text}\n{motrix_text}"
        request_text = "Danbooru 请求使用系统或代理链路的默认 DNS 解析。"
        motrix_text = "Motrix 不启用 Danbooru 本地 DNS stub。"
        if self.motrix_aria2_conf_path:
            motrix_text += " 设置页保存时会清空 aria2.conf 里的 Danbooru DNS 覆写。"
        return f"{request_text}\n{motrix_text}"

    def resolve_download_path(self, post: DanbooruPost, *, base_path: Optional[str] = None) -> p.Path:
        root = p.Path(base_path or self.save_path)
        if self.save_type == DANBOORU_SAVE_TYPE_SEARCH_TAG:
            canonical_term = DanbooruSearchQuery.normalize(post.canonical_term)
            if canonical_term:
                root = root.joinpath(folder_sub.sub("-", canonical_term))
        return root.joinpath(post.filename)


@dataclass(frozen=True, slots=True)
class DanbooruAutocompleteCandidate:
    value: str
    antecedent: str = ""
    autocomplete_type: str = ""
    category: Optional[int] = None
    proper_name: str = ""
    post_count_text: str = ""

    @property
    def menu_text(self) -> str:
        display = self.antecedent or self.proper_name or self.value
        if display.casefold() != self.value.casefold():
            display = f"{display} -> {self.value}"
        if self.post_count_text:
            display = f"{display} ({self.post_count_text})"
        return display


@dataclass(slots=True)
class DanbooruAutocompleteResult:
    canonical_term: str
    matches: list[DanbooruAutocompleteCandidate] = field(default_factory=list)
    reason: Optional[str] = None

    @property
    def is_single_match(self) -> bool:
        return len(self.matches) == 1

    @property
    def has_matches(self) -> bool:
        return bool(self.matches)

    @property
    def selected_term(self) -> Optional[str]:
        return self.matches[0].value if self.is_single_match else None


@dataclass(slots=True)
class DownloadPlan:
    deduped_skipped: list[DanbooruPost] = field(default_factory=list)
    to_submit: list[DanbooruPost] = field(default_factory=list)
    failed_pre_submit: list[DanbooruPost] = field(default_factory=list)
    submission_errors: list[str] = field(default_factory=list)
