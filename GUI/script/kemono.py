import sys
import subprocess
import pathlib as p
import pickle
import typing as t
from datetime import datetime

from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QSpacerItem, QSizePolicy
from PyQt5.QtCore import Qt, QUrl, pyqtSignal, QThread, QDate, QSortFilterProxyModel
from PyQt5.QtGui import QFont, QStandardItemModel, QStandardItem, QGuiApplication, QDesktopServices
from qfluentwidgets import (
    LineEdit, PrimaryPushButton,
    VBoxLayout, FluentIcon as FIF, ZhDatePicker, StrongBodyLabel,
    TransparentToolButton, TransparentPushButton, HyperlinkButton, PushButton, PrimaryToolButton,
    TableView, FlyoutViewBase, FlyoutAnimationType, TextEdit, qconfig
)
from qframelesswindow import FramelessWindow

from deploy import curr_os
from utils import ori_path, temp_p, font_color
from utils.script.image.kemono import kemono_topic, conf, KemonoAuthor
from utils.config.qc import filter_cfg
from GUI.uic.qfluent.components import TextBrowserWithBg, BgMgr, CustomFlyout


class FilterView(FlyoutViewBase):
    closed = pyqtSignal()  # 添加closed信号
    
    def __init__(self, parent=None):
        super(FilterView, self).__init__(parent)
        self.interface = parent
        self.width = int(parent.width() * 0.6)
        self.setupUi()

    def setupUi(self):
        self.layout = VBoxLayout(self)
        
        first_row = QtWidgets.QHBoxLayout()
        self.textEdit = TextEdit(self)
        self.textEdit.setPlaceholderText("基于示例，格式严格遵循yml，过滤方式为正则匹配")
        self.textEdit.setPlainText(filter_cfg.filterText.value)
        first_row.addWidget(self.textEdit)
        
        second_row = QtWidgets.QHBoxLayout()
        self.linkBtn = HyperlinkButton(FIF.LINK, "https://jasoneri.github.io/ComicGUISpider/feat/script.html#%F0%9F%9A%80-%E5%BF%AB%E9%80%9F%E5%BC%80%E5%A7%8B", "查看示例", self)
        spacerItem = QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.svBtn = PrimaryToolButton(FIF.SAVE, self)
        self.svBtn.clicked.connect(self.save)
        self.closeBtn = TransparentToolButton(FIF.CLOSE, self)
        self.closeBtn.clicked.connect(self.closed)
        second_row.addWidget(self.linkBtn)
        second_row.addItem(spacerItem)
        second_row.addWidget(self.svBtn)
        second_row.addWidget(self.closeBtn)

        self.layout.addLayout(first_row)
        self.layout.addLayout(second_row)
        self.setFixedWidth(self.width)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)

    def save(self):
        filter_cfg.filterText.value = self.textEdit.toPlainText()
        qconfig.save()
        self.closeBtn.click()


class CustomSortFilterProxyModel(QSortFilterProxyModel):
    def lessThan(self, left, right):
        left_column = left.column()

        # 对于更新时间列(索引2)和收藏数列(索引3)，使用存储的原始数据进行比较
        if left_column in [2, 3]:
            left_data = self.sourceModel().data(left, Qt.UserRole)
            right_data = self.sourceModel().data(right, Qt.UserRole)

            # 确保数据类型正确
            if left_data is not None and right_data is not None:
                try:
                    return float(left_data) < float(right_data)
                except (ValueError, TypeError):
                    pass

        # 对于其他列，使用默认的字符串比较
        return super().lessThan(left, right)


class KemonoTableView(FramelessWindow):
    """Kemono作者表格视图"""
    closed = pyqtSignal()

    def __init__(self, data: t.Dict[str, KemonoAuthor], parent=None):
        super().__init__()
        self.interface = parent
        self._table_initialized = False  # 标记表格是否已初始化

        # 隐藏标题栏按钮
        self.titleBar.minBtn.hide()
        self.titleBar.maxBtn.hide()
        self.titleBar.closeBtn.hide()

        # 计算窗口大小
        if parent:
            p_width = parent.width()
            p_height = parent.height()
        else:
            screen = QGuiApplication.primaryScreen()
            screen_geo = screen.geometry()
            p_width = screen_geo.width()
            p_height = screen_geo.height()

        window_width = int(p_width * 0.8)
        window_height = int(p_height * 0.7)

        self.resize(window_width, window_height)
        screen = QGuiApplication.primaryScreen()
        screen_geo = screen.geometry()
        self.move(
            int((screen_geo.width() - window_width) / 2),
            int((screen_geo.height() - window_height) / 2)
        )

        self.layout = VBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        authors_list = sorted(data.values(), key=lambda x: x.favorited, reverse=True)
        self.data = {i: author for i, author in enumerate(authors_list)}

        self.set_table()
        first_row = QHBoxLayout()
        first_row.addWidget(self.tableView)

        second_row = QHBoxLayout()
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.closeBtn = TransparentToolButton(FIF.CLOSE, self)
        self.closeBtn.clicked.connect(self.hide)
        selectBtn = PrimaryPushButton(FIF.SEND, "将所选行发送到输入框", self)
        selectBtn.clicked.connect(self.select_author)
        self.searchEdit = LineEdit(self)
        self.searchEdit.setPlaceholderText("搜索作者...")
        self.searchEdit.textChanged.connect(self.filter_table)
        self.searchEdit.setClearButtonEnabled(True)
        linkBtn = TransparentPushButton(FIF.LINK, "查看所选作品", self)
        linkBtn.clicked.connect(self.link_author)
        second_row.addWidget(selectBtn)
        second_row.addWidget(self.searchEdit)
        second_row.addWidget(linkBtn)
        second_row.addItem(spacerItem)
        second_row.addWidget(self.closeBtn)

        self.layout.addLayout(first_row)
        self.layout.addLayout(second_row)
        
    def set_table(self):
        self.tableView = TableView(self)
        self.tableView.setBorderRadius(15)
        self.tableView.setWordWrap(False)
        tb_width = self.width()
        tb_height = self.height() - 60  # 为搜索框留出空间
        self.tableView.setFixedSize(tb_width, tb_height)
        self.tableView.verticalHeader().hide()

        # 设置数据模型
        self.source_model = QStandardItemModel()
        self.source_model.setHorizontalHeaderLabels(["作者", "平台", "更新时间", "收藏数"])

        # 按行索引顺序遍历数据
        for row_index in sorted(self.data.keys()):
            item = self.data[row_index]
            # 创建表格项
            name_item = QStandardItem(item.name)
            service_item = QStandardItem(item.service)

            # 更新时间项 - 存储时间戳用于排序，显示格式化日期
            updated_timestamp = item.updated
            updated_date = datetime.fromtimestamp(updated_timestamp).strftime(r'%Y-%m-%d')
            date_item = QStandardItem(updated_date)
            date_item.setData(updated_timestamp, Qt.UserRole)  # 存储原始时间戳用于排序

            # 收藏数项 - 存储数值用于排序
            favorited_count = item.favorited
            favorited_item = QStandardItem(str(favorited_count))
            favorited_item.setData(favorited_count, Qt.UserRole)  # 存储原始数值用于排序

            row = [name_item, service_item, date_item, favorited_item]
            self.source_model.appendRow(row)

        # 创建自定义筛选代理模型
        self.proxy_model = CustomSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.source_model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)  # 搜索所有列

        self.tableView.setModel(self.proxy_model)
        self.tableView.horizontalHeader().setStretchLastSection(True)

        # 启用排序功能
        self.tableView.setSortingEnabled(True)
        self.tableView.horizontalHeader().setSortIndicatorShown(True)

        # 设置默认排序：按收藏数降序排列
        self.proxy_model.sort(3, Qt.DescendingOrder)

        # 调整列宽
        self.tableView.setColumnWidth(0, int(tb_width * 0.3))  # 作者名
        self.tableView.setColumnWidth(1, int(tb_width * 0.2))  # 服务
        self.tableView.setColumnWidth(2, int(tb_width * 0.25)) # 更新时间
        self.tableView.setColumnWidth(3, int(tb_width * 0.2))  # 收藏数

        self.tableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tableView.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

    def filter_table(self, text):
        """筛选表格数据"""
        self.proxy_model.setFilterRegExp(text)

    def select_author(self):
        """选择作者功能"""
        selection = self.tableView.selectionModel().selectedRows()
        if not selection:
            return

        # 获取选中行的数据（需要通过代理模型映射到源模型）
        proxy_row = selection[0].row()
        proxy_index = self.proxy_model.index(proxy_row, 0)
        source_index = self.proxy_model.mapToSource(proxy_index)
        source_row = source_index.row()

        # 直接通过行索引获取对应的KemonoAuthor对象
        selected_author = self.data.get(source_row)
        self.interface.kemonoTextBrowser.append(
            f"已选ID({selected_author.id}): 作者「{selected_author.name}」({selected_author.service})"
        )
        self.interface.selected.append(selected_author.id)
        self.interface.kwEdit.setText(f"creatorid={self.interface.selected}".replace("'", '"'))
        self.closed.emit()

    def link_author(self):
        author_url = "https://kemono.su"
        selection = self.tableView.selectionModel().selectedRows()
        if selection:
            proxy_row = selection[0].row()
            proxy_index = self.proxy_model.index(proxy_row, 0)
            source_index = self.proxy_model.mapToSource(proxy_index)
            source_row = source_index.row()
            selected_author = self.data.get(source_row)
            author_url = f"{author_url}/{selected_author.service}/user/{selected_author.id}"
        QDesktopServices.openUrl(QUrl(author_url))


class KemonoInterface(QFrame):
    """Kemono界面Widget类"""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.parent_window = parent
        self.backend_thread = None
        self.table_inited = False
        self.selected = []
        self.setObjectName("KemonoInterface")
        self.setupUi()

    def setupUi(self):
        self.main_layout = VBoxLayout(self)

        first_row = QHBoxLayout()
        self.kwEdit = LineEdit(self)
        self.kwEdit.setPlaceholderText("输入样例：creatorid=[1234,4321] 推荐使用作者表格方式输入，支持多次发送叠加")
        self.kwEdit.setClearButtonEnabled(True)
        self.eraseBtn = TransparentToolButton(FIF.ERASE_TOOL, self)
        self.eraseBtn.clicked.connect(self.erase_selected)
        self.showTbBtn = PushButton(FIF.BOOK_SHELF, "作者表格", self)
        self.showTbBtn.clicked.connect(self.show_kemono_table)
        first_row.addWidget(self.kwEdit)
        first_row.addWidget(self.eraseBtn)
        first_row.addWidget(self.showTbBtn)

        second_row = QHBoxLayout()
        startDateLabel = StrongBodyLabel("开始", self)
        self.startDateEdit = ZhDatePicker(self)
        endDateLabel = StrongBodyLabel("结束", self)
        self.endDateEdit = ZhDatePicker(self)
        spacerItem2 = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.startDateEdit.setDate(QDate(2025, 1, 1))
        self.endDateEdit.setDate(QDate(2045, 1, 1))
        self.extraFilterBtn = PushButton(FIF.FILTER, "额外过滤", self)
        self.extraFilterBtn.clicked.connect(self.show_extra_filter)
        second_row.addWidget(startDateLabel)
        second_row.addWidget(self.startDateEdit)
        second_row.addWidget(endDateLabel)
        second_row.addWidget(self.endDateEdit)
        second_row.addWidget(self.extraFilterBtn)
        second_row.addItem(spacerItem2)

        third_row = QHBoxLayout()
        self.runBtn = PrimaryPushButton(FIF.PLAY, "运行", self)
        self.runBtn.clicked.connect(self.run_kemono)
        self.openBtn = TransparentToolButton(FIF.FOLDER, self)
        def open_sv_path():
            curr_os.open_folder(p.Path(conf.kemono.get('sv_path')))
        self.openBtn.clicked.connect(open_sv_path)
        third_row.addWidget(self.runBtn)
        third_row.addWidget(self.openBtn)

        fourth_row = QHBoxLayout()
        self.kemonoTextBrowser = TextBrowserWithBg(self)
        font = QFont()
        font.setFamily("Consolas, Monaco, 'Courier New', monospace")  # 等宽字体，支持Unicode
        font.setPointSize(10)
        self.kemonoTextBrowser.setFont(font)
        fourth_row.addWidget(self.kemonoTextBrowser)

        self.main_layout.addLayout(first_row)
        self.main_layout.addLayout(second_row)
        self.main_layout.addLayout(third_row)
        self.main_layout.addLayout(fourth_row)
        self.bg_mgr = BgMgr()
        if self.bg_mgr.bg_f:
            self.kemonoTextBrowser.set_fixed_image(self.bg_mgr.bg_f, int(self.parent_window.height()*0.7))
        self.reset_browser()
    
    def reset_browser(self):
        self.kemonoTextBrowser.clear()
        self.say(kemono_topic)
        self.say("<hr><p></p>")

    def _get_backend_kw(self):
        if not self.selected:
            return None
        
        start_date = self.startDateEdit.getDate().toString("yyyy-MM-dd")
        end_date = self.endDateEdit.getDate().toString("yyyy-MM-dd")
        filter_ckw = {"start_date": start_date,"end_date": end_date}
        backend_kw = {**{"creatorid": self.selected}, **filter_ckw}
        return backend_kw

    def run_kemono(self):
        backend_kw = self._get_backend_kw()
        if not backend_kw:
            self.say("input empty")
            return
        
        self.say(font_color("\n🔔留意 Motrix 有任务开始即可", color="orange"))
        self.backend_thread = KemonoBackendThread(backend_kw, self)
        self.backend_thread.output_signal.connect(self.say)
        self.backend_thread.finished_signal.connect(self._on_kemono_finished)
        self.backend_thread.start()

    def _on_kemono_finished(self, exit_code):
        if exit_code != 0:
            self.say(font_color("任务执行失败，退出码: {exit_code}", color="red"))

    def say(self, text):
        self.kemonoTextBrowser.append(text)
        
    def erase_selected(self):
        self.selected = []
        self.kwEdit.setText("")
        self.reset_browser()

    def show_extra_filter(self):
        CustomFlyout.make(
            view=FilterView(self), target=self.extraFilterBtn, parent=self,
            aniType=FlyoutAnimationType.SLIDE_LEFT
        )

    def show_kemono_table(self):
        if not self.table_inited:
            self._set_kemono_table()
            self.table_inited = True
        self.table_window.show()

    def _set_kemono_table(self):
        with open(temp_p.joinpath("kemono_data.pkl"), 'rb') as f:
            data = pickle.load(f)
        self.table_window = KemonoTableView(data, self)
        self.table_window.closeBtn.clicked.connect(self.table_window.close)
        self.table_window.closed.connect(self.table_window.hide)


class KemonoBackendThread(QThread):
    output_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(int)  # 添加完成信号，传递退出码

    def __init__(self, backend_kw, parent=None):
        super().__init__(parent)
        self.backend_kw = backend_kw

    def print(self, *args, **kwargs):
        self.output_signal.emit(*args, **kwargs)

    def run(self):
        script_path = ori_path.joinpath("utils/script/image/kemono.py")

        args = []
        args.extend(["-c", f"creatorid={self.backend_kw['creatorid']}".replace("'", '"')])
        args.extend(["-sd", self.backend_kw.get("start_date"),"-ed", self.backend_kw.get("end_date")])

        cmd = [sys.executable, str(script_path)] + args
        self.output_signal.emit(f"🎯cmd: {cmd}")
        process = subprocess.Popen(
            cmd, cwd=ori_path,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, universal_newlines=True
        )
        while True:
            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    break  # 进程结束且无输出时退出
                continue
            line = line.strip()
            self.print(line)
        remaining = process.stdout.read()
        if remaining:
            for line in remaining.splitlines():
                cleaned_line = line.strip()
                self.print(cleaned_line)
        exit_code = process.wait()
        if exit_code == 0:
            self.print(font_color("✅ done!", color="green"))

        self.finished_signal.emit(exit_code)
