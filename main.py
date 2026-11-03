"""网易云歌单排序器 - PyQt6"""
import sys
from PyQt6.QtWidgets import QApplication
from logger import _log
from ui.main_window import MainWindow
from ui.ui_thread import init as init_ui_thread

_log("APP START")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    init_ui_thread()
    w = MainWindow()
    w.show()
    sys.exit(app.exec())