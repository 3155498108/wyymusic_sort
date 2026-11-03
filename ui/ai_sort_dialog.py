"""AI 排序弹窗"""
import json
import os
import threading

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton, QMessageBox, QProgressBar, QHBoxLayout
from PyQt6.QtCore import Qt, QTimer

from core.ai_sorter import ask_ai_sort
from constants import CONFIG_FILE
from ui.theme import apply_dark_title_bar
from ui.ui_thread import post


class AISortDialog(QDialog):
    def __init__(self, tracks, parent=None):
        super().__init__(parent)
        self.tracks = tracks
        self.sorted_enc_ids = None
        self._setup_ui()
        apply_dark_title_bar(self)

    def _setup_ui(self):
        self.setWindowTitle("AI 智能排序")
        self.setMinimumSize(500, 300)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.Dialog)
        self.setModal(True)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"歌单共 {len(self.tracks)} 首歌曲，请描述排序要求："))
        layout.addSpacing(5)

        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("例如：周杰伦的歌放前面，其余按入库时间排序\n或者：按专辑发行时间降序排列")
        self.prompt_edit.setMaximumHeight(100)
        layout.addWidget(self.prompt_edit)

        layout.addWidget(QLabel("提示：尽量描述清楚排序规则，AI 会尽可能按要求排序。"))

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_lbl = QLabel("")
        self.status_lbl.setProperty("variant", "weak")
        layout.addWidget(self.status_lbl)

        layout.addSpacing(10)

        btns = QHBoxLayout()
        btns.addStretch()

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btns.addWidget(self.cancel_btn)

        self.start_btn = QPushButton("🤖 开始 AI 排序")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.setProperty("variant", "primary")
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.clicked.connect(self._do_sort)
        btns.addWidget(self.start_btn)

        layout.addLayout(btns)

    def _do_sort(self):
        prompt = self.prompt_edit.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "提示", "请输入排序要求")
            return

        # 检查是否配置了 API Key
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
            if not config.get("ai_api_key"):
                QMessageBox.warning(self, "提示", "请先在「配置」中填写 AI API Key")
                return
        else:
            QMessageBox.warning(self, "提示", "请先在「配置」中填写 AI API Key")
            return

        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.status_lbl.setText("正在排序...")

        def _progress(cur, total, status):
            def _update():
                self.progress_bar.setMaximum(total)
                self.progress_bar.setValue(cur)
                self.status_lbl.setText(status)
            post(_update)

        def _bg():
            result = ask_ai_sort(self.tracks, prompt, _progress)

            def _done():
                self.progress_bar.setVisible(False)
                self.start_btn.setEnabled(True)
                self.cancel_btn.setEnabled(True)

                if result is None:
                    self.status_lbl.setText("")
                    QMessageBox.warning(self, "错误", "AI 排序失败，请检查 API Key 和网络连接")
                    return

                if not result:
                    self.status_lbl.setText("")
                    QMessageBox.warning(self, "提示", "未返回有效排序结果")
                    return

                # 验证返回的 ID 是否都来自原始歌单
                original_ids = set(t.get("encId", t.get("id", "")) for t in self.tracks)
                valid_ids = [rid for rid in result if rid in original_ids]

                if len(valid_ids) < len(result):
                    self.status_lbl.setText(f"警告：{len(result) - len(valid_ids)} 个 ID 不在原始歌单中，已忽略")

                if not valid_ids:
                    QMessageBox.warning(self, "提示", "返回的排序结果无效")
                    return

                self.sorted_enc_ids = valid_ids
                QTimer.singleShot(300, self.accept)

            post(_done)

        threading.Thread(target=_bg, daemon=True).start()