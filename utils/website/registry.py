from utils import md5

site_gateway_map = {}
spider_adapter_map = {}


def resolve_site_gateway(site_key):
    gateway = site_gateway_map.get(site_key)
    if gateway is None:
        raise ValueError(f"unsupported site gateway: {site_key!r}")
    return gateway


def resolve_spider_adapter(site_key):
    adapter = spider_adapter_map.get(site_key)
    if adapter is None:
        raise ValueError(f"unsupported spider adapter: {site_key!r}")
    return adapter


class Uuid:
    """
    A class to generate spider-specific UUIDs.
    It relies on the spider adapter registry being populated at runtime.
    """
    def __init__(self, spider_name):
        self.spider = spider_name
        self.get = resolve_spider_adapter(self.spider).get_uuid

    def id_and_md5(self, info):
        # id_and_md5前端识别
        _id = self.get(info)
        return _id, md5(_id)
