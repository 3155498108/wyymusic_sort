"""主窗口"""
import datetime
import os
import threading

from PyQt6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                             QListWidget, QTableWidget, QTableWidgetItem,
                             QPushButton, QComboBox, QLabel, QMessageBox, QHeaderView,
                             QAbstractItemView, QCheckBox,
                             QVBoxLayout as QVBL2, QProgressBar, QDialog,
                             QApplication, QFileDialog)
from PyQt6.QtCore import QTimer, Qt

from logger import _log
from constants import CONFIG_FILE
from core.ncm_client import (
    ncm_login_check, ncm_logout, ncm_login,
    ncm_get_tracks, ncm_reorder, ncm_create_and_fill_playlist,
    ncm_fill_publish_time, ncm_reorder_in_place,
)
from ui.login_dialog import LoginDialog
from ui.config_dialog import ConfigDialog
from ui.ai_sort_dialog import AISortDialog
from ui.search_dialog import SearchDialog
from ui.theme import apply_dark_title_bar
from ui.ui_thread import post
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
        self._ensure_config()
        self._check_login()
        QTimer.singleShot(300, self.load_playlists)

    def _ensure_config(self):
        if not os.path.exists(CONFIG_FILE):
            dlg = ConfigDialog(self)
            if dlg.exec() != ConfigDialog.DialogCode.Accepted:
                import sys
                sys.exit(0)

    def _check_login(self):
        status = ncm_login_check()
        if status.get("success"):
            msg = status.get("message", "已登录")
            self.status_lbl2.setText(f"● {msg}")
            self.status_lbl2.setStyleSheet("color:#4FC08D; font-size:12px;")
            self.login_btn.setText("退出登录")
            self.login_btn.setProperty("variant", "ghost")
            self.login_btn.setEnabled(True)
        else:
            self.status_lbl2.setText("○ 未登录")
            self.status_lbl2.setStyleSheet("color:#E06C6C; font-size:12px;")
            self.login_btn.setText("扫码登录")
            self.login_btn.setProperty("variant", "primary")
            self.login_btn.setEnabled(True)
        self._repolish(self.login_btn)

    @staticmethod
    def _repolish(widget):
        """动态属性改变后重新应用样式"""
        widget.style().unpolish(widget)
        widget.style().polish(widget)

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
            self.current_tracks = []
            self.title_lbl.setText("未选择歌单")
            self.sub_lbl.setText("从左侧选择一个歌单开始")
            self.status_lbl.setText("已退出登录")
        else:
            QMessageBox.warning(self, "错误", "退出登录失败")

    def _on_login_btn_click(self):
        status = ncm_login_check()
        if status.get("success"):
            self._logout()
        else:
            self._show_login()

    def _open_config(self):
        dlg = ConfigDialog(self)
        dlg.exec()

    def _setup_ui(self):
        self.setWindowTitle("网易云歌单排序器")
        self.setMinimumSize(1100, 680)
        self.resize(1280, 800)

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_content(), 1)

        apply_dark_title_bar(self)

    def _build_sidebar(self) -> QWidget:
        """左侧栏：品牌 + 我的歌单 + 文件操作 + 登录状态"""
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(238)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(14, 18, 14, 14)
        lay.setSpacing(10)

        # 品牌
        brand_row = QHBoxLayout()
        brand_row.setSpacing(9)
        logo = QLabel("♪")
        logo.setObjectName("logo")
        logo.setFixedSize(26, 26)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_row.addWidget(logo)
        brand = QLabel("网易云歌单排序器")
        brand.setProperty("variant", "brand")
        brand_row.addWidget(brand)
        brand_row.addStretch()
        lay.addLayout(brand_row)
        lay.addSpacing(8)

        # 我的歌单
        title_row = QHBoxLayout()
        title_row.setSpacing(2)
        pl_title = QLabel("我的歌单")
        pl_title.setProperty("variant", "section")
        title_row.addWidget(pl_title)
        title_row.addStretch()
        refresh_btn = QPushButton("刷新")
        refresh_btn.setToolTip("重新获取歌单列表")
        refresh_btn.setProperty("variant", "ghost")
        refresh_btn.clicked.connect(self.load_playlists)
        self.reload_btn = QPushButton("重载")
        self.reload_btn.setProperty("variant", "ghost")
        self.reload_btn.setToolTip("重新加载当前歌单的歌曲")
        self.reload_btn.clicked.connect(self._on_reload)
        self.reload_btn.setEnabled(False)
        title_row.addWidget(refresh_btn)
        title_row.addWidget(self.reload_btn)
        lay.addLayout(title_row)

        self.playlist_list = QListWidget()
        self.playlist_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.playlist_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.playlist_list.currentRowChanged.connect(self._on_select)
        lay.addWidget(self.playlist_list, 1)

        # 选项
        self.load_time_cb = QCheckBox("加载发行时间（较慢）")
        self.load_time_cb.setChecked(False)
        self.load_time_cb.setToolTip(
            "专辑发行时间要逐张专辑请求，专辑多的大歌单会明显变慢。\n"
            "不勾选时，排序用到「专辑发行时间」会提示按需加载（结果会缓存）。")
        lay.addWidget(self.load_time_cb)

        self.show_id_cb = QCheckBox("显示歌曲 ID")
        self.show_id_cb.setChecked(False)
        self.show_id_cb.toggled.connect(lambda on: self.table.setColumnHidden(4, not on))
        lay.addWidget(self.show_id_cb)

        file_row = QHBoxLayout()
        file_row.setSpacing(8)
        self.import_btn = QPushButton("导入 Excel")
        self.import_btn.clicked.connect(self.import_playlist)
        self.export_btn = QPushButton("导出 Excel")
        self.export_btn.clicked.connect(self.export_playlist)
        self.export_btn.setEnabled(False)
        file_row.addWidget(self.import_btn)
        file_row.addWidget(self.export_btn)
        lay.addLayout(file_row)

        # 登录
        divider = QWidget()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background:#232323;")
        lay.addWidget(divider)

        self.status_lbl2 = QLabel("检测登录状态中...")
        self.status_lbl2.setProperty("variant", "weak")
        lay.addWidget(self.status_lbl2)

        self.login_btn = QPushButton("扫码登录")
        self.login_btn.setProperty("variant", "primary")
        self.login_btn.clicked.connect(self._on_login_btn_click)
        lay.addWidget(self.login_btn)
        return side

    def _build_content(self) -> QWidget:
        """右侧：顶栏 + 歌单头部 + 排序卡片 + 曲目列表 + 状态条"""
        content = QWidget()
        content.setObjectName("content")
        outer = QVBoxLayout(content)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(22, 16, 22, 10)
        lay.setSpacing(12)

        # ---- 顶栏
        top = QHBoxLayout()
        top.setSpacing(10)
        self.search_artists_btn = QPushButton("搜索歌曲 / 专辑")
        self.search_artists_btn.setProperty("variant", "search")
        self.search_artists_btn.setFixedHeight(32)
        self.search_artists_btn.setMinimumWidth(250)
        self.search_artists_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_artists_btn.setToolTip("跨歌单按歌手/专辑/歌曲名筛选，或全网搜索专辑，收进新歌单")
        self.search_artists_btn.clicked.connect(self._show_search_dialog)
        top.addWidget(self.search_artists_btn)
        top.addStretch()

        self.ai_sort_btn = QPushButton("AI 排序")
        self.ai_sort_btn.setProperty("variant", "ghost")
        self.ai_sort_btn.clicked.connect(self._show_ai_sort_dialog)
        top.addWidget(self.ai_sort_btn)

        config_btn = QPushButton("设置")
        config_btn.setProperty("variant", "ghost")
        config_btn.clicked.connect(self._open_config)
        top.addWidget(config_btn)
        lay.addLayout(top)

        # ---- 歌单头部
        head = QHBoxLayout()
        head.setSpacing(12)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self.title_lbl = QLabel("未选择歌单")
        self.title_lbl.setProperty("variant", "h1")
        self.sub_lbl = QLabel("从左侧选择一个歌单开始")
        self.sub_lbl.setProperty("variant", "sub")
        title_col.addWidget(self.title_lbl)
        title_col.addWidget(self.sub_lbl)
        head.addLayout(title_col)
        head.addStretch()

        preview_btn = QPushButton("▶")
        preview_btn.setProperty("variant", "round")
        preview_btn.setFixedSize(38, 38)
        preview_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        preview_btn.setToolTip("预览排序结果")
        preview_btn.clicked.connect(self.preview)
        head.addWidget(preview_btn)

        self.apply_btn = QPushButton("应用到服务器")
        self.apply_btn.setProperty("variant", "primary")
        self.apply_btn.setMinimumHeight(34)
        self.apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_btn.clicked.connect(self.apply_to_server)
        self.apply_btn.setEnabled(False)
        head.addWidget(self.apply_btn)
        lay.addLayout(head)

        # ---- 排序卡片
        card = QWidget()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 12, 16, 12)
        cl.setSpacing(10)

        sort_row = QHBoxLayout()
        sort_row.setSpacing(8)
        sort_lbl = QLabel("多级排序")
        sort_lbl.setProperty("variant", "section")
        sort_row.addWidget(sort_lbl)
        sort_row.addSpacing(6)

        self.sort_cbs = []
        self.sort_asc_cbs = []
        for i, label in enumerate(["第1层", "第2层", "第3层"]):
            cb = QComboBox()
            cb.addItems(["未设置", "艺人", "专辑", "歌曲名", "入库时间", "专辑发行时间", "自定义顺序"])
            cb.setMinimumWidth(104)
            asc_cb = QComboBox()
            asc_cb.addItems(["升序", "降序"])
            asc_cb.setFixedWidth(72)
            lbl = QLabel(label)
            lbl.setProperty("variant", "weak")
            sort_row.addWidget(lbl)
            sort_row.addWidget(cb)
            sort_row.addWidget(asc_cb)
            self.sort_cbs.append(cb)
            self.sort_asc_cbs.append(asc_cb)
        sort_row.addStretch()
        cl.addLayout(sort_row)

        custom_row = QHBoxLayout()
        custom_row.setSpacing(8)
        custom_lbl = QLabel("自定义顺序")
        custom_lbl.setProperty("variant", "section")
        custom_row.addWidget(custom_lbl)
        self.custom_file_lbl = QLabel("未选择文件")
        self.custom_file_lbl.setProperty("variant", "weak")
        self.custom_file_lbl.setMaximumWidth(420)
        custom_row.addWidget(self.custom_file_lbl)
        custom_import_btn = QPushButton("导入名单")
        custom_import_btn.clicked.connect(self.import_custom_order)
        custom_row.addWidget(custom_import_btn)
        custom_clear_btn = QPushButton("清除")
        custom_clear_btn.clicked.connect(self.clear_custom_order)
        custom_row.addWidget(custom_clear_btn)
        custom_row.addStretch()

        copy_btn = QPushButton("复制结果")
        copy_btn.setProperty("variant", "ghost")
        copy_btn.clicked.connect(self.copy_result)
        custom_row.addWidget(copy_btn)
        cl.addLayout(custom_row)
        lay.addWidget(card)

        # ---- 曲目表
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["#", "歌曲名", "艺人", "专辑", "ID", "入库时间", "发行时间"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setDefaultSectionSize(38)
        header = self.table.horizontalHeader()
        header.setFixedHeight(36)
        header.setHighlightSections(False)
        widths = {0: 42, 2: 222, 3: 286, 4: 96, 5: 126, 6: 92}
        for col, w in widths.items():
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(col, w)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnHidden(4, True)
        self.table.setMinimumHeight(360)
        lay.addWidget(self.table, 1)

        outer.addWidget(body, 1)

        # ---- 底部状态条
        bottom = QWidget()
        bottom.setObjectName("bottombar")
        bottom.setFixedHeight(42)
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(22, 0, 22, 0)
        bl.setSpacing(12)
        self.status_lbl = QLabel("就绪")
        self.status_lbl.setProperty("variant", "weak")
        bl.addWidget(self.status_lbl, 1)
        self.album_progress = QProgressBar()
        self.album_progress.setFixedHeight(4)
        self.album_progress.setFixedWidth(220)
        self.album_progress.setTextVisible(False)
        self.album_progress.setVisible(False)
        bl.addWidget(self.album_progress)
        outer.addWidget(bottom)
        return content

    def load_playlists(self):
        self.status_lbl.setText("加载歌单...")
        self.playlist_list.clear()
        threading.Thread(target=self._bg_load_pl, daemon=True).start()

    def _bg_load_pl(self):
        # 先检查登录状态
        login_status = ncm_login_check()
        if not login_status.get("success"):
            post(self.status_lbl.setText, "⚠ 未登录，请先扫码登录")
            return
        from core.ncm_client import ncm_get_playlists
        self.playlists = ncm_get_playlists()
        if not self.playlists:
            # ncm_get_playlists 失败，可能是全局 ncm-cli 未安装
            post(self.status_lbl.setText,
                 "⚠ 获取歌单失败。请确保已安装全局 ncm-cli：\nnpm install -g @music163/ncm-cli")
            return
        post(self._show_pl)

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
        self.current_pl_name = p.get("name", "?")  # 用于创建新歌单名字
        self._pl_total_tracks = p.get("trackCount", 0) or 0  # 歌单总歌曲数
        self._load_pt = self.load_time_cb.isChecked()
        self._sorted_tracks = None
        self.apply_btn.setEnabled(False)
        self.title_lbl.setText(self.current_pl_name)
        self.sub_lbl.setText(f"共 {self._pl_total_tracks} 首" if self._pl_total_tracks else "加载中...")
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
        self._load_pt = self.load_time_cb.isChecked()
        threading.Thread(target=self._bg_load_tracks, daemon=True).start()

    def _bg_load_tracks(self):
        _log(f"[_bg_load_tracks] start, playlistId={self.current_pl_enc_id}")

        def _on_album_progress(cur, total):
            def _do():
                self.album_progress.setVisible(True)
                self.album_progress.setMaximum(total)
                self.album_progress.setValue(cur)
                self.status_lbl.setText(f"加载歌曲 {cur}/{total}")
            post(_do)

        enc_ids, tracks_data = ncm_get_tracks(
            self.current_pl_enc_id, _on_album_progress,
            load_publish_time=getattr(self, "_load_pt", True)
        )
        def _done():
            self.album_progress.setVisible(False)
            self.status_lbl.setText("就绪")
        post(_done)
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
        _log(f"[_bg_load_tracks] scheduling _show_tracks with {len(ordered_tracks)} tracks")
        # UI 更新必须回到主线程
        post(self._show_tracks, ordered_tracks)
        post(self.reload_btn.setEnabled, True)

    def _fill_table(self, tracks):
        """把 tracks 填充到表格（供加载与预览共用）"""
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
            self.table.item(i, 1).setToolTip(f"加密ID：{track_id}")
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

    def _show_tracks(self, tracks):
        _log(f"[_show_tracks] CALLED with {len(tracks)} tracks")
        try:
            total = len(self.server_track_ids)
            shown = len(tracks)
            self._fill_table(tracks)
            self.export_btn.setEnabled(shown > 0)
            self.reload_btn.setEnabled(True)
            pl_total = getattr(self, '_pl_total_tracks', 0) or 0
            self.sub_lbl.setText(f"共 {shown} 首")
            if pl_total > shown:
                self.status_lbl.setText(f"歌单较大，仅加载了 {shown}/{pl_total} 首")
            elif total > shown:
                self.status_lbl.setText(f"显示 {shown}/{total} 首")
            else:
                self.status_lbl.setText("就绪")
            _log(f"[_show_tracks] DONE, set {shown} rows")
        except Exception as e:
            _log(f"[_show_tracks] EXCEPTION: {type(e).__name__}: {e}")
            self.status_lbl.setText(f"显示错误: {e}")

    def import_custom_order(self):
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
            if not field or field == "未设置":
                continue
            reverse = (asc_cb.currentIndex() == 1)
            levels.append((field, reverse))

        # 按「专辑发行时间」排序时才按需加载（避免每首歌单都逐张专辑请求）
        if any(field == "专辑发行时间" for field, _ in levels):
            if self._ensure_publish_time():
                return

        ordered = sort_multi_level(
            self.current_tracks,
            levels,
            custom_order=self._custom_order if any(lvl[0] == "自定义顺序" for lvl in levels) else None,
        )

        self._sorted_tracks = ordered
        self._show_sorted_tracks(ordered)
        self.apply_btn.setEnabled(True)

    def _missing_publish_time_albums(self) -> int:
        """统计还没加载发行时间的专辑数量"""
        albums = set()
        for tr in self.current_tracks:
            if tr.get("publishTime"):
                continue
            al = tr.get("album") or tr.get("al") or {}
            aid = al.get("id") if isinstance(al, dict) else ""
            if aid:
                albums.add(str(aid))
        return len(albums)

    def _ensure_publish_time(self) -> bool:
        """按需加载专辑发行时间；返回 True 表示已开始在后台加载（本次预览中止）"""
        if getattr(self, "_pt_loading", False):
            return True
        album_count = self._missing_publish_time_albums()
        if album_count <= 0:
            return False

        reply = QMessageBox.question(
            self, "需要加载发行时间",
            f"还有 {album_count} 张专辑的发行时间未加载。\n"
            f"加载需要逐张专辑请求，首次会比较慢（之后会缓存，无需重复加载）。\n\n"
            f"是否现在加载并继续排序？（选择「否」则发行时间显示为 -）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return False

        self._pt_loading = True
        self.apply_btn.setEnabled(False)
        self.album_progress.setVisible(True)
        self.album_progress.setMaximum(0)
        self.status_lbl.setText("正在加载专辑发行时间...")

        def _progress(cur, total):
            def _do():
                self.album_progress.setVisible(True)
                self.album_progress.setMaximum(max(total, 1))
                self.album_progress.setValue(cur)
                self.status_lbl.setText(f"加载专辑发行时间 {cur}/{total}")
            post(_do)

        def _bg():
            try:
                ncm_fill_publish_time(self.current_tracks, _progress)
            except Exception as e:
                _log(f"[_ensure_publish_time] failed: {e}")

            def _done():
                self._pt_loading = False
                self.album_progress.setVisible(False)
                self.status_lbl.setText("发行时间加载完成")
                self.preview()
            post(_done)

        threading.Thread(target=_bg, daemon=True).start()
        return True

    def _show_sorted_tracks(self, tracks):
        try:
            self._fill_table(tracks)
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

        playlist_name = self.playlist_list.currentItem().text().split("(")[0].strip()
        is_large = len(enc_ids) > 200

        # 统一弹窗：新建歌单 / 原地修改（≤200 直接重排，>200 用组合方案）
        dlg = QDialog(self)
        dlg.setWindowTitle("选择排序方式")
        dlg.setMinimumWidth(460)
        layout = QVBL2()
        layout.setContentsMargins(22, 18, 22, 16)
        layout.setSpacing(10)

        if is_large:
            tip = QLabel(
                f"歌单共 {len(enc_ids)} 首，超过 200 首时无法一次性重排（ID 过长会被服务端拒绝）。\n"
                "可以选择新建一个排序后的副本，或者原地重排：")
            tip.setWordWrap(True)
            layout.addWidget(tip)
        else:
            layout.addWidget(QLabel(f"歌单共 {len(enc_ids)} 首，请选择排序方式："))
        layout.addSpacing(6)

        def do_new():
            dlg.accept()
            new_name = f"{playlist_name}-排序版"
            self.status_lbl.setText("正在创建新歌单并添加歌曲...")
            self.apply_btn.setEnabled(False)
            threading.Thread(target=self._bg_create_and_fill, args=(enc_ids, new_name), daemon=True).start()

        def do_reorder():
            dlg.accept()
            if is_large:
                self.status_lbl.setText("正在原地重排（分两步，请勿刷新歌单）...")
            else:
                self.status_lbl.setText("正在应用排序到服务器...")
            self.apply_btn.setEnabled(False)
            threading.Thread(target=self._bg_reorder, args=(enc_ids,), daemon=True).start()

        btn_new = QPushButton(f"新建歌单「{playlist_name}-排序版」\n（稳定可靠，原歌单不变）")
        btn_new.setMinimumHeight(62)
        btn_new.setProperty("variant", "primary")
        btn_new.clicked.connect(do_new)
        layout.addWidget(btn_new)

        if is_large:
            btn_reorder = QPushButton(
                "原地重排（保留原歌单）\n"
                "⚠️ 歌曲「入库时间」会刷新为现在；个别受限歌曲可能加不回去")
        else:
            btn_reorder = QPushButton("直接修改原歌单\n（快速）")
        btn_reorder.setMinimumHeight(62)
        btn_reorder.clicked.connect(do_reorder)
        layout.addWidget(btn_reorder)

        layout.addSpacing(4)
        hint = QLabel("提示：重排完成前请勿在网页或客户端刷新歌单。")
        hint.setProperty("variant", "weak")
        layout.addWidget(hint)
        dlg.setLayout(layout)
        dlg.exec()

    def _bg_create_and_fill(self, enc_ids, new_name=None):
        if new_name is None:
            new_name = f"{getattr(self, 'current_pl_name', '歌单')}-排序版"
        result = ncm_create_and_fill_playlist(new_name, enc_ids)
        _log("[_bg_create_and_fill] done, posting UI update")
        post(self._do_update_ui_new_playlist, result, enc_ids, new_name)

    def _bg_reorder(self, enc_ids):
        _log("[_bg_reorder] started")
        if len(enc_ids) > 200:
            # 大歌单：单次 reorder 放不下，用「reorder 尾段 + add 前段」组合方案
            def _progress(cur, total, msg):
                def _do():
                    self.album_progress.setVisible(True)
                    self.album_progress.setMaximum(max(total, 1))
                    self.album_progress.setValue(cur)
                    self.status_lbl.setText(msg)
                post(_do)

            result = ncm_reorder_in_place(self.current_pl_enc_id, enc_ids, progress_callback=_progress)
        else:
            result = ncm_reorder(self.current_pl_enc_id, enc_ids)
        _log("[_bg_reorder] done, posting UI update")
        post(self._do_update_ui, result, enc_ids)

    def _do_update_ui(self, result, enc_ids):
        _log(f"[_do_update_ui] called, result={result}")
        self.apply_btn.setEnabled(True)
        if result is None:
            QTimer.singleShot(0, lambda: QMessageBox.warning(self, "错误", "调用 reorder 失败，请检查网络和登录状态"))
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
            data = result.get("data") or {}
            missing = data.get("missing") or []
            note = data.get("message") or ""
            if note:
                self.status_lbl.setText(f"⚠️ 排序已应用，但{note}")
            else:
                self.status_lbl.setText(f"✅ 排序成功应用（{len(enc_ids)} 首）")
            extra = ""
            if missing:
                extra = (f"\n\n⚠️ 有 {len(missing)} 首没能加回该歌单"
                         f"（可能是 VIP / 地区限制歌曲）。\n这些歌已不在歌单中，"
                         f"可以手动加回或在客户端检查。")
            elif note:
                extra = f"\n\n⚠️ {note}"
            QTimer.singleShot(0, lambda: QMessageBox.information(
                self, "成功", f"已成功将 {len(enc_ids)} 首歌曲排序到服务器！{extra}\n\n刷新歌单即可看到新顺序。"))
        else:
            msg = result.get("message", "未知错误")
            QTimer.singleShot(0, lambda: QMessageBox.warning(self, "排序失败", f"服务器返回错误：{msg}\n\ncode: {code}"))
            self.status_lbl.setText(f"排序失败：{msg}")

    def _do_update_ui_new_playlist(self, result, enc_ids, new_name):
        _log(f"[_do_update_ui_new_playlist] called, result={result}")
        self.apply_btn.setEnabled(True)
        if result is None:
            QTimer.singleShot(0, lambda: QMessageBox.warning(self, "错误", "创建歌单失败，请检查网络和登录状态"))
            self.status_lbl.setText("创建歌单失败")
            return
        code = result.get("code")
        if code == 200:
            new_pl_id = result.get("data", {}).get("id", "")
            track_count = result.get("data", {}).get("trackCount", len(enc_ids))
            self.status_lbl.setText(f"✅ 新歌单「{new_name}」创建成功（{track_count} 首）")
            QTimer.singleShot(0, lambda: QMessageBox.information(
                self, "成功",
                f"已在新歌单「{new_name}」中按正确顺序添加 {track_count} 首歌曲！\n\n"
                f"新歌单ID：{new_pl_id}\n\n"
                f"请在网易云音乐 App 或网页版查看。\n\n"
                f"提示：如果歌单未立即显示，尝试下拉刷新。"
            ))
        else:
            msg = result.get("message", "未知错误")
            QTimer.singleShot(0, lambda: QMessageBox.warning(self, "创建失败", f"服务器返回错误：{msg}\n\ncode: {code}"))
            self.status_lbl.setText(f"创建失败：{msg}")

    def export_playlist(self):
        rows = self.table.rowCount()
        if rows == 0:
            return
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

    def _show_search_dialog(self):
        dlg = SearchDialog(self.playlists, self)
        dlg.exec()
        if dlg.result_playlist_id:
            QTimer.singleShot(300, self.load_playlists)

    def _show_ai_sort_dialog(self):
        if not self.current_tracks:
            QMessageBox.information(self, "提示", "请先加载歌单")
            return
        dlg = AISortDialog(self.current_tracks, self)
        dlg.exec()
        if dlg.sorted_enc_ids:
            self._apply_ai_sort_result(dlg.sorted_enc_ids)

    def _apply_ai_sort_result(self, sorted_enc_ids):
        """应用 AI 排序结果到表格"""
        enc_to_tr = {tr.get("encId"): tr for tr in self.current_tracks if tr.get("encId")}
        ordered = [enc_to_tr[eid] for eid in sorted_enc_ids if eid in enc_to_tr]
        if ordered:
            self._sorted_tracks = ordered
            self._show_sorted_tracks(ordered)
            self.apply_btn.setEnabled(True)
            self.status_lbl.setText(f"AI 排序完成，共 {len(ordered)} 首")
        else:
            QMessageBox.warning(self, "提示", "排序结果无效")

