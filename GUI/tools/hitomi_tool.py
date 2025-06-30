import sqlite3
from contextlib import closing
import urllib.parse as up
from PyQt5.QtCore import Qt, QUrl, QTimer
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QDesktopServices
from PyQt5.QtWidgets import QApplication, QSpacerItem, QSizePolicy, QHBoxLayout, QComboBox, QFrame, QWidget
from qfluentwidgets import (
    ComboBox, VBoxLayout, RoundMenu, Action,
    PrimaryToolButton, ToolButton, DropDownToolButton, 
    TransparentToggleToolButton, TransparentTogglePushButton,
    TitleLabel, StrongBodyLabel, FluentIcon as FIF,
    InfoBadgePosition, InfoBadge, ToolTipFilter, ToolTipPosition, 
    InfoBar, InfoBarPosition, ListView
)

from assets import res
from variables import DEFAULT_COMPLETER
from utils import ori_path, conf

hitomi_db_path = ori_path.joinpath("assets/hitomi.db")


class CustomComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._list_view = None
        
    def setView(self, view):
        self._list_view = view
        super().setView(view)

    def eventFilter(self, obj, event):
        if obj == self._list_view and (event.type() == event.MouseButtonPress or event.type() == event.MouseButtonRelease):
            viewport = self._list_view.viewport()
            if event.pos().x() > viewport.width() - self._list_view.verticalScrollBar().width():
                return True
        return super().eventFilter(obj, event)


class HitomiTools(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.gui = parent
        self.removed_flag = False
        self.category_type_flag = False
        self.order_flag = False
        self.output_type = ''
        self.output_mgr = self.OutputMgr(self)
        self.tmp_map = {}
        self.conn = sqlite3.connect(ori_path.joinpath('assets/hitomi.db'))
        self.init_ui()
        self.set_dataset()
        self.update_entries()  # Initial update
        
    def init_ui(self):
        main_layout = VBoxLayout(self)
        
        # First row
        first_row = QHBoxLayout()
        self.category = ComboBox()
        self.category.addItems(('tag', 'artist', 'series', 'character', 'type'))
        self.letter = ComboBox()
        self.letter.addItems(('123', *[chr(i) for i in range(97, 123)]))
        self.sub_ = ComboBox()
        self.sub_.addItems(('imageset', 'manga', 'doujinshi', 'artistcg', 'gamecg'))
        
        self.removeBtn = TransparentToggleToolButton(FIF.REMOVE_FROM)
        self.removeBtn.setToolTip(res.GUI.Tools.hitomi_tip_remove)
        self.line = QFrame(self)
        self.line.setFrameShape(QFrame.VLine)
        self.line.setFrameShadow(QFrame.Sunken)
        self.orderbyBtn = TransparentTogglePushButton(FIF.SCROLL, 'OrderBy')
        self.orderby = ComboBox()
        self.orderby.addItems(('date', 'popular'))
        self.orderby.setToolTip(res.GUI.Tools.hitomi_tip_orderby)
        self.orderbyKeyDate = ComboBox()
        self.orderbyKeyDate.addItems(('published', 'added/index'))
        self.orderbyKeyPopular = ComboBox()
        self.orderbyKeyPopular.addItems(('today', 'week', 'month', 'year'))
        
        spacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.language_label = StrongBodyLabel('language:')
        self.language = ComboBox()
        self.language.addItems(('all','indonesian','javanese','catalan','cebuano','czech','danish','german','estonian','english',
                                'spanish','esperanto','french','hindi','icelandic','italian','latin','hungarian','dutch','norwegian',
                                'polish','portuguese','romanian','albanian','slovak','serbian','finnish','swedish','tagalog','vietnamese',
                                'turkish','greek','bulgarian','mongolian','russian','ukrainian','hebrew','arabic','persian','thai',
                                'burmese','korean','chinese','japanese'))
        for _ in (self.sub_, self.orderby, self.orderbyKeyDate, self.orderbyKeyPopular):
            _.hide()
        first_row_els = (self.category, self.letter, self.sub_, self.removeBtn, self.line, 
                         self.orderbyBtn, self.orderby, self.orderbyKeyDate, self.orderbyKeyPopular,
                         self.language_label, self.language)
        for _ in first_row_els:
            first_row.addWidget(_)
        first_row.insertSpacerItem(len(first_row_els)-2, spacer)
        
        # Second row
        second_row = QHBoxLayout()
        self.entry_label = StrongBodyLabel('tag:')
        self.entry = CustomComboBox()
        self.entry.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        second_row.addWidget(self.entry_label)
        second_row.addWidget(self.entry)
        
        # Third row
        third_row = QHBoxLayout()
        self.output_num = TitleLabel(' ')
        self.output_num.setMinimumWidth(40)
        self.output_num.setAlignment(Qt.AlignCenter)
        self.output = TitleLabel()
        self.output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.output.setAlignment(Qt.AlignCenter)
        
        third_row.addWidget(self.output_num)
        third_row.addWidget(self.output)
        
        # Fourth_row
        spacer_info = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        fourth_row = QHBoxLayout()
        self.copyBtn = ToolButton(FIF.COPY)
        self.searchDownToolBtn = DropDownToolButton(FIF.SEARCH)
        self.searchDownToolBtn.setToolTip(res.GUI.Tools.hitomi_tip_search)
        self.globe_menu = RoundMenu(parent=self)
        self.set_globe_menu()
        self.svBtn = PrimaryToolButton(FIF.SAVE)
        self.svBtn.setToolTip(res.GUI.Tools.hitomi_tip_sv)
        self.sendBtn = PrimaryToolButton(FIF.SEND, self)
        self.sendBtn.clicked.connect(self.send)
        self.sendBtn.setToolTip(res.GUI.Tools.hitomi_tip_send)

        fourth_row.addSpacerItem(spacer_info)
        for _ in (self.copyBtn, self.searchDownToolBtn, self.svBtn, self.sendBtn):
            fourth_row.addWidget(_)
        
        # Add to main layout
        for _ in (first_row, second_row, third_row, fourth_row):
            main_layout.addLayout(_)
        
        for btn in (self.removeBtn, self.orderby,
                self.searchDownToolBtn, self.svBtn, self.sendBtn):
            btn.installEventFilter(ToolTipFilter(btn, showDelay=300, position=ToolTipPosition.TOP))

        # Signals
        self.category.currentTextChanged.connect(self.category_changed)
        self.letter.currentTextChanged.connect(self.update_entries)
        self.sub_.currentTextChanged.connect(self.update_output)
        self.removeBtn.clicked.connect(self.toggle_remove)
        self.orderbyBtn.clicked.connect(self.toggle_orderby)
        self.orderby.currentTextChanged.connect(self.orderby_change)
        self.orderbyKeyDate.currentTextChanged.connect(self.update_output)
        self.orderbyKeyPopular.currentTextChanged.connect(self.update_output)
        self.language.currentTextChanged.connect(self.update_output)
        self.entry.currentTextChanged.connect(self.update_output)
        self.copyBtn.clicked.connect(self.copy_path)
        self.svBtn.clicked.connect(self.save)

    def set_globe_menu(self):
        self.globe_menu.clear()
        sites = [
            ('https://mzh.moegirl.org/index.php?search=', '萌娘百科'),
            ('https://myanimelist.net/search/all?q=', 'MyAnimeList'),
            ('https://www.anime-planet.com/', 'Anime-Planet'),
            ('https://danbooru.donmai.us/posts?tags=', 'Danbooru'),
            ('https://rule34.xxx/index.php?page=post&s=list&tags=', 'Rule34'),
        ]
        if self.category.currentText() == 'artist':
            sites = [
                ('https://www.pixiv.net/search/users?s_mode=s_usr&nick=', 'Pixiv'),
                ('https://danbooru.donmai.us/posts?tags=', 'Danbooru'),
                ('https://rule34.xxx/index.php?page=post&s=list&tags=', 'Rule34'),
            ]
        for site, name in sites:
            entry = self.entry.currentText()
            current_site = site
            if entry and name != 'Anime-Planet':
                current_site = site + entry 
            self.globe_menu.addAction(
                Action(name, triggered=lambda _, s=current_site: QDesktopServices.openUrl(QUrl(s)))
            )
        self.searchDownToolBtn.setMenu(self.globe_menu)

    def set_dataset(self):
        self.query_cache = {}
        self.model_cache = {}
        self.list_view = ListView()
        self.entry.setView(self.list_view)
        self.list_view.installEventFilter(self.entry)
    
    def toggle_remove(self):
        """ban category/letter/sub_selector"""
        widgets = (self.category, self.letter, self.sub_, self.entry, self.searchDownToolBtn)
        if self.removeBtn.isChecked():
            for widget in widgets:
                widget.hide()
            self.removed_flag = True
            if not self.orderbyBtn.isChecked():
                self.orderbyBtn.click()
            self.orderbyBtn.setDisabled(True)
        else:
            self.orderbyBtn.setDisabled(False)
            for widget in widgets:
                widget.show()
            self.removed_flag = False
            if self.category.currentText() == 'type':
                self.letter.hide()
            else:
                self.sub_.hide()
        self.update_output()
    
    def toggle_orderby(self):
        if self.orderbyBtn.isChecked():
            self.orderby.show()
            self.orderby_change()
            self.order_flag = True
        else:
            for _ in (self.orderby, self.orderbyKeyDate, self.orderbyKeyPopular):
                _.hide()
            self.order_flag = False
        self.update_output()
    
    def orderby_change(self):
        if self.orderby.currentText() == 'popular':
            self.orderbyKeyDate.hide()
            self.orderbyKeyPopular.show()
        else:
            self.orderbyKeyDate.show()
            self.orderbyKeyPopular.hide()
        self.update_output()
        
    def send(self):
        self.gui.searchinput.setText(self.output_mgr.actual)
        InfoBar.success(
            title='', content=res.GUI.Tools.hitomi_info_sended,
            orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
            duration=4000, parent=self.gui.textBrowser
        )
        QTimer.singleShot(100, self.gui.toolWin.close)

    def copy_path(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.output.text())
        InfoBar.success(
            title='', content=res.GUI.Tools.hitomi_info_copied,
            orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM_LEFT,
            duration=4000, parent=self
        )
    
    def save(self):
        hitomi_completer = conf.completer.get(6, DEFAULT_COMPLETER.get(6))
        if self.output_mgr.actual in hitomi_completer:
            hitomi_completer.remove(self.output_mgr.actual)
        hitomi_completer.insert(0, self.output_mgr.actual)
        conf.completer[6] = hitomi_completer
        conf.update()
        InfoBar.success(
            title='', content=res.GUI.Tools.hitomi_info_sved,
            orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM_LEFT,
            duration=4000, parent=self
        )

    def category_changed(self):
        match self.category.currentText():
            case 'type':
                for _ in (self.letter, self.entry):
                    _.hide()
                self.sub_.show()
                self.category_type_flag = True
                self.update_output()
            case _:
                self.sub_.hide()
                for _ in (self.letter, self.entry):
                    _.show()
                self.category_type_flag = False
                self.update_entries()

    def update_entries(self):
        _category = self.category.currentText()
        category = f"{_category}s" if _category != 'series' else _category
        table_name = f"all{category}-{self.letter.currentText()}"
        if table_name in self.model_cache:
            self.entry.setModel(self.model_cache[table_name])
            return
        if table_name in self.query_cache:
            self.tmp_map = self.query_cache[table_name]
        else:
            with closing(self.conn.cursor()) as cursor:
                cursor.execute(f"SELECT content, num FROM `{table_name}`")
                entries = cursor.fetchall()  # content, num
            self.entry.clear()
            self.tmp_map = {up.unquote(entry[0]): entry for entry in entries}
            self.query_cache[table_name] = self.tmp_map
        
        model = QStandardItemModel()    # self.entry.addItems is too slow! temp use model instead
        for entry in self.tmp_map.keys():
            item = QStandardItem(entry)
            item.setData(entry, role=Qt.UserRole)
            model.appendRow(item)
        self.entry.setModel(model)
        self.model_cache[table_name] = model

    class OutputMgr:
        info_badge = None
        
        def __init__(self, parent):
            self.ht = parent
            self.path = ''
            self.actual = ''
        
        def update(self):
            area = self.ht.category.currentText()
            entry = self.ht.entry.currentText()
            tag = ''
            lang = self.ht.language.currentText()
            badge_value = '-------'
            
            if self.ht.removed_flag:
                ...
            elif self.ht.category_type_flag:
                tag = self.ht.sub_.currentText()
            elif not entry:
                return
            else:
                entry_info = self.ht.tmp_map[entry]
                badge_value = str(entry_info[1]).zfill(5)
                tag = entry

            output_l = [area, '-'.join((tag, lang))]
            if self.ht.order_flag:
                orderby = self.ht.orderby.currentText()
                orderbykey = self.ht.orderbyKeyDate.currentText() if orderby == 'date' else \
                    self.ht.orderbyKeyPopular.currentText()
                
                if orderbykey == 'added/index':
                    if not tag:
                        tag = 'index'   # Priority first
                        output_l = ['-'.join((tag, lang))]
                    else:
                        output_l = [area, '-'.join((tag, lang))]
                elif self.ht.removed_flag:
                    tag = orderbykey
                    area = orderby
                    output_l = [area, '-'.join((tag, lang))]
                else:
                    output_l = [area, orderby, orderbykey, '-'.join((tag, lang))]
            
            self.path = '/'.join(output_l)
            actual_tag = self.ht.tmp_map[tag][0] if tag in self.ht.tmp_map else tag
            self.actual = '/'.join((*output_l[:-1], '-'.join((actual_tag, lang))))
            
            if getattr(self, 'info_badge', None):
                self.info_badge.setText(badge_value)
            else:
                self.info_badge = InfoBadge.success(
                    badge_value,
                    parent=self.ht,
                    target=self.ht.output_num,
                    position=InfoBadgePosition.RIGHT
                )

    def update_output(self):
        self.output_mgr.update()        
        self.output.setText(self.output_mgr.path)
        self.set_globe_menu()
