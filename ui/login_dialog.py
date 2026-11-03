"""扫码登录弹窗"""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QLineEdit
from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QDesktopServices

from core.ncm_client import ncm_login_check
from ui.theme import apply_dark_title_bar


class LoginDialog(QDialog):
    def __init__(self, qr_url, parent=None):
        super().__init__(parent)
        self.setWindowTitle("扫码登录网易云音乐")
        self.setMinimumSize(500, 200)

        layout = QVBoxLayout(self)

        lbl = QLabel("请用网易云音乐 App 扫码登录：")
        lbl.setProperty("variant", "h1")
        layout.addWidget(lbl)

        self.url_edit = QLineEdit(qr_url)
        self.url_edit.setReadOnly(True)
        self.url_edit.returnPressed.connect(self._open_url)
        layout.addWidget(self.url_edit)

        open_btn = QPushButton("在浏览器中打开")
        open_btn.clicked.connect(self._open_url)
        layout.addWidget(open_btn)

        hint = QLabel("提示：将上方链接复制到手机浏览器打开，或直接扫描二维码")
        hint.setProperty("variant", "weak")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.status_lbl = QLabel("等待扫码登录...")
        self.status_lbl.setStyleSheet("color:#E06C6C; font-size:13px;")
        layout.addWidget(self.status_lbl)

        self.ok_btn = QPushButton("已完成扫码")
        self.ok_btn.setProperty("variant", "primary")
        self.ok_btn.clicked.connect(self._check_login)
        layout.addWidget(self.ok_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

        self.qr_url = qr_url
        apply_dark_title_bar(self)
        self.polling_timer = QTimer()
        self.polling_timer.timeout.connect(self._check_login)
        self.polling_timer.start(3000)

    def _open_url(self):
        QDesktopServices.openUrl(QUrl(self.qr_url))

    def _check_login(self):
        status = ncm_login_check()
        if status.get("success"):
            self.polling_timer.stop()
            self.status_lbl.setText(f"✅ 登录成功：{status.get('message', '')}")
            self.ok_btn.setEnabled(False)
            QTimer.singleShot(1500, self.accept)
