import time
import typing as t
from dataclasses import asdict


class State:
    """gui与后端需要共用的一个状态变量时，使用此类；
    由于处于不同进程，需要创建一个对应的Queues做通讯"""
    buffer: dict = None

    def sv_cache(self):
        """take snapshot when sth occur
        run before sent
        """
        try:
            self.buffer = asdict(self)
        except AttributeError:
            ...

    def __eq__(self, other):
        return asdict(self) == other.buffer

    def __setattr__(self, key, value):
        super().__setattr__(key, value)
        if key != 'buffer':
            self.sv_cache()


class Queues:
    @staticmethod
    def send(queue, state: State, wait=False):
        try:
            if wait:
                while not queue.empty():
                    time.sleep(0.01)
            else:
                if not queue.empty():
                    queue.get()
        except Exception as e:
            raise e
        queue.put(state)

    @staticmethod
    def recv(queue) -> t.Optional[State]:
        try:
            if queue.empty():
                return None
            state = queue.get()
            queue.put_nowait(state)
        except Exception as e:
            raise e
        return state

    @staticmethod
    def clear(queue):
        try:
            while True:
                queue.get_nowait()
        except Exception:
            pass


class TasksObj:
    def __init__(self, taskid: str, title: str, tasks_count: int, title_url: str = None, episode_name: str = None):
        self.taskid = taskid
        self.title = title
        self.tasks_count = tasks_count
        self.title_url = title_url
        self.episode_name = episode_name
        self.downloaded = []

    @property
    def display_title(self) -> str:
        return f"{self.title} - {self.episode_name}" if (self.episode_name and self.episode_name != "meaningless") else self.title


class TaskObj:
    success: bool = True

    def __init__(self, taskid: str, page: str, url: str = None):
        self.taskid = taskid
        self.page = page
        self.url = url
