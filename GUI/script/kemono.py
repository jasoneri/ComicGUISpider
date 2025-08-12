import sys
import subprocess
import pathlib as p
import pickle
import typing as t
from datetime import datetime

from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QSpacerItem, QSizePolicy
from PyQt5.QtCore import Qt, QUrl, pyqtSignal, QThread, QDate, QAbstractTableModel, QModelIndex
from PyQt5.QtGui import QFont, QGuiApplication, QDesktopServices
from qfluentwidgets import (
    LineEdit, PrimaryPushButton,
    VBoxLayout, FluentIcon as FIF, ZhDatePicker, StrongBodyLabel,
    TransparentToolButton, HyperlinkButton, PushButton, PrimaryToolButton, TransparentTogglePushButton,
    TableView, FlyoutViewBase, FlyoutAnimationType, TextEdit, qconfig,
    Flyout, CommandBarView, Action, InfoBar, InfoBarPosition
)
from qframelesswindow import FramelessWindow

from deploy import curr_os
from utils import ori_path, temp_p
from utils.script.image.kemono import kemono_topic, conf, KemonoAuthor
from utils.config.qc import kemono_cfg
from GUI.core.font import font_color
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
        self.textEdit.setPlainText(kemono_cfg.filterText.value)
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
        kemono_cfg.filterText.value = self.textEdit.toPlainText()
        qconfig.save()
        self.closeBtn.click()


class VirtualKemonoTableModel(QAbstractTableModel):
    """虚拟化Kemono表格模型，用于高性能处理大量数据"""

    def __init__(self, data_dict):
        super().__init__()
        # 按收藏数降序排序，与原有逻辑保持一致
        self.authors_list = sorted(data_dict.values(), key=lambda x: x.favorited, reverse=True)
        self.filtered_indices = list(range(len(self.authors_list)))  # 用于搜索过滤
        self.headers = ["作者", "平台", "更新时间", "收藏数"]
        self.current_row_author = None  # 存储当前选中行的作者数据
        self.favorites_only_mode = False
        self.favorite_ids = []

    def rowCount(self, parent=QModelIndex()):
        return len(self.filtered_indices)

    def columnCount(self, parent=QModelIndex()):
        return 4

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.filtered_indices):
            return None

        actual_row = self.filtered_indices[index.row()]
        author = self.authors_list[actual_row]
        col = index.column()

        if role == Qt.DisplayRole:
            if col == 0:
                return author.name
            elif col == 1:
                return author.service
            elif col == 2:
                return datetime.fromtimestamp(author.updated).strftime(r'%Y-%m-%d')
            elif col == 3:
                return str(author.favorited)
        elif role == Qt.UserRole:  # 存储原始数据用于排序，与原有逻辑保持一致
            if col == 2:
                return author.updated
            elif col == 3:
                return author.favorited
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.headers[section]
        return None

    def sort(self, column, order):
        self.layoutAboutToBeChanged.emit()

        reverse = (order == Qt.DescendingOrder)

        if column == 0:  # 作者名
            self.authors_list.sort(key=lambda x: x.name, reverse=reverse)
        elif column == 1:  # 平台
            self.authors_list.sort(key=lambda x: x.service, reverse=reverse)
        elif column == 2:  # 更新时间
            self.authors_list.sort(key=lambda x: x.updated, reverse=reverse)
        elif column == 3:  # 收藏数
            self.authors_list.sort(key=lambda x: x.favorited, reverse=reverse)

        # 重新构建过滤索引
        self.update_filtered_indices()
        self.layoutChanged.emit()

    def apply_filter(self, filter_text):
        if self.favorites_only_mode:
            return
        self.beginResetModel()

        if not filter_text:
            self.filtered_indices = list(range(len(self.authors_list)))
        else:
            self.filtered_indices = []
            filter_lower = filter_text.lower()

            for i, author in enumerate(self.authors_list):
                # 搜索所有列，与原有逻辑保持一致
                if (filter_lower in author.name.lower() or
                    filter_lower in author.service.lower() or
                    filter_lower in datetime.fromtimestamp(author.updated).strftime(r'%Y-%m-%d').lower() or
                    filter_lower in str(author.favorited)):
                    self.filtered_indices.append(i)
        self.endResetModel()

    def update_filtered_indices(self):
        if len(self.filtered_indices) != len(self.authors_list):
            # 这里需要重新应用当前的过滤条件
            # 暂时重置为显示所有数据，实际使用时会通过apply_filter重新设置
            self.filtered_indices = list(range(len(self.authors_list)))

    def get_author_at_row(self, row):
        if 0 <= row < len(self.filtered_indices):
            actual_row = self.filtered_indices[row]
            return self.authors_list[actual_row]
        return None

    def show_favorites_only(self, favorite_ids):
        self.beginResetModel()
        self.favorites_only_mode = True
        self.favorite_ids = favorite_ids
        self.filtered_indices = []
        for i, author in enumerate(self.authors_list):
            if author.id in self.favorite_ids:
                self.filtered_indices.append(i)
        self.endResetModel()

    def show_all_authors(self):
        self.beginResetModel()
        self.favorites_only_mode = False
        self.favorite_ids = []

        # 恢复显示所有作者
        self.filtered_indices = list(range(len(self.authors_list)))
        self.endResetModel()


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

        window_width = int(p_width * 0.9)
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

        self.virtual_model = VirtualKemonoTableModel(data)

        self.set_table()
        self.setupUi()

    def setupUi(self):
        first_row = QHBoxLayout()
        first_row.addWidget(self.tableView)

        second_row = QHBoxLayout()
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.closeBtn = TransparentToolButton(FIF.CLOSE, self)
        self.closeBtn.clicked.connect(self.hide)
        self.searchEdit = LineEdit(self)
        self.searchEdit.setPlaceholderText("搜索...")
        self.searchEdit.textChanged.connect(self.filter_table)
        self.searchEdit.setClearButtonEnabled(True)
        self.favBtn = TransparentTogglePushButton(FIF.HEART, "查看本地收藏", self)
        self.favBtn.clicked.connect(self.toggle_favorites_view)
        second_row.addWidget(self.searchEdit)
        second_row.addWidget(self.favBtn)
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

        # 使用虚拟化模型，大幅提升性能
        self.tableView.setModel(self.virtual_model)
        self.tableView.horizontalHeader().setStretchLastSection(True)

        # 启用排序功能
        self.tableView.setSortingEnabled(True)
        self.tableView.horizontalHeader().setSortIndicatorShown(True)

        self.virtual_model.sort(3, Qt.DescendingOrder)

        # 调整列宽
        self.tableView.setColumnWidth(0, int(tb_width * 0.3))  # 作者名
        self.tableView.setColumnWidth(1, int(tb_width * 0.2))  # 服务
        self.tableView.setColumnWidth(2, int(tb_width * 0.25)) # 更新时间
        self.tableView.setColumnWidth(3, int(tb_width * 0.2))  # 收藏数

        self.tableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tableView.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        # 启用右键菜单
        self.tableView.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tableView.customContextMenuRequested.connect(self.on_right_click)

    def filter_table(self, text):
        self.virtual_model.apply_filter(text)

    def toggle_favorites_view(self):
        if self.favBtn.isChecked():
            self.searchEdit.clear()
            self.searchEdit.setDisabled(True)
            self.show_favorites_only()
        else:
            self.searchEdit.setDisabled(False)
            self.show_all_authors()

    def show_favorites_only(self):
        favorite_ids = kemono_cfg.favoriteAuthors.value
        self.virtual_model.show_favorites_only(favorite_ids)

    def show_all_authors(self):
        self.virtual_model.show_all_authors()

    def on_right_click(self, position):
        index = self.tableView.indexAt(position)
        if not index.isValid():
            return

        model_row = index.row()
        selected_author = self.virtual_model.get_author_at_row(model_row)
        if not selected_author:
            return

        self.virtual_model.current_row_author = selected_author

        commandBar = CommandBarView()
        send_action = Action(FIF.SEND, '发送至输入框')
        send_action.triggered.connect(lambda: self.send_author_to_input(selected_author))
        link_action = Action(FIF.LINK, '查看其作品')
        link_action.triggered.connect(lambda: self.open_author_link(selected_author))
        fav_action = Action(FIF.HEART, '收藏至本地')
        fav_action.triggered.connect(lambda: self.fav_author(selected_author))
        commandBar.addAction(send_action)
        commandBar.addAction(link_action)
        commandBar.addAction(fav_action)
        commandBar.resizeToSuitableWidth()

        target_pos = self.tableView.mapToGlobal(position)
        Flyout.make(commandBar, target=target_pos, parent=self, aniType=FlyoutAnimationType.FADE_IN)

    def send_author_to_input(self, author):
        self.interface.textBrowser.append(
            f"已选ID({author.id}): 作者「{author.name}」({author.service})"
        )
        self.interface.selected.append(author.id)
        self.interface.kwEdit.setText(f"creatorid={self.interface.selected}".replace("'", '"'))

    def open_author_link(self, author):
        """打开作者链接"""
        author_url = f"https://kemono.cr/{author.service}/user/{author.id}"
        QDesktopServices.openUrl(QUrl(author_url))

    def fav_author(self, author):
        is_favorited = kemono_cfg.toggle_favorite(author.id)
        action_text = "已添加收藏" if is_favorited else "已取消收藏"
        at = InfoBar.success if is_favorited else InfoBar.warning
        at(
            title="", content=f"{action_text}「{author.name}」",
            orient=Qt.Horizontal, position=InfoBarPosition.TOP,
            duration=2000, parent=self
        )


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
        self.kwEdit.setPlaceholderText("打开作者表格，对某行右键点击发送，支持多次发送叠加")
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
        self.textBrowser = TextBrowserWithBg(self)
        font = QFont()
        font.setFamily("Consolas, Monaco, 'Courier New', monospace")  # 等宽字体，支持Unicode
        font.setPointSize(10)
        self.textBrowser.setFont(font)
        fourth_row.addWidget(self.textBrowser)

        self.main_layout.addLayout(first_row)
        self.main_layout.addLayout(second_row)
        self.main_layout.addLayout(third_row)
        self.main_layout.addLayout(fourth_row)
        self.bg_mgr = BgMgr()
        if self.bg_mgr.bg_f:
            self.textBrowser.set_fixed_image(self.bg_mgr.bg_f, int(self.parent_window.height()*0.7))
        self.reset_browser()
    
    def reset_browser(self):
        self.textBrowser.clear()
        self.say(kemono_topic)
        self.say("当前仅支持作者作品集层面下载（不支持下载单个post的小操作）")
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
        
        self.say(font_color("""<br>🔔留意 Motrix 有任务开始即可<br>任务提示done后运行键会恢复，可继续接下一轮任务<br>""", 
                            cls='theme-highlight'))
        self.backend_thread = KemonoBackendThread(backend_kw, self)
        self.backend_thread.output_signal.connect(self.say)
        self.backend_thread.finished_signal.connect(self._on_kemono_finished)
        self.backend_thread.start()
        self.runBtn.setDisabled(True)

    def _on_kemono_finished(self, exit_code):
        if exit_code != 0:
            self.say(font_color("任务执行失败，退出码: {exit_code}", cls='theme-err'))

    def say(self, text):
        self.textBrowser.append(text)
        
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
        self.interface = parent
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
            self.print(font_color("✅ done!", cls='theme-success'))
        self.interface.runBtn.setEnabled(True)
        self.finished_signal.emit(exit_code)
