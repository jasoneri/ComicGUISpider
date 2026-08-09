import sys
from importlib import import_module

from PySide6.QtCore import QThread

# Deferred off the startup critical path; first chooseBox otherwise pays them on
# the GUI thread before preprocess can show its tooltip:
# - providers barrel → every site provider (+ cryptography / lxml / …)
# - scrapy.crawler stack → SpiderRuntimeThread.wait_ready (measured ~3.6s cold)
# Transport/doh is already pulled by generation_bind → preview → site_runtime.
WARMUP_MODULES = (
    "utils.website.providers",
    "scrapy.crawler",
    "scrapy.utils.log",
    "scrapy.utils.project",
    "twisted.internet.reactor",
)


class ImportWarmupThread(QThread):
    """Load deferred modules off the main thread so lazification does not move
    the stall to first site selection.

    Safe off-main-thread: CPython 3.3+ uses a per-module import lock; disk I/O
    releases the GIL. Concurrent first-use on the GUI thread simply waits the
    same import rather than double-loading.
    """

    def __init__(self, gui, modules=WARMUP_MODULES):
        super().__init__(gui)
        self.gui = gui
        self._modules = tuple(modules)

    def run(self):
        for name in self._modules:
            if name in sys.modules:
                continue
            try:
                import_module(name)
            except Exception:
                self.gui.log.exception(f"[warmup] {name} failed")
