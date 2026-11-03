"""AppID/PrivateKey + AI 配置弹窗"""
import json
import os

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QMessageBox, QComboBox)
from PyQt6.QtCore import Qt

from constants import CONFIG_FILE
from ui.theme import apply_dark_title_bar


class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("配置")
        self.setMinimumWidth(470)
        self.app_id = ""
        self.private_key = ""
        self.ai_provider = "openai"
        self.ai_api_key = ""
        self.ai_model = ""
        self._setup_ui()
        self._load_existing()
        apply_dark_title_bar(self)

    def _setup_ui(self):
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.Dialog)
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(8)

        # 网易云音乐配置
        api_lbl = QLabel("网易云音乐 API 凭据")
        api_lbl.setProperty("variant", "section")
        layout.addWidget(api_lbl)

        layout.addWidget(QLabel("AppID"))
        self.app_id_edit = QLineEdit()
        self.app_id_edit.setPlaceholderText("请输入 AppID")
        layout.addWidget(self.app_id_edit)

        layout.addWidget(QLabel("PrivateKey"))
        self.private_key_edit = QLineEdit()
        self.private_key_edit.setPlaceholderText("请输入 PrivateKey")
        self.private_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.private_key_edit)

        layout.addSpacing(14)

        # AI 配置
        ai_lbl = QLabel("AI 排序配置")
        ai_lbl.setProperty("variant", "section")
        layout.addWidget(ai_lbl)

        layout.addWidget(QLabel("AI 提供商"))
        self.ai_provider_combo = QComboBox()
        self.ai_provider_combo.addItems(["OpenAI", "Anthropic Claude", "本地模型 (Ollama)"])
        self.ai_provider_combo.setCurrentIndex(0)
        layout.addWidget(self.ai_provider_combo)

        layout.addWidget(QLabel("API Key"))
        self.ai_api_key_edit = QLineEdit()
        self.ai_api_key_edit.setPlaceholderText("请输入 API Key")
        self.ai_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.ai_api_key_edit)

        layout.addWidget(QLabel("模型（可选）"))
        self.ai_model_edit = QLineEdit()
        self.ai_model_edit.setPlaceholderText("如 gpt-4o-mini / claude-sonnet-4-20250514（留空使用默认）")
        layout.addWidget(self.ai_model_edit)

        layout.addSpacing(16)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.setMinimumWidth(84)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("保存")
        save_btn.setMinimumWidth(96)
        save_btn.setProperty("variant", "primary")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        self.note_lbl = QLabel("配置文件保存在应用目录下")
        self.note_lbl.setProperty("variant", "weak")
        layout.addWidget(self.note_lbl)

    def _load_existing(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.app_id_edit.setText(data.get("app_id", ""))
                self.private_key_edit.setText(data.get("private_key", ""))

                provider_map = {"openai": 0, "anthropic": 1, "local": 2}
                self.ai_provider_combo.setCurrentIndex(provider_map.get(data.get("ai_provider", "openai"), 0))
                self.ai_api_key_edit.setText(data.get("ai_api_key", ""))
                self.ai_model_edit.setText(data.get("ai_model", ""))
            except Exception:
                pass

    def _save(self):
        app_id = self.app_id_edit.text().strip()
        private_key = self.private_key_edit.text().strip()
        if not app_id or not private_key:
            QMessageBox.warning(self, "提示", "AppID 和 PrivateKey 均不能为空")
            return

        ai_provider_map = {0: "openai", 1: "anthropic", 2: "local"}
        config = {
            "app_id": app_id,
            "private_key": private_key,
            "ai_provider": ai_provider_map.get(self.ai_provider_combo.currentIndex(), "openai"),
            "ai_api_key": self.ai_api_key_edit.text().strip(),
            "ai_model": self.ai_model_edit.text().strip(),
        }

        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存配置失败:\n{e}")