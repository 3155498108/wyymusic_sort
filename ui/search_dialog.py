"""多歌单搜索 / 全网搜专辑 → 新建歌单

两种模式：
1. 从我的歌单中筛选：跨歌单按 歌手 / 专辑 / 歌曲名 模糊匹配，去重后建歌单
2. 全网搜专辑：按关键词搜索网易云专辑，勾选专辑后取其全部歌曲建歌单

交互：先「搜索」出结果 → 结果表中勾选 / 取消相册 → 「创建歌单」。
"""
import datetime
import threading

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget,
)

from logger import _log
from ui.theme import apply_dark_title_bar
from ui.ui_thread import post
from core.ncm_client import (
    ncm_collect_album_tracks, ncm_create_and_fill_playlist,
    ncm_search_albums, ncm_search_tracks_in_playlists,
)
from utils.match import (
    FIELD_ALBUM, FIELD_ARTIST, FIELD_SONG, group_by_album, normalize,
    parse_keywords,
)

MODE_PLAYLIST = "playlist"
MODE_ALBUM = "album"

class SearchDialog(QDialog):
    """多歌单搜索（含搜专辑）/ 全网搜专辑 的统一弹窗"""

    def __init__(self, playlists, parent=None):
        super().__init__(parent)
        self.playlists = playlists or []
        self.result_playlist_id = None
        self._groups = []       # 模式一：按专辑分组的匹配结果
        self._albums = []       # 模式二：在线搜到的专辑
        self._busy = False
        self._build_ui()
        self._on_mode_changed()
        apply_dark_title_bar(self)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.setWindowTitle("搜索歌曲 / 专辑 并创建歌单")
        self.setMinimumSize(820, 700)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 模式
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("搜索方式："))
        self.mode_cb = QComboBox()
        self.mode_cb.addItem("从我的歌单中筛选（歌手 / 专辑 / 歌曲名）", MODE_PLAYLIST)
        self.mode_cb.addItem("全网搜索专辑（专辑名匹配，收录整张专辑）", MODE_ALBUM)
        self.mode_cb.setMinimumWidth(360)
        self.mode_cb.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_cb)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        # 关键词
        kw_box = QGroupBox("关键词（每行一个，包含即匹配；以 - 开头表示排除）")
        kw_layout = QVBoxLayout(kw_box)
        self.keyword_edit = QTextEdit()
        self.keyword_edit.setPlaceholderText("逆転裁判\n-オーケストラ")
        self.keyword_edit.setMaximumHeight(84)
        self.keyword_edit.setAcceptRichText(False)
        kw_layout.addWidget(self.keyword_edit)
        self.field_row = QWidget()
        fr = QHBoxLayout(self.field_row)
        fr.setContentsMargins(0, 0, 0, 0)
        fr.addWidget(QLabel("匹配字段："))
        self.cb_artist = QCheckBox("歌手")
        self.cb_album = QCheckBox("专辑")
        self.cb_song = QCheckBox("歌曲名")
        self.cb_artist.setChecked(True)
        self.cb_album.setChecked(True)
        self.cb_song.setChecked(False)
        for cb in (self.cb_artist, self.cb_album, self.cb_song):
            fr.addWidget(cb)
        fr.addStretch()
        kw_layout.addWidget(self.field_row)
        layout.addWidget(kw_box)

        # 歌单选择（仅模式一）
        self.playlist_box = QGroupBox("选择要搜索的歌单（可多选）")
        pl_layout = QVBoxLayout(self.playlist_box)
        pl_top = QHBoxLayout()
        self.pl_filter = QLineEdit()
        self.pl_filter.setPlaceholderText("过滤歌单名...")
        self.pl_filter.textChanged.connect(self._filter_playlists)
        pl_top.addWidget(self.pl_filter)
        btn_all = QPushButton("全选")
        btn_all.clicked.connect(lambda: self._set_playlists_checked(True))
        btn_none = QPushButton("清空")
        btn_none.clicked.connect(lambda: self._set_playlists_checked(False))
        pl_top.addWidget(btn_all)
        pl_top.addWidget(btn_none)
        pl_layout.addLayout(pl_top)

        self.pl_container = QWidget()
        self.pl_container_layout = QVBoxLayout(self.pl_container)
        self.pl_container_layout.setSpacing(2)
        self.pl_container_layout.setContentsMargins(4, 4, 4, 4)
        self.playlist_cbs = []
        for p in self.playlists:
            name = p.get("name", "?")
            count = p.get("trackCount", 0) or 0
            cb = QCheckBox(f"{name}  ({count}首)")
            self.playlist_cbs.append(cb)
            self.pl_container_layout.addWidget(cb)
        self.pl_container_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidget(self.pl_container)
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(130)
        pl_layout.addWidget(scroll)
        layout.addWidget(self.playlist_box)

        # 搜索行
        search_row = QHBoxLayout()
        self.search_btn = QPushButton("搜索")
        self.search_btn.setProperty("variant", "primary")
        self.search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_btn.clicked.connect(self._do_search)
        search_row.addWidget(self.search_btn)
        self.status_lbl = QLabel("输入关键词后点击搜索")
        self.status_lbl.setProperty("variant", "weak")
        search_row.addWidget(self.status_lbl, 1)
        layout.addLayout(search_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 结果表
        self.result_box = QGroupBox("搜索结果（取消勾选可排除）")
        res_layout = QVBoxLayout(self.result_box)
        res_top = QHBoxLayout()
        self.select_all_cb = QCheckBox("全选")
        self.select_all_cb.setChecked(True)
        self.select_all_cb.stateChanged.connect(self._on_select_all_changed)
        res_top.addWidget(self.select_all_cb)
        self.count_lbl = QLabel("")
        self.count_lbl.setProperty("variant", "weak")
        res_top.addWidget(self.count_lbl, 1)
        res_layout.addLayout(res_top)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["选择", "专辑", "艺人", "数量"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.horizontalHeader().setFixedHeight(34)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemChanged.connect(self._on_item_changed)
        res_layout.addWidget(self.table)
        self.result_box.setEnabled(False)
        layout.addWidget(self.result_box, 1)

        # 底部
        bottom = QHBoxLayout()
        bottom.addWidget(QLabel("新歌单名称："))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：逆転裁判 精选")
        bottom.addWidget(self.name_edit, 1)
        self.cancel_btn = QPushButton("关闭")
        self.cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(self.cancel_btn)
        self.create_btn = QPushButton("创建歌单")
        self.create_btn.setProperty("variant", "primary")
        self.create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.create_btn.clicked.connect(self._do_create)
        self.create_btn.setEnabled(False)
        bottom.addWidget(self.create_btn)
        layout.addLayout(bottom)

    # ------------------------------------------------------------- 模式切换
    def _current_mode(self) -> str:
        return self.mode_cb.currentData() or MODE_PLAYLIST

    def _on_mode_changed(self, *args):
        is_playlist_mode = self._current_mode() == MODE_PLAYLIST
        self.playlist_box.setVisible(is_playlist_mode)
        self.field_row.setVisible(is_playlist_mode)
        if is_playlist_mode:
            self.keyword_edit.setPlaceholderText("逆転裁判\n-オーケストラ")
        else:
            self.keyword_edit.setPlaceholderText("逆転裁判\n（专辑名包含关键词的整张专辑都会被收录）")
        self._clear_results()

    def _clear_results(self):
        self._groups = []
        self._albums = []
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.table.blockSignals(False)
        self.result_box.setEnabled(False)
        self.create_btn.setEnabled(False)
        self.count_lbl.setText("")

    # ------------------------------------------------------------- 歌单操作
    def _visible_playlist_cbs(self):
        return [cb for cb in self.playlist_cbs if cb.isVisible()]

    def _set_playlists_checked(self, checked: bool):
        for cb in self._visible_playlist_cbs():
            cb.setChecked(checked)

    def _filter_playlists(self, text: str):
        key = normalize(text)
        for cb in self.playlist_cbs:
            cb.setVisible(key in normalize(cb.text()) if key else True)

    # ----------------------------------------------------------------- 搜索
    def _read_conditions(self):
        raw = self.keyword_edit.toPlainText()

        # 模式二只需要一个搜索入口关键词；用第一个包含关键词搜索
        include, exclude = parse_keywords(raw)
        return raw, include, exclude

    def _do_search(self):
        if self._busy:
            return
        raw, include, exclude = self._read_conditions()
        if not include:
            QMessageBox.warning(self, "提示", "请输入至少一个关键词")
            return

        mode = self._current_mode()
        selected = []
        if mode == MODE_PLAYLIST:
            selected = [self.playlists[i] for i, cb in enumerate(self.playlist_cbs)
                        if cb.isChecked() and i < len(self.playlists)]
            if not selected:
                QMessageBox.warning(self, "提示", "请至少选择一个歌单")
                return
            fields = []
            if self.cb_artist.isChecked():
                fields.append(FIELD_ARTIST)
            if self.cb_album.isChecked():
                fields.append(FIELD_ALBUM)
            if self.cb_song.isChecked():
                fields.append(FIELD_SONG)
            if not fields:
                QMessageBox.warning(self, "提示", "请至少勾选一个匹配字段")
                return

        self._clear_results()
        self._set_busy(True, "正在搜索...")
        if not self.name_edit.text().strip():
            self.name_edit.setText(f"{raw.strip().splitlines()[0].lstrip('-!')} 合集")

        if mode == MODE_PLAYLIST:
            param = {
                "playlist_ids": [p.get("id", "") for p in selected],
                "keywords": include,
                "exclude": exclude,
                "fields": fields,
            }
            threading.Thread(target=self._bg_search_playlists, args=(param,), daemon=True).start()
        else:
            threading.Thread(target=self._bg_search_albums,
                             args=(include, exclude), daemon=True).start()

    def _bg_search_playlists(self, param):
        try:
            _, tracks = ncm_search_tracks_in_playlists(
                param["playlist_ids"], param["keywords"], param["fields"],
                exclude_keywords=param["exclude"],
                progress_callback=self._progress,
            )
            groups = group_by_album(tracks)
        except Exception as e:
            _log(f"[SearchDialog] playlist search failed: {e}")
            self._ui(self._search_failed, str(e))
            return
        self._ui(self._search_done_groups, groups)

    def _bg_search_albums(self, include, exclude):
        try:
            merged: dict[str, dict] = {}
            for kw in include:
                for album in ncm_search_albums(kw, limit=100):
                    aid = album.get("id")
                    if aid and aid not in merged:
                        merged[aid] = album
            albums = []
            for album in merged.values():
                name = normalize(album.get("name", ""))
                names = [name, normalize(album.get("aliaName", ""))]
                artists = " / ".join(a.get("name", "") for a in (album.get("artists") or []))
                artists = normalize(artists)
                texts = [t for t in names + [artists] if t]
                if not any(k in t for k in include for t in texts):
                    continue
                if exclude and any(x in t for x in exclude for t in texts):
                    continue
                albums.append(album)
        except Exception as e:
            _log(f"[SearchDialog] album search failed: {e}")
            self._ui(self._search_failed, str(e))
            return
        self._ui(self._search_done_albums, albums)

    # ------------------------------------------------------------- 结果渲染
    def _search_failed(self, msg: str):
        self._set_busy(False, "搜索失败")
        QMessageBox.warning(self, "错误", f"搜索失败：{msg}")

    def _search_done_groups(self, groups):
        self._set_busy(False, "")
        self._groups = groups
        total_tracks = sum(len(g["tracks"]) for g in groups)
        if not groups:
            self.status_lbl.setText("没有匹配到歌曲，试试减少关键词或更换匹配字段")
            return
        self.table.setHorizontalHeaderLabels(["选择", "专辑", "艺人", "歌曲数"])
        self.table.blockSignals(True)
        self.table.setRowCount(len(groups))
        for row, group in enumerate(groups):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            check.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(row, 0, check)
            self.table.setItem(row, 1, QTableWidgetItem(group["name"]))
            self.table.setItem(row, 2, QTableWidgetItem(group["artists"]))
            count_item = QTableWidgetItem(str(len(group["tracks"])))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, count_item)
        self.table.blockSignals(False)
        self.result_box.setEnabled(True)
        self.create_btn.setEnabled(True)
        self.count_lbl.setText(f"匹配 {total_tracks} 首，来自 {len(groups)} 张专辑")
        self.status_lbl.setText(f"匹配 {total_tracks} 首歌曲，勾选要收录的专辑后创建歌单")

    def _search_done_albums(self, albums):
        self._set_busy(False, "")
        self._albums = albums
        if not albums:
            self.status_lbl.setText("没有搜到匹配的专辑，换个关键词试试")
            return
        self.table.setHorizontalHeaderLabels(["选择", "专辑", "艺人", "发行年份"])
        self.table.blockSignals(True)
        self.table.setRowCount(len(albums))
        for row, album in enumerate(albums):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            check.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(row, 0, check)
            self.table.setItem(row, 1, QTableWidgetItem(album.get("name", "")))
            artists = " / ".join(a.get("name", "") for a in (album.get("artists") or []))
            self.table.setItem(row, 2, QTableWidgetItem(artists))
            pt = album.get("publishTime") or 0
            year = "-"
            if pt:
                year = datetime.datetime.fromtimestamp(pt / 1000).strftime("%Y")
            year_item = QTableWidgetItem(year)
            year_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, year_item)
        self.table.blockSignals(False)
        self.result_box.setEnabled(True)
        self.create_btn.setEnabled(True)
        self.count_lbl.setText(f"搜到 {len(albums)} 张专辑（勾选后取其全部歌曲）")
        self.status_lbl.setText(f"搜到 {len(albums)} 张专辑，确认勾选后创建歌单")

    def _on_item_changed(self, item):
        if item.column() != 0:
            return
        self._update_count_label()

    def _on_select_all_changed(self, state):
        checked = (state == Qt.CheckState.Checked.value)
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            it = self.table.item(row, 0)
            if it:
                it.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self._update_count_label()

    def _checked_rows(self) -> list[int]:
        rows = []
        for row in range(self.table.rowCount()):
            it = self.table.item(row, 0)
            if it and it.checkState() == Qt.CheckState.Checked:
                rows.append(row)
        return rows

    def _update_count_label(self):
        rows = self._checked_rows()
        if self._current_mode() == MODE_PLAYLIST:
            total = sum(len(self._groups[r]["tracks"]) for r in rows if r < len(self._groups))
            self.count_lbl.setText(f"已勾选 {len(rows)} 张专辑 / {total} 首歌曲")
        else:
            self.count_lbl.setText(f"已勾选 {len(rows)} 张专辑")

    # ----------------------------------------------------------------- 创建
    def _do_create(self):
        if self._busy:
            return
        rows = self._checked_rows()
        if not rows:
            QMessageBox.warning(self, "提示", "请至少勾选一张专辑")
            return
        new_name = self.name_edit.text().strip()
        if not new_name:
            QMessageBox.warning(self, "提示", "请输入新歌单名称")
            return

        mode = self._current_mode()
        if mode == MODE_PLAYLIST:
            seen: set[str] = set()
            enc_ids = []
            for r in rows:
                if r >= len(self._groups):
                    continue
                for tr in self._groups[r]["tracks"]:
                    enc = tr.get("id") or tr.get("encId")
                    if enc and enc not in seen:
                        seen.add(enc)
                        enc_ids.append(enc)
            if not enc_ids:
                QMessageBox.warning(self, "提示", "没有可收录的歌曲")
                return
            self._start_create(new_name, enc_ids)
        else:
            albums = [self._albums[r] for r in rows if r < len(self._albums)]
            self._set_busy(True, "正在获取专辑歌曲...")
            self.progress_bar.setVisible(True)
            self.progress_bar.setMaximum(0)
            threading.Thread(target=self._bg_collect_albums,
                             args=(albums, new_name), daemon=True).start()

    def _bg_collect_albums(self, albums, new_name):
        try:
            enc_ids, _ = ncm_collect_album_tracks(albums, progress_callback=self._progress)
        except Exception as e:
            _log(f"[SearchDialog] collect albums failed: {e}")
            self._ui(self._search_failed, str(e))
            return
        if not enc_ids:
            self._ui(self._search_failed, "专辑里没有可收录的歌曲")
            return
        self._ui(lambda: self._start_create(new_name, enc_ids, already_busy=True))

    def _start_create(self, new_name: str, enc_ids: list[str], already_busy: bool = False):
        if not already_busy:
            self._set_busy(True, f"正在创建歌单（{len(enc_ids)} 首）...")
        else:
            self.status_lbl.setText(f"正在创建歌单（{len(enc_ids)} 首）...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(0)
        threading.Thread(target=self._bg_create, args=(new_name, enc_ids), daemon=True).start()

    def _bg_create(self, new_name, enc_ids):
        try:
            result = ncm_create_and_fill_playlist(
                new_name, enc_ids,
                progress_callback=lambda cur, total, msg: self._ui(self.status_lbl.setText, msg),
            )
        except Exception as e:
            _log(f"[SearchDialog] create failed: {e}")
            self._ui(self._create_failed, str(e))
            return
        self._ui(self._create_done, result, new_name, enc_ids)

    def _create_done(self, result, new_name, enc_ids):
        self._set_busy(False, "")
        if result and result.get("code") == 200:
            self.result_playlist_id = result.get("data", {}).get("id", "")
            count = result.get("data", {}).get("trackCount", len(enc_ids))
            self.status_lbl.setText(f"✅ 歌单「{new_name}」创建成功，共 {count} 首")
            QMessageBox.information(
                self, "完成",
                f"已创建歌单「{new_name}」，共 {count} 首歌曲。\n\n"
                f"歌单ID：{self.result_playlist_id}\n\n"
                f"如果客户端未立即显示，下拉刷新一下。",
            )
            self.create_btn.setText("已完成")
            self.create_btn.setEnabled(False)

    def _create_failed(self, msg: str):
        self._set_busy(False, "创建失败")
        QMessageBox.warning(self, "错误", f"创建歌单失败：{msg}")

    # ------------------------------------------------------------- 线程/UI桥
    def _ui(self, func, *args):
        """把 UI 更新调度回主线程"""
        post(func, *args)

    def _progress(self, cur, total, msg):
        def _update():
            if total and total > 0:
                self.progress_bar.setVisible(True)
                self.progress_bar.setMaximum(total)
                self.progress_bar.setValue(cur)
            else:
                self.progress_bar.setVisible(True)
                self.progress_bar.setMaximum(0)
            if msg:
                self.status_lbl.setText(msg)
        post(_update)

    def _set_busy(self, busy: bool, msg: str = ""):
        self._busy = busy
        self.search_btn.setEnabled(not busy)
        self.mode_cb.setEnabled(not busy)
        self.keyword_edit.setReadOnly(busy)
        self.name_edit.setReadOnly(busy)
        if busy:
            self.create_btn.setEnabled(False)
            self.progress_bar.setVisible(True)
        else:
            self.progress_bar.setVisible(False)
            self.create_btn.setEnabled(self.table.rowCount() > 0)
        if msg:
            self.status_lbl.setText(msg)
