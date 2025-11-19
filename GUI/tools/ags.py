import importlib
from dataclasses import dataclass
from typing import Optional
from PyQt5 import QtWidgets
from PyQt5.QtCore import QUrl, Qt, QTimer, QSize
from PyQt5.QtGui import QPixmap, QDesktopServices
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QWidget, QFileDialog
from qfluentwidgets import (
    VBoxLayout, PrimaryPushButton, PushButton, PrimaryToolButton,
    SmoothScrollArea,TeachingTip,TeachingTipTailPosition,
    FluentIcon as FIF, InfoBar, InfoBarIcon, InfoBarPosition,
    LineEdit, TransparentToggleToolButton, TransparentToolButton, ImageLabel,
    ToolTipFilter, ToolTipPosition, BodyLabel
)

from assets import res as ori_res
from utils import conf
from utils.ags import Extractor, parse, SearchKey

ags_res = ori_res.GUI.Ags
methods = Extractor.get_available_methods()


@dataclass
class DisplayConfig:
    image_path: str
    is_centered: bool
    text: str = ""


class PicMgr:
    IMAGE_HEIGHT_RATIO = 0.35  # 图片高度占窗口高度的比例
    TEXT_MARGIN = 10  # 文字与图片的间距
    
    def __init__(self, view):
        self.view = view
        self.image_label: Optional[ImageLabel] = None
        self.text_label: Optional[BodyLabel] = None
        self.display_cfg: DisplayConfig = None

    def set_success(self):
        self._clear_widgets()

    def set_empty(self):
        cfg = DisplayConfig(
            image_path=":/ags/empty.png", is_centered=True, text=ags_res.empty_input2select
        )
        self.display_cfg = cfg
        self._show_display()

    def set_guide(self):
        cfg = DisplayConfig(
            image_path=":/ags/guide.png", is_centered=False, text=ags_res.guide_message
        )
        cfg.height_ratio = 0.45
        self.display_cfg = cfg
        self._show_display()

    def _clear_widgets(self):
        for widget in [self.image_label, self.text_label]:
            if widget:
                try:
                    widget.setParent(None)
                    widget.deleteLater()
                except RuntimeError:
                    pass
        self.image_label = None
        self.text_label = None

    def _show_display(self):
        self._clear_widgets()

        parent = self._get_or_create_scroll_widget()
        pixmap = self._load_pixmap(self.display_cfg.image_path)
        if not pixmap:
            return

        self.image_label = self._create_image_label(parent, pixmap)
        QTimer.singleShot(0, self._apply_layout)

    def _get_or_create_scroll_widget(self) -> QWidget:
        scroll_widget = self.view.selectScrollingRegion.widget()
        if not scroll_widget:
            scroll_widget = QWidget()
            scroll_widget.setStyleSheet("QWidget {background-color: transparent;}")
            self.view.selectScrollingRegion.setWidget(scroll_widget)
        return scroll_widget

    def _load_pixmap(self, image_path: str) -> Optional[QPixmap]:
        pixmap = QPixmap(image_path)
        return pixmap if not pixmap.isNull() else None

    def _create_image_label(self, parent: QWidget, pixmap: QPixmap) -> ImageLabel:
        label = ImageLabel(parent)
        label.setScaledContents(True)
        label.setImage(pixmap)
        label.lower()
        return label

    def _create_text_label(self, parent: QWidget, text: str, is_centered: bool) -> BodyLabel:
        label = BodyLabel(text, parent)
        label.setAlignment(Qt.AlignCenter if is_centered else Qt.AlignLeft)
        if is_centered:
            scroll_width = self.view.selectScrollingRegion.width()
            label.setFixedWidth(scroll_width)
        return label

    def _calculate_image_size(self, pixmap: QPixmap) -> QSize:
        tool_window = self.view.window()
        if hasattr(self.display_cfg, "height_ratio"):
            height_ratio = self.display_cfg.height_ratio
        else:
            height_ratio = self.IMAGE_HEIGHT_RATIO
        target_height = int(tool_window.height() * height_ratio)
        target_width = int(target_height * pixmap.width() / pixmap.height())
        return QSize(target_width, target_height)

    def _calculate_layout_positions(self, image_size: QSize, is_centered: bool,
                                    has_text: bool) -> dict:
        scroll_area = self.view.selectScrollingRegion
        scroll_width = scroll_area.width()
        scroll_height = scroll_area.height()

        img_width = image_size.width()
        img_height = image_size.height()
        if is_centered:
            img_x = (scroll_width - img_width) // 2
            if has_text:
                text_height = self.text_label.fontMetrics().height() if self.text_label else 0
                total_height = img_height + self.TEXT_MARGIN + text_height
                img_y = (scroll_height - total_height) // 2
                text_x = 0
                text_y = img_y + img_height + self.TEXT_MARGIN
            else:
                img_y = (scroll_height - img_height) // 2
                text_x = text_y = 0
        else:
            img_x = img_y = 0
            text_x = 0
            text_y = img_height + self.TEXT_MARGIN if has_text else 0

        return {
            'image_pos': (img_x, img_y),
            'text_pos': (text_x, text_y)
        }

    def _apply_layout(self):
        if not self.image_label:
            return
        pixmap = self.image_label.pixmap()
        if not pixmap or pixmap.isNull():
            return
        parent = self.image_label.parent()
        if not parent:
            return
        # 1. 计算图片尺寸并设置
        image_size = self._calculate_image_size(pixmap)
        self.image_label.setFixedSize(image_size)
        # 2. 创建文字标签（如果需要）
        if self.display_cfg.text:
            self.text_label = self._create_text_label(parent, self.display_cfg.text, self.display_cfg.is_centered)
        # 3. 计算位置
        positions = self._calculate_layout_positions(
            image_size,
            self.display_cfg.is_centered,
            bool(self.display_cfg.text)
        )
        # 4. 应用位置
        self.image_label.move(*positions['image_pos'])
        if self.text_label:
            self.text_label.move(*positions['text_pos'])
            self.text_label.show()

        self.image_label.show()


class AgsFromFileLayout(QHBoxLayout):
    def __init__(self, parent=None):
        super().__init__()
        self.view = parent
        self.gui = parent.gui
        self.extractor = Extractor()
        self.init_ui()

    def init_ui(self):
        self.fileSet = TransparentToolButton(FIF.FOLDER)
        self.fileSet.clicked.connect(self._onSelectFile)
        self.fromFileBtn = PushButton(f"from {ags_res.file_label}", self.view)
        self.fromFileBtn.clicked.connect(self._onLoadFromFile)
        self.addWidget(self.fileSet)
        self.addWidget(self.fromFileBtn)

    def _onSelectFile(self):
        file, _ = QFileDialog.getOpenFileName(
            self.view, ags_res.select_file_dialog_title, "", "Text Files (*.txt);;All Files (*)"
        )
        if file:
            conf.update(ags_file=file)
            self.fromFileBtn.setEnabled(True)
            TeachingTip.create(
                target=self.fileSet, title='', icon=InfoBarIcon.SUCCESS,
                content=f"{ags_res.set_file_success}:\n{file}",
                tailPosition=TeachingTipTailPosition.TOP_LEFT,
                duration=5000, parent=self.fromFileBtn
            )

    def _onLoadFromFile(self):
        if conf.ags_file.name == "":
            TeachingTip.create(
                target=self.fromFileBtn, title='', isClosable=False,
                content=ags_res.set_file_first,
                tailPosition=TeachingTipTailPosition.LEFT,
                duration=2000, parent=self.fromFileBtn
            )
            return
        try:
            content_obj = self.extractor.change_file(conf.ags_file).load()  # extractor 初始化没设 file，在读时统一处理 change_file
            def make_search_tasks_from_file(text):
                return content_obj.extracted
            self.view.set_select(make_search_tasks_func=make_search_tasks_from_file)
        except Exception as e:
            InfoBar.error(
                title='', content=f"{ags_res.load_fail}: {str(e)}",
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
                duration=-1, parent=self.view
            )


class AggrSearchView(QWidget):
    def __init__(self, parent=None):
        QWidget.__init__(self)
        self.gui = parent
        self.pic_mgr = PicMgr(self)
        self.init_ui()

    def init_ui(self):
        self.main_layout = VBoxLayout(self)

        first_row = QHBoxLayout()
        self.inputBtnLayout = QtWidgets.QVBoxLayout()
        self.selection_widgets = []
        self.set_inputBtn()
        
        selectLayout = QtWidgets.QVBoxLayout()
        self.selectScrollingRegion = SmoothScrollArea()
        self.selectScrollingRegion.setWidgetResizable(True)
        selectLayout.addWidget(self.selectScrollingRegion)
        
        first_row.addLayout(self.inputBtnLayout)
        first_row.addLayout(selectLayout)

        second_row = QHBoxLayout()
        self.runBtn = PrimaryPushButton(FIF.PLAY, ags_res.run_btn, self)
        self.runBtn.clicked.connect(self.run)
        self.runBtn.setDisabled(1)
        second_row.addWidget(self.runBtn)

        for row in (first_row, second_row):
            self.main_layout.addLayout(row)
        self.setLayout(self.main_layout)
        self.pic_mgr.set_guide()

    def set_inputBtn(self):
        self.fileLayout = AgsFromFileLayout(self)
        self.inputBtnLayout.addLayout(self.fileLayout)
        extractor_module = importlib.import_module('utils.ags.extractor')
        for method in methods:
            btn = PushButton(f"from {method}", self)
            _func = getattr(extractor_module, method)
            btn.clicked.connect(lambda checked, func=_func: self.set_select(make_search_tasks_func=func))
            self.inputBtnLayout.addWidget(btn)
        
        extendLayout = QHBoxLayout()
        agsDocBtn = PrimaryToolButton(FIF.QUESTION)
        agsDocBtn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://jasoneri.github.io/ComicGUISpider/feat/ags')))
        extendBtn = PushButton(FIF.ADD, ags_res.extend_btn, self)
        extendBtn.setDisabled(1)
        extendLayout.addWidget(agsDocBtn)
        extendLayout.addWidget(extendBtn)
        
        self.inputBtnLayout.addLayout(extendLayout)
        self.inputBtnLayout.addItem(QtWidgets.QSpacerItem(10, 10, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding))

    def set_select(self, make_search_tasks_func):
        self.selection_widgets = []
        scroll_content_widget = QWidget()
        content_layout = QtWidgets.QVBoxLayout(scroll_content_widget)
        content_layout.setAlignment(Qt.AlignTop)
        def add_select(search_key):
            row_widget = QWidget(scroll_content_widget)
            row = QHBoxLayout(row_widget)
            toggleBtn = TransparentToggleToolButton(FIF.ACCEPT_MEDIUM, row_widget)
            toggleBtn.setChecked(1)
            resetBtn = TransparentToolButton(FIF.CANCEL, row_widget)
            resetBtn.setToolTip(ags_res.reset_input)
            resetBtn.installEventFilter(ToolTipFilter(resetBtn, showDelay=300, position=ToolTipPosition.TOP))
            edit = LineEdit(row_widget)
            edit.group_idx = search_key.group_idx
            edit.setText(parse(search_key))
            edit.setClearButtonEnabled(True)
            resetBtn.clicked.connect(lambda: edit.setText(search_key))
            for _ in (toggleBtn, edit, resetBtn):
                row.addWidget(_)
            content_layout.addWidget(row_widget)
            self.selection_widgets.append((toggleBtn, edit))
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        skeys = [SearchKey(_, i) for i, _ in enumerate(make_search_tasks_func(text))]
        for _ in skeys:
            add_select(_)

        self.selectScrollingRegion.setWidget(scroll_content_widget)
        if self.selection_widgets:
            self.pic_mgr.set_success()
            self.runBtn.setEnabled(1)
        else:
            self.pic_mgr.set_empty()

    def get_select(self):
        selected_texts = []
        for toggleBtn, edit in self.selection_widgets:
            if toggleBtn.isChecked() and edit.text():
                selected_texts.append(SearchKey(edit.text(), edit.group_idx))
        return selected_texts

    def run(self):
        selected_items = self.get_select()
        print(selected_items)
        self.gui.ags_mgr.extractor = self.fileLayout.extractor  # 传递 extractor 引用给 manager
        self.gui.ags_mgr.run(selected_items)
        self.gui.toolWin.close()
