from utils import md5


spider_utils_map = {}

class Uuid:
    """
    A class to generate spider-specific UUIDs.
    It relies on the spider_utils_map being populated at runtime.
    """
    def __init__(self, spider_name):
        self.spider = spider_name
        self.get = getattr(spider_utils_map[self.spider], 'get_uuid')

    def id_and_md5(self, info):
        # id_and_md5前端识别
        _id = self.get(info)
        return _id, md5(_id)
