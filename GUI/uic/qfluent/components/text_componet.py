from PyQt5.QtCore import QTimer, QSize
from PyQt5.QtGui import QPixmap
from qfluentwidgets import ImageLabel, TextBrowser, TextEdit


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


class TextEditWithBg(TextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_label = None
        self.image_path = None
        self.image_margin = 0

    def set_fixed_image(self, image_path, height=None, margin=0):
        self.image_path = image_path
        self.image_margin = margin
        if self.image_label:
            self.image_label.setParent(None)
            self.image_label.deleteLater()
            QTimer.singleShot(20, lambda: self.set_fixed_image(image_path, height, margin))
        else:
            self.image_label = ImageLabel(self)
            self.image_label.hide()  
            self.image_label.setScaledContents(True)
        pixmap = QPixmap(self.image_path)
        if pixmap.isNull():
            self.image_label.hide()
            return
        self.image_label.setImage(pixmap)
        self.image_label.lower()

    def img_resize_and_repos(self):
        if not self.image_label or not self.image_path:
            return
        pixmap = self.image_label.pixmap()
        if not pixmap or pixmap.isNull() or pixmap.height() == 0:
            return
        # resize
        current_height = self.height() - self.image_margin
        new_width = int(current_height * pixmap.width() / pixmap.height())
        self.image_label.setFixedSize(QSize(new_width, current_height))
        # repos
        rect = self.rect()
        x = rect.width() - self.image_label.width() - self.image_margin
        y = rect.height() - self.image_label.height() - self.image_margin
        self.image_label.move(x, y)
        if not self.image_label.isVisible():
            self.image_label.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.image_label:
            QTimer.singleShot(0, self.img_resize_and_repos)
