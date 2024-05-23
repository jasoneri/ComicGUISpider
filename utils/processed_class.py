#!/usr/bin/python
# -*- coding: utf-8 -*-
import time
import typing as t
from dataclasses import dataclass
from multiprocessing import Queue

from utils import State, QueuesManager, Queues


@dataclass
class InputFieldState(State):
    keyword: str
    bookSelected: int
    indexes: t.Union[str, list]


@dataclass
class TextBrowserState(State):
    text: str


@dataclass
class ProcessState(State):
    process: str


def refresh_state(self, state_name, queue_name, monitor=False):
    _ = getattr(self, state_name)
    state = self.Q(queue_name).recv()
    while monitor:
        if state == _:
            state = self.Q(queue_name).recv()
        else:
            break
    setattr(self, state_name, state)


class QueueHandler:
    def __init__(self, manager):
        self.manager = manager

    class Q:
        def __init__(self, queue):
            self.queue = queue

        def send(self, state: State, **kw):
            return Queues.send(self.queue, state, **kw)

        def recv(self) -> State:
            flag = False
            while not flag:
                flag = Queues.recv(self.queue)
                time.sleep(0.2)
            return flag

    def __call__(self, queue_name, *args, **kwargs):
        _inner_attr = f'_instance_{queue_name}'
        if not hasattr(self, _inner_attr):
            setattr(self, f'_instance_{queue_name}', self.Q(getattr(self.manager, queue_name)()))
        return getattr(self, _inner_attr)


class GuiQueuesManger(QueuesManager):
    grids = ['InputFieldQueue', 'RetryQueue', 'TextBrowser', 'ProcessQueue', 'BarQueue']

    def __iter__(self):
        for i in self.grids:
            yield getattr(self, i)


def startup_bg_queue_manager():
    InputFieldQueue = Queue()
    TextBrowserQueue = Queue(2)
    ProcessQueue = Queue()
    BarQueue = Queue()
    QueuesManager.register('InputFieldQueue', callable=lambda: InputFieldQueue)  # GUI > 爬虫
    QueuesManager.register('TextBrowserQueue', callable=lambda: TextBrowserQueue)  # 爬虫 > GUI.thread
    QueuesManager.register('ProcessQueue', callable=lambda: ProcessQueue)  # 爬虫 > GUI
    QueuesManager.register('BarQueue', callable=lambda: BarQueue)  # 爬虫 > GUI.thread
    manager = QueuesManager(address=('127.0.0.1', 50000), authkey=b'abracadabra')
    s = manager.get_server()
    s.serve_forever()
