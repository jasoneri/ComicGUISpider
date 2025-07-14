import time
from qfluentwidgets import QConfig, ConfigItem, qconfig
from utils.config import conf_dir


class KemonoConfig(QConfig):
    """Kemono配置管理，包含过滤和收藏功能"""
    filterText = ConfigItem("Filter", "FilterText", "", restart=False)
    favoriteAuthors = ConfigItem("Favorites", "Authors", [], restart=False)

    def is_favorite(self, author_id):
        """检查是否已收藏"""
        return author_id in self.favoriteAuthors.value

    def toggle_favorite(self, author_id):
        """切换收藏状态，返回新状态"""
        favorites = self.favoriteAuthors.value.copy()
        if author_id in favorites:
            favorites.remove(author_id)
            is_favorited = False
        else:
            favorites.append(author_id)
            is_favorited = True

        self.favoriteAuthors.value = favorites
        qconfig.save()
        return is_favorited

    def is_favorited(self, author_id):
        """检查是否已收藏"""
        return author_id in self.favoriteAuthors.value

    def get_favorites(self):
        """获取所有收藏"""
        return self.favoriteAuthors.value


kemono_cfg = KemonoConfig()
qconfig.load(conf_dir.joinpath("qc_kemono.json"), kemono_cfg)
