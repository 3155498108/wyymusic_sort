"""网易云歌单排序器 - PyQt6"""
import sys
from PyQt6.QtWidgets import QApplication
from logger import _log
from ui.main_window import MainWindow

_log("APP START")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())