import os
import time
from multiprocessing import Manager, Process, freeze_support
from multiprocessing.managers import RemoteError

from PyQt5.QtCore import QThread, Qt, pyqtSignal, QCoreApplication
from PyQt5.QtWidgets import QDialog, QMainWindow

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from GUI.ui_mainwindow import Ui_MainWindow
from GUI.ui_ensure_dia import Ui_FinEnsureDialog
from GUI.ui_helplabel import Ui_HelpLabel
from utils import judge_input, clear_queue, cLog, font_color
import traceback


class FinEnsureDialog(QDialog, Ui_FinEnsureDialog):
    def __init__(self, parent=None):
        super(FinEnsureDialog, self).__init__(parent)
        self.setupUi(self)

    def setupUi(self, ensureDialog):
        super(FinEnsureDialog, self).setupUi(ensureDialog)


class SpiderGUI(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super(SpiderGUI, self).__init__(parent)
        self.dia = FinEnsureDialog()
        self.log = cLog(name="GUI")
        # self.log.debug(f'-*- 主进程id {os.getpid()}')
        # self.log.debug(f'-*- 主线程id {threading.currentThread().ident}')
        self.setupUi(self)

    def setupUi(self, MainWindow):
        super(SpiderGUI, self).setupUi(MainWindow)
        self.helpbtn.setFocus()
        self.textBrowser.setText(''.join(text))

        self.progressBar.setStyleSheet(r'QProgressBar {text-align: center; border-color: #0000ff;}'
                                       r'QProgressBar::chunk {background-color: #0cc7ff; width: 3px;}')

        self.helplabel = Ui_HelpLabel(self.centralwidget)

        # self.palette = QPalette()
        # brush = QBrush(QColor(255, 0, 0))
        # brush.setStyle(Qt.SolidPattern)
        # self.palette.setBrush(QPalette.Active, QPalette.Text, brush)

        self.helpclickCnt = 0
        self.nextclickCnt = 0
        # 初始化与后端爬虫的通信管道
        self.print_Q = Manager().Queue()
        self.bar = Manager().Queue()
        self.current_status = {'keyword':None, 'choose':None, 'retry':False}
        self.current_Q = Manager().Queue(2)
        self.retry_Q = Manager().Queue(1)
        self.step = 'origin'
        self.step_Q = Manager().Queue(1)
        self.btn_logic()

        def status_tip(index):
            text = {0: None,
                    1: '90MH网：（1）输入【搜索词】返回搜索结果（2）可输入【更新】【排名】..字如其名',
                    2: 'kukuM网：（1）输入【搜索词】返回搜索结果（2）可输入【更新】【推荐】..字如其名',
                    3: 'joyhentai网：（1）输入【搜索词】返回搜索结果（2）可输入【最新】【日排名】【周排名】【月排名】..字如其名'}
            self.searchinput.setStatusTip(QCoreApplication.translate("MainWindow", text[index]))
        self.chooseBox.currentIndexChanged.connect(status_tip)

        self.show()

    def btn_logic(self):
        def search_btn(text):
            self.next_btn.setEnabled(len(text) > 6) if self.chooseBox.currentIndex() in [1, 2, 3] else None
        self.searchinput.textChanged.connect(search_btn)
        # self.next_btn.setEnabled(True)
        self.crawl_btn.clicked.connect(self.crawl)
        self.retrybtn.clicked.connect(self.retry_schedule)
        self.next_btn.clicked.connect(self.next_schedule)

    def params_send(self, update_what):
        self.current_status.update(update_what)
        self.current_Q.put(self.current_status)

    @staticmethod
    def warning_(text):
        return font_color(text)

    def step_recv(self):
        try:
            self.step = self.step_Q.get(timeout=0.1)
        except Exception as e:
            # print(f"{e} text change conn… ")
            pass
        else:
            self.step_Q.task_done()
        QThread.msleep(5)
        return self.step

    def show_help(self):
        self.helplabel.hide() if self.helpclickCnt%2 else self.helplabel.show()
        self.helpclickCnt += 1

    def judge_retry(self):
        # 发出retry信号供后端爬虫识别，本GUI下判断spider的retry容易产生逻辑混乱
        self.params_send({'retry': False})

    def retry_schedule(self):
        self.log.info(f'===--→ retrying…… after step: {self.step_recv()}')

        def retry_middle():
            self.chooseinput.setEnabled(True)
            self.crawl_btn.setDisabled(True)

        def retry_all():
            self.textBrowser.setStyleSheet('background-color: red;')
            self.textbrowser_load(font_color('…………重启爬虫中，会卡个几秒', size=6))
            self.retrybtn.setToolTip(QCoreApplication.translate("MainWindow", "retry重启时会卡几秒，等等"))
            QThread.msleep(200)
            try:
                clear_queue((self.step_Q, self.current_Q, self.print_Q))
                time.sleep(0.8)
                self.p.kill()
                self.p.join()
                self.p.close()
                self.bThread.active = False
                self.bThread.quit()  # 关闭线程
                self.bThread.wait()
            except (FileNotFoundError, RemoteError, ConnectionRefusedError, ValueError, BrokenPipeError) as e:
                self.log.error(str(traceback.format_exc()))
                # self.log.warning(f'when retry_all occur {e.args}')
            self.setupUi(self)

        retry_do_what = {'search': retry_all,
                         'origin': retry_all,
                         'parse': retry_middle,
                         'parse section': lambda: self.chooseinput.setEnabled(True),
                         'fin': retry_all}

        self.params_send({'retry': True})
        QThread.msleep(5)
        self.log.debug(f"after retry spider'step : {self.step_recv()}")
        retry_do_what[self.step]()
        self.retrybtn.setDisabled(True)
        if self.step == 'parse section':
            if self.book_num > 1 or self.book_choose == [0]:
                self.textBrowser.append(self.warning_(f'<br>{"*" * 20}警告！！检测到选择多本书的情况下retry会产生重复操作，已选并确认的可能成功了，<br>' +
                                                      '但为避免错误程序仍重新启动, 请等候<br>'))
                self.log.warning(f' ! choose many book also click retry ')
                QThread.msleep(1500)
                self.close()
                retry_all()
        self.log.debug('===--→ retry_schedule end\n')

    def next_schedule(self):
        def start_and_search():
            self.log.debug('===--→ -*- searching')
            self.next_btn.setText('Next')
            keyword = self.searchinput.text()[6:].strip()
            index = self.chooseBox.currentIndex()
            # 将GUI的网站序号结合搜索关键字 →→ 开多线程or进程后台处理scrapy，线程检测spider发送的信号

            if self.nextclickCnt == 0:          # 从section步 回parse步 的话以免重开
                self.bThread = WorkThread(self)

                def crawl_btn(text):
                    if len(text) > 5:
                        self.crawl_btn.setEnabled(self.step_recv()=='parse section')
                        self.next_btn.setDisabled(self.crawl_btn.isEnabled())
                self.chooseinput.textChanged.connect(crawl_btn)

                self.p = Process(target=crawl_what, args=(index, self.print_Q, self.bar, self.current_Q, self.step_Q))

                self.bThread.print_signal.connect(self.textbrowser_load)
                self.bThread.item_count_signal.connect(self.processbar_load)
                self.bThread.finishSignal.connect(self.crawl_end)

                self.p.start()
                self.bThread.start()
                self.log.info(f'-*-*- Background thread & spider starting')

            self.chooseBox.setDisabled(True)
            self.params_send({'keyword':keyword})
            self.log.debug(f'website_index:[{index}], keyword [{keyword}] success ')

        def _next():
            self.log.debug('===--→ nexting')
            self.judge_retry()                                  # 非retry的时候先把retry=Flase解锁spider的下一步
            choose = judge_input(self.chooseinput.text()[5:].strip())
            if self.nextclickCnt == 1:
                self.book_choose = choose if choose!=[0] else [_ for _ in range(1, 11)]  # 选0的话这里要爬虫返回书本数量数据，还要加个Queue
                self.book_num = len(self.book_choose)
                if self.book_num > 1:
                    self.log.info('book_num > 1')
                    self.textBrowser.append(self.warning_(f'<br>{"*" * 20}警告！！多选书本时不要随意使用 retry<br>'))
            self.chooseinput.clear()
            # choose逻辑 交由crawl, next,retry3个btn的schedule控制
            self.params_send({'choose': choose})
            self.log.debug(f'send choose: {choose} success')

        self.retrybtn.setEnabled(True)
        if self.next_btn.text()!='搜索':
            _next()
        else:
            start_and_search()

        self.nextclickCnt += 1
        self.searchinput.setEnabled(False)
        # self.next_btn.setEnabled(False)
        self.chooseinput.setFocusPolicy(Qt.StrongFocus)

        self.step_recv()
        self.log.debug(f"===--→ next_schedule end (now step: {self.step})\n")

    def crawl(self):
        def dia_text(_str):
            self.dia.textEdit.append(self.warning_(_str) if 'notice' in _str else _str)

        choose = judge_input(self.chooseinput.text()[5:].strip())
        self.log.debug(f'===--→ click down crawl_btn')
        self.dia.textEdit.clear()
        self.bThread.print_signal.disconnect(self.textbrowser_load)
        self.bThread.print_signal.connect(dia_text)

        self.judge_retry()
        QThread.msleep(10)
        self.params_send({'choose': choose})
        self.log.debug(f'send choose success')

        if self.dia.exec_() == QDialog.Accepted:    # important dia窗口确认为最后把关
            self.params_send({'retry': False})
            self.book_num -= 1
        else:
            self.params_send({'retry': True})       # -*- 看需求 确认框按错可重选section序号 /择其一/ 多选书时忽略部分不要的yield
        self.bThread.print_signal.connect(self.textbrowser_load)

        if self.book_num == 0:
            self.helplabel.re_pic()
            self.textbrowser_load(font_color(">>>>> 说明按钮内容已更新，去点下看看吧<br>", 'purple'))
            self.crawl_btn.setDisabled(True)
            # self.funcGroupBox.setDisabled(True)
            self.input_yield.setDisabled(True)
        else:
            self.chooseinput.clear()
            self.retrybtn.setEnabled(True)
        self.bThread.print_signal.disconnect(dia_text)
        self.log.debug(f'book_num remain: {self.book_num}')
        self.log.debug(f"===--→ crawl finish (now step: {self.step})\n")

    def crawl_end(self, imgs_path):
        clear_queue((self.step_Q, self.current_Q, self.print_Q))
        # self.bThread.quit()    # 关闭线程--------------
        # self.bThread.wait()
        # self.p.close()
        self.progressBar.setStyleSheet(r'QProgressBar {text-align: center; border-color: #0000ff;}'
                                       r'QProgressBar::chunk { background-color: #00ff00;}')
        self.chooseinput.setDisabled(True)
        self.next_btn.setDisabled(True)
        self.retrybtn.setEnabled(True)
        self.input_yield.setEnabled(True)
        # self.funcGroupBox.setEnabled(True)

        self.step = 'fin'
        self.helplabel.re_pic()
        self.textbrowser_load(
            font_color(">>>>> 重申，说明按钮内容已更新，去点下看看吧<br>", 'purple') + font_color("…… (*￣▽￣)(￣▽:;.…::;.:.:::;..::;.:...",
                                                                               'Salmon'))
        os.startfile(imgs_path) if self.checkisopen.isChecked() else None
        self.checkisopen.clicked.connect(lambda: os.startfile(imgs_path))
        self.log.info(f"-*-*- crawl_end finish, spider closed \n")

    def textbrowser_load(self, string):
        if 'http' in string:
            self.textBrowser.setOpenExternalLinks(True)
            string = u'<a href="%s" ><b style="font-size:20px;"><br> 点击查看搜索结果</b></a><b><s><font color="WhiteSmoke"  size="4"> 懒得做预览图功能</font></s></b>' % string
            self.textBrowser.append(string)
        else:
            string = r'<p>%s</p>' % string
            self.textBrowser.append(string)

        self.cursor = self.textBrowser.textCursor()
        self.textBrowser.moveCursor(self.cursor.End)  # 光标移到最后，这样就会自动显示出来

    def processbar_load(self, i):
        # 发送item目前信号>更新进度条
        self.progressBar.setValue(i)

    def enterEvent(self, QEvent):
        self.textBrowser.setStyleSheet('background-color: white;')

    def leaveEvent(self, QEvent):
        self.textBrowser.setStyleSheet('background-color: pink;')


text = (f"{'{:-^95}'.format('message')}<br>" +
        font_color(" 不懂的： 1、右下点说明跟着走，2、首次使用去打开【运行必读.txt】看下", 'blue', size=5) +
        font_color('别老问怎么错<br>', 'white') +
        f"{'{:-^90}'.format('仅为学习使用')}")


def crawl_what(index, print_Q, bar, current_Q, step_Q):
    spider_what = {1: 'comic90mh',
                   2: 'comickukudm',
                   3: 'joyhentai'}

    freeze_support()
    process = CrawlerProcess(get_project_settings())
    process.crawl(spider_what[index], print_Q=print_Q, bar=bar, current_Q=current_Q, step_Q=step_Q)
    process.start()
    process.join()
    process.stop()


class WorkThread(QThread):
    item_count_signal = pyqtSignal(int)
    print_signal = pyqtSignal(str)
    finishSignal = pyqtSignal(str)
    active = True

    def __init__(self, gui):
        super(WorkThread, self).__init__()
        self.gui = gui
        self.flag = 1

    def run(self):
        while self.active:
            self.msleep(8)
            if not self.gui.print_Q.empty():
                self.msleep(8)
                self.print_signal.emit(str(self.gui.print_Q.get()))
            if not self.gui.bar.empty():
                self.item_count_signal.emit(self.gui.bar.get())
                self.msleep(10)
            if '完成任务' in self.gui.textBrowser.toPlainText():
                self.item_count_signal.emit(100)
                self.msleep(20)
                break
        if self.active:
            from ComicSpider.settings import IMAGES_STORE
            self.finishSignal.emit(IMAGES_STORE)

    # def __del__(self):
    #     self.wait()

    def stop(self):
        self.flag = 0

