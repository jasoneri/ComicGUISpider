import typing as t
from enum import Enum
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QApplication, QGraphicsOpacityEffect
from PyQt5.QtCore import Qt, QUrl, pyqtSignal, QTimer, QEvent, QPropertyAnimation, QEasingCurve, QPoint, QObject
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QDesktopServices
from qfluentwidgets import (
    TransparentToolButton, HyperlinkButton, PrimaryPushButton,
    FluentIcon, FluentIconBase, Theme,
    VBoxLayout, Flyout, FlyoutAnimationType, FlyoutViewBase, TableView,
    InfoBar, InfoBarIcon, InfoBarPosition, IndeterminateProgressBar, BodyLabel,
    TeachingTip, TeachingTipTailPosition, ImageLabel,
    StrongBodyLabel, IconInfoBadge, InfoBadgeManager, InfoBadgePosition,
    DotInfoBadge, SwitchButton, ComboBox, TextEdit
)


from assets import res
from utils.redViewer_tools import BookShow


class ClickableIconInfoBadge(IconInfoBadge):
    clicked = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 移除透明鼠标事件属性，使 badge 可点击
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.isEnabled():
            self.clicked.emit()
        super().mousePressEvent(e)

    def eventFilter(self, obj, e):
        if self._inside and obj is self._target and e.type() in (QEvent.Resize, QEvent.Move):
            self._update_position_inside()
        return super().eventFilter(obj, e)


class _BadgeAnchor(QObject):
    """Tracks target widget movement and repositions badge via mapTo."""
    def __init__(self, target, badge, parent_widget, pos):
        super().__init__(badge)
        self.target = target
        self.badge = badge
        self.parent_widget = parent_widget
        self.pos = pos
        target.installEventFilter(self)
        if target.parentWidget():
            target.parentWidget().installEventFilter(self)

    def eventFilter(self, obj, e):
        if e.type() in (QEvent.Resize, QEvent.Move):
            self.badge.move(self.calc_position())
        return False

    def calc_position(self):
        tr = self.target.rect().topRight()
        mapped = self.target.mapTo(self.parent_widget, tr)
        return QPoint(mapped.x() - self.badge.width() // 2, mapped.y() - self.badge.height() // 2)


class CustomBadge:
    @classmethod
    def make(cls, bge_args, pos: InfoBadgePosition, target):
        _bge = ClickableIconInfoBadge(*bge_args)
        _bge.manager = InfoBadgeManager.make(pos, target, _bge)
        _bge.move(_bge.manager.position())
        return _bge

    @classmethod
    def make_ani_dot(cls, parent, size=None, target=None, level="success", pos=InfoBadgePosition.TOP_RIGHT):
        t = target or parent
        sz = size or (10, 10)
        dot = getattr(DotInfoBadge, level)(parent, target=None, position=pos)
        dot.setFixedSize(*sz)
        anchor = _BadgeAnchor(t, dot, parent, pos)
        dot.move(anchor.calc_position())
        dot._anchor = anchor
        opacity = QGraphicsOpacityEffect(dot)
        dot.setGraphicsEffect(opacity)
        anim = QPropertyAnimation(opacity, b"opacity")
        anim.setDuration(1500)
        anim.setStartValue(0.3)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.InOutSine)
        anim.finished.connect(lambda: (
            anim.setDirection(anim.Backward if anim.direction() == anim.Forward else anim.Forward),
            anim.start()
        ))
        anim.start()
        dot._breath_anim = anim
        return dot


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
    def make(cls, view, target, parent, tailPosition=TeachingTipTailPosition.BOTTOM):
        _tip = TeachingTip.make(
            view=view, target=target, duration=-1, tailPosition=tailPosition, parent=parent
        )
        if hasattr(view, "closed"):
            view.closed.connect(_tip.close)
        return _tip


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
        self.bind()
        self.setupUi()

    def setupUi(self):
        self.main_layout = VBoxLayout(self)
        self.setLayout(self.main_layout)
        
        cookiesLayout = QtWidgets.QHBoxLayout()
        cookiesLayout.setObjectName("cookiesLayout")
        self.conf_dia.verticalLayout_3 = QtWidgets.QVBoxLayout()
        self.conf_dia.verticalLayout_3.setObjectName("verticalLayout_3")
        self.conf_dia.cookiesLabel = StrongBodyLabel()
        self.conf_dia.cookiesLabel.setEnabled(True)
        self.conf_dia.cookiesLabel.setMinimumSize(QtCore.QSize(60, 20))
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
        self.conf_dia.cookiesEdit = TextEdit()
        self.conf_dia.cookiesEdit.setObjectName("cookiesEdit")
        cookiesLayout.addWidget(self.conf_dia.cookiesEdit)
        setattr(self.conf_dia, "horizontalLayout_label_cookies", cookiesLayout)
        # self.conf_dia.cookiesLabel.setText(_translate("Dialog", "Cookies"))
        
        custMapLayout = QtWidgets.QHBoxLayout()
        custMapLayout.setObjectName("custMapLayout")
        self.custMapLabelLayout = QtWidgets.QVBoxLayout()
        self.custMapLabelLayout.setSpacing(0)
        custMapLabel = StrongBodyLabel(self.conf_dia)
        custMapLabel.setMinimumSize(QtCore.QSize(40, 20))
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
        pypi_label.setMinimumSize(QtCore.QSize(40, 20))
        lang_label = StrongBodyLabel(res.GUI.Uic.confDia_langLabel, self)
        lang_label.setMinimumSize(QtCore.QSize(40, 20))
        second_row.addWidget(lang_label)
        second_row.addWidget(self.conf_dia.langBox)
        second_row.addWidget(pypi_label)
        second_row.addWidget(self.conf_dia.pypiSourceBox)
        second_row.addStretch()
        
        self.main_layout.addLayout(cookiesLayout)
        self.main_layout.addLayout(custMapLayout)
        self.main_layout.addLayout(second_row)

        self.conf_dia.skipDev = SwitchButton(self)
        self.conf_dia.skipDev.setOnText(res.GUI.Uic.confDia_skipDevRelease)
        self.conf_dia.skipDev.setOffText(res.GUI.Uic.confDia_skipDevRelease)
        self.conf_dia.kbShowDhb = SwitchButton(self)
        self.conf_dia.kbShowDhb.setOnText(res.GUI.Uic.confDia_kbShowDhb)
        self.conf_dia.kbShowDhb.setOffText(res.GUI.Uic.confDia_kbShowDhb)
        line = QtWidgets.QFrame(self)
        line.setFrameShape(QtWidgets.QFrame.VLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        second_row.addWidget(self.conf_dia.skipDev)
        second_row.addWidget(line)
        second_row.addWidget(self.conf_dia.kbShowDhb)

    def bind(self):
        def _toggle_adv(_=None):
            now = not self.isVisible()
            self.setVisible(now)
            self.conf_dia.advBtn.setChecked(now)
            self.conf_dia.refresh_size_for_expand(now)
            self.conf_dia.advBtn.setText(res.GUI.Uic.confDia_hide_adv_settings if now else res.GUI.Uic.confDia_show_adv_settings)
        self.conf_dia.advBtn.clicked.connect(_toggle_adv)


class SupportView(FlyoutViewBase):
    closed = pyqtSignal()  # 添加closed信号
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
            QTimer.singleShot(4000, lambda: QDesktopServices.openUrl(QUrl("https://www.yuque.com")))
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
    closed = pyqtSignal()

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
                self.gui.next_btn.click()
                cont = f'''「{book_name}」已发至输入框进行搜索中'''
            InfoBar.info(title='', content=cont,
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
                duration=2000, parent=self.gui.textBrowser)
        QTimer.singleShot(10, do)
        self.rvInterface.table_fv.close()
        self.rvInterface.toolWin.close()
