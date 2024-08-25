# -*- coding: utf-8 -*-
"""debug scrapy for test，no gui,no wait for Interactive"""
import time
from loguru import logger

from utils import transfer_input
from utils.processed_class import (
    GuiQueuesManger, crawl_what, QueuesManager, QueueHandler, InputFieldState, refresh_state, ProcessState
)
from multiprocessing import Process


def say_to_textBrowser(textBrowserQueue):
    q = textBrowserQueue.queue
    while 1:
        if not q.empty():
            _state = q.get()
            _ = _state.text
            logger.debug(_)
            if '完成任务' in _:
                break


class Gui:
    process_state = ProcessState(process='init')

    def __init__(self, port):
        manager = QueuesManager.create_manager(
            'InputFieldQueue', 'TextBrowserQueue', 'ProcessQueue', 'BarQueue',
            address=('127.0.0.1', port), authkey=b'abracadabra'
        )
        manager.connect()
        self.Q = QueueHandler(manager)


def test_turn_page():
    keyword = '排名月'  # 输入关键词
    input_1 = ""  # 选书
    input_2 = ""  # 选章节
    state_1 = InputFieldState(keyword=keyword, bookSelected=spider_choice, indexes='', pageTurn='')
    state_2 = InputFieldState(keyword=keyword, bookSelected=spider_choice, indexes=transfer_input(input_2),
                              pageTurn='next26')
    state_3 = InputFieldState(keyword=keyword, bookSelected=spider_choice, indexes=transfer_input(input_2),
                              pageTurn='120')
    state_4 = InputFieldState(keyword=keyword, bookSelected=spider_choice, indexes=transfer_input(input_2),
                              pageTurn='previous3')
    state_5 = InputFieldState(keyword=keyword, bookSelected=spider_choice, indexes=transfer_input(input_2),
                              pageTurn='300')

    gui.Q('InputFieldQueue').send(state_1)
    refresh_state(gui, 'process_state', 'ProcessQueue', monitor_change=True)
    time.sleep(4)
    gui.Q('InputFieldQueue').send(state_2)
    time.sleep(2)
    gui.Q('InputFieldQueue').send(state_3)
    time.sleep(2)
    gui.Q('InputFieldQueue').send(state_4)
    time.sleep(2)
    gui.Q('InputFieldQueue').send(state_5)


def test_normal_process():
    keyword = '汉化'  # 输入关键词    # TODO[8](2024-08-19): debug 拷贝漫画轻小说book请求
    input_2 = "1"  # 选书
    input_3 = "2"  # 选章节
    state_1 = InputFieldState(keyword=keyword, bookSelected=spider_choice, indexes='', pageTurn='')
    state_2 = InputFieldState(keyword=keyword, bookSelected=spider_choice, indexes=transfer_input(input_2), pageTurn='')
    state_3 = InputFieldState(keyword=keyword, bookSelected=spider_choice, indexes=transfer_input(input_3), pageTurn='')

    gui.Q('InputFieldQueue').send(state_1)
    refresh_state(gui, 'process_state', 'ProcessQueue', monitor_change=True)
    time.sleep(4)
    gui.Q('InputFieldQueue').send(state_2)
    refresh_state(gui, 'process_state', 'ProcessQueue')
    #  上面这行 refresh_state，当测试三步跳转时要加 monitor_change=True
    time.sleep(2)
    gui.Q('InputFieldQueue').send(state_3)
    time.sleep(2)


if __name__ == '__main__':
    spider_choice = 1  # 选网站/爬虫，转crawl_what方法一目了然

    guiQueuesManger = GuiQueuesManger()
    queue_port = guiQueuesManger.find_free_port()
    p_qm = Process(target=guiQueuesManger.create_server_manager)
    p_qm.start()

    gui = Gui(queue_port)
    p_crawler = Process(target=crawl_what, args=(spider_choice, queue_port),
                        kwargs={"LOG_LEVEL": "DEBUG", "LOG_FILE": None})
    p_crawler.start()

    p_bThread = Process(target=say_to_textBrowser, args=(gui.Q('TextBrowserQueue'),))
    p_bThread.start()

    test_turn_page()
    # test_normal_process()

    for p in [p_qm, p_bThread]:
        if p is not None:  # break point for it, scrapy end then restore for all process end
            time.sleep(2)  # break point for it, scrapy end then restore for all process end
            p.kill()
            p.join()
            p.close()
    for p in [p_qm, p_bThread]:
        del p
