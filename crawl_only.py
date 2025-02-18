# -*- coding: utf-8 -*-
"""cli，no gui,no wait for Interactive"""
import time
import argparse
from multiprocessing import Process

from loguru import logger

from assets import res
from utils import transfer_input
from utils.processed_class import (
    GuiQueuesManger, crawl_what, QueuesManager, QueueHandler, InputFieldState, refresh_state, ProcessState
)
from variables import SPECIAL_WEBSITES_IDXES, SPIDERS


def say_to_textBrowser(textBrowserQueue):
    q = textBrowserQueue.queue
    while 1:
        if not q.empty():
            _state = q.get()
            if _state is None:
                break
            _ = _state.text
            logger.debug(_)
            if res.GUI.WorkThread_finish_flag in _:
                break
    textBrowserQueue.queue.put(None)


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


def test_normal_process(keyword, input_2, input_3):
    """
    input_2: 选书
    input_3: 选章节
    """
    # TODO[8](2024-08-19): debug 拷贝漫画轻小说book请求
    state_1 = InputFieldState(keyword=keyword, bookSelected=spider_choice, indexes='', pageTurn='')
    state_2 = InputFieldState(keyword=keyword, bookSelected=spider_choice, indexes=transfer_input(input_2), pageTurn='')
    if input_3:
        state_3 = InputFieldState(keyword=keyword, bookSelected=spider_choice, indexes=transfer_input(input_3),
                                  pageTurn='')

    gui.Q('InputFieldQueue').send(state_1)
    refresh_state(gui, 'process_state', 'ProcessQueue', monitor_change=True)
    time.sleep(2)
    gui.Q('InputFieldQueue').send(state_2)
    refresh_state(gui, 'process_state', 'ProcessQueue', monitor_change=input_3 or False)
    #  上面这行 refresh_state，当测试三步跳转时要加 monitor_change=True
    if input_3:
        time.sleep(2)
        gui.Q('InputFieldQueue').send(state_3)
        time.sleep(2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description=f"""CGS命令行脚本，目前支持简单下载/调试功能
网站对应序号: {SPIDERS}""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('-w', '--website', type=int, help='选择网站序号')
    parser.add_argument('-k', '--keyword', help='关键字（作品名）')
    parser.add_argument('-i', '--indexes',
                        help='e.g., 0 表示全选(特殊)  |  1 表示单选 1 (类推)  |  7+9 →表示多选 7、9 (加号)  |  3-5 →多选 3、4、5 (减号)  |  1+7-9 →复合多选 1、7、8、9')
    # TODO[3](2025-02-11): 负数扩展，例如当indexes=-3时，从倒数第三个至最后一个，（下载最新3话）
    parser.add_argument('-i2', '--indexes2', help=f'同-i，当网站序号非{SPECIAL_WEBSITES_IDXES}时，必须设置用于选择章节')
    parser.add_argument('-tw', '--time_wait',
                        help='设置主进程最大等待的退出时间，可按使用习惯的平均完成时间设值，不设置时默认300')
    parser.add_argument('-tp', '--turn_p', action='store_true', help='Run turn_page_test')
    args = parser.parse_args()

    if not args.keyword or not args.indexes:
        parser.error("the following arguments are required: -k/--keyword and -i/--indexes")

    if args.website not in SPECIAL_WEBSITES_IDXES:
        if not args.indexes2:
            parser.error(
                "the following argument is required when website is not in SPECIAL_WEBSITES_IDXES: -i2/--indexes2")
    else:
        if args.indexes2:
            parser.error("the argument -i2/--indexes2 is not allowed when website is in SPECIAL_WEBSITES_IDXES")

    spider_choice = args.website if args.website else 1  # 选网站/爬虫，转crawl_what方法一目了然

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

    if args.turn_p:
        test_turn_page()
    else:
        test_normal_process(args.keyword, args.indexes, args.indexes2)

    try:
        p_bThread.join(timeout=args.time_wait or 300)
        gui.Q('TextBrowserQueue').send(None)
        for p in [p_crawler, p_qm]:
            if p.is_alive():
                p.terminate()
        for p in [p_crawler, p_qm, p_bThread]:
            p.join(timeout=5)
    finally:
        for p in [p_crawler, p_qm, p_bThread]:
            if p.is_alive():
                p.kill()
            p.close()
