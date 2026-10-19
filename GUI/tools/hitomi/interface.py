# -*- coding: utf-8 -*-
"""hitomiTool 页面：筛选条件 + tag 表 + 动作栏。

控件映射：
- category / sub_ / orderby / orderbyKeyDate / orderbyKeyPopular（2~5 单选）→ SegmentedWidget
- letter(27) / language(44) 单选 → chip 单行 + SingleDirectionScrollArea 横滚
- entry（大数据量）→ TableView 常驻表，列 [tag, num]，行点击即选中
- 输出区：_ElidedLabel 路径（中间省略 + tooltip）+ muted 计数，置于 HitomiActionBar

sqlite 连接随页面 closeEvent 关闭，由宿主调 ``dispose()``。
"""
from __future__ import annotations

import sqlite3
import urllib.parse as up
from contextlib import closing

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    BodyLabel,
    DropDownToolButton,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    PillPushButton,
    PrimaryToolButton,
    RoundMenu,
    SegmentedWidget,
    SingleDirectionScrollArea,
    SubtitleLabel,
    TableView,
    ToolButton,
    ToolTipFilter,
    ToolTipPosition,
    TransparentToolButton,
    TransparentTogglePushButton,
    TransparentToggleToolButton,
)

from assets import res
from GUI.core.timer import safe_single_shot
from utils import conf
from utils.website.preprocess import site_db_path
from variables import DEFAULT_COMPLETER, Spider

# 与 workspace 挂页门同源（utils.website.preprocess.site_db_path 为路径单一事实源）。
HITOMI_DB_PATH = site_db_path("hitomi")

_LETTERS = ('123', *[chr(i) for i in range(97, 123)])
_LANGUAGES = (
    'all', 'indonesian', 'javanese', 'catalan', 'cebuano', 'czech', 'danish', 'german', 'estonian', 'english',
    'spanish', 'esperanto', 'french', 'hindi', 'icelandic', 'italian', 'latin', 'hungarian', 'dutch', 'norwegian',
    'polish', 'portuguese', 'romanian', 'albanian', 'slovak', 'serbian', 'finnish', 'swedish', 'tagalog', 'vietnamese',
    'turkish', 'greek', 'bulgarian', 'mongolian', 'russian', 'ukrainian', 'hebrew', 'arabic', 'persian', 'thai',
    'burmese', 'korean', 'chinese', 'japanese',
)


class _SegmentGroup(QWidget):
    """2~5 项互斥单选：SegmentedWidget 封装，``current`` 即当前选项文本。"""

    changed = Signal(str)

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.seg = SegmentedWidget(self)
        for opt in options:
            self.seg.addItem(routeKey=opt, text=opt, onClick=lambda _c=False, _t=opt: self.changed.emit(_t))
        # SegmentedWidget 无自动首项（currentRouteKey 默认 ''），显式置首项为当前。
        self.seg.setCurrentItem(options[0])
        lay.addWidget(self.seg)

    @property
    def current(self) -> str:
        return self.seg.currentRouteKey()


class _ChipGroup(QWidget):
    """单行 chip 条：按钮自然宽（不夹字形）、QButtonGroup 互斥，横滚交宿主滚动区。"""

    changed = Signal(str)

    def __init__(self, options, parent=None, chip_height=28, button_cls=PillPushButton):
        super().__init__(parent)
        self._buttons: dict = {}
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        for opt in options:
            btn = button_cls(opt, self)
            btn.setCheckable(True)
            btn.setFixedHeight(chip_height)
            btn.clicked.connect(lambda _c=False, _t=opt: self.changed.emit(_t))
            self.group.addButton(btn)
            lay.addWidget(btn)
            self._buttons[opt] = btn
        if options:
            self._buttons[options[0]].setChecked(True)
        self.adjustSize()

    @property
    def current(self) -> str:
        for text, btn in self._buttons.items():
            if btn.isChecked():
                return text
        return ""


class _ElidedLabel(SubtitleLabel):
    """中间省略的单行标签：全文进 tooltip，宽度变化时重省略，最小宽 0 不撑页。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def setFullText(self, text: str) -> None:
        self._full = text or ""
        self.setToolTip(self._full)
        self._apply_elide()

    def _apply_elide(self) -> None:
        self.setText(self.fontMetrics().elidedText(
            self._full, Qt.TextElideMode.ElideMiddle, max(30, self.width())))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_elide()

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        return QSize(0, hint.height())


class HitomiInterface(QWidget):
    """hitomiTool pivot 页（objectName ``htInterface``）。"""

    def __init__(self, gui, parent=None, *, host_window=None):
        super().__init__(parent)
        self.gui = gui
        # 必须先于 init_ui：init_ui → set_globe_menu / update_entries 链路在构造阶段就会读 _selected_tag。
        self._selected_tag = ""
        self.removed_flag = False
        self.category_type_flag = False
        self.order_flag = False
        self.tmp_map = {}
        self.output_mgr = self.OutputMgr(self)
        self.conn = sqlite3.connect(HITOMI_DB_PATH)
        self.setObjectName("htInterface")
        # 动作后关窗宿主：send 完关闭工作区壳。
        self.host_window = host_window or parent
        self.init_ui()
        self.set_dataset()
        self.update_entries()

    # ------------------------------------------------------------------ ui

    def init_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(8)
        self.main_layout = main

        # ---- 筛选卡 ----
        self.filter_card = QFrame(self)
        self.filter_card.setObjectName("HitomiFilterCard")
        # 竖向 Fixed：remove 模式隐藏表格后，页级富余空间不得灌进筛选卡。
        self.filter_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        card = QVBoxLayout(self.filter_card)
        card.setContentsMargins(12, 10, 12, 10)
        card.setSpacing(8)

        # category：5 单选
        self.category = _SegmentGroup(('tag', 'artist', 'series', 'character', 'type'), self.filter_card)
        self.category.changed.connect(self.category_changed)
        card.addWidget(self.category)

        # letter 行：27 chip 单行横滚（category=type 时整行隐藏让位 sub_）
        self.letter_row = QWidget(self.filter_card)
        letter_lay = QVBoxLayout(self.letter_row)
        letter_lay.setContentsMargins(0, 0, 0, 0)
        self.letter = _ChipGroup(_LETTERS, chip_height=28, button_cls=TransparentTogglePushButton)
        self.letter_scroll = SingleDirectionScrollArea(self.letter_row, orient=Qt.Orientation.Horizontal)
        self.letter_scroll.setObjectName("HitomiLetterScroll")
        self.letter_scroll.setWidgetResizable(False)
        self.letter_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.letter_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.letter_scroll.enableTransparentBackground()
        self.letter_scroll.setFixedHeight(44)
        self.letter_scroll.setWidget(self.letter)
        self.letter.changed.connect(self.update_entries)
        letter_lay.addWidget(self.letter_scroll)
        card.addWidget(self.letter_row)

        # sub_ 行：5 单选，仅 category=type 可见
        self.sub_ = _SegmentGroup(('imageset', 'manga', 'doujinshi', 'artistcg', 'gamecg'), self.filter_card)
        self.sub_.changed.connect(self.update_output)
        self.sub_.setVisible(False)
        card.addWidget(self.sub_)

        # order toggle 行：两图标 toggle 右对齐
        self.removeBtn = TransparentToggleToolButton(FIF.REMOVE_FROM, self.filter_card)
        self.removeBtn.setToolTip(res.GUI.Tools.hitomi_tip_remove)
        self.removeBtn.clicked.connect(self.toggle_remove)
        self.orderbyBtn = TransparentToggleToolButton(FIF.SCROLL, self.filter_card)
        self.orderbyBtn.setToolTip(res.GUI.Tools.hitomi_tip_orderby)
        self.orderbyBtn.clicked.connect(self.toggle_orderby)
        self.orderby = _SegmentGroup(('date', 'popular'), self.filter_card)
        self.orderby.changed.connect(self.orderby_change)
        self.orderbyKeyDate = _SegmentGroup(('published', 'added/index'), self.filter_card)
        self.orderbyKeyDate.changed.connect(self.update_output)
        self.orderbyKeyPopular = _SegmentGroup(('today', 'week', 'month', 'year'), self.filter_card)
        self.orderbyKeyPopular.changed.connect(self.update_output)
        order_row = QHBoxLayout()
        order_row.setContentsMargins(0, 0, 0, 0)
        order_row.addStretch(1)
        order_row.addWidget(self.removeBtn)
        order_row.addWidget(self.orderbyBtn)
        for w in (self.orderby, self.orderbyKeyDate, self.orderbyKeyPopular):
            w.setVisible(False)
            order_row.addWidget(w)
        card.addLayout(order_row)

        # 分隔线
        self.divider = QFrame(self.filter_card)
        self.divider.setObjectName("HitomiDivider")
        self.divider.setFixedHeight(1)
        card.addWidget(self.divider)

        # language 行：44 chip 单行横滚
        self.language_row = QWidget(self.filter_card)
        lang_lay = QHBoxLayout(self.language_row)
        lang_lay.setContentsMargins(0, 0, 0, 0)
        self.language_icon = TransparentToolButton(FIF.LANGUAGE, self.language_row)
        self.language_icon.setDisabled(True)
        lang_lay.addWidget(self.language_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        self.language = _ChipGroup(_LANGUAGES, chip_height=28)
        self.language_scroll = SingleDirectionScrollArea(self.language_row, orient=Qt.Orientation.Horizontal)
        self.language_scroll.setObjectName("HitomiLangScroll")
        self.language_scroll.setWidgetResizable(False)
        self.language_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.language_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.language_scroll.enableTransparentBackground()
        self.language_scroll.setFixedHeight(44)
        self.language_scroll.setWidget(self.language)
        self.language.changed.connect(self.update_output)
        lang_lay.addWidget(self.language_scroll, 1)
        card.addWidget(self.language_row)

        main.addWidget(self.filter_card)

        # ---- entry：常驻表 [tag, num]，行点击即选中 ----
        self.entry_table = TableView(self)
        self.entry_table.setBorderRadius(10)
        self.entry_table.setWordWrap(False)
        self.entry_table.verticalHeader().hide()
        self.entry_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.entry_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.entry_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.entry_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.entry_table.setSortingEnabled(True)
        self.entry_table.clicked.connect(self._on_entry_clicked)
        main.addWidget(self.entry_table, 1)
        # remove 模式（表格隐藏）时由 filler 接管富余空间，动作栏保持贴底。
        self.tail_filler = QWidget(self)
        main.addWidget(self.tail_filler, 0)

        # ---- 动作栏 ----
        self.action_bar = QFrame(self)
        self.action_bar.setObjectName("HitomiActionBar")
        bar = QHBoxLayout(self.action_bar)
        bar.setContentsMargins(12, 8, 12, 8)
        bar.setSpacing(6)

        self.output = _ElidedLabel(self.action_bar)
        self.output.setObjectName("HitomiOutputPath")
        self.output.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        # Ignored 尺寸策略下 smartSizeHint=0，须配 stretch 1 才可见。
        bar.addWidget(self.output, 1)
        col_box = QVBoxLayout()
        col_box.setContentsMargins(0, 0, 0, 0)
        col_box.setSpacing(6)
        bar.addLayout(col_box)
        self.output_count = BodyLabel(' ', self.action_bar)
        self.output_count.setObjectName("HitomiOutputCount")
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.addStretch(1)
        row1.addWidget(self.output_count)

        self.copyBtn = ToolButton(FIF.COPY)
        self.copyBtn.clicked.connect(self.copy_path)
        self.searchDownToolBtn = DropDownToolButton(FIF.SEARCH)
        self.searchDownToolBtn.setToolTip(res.GUI.Tools.hitomi_tip_search)
        self.globe_menu = RoundMenu(parent=self)
        self.set_globe_menu()
        self.svBtn = PrimaryToolButton(FIF.SAVE)
        self.svBtn.setToolTip(res.GUI.Tools.hitomi_tip_sv)
        self.svBtn.clicked.connect(self.save)
        self.sendBtn = PrimaryToolButton(FIF.SEND, self)
        self.sendBtn.setToolTip(res.GUI.Tools.hitomi_tip_send)
        self.sendBtn.clicked.connect(self.send)
        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.addStretch(1)
        for btn in (self.copyBtn, self.searchDownToolBtn, self.svBtn, self.sendBtn):
            row2.addWidget(btn)
        col_box.addLayout(row1)
        col_box.addLayout(row2)

        main.addWidget(self.action_bar)

        for btn in (self.removeBtn, self.orderbyBtn, self.searchDownToolBtn, self.svBtn, self.sendBtn):
            btn.installEventFilter(ToolTipFilter(btn, showDelay=300, position=ToolTipPosition.TOP))

    def set_dataset(self):
        """初始化查询与模型缓存（key = ``all<category>-<letter>`` 表名）。"""
        self.query_cache: dict = {}
        self.model_cache: dict = {}

    # ------------------------------------------------------------- 数据/交互

    def update_entries(self):
        _category = self.category.current
        category = f"{_category}s" if _category != 'series' else _category
        table_name = f"all{category}-{self.letter.current}"
        if table_name in self.model_cache:
            self._set_entry_model(self.model_cache[table_name], self.query_cache[table_name])
            return
        if table_name in self.query_cache:
            self.tmp_map = self.query_cache[table_name]
        else:
            with closing(self.conn.cursor()) as cursor:
                cursor.execute(f"SELECT content, num FROM `{table_name}`")
                entries = cursor.fetchall()  # content, num
            self.tmp_map = {up.unquote(entry[0]): entry for entry in entries}
            self.query_cache[table_name] = self.tmp_map

        model = self._build_entry_model(self.tmp_map)
        self.model_cache[table_name] = model
        self._set_entry_model(model, self.tmp_map)

    @staticmethod
    def _build_entry_model(tmp_map):
        """构建 [tag, num] 常驻表模型。

        num 必须以整数存入 DisplayRole：点 num 列头才按数值排序（存字符串会排成
        99,974,9292,91,9）。整数型 DisplayRole 仍由委托渲染为数字文本。
        """
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(["tag", "num"])
        for entry in tmp_map:
            tag_item = QStandardItem(entry)
            num_item = QStandardItem()
            num_item.setData(tmp_map[entry][1], Qt.ItemDataRole.DisplayRole)
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            model.appendRow((tag_item, num_item))
        return model

    def _configure_columns(self):
        header = self.entry_table.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        # num 列按内容自适应：固定宽会截断四五位数计数。
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

    def _set_entry_model(self, model, tmp_map):
        self.tmp_map = tmp_map
        self.entry_table.setModel(model)
        self._configure_columns()
        self._selected_tag = ""
        first = model.index(0, 0)
        if first.isValid():
            self._on_entry_clicked(first)

    def _on_entry_clicked(self, index):
        if not index.isValid():
            return
        self._selected_tag = index.data(Qt.ItemDataRole.DisplayRole) or ""
        self.update_output()

    def category_changed(self):
        self.category_type_flag = self.category.current == 'type'
        self._sync_filter_visibility()
        if self.category_type_flag:
            self.update_output()
        else:
            self.update_entries()

    def _sync_filter_visibility(self):
        """按 category 决定 letter/sub_/entry 可见性：type → sub_，否则 → letter + entry。"""
        is_type = self.category_type_flag
        self.sub_.setVisible(is_type)
        self.letter_row.setVisible(not is_type)
        self.entry_table.setVisible(not is_type)

    def toggle_remove(self):
        if self.removeBtn.isChecked():
            for w in (self.category, self.letter_row, self.sub_, self.entry_table, self.searchDownToolBtn):
                w.setVisible(False)
            self.main_layout.setStretch(self.main_layout.indexOf(self.tail_filler), 1)
            self.removed_flag = True
            if not self.orderbyBtn.isChecked():
                self.orderbyBtn.click()
            self.orderbyBtn.setDisabled(True)
        else:
            self.orderbyBtn.setDisabled(False)
            self.category.setVisible(True)
            self.searchDownToolBtn.setVisible(True)
            self._sync_filter_visibility()
            self.main_layout.setStretch(self.main_layout.indexOf(self.tail_filler), 0)
            self.removed_flag = False
        self.update_output()

    def toggle_orderby(self):
        if self.orderbyBtn.isChecked():
            self.orderby.setVisible(True)
            self._sync_orderby_key()
            self.order_flag = True
        else:
            for w in (self.orderby, self.orderbyKeyDate, self.orderbyKeyPopular):
                w.setVisible(False)
            self.order_flag = False
        self.update_output()

    def orderby_change(self):
        self._sync_orderby_key()
        self.update_output()

    def _sync_orderby_key(self):
        is_date = self.orderby.current == 'date'
        self.orderbyKeyDate.setVisible(is_date)
        self.orderbyKeyPopular.setVisible(not is_date)

    def send(self):
        self.gui.searchinput.setText(self.output_mgr.actual)
        InfoBar.success(
            title='', content=res.GUI.Tools.hitomi_info_sended,
            orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
            duration=4000, parent=self.gui.showArea
        )
        safe_single_shot(100, self.host_window.close)

    def copy_path(self):
        QApplication.clipboard().setText(self.output.text())
        InfoBar.success(
            title='', content=res.GUI.Tools.hitomi_info_copied,
            orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM_LEFT,
            duration=4000, parent=self
        )

    def save(self):
        """把当前输出路径写进 hitomi 站点的补全预设（置顶去重后落盘）。"""
        hitomi_completer = conf.completer.get(Spider.HITOMI, DEFAULT_COMPLETER.get(Spider.HITOMI))
        if self.output_mgr.actual in hitomi_completer:
            hitomi_completer.remove(self.output_mgr.actual)
        hitomi_completer.insert(0, self.output_mgr.actual)
        conf.completer[Spider.HITOMI] = hitomi_completer
        conf.update()
        InfoBar.success(
            title='', content=res.GUI.Tools.hitomi_info_sved,
            orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM_LEFT,
            duration=4000, parent=self
        )

    def set_globe_menu(self):
        self.globe_menu.clear()
        sites = [
            ('https://mzh.moegirl.org/index.php?search=', '萌娘百科'),
            ('https://myanimelist.net/search/all?q=', 'MyAnimeList'),
            ('https://www.anime-planet.com/', 'Anime-Planet'),
            ('https://danbooru.donmai.us/posts?tags=', 'Danbooru'),
            ('https://rule34.xxx/index.php?page=post&s=list&tags=', 'Rule34'),
        ]
        if self.category.current == 'artist':
            sites = [
                ('https://www.pixiv.net/search/users?s_mode=usr&nick=', 'Pixiv'),
                ('https://danbooru.donmai.us/posts?tags=', 'Danbooru'),
                ('https://rule34.xxx/index.php?page=post&s=list&tags=', 'Rule34'),
            ]
        for site, name in sites:
            entry = self._selected_tag
            current_site = site
            if entry and name != 'Anime-Planet':
                current_site = site + entry
            self.globe_menu.addAction(
                Action(name, triggered=lambda _, s=current_site: QDesktopServices.openUrl(QUrl(s)))
            )
        self.searchDownToolBtn.setMenu(self.globe_menu)

    def update_output(self):
        self.output_mgr.update()
        self.output.setFullText(self.output_mgr.path)
        self.set_globe_menu()

    # ------------------------------------------------------------- 输出组装

    class OutputMgr:
        """组装输出路径与计数；tag 来源 = 表中选中行。"""

        def __init__(self, parent):
            self.ht = parent
            self.path = ''
            self.actual = ''

        def update(self):
            ht = self.ht
            area = ht.category.current
            entry = ht._selected_tag
            tag = ''
            lang = ht.language.current
            badge_value = '-------'

            if ht.removed_flag:
                ...
            elif ht.category_type_flag:
                tag = ht.sub_.current
            elif not entry:
                return
            else:
                entry_info = ht.tmp_map[entry]
                badge_value = str(entry_info[1])
                tag = entry

            output_l = [area, '-'.join((tag, lang))]
            if ht.order_flag:
                orderby = ht.orderby.current
                orderbykey = ht.orderbyKeyDate.current if orderby == 'date' else \
                    ht.orderbyKeyPopular.current

                if orderbykey == 'added/index':
                    if not tag:
                        tag = 'index'   # Priority first
                        output_l = ['-'.join((tag, lang))]
                    else:
                        output_l = [area, '-'.join((tag, lang))]
                elif ht.removed_flag:
                    tag = orderbykey
                    area = orderby
                    output_l = [area, '-'.join((tag, lang))]
                else:
                    output_l = [area, orderby, orderbykey, '-'.join((tag, lang))]

            self.path = '/'.join(output_l)
            actual_tag = ht.tmp_map[tag][0] if tag in ht.tmp_map else tag
            self.actual = '/'.join((*output_l[:-1], '-'.join((actual_tag, lang))))
            ht.output_count.setText(badge_value)

    # ------------------------------------------------------------- 生命周期

    def dispose(self) -> None:
        """关闭 sqlite 连接。"""
        self.conn.close()
