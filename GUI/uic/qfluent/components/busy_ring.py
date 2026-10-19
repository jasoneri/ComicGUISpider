from PySide6.QtWidgets import QWidget
from qfluentwidgets import IndeterminateProgressRing, ProgressRing


class BusyRingHost(QWidget):
    """按钮槽位忙碌指示器·基形（单环，仅 IndeterminateProgressRing）。

    主体语义：busy 时取代目标按钮的槽位——按钮 hide、宿主 show 并开始旋转；
    空闲时反向。无确定进度的业务（如 WebDAV 读写测试）用基形即可；
    底环承载确定进度的双环是变种 DualBusyRingHost，经 make(determinate=True) 创建。
    尺寸（宿主 / 内环 / 描边）实例化可调，内环始终居中于宿主。
    """

    DEFAULT_SIZE = 36
    DEFAULT_INNER_SIZE = 18
    DEFAULT_STROKE_WIDTH = 3

    def __init__(self, parent=None, *, button, size=None, inner_size=None, stroke_width=None, object_name=""):
        super().__init__(parent)
        self._button = button
        self._size = int(size or self.DEFAULT_SIZE)
        self._inner_size = int(inner_size or self.DEFAULT_INNER_SIZE)
        self._stroke_width = int(stroke_width or self.DEFAULT_STROKE_WIDTH)
        self._busy = False
        if object_name:
            self.setObjectName(object_name)
        self.setFixedSize(self._size, self._size)
        self.indeterminate_ring = IndeterminateProgressRing(self, start=False)
        self.indeterminate_ring.setFixedSize(self._inner_size, self._inner_size)
        self.indeterminate_ring.setStrokeWidth(self._stroke_width)
        self.indeterminate_ring.raise_()
        self._place_inner_ring()
        self.hide()

    @classmethod
    def make(cls, parent, button, *, determinate=False, size=None, inner_size=None, stroke_width=None,
             object_name=""):
        """工厂：determinate=True 产双环变种（底环承载确定进度），否则产基形单环。"""
        host_cls = DualBusyRingHost if determinate else BusyRingHost
        return host_cls(parent, button=button, size=size, inner_size=inner_size, stroke_width=stroke_width,
                        object_name=object_name)

    @property
    def size(self) -> int:
        return self._size

    @property
    def inner_size(self) -> int:
        return self._inner_size

    @property
    def stroke_width(self) -> int:
        return self._stroke_width

    def apply_sizes(self, size=None, inner_size=None, stroke_width=None):
        """实例化后调整尺寸；内环始终居中于宿主。"""
        if size is not None:
            self._size = int(size)
        if inner_size is not None:
            self._inner_size = int(inner_size)
        if stroke_width is not None:
            self._stroke_width = int(stroke_width)
        self.setFixedSize(self._size, self._size)
        self.indeterminate_ring.setFixedSize(self._inner_size, self._inner_size)
        self.indeterminate_ring.setStrokeWidth(self._stroke_width)
        self._place_inner_ring()

    def set_busy(self, busy: bool):
        """按钮槽位显隐切换 + 旋转起止；状态未变则空转返回（不会叠加动画）。"""
        if busy == self._busy:
            return
        self._busy = busy
        if busy:
            self._button.hide()
            self.show()
            self.indeterminate_ring.show()
            self.indeterminate_ring.start()
        else:
            self.indeterminate_ring.stop()
            self.hide()
            self._button.show()

    def _place_inner_ring(self):
        offset = (self._size - self._inner_size) // 2
        self.indeterminate_ring.move(offset, offset)


class DualBusyRingHost(BusyRingHost):
    """双环变种：ProgressRing 底环承载确定进度（set_value），内环持续旋转表示运行中。"""

    def __init__(self, parent=None, *, button, size=None, inner_size=None, stroke_width=None, object_name=""):
        super().__init__(parent, button=button, size=size, inner_size=inner_size, stroke_width=stroke_width,
                         object_name=object_name)
        self.ring = ProgressRing(self)
        self.ring.setTextVisible(False)
        self.ring.setFixedSize(self._size, self._size)
        self.ring.setRange(0, 100)
        self.ring.move(0, 0)
        self.indeterminate_ring.raise_()

    def apply_sizes(self, size=None, inner_size=None, stroke_width=None):
        super().apply_sizes(size, inner_size, stroke_width)
        self.ring.setFixedSize(self._size, self._size)

    def set_value(self, percent):
        """底环确定进度（0-100）；无确定进度时传 0 即纯底环。"""
        self.ring.setValue(int(percent))
