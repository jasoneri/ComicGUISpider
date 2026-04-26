from __future__ import annotations

from utils import conf, md5

from .site_runtime import GuiSiteRuntime, ProviderDescriptor, SpiderSiteRuntime

ProviderKey = int | str

provider_descriptor_map: dict[ProviderKey, ProviderDescriptor] = {}
provider_descriptor_spider_map: dict[str, ProviderDescriptor] = {}


def clear_provider_descriptors():
    provider_descriptor_map.clear()
    provider_descriptor_spider_map.clear()


def _register_unique(mapping: dict, key, descriptor: ProviderDescriptor, *, label: str):
    existing = mapping.get(key)
    if existing is not None and existing is not descriptor:
        raise ValueError(
            f"conflicting provider descriptor {label}: key={key!r} "
            f"existing={existing.provider_cls.__name__} new={descriptor.provider_cls.__name__}"
        )
    mapping[key] = descriptor


def register_provider_descriptor(site_key: ProviderKey, descriptor: ProviderDescriptor):
    _register_unique(provider_descriptor_map, site_key, descriptor, label="site key")


def register_provider_spider_alias(spider_name: str, descriptor: ProviderDescriptor):
    normalized = str(spider_name or "").strip()
    if not normalized:
        raise ValueError("spider alias is required")
    _register_unique(provider_descriptor_spider_map, normalized, descriptor, label="spider alias")


def resolve_provider_descriptor_by_site(site_key: ProviderKey) -> ProviderDescriptor:
    descriptor = provider_descriptor_map.get(site_key)
    if descriptor is None:
        raise ValueError(f"unsupported provider descriptor: {site_key!r}")
    return descriptor


def resolve_provider_descriptor_by_spider(spider_name: str) -> ProviderDescriptor:
    descriptor = provider_descriptor_spider_map.get(spider_name)
    if descriptor is None:
        raise ValueError(f"unsupported provider descriptor spider: {spider_name!r}")
    return descriptor


def create_gui_site_runtime(
    site_key: ProviderKey,
    *,
    snapshot=None,
    conf_state=conf,
    default_doh_url: str | None = None,
) -> GuiSiteRuntime:
    descriptor = resolve_provider_descriptor_by_site(site_key)
    site_index = site_key if isinstance(site_key, int) else descriptor.site_index
    if site_index is None:
        raise ValueError(f"provider descriptor does not expose numeric site index: {site_key!r}")
    return GuiSiteRuntime.create(
        descriptor, site_index=site_index, snapshot=snapshot, conf_state=conf_state, default_doh_url=default_doh_url
    )


def create_spider_site_runtime(spider_name, conf_state=conf) -> SpiderSiteRuntime:
    descriptor = resolve_provider_descriptor_by_spider(spider_name)
    return SpiderSiteRuntime(descriptor, conf_state=conf_state)


class Uuid:
    """
    Generate provider-specific UUIDs from the descriptor registry.
    """
    def __init__(self, provider_key: ProviderKey):
        self.provider_key = provider_key
        self.get = resolve_provider_descriptor_by_site(self.provider_key).get_uuid

    def id_and_md5(self, info):
        # id_and_md5前端识别
        _id = self.get(info)
        return _id, md5(_id)
