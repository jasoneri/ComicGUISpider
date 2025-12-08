import asyncio

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QWidget
from qfluentwidgets import (
    VBoxLayout, PrimaryPushButton, 
    HyperlinkButton, FluentIcon as FIF, StrongBodyLabel,
    InfoBadge, InfoBadgePosition, InfoBar, InfoBarPosition
)

from assets import res as ori_res
from utils import temp_p

tools_res = ori_res.GUI.Tools


class PublishPageToolView(QWidget):
    """发布页面测试工具
    
    功能:
    1. 接收选中的文本（URL或域名）
    2. 测试可用性
    3. 显示测试结果
    4. 提供跳转到发布URL的快捷方式
    """
    
    def __init__(self, parent=None):
        super().__init__()
        self.gui = parent
        self.spiderUtils = self.gui.spiderUtils
        self.init_ui()

    def init_ui(self):
        """初始化UI界面"""
        self.main_layout = VBoxLayout(self)
        self.setLayout(self.main_layout)
        
        # 第一行：描述和说明
        first_row = QHBoxLayout()
        desc = StrongBodyLabel("发布页面快速测试工具")
        first_row.addStretch()
        first_row.addWidget(desc)
        first_row.addStretch()
        
        # 第二行：操作按钮
        self.second_row = QHBoxLayout()
        self.second_row.addStretch()
        
        goBtn = HyperlinkButton(
            FIF.LINK, 
            self.gui.spiderUtils.publish_url, 
            '发布页'
        )
        
        testBtn = PrimaryPushButton(
            FIF.COMMAND_PROMPT, 
            '测试选中文本', 
            self
        )
        testBtn.clicked.connect(self.handle_selected_text)
        
        self.second_row.addWidget(goBtn)
        self.second_row.addWidget(testBtn)
        self.second_row.addStretch()
        
        self.main_layout.addLayout(first_row)
        self.main_layout.addLayout(self.second_row)

    def handle_selected_text(self):
        """处理选中的文本
        
        流程:
        1. 从剪贴板获取文本（实际应用中应从右键菜单获取选定文本）
        2. 调用测试函数进行检验
        3. 显示测试结果（成功/失败）
        4. 根据结果进行后续操作
        """
        # 获取剪贴板中的文本
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        
        if not text:
            InfoBar.error(
                title='',
                content="请先选中或复制文本到剪贴板",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            return
        
        # 执行测试
        self._test_text(text)

    def handle(self, texts: str):
        """处理传入的文本（供右键菜单调用）
        
        Args:
            texts: 选中的文本
        """
        if not texts or not texts.strip():
            InfoBar.error(
                title='',
                content="没有获取到有效的文本",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            return
        
        self._test_text(texts.strip())

    def _test_text(self, text: str):
        """测试文本的有效性
        
        Args:
            text: 要测试的文本（URL或域名）
        """
        try:
            # 这里应该调用spiderUtils的测试方法
            # 示例：测试URL或域名是否可访问
            loop = asyncio.get_event_loop()
            
            # 调用异步测试函数（如果spiderUtils提供）
            if hasattr(self.spiderUtils, 'test_aviable_domain'):
                result = loop.run_until_complete(
                    self.spiderUtils.test_aviable_domain(text)
                )
            else:
                # 备用方案：基本的有效性检查
                result = self._basic_test(text)
            
            # 显示测试结果
            if result:
                self._show_success_result(text, result)
            else:
                self._show_error_result(text)
                
        except Exception as e:
            self._show_error_result(text, str(e))

    def _basic_test(self, text: str) -> bool:
        """基础测试（如果spiderUtils没有提供测试方法）
        
        Args:
            text: 要测试的文本
            
        Returns:
            bool: 测试是否通过
        """
        # 简单的URL或域名格式检查
        import re
        
        url_pattern = r'^https?://[^\s]+$'
        domain_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z]{2,})+$'
        
        return bool(
            re.match(url_pattern, text) or 
            re.match(domain_pattern, text)
        )

    def _show_success_result(self, text: str, result=None):
        """显示成功的测试结果
        
        Args:
            text: 测试的文本
            result: 测试结果
        """
        # 添加成功标记
        self.second_row.insertWidget(
            3,
            InfoBadge.success(
                text,
                parent=self,
                target=self.second_row,
                position=InfoBadgePosition.RIGHT
            )
        )
        
        # 显示成功提示
        success_msg = f"✓ '{text}' 测试通过"
        InfoBar.success(
            title='',
            content=success_msg,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=4000,
            parent=self
        )
        
        # 3秒后关闭工具窗口
        QTimer.singleShot(4000, self.close_later)

    def _show_error_result(self, text: str, error_msg: str = None):
        """显示失败的测试结果
        
        Args:
            text: 测试的文本
            error_msg: 错误信息
        """
        # 添加错误标记
        self.second_row.insertWidget(
            3,
            InfoBadge.error(
                text,
                parent=self,
                target=self.second_row,
                position=InfoBadgePosition.RIGHT
            )
        )
        
        # 显示错误提示
        error_content = f"✗ '{text}' 测试失败"
        if error_msg:
            error_content += f": {error_msg}"
        
        InfoBar.error(
            title='',
            content=error_content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self
        )

    def close_later(self):
        """延迟关闭工具窗口
        
        逻辑参考: DomainToolView.close_later
        """
        self.gui.toolWin.close()
        # 可选：触发重试按钮
        if hasattr(self.gui, 'retrybtn'):
            self.gui.retrybtn.click()
