from PyQt5.QtCore import QTimer
from qfluentwidgets import ImageLabel, TextBrowser


class TextBrowserWithBg(TextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_label = None
        self.setStyleSheet("""
            QTextBrowser {
                background-color: transparent;
            }
        """)

    def set_fixed_image(self, image_path, height=None, margin=0):
        if self.image_label:
            self.image_label.setParent(None)
            self.image_label.deleteLater()

        # 创建新的图片标签
        self.image_label = ImageLabel(self)
        self.image_label.setImage(image_path)
        if not height:
            height = int(self.height()*1.0)
        pixmap = self.image_label.pixmap()
        if pixmap.isNull() or pixmap.height() == 0:
            self.image_label = None
            return
        self.image_label.setFixedSize(int(height * (pixmap.width() / pixmap.height())), height)
        self.image_label.setScaledContents(True)

        self.image_margin = margin

        self.position_image()
        self.image_label.lower()
        self.image_label.show()

    def remove_fixed_image(self):
        if self.image_label:
            self.image_label.setParent(None)
            self.image_label.deleteLater()
            self.image_label = None

    def position_image(self):
        if not self.image_label:
            return
        rect = self.rect()
        margin = getattr(self, 'image_margin', 15)
        x = rect.width() - self.image_label.width() - margin
        y = rect.height() - self.image_label.height() - margin

        self.image_label.move(x, y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.image_label:
            QTimer.singleShot(0, self.position_image)
