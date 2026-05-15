"""AppID/PrivateKey 配置弹窗"""
import json
import os

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
from PyQt6.QtCore import Qt

from constants import CONFIG_FILE


class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("首次配置")
        self.setMinimumWidth(420)
        self.app_id = ""
        self.private_key = ""
        self._setup_ui()
        self._load_existing()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("请输入网易云音乐 API 凭据："))
        layout.addSpacing(5)

        layout.addWidget(QLabel("AppID："))
        self.app_id_edit = QLineEdit()
        self.app_id_edit.setPlaceholderText("请输入 AppID")
        layout.addWidget(self.app_id_edit)

        layout.addWidget(QLabel("PrivateKey："))
        self.private_key_edit = QLineEdit()
        self.private_key_edit.setPlaceholderText("请输入 PrivateKey")
        self.private_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.private_key_edit)

        layout.addSpacing(10)

        btns = QPushButton("保存")
        btns.setMinimumHeight(40)
        btns.setStyleSheet("background:#1db100; color:white; font-weight:bold;")
        btns.clicked.connect(self._save)
        layout.addWidget(btns)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

        self.note_lbl = QLabel("（配置文件保存在应用目录下）")
        self.note_lbl.setStyleSheet("color:#888; font-size:11px;")
        layout.addWidget(self.note_lbl)

    def _load_existing(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.app_id_edit.setText(data.get("app_id", ""))
                self.private_key_edit.setText(data.get("private_key", ""))
            except Exception:
                pass

    def _save(self):
        app_id = self.app_id_edit.text().strip()
        private_key = self.private_key_edit.text().strip()
        if not app_id or not private_key:
            QMessageBox.warning(self, "提示", "AppID 和 PrivateKey 均不能为空")
            return
        self.app_id = app_id
        self.private_key = private_key
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"app_id": app_id, "private_key": private_key}, f, ensure_ascii=False, indent=2)
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存配置失败:\n{e}")