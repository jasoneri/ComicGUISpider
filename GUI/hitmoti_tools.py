import sqlite3
from contextlib import closing
import urllib.parse as up
from PyQt5.QtCore import Qt, QUrl, QTimer
from PyQt5.QtGui import QGuiApplication, QStandardItemModel, QStandardItem, QDesktopServices
from PyQt5.QtWidgets import QApplication, QSpacerItem, QSizePolicy, QHBoxLayout, QListView, QComboBox
from qfluentwidgets import (
    ComboBox, VBoxLayout, RoundMenu, Action,
    PrimaryToolButton, ToolButton, DropDownToolButton, TransparentToolButton,
    TitleLabel, StrongBodyLabel, FluentIcon as FIF,
    InfoBadgePosition, InfoBadge, ToolTipFilter, ToolTipPosition, ToolTip, 
    InfoBar, InfoBarPosition
)
from qframelesswindow import FramelessWindow

from assets import res
from variables import DEFAULT_COMPLETER
from utils import ori_path, conf


class HitomiTools(FramelessWindow):
    def __init__(self, parent=None):
        super().__init__()
        self.gui = parent
        self.titleBar.minBtn.hide()
        self.titleBar.maxBtn.hide()
        self.titleBar.closeBtn.hide()
        screen = QGuiApplication.primaryScreen()
        screen_geo = screen.geometry()
        # 计算窗口尺寸
        window_width = int(screen_geo.width() * 0.4)
        window_height = int(screen_geo.height() * 0.15)
        self.setMinimumSize(window_width, window_height)
        self.resize(window_width, window_height)
        self.move(
            int((screen_geo.width() - window_width) / 2),
            int((screen_geo.height() - window_height) / 2)
        )
        self.tmp_map = {}
        self.actual_path = ''
        self.conn = sqlite3.connect(ori_path.joinpath('assets/hitomi.db'))
        self.init_ui()
        self.set_dataset()
        self.update_entries()  # Initial update
        
    def init_ui(self):
        main_layout = VBoxLayout(self)
        
        # First row
        first_row = QHBoxLayout()
        self.category = ComboBox()
        self.category.addItems(['tag', 'artist', 'serie', 'character'])
        self.letter = ComboBox()
        self.letter.addItems(['123', *[chr(i) for i in range(97, 123)]])
        
        spacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.language = ComboBox()
        self.load_languages()
        self.language_label = StrongBodyLabel('language:')
        
        first_row.addWidget(self.category)
        first_row.addWidget(self.letter)
        first_row.addSpacerItem(spacer)
        first_row.addWidget(self.language_label)
        first_row.addWidget(self.language)
        
        # Second row
        second_row = QHBoxLayout()
        self.entry_label = StrongBodyLabel('tag:')
        self.entry = QComboBox()
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
        self.searchDownToolBtn.setToolTip(res.GUI.Uic.hitomiTools_tip_search)
        self.globe_menu = RoundMenu(parent=self)
        self.set_globe_menu()
        self.svBtn = PrimaryToolButton(FIF.SAVE)
        self.svBtn.setToolTip(res.GUI.Uic.hitomiTools_tip_sv)
        self.sendBtn = PrimaryToolButton(FIF.SEND, self)
        self.sendBtn.clicked.connect(self.send)
        self.sendBtn.setToolTip(res.GUI.Uic.hitomiTools_tip_send)
        self.cancelBtn = TransparentToolButton(FIF.CLOSE, self)
        self.cancelBtn.clicked.connect(self.close)
        tt = ToolTip('sdfadf', self.cancelBtn)
        for btn in (self.searchDownToolBtn, self.svBtn, self.sendBtn):
            btn.installEventFilter(ToolTipFilter(btn, showDelay=300, position=ToolTipPosition.TOP))

        fourth_row.addSpacerItem(spacer_info)
        fourth_row.addWidget(self.copyBtn)
        fourth_row.addWidget(self.searchDownToolBtn)
        fourth_row.addWidget(self.svBtn)
        fourth_row.addWidget(self.sendBtn)
        fourth_row.addWidget(self.cancelBtn)
        
        # Add to main layout
        main_layout.addLayout(first_row)
        main_layout.addLayout(second_row)
        main_layout.addLayout(third_row)
        main_layout.addLayout(fourth_row)
        
        # Signals
        self.category.currentTextChanged.connect(self.update_entries)
        self.letter.currentTextChanged.connect(self.update_entries)
        self.entry.currentTextChanged.connect(self.update_output)
        self.language.currentTextChanged.connect(self.update_output)
        self.copyBtn.clicked.connect(self.copy_path)
        self.svBtn.clicked.connect(self.save)

    def set_globe_menu(self):
        self.globe_menu.clear()
        sites = [
            ('https://mzh.moegirl.org/index.php?search=', '萌娘百科'),
            ('https://myanimelist.net/search/all?q=', 'MyAnimeList'),
            ('https://www.anime-planet.com/', 'Anime-Planet'),
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
        list_view = QListView()
        list_view.setUniformItemSizes(True)
        self.entry.setView(list_view)
    
    def send(self):
        self.gui.searchinput.setText(self.actual_path)
        InfoBar.success(
            title='', content=res.GUI.Uic.hitomiTools_info_sended,
            orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
            duration=4000, parent=self.gui.textBrowser
        )
        QTimer.singleShot(100, self.close)

    def copy_path(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.output.text())
        InfoBar.success(
            title='', content=res.GUI.Uic.hitomiTools_info_copied,
            orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM_LEFT,
            duration=4000, parent=self
        )
    
    def save(self):
        hitomi_completer = conf.completer.get(6, DEFAULT_COMPLETER.get(6))
        hitomi_completer.insert(0, self.actual_path)
        conf.completer[6] = hitomi_completer
        conf.update()
        InfoBar.success(
            title='', content=res.GUI.Uic.hitomiTools_info_sved,
            orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM_LEFT,
            duration=4000, parent=self
        )

    def load_languages(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT content FROM language")
        self.language.addItems([row[0] for row in cursor.fetchall()])

    def update_entries(self):
        table_name = f"all{self.category.currentText()}s-{self.letter.currentText()}"
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

    def update_output(self):
        category = self.category.currentText()
        entry = self.entry.currentText()
        lang = self.language.currentText()
        if not entry:
            return
        entry_info = self.tmp_map[entry]
        badge_value = str(entry_info[1]).zfill(5)
        if hasattr(self, 'info_badge'):
            self.info_badge.setText(badge_value)
        else:
            self.info_badge = InfoBadge.success(
                badge_value,
                parent=self,
                target=self.output_num,
                position=InfoBadgePosition.RIGHT
            )
        
        path = f"{category}/{entry}-{lang}"
        self.actual_path = f"{category}/{entry_info[0]}-{lang}"
        self.output.setText(path)
        self.set_globe_menu()


if __name__ == '__main__':
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication([])
    window = HitomiTools()
    window.show()
    app.exec_()
