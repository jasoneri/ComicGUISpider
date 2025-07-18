import io
import random
from PyQt5.QtCore import QSize
from PyQt5.QtGui import QIcon, QMovie, QPixmap
from qfluentwidgets import (
    ImageLabel, SplashScreen
)
from PIL import Image, ImageFilter, ImageDraw
from utils import ori_path, conf

cus_p = ori_path.joinpath(r"custom")


class BgMgr:
    def __init__(self):
        self.start_bg_f, self.start_ext = self._find_start_bg()
        self.bg_f, self.ext = self._find_bg()
        self.movie = None

    def _find_bg(self):
        target_dir = conf.bg_path
        if not target_dir or str(target_dir) == "." or not target_dir.is_dir():
            return None, None
        matched_files = []
        for file in target_dir.rglob('*.png'):
            matched_files.append((file.as_posix(), file.suffix))
        if matched_files:
            return random.choice(matched_files)
        return None, None

    def _find_start_bg(self, kind: str = "start"):
        valid_exts = ('.gif', '.png')
        matched_files = []
        for file in cus_p.iterdir():
            if file.is_file() and file.suffix.lower() in valid_exts:
                matched_files.append((file.as_posix(), file.suffix))
        if matched_files:
            return random.choice(matched_files)
        return None, None

    def create_edge_blur_image(self, pil_image, fade_distance=50, blur_radius=10):
        """创建边界模糊效果的PIL图片"""
        try:
            img = pil_image.convert('RGBA')
            width, height = img.size

            # 创建渐变遮罩
            mask = Image.new('L', (width, height), 255)
            draw = ImageDraw.Draw(mask)

            # 创建边界渐变效果
            for i in range(fade_distance):
                alpha = int(255 * (i / fade_distance))
                draw.rectangle([i, i, width-1-i, height-1-i], outline=alpha)

            # 应用高斯模糊到遮罩
            mask = mask.filter(ImageFilter.GaussianBlur(blur_radius))
            img.putalpha(mask)

            return img

        except Exception as e:
            print(f"边界模糊处理失败: {e}")
            return pil_image.convert('RGBA')

    def apply_full_blur(self, pil_image, blur_radius=15):
        """在PIL图片基础上应用整体模糊"""
        return pil_image.filter(ImageFilter.GaussianBlur(blur_radius))

    def create_splash_pil_image(self, fade_distance=80, blur_radius=25):
        """为启动画面创建PIL图片"""
        if not self.start_bg_f or self.start_ext == '.gif':
            return None

        # 打开图像文件并应用边界模糊效果
        pil_image = Image.open(self.start_bg_f)
        return self.create_edge_blur_image(
            pil_image, fade_distance=fade_distance, blur_radius=blur_radius
        )


class CustomSplashScreen(SplashScreen):
    def __init__(self, parent=None, enableShadow=True):
        self.gui = parent
        self.gui.bg_mgr = BgMgr()

        if self.gui.bg_mgr.start_bg_f:
            ico = QIcon()
        else:
            ico = QIcon(":/guide.png")

        super(CustomSplashScreen, self).__init__(ico, parent, enableShadow)
        self.titleBar.minBtn.hide()
        self.titleBar.maxBtn.hide()
        self.titleBar.closeBtn.hide()

        if self.gui.bg_mgr.start_bg_f:
            self._set_start_bg()
        else:
            height = int(self.gui.height() * 0.7)
            self.setIconSize(QSize(height, height))
        
        if self.gui.bg_mgr.bg_f:
            self.gui.bg_f = self.gui.bg_mgr.bg_f
            self.gui.textBrowser.set_fixed_image(self.gui.bg_f)

    @staticmethod
    def pil_to_qpixmap(pil_image):
        img_bytes = io.BytesIO()
        pil_image.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        pixmap = QPixmap()
        pixmap.loadFromData(img_bytes.getvalue())
        return pixmap

    def _set_start_bg(self):
        def scale_pixmap_to_size(pixmap, target_width, target_height):
            """将QPixmap缩放到指定尺寸"""
            if pixmap.isNull():
                return pixmap
            return pixmap.scaled(target_width, target_height, aspectRatioMode=1)

        self.iconWidget = ImageLabel(self)
        self.iconWidget.setScaledContents(True)

        target_height = self.gui.height()

        if self.gui.bg_mgr.start_ext == '.gif':
            self.gui.bg_mgr.movie = QMovie(str(self.gui.bg_mgr.start_bg_f))
            self.iconWidget.setMovie(self.gui.bg_mgr.movie)
            self.gui.bg_mgr.movie.start()
            pixmap = self.gui.bg_mgr.movie.currentPixmap()
        else:
            pil_img = self.gui.bg_mgr.create_splash_pil_image()
            pixmap = self.pil_to_qpixmap(pil_img)

        # 先根据原图比例计算正确的容器尺寸
        target_width = target_height if pixmap.isNull() \
            else int(target_height * pixmap.width() / pixmap.height())

        # 设置容器尺寸
        self.iconWidget.setFixedSize(target_width, target_height)
        self.setIconSize(QSize(target_width, target_height))

        # 最后让pixmap适应容器尺寸
        if self.gui.bg_mgr.start_ext != '.gif':
            scaled_pixmap = scale_pixmap_to_size(pixmap, target_width, target_height)
            self.iconWidget.setPixmap(scaled_pixmap)
