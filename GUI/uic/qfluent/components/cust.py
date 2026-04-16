import typing as t
from enum import Enum
from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import QApplication, QSizePolicy
from PySide6.QtCore import Qt, QUrl, Signal, QSize
from GUI.core.timer import safe_single_shot
from PySide6.QtGui import QStandardItemModel, QStandardItem, QDesktopServices, QBrush, QPixmap, QImageReader, QImage, QMovie
from PySide6.QtWidgets import QWidget, QHBoxLayout, QGraphicsView, QGraphicsScene, QCompleter

from qfluentwidgets import (
    TransparentToolButton, HyperlinkButton, PrimaryPushButton, 
    FluentIcon, FluentIconBase, Theme, LineEdit, LineEditButton,
    VBoxLayout, Flyout, FlyoutAnimationType, FlyoutViewBase, TableView,
    InfoBar, InfoBarIcon, InfoBarPosition, IndeterminateProgressBar, BodyLabel,
    TeachingTip, ImageLabel, TeachingTipView, PrimaryToolButton, TeachingTipTailPosition, 
    StrongBodyLabel, SwitchButton, ComboBox
)

from assets import res
from GUI.core.anim import ProxyRotationController, ExpandCollapseOrchestrator, ContentTarget
from utils.redViewer_tools import BookShow
from utils.config.qc import cgs_cfg
from utils.network.doh import DEFAULT_DOH_URL


class DoHButtonController:
    def __init__(self, button, parent, on_saved=None, tail_position=TeachingTipTailPosition.RIGHT):
        self._button = button
        self._parent = parent
        self._on_saved = on_saved
        self._tail_position = tail_position
        self._tip = None
        self._button.clicked.connect(self.show_tip)

    def show_tip(self):
        if self._tip is not None:
            self._tip.close()
        dohEdit = LineEdit(self._parent)
        dohEdit.setMinimumWidth(360)
        dohEdit.setPlaceholderText(DEFAULT_DOH_URL)
        dohEdit.setText(cgs_cfg.get_doh_url())
        completer = QCompleter(cgs_cfg.get_doh_history(), dohEdit)
        completer.setFilterMode(Qt.MatchStartsWith)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        dohEdit.setCompleter(completer)
        dohEdit.setClearButtonEnabled(True)
        dohSvBtn = PrimaryToolButton(FluentIcon.SAVE, self._parent)
        tip = CustomTeachingTip.create(
            [dohEdit, dohSvBtn],target=self._button,parent=self._parent,tailPosition=self._tail_position,
        )
        self._tip = tip
        tip.destroyed.connect(lambda *_args: setattr(self, "_tip", None))
        dohEdit.returnPressed.connect(dohSvBtn.click)
        dohSvBtn.clicked.connect(lambda: self._save(dohEdit.text()))

    def _save(self, raw_value: str):
        try:
            doh_url = cgs_cfg.set_doh_url(raw_value)
        except Exception as exc:
            InfoBar.error(
                title="", content=f"DoH 配置保存失败: {exc}", orient=Qt.Horizontal, isClosable=True, 
                position=InfoBarPosition.BOTTOM, duration=8000, parent=self._parent)
            return
        InfoBar.success(
            title="",content="DoH 配置保存成功",orient=Qt.Horizontal,isClosable=True,
            position=InfoBarPosition.BOTTOM,duration=2500,parent=self._parent)
        if callable(self._on_saved):
            self._on_saved(doh_url)
        if self._tip is not None:
            self._tip.close()


class CustEdit(LineEdit):
    custSignal = Signal(str)
    clearSignal = Signal()
    icon: FluentIconBase = None
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.btn = LineEditButton(self.icon, self)
        self.hBoxLayout.addWidget(self.btn, 0, Qt.AlignRight)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))
        self.setClearButtonEnabled(True)
        self.setTextMargins(0, 0, 59, 0)
        self.btn.clicked.connect(self.do)
        self.returnPressed.connect(self.do)
        self.clearButton.clicked.connect(self.clearSignal)

    def setClearButtonEnabled(self, enable: bool):
        self._isClearButtonEnabled = enable
        self.setTextMargins(0, 0, 28*enable+30, 0)
    
    def do(self):
        """self logic"""


class LinkEdit(CustEdit):
    """ Search line edit """
    icon = FluentIcon.LINK

    def do(self):
        text = self.text().strip()
        if text:
            self.custSignal.emit(text)
        else:
            self.clearSignal.emit()


class AcceptEdit(CustEdit):
    """ Search line edit """
    icon = FluentIcon.ACCEPT

    def do(self):
        self.custSignal.emit(self.text().strip())


class FlexImageLabel(ImageLabel):
    def setImage(self, image=None):
        self.image = image or QImage()
        if isinstance(image, str):
            reader = QImageReader(image)
            if reader.supportsAnimation():
                self.setMovie(QMovie(image))
            else:
                self.image = reader.read()
        elif isinstance(image, QPixmap):
            self.image = image.toImage()
        self.update()

    def sizeHint(self):
        return QSize(0, 0)

    def minimumSizeHint(self):
        return QSize(0, 0)


class CustomInfoBar:
    @staticmethod
    def show(title, content, parent, url, url_name, _type="ERROR", **kw):
        InfoBar_kw = dict(
            icon=getattr(InfoBarIcon, _type.upper()),
            title=title, content=content,
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.BOTTOM, duration=-1,
            parent=parent
        )
        w = InfoBar(**{**InfoBar_kw, **kw})
        w.addWidget(HyperlinkButton(FluentIcon.LINK, url, url_name, parent=None))
        w.show()

    @staticmethod
    def show_custom(title, content, parent, _type="ERROR", ib_pos=InfoBarPosition.BOTTOM, duration=-1,
                    widgets=[], **kw):
        InfoBar_kw = dict(
            icon=getattr(InfoBarIcon, _type.upper()),
            title=title, content=content,
            orient=Qt.Horizontal, isClosable=True,
            position=ib_pos, duration=duration,
            parent=parent
        )
        w = InfoBar(**{**InfoBar_kw, **kw})
        for widget in widgets:
            w.addWidget(widget)
        w.show()


class CustomFlyout:
    @classmethod
    def make(cls, view, target, parent, calc_bottom=False, aniType=FlyoutAnimationType.PULL_UP):
        _fly = Flyout.make(
            view=view, parent=parent, aniType=aniType, 
            target=cls.calculate_target_position(target) if calc_bottom else target
        )
        if hasattr(view, "closed"):
            view.closed.connect(_fly.close)
        return _fly


    @staticmethod
    def calculate_target_position(widget):
        rect = widget.rect()
        bottom_center = widget.mapToGlobal(rect.bottomLeft())
        bottom_center.setX(bottom_center.x() + rect.width() // 2 - widget.width() // 2)
        bottom_center.setY(bottom_center.y() - 15)
        return bottom_center


class CustomTeachingTip:
    @classmethod
    def create(cls, widgets, target, parent, content=None,
             isClosable=True, duration=-1, **kw):
        view = TeachingTipView(
            title="", content="", isClosable=isClosable
        )
        offset = 0
        cindex = 1 if isClosable else 0
        for w in widgets:
            view.viewLayout.insertWidget(view.viewLayout.count() - cindex, w)
            offset += (w.sizeHint().width() + 5)
        view.adjustSize()
        tip = TeachingTip(view, target, duration, parent=parent, **kw)
        tip.show()
        view.closeButton.clicked.connect(tip.close)
        return tip


class CustomIcon(FluentIconBase, Enum):
    DISCORD = "configDialog/discord"
    QQ = "configDialog/qq"
    TOOL_MERGE = "tools/merge"
    TOOL_BOOK_MARKED = "tools/book_marked"
    
    def path(self, theme=Theme.AUTO):
        return f':/{self.value}.svg'


class ExpandSettings(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.conf_dia = parent
        self.setVisible(False)
        self._driver = None
        self._section_widgets = []
        self.setupUi()
        self.bind()

    def setupUi(self):
        self.main_layout = VBoxLayout(self)
        self.setLayout(self.main_layout)
        
        cookiesLayout = QtWidgets.QHBoxLayout()
        cookiesLayout.setObjectName("cookiesLayout")
        self.conf_dia.verticalLayout_3 = QtWidgets.QVBoxLayout()
        self.conf_dia.verticalLayout_3.setObjectName("verticalLayout_3")
        self.conf_dia.cookiesLabel = StrongBodyLabel()
        self.conf_dia.cookiesLabel.setEnabled(True)
        self.conf_dia.cookiesLabel.setMinimumSize(QtCore.QSize(60, 0))
        self.conf_dia.cookiesLabel.setMaximumSize(QtCore.QSize(60, 40))
        self.conf_dia.cookiesLabel.setAlignment(QtCore.Qt.AlignCenter)
        self.conf_dia.cookiesLabel.setObjectName("cookiesLabel")
        self.conf_dia.cookiesLabel.setText("Cookies")
        self.conf_dia.verticalLayout_3.addWidget(self.conf_dia.cookiesLabel)
        self.conf_dia.cookiesBox = ComboBox()
        self.conf_dia.cookiesBox.setObjectName("cookiesBox")
        self.conf_dia.verticalLayout_3.addWidget(self.conf_dia.cookiesBox)
        spacerItem2 = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.conf_dia.verticalLayout_3.addItem(spacerItem2)
        cookiesLayout.addLayout(self.conf_dia.verticalLayout_3)
        setattr(self.conf_dia, "horizontalLayout_label_cookies", cookiesLayout)
        # self.conf_dia.cookiesLabel.setText(_translate("Dialog", "Cookies"))
        
        custMapLayout = QtWidgets.QHBoxLayout()
        custMapLayout.setObjectName("custMapLayout")
        self.custMapLabelLayout = QtWidgets.QVBoxLayout()
        self.custMapLabelLayout.setSpacing(0)
        custMapLabel = StrongBodyLabel(self.conf_dia)
        custMapLabel.setMinimumSize(QtCore.QSize(40, 0))
        custMapLabel.setMaximumSize(QtCore.QSize(40, 20))
        custMapLabel.setAlignment(QtCore.Qt.AlignCenter)
        custMapLabel.setObjectName("label_3")
        custMapLabel.setText(QtCore.QCoreApplication.translate("Dialog", res.GUI.Uic.confDia_labelMap))
        self.custMapLabelLayout.addWidget(custMapLabel)
        self.custMapLabelLayout.addStretch()
        custMapLayout.addLayout(self.custMapLabelLayout)
        setattr(self.conf_dia, "horizontalLayout_label_custom_map", custMapLayout)

        second_row = QtWidgets.QHBoxLayout()
        pypi_label = StrongBodyLabel(res.GUI.Uic.confDia_pypiLabel, self)
        pypi_label.setMinimumSize(QtCore.QSize(40, 0))
        lang_label = StrongBodyLabel(res.GUI.Uic.confDia_langLabel, self)
        lang_label.setMinimumSize(QtCore.QSize(40, 0))
        second_row.addWidget(lang_label)
        second_row.addWidget(self.conf_dia.langBox)
        second_row.addWidget(pypi_label)
        second_row.addWidget(self.conf_dia.pypiSourceBox)
        second_row.addStretch()
        
        self.cookies_section = QtWidgets.QWidget(self)
        cookies_section_layout = QtWidgets.QVBoxLayout(self.cookies_section)
        cookies_section_layout.setContentsMargins(10,0,10,0)
        cookies_section_layout.setSpacing(10)
        cookies_section_layout.addLayout(cookiesLayout)

        self.cust_map_section = QtWidgets.QWidget(self)
        cust_map_section_layout = QtWidgets.QVBoxLayout(self.cust_map_section)
        cust_map_section_layout.setContentsMargins(10,0,10,0)
        cust_map_section_layout.setSpacing(10)
        cust_map_section_layout.addLayout(custMapLayout)

        self.second_row_section = QtWidgets.QWidget(self)
        second_row_section_layout = QtWidgets.QVBoxLayout(self.second_row_section)
        second_row_section_layout.setContentsMargins(10,0,10,0)
        second_row_section_layout.setSpacing(10)
        second_row_section_layout.addLayout(second_row)

        self.main_layout.addWidget(self.cookies_section)
        self.main_layout.addWidget(self.cust_map_section)
        self.main_layout.addWidget(self.second_row_section)
        self._section_widgets = [
            self.cookies_section,
            self.cust_map_section,
            self.second_row_section,
        ]

        self.conf_dia.skipDev = SwitchButton(self)
        self.conf_dia.skipDev.setMinimumHeight(0)
        self.conf_dia.skipDev.setOnText(res.GUI.Uic.confDia_skipDevRelease)
        self.conf_dia.skipDev.setOffText(res.GUI.Uic.confDia_skipDevRelease)
        self.conf_dia.kbShowDhb = SwitchButton(self)
        self.conf_dia.kbShowDhb.setMinimumHeight(0)
        self.conf_dia.kbShowDhb.setOnText(res.GUI.Uic.confDia_kbShowDhb)
        self.conf_dia.kbShowDhb.setOffText(res.GUI.Uic.confDia_kbShowDhb)
        second_row.addWidget(self.conf_dia.skipDev)
        second_row.addWidget(self.conf_dia.kbShowDhb)

    def bind(self):
        self._driver = ExpandCollapseOrchestrator(
            window_target=self.conf_dia,
            content_targets=[
                ContentTarget(widget=self.cookies_section,
                    measure_height=self._section_target_height,
                    duration_weight=98.0,
                ),
                ContentTarget(widget=self.cust_map_section,
                    measure_height=self._section_target_height,
                    duration_weight=98.0,
                ),
                ContentTarget(widget=self.second_row_section,
                    measure_height=self._section_target_height,
                    duration_weight=32.0,
                ),
            ],
            duration_ms=233,
            window_target_height_getter=self._window_target_height,
            before_expand=self._before_expand,
            after_collapse=self._after_collapse,
            parent=self,
        )
        for section_widget in self._section_widgets:
            self._driver.set_content_height(section_widget, 0)
            section_widget.setVisible(False)

        hide_text = res.GUI.Uic.confDia_hide_adv_settings
        show_text = res.GUI.Uic.confDia_show_adv_settings

        def _toggle_adv(_=None):
            if self._driver.is_transitioning:
                return
            want_expand = not self.isVisible()
            self.conf_dia.advBtn.setChecked(want_expand)
            self.conf_dia.advBtn.setText(hide_text if want_expand else show_text)

            if want_expand:
                self.conf_dia.setWindowOpacity(0.0)
                self.setVisible(True)

                def _begin_expand():
                    if self._driver is None or self.conf_dia is None:
                        if self.conf_dia is not None:
                            self.conf_dia.setWindowOpacity(1.0)
                        return
                    try:
                        self.conf_dia.setWindowOpacity(1.0)
                        if not self._driver.expand():
                            self.conf_dia.setWindowOpacity(1.0)
                    except Exception:
                        self.setVisible(False)
                        self.conf_dia.setWindowOpacity(1.0)
                        raise
                safe_single_shot(0, _begin_expand)
            else:
                self._driver.collapse()

        self.conf_dia.advBtn.clicked.connect(_toggle_adv)

    def _before_expand(self):
        self.conf_dia.completerEdit.setMaximumHeight(100)

    def _after_collapse(self):
        self.conf_dia.completerEdit.setMaximumHeight(1000)
        self.setVisible(False)

    @staticmethod
    def _section_target_height(section_widget):
        return max(0, int(section_widget.sizeHint().height()))

    def _window_target_height(self, total_expand_delta):
        target_height = self.conf_dia.maximumHeight()
        return min(target_height, self.conf_dia.maximumHeight())


class SupportView(FlyoutViewBase):
    closed = Signal()  # 添加closed信号
    res = res.GUI.Uic
    
    def __init__(self, conf_dia=None):
        super(SupportView, self).__init__(conf_dia)
        self.conf_dia = conf_dia
        self.width = int(conf_dia.width() * 0.8)
        self.layout = VBoxLayout(self)
        self.titleLayout = QtWidgets.QHBoxLayout()
        self.qqGroupBtn = HyperlinkButton(CustomIcon.QQ, "https://qm.qq.com/q/T2SONVQmiW", "QQ")
        self.discordBtn = HyperlinkButton(CustomIcon.DISCORD, "https://discord.gg/znD4p2fpSE", "Discord")
        spacerItem = QtWidgets.QSpacerItem(10, 10, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.closeBtn = TransparentToolButton(FluentIcon.CLOSE, self)
        self.closeBtn.clicked.connect(self.closed)
        self.titleLayout.addWidget(self.qqGroupBtn)
        self.titleLayout.addWidget(self.discordBtn)
        self.titleLayout.addItem(spacerItem)
        self.titleLayout.addWidget(self.closeBtn)
        
        self.promoteLayout = QtWidgets.QHBoxLayout()
        self.promoteBtn = HyperlinkButton(FluentIcon.LINK, self.res.confDia_promote_url, self.res.confDia_promote_title)
        self.promoteLayout.addWidget(self.promoteBtn)
        self.promoteLayout.addItem(QtWidgets.QSpacerItem(10, 10, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum))

        self.contentLabel = BodyLabel(res.GUI.Uic.confDia_support_content) 

        self.affLayout = QtWidgets.QHBoxLayout()
        self.riesBtn = HyperlinkButton(FluentIcon.EDUCATION, "https://Ries.ai?c=Jzva", "英语插件")
        self.siliconBtn = HyperlinkButton(FluentIcon.CLOUD, "https://cloud.siliconflow.cn/i/j0SGXRO6", "硅基")
        self.yuqueBtn = PrimaryPushButton(FluentIcon.QUICK_NOTE, "语雀")
        def _yuque():
            copyBtn = TransparentToolButton(FluentIcon.COPY)
            def _copied():
                QApplication.clipboard().setText("CZULIQ")
                InfoBar.success(title='', content='已复制', parent=self.conf_dia, position=InfoBarPosition.TOP, duration=2000)
            copyBtn.clicked.connect(_copied)
            CustomInfoBar.show_custom(title='', content='点按钮复制邀请码', parent=self.conf_dia, _type="INFORMATION",
                ib_pos=InfoBarPosition.TOP, widgets=[copyBtn])
            safe_single_shot(4000, lambda: QDesktopServices.openUrl(QUrl("https://www.yuque.com")))
        self.yuqueBtn.clicked.connect(_yuque)
        self.affLayout.addWidget(self.riesBtn)
        self.affLayout.addWidget(self.siliconBtn)
        self.affLayout.addWidget(self.yuqueBtn)
        self.affLayout.addItem(QtWidgets.QSpacerItem(10, 10, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum))

        self.layout.addLayout(self.titleLayout)
        self.hLine = QtWidgets.QFrame(self)
        self.hLine.setFrameShape(QtWidgets.QFrame.HLine)
        self.hLine.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.layout.addWidget(self.hLine)
        self.layout.addLayout(self.promoteLayout)
        self.layout.addWidget(self.contentLabel)
        self.layout.addLayout(self.affLayout)
        # self.layout.addLayout(self.picLayout)
        self.setFixedWidth(self.width)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)


class IndeterminateBarFView(FlyoutViewBase):
    def __init__(self, parent=None):
        super(IndeterminateBarFView, self).__init__(parent)
        self.barLayout = QtWidgets.QHBoxLayout()
        self.barLayout.setContentsMargins(8, 0, 8, 0)
        indeterminateBar = IndeterminateProgressBar(self, start=True)
        self.barLayout.addWidget(indeterminateBar)
        self.setLayout(self.barLayout)
        self.setFixedSize(int(parent.width()*0.93), 10)


class TableFlyoutView(FlyoutViewBase):
    closed = Signal()

    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.rvInterface = parent
        self.gui = parent.toolWin.gui
        p_width = parent.width()
        p_height = parent.height()
        self.width = int(p_width * 0.8)
        self.height = int(p_height * 4)
        # 必须设置布局
        self.layout = VBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        # 创建表格视图
        self.set_table(data)
        first_row = QtWidgets.QHBoxLayout()
        first_row.addWidget(self.tableView)
        
        second_row = QtWidgets.QHBoxLayout()
        
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.closeBtn = TransparentToolButton(FluentIcon.CLOSE, self)
        self.closeBtn.clicked.connect(self.closed)
        self.delBtn = PrimaryPushButton(FluentIcon.DELETE, "删除选中记录", self)
        self.delBtn.clicked.connect(self.delete_selected_record)
        self.searchBtn = PrimaryPushButton(FluentIcon.SEARCH, "搜索选中记录", self)
        self.searchBtn.clicked.connect(self.send_selected_record)
        second_row.addWidget(self.delBtn)
        second_row.addWidget(self.searchBtn)
        second_row.addItem(spacerItem)
        second_row.addWidget(self.closeBtn)
        
        self.layout.addLayout(first_row)
        self.layout.addLayout(second_row)
        # 必须设置视图尺寸
        self.setFixedSize(self.width, self.height)

    def set_table(self, data: t.Dict[str, BookShow]):
        self.tableView = TableView(self)
        self.tableView.setBorderRadius(15)
        self.tableView.setWordWrap(False)
        tb_width = self.width
        tb_height = self.height - 30
        self.tableView.setFixedSize(tb_width, tb_height)
        self.tableView.verticalHeader().hide()
        # 设置数据模型
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(["漫画", "已阅最新章节", "已下载最新章节"])
        for book in data.values():
            row = [
                QStandardItem(book.name),
                QStandardItem(book.show_max),
                QStandardItem(book.dl_max)
            ]
            model.appendRow(row)
        self.tableView.setModel(model)
        self.tableView.setSortingEnabled(True)
        self.tableView.horizontalHeader().setSortIndicatorShown(True)
        self.tableView.horizontalHeader().setStretchLastSection(True)
        # 调整列宽
        self.tableView.setColumnWidth(0, int(tb_width * 0.5))
        self.tableView.setColumnWidth(1, int(tb_width * 0.2))
        self.tableView.setColumnWidth(2, int(tb_width * 0.2))

        self.tableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tableView.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

    def delete_selected_record(self):
        selection_model = self.tableView.selectionModel()
        if not selection_model.hasSelection():
            InfoBar.warning(
                title='', content='请先选择要删除的记录',
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM_LEFT,
                duration=5000, parent=self.rvInterface
            )
            return
        selected_indexes = selection_model.selectedRows()
        row = selected_indexes[0].row()
        model = self.tableView.model()
        book_name = model.item(row, 0).text()
        self.gui.rv_tools.delete_record(book_name)
        model.removeRow(row)

    def send_selected_record(self):
        selection_model = self.tableView.selectionModel()
        if not selection_model.hasSelection():
            InfoBar.warning(
                title='', content='请先选择行',
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM_RIGHT,
                duration=5000, parent=self.rvInterface.table_fv
            )
            return
        elif self.gui.chooseBox.currentIndex() == 0:
            InfoBar.warning(
                title='', content='请先选择搜索源',
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM_RIGHT,
                duration=5000, parent=self.rvInterface.table_fv
            )
            return
        selected_indexes = selection_model.selectedRows()
        row = selected_indexes[0].row()
        model = self.tableView.model()
        book_name = model.item(row, 0).text()
        def do():
            self.gui.searchinput.setText(book_name)
            cont = '已发至输入框，自行调整再点击搜索'
            if self.gui.rv_tools.ero != 1:
                # TODO[1](2026-03-05): 处理一下
                self.gui.mpreviewBtn.click()
                cont = f'''「{book_name}」已发至输入框进行搜索中'''
            InfoBar.info(title='', content=cont,
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
                duration=2000, parent=self.gui.showArea)
        safe_single_shot(10, do)
        self.rvInterface.table_fv.close()
        self.rvInterface.toolWin.close()


_ICON_SIZE = 18
_VIEW_SIZE = 24
_PAD = (_VIEW_SIZE - _ICON_SIZE) // 2

class ExpandButton(QWidget):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.expanded = False

        self._label = ImageLabel()
        self._label.setImage(QPixmap(":/expand.svg"))
        self._label.setFixedSize(_ICON_SIZE, _ICON_SIZE)

        self._scene = QGraphicsScene(self)
        self._view = QGraphicsView(self._scene, self)
        self._proxy = self._scene.addWidget(self._label)
        self._proxy.setPos(_PAD, _PAD)
        self._proxy.setTransformOriginPoint(_ICON_SIZE / 2, _ICON_SIZE / 2)
        self._scene.setSceneRect(0, 0, _VIEW_SIZE, _VIEW_SIZE)

        self._view.setFixedSize(_VIEW_SIZE, _VIEW_SIZE)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._view.setFrameShape(QGraphicsView.NoFrame)
        self._view.setStyleSheet("background: transparent;")
        self._view.setBackgroundBrush(QBrush(Qt.transparent))
        self._view.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._anim_ctrl = ProxyRotationController(self._proxy)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

        self.setFixedSize(_VIEW_SIZE, _VIEW_SIZE)
        self.setCursor(Qt.PointingHandCursor)

    def expand(self):
        self.expanded = not self.expanded
        self._anim_ctrl.rotate_to(-45.0 if self.expanded else 0.0)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)

    def click(self):
        self.clicked.emit()
