from qfluentwidgets import QConfig, ConfigItem, qconfig
from utils.config import conf_dir


class FilterConfig(QConfig):
    filterText = ConfigItem("Filter", "FilterText", "", restart=False)


filter_cfg = FilterConfig()
qconfig.load(conf_dir.joinpath("qc.json"), filter_cfg)
