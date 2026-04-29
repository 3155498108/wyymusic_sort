"""网易云歌单排序器 - PyQt6
流程：打开程序 → 扫码登录（如需） → 加载歌单 → 多级排序 → 复制 或 直接应用到服务器
"""
import sys
import json
import threading
import os
import subprocess
import re
import urllib.request
import urllib.parse
import datetime as _dt

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
                             QVBoxLayout, QListWidget, QTableWidget, QTableWidgetItem,
                             QPushButton, QComboBox, QLabel, QMessageBox, QHeaderView,
                             QAbstractItemView, QGroupBox, QCheckBox, QLineEdit,
                             QTextBrowser, QDialog, QVBoxLayout as QVBL2)
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QGuiApplication, QClipboard, QDesktopServices
import openpyxl


import time as _time

def _log(msg):
    """写调试日志到固定路径"""
    try:
        with open(r"C:\Users\spenc\AppData\Local\Temp\ncm_sorter.log", "a", encoding="utf-8", errors="replace") as f:
            f.write(f"[{_time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass

_log("APP START")

# ===== 路径（兼容 PyInstaller 打包）=====
APP_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))

def _base_dir():
    """返回 dist/ 根目录
    打包结构：dist/
      网易云歌单排序器/
        网易云歌单排序器.exe  ← sys.executable 在这里
      node/
      ncm-cli/
    所以要往上一级才能找到 node/ 和 ncm-cli/
    """
    import os as osmod
    return osmod.path.dirname(osmod.path.dirname(sys.executable))

BASE_DIR = _base_dir()
NODE = os.path.join(BASE_DIR, "node", "node.exe")
NCM_CLI = os.path.join(BASE_DIR, "ncm-cli", "dist", "index.js")
# 全局 ncm-cli（用户全局安装的版本）
SYSTEM_NODE = r"C:\Program Files\nodejs\node.exe"
GLOBAL_NCM_CLI = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "npm", "node_modules", "@music163", "ncm-cli", "dist", "index.js")
# 本地 ncm-cli（打包的完整版，包含 playlist 命令）
LOCAL_NCM_CLI = os.path.join(BASE_DIR, "ncm-cli", "dist", "index.js")


def _find_npm():
    """查找系统 npm.cmd 的路径"""
    possible_npm = [
        r"C:\Program Files\nodejs\npm.cmd",
        r"C:\Program Files (x86)\nodejs\npm.cmd",
    ]
    for p in possible_npm:
        if os.path.exists(p):
            return p
    import shutil
    return shutil.which("npm.cmd") or ""


def run_ncm(args, timeout=60):
    """用系统 npm exec --global 调用全局 ncm-cli（login/logout/check 等基本命令）"""
    npm = _find_npm()
    if not npm or not os.path.exists(npm):
        return -1, "", ("错误：未找到 npm。请确保已安装 Node.js。\n"
                           "下载地址：https://nodejs.org/")
    env = {
        **os.environ,
        "USERPROFILE": os.path.expanduser("~"),
        "HOME": os.path.expanduser("~"),
        "XDG_CONFIG_HOME": os.path.join(os.path.expanduser("~"), ".config"),
    }
    cmd = [npm, "exec", "--global", "ncm-cli", "--"] + args
    r = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env)
    return r.returncode, r.stdout.decode("utf-8", errors="replace"), r.stderr.decode("utf-8", errors="replace")


def run_ncm_global(args, timeout=120):
    """用系统 npm exec --global 调用全局 ncm-cli（playlist 等命令）"""
    npm = _find_npm()
    if not npm or not os.path.exists(npm):
        return -1, "", ("错误：未找到 npm。请确保已安装 Node.js。\n"
                           "下载地址：https://nodejs.org/")
    env = {
        **os.environ,
        "USERPROFILE": os.path.expanduser("~"),
        "HOME": os.path.expanduser("~"),
    }
    cmd = [npm, "exec", "--global", "ncm-cli", "--"] + args
    r = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env)
    return r.returncode, r.stdout.decode("utf-8", errors="replace"), r.stderr.decode("utf-8", errors="replace")

def ncm_login_check():
    rc, out, _ = run_ncm(["login", "--check", "--output", "json"])
    if rc == 0 and out.strip():
        text = out.strip()
        brace = text.find("{")
        if brace >= 0:
            text = text[brace:]
        try:
            return json.loads(text)
        except:
            pass
    return {"success": False}


def ncm_logout():
    """退出登录"""
    rc, out, _ = run_ncm(["logout", "--output", "json"])
    return rc == 0


def ncm_login():
    rc, out, err = run_ncm(["login", "--output", "json"], timeout=8)
    if rc == 0 and out.strip():
        text = out.strip()
        brace = text.find("{")
        if brace >= 0:
            text = text[brace:]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    return None


def ncm_get_tracks(playlist_enc_id):
    """获取歌单 tracks（分页获取最多1000首）：返回 (enc_ids列表, tracks_info列表)"""
    _log(f"[ncm_get_tracks] playlistId={playlist_enc_id}")
    all_tracks = []
    offset = 0
    while True:
        rc, out, err = run_ncm_global([
            "playlist", "tracks",
            "--playlistId", playlist_enc_id,
            "--limit", "500",
            "--offset", str(offset),
            "--output", "json"
        ])
        if rc != 0:
            _log(f"[ncm_get_tracks] FAILED at offset={offset}: {err[:300]}")
            break
        text = out.strip()
        brace = text.find("{")
        if brace >= 0:
            text = text[brace:]
        try:
            parsed = json.loads(text)
            batch = parsed.get("data") or []
            all_tracks.extend(batch)
            _log(f"[ncm_get_tracks] offset={offset}, got {len(batch)} tracks, total={len(all_tracks)}")
            if len(batch) < 500:
                break
            offset += 500
            if offset >= 1000:
                break
        except:
            _log(f"[ncm_get_tracks] JSON parse error at offset={offset}")
            break
    enc_ids = [t["id"] for t in all_tracks]
    return enc_ids, all_tracks


def ncm_reorder(playlist_enc_id, track_ids_ordered):
    """调用 ncm-cli playlist reorder（需要全局 ncm-cli）"""
    track_ids_str = ",".join(track_ids_ordered)
    rc, out, _ = run_ncm_global([
        "playlist", "reorder",
        "--playlistId", playlist_enc_id,
        "--trackIds", track_ids_str,
        "--output", "json"
    ])
    if rc != 0:
        return None
    text = out.strip()
    brace = text.find("{")
    if brace >= 0:
        text = text[brace:]
    try:
        return json.loads(text)
    except:
        return None


def ncm_get_playlists():
    """获取我创建的歌单（分页最多500）"""
    all_playlists = []
    offset = 0
    while True:
        _log(f"[ncm_get_playlists] fetching offset={offset}")
        rc, out, _ = run_ncm_global(["playlist", "created", "--limit", "500", "--offset", str(offset), "--output", "json"])
        if rc != 0:
            _log(f"[ncm_get_playlists] rc={rc} at offset={offset}")
            break
        text = out.strip()
        brace = text.find("{")
        if brace >= 0:
            text = text[brace:]
        try:
            parsed = json.loads(text)
            records = parsed.get("data", {}).get("records", [])
            total = parsed.get("data", {}).get("recordCount", 0)
            all_playlists.extend(records)
            _log(f"[ncm_get_playlists] offset={offset}, got {len(records)} playlists, total={total}")
            if len(records) < 500 or offset + len(records) >= total:
                break
            offset += 500
        except Exception as e:
            _log(f"[ncm_get_playlists] error: {e}")
            break
    _log(f"[ncm_get_playlists] returning {len(all_playlists)} playlists")
    return all_playlists


# ===== 扫码登录弹窗 =====
class LoginDialog(QDialog):
    def __init__(self, qr_url, parent=None):
        super().__init__(parent)
        self.setWindowTitle("扫码登录网易云音乐")
        self.setMinimumSize(500, 200)

        layout = QVBL2(self)

        lbl = QLabel("请用网易云音乐 App 扫码登录：")
        lbl.setStyleSheet("font-size:14px; font-weight:bold;")
        layout.addWidget(lbl)

        self.url_edit = QLineEdit(qr_url)
        self.url_edit.setReadOnly(True)
        self.url_edit.setStyleSheet("color:#1db100; background:#f0f0f0;")
        self.url_edit.returnPressed.connect(self._open_url)
        layout.addWidget(self.url_edit)

        open_btn = QPushButton("在浏览器中打开")
        open_btn.clicked.connect(self._open_url)
        layout.addWidget(open_btn)

        hint = QLabel("提示：将上方链接复制到手机浏览器打开，或直接扫描二维码")
        hint.setStyleSheet("color:#888; font-size:12px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.status_lbl = QLabel("等待扫码登录...")
        self.status_lbl.setStyleSheet("color:#e55; font-size:13px;")
        layout.addWidget(self.status_lbl)

        self.ok_btn = QPushButton("已完成扫码")
        self.ok_btn.setStyleSheet("background:#1db100; color:white; font-weight:bold; padding:6px;")
        self.ok_btn.clicked.connect(self._check_login)
        layout.addWidget(self.ok_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

        self.qr_url = qr_url
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
        # else: keep polling


# ===== 主窗口 =====
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.playlists = []           # ncm-cli 返回的原始记录
        self.current_pl_enc_id = None   # 当前歌单加密ID
        self.current_pl_raw_id = None    # 当前歌单原始数字ID
        self.server_track_ids = []     # 服务器当前顺序的加密ID列表
        self.id_to_enc = {}           # 数字ID -> 加密ID
        self.enc_to_info = {}         # 加密ID -> {name, artists, album, addTime}
        self.current_tracks = []      # 当前有元数据的 tracks
        self._sorted_tracks = None    # 预览排序后的结果
        self._custom_order = None
        self._setup_ui()
        self._check_login()
        QTimer.singleShot(300, self.load_playlists)

    def _check_login(self):
        status = ncm_login_check()
        if status.get("success"):
            msg = status.get("message", "已登录")
            self.status_lbl2.setText(f"✅ {msg}")
            self.status_lbl2.setStyleSheet("color:#1db100; font-size:13px; font-weight:bold;")
            self.login_btn.setText("🚪 退出登录")
            self.login_btn.setStyleSheet("color:#e55; font-weight:bold;")
            self.login_btn.setEnabled(True)
        else:
            self.status_lbl2.setText("⚠ 未登录")
            self.status_lbl2.setStyleSheet("color:#e55; font-size:13px; font-weight:bold;")
            self.login_btn.setText("🔐 扫码登录")
            self.login_btn.setStyleSheet("color:#1db100; font-weight:bold;")
            self.login_btn.setEnabled(True)

    def _show_login(self):
        result = ncm_login()
        if not result:
            QMessageBox.warning(self, "错误", "无法获取登录二维码，请确保 ncm-cli 正常工作")
            return
        qr_url = result.get("clickableUrl") or result.get("qrCodeUrl", "")
        dlg = LoginDialog(qr_url, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._check_login()
            self.load_playlists()

    def _logout(self):
        reply = QMessageBox.question(self, "退出登录", "确定退出当前账号登录？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        ok = ncm_logout()
        if ok:
            self._check_login()
            self.playlist_list.clear()
            self.table.setRowCount(0)
            self.status_lbl.setText("已退出登录")
        else:
            QMessageBox.warning(self, "错误", "退出登录失败")

    def _on_login_btn_click(self):
        status = ncm_login_check()
        if status.get("success"):
            self._logout()
        else:
            self._show_login()

    def _setup_ui(self):
        self.setWindowTitle("网易云歌单排序器")
        self.setGeometry(150, 80, 1200, 740)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        # ===== 左：歌单列表 =====
        left = QVBoxLayout()
        left.addWidget(QLabel("我的歌单"))
        self.playlist_list = QListWidget()
        self.playlist_list.setMaximumWidth(380)
        self.playlist_list.currentRowChanged.connect(self._on_select)
        left.addWidget(self.playlist_list)

        refresh_btn = QPushButton("刷新歌单")
        refresh_btn.clicked.connect(self.load_playlists)
        left.addWidget(refresh_btn)

        self.import_btn = QPushButton("导入Excel")
        self.import_btn.clicked.connect(self.import_playlist)
        self.import_btn.setStyleSheet("background:#555; color:white; padding:5px 14px;")
        left.addWidget(self.import_btn)
        self.export_btn = QPushButton("导出Excel")
        self.export_btn.clicked.connect(self.export_playlist)
        self.export_btn.setEnabled(False)
        left.addWidget(self.export_btn)

        # 登录状态标签（醒目）
        self.status_lbl2 = QLabel("⚠ 检测登录状态中...")
        self.status_lbl2.setStyleSheet("color:#888; font-size:12px;")
        left.addWidget(self.status_lbl2)

        self.login_btn = QPushButton("🔐 扫码登录")
        self.login_btn.setStyleSheet("color:#1db100; font-weight:bold;")
        self.login_btn.clicked.connect(self._on_login_btn_click)
        left.addWidget(self.login_btn)

        layout.addLayout(left)

        # ===== 右：排序 + 表格 =====
        right = QVBoxLayout()

        # 排序选项
        sort_group = QGroupBox("多级排序")
        sl = QHBoxLayout()
        self.sort_cbs = []
        self.sort_asc_cbs = []  # per-level asc/desc comboboxes
        for i, label in enumerate(["第1层:", "第2层:", "第3层:"]):
            cb = QComboBox()
            cb.addItems(["", "艺人", "专辑", "歌曲名", "入库时间", "自定义顺序"])
            cb.setMinimumWidth(110)
            asc_cb = QComboBox()
            asc_cb.addItems(["升序", "降序"])
            asc_cb.setMinimumWidth(65)
            lbl = QLabel(label)
            lbl.setMinimumWidth(35)
            sl.addWidget(lbl)
            sl.addWidget(cb)
            sl.addWidget(asc_cb)
            self.sort_cbs.append(cb)
            self.sort_asc_cbs.append(asc_cb)
        sl.addStretch()

        preview_btn = QPushButton("预览")
        preview_btn.clicked.connect(self.preview)
        sl.addWidget(preview_btn)

        self.apply_btn = QPushButton("🚀 直接应用到服务器")
        self.apply_btn.setStyleSheet("background:#e55; color:white; font-weight:bold; padding:5px 14px;")
        self.apply_btn.clicked.connect(self.apply_to_server)
        self.apply_btn.setEnabled(False)
        sl.addWidget(self.apply_btn)

        import_btn = QPushButton("📥 导入Excel")
        import_btn.clicked.connect(self.import_playlist)
        import_btn.setStyleSheet("background:#555; color:white; padding:5px 14px;")
        sl.addWidget(import_btn)

        copy_btn = QPushButton("📋 复制排序结果")
        copy_btn.setStyleSheet("background:#1db100; color:white; font-weight:bold; padding:5px 14px;")
        copy_btn.clicked.connect(self.copy_result)
        sl.addWidget(copy_btn)

        sort_group.setLayout(sl)
        right.addWidget(sort_group)

        # 自定义顺序导入
        import_group = QGroupBox("自定义顺序")
        il = QHBoxLayout()
        self.custom_file_lbl = QLabel("未选择文件")
        self.custom_file_lbl.setStyleSheet("color:#888; font-size:12px;")
        self.custom_file_lbl.setMaximumWidth(400)
        import_btn = QPushButton("导入歌曲名单 (.txt/.csv)")
        import_btn.clicked.connect(self.import_custom_order)
        clear_btn = QPushButton("清除")
        clear_btn.clicked.connect(self.clear_custom_order)
        il.addWidget(self.custom_file_lbl)
        il.addWidget(import_btn)
        il.addWidget(clear_btn)
        il.addStretch()
        import_group.setLayout(il)
        right.addWidget(import_group)

        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["#", "歌曲名", "艺人", "专辑", "ID", "入库时间"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(500)
        right.addWidget(self.table)

        self.status_lbl = QLabel("就绪")
        self.status_lbl.setStyleSheet("color:#888; font-size:12px;")
        right.addWidget(self.status_lbl)

        layout.addLayout(right)

    def load_playlists(self):
        self.status_lbl.setText("加载歌单...")
        self.playlist_list.clear()
        threading.Thread(target=self._bg_load_pl, daemon=True).start()

    def _bg_load_pl(self):
        # 先检查登录状态
        login_status = ncm_login_check()
        if not login_status.get("success"):
            QTimer.singleShot(0, lambda: self.status_lbl.setText("⚠ 未登录，请先扫码登录"))
            return
        self.playlists = ncm_get_playlists()
        if not self.playlists:
            # ncm_get_playlists 失败，可能是全局 ncm-cli 未安装
            QTimer.singleShot(0, lambda: self.status_lbl.setText(
                "⚠ 获取歌单失败。请确保已安装全局 ncm-cli：\nnpm install -g @music163/ncm-cli"))
            return
        QTimer.singleShot(0, self._show_pl)

    def _show_pl(self):
        for p in self.playlists:
            name = p.get("name", "?")
            count = p.get("trackCount", 0) or 0
            self.playlist_list.addItem(f"{name}  ({count}首)")
        self.status_lbl.setText(f"共 {len(self.playlists)} 个歌单")
        if self.playlists:
            self.playlist_list.setCurrentRow(0)

    def _on_select(self, row):
        if row < 0 or row >= len(self.playlists):
            return
        p = self.playlists[row]
        self.current_pl_enc_id = p.get("id", "")
        self.current_pl_raw_id = p.get("originalId", "")
        self._sorted_tracks = None
        self.apply_btn.setEnabled(False)
        self.status_lbl.setText("加载歌曲...")
        threading.Thread(target=self._bg_load_tracks, daemon=True).start()

    def _bg_load_tracks(self):
        _log(f"[_bg_load_tracks] start, playlistId={self.current_pl_enc_id}")
        enc_ids, tracks_data = ncm_get_tracks(self.current_pl_enc_id)
        _log(f"[_bg_load_tracks] got enc_ids: {enc_ids is not None}, count={len(enc_ids) if enc_ids else 0}")
        self.server_track_ids = enc_ids or []

        # 直接从 tracks_data 构建映射，不发第二次 API
        self.enc_to_info = {}
        self.id_to_enc = {}
        numeric_to_enc = {}
        enc_to_numeric = {}
        for t in tracks_data:
            enc_id = t.get("id", "")
            orig_id = t.get("originalId", "")
            # 原地改造：给 raw track 数据加上展示层需要的字段
            t["encId"] = enc_id
            t["_addTime"] = (t.get("extMap") or {}).get("addTime", 0)
            t["ar"] = t.get("artists") or []
            t["al"] = t.get("album") or {}
            self.enc_to_info[enc_id] = {
                "name": t.get("name", ""),
                "artists": t.get("artists", []) or [],
                "album": t.get("album") or {},
                "addTime": t.get("_addTime", 0),
                "originalId": orig_id,
            }
            if orig_id:
                numeric_to_enc[str(orig_id)] = enc_id
                enc_to_numeric[enc_id] = str(orig_id)
        self.id_to_enc = numeric_to_enc
        # current_tracks 和 ordered_tracks 指向同一个原地改造后的 list
        self.current_tracks = tracks_data

        _log(f"[_bg_load_tracks] built info for {len(self.enc_to_info)} tracks")
        _log(f"[_bg_load_tracks] first track keys={list(tracks_data[0].keys()) if tracks_data else 'empty'}")
        # 构建 ordered_tracks（按服务器当前顺序）
        ordered_tracks = []
        for enc in (enc_ids or []):
            info = self.enc_to_info.get(enc, {})
            orig_id = enc_to_numeric.get(enc, "")
            if info:
                tr = {
                    "id": orig_id,
                    "encId": enc,
                    "name": info.get("name", ""),
                    "ar": info.get("artists", []),
                    "al": info.get("album", {}),
                    "_addTime": info.get("addTime", 0),
                }
            else:
                tr = {"id": orig_id, "encId": enc, "name": "（无信息）", "ar": [], "al": {}, "_addTime": 0}
            ordered_tracks.append(tr)
        _log(f"[_bg_load_tracks] first ordered_track keys={list(ordered_tracks[0].keys()) if ordered_tracks else 'empty'}")
        self._sorted_tracks = None
        _log(f"[_bg_load_tracks] calling _show_tracks directly with {len(ordered_tracks)} tracks")
        self._show_tracks(ordered_tracks)

    def _show_tracks(self, tracks):
        _log(f"[_show_tracks] CALLED with {len(tracks)} tracks, table={self.table is not None}")
        try:
            total = len(self.server_track_ids)
            shown = len(tracks)
            self.table.setRowCount(shown)
            for i, tr in enumerate(tracks):
                self.table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
                self.table.setItem(i, 1, QTableWidgetItem(str(tr.get("name", ""))))
                ar = tr.get("fullArtists") or tr.get("artists") or tr.get("ar") or []
                self.table.setItem(i, 2, QTableWidgetItem("/".join(a.get("name", "") for a in ar if a.get("name"))))
                al = tr.get("album") or tr.get("al") or {}
                al_name = al.get("name", "") if isinstance(al, dict) else ""
                self.table.setItem(i, 3, QTableWidgetItem(al_name))
                track_id = tr.get("encId") or tr.get("id", "")
                self.table.setItem(i, 4, QTableWidgetItem(str(track_id)))
                add_time = (tr.get("extMap") or {}).get("addTime", 0) or tr.get("_addTime", 0)
                if add_time:
                    import datetime
                    dt = datetime.datetime.fromtimestamp(add_time / 1000)
                    self.table.setItem(i, 5, QTableWidgetItem(dt.strftime("%Y-%m-%d %H:%M")))
                else:
                    self.table.setItem(i, 5, QTableWidgetItem("-"))
            self.table.resizeRowsToContents()
            self.export_btn.setEnabled(shown > 0)
            if total > shown:
                self.status_lbl.setText(f"显示 {shown}/{total} 首（歌单共 {total} 首）")
            else:
                self.status_lbl.setText(f"共 {shown} 首")
            _log(f"[_show_tracks] DONE, set {shown} rows")
        except Exception as e:
            _log(f"[_show_tracks] EXCEPTION: {type(e).__name__}: {e}")
            self.status_lbl.setText(f"显示错误: {e}")

    def import_custom_order(self):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "导入歌曲名单", "",
            "文本文件 (*.txt *.csv);;所有文件 (*.*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            self._custom_order = lines
            import os as osmod
            self.custom_file_lbl.setText(osmod.path.basename(path) + f"  ({len(lines)} 条)")
            self.custom_file_lbl.setStyleSheet("color:#1db100; font-size:12px;")
            self.status_lbl.setText(f"已导入 {len(lines)} 条自定义顺序")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"读取文件失败:\n{e}")

    def clear_custom_order(self):
        self._custom_order = None
        self.custom_file_lbl.setText("未选择文件")
        self.custom_file_lbl.setStyleSheet("color:#888; font-size:12px;")
        self.status_lbl.setText("已清除自定义顺序")

    def _sort_by_custom_order(self, tracks):
        if not self._custom_order:
            return tracks
        name_to_tr = {}
        for tr in tracks:
            name = tr.get("name", "").strip()
            if name:
                name_to_tr[name] = tr
        ordered = []
        unmatched = []
        for name in self._custom_order:
            matched = None
            if name in name_to_tr:
                matched = name_to_tr.pop(name)
            else:
                clean = re.sub(r"[（(].*?[）)]", "", name).strip()
                for k, v in list(name_to_tr.items()):
                    k_clean = re.sub(r"[（(].*?[）)]", "", k).strip()
                    if k_clean == clean:
                        matched = name_to_tr.pop(k)
                        break
            if matched:
                ordered.append(matched)
            else:
                unmatched.append(name)
        for tr in tracks:
            if tr not in ordered:
                ordered.append(tr)
        if unmatched:
            self.status_lbl.setText(f"自定义顺序：{len(ordered)} 首已排，{len(unmatched)} 首未匹配")
        else:
            self.status_lbl.setText(f"自定义顺序：{len(ordered)} 首已排")
        return ordered

    def preview(self):
        _log(f"[preview] called, current_tracks len={len(self.current_tracks) if self.current_tracks else 0}, sort_cbs={[cb.currentText() for cb in self.sort_cbs]}")
        if not self.current_tracks:
            return

        levels = []
        for cb, asc_cb in zip(self.sort_cbs, self.sort_asc_cbs):
            field = cb.currentText()
            if not field:
                continue
            reverse = (asc_cb.currentIndex() == 1)
            levels.append((field, reverse))

        # Special case: 艺人 primary + 入库时间 secondary
        # Group by primary artist, sort artist groups by group's extreme addTime,
        # within each group sort by addTime
        is_artist_primary = len(levels) >= 1 and levels[0][0] == "艺人"
        is_addtime_secondary = len(levels) >= 2 and levels[1][0] == "入库时间"

        if len(levels) == 2 and is_artist_primary and is_addtime_secondary:
            from collections import defaultdict
            # 入库时间第2层的升/降控制艺人组的排序方向
            group_dir = levels[1][1]  # 0=升序(最早入库艺人先)=min, 1=降序(最新入库艺人先)=max
            # 艺人第1层的升/降控制艺人组内歌曲的排序方向
            within_dir = levels[0][1]

            groups = defaultdict(list)
            for tr in self.current_tracks:
                ar = tr.get("fullArtists") or tr.get("artists") or tr.get("ar") or []
                primary = ar[0].get("name", "") if ar else ""
                groups[primary].append(tr)

            groups_list = [(p, list(s)) for p, s in groups.items()]

            # Within each group sort by addTime (controlled by 艺人层的升/降)
            for p, s in groups_list:
                s.sort(key=lambda tr: tr.get("_addTime", 0), reverse=within_dir)

            # Sort artist groups by group's extreme addTime (controlled by 入库时间层的升/降)
            if group_dir:  # 降序 -> newest artist group first (max addTime)
                groups_list.sort(key=lambda g: max(tr.get("_addTime", 0) for tr in g[1]), reverse=True)
            else:  # 升序 -> oldest artist group first (min addTime)
                groups_list.sort(key=lambda g: min(tr.get("_addTime", 0) for tr in g[1]), reverse=False)

            ordered = []
            for p, s in groups_list:
                ordered.extend(s)

        else:
            # Standard multi-level stable sort
            ordered = list(self.current_tracks)
            for field, reverse in levels:
                if field == "自定义顺序":
                    ordered = self._sort_by_custom_order(ordered)
                elif field == "艺人":
                    def _key(tr): return "/".join(a.get("name", "") for a in (tr.get("ar") or []) if a.get("name"))
                    ordered.sort(key=_key, reverse=reverse)
                elif field == "专辑":
                    def _key(tr): return (tr.get("al") or {}).get("name", "") if isinstance(tr.get("al"), dict) else ""
                    ordered.sort(key=_key, reverse=reverse)
                elif field == "歌曲名":
                    def _key(tr): return tr.get("name", "")
                    ordered.sort(key=_key, reverse=reverse)
                elif field == "入库时间":
                    def _key(tr): return tr.get("_addTime", 0)
                    ordered.sort(key=_key, reverse=reverse)

        self._sorted_tracks = ordered
        self._show_sorted_tracks(ordered)
        self.apply_btn.setEnabled(True)

    def _show_sorted_tracks(self, tracks):
        try:
            self.table.setRowCount(len(tracks))
            for i, tr in enumerate(tracks):
                self.table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
                self.table.setItem(i, 1, QTableWidgetItem(str(tr.get("name", ""))))
                ar = tr.get("fullArtists") or tr.get("artists") or tr.get("ar") or []
                self.table.setItem(i, 2, QTableWidgetItem("/".join(a.get("name", "") for a in ar if a.get("name"))))
                al = tr.get("album") or tr.get("al") or {}
                al_name = al.get("name", "") if isinstance(al, dict) else ""
                self.table.setItem(i, 3, QTableWidgetItem(al_name))
                track_id = tr.get("encId") or tr.get("id", "")
                self.table.setItem(i, 4, QTableWidgetItem(str(track_id)))
                add_time = (tr.get("extMap") or {}).get("addTime", 0) or tr.get("_addTime", 0)
                if add_time:
                    import datetime
                    dt = datetime.datetime.fromtimestamp(add_time / 1000)
                    self.table.setItem(i, 5, QTableWidgetItem(dt.strftime("%Y-%m-%d %H:%M")))
                else:
                    self.table.setItem(i, 5, QTableWidgetItem("-"))
            self.table.resizeRowsToContents()
            self.status_lbl.setText(f"共 {len(tracks)} 首（预览模式）")
        except Exception as e:
            _log(f"[_show_sorted_tracks] EXCEPTION: {e}")
            self.status_lbl.setText(f"预览失败: {e}")

    def apply_to_server(self):
        _log(f"[apply_to_server] _sorted_tracks={type(self._sorted_tracks).__name__}, len={len(self._sorted_tracks) if self._sorted_tracks else 0}")
        if not self._sorted_tracks:
            QMessageBox.warning(self, "错误", "请先点击「预览」生成排序顺序")
            return
        if not self.current_pl_enc_id:
            QMessageBox.warning(self, "错误", "未选择歌单")
            return

        # 从 sorted_tracks 提取加密ID（encId 字段）
        enc_ids = [tr.get("encId") for tr in self._sorted_tracks if tr.get("encId")]
        _log(f"[apply_to_server] first track keys={list(self._sorted_tracks[0].keys()) if self._sorted_tracks else []}")
        _log(f"[apply_to_server] enc_ids count={len(enc_ids)}, first={enc_ids[0] if enc_ids else None}")
        if not enc_ids:
            QMessageBox.warning(self, "错误", "无法获取歌曲加密ID（歌单可能为空）")
            return

        reply = QMessageBox.question(
            self, "确认", 
            f"确定要将「{self.playlist_list.currentItem().text().split('(')[0].strip()}」的 {len(enc_ids)} 首歌曲按当前顺序排序到服务器？\n\n此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.status_lbl.setText("正在应用排序到服务器...")
        self.apply_btn.setEnabled(False)
        threading.Thread(target=self._bg_reorder, args=(enc_ids,), daemon=True).start()

    def _bg_reorder(self, enc_ids):
        result = ncm_reorder(self.current_pl_enc_id, enc_ids)
        QTimer.singleShot(0, lambda: self._on_reorder_result(result, enc_ids))

    def _on_reorder_result(self, result, enc_ids):
        self.apply_btn.setEnabled(True)
        if result is None:
            QMessageBox.warning(self, "错误", "调用 reorder 失败，请检查网络和登录状态")
            self.status_lbl.setText("应用失败")
            return
        code = result.get("code")
        if code == 200:
            # 更新本地服务器数据
            self.server_track_ids = enc_ids
            # 用新顺序重新构建 current_tracks
            enc_to_tr = {tr.get("encId"): tr for tr in self.current_tracks if tr.get("encId")}
            self.current_tracks = [enc_to_tr[e] for e in enc_ids if e in enc_to_tr]
            self._sorted_tracks = None
            self.status_lbl.setText(f"✅ 排序成功应用（{len(enc_ids)} 首）")
            QMessageBox.information(self, "成功", f"已成功将 {len(enc_ids)} 首歌曲排序到服务器！\n\n刷新歌单即可看到新顺序。")
        else:
            msg = result.get("message", "未知错误")
            QMessageBox.warning(self, "排序失败", f"服务器返回错误：{msg}\n\ncode: {code}")
            self.status_lbl.setText(f"排序失败：{msg}")

    def export_playlist(self):
        rows = self.table.rowCount()
        if rows == 0:
            return
        names = []
        for r in range(rows):
            item = self.table.item(r, 1)
            if item:
                names.append(item.text())
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        default_name = "playlist.xlsx"
        if self.playlist_list.currentItem():
            default_name = self.playlist_list.currentItem().text().split("(")[0].strip() + ".xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "导出歌曲名单", default_name, "Excel 表格 (*.xlsx);;所有文件 (*.*)")
        if not path:
            return
        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "歌曲排序"
            ws.append(["序号", "歌曲名", "艺人", "专辑", "加密ID", "入库时间"])
            for r in range(rows):
                row_data = []
                for c in range(6):
                    item = self.table.item(r, c)
                    row_data.append(item.text() if item else "")
                ws.append(row_data)
            wb.save(path)
            self.status_lbl.setText(f"已导出 {rows} 首")
            QMessageBox.information(self, "完成", f"已导出 {rows} 首歌曲到：\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"导出失赫:\n{e}")
            QMessageBox.warning(self, "错误", f"导出失败:\n{e}")



    def import_playlist(self):
        """从 Excel 表格导入歌曲顺序（用于自定义排序）"""
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        if not self.current_tracks:
            QMessageBox.information(self, "提示", "请先加载歌单歌曲")
            return
        path, _ = QFileDialog.getOpenFileName(self, "导入歌曲名单", "", "Excel 表格 (*.xlsx);;所有文件 (*.*)")
        if not path:
            return
        try:
            wb = openpyxl.load_workbook(path)
            ws = wb.active
            rows_data = list(ws.iter_rows(min_row=2, values_only=True))  # skip header
            if not rows_data:
                QMessageBox.information(self, "提示", "表格中没有数据")
                return
            encid_to_tr = {tr.get("encId"): tr for tr in self.current_tracks if tr.get("encId")}
            ordered = []
            missing = 0
            for row in rows_data:
                seq, name, artist, album, enc_id, add_time = (row[i] if i < len(row) else None for i in range(6))
                if not enc_id:
                    continue
                tr = encid_to_tr.get(enc_id)
                if tr:
                    ordered.append(tr)
                else:
                    missing += 1
            if not ordered:
                QMessageBox.warning(self, "错误", "未能匹配到任何歌曲（歌单可能有变化）")
                return
            self._sorted_tracks = ordered
            self._show_sorted_tracks(ordered)
            self.apply_btn.setEnabled(True)
            self.status_lbl.setText(f"已导入 {len(ordered)} 首" + (f"（{missing} 首未匹配）" if missing else ""))
            QMessageBox.information(self, "完成", f"已从 Excel 导入 {len(ordered)} 首歌曲顺序" + (f"\n{missing} 首未匹配（歌单可能有变化）" if missing else ""))
        except Exception as e:
            QMessageBox.warning(self, "错误", f"导入失败:\n{e}")

    def copy_result(self):
        rows = self.table.rowCount()
        if rows == 0:
            return
        ids = []
        for r in range(rows):
            item = self.table.item(r, 4)
            if item and item.text():
                ids.append(item.text())
        if not ids:
            QMessageBox.warning(self, "错误", "无法获取歌曲 ID")
            return
        text = ",".join(ids)
        QApplication.clipboard().setText(text)
        self.status_lbl.setText(f"已复制 {len(ids)} 个歌曲 ID 到剪贴板")
        QMessageBox.information(self, "已复制", f"已复制 {len(ids)} 个歌曲 ID 到剪贴板")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
