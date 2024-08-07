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


if __name__ == '__main__':
    spider_choice = 2  # 选网站/爬虫，转crawl_what方法一目了然
    keyword = '満开开花'  # 输入关键词    # FIXME(2024-06-18): debug kaobei轻小说book请求
    input_1 = "10-12+22+26+"  # 选书
    # input_2 = "11"  # 选章节

    state_1 = InputFieldState(keyword=keyword, bookSelected=spider_choice, indexes='')
    state_2 = InputFieldState(keyword=keyword, bookSelected=spider_choice, indexes=transfer_input(input_1))
    state_3 = InputFieldState(keyword=keyword, bookSelected=spider_choice, indexes=transfer_input(input_2))

    guiQueuesManger = GuiQueuesManger()
    queue_port = guiQueuesManger.find_free_port()
    p_qm = Process(target=guiQueuesManger.create_server_manager)
    p_qm.start()

    gui = Gui(queue_port)
    p_crawler = Process(target=crawl_what, args=(spider_choice, queue_port),
                        kwargs={"LOG_LEVEL": "DEBUG"})
    p_crawler.start()

    p_bThread = Process(target=say_to_textBrowser, args=(gui.Q('TextBrowserQueue'),))
    p_bThread.start()

    gui.Q('InputFieldQueue').send(state_1)
    refresh_state(gui, 'process_state', 'ProcessQueue', monitor_change=True)
    time.sleep(2)
    gui.Q('InputFieldQueue').send(state_2)
    time.sleep(2)
    refresh_state(gui, 'process_state', 'ProcessQueue', monitor_change=True)
    gui.Q('InputFieldQueue').send(state_3)  # 测jm也不要注释这

    for p in [p_qm, p_bThread]:
        if p is not None:
            time.sleep(2)
            p.kill()  # break point for it, scrapy end then restore for all process end
            p.join()
            p.close()
    for p in [p_qm, p_bThread]:
        del p
