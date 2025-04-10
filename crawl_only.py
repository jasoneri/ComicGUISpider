# -*- coding: utf-8 -*-
"""cli，no gui,no wait for Interaction"""
import time
import re
import argparse
from multiprocessing import Process, set_start_method

from loguru import logger

from assets import res
from utils import transfer_input
from utils.processed_class import (
    GuiQueuesManger, crawl_what, QueuesManager, QueueHandler, InputFieldState, refresh_state, ProcessState
)
from variables import SPECIAL_WEBSITES_IDXES, SPIDERS


def say_to_textBrowser(textBrowserQueue, TasksQueue, daily_test_flag=False):
    text_browser_q = textBrowserQueue.queue
    task_q = TasksQueue.queue
    break_flag = re.compile(f"{res.GUI.WorkThread_finish_flag}|{res.GUI.WorkThread_empty_flag}")
    while 1:
        if not text_browser_q.empty():
            _state = text_browser_q.get()
            if _state is None:
                break
            _ = _state.text
            if not daily_test_flag:
                logger.debug(_)
            if bool(break_flag.search(_)):
                break
        if not task_q.empty():
            _task_state = task_q.get()
    textBrowserQueue.queue.put(None)


class Gui:
    process_state = ProcessState(process='init')

    def __init__(self, port):
        logger.debug(f"{port=}")
        manager = QueuesManager.create_manager(
            'InputFieldQueue', 'TextBrowserQueue', 'ProcessQueue', 'BarQueue', 'TasksQueue',
            address=('localhost', port), authkey=b'abracadabra'
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
    state_2 = InputFieldState(keyword=keyword, bookSelected=spider_choice, indexes=input_2, pageTurn='')
    if input_3:
        state_3 = InputFieldState(keyword=keyword, bookSelected=spider_choice, indexes=input_3, pageTurn='')

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
    set_start_method('spawn', force=True)
    parser = argparse.ArgumentParser(
        description=f"""CGS命令行脚本，目前支持简单下载/调试功能
网站对应序号: {SPIDERS}""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('-w', '--website', type=int, help='选择网站序号')
    parser.add_argument('-k', '--keyword', help='关键字（作品名）')
    parser.add_argument('-i', '--indexes', type=str, nargs='?',
                        help=res.GUI.Uic.chooseinputTip)
    parser.add_argument('-i2', '--indexes2', type=str, nargs='?', default=None, help=f'同-i，当网站序号非{SPECIAL_WEBSITES_IDXES}时，必须设置用于选择章节')
    parser.add_argument('-l', '--log_level', type=str, nargs='?', default='DEBUG', help='log level')
    parser.add_argument('-tw', '--time_wait',
                        help='设置主进程最大等待的退出时间，可按使用习惯的平均完成时间设值，不设置时默认300')
    parser.add_argument('-tp', '--turn_page', action='store_true', help='Run turn_page_test')
    parser.add_argument('-dt', '--daily_test', action='store_true', help='Run daily_test')
    parser.add_argument('-sp', '--start_port', type=int, nargs='?', default=50000, help='bind start port')
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
    queue_port = guiQueuesManger.find_free_port(start_port=args.start_port)
    p_qm = Process(target=guiQueuesManger.create_server_manager)
    p_qm.start()

    try:
        gui = Gui(queue_port)
    except Exception as e:
        if p_qm.is_alive():
            p_qm.terminate()
        raise e
    p_crawler_kwargs = {"LOG_LEVEL": args.log_level, "LOG_FILE": None}
    if args.daily_test:
        p_crawler_kwargs.update({
            "CLOSESPIDER_ITEMCOUNT": 13,
        })
    p_crawler = Process(target=crawl_what, args=(spider_choice, queue_port), kwargs=p_crawler_kwargs)
    p_crawler.start()

    p_bThread = Process(target=say_to_textBrowser, args=(gui.Q('TextBrowserQueue'), gui.Q('TasksQueue'), args.daily_test))
    p_bThread.start()

    if args.turn_page:
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
            p.join(timeout=3)
    finally:
        for p in [p_crawler, p_qm, p_bThread]:
            if p.is_alive():
                p.kill()
            p.close()
