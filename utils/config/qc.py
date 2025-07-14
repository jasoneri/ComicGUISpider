import time
from qfluentwidgets import QConfig, ConfigItem, qconfig
from utils.config import conf_dir


class KemonoConfig(QConfig):
    """Kemono配置管理，包含过滤和收藏功能"""
    filterText = ConfigItem("Filter", "FilterText", "", restart=False)
    favoriteAuthors = ConfigItem("Favorites", "Authors", {}, restart=False)

    def add_favorite(self, author_data):
        """添加收藏"""
        favorites = self.favoriteAuthors.value
        favorites[author_data['id']] = {
            'id': author_data['id'],
            'name': author_data['name'],
            'service': author_data['service'],
            'updated': author_data['updated'],
            'favorited': author_data['favorited'],
            'favorite_time': int(time.time())
        }
        self.favoriteAuthors.value = favorites
        qconfig.save()

    def remove_favorite(self, author_id):
        """移除收藏"""
        favorites = self.favoriteAuthors.value
        if author_id in favorites:
            del favorites[author_id]
            self.favoriteAuthors.value = favorites
            qconfig.save()

    def is_favorited(self, author_id):
        """检查是否已收藏"""
        return author_id in self.favoriteAuthors.value

    def get_favorites(self):
        """获取所有收藏"""
        return self.favoriteAuthors.value


kemono_cfg = KemonoConfig()
qconfig.load(conf_dir.joinpath("qc_kemono.json"), kemono_cfg)
