# -*- coding: utf-8 -*-
"""addonsInterface：cell 网格页（挂 ToolWorkspaceWindow pivot）。

cell 尺寸恒定、不随窗口伸缩：窗口变宽只增加列数（FlowLayout reflow，行数向下延伸，
溢出走纵向滚动）。所有 cell 共用一套比例——正方形包裹（边长 = 2×按钮行高 + 行间距）、
背景图 cover 铺满、按钮高 = 行高；排布只能改放置，不得改比例。

cell 家族：``RvCell``（redViewer 部署/清理/运行）与 ``CustomCell``（用户新增，定义
持久化在 ``cgs_cfg.addonsCells``）为多按钮结构，卡片底 + 闭合边框；``BuiltinLogicCell``
是内置 icon-only 单按钮逻辑 cell 父类——只承载结构（正方形几何 / 背景 cover / 整格
点击 / 取景框边角），业务由子类的 ``activate`` 钩子提供；其格面全透明、格界由四角
L 型包边给出（QSS 画不出断开的边框，故走 ``_ReticleOverlay`` 的 QPainter 绘制）。
``SauceCell``（saucenao 以图搜源，按站点是否 R18 条件可见）与 ``acggrCell``
（scriptWin 入口，过渡壳）即该父类下的兄弟子类。另有常驻末位的 ``MgrCell``
（新增 / 清理管理开关）。

全部 cell 于本页首次 show 才构造：页面壳本身不碰 DB、不做扫描，不吃启动路径。
网格顺序：rvCell → acggrCell（常驻）→ sauceCell（条件）→ 自定义 cell（创建序）→ mgrCell。
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGraphicsBlurEffect,
    QGraphicsEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    FluentIcon as FIF,
    FlowLayout,
    ImageLabel,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    PrimaryToolButton,
    SingleDirectionScrollArea,
    ToggleToolButton,
    ToolTipFilter,
    TransparentToolButton,
    VBoxLayout,
)

from assets import res as ori_res
from GUI.core.theme import theme_mgr
from GUI.core.theme.button_variant import apply_button_variant
from GUI.core.theme.qss_template import read_templated_qss_tokens
from GUI.uic.qfluent import CustomInfoBar, MonkeyPatch as FluentMonkeyPatch
from utils import conf, curr_os, ori_path
from utils.config.qc import cgs_cfg
from .dialog import MODE_BIN, CommandEditDialog, CustomCellDialog

tools_res = ori_res.GUI.Tools
_QSS_PATH = ori_path.joinpath("GUI/core/theme/subscribe.qss")

# —— cell 设计系统：所有排布只改放置、不改比例 ——
CELL_ROW_H = 71                                 # 按钮行高：按钮高 = 行高
CELL_BTN_GAP = 5                                # 行间距
CELL_SIZE = 2 * CELL_ROW_H + CELL_BTN_GAP       # 147：正方形边长 = 2×行高 + 行间距
GRID_GAP = 12                                   # 网格横纵间距；列数 = floor((宽+间距)/(边长+间距))
# 清理模式抖动：burst 0.75s + rest 1.35s 循环。burst 后必须 rest——持续 motion 会被动
# 抢占注意力，反而成为干扰；包络取 sin² 使边缘小、中间大、首末严格归零。
WOBBLE_ANGLE = 2.5                              # 抖动峰值幅度（度）
WOBBLE_BURST_MS = 750                           # 单次抖动时长（约 2 个振荡周期）
WOBBLE_REST_MS = 1350                           # 抖动后的停歇
WOBBLE_FREQ_HZ = 3.0                            # 振荡频率
MASK_BTN_SIZE = int(CELL_SIZE * math.sqrt(0.75)) + 1  # rmBtn 边长：占格面积 ≥75%
MASK_BLUR_RADIUS = 16                           # 遮罩冰冻玻璃模糊半径
LOGIC_CELL_BG_OPACITY = 0.85                    # 内置逻辑 cell 背景透明度：无按钮层遮挡，背景即格面本体
# 取景框边角（Viewfinder Reticle）：四角 L 型圆角包边、四边中段留空。QSS 的 border 只能画
# 闭合矩形，故走 QPainter 原生绘制（见 _ReticleOverlay）；线色与衬边色取自 subscribe.qss
# 的 LOGIC_CELL_RETICLE / LOGIC_CELL_RETICLE_HALO token。
RETICLE_STROKE = 3                              # 线宽
RETICLE_INSET = 5                               # 描边中心距格边
RETICLE_ARM = 32                                # 自角点沿两边延伸的长度（含圆角段）
RETICLE_RADIUS = 14                             # 拐角圆角半径
RETICLE_HALO_PAD = 2                            # 衬边单侧外扩：线要压在任意背景图上，靠反差衬边保可辨

# (scale_x, scale_y, translate_x, translate_y)：左上为基准路径，其余三角镜像复用
_RETICLE_MIRRORS = (
    (1, 1, 0, 0),
    (-1, 1, CELL_SIZE, 0),
    (1, -1, 0, CELL_SIZE),
    (-1, -1, CELL_SIZE, CELL_SIZE),
)


class _WobbleEffect(QGraphicsEffect):
    """整格微旋转抖动：源位图（含子按钮与遮罩）绕格心旋转后绘制。

    动 geometry 会跟 FlowLayout 抢位置；effect 只改绘制不改几何，布局零感知。
    角部超出格界的微量裁切即旋转观感；angle=0 时直绘源图（无副作用）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0.0

    def setAngle(self, angle: float):
        if angle != self._angle:
            self._angle = angle
            self.update()

    def draw(self, painter: QPainter):
        pix = self.sourcePixmap(Qt.LogicalCoordinates, None, QGraphicsEffect.PadToEffectiveBoundingRect)
        if pix.isNull():
            return
        if not self._angle:
            painter.drawPixmap(0, 0, pix)
            return
        w, h = pix.width(), pix.height()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.translate(w / 2, h / 2)
        painter.rotate(self._angle)
        painter.drawPixmap(-w / 2, -h / 2, pix)
        painter.restore()


class _WinOS:
    file_type = ".exe"
    script_type = "Script Exe (*.exe)"
    run_cmd = ["start", "/B"]
    run_cmd_kw = dict(start_new_session=True, shell=True, creationflags=0x00000008 | 0x00000200)


class _ElseOS:
    file_type = ".sh"
    script_type = "Script Files (*.sh)"
    run_cmd = [curr_os.shell]
    run_cmd_kw = dict(start_new_session=True, shell=True)


_TmpCurrOs = _WinOS if curr_os.shell == "powershell" else _ElseOS


def _set_cell_background(bg: ImageLabel, icon: str) -> None:
    """把背景图按 cover 铺满整格（所有 cell 共用）。

    ``ImageLabel.setImage()`` 内部会 ``setFixedSize(图片原始尺寸)``，覆盖调用前设好的
    geometry：源图小于格边长时背景会缩成原图大小而铺不满。故先按
    KeepAspectRatioByExpanding 放大到不小于格尺寸、居中裁成正方形，再在 setImage
    之后重新钉回格几何。
    """
    pixmap = QPixmap(icon)
    if pixmap.isNull():
        return
    scaled = pixmap.scaled(CELL_SIZE, CELL_SIZE,
                           Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x = (scaled.width() - CELL_SIZE) // 2
    y = (scaled.height() - CELL_SIZE) // 2
    bg.setImage(scaled.copy(x, y, CELL_SIZE, CELL_SIZE))
    # setImage 的 setFixedSize(图片尺寸) 会覆盖先前的 geometry，必须再钉一次
    bg.setGeometry(1, 1, CELL_SIZE - 2, CELL_SIZE - 2)


class RvCell(QFrame):
    """redViewer 格：部署 / 清理 / 运行，比例锁定。"""

    def __init__(self, host_window, parent=None):
        super().__init__(parent)
        self.host_window = host_window
        self.setObjectName("AddonsCell")
        self.setFixedSize(CELL_SIZE, CELL_SIZE)

        self.bg = ImageLabel(self)
        self.bg.setScaledContents(True)
        self.bg.setBorderRadius(9, 9, 9, 9)
        _set_cell_background(self.bg, ":/tools/rv.png")
        bg_opacity = QGraphicsOpacityEffect(self.bg)
        bg_opacity.setOpacity(0.3)
        self.bg.setGraphicsEffect(bg_opacity)
        self.bg.lower()

        col = VBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(CELL_BTN_GAP)
        self.deployBtn = PrimaryPushButton(FIF.DOWNLOAD, tools_res.rv_deploy_desc)
        deploy_opacity = QGraphicsOpacityEffect(self.deployBtn)
        deploy_opacity.setOpacity(0.8)
        self.deployBtn.setGraphicsEffect(deploy_opacity)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(CELL_BTN_GAP)
        self.broomBtn = TransparentToolButton(FIF.BROOM, self)
        self.broomBtn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.broomBtn.setToolTip(tools_res.rv_tip_broom)
        self.broomBtn.setAccessibleName(tools_res.rv_tip_broom)
        self.broomBtn.installEventFilter(ToolTipFilter(self.broomBtn))
        self._sync_broom_state()
        self.runBtn = PrimaryToolButton(FIF.PLAY)
        self.runBtn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.runBtn.setToolTip(tools_res.rv_tip_run)
        self.runBtn.setAccessibleName(tools_res.rv_tip_run)
        self.runBtn.installEventFilter(ToolTipFilter(self.runBtn))
        run_opacity = QGraphicsOpacityEffect(self.runBtn)
        run_opacity.setOpacity(0.8)
        self.runBtn.setGraphicsEffect(run_opacity)
        btn_row.addWidget(self.broomBtn)
        btn_row.addWidget(self.runBtn)
        for btn in (self.deployBtn, self.broomBtn, self.runBtn):
            btn.setFixedHeight(CELL_ROW_H)
        col.addWidget(self.deployBtn)
        col.addLayout(btn_row)

        self.deployBtn.clicked.connect(self.deploy)
        self.broomBtn.clicked.connect(self.broom)
        self.runBtn.clicked.connect(self.run)

    def sizeHint(self):
        # FlowLayout 以 item.sizeHint() 做 reflow 排布：固定尺寸必须由 sizeHint 如实上报。
        return QSize(CELL_SIZE, CELL_SIZE)

    def _sync_broom_state(self):
        rv = conf.rv_script
        self.broomBtn.setEnabled(bool(rv and str(rv) != "."))

    def deploy(self):
        QDesktopServices.openUrl(QUrl("https://github.com/jasoneri/redViewer/releases"))

    def broom(self):
        conf.update(rv_script="")
        self._sync_broom_state()

    def run(self):
        if _TmpCurrOs is not _WinOS:
            CustomInfoBar.show(
                title='', content=tools_res.rv_nonwin_guide,
                parent=self,
                url="https://rv.101114105.xyz/deploy/#%E2%8C%98-2-%E5%91%BD%E4%BB%A4%E8%A1%8C-%E9%83%A8%E7%BD%B2-%E8%BF%90%E8%A1%8C%E2%80%94%E5%A4%9A%E5%90%88%E4%B8%80%E8%84%9F%E6%9C%AC",
                url_name=tools_res.rv_deploy_desc,
                _type="INFORMATION"
            )
            return

        rv_script = conf.rv_script
        if not (rv_script and str(rv_script) != "." and rv_script.is_file() and rv_script.suffix == _TmpCurrOs.file_type):
            file, _ = QFileDialog.getOpenFileName(self, ori_res.GUI.Uic.sv_path_desc_tip, "", _TmpCurrOs.script_type)
            if not file:
                return
            conf.update(rv_script=file)
            rv_script = conf.rv_script
            self._sync_broom_state()

        cmd = _TmpCurrOs.run_cmd + [str(rv_script)]
        subprocess.Popen(cmd, cwd=str(rv_script.parent), **_TmpCurrOs.run_cmd_kw)
        self.host_window.close()


def _reticle_corner_path() -> QPainterPath:
    """左上角 L 型圆角包边路径；其余三角由 ``_RETICLE_MIRRORS`` 镜像复用。"""
    path = QPainterPath()
    path.moveTo(RETICLE_INSET, RETICLE_INSET + RETICLE_ARM)
    path.lineTo(RETICLE_INSET, RETICLE_INSET + RETICLE_RADIUS)
    path.quadTo(RETICLE_INSET, RETICLE_INSET, RETICLE_INSET + RETICLE_RADIUS, RETICLE_INSET)
    path.lineTo(RETICLE_INSET + RETICLE_ARM, RETICLE_INSET)
    return path


def _reticle_colors() -> tuple[QColor, QColor]:
    """(线色, 衬边色)：色板集中在 subscribe.qss，按当前主题取 token。"""
    tokens = read_templated_qss_tokens(_QSS_PATH, theme_mgr.get_theme().value)
    return QColor(tokens["LOGIC_CELL_RETICLE"]), QColor(tokens["LOGIC_CELL_RETICLE_HALO"])


class _ReticleOverlay(QWidget):
    """取景框边角绘制层：叠在背景图之上，鼠标穿透。

    父格 paintEvent 先于子控件执行，直接画在父格会被背景图盖住，故独立成层。
    先宽衬边后细线：线要压在任意背景图上（saucenao 是暗图、acggr 是透明底），
    单色线在某一侧必然糊掉，反差衬边保证两种底都读得出来。
    线色随主题切换重取并重绘（订阅 theme_mgr）。
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setGeometry(0, 0, CELL_SIZE, CELL_SIZE)
        self._line_color, self._halo_color = _reticle_colors()
        self._theme_callback = self._on_theme_changed
        theme_mgr.subscribe(self._theme_callback)
        self.destroyed.connect(self._unsubscribe_theme)

    def _on_theme_changed(self, _theme=None):
        self._line_color, self._halo_color = _reticle_colors()
        self.update()

    def _unsubscribe_theme(self, _obj=None):
        theme_mgr.unsubscribe(self._theme_callback)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        corner = _reticle_corner_path()
        for color, width in ((self._halo_color, RETICLE_STROKE + 2 * RETICLE_HALO_PAD),
                             (self._line_color, RETICLE_STROKE)):
            pen = QPen(color, width)
            pen.setCapStyle(Qt.FlatCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            for scale_x, scale_y, offset_x, offset_y in _RETICLE_MIRRORS:
                painter.save()
                painter.translate(offset_x, offset_y)
                painter.scale(scale_x, scale_y)
                painter.drawPath(corner)
                painter.restore()


class BuiltinLogicCell(QFrame):
    """内置 icon-only 单按钮逻辑 cell 父类：结构与业务分离。

    结构（正方形几何 / 背景 cover 铺满 / 整格点击）集中在本父类，与
    cell 设计系统硬约束同源；子类只做两行类属性声明（背景 / 提示）外加一个
    ``activate`` 槽，即"新增一个内置逻辑 cell"的全部工作量。
    """

    bg_resource: str = ""             # 子类：背景资源路径（照 cell 设计系统 cover 铺满）
    tool_tip: str = ""                # 子类：tooltip 与无障碍名

    def __init__(self, gui, parent=None):
        super().__init__(parent)
        self.gui = gui
        # 独立 objectName：本类走 subscribe.qss 的 AddonsLogicCell 规则（无卡片底/边框，全透明）
        self.setObjectName("AddonsLogicCell")
        self.setFixedSize(CELL_SIZE, CELL_SIZE)

        # 背景图与其他 cell 同一套 cover 铺满规范；透明度取 85%——本类无按钮层，
        # 背景即格面本体，压到多按钮 cell 的 0.3 会糊成一片
        self.bg = ImageLabel(self)
        self.bg.setScaledContents(True)
        self.bg.setBorderRadius(9, 9, 9, 9)
        _set_cell_background(self.bg, self.bg_resource)
        bg_opacity = QGraphicsOpacityEffect(self.bg)
        bg_opacity.setOpacity(LOGIC_CELL_BG_OPACITY)
        self.bg.setGraphicsEffect(bg_opacity)
        self.bg.lower()

        # 格界由取景框边角给出（无卡片底/边框），叠在背景图之上
        self.reticle = _ReticleOverlay(self)
        self.reticle.raise_()

        # 只留铺满的背景图这一层：不叠同图 icon 按钮，也不挂底部文字说明
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(self.tool_tip)
        self.setAccessibleName(self.tool_tip)

    def sizeHint(self):
        return QSize(CELL_SIZE, CELL_SIZE)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.activate()
        super().mousePressEvent(event)

    def activate(self):
        """子类钩子：整格点击的业务动作。"""
        raise NotImplementedError


class SauceCell(BuiltinLogicCell):
    """saucenao 以图搜源格。可见性由 ``AddonsInterface.set_sauce_visible`` 驱动。"""

    bg_resource = ":/tools/saucenao.png"
    tool_tip = tools_res.search_by_pic

    def activate(self):
        def callback():
            bro = self.gui.BrowserWindow
            FluentMonkeyPatch.rbutton_menu_sauce(bro)
            target = bro.view.mapToGlobal(bro.view.rect().bottomLeft())
            target.setX(target.x() + 18)
            target.setY(target.y() - 18)
            guide = BodyLabel(tools_res.search_by_pic_guide)
            img = ImageLabel()
            img.setImage(QPixmap(":/tools/ascii2d.png"))
            CustomInfoBar.show_custom(title='', content='', parent=bro.view, _type="INFORMATION", duration=7000,
                ib_pos=InfoBarPosition.TOP_LEFT, widgets=[guide, img])
        self.gui.open_url_by_browser("https://saucenao.com/", callback)


class acggrCell(BuiltinLogicCell):
    """scriptWin 入口格（过渡壳：旧 chooseBox script 选项已退场，此格即唯一入口）。

    点击 = script 预处理（服务/依赖/数据检查 → infobar 消息）→ 隐藏 SpiderGUI → 开
    scriptWin。壳名与旧入口同寿。
    """

    bg_resource = ":/tools/acggr.png"
    tool_tip = "打开 ScriptWindow"

    def activate(self):
        # 走 PreprocessManager 的 script 入口：async 检查 → _display_message infobar
        # → _apply_action open_scriptWin
        self.gui.preprocess_mgr.run_script_entry()


class _CellMask(QWidget):
    """清理模式遮罩：父格快照模糊 + 压暗 + 居中大 rmBtn。

    用快照而非实时模糊，是因为每个 cell 只有一个 QGraphicsEffect 槽位（已被微旋转
    常驻占用）。快照挂在自己的 backdrop 标签上过 QGraphicsBlurEffect，可随格一同旋转；
    清理模式下内容静态，进入时抓一次即可。
    """

    close_clicked = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("AddonsCellMask")
        self.setGeometry(0, 0, CELL_SIZE, CELL_SIZE)
        self.backdrop = QLabel(self)
        self.backdrop.setGeometry(0, 0, CELL_SIZE, CELL_SIZE)
        self.backdrop.setScaledContents(True)
        blur = QGraphicsBlurEffect(self.backdrop)
        blur.setBlurRadius(MASK_BLUR_RADIUS)
        blur.setBlurHints(QGraphicsBlurEffect.QualityHint)
        self.backdrop.setGraphicsEffect(blur)
        self.closeBtn = TransparentToolButton(FIF.CLOSE, self)
        self.closeBtn.setIconSize(QSize(72, 72))
        self.closeBtn.setFixedSize(MASK_BTN_SIZE, MASK_BTN_SIZE)
        offset = (CELL_SIZE - MASK_BTN_SIZE) // 2
        self.closeBtn.setGeometry(offset, offset, MASK_BTN_SIZE, MASK_BTN_SIZE)
        self.closeBtn.setCursor(Qt.PointingHandCursor)
        self.closeBtn.setToolTip("删除此 cell")
        self.closeBtn.setAccessibleName("删除")
        self.closeBtn.installEventFilter(ToolTipFilter(self.closeBtn))
        self.closeBtn.clicked.connect(self.close_clicked)

    def refresh_backdrop(self):
        """抓父格内容（先隐藏自身，避免抓到自己）→ 压暗合成 → 设为模糊底图。"""
        self.hide()
        snapshot = self.parent().grab()
        self.show()
        image = snapshot.toImage()
        painter = QPainter(image)
        painter.fillRect(image.rect(), QColor(120, 120, 120, 96))
        painter.end()
        self.backdrop.setPixmap(QPixmap.fromImage(image))


class CustomCell(QFrame):
    """用户自定义格：选/换执行文件或命令行，再运行。

    比例与 ``RvCell`` 一致（只改放置、不改比例）。配置改动经 ``changed`` 交页面即时
    落盘；删除由 ``MgrCell`` 的清理管理模式触发。
    """

    changed = Signal(object)        # (更新后的 cell data dict)
    close_requested = Signal()      # 清理模式点 CLOSE：页面删格并落盘

    def __init__(self, host_window, data: dict, parent=None):
        super().__init__(parent)
        self.host_window = host_window
        self.gui = host_window.gui
        self.data = data
        self.setObjectName("AddonsCell")
        self.setFixedSize(CELL_SIZE, CELL_SIZE)

        if icon := data.get("icon"):
            bg = ImageLabel(self)
            bg.setScaledContents(True)
            bg.setBorderRadius(9, 9, 9, 9)
            _set_cell_background(bg, icon)
            bg_opacity = QGraphicsOpacityEffect(bg)
            bg_opacity.setOpacity(0.3)
            bg.setGraphicsEffect(bg_opacity)
            bg.lower()

        col = VBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(CELL_BTN_GAP)
        # bin 模式配文件夹图标、命令行模式配终端图标（qfw 无 FIF.COMMAND）
        self.executefileBtn = PrimaryPushButton(
            FIF.FOLDER if self.data.get("mode") == MODE_BIN else FIF.COMMAND_PROMPT,
            self._execute_label())
        exec_opacity = QGraphicsOpacityEffect(self.executefileBtn)
        exec_opacity.setOpacity(0.8)
        self.executefileBtn.setGraphicsEffect(exec_opacity)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(CELL_BTN_GAP)
        self.broomBtn = TransparentToolButton(FIF.BROOM, self)
        self.broomBtn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.broomBtn.setToolTip("清除已配置的执行文件/命令行（cell 保留，只清执行指定）")
        self.broomBtn.installEventFilter(ToolTipFilter(self.broomBtn))
        self.runBtn = PrimaryToolButton(FIF.PLAY)
        self.runBtn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.runBtn.setToolTip("运行")
        self.runBtn.installEventFilter(ToolTipFilter(self.runBtn))
        run_opacity = QGraphicsOpacityEffect(self.runBtn)
        run_opacity.setOpacity(0.8)
        self.runBtn.setGraphicsEffect(run_opacity)
        btn_row.addWidget(self.broomBtn)
        btn_row.addWidget(self.runBtn)
        for btn in (self.executefileBtn, self.broomBtn, self.runBtn):
            btn.setFixedHeight(CELL_ROW_H)
        col.addWidget(self.executefileBtn)
        col.addLayout(btn_row)

        self.executefileBtn.clicked.connect(self.pick_execute)
        self.broomBtn.clicked.connect(self.clear_execute)
        self.runBtn.clicked.connect(self.run)
        self._sync_state()

        # 清理模式态：遮罩懒建；微旋转 effect 常驻（angle=0 直绘源图，无副作用），动画按需启停
        self._manage_active = False
        self._mask: _CellMask | None = None
        self._wobble_phase = 0                           # 错峰相位：由页面按插入序赋值
        self._wobble = _WobbleEffect(self)
        self.setGraphicsEffect(self._wobble)
        self._wobble_anim = self._make_wobble_anim()

    def _make_wobble_anim(self) -> QVariantAnimation:
        """抖一抖停一会：burst 段用 sin² 包络起落振荡（首末严格归零），rest 段归零静默。

        各 cell 按 ``_wobble_phase`` 前置一段静默（lead），避免整片网格整齐划一地同抖。
        """
        steps = 25                                    # burst 内采样步数（30ms 级）
        burst_s = WOBBLE_BURST_MS / 1000
        total_ms = WOBBLE_BURST_MS + WOBBLE_REST_MS
        lead = (self._wobble_phase % 8) / 8 * WOBBLE_BURST_MS
        keys, last_step = [(0.0, 0.0)], 0.0
        for i in range(steps + 1):
            step = (lead + i * WOBBLE_BURST_MS / steps) / total_ms
            if step <= last_step:
                continue
            t = i / steps
            envelope = math.sin(math.pi * t) ** 2      # 0→1→0：边缘小、中间大、末态归零
            angle = WOBBLE_ANGLE * envelope * math.sin(2 * math.pi * WOBBLE_FREQ_HZ * burst_s * t)
            keys.append((step, angle))
            last_step = step
        keys.append((1.0, 0.0))                        # rest 段恒零（直绘源图，无副作用）
        anim = QVariantAnimation(self)
        anim.setDuration(total_ms)
        anim.setLoopCount(-1)
        anim.setKeyValues(keys)
        anim.valueChanged.connect(lambda v: self._wobble.setAngle(float(v)))
        return anim

    def set_manage_mode(self, active: bool):
        """清理模式：动作钮置灰 + 遮罩 + CLOSE 钮 + 整格微旋转；退出即复原。"""
        self._manage_active = active
        self.executefileBtn.setEnabled(not active)
        self.runBtn.setEnabled(not active)
        self.broomBtn.setEnabled(not active and self._is_configured())
        if active:
            if self._mask is None:
                self._mask = _CellMask(self)
                self._mask.close_clicked.connect(self.close_requested)
            self._mask.raise_()
            self._mask.refresh_backdrop()   # 须在 show 前刷新（刷新时要隐藏自身抓父格）
            self._mask.show()
            self._wobble_anim.start()
        else:
            if self._mask is not None:
                self._mask.hide()
            self._wobble_anim.stop()
            self._wobble.setAngle(0.0)

    def sizeHint(self):
        return QSize(CELL_SIZE, CELL_SIZE)

    def _execute_label(self) -> str:
        if self.data.get("mode") == MODE_BIN:
            return Path(self.data["path"]).name if self.data.get("path") else "选择执行文件"
        return "命令行"

    def _is_configured(self) -> bool:
        return bool(self.data.get("path") if self.data.get("mode") == MODE_BIN else self.data.get("cmd"))

    def _sync_state(self):
        self.executefileBtn.setText(self._execute_label())
        # 只展示文件名（含后缀），不展示路径；命令行模式 tooltip 展示全文
        tip = self._execute_label()
        if self.data.get("cmd"):
            tip = self.data["cmd"]
        self.executefileBtn.setToolTip(tip)
        self.broomBtn.setEnabled(self._is_configured())

    def pick_execute(self):
        """bin 模式选/换执行文件；cmd 模式编辑命令行。改动经 changed 落盘。"""
        if self.data.get("mode") == MODE_BIN:
            file, _ = QFileDialog.getOpenFileName(self, ori_res.GUI.Uic.sv_path_desc_tip)
            if not file:
                return
            self.data["path"] = file
        else:
            dialog = CommandEditDialog(self.data.get("cmd") or "", self.host_window)
            if not (dialog.exec() and dialog.command):
                return
            self.data["cmd"] = dialog.command
        self._sync_state()
        self.changed.emit(self.data)

    def clear_execute(self):
        if self.data.get("mode") == MODE_BIN:
            self.data["path"] = ""
        else:
            self.data["cmd"] = ""
        self._sync_state()
        self.changed.emit(self.data)

    def run(self):
        if self.data.get("mode") == MODE_BIN:
            path = Path(self.data["path"])
            if not path.is_file():
                InfoBar.warning(title="", content=f"执行文件不存在：{path}", parent=self,
                                position=InfoBarPosition.TOP, duration=4000)
                return
            subprocess.Popen([str(path)], cwd=str(path.parent), start_new_session=True)
        else:
            cmd = self.data.get("cmd") or ""
            if not cmd:
                InfoBar.warning(title="", content="命令行为空", parent=self,
                                position=InfoBarPosition.TOP, duration=4000)
                return
            # 与 rvCell.run 同款脱离参数（Windows 下 DETACHED_PROCESS 免得闪控制台窗）
            subprocess.Popen(cmd, **_TmpCurrOs.run_cmd_kw)
        self.host_window.close()


class MgrCell(QFrame):
    """常驻网格末位的管理格：上 addBtn 新增自定义 cell，下 rmBtn 切清理管理模式。

    清理模式下自定义 cell 动作钮置灰 + 遮罩 + 居中 CLOSE 钮 + 整格微旋转抖动；
    点 CLOSE 直接删格并落盘，再点 rmBtn 退出。
    """

    clicked = Signal()              # addBtn：弹自定义 cell 创建对话框
    manage_toggled = Signal(bool)   # rmBtn：清理管理模式开关

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AddonsMgrCell")
        self.setFixedSize(CELL_SIZE, CELL_SIZE)

        col = VBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(CELL_BTN_GAP)
        # 上下两钮各占半格、铺满宽高（需显式传 Qt.Alignment()，qfluent VBox 默认 AlignTop 不填充）
        self.addBtn = TransparentToolButton(FIF.ADD)
        self.addBtn.setIconSize(QSize(40, 40))
        self.addBtn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.addBtn.setToolTip("添加自定义 cell")
        self.addBtn.setAccessibleName("添加")
        self.addBtn.installEventFilter(ToolTipFilter(self.addBtn))
        self.addBtn.clicked.connect(self.clicked.emit)
        col.addWidget(self.addBtn, 1, Qt.Alignment())
        self.rmBtn = ToggleToolButton(FIF.DELETE)
        self.rmBtn.setIconSize(QSize(40, 40))
        self.rmBtn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.rmBtn.setToolTip("清理管理模式（再点退出）")
        self.rmBtn.setAccessibleName("清理管理")
        self.rmBtn.installEventFilter(ToolTipFilter(self.rmBtn))
        self.rmBtn.toggled.connect(self.manage_toggled)
        # 激活态浅红 = subscribe.qss 的 danger 按钮变种（色板规则集中在 qss，py 只标记）
        self.rmBtn.setProperty("variant", "danger")
        apply_button_variant(self.rmBtn)
        col.addWidget(self.rmBtn, 1, Qt.Alignment())

    def sizeHint(self):
        return QSize(CELL_SIZE, CELL_SIZE)


class _GridHost(QWidget):
    """FlowLayout 宿主：widgetResizable 滚动区只认 widget 最小高，故宿主每次变宽/变窄后
    都要重算最小高（行数随宽 reflow）。"""

    def __init__(self, page, parent=None):
        super().__init__(parent)
        self._page = page

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._page._sync_grid_height()


class AddonsInterface(QWidget):
    """addonsInterface 页（挂 ToolWorkspaceWindow pivot，显示名 addons）。"""

    def __init__(self, gui, parent=None, *, host_window=None):
        super().__init__(parent)
        self.gui = gui
        # 动作后关窗的宿主窗口（ToolWorkspaceWindow）。
        self.host_window = host_window or parent
        self.setObjectName("addonsInterface")
        # 懒构造：本页首次 show 才建全部 cell
        self.rvCell = None
        self.acggrCell = None
        self.sauceCell = None
        self.mgrCell = None
        self.customCells: list[CustomCell] = []
        self._cells_built = False
        self._sauce_visible = False
        self._manage_mode = False
        self.init_ui()

    def init_ui(self):
        main = VBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        self.grid_scroll = SingleDirectionScrollArea(self, Qt.Orientation.Vertical)
        self.grid_scroll.setObjectName("AddonsGridScroll")
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.grid_scroll.enableTransparentBackground()
        self.grid_host = _GridHost(self, self.grid_scroll)
        self.grid_host.setObjectName("AddonsGridHost")
        self.grid_flow = FlowLayout(self.grid_host)
        self.grid_flow.setContentsMargins(0, 0, 0, 0)
        self.grid_flow.setHorizontalSpacing(GRID_GAP)
        self.grid_flow.setVerticalSpacing(GRID_GAP)
        self.grid_scroll.setWidget(self.grid_host)
        # 需显式传 Qt.Alignment()：qfluent VBoxLayout.addWidget 默认 AlignTop，stretch 不填充。
        main.addWidget(self.grid_scroll, 1, Qt.Alignment())

    def showEvent(self, event):
        super().showEvent(event)
        self._ensure_cells()
        self._sync_grid_height()

    def set_sauce_visible(self, visible: bool):
        """sauceCell 按站点是否 R18 条件可见；页尚未构造时只记意图。"""
        self._sauce_visible = bool(visible)
        if self.sauceCell is not None:
            self.sauceCell.setVisible(self._sauce_visible)
        self._sync_grid_height()

    def _ensure_cells(self):
        """网格顺序：rvCell → acggrCell（常驻）→ sauceCell（条件）→ 自定义 cell（创建序）→ mgrCell（末位）。"""
        if self._cells_built:
            return
        self._cells_built = True
        self.rvCell = RvCell(self.host_window, self.grid_host)
        self.grid_flow.addWidget(self.rvCell)
        self.acggrCell = acggrCell(self.gui, self.grid_host)
        self.grid_flow.addWidget(self.acggrCell)
        self.sauceCell = SauceCell(self.gui, self.grid_host)
        self.sauceCell.setVisible(self._sauce_visible)
        self.grid_flow.addWidget(self.sauceCell)
        for data in cgs_cfg.addonsCells.value:
            self._insert_custom_cell(data)
        self.mgrCell = MgrCell(self.grid_host)
        self.mgrCell.clicked.connect(self._on_add_cell)
        self.mgrCell.manage_toggled.connect(self._set_manage_mode)
        self.grid_flow.addWidget(self.mgrCell)

    def _set_manage_mode(self, active: bool):
        """清理模式开关：全部自定义 cell 置灰 + 遮罩 + CLOSE + 微旋转。"""
        self._manage_mode = active
        for cell in self.customCells:
            cell.set_manage_mode(active)

    def _insert_custom_cell(self, data: dict):
        cell = CustomCell(self.host_window, data, self.grid_host)
        cell.changed.connect(self._on_cell_changed)
        cell.close_requested.connect(lambda: self._remove_custom_cell(cell))
        cell._wobble_phase = len(self.customCells)   # 按插入序确定错峰，保证可复现
        cell._wobble_anim = cell._make_wobble_anim()
        cell.set_manage_mode(self._manage_mode)
        self.customCells.append(cell)
        index = self.grid_flow.indexOf(self.mgrCell)
        if index < 0:
            self.grid_flow.addWidget(cell)
        else:
            self.grid_flow.insertWidget(index, cell)

    def _remove_custom_cell(self, cell: CustomCell):
        """清理模式删除：直接移除并同步 yml 记录（无二次确认）。"""
        name = cell.data.get("name")
        self.grid_flow.removeWidget(cell)
        if cell in self.customCells:
            self.customCells.remove(cell)
        cell.hide()
        cell.deleteLater()
        cgs_cfg.addonsCells.value = [c for c in cgs_cfg.addonsCells.value if c.get("name") != name]
        cgs_cfg.save()
        self._sync_grid_height()

    def _on_cell_changed(self, data: dict):
        """cell 内改配置（换执行文件 / 编辑命令行 / 清理）即时落盘。"""
        cgs_cfg.addonsCells.value = [
            data if c.get("name") == data.get("name") else c for c in cgs_cfg.addonsCells.value]
        cgs_cfg.save()

    def _on_add_cell(self):
        dialog = CustomCellDialog([c.data.get("name") for c in self.customCells], self.host_window)
        if not (dialog.exec() and dialog.cell_data):
            return
        data = dialog.cell_data
        cells = list(cgs_cfg.addonsCells.value)
        cells.append(data)
        cgs_cfg.addonsCells.value = cells
        cgs_cfg.save()
        self._insert_custom_cell(data)
        self._sync_grid_height()

    def _sync_grid_height(self):
        self.grid_host.setMinimumHeight(self.grid_flow.heightForWidth(max(1, self.grid_host.width())))
