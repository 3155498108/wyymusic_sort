# Agent 手册：网易云歌单排序器

## 项目概述

网易云歌单排序器是一款基于 PyQt6 的桌面工具，用于对网易云音乐歌单进行多级排序。支持扫码登录、多级排序规则、批量获取歌曲信息、以及直接应用到服务器或复制到剪贴板导出。

## 架构

```
main.py                 # 入口（~13行），仅负责 QApplication 启动
├── constants.py        # 路径、锁等常量
├── logger.py           # 日志工具，写入 TEMP/ncm_sorter.log
├── ui/
│   ├── main_window.py  # MainWindow，主窗口所有逻辑（~550行）
│   └── login_dialog.py # LoginDialog，扫码登录弹窗
├── core/
│   └── ncm_client.py   # ncm-cli 封装（login/logout/check/tracks/reorder/playlists）
└── utils/
    ├── sort.py         # 排序算法（自定义顺序 + 多级排序）
    └── excel.py        # Excel 导入导出
```

### 模块职责

| 模块 | 职责 | 外部依赖 |
|------|------|---------|
| `main.py` | 入口，QApplication 创建，MainWindow 展示 | PyQt6 |
| `constants.py` | APP_DIR, BASE_DIR, album_lock, NODE, NCM_CLI | 无 |
| `logger.py` | `_log(msg)` 写日志到 TEMP | 无 |
| `ui/main_window.py` | 所有 UI 逻辑、信号处理、track 加载/排序/应用 | PyQt6, ncm_client, sort, excel |
| `ui/login_dialog.py` | 扫码登录弹窗，3秒轮询登录状态 | PyQt6, ncm_client |
| `core/ncm_client.py` | 调用系统 npm 全局安装的 ncm-cli | subprocess, json |
| `utils/sort.py` | `sort_by_custom_order`, `sort_multi_level`（含艺人+入库时间特殊分组） | re, collections |
| `utils/excel.py` | `export_table_to_excel`, `import_tracks_from_excel` | openpyxl |

## 工作流程

1. **启动** → MainWindow 初始化 → `_check_login()` 检查登录状态
2. **登录** → 未登录显示 LoginDialog（扫码 + 3秒轮询）
3. **加载歌单** → `load_playlists()` 调用 `ncm_get_playlists()`
4. **选择歌单** → `on_playlist_select()` 调用 `ncm_get_tracks()` 获取曲目，并发获取专辑发行时间
5. **排序** → `preview()` 调用 `sort_multi_level()` 或 `sort_by_custom_order()` 预览
6. **应用** → `apply_to_server()` 调用 `ncm_reorder()` 或 `copy_to_clipboard()`

## ncm-cli 调用约定

ncm-cli 需全局安装（`npm install -g ncm-cli`）。调用通过 `run_ncm` / `run_ncm_global`：

- `ncm_login()` → `run_ncm_global(["ncm", "login"])`
- `ncm_login_check()` → `run_ncm_global(["ncm", "login", "check"])`
- `ncm_logout()` → `run_ncm_global(["ncm", "logout"])`
- `ncm_get_tracks(enc_id)` → `run_ncm(["ncm", "tracks", enc_id])`
- `ncm_reorder(enc_id, track_ids)` → `run_ncm(["ncm", "reorder", enc_id, ...track_ids])`
- `ncm_get_playlists()` → `run_ncm_global(["ncm", "playlist", "list"])`

## 关键数据结构

```python
# MainWindow 状态
self.playlists = []                    # [{encId, name, ...}, ...]
self.current_pl_enc_id = None         # 当前歌单加密ID
self.server_track_ids = []            # 服务器当前加密ID列表
self.id_to_enc = {}                   # 数字ID → 加密ID
self.enc_to_info = {}                 # 加密ID → {name, artists, album, addTime}
self.current_tracks = []              # 当前有元数据的 tracks
self._sorted_tracks = None           # 预览排序结果
self._custom_order = None            # 自定义顺序列表
```

```python
# track 对象结构
{
    "id": 123456,          # 数字ID
    "encId": "xxxx",       # 加密ID（用于 reorder）
    "name": "歌曲名",
    "ar": [{"name": "艺人"}],    # 艺术家列表
    "al": {"name": "专辑", "publishTime": 0},  # 专辑（含发行时间）
    "_addTime": 1234567890  # 入库时间戳（额外附加）
}
```

## 打包

```bash
pyinstaller 网易云歌单排序器2.spec
```

输出目录：`dist/网易云歌单排序器2/`

## 测试文件说明

根目录下的 `test_*.py` 和 `*.py`（非上述 7 个模块）均为临时调试脚本，切勿在生产代码中使用。生产逻辑全部在上述 7 个模块中。