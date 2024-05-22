#!/usr/bin/python
# -*- coding: utf-8 -*-
from dataclasses import dataclass
import typing as t
from multiprocessing import managers, Queue
from utils import Queues, State


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


class MyManager(managers.BaseManager):
    def __new__(cls, *args, **kwargs):
        if not hasattr(MyManager, "_instance"):
            MyManager.register("GuiQueues", GuiQueues)
            MyManager._instance = object.__new__(cls)
        return MyManager._instance


class GuiQueues(Queues):
    InputFieldState = Queue()  # gui发，爬虫收
    RetryState = Queue()  # gui发，爬虫收
    TextBrowser = Queue()  # 爬虫发，gui收
    ProcessState = Queue()  # 爬虫发，gui收
    Bar = Queue()  # 爬虫发，gui收
    grids = ['InputFieldState', 'RetryState', 'TextBrowser', 'ProcessState', 'Bar']

    def __iter__(self):
        for i in self.grids:
            yield getattr(self, i)

    # def __new__(cls, *args, **kwargs):
    #     if not hasattr(GuiQueues, "_instance"):
    #         GuiQueues._instance = object.__new__(cls)
    #         GuiQueues._instance.InputFieldState = Queue()  # gui发，爬虫收
    #         GuiQueues._instance.RetryState = Queue()  # gui发，爬虫收
    #         GuiQueues._instance.TextBrowser = Queue()  # 爬虫发，gui收
    #         GuiQueues._instance.ProcessState = Queue()  # 爬虫发，gui收
    #         GuiQueues._instance.Bar = Queue()  # 爬虫发，gui收
    #     return GuiQueues._instance
