"""主窗口"""
import datetime
import os
import threading

from PyQt6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                             QListWidget, QTableWidget, QTableWidgetItem,
                             QPushButton, QComboBox, QLabel, QMessageBox, QHeaderView,
                             QAbstractItemView, QGroupBox, QCheckBox,
                             QVBoxLayout as QVBL2, QProgressBar)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QGuiApplication, QClipboard

from logger import _log
from core.ncm_client import (
    ncm_login_check, ncm_logout, ncm_login,
    ncm_get_tracks, ncm_reorder,
)
from ui.login_dialog import LoginDialog
from utils.sort import sort_multi_level, sort_by_custom_order
from utils.excel import export_table_to_excel, import_tracks_from_excel


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
        self._pl_total_tracks = 0      # 歌单总歌曲数（从playlist元数据获取）
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
        if dlg.exec() == LoginDialog.DialogCode.Accepted:
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

        self.reload_btn = QPushButton("🔄 重新加载")
        self.reload_btn.setStyleSheet("color:#555; padding:4px 10px;")
        self.reload_btn.clicked.connect(self._on_reload)
        self.reload_btn.setEnabled(False)
        left.addWidget(self.reload_btn)

        self.load_time_cb = QCheckBox("加载发行时间")
        self.load_time_cb.setChecked(True)
        self.load_time_cb.setStyleSheet("color:#666; font-size:12px;")
        left.addWidget(self.load_time_cb)

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
            cb.addItems(["", "艺人", "专辑", "歌曲名", "入库时间", "专辑发行时间", "自定义顺序"])
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
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["#", "歌曲名", "艺人", "专辑", "ID", "入库时间", "发行时间"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(500)
        right.addWidget(self.table)

        self.status_lbl = QLabel("就绪")
        self.status_lbl.setStyleSheet("color:#888; font-size:12px;")
        right.addWidget(self.status_lbl)

        # 专辑信息加载进度条（放在 status_lbl 下方）
        self.album_progress = QProgressBar()
        self.album_progress.setFixedHeight(8)
        self.album_progress.setTextVisible(False)
        self.album_progress.setStyleSheet("QProgressBar { border: none; background: #e0e0e0; border-radius: 4px; } QProgressBar::chunk { background: #1db100; border-radius: 4px; }")
        self.album_progress.setVisible(False)
        right.addWidget(self.album_progress)

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
        from core.ncm_client import ncm_get_playlists
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
        self._pl_total_tracks = p.get("trackCount", 0) or 0  # 歌单总歌曲数
        self._sorted_tracks = None
        self.apply_btn.setEnabled(False)
        self.album_progress.setVisible(True)
        self.album_progress.setMaximum(0)
        self.album_progress.setValue(0)
        self.status_lbl.setText("加载歌曲...")
        self.reload_btn.setEnabled(False)
        threading.Thread(target=self._bg_load_tracks, daemon=True).start()

    def _on_reload(self):
        if not self.current_pl_enc_id:
            return
        self._sorted_tracks = None
        self.apply_btn.setEnabled(False)
        self.album_progress.setVisible(True)
        self.album_progress.setMaximum(0)
        self.album_progress.setValue(0)
        self.status_lbl.setText("加载歌曲...")
        self.reload_btn.setEnabled(False)
        self._pl_total_tracks = getattr(self, '_pl_total_tracks', 0) or 0
        threading.Thread(target=self._bg_load_tracks, daemon=True).start()

    def _bg_load_tracks(self):
        _log(f"[_bg_load_tracks] start, playlistId={self.current_pl_enc_id}")
        total_albums = 0
        fetched_albums = [0]  # 用列表包装以便在内层函数修改

        def _on_album_progress(cur, total):
            total_albums = total
            fetched_albums[0] = cur
            def _do():
                self.album_progress.setVisible(True)
                self.album_progress.setMaximum(total)
                self.album_progress.setValue(cur)
                self.status_lbl.setText(f"加载歌曲 {cur}/{total}")
            QTimer.singleShot(0, _do)

        enc_ids, tracks_data = ncm_get_tracks(
            self.current_pl_enc_id, _on_album_progress,
            load_publish_time=self.load_time_cb.isChecked()
        )
        def _done():
            self.album_progress.setVisible(False)
            self.status_lbl.setText("就绪")
        QTimer.singleShot(0, _done)
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
                "publishTime": t.get("publishTime", 0),
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
                    "publishTime": info.get("publishTime", 0),
                }
            else:
                tr = {"id": orig_id, "encId": enc, "name": "（无信息）", "ar": [], "al": {}, "_addTime": 0, "publishTime": 0}
            ordered_tracks.append(tr)
        _log(f"[_bg_load_tracks] first ordered_track keys={list(ordered_tracks[0].keys()) if ordered_tracks else 'empty'}")
        self._sorted_tracks = None
        _log(f"[_bg_load_tracks] calling _show_tracks directly with {len(ordered_tracks)} tracks")
        self._show_tracks(ordered_tracks)

        def _reload_done():
            self.reload_btn.setEnabled(True)
        QTimer.singleShot(0, _reload_done)

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
                    dt = datetime.datetime.fromtimestamp(add_time / 1000)
                    self.table.setItem(i, 5, QTableWidgetItem(dt.strftime("%Y-%m-%d %H:%M")))
                else:
                    self.table.setItem(i, 5, QTableWidgetItem("-"))
                pt = tr.get("publishTime", 0)
                if pt and pt > 0:
                    pub_dt = datetime.datetime.fromtimestamp(pt / 1000)
                    self.table.setItem(i, 6, QTableWidgetItem(pub_dt.strftime("%Y-%m-%d")))
                else:
                    self.table.setItem(i, 6, QTableWidgetItem("-"))
            self.table.resizeRowsToContents()
            self.export_btn.setEnabled(shown > 0)
            self.reload_btn.setEnabled(True)
            pl_total = getattr(self, '_pl_total_tracks', 0) or 0
            if pl_total > shown:
                self.status_lbl.setText(f"已加载 {shown}/{pl_total} 首（歌单较大，部分歌曲暂无法排序）")
                self.status_lbl.setStyleSheet("color:#e55;")
            elif total > shown:
                self.status_lbl.setText(f"显示 {shown}/{total} 首（歌单共 {total} 首）")
            else:
                self.status_lbl.setText(f"共 {shown} 首")
                self.status_lbl.setStyleSheet("")
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
            self.custom_file_lbl.setText(os.path.basename(path) + f"  ({len(lines)} 条)")
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
        ordered, unmatched = sort_by_custom_order(tracks, self._custom_order)
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

        ordered = sort_multi_level(
            self.current_tracks,
            levels,
            custom_order=self._custom_order if any(lvl[0] == "自定义顺序" for lvl in levels) else None,
        )

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
                    dt = datetime.datetime.fromtimestamp(add_time / 1000)
                    self.table.setItem(i, 5, QTableWidgetItem(dt.strftime("%Y-%m-%d %H:%M")))
                else:
                    self.table.setItem(i, 5, QTableWidgetItem("-"))
                pt = tr.get("publishTime", 0)
                if pt and pt > 0:
                    pub_dt = datetime.datetime.fromtimestamp(pt / 1000)
                    self.table.setItem(i, 6, QTableWidgetItem(pub_dt.strftime("%Y-%m-%d")))
                else:
                    self.table.setItem(i, 6, QTableWidgetItem("-"))
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
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        default_name = "playlist.xlsx"
        if self.playlist_list.currentItem():
            default_name = self.playlist_list.currentItem().text().split("(")[0].strip() + ".xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "导出歌曲名单", default_name, "Excel 表格 (*.xlsx);;所有文件 (*.*)")
        if not path:
            return
        try:
            rows = export_table_to_excel(self.table, default_name, path)
            self.status_lbl.setText(f"已导出 {rows} 首")
            QMessageBox.information(self, "完成", f"已导出 {rows} 首歌曲到：\n{path}")
        except Exception as e:
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
            ordered, missing = import_tracks_from_excel(path, self.current_tracks)
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
