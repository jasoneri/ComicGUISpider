from PyQt5.QtCore import QObject
from qfluentwidgets import InfoBar, InfoBarPosition

from GUI.thread import RvThread


class RVManager(QObject):
    pos = InfoBarPosition.TOP_RIGHT
    
    def __init__(self, gui):
        super().__init__(gui)
        self.gui = gui
        self.scan_thread = None

    def start_scan(self, show_progress: bool = False, **show_kws):
        if self.scan_thread and self.scan_thread.isRunning():
            self.gui.log.warning("RV scan thread is already running, skipping new scan")
            return
        
        show_kws.update(pos=show_kws.get("pos", self.pos))
        self.scan_thread = RvThread(self.gui, show_progress=show_progress)
        self.scan_thread.scan_progress.connect(
            lambda msg: self._show_scan_progress(msg, **show_kws)
        )
        self.scan_thread.scan_completed.connect(
            lambda total: self._on_scan_completed(total, **show_kws)
        )
        self.scan_thread.start()

    def _show_scan_progress(self, message: str, **show_kws):
        parent = show_kws.get("parent_widget", self.gui.textBrowser)
        InfoBar.info(title='', content=message,
            position=show_kws['pos'], duration=2000, parent=parent)

    def _on_scan_completed(self, total: int, **show_kws):
        self.gui.log.info(f"Scanned: {total} episodes")
        self.gui.bsm = None
        parent = show_kws.get("parent_widget", self.gui.textBrowser)
        info_what = InfoBar.success if total else InfoBar.warning
        info_what(title='', content=f'scaned: {total} books/epsiodes',
            position=show_kws['pos'], duration=3000, parent=parent)

    def stop_scan(self):
        if self.scan_thread and self.scan_thread.isRunning():
            self.scan_thread.quit()
            self.scan_thread.wait(1000)
