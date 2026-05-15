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
│   ├── login_dialog.py # LoginDialog，扫码登录弹窗
│   └── config_dialog.py # ConfigDialog，首次配置 AppID/PrivateKey 弹窗
├── core/
│   └── ncm_client.py   # ncm-cli 封装（login/logout/check/tracks/reorder/playlists/create/add）。小歌单（≤200首）用 ncm-cli reorder；大歌单（>200首）用 `ncm_create_and_fill_playlist` 新建歌单分批添加歌曲
└── utils/
    ├── sort.py         # 排序算法（自定义顺序 + 多级排序）
    └── excel.py        # Excel 导入导出
```

### 模块职责

| 模块 | 职责 | 外部依赖 |
|------|------|---------|
| `main.py` | 入口，QApplication 创建，MainWindow 展示 | PyQt6 |
| `constants.py` | APP_DIR, BASE_DIR, CONFIG_FILE, album_lock, NODE, NCM_CLI | 无 |
| `ui/config_dialog.py` | AppID/PrivateKey 配置弹窗，首次启动时检测是否已配置，未配置则弹出对话框 | PyQt6, constants |
| `logger.py` | `_log(msg)` 写日志到 TEMP | 无 |
| `ui/main_window.py` | 所有 UI 逻辑、信号处理、track 加载/排序/应用、多歌单歌手搜索 | PyQt6, ncm_client, sort, excel |
| `ui/login_dialog.py` | 扫码登录弹窗，3秒轮询登录状态 | PyQt6, ncm_client |
| `core/ncm_client.py` | 调用系统 npm 全局安装的 ncm-cli（优先使用打包内的 ncm-cli.exe，回退到系统 npm）。小歌单用 ncm-cli reorder；大歌单用 `ncm_create_and_fill_playlist` 新建歌单分批添加歌曲 | subprocess, json |
| `utils/sort.py` | `sort_by_custom_order`, `sort_multi_level`（含艺人+入库时间特殊分组） | re, collections |
| `utils/excel.py` | `export_table_to_excel`, `import_tracks_from_excel` | openpyxl |

## 已知问题与限制

1. **大歌单 reorder**：歌单超过200首时，ncm-cli `--trackIds` 命令行参数超限（~235 IDs 逗号分隔）。解决方案：大歌单用 `ncm_create_and_fill_playlist` 新建歌单分批添加歌曲，绕过命令行限制。
2. **凭据加密**：`credentials.enc.json` 使用机器相关密钥加密，无法直接读取。

## 工作流程

1. **启动** → MainWindow 初始化 → `_ensure_config()` 检查 AppID/PrivateKey 配置，未配置则弹出 ConfigDialog
2. **登录** → 未登录显示 LoginDialog（扫码 + 3秒轮询）
3. **加载歌单** → `load_playlists()` 调用 `ncm_get_playlists()`
4. **选择歌单** → `on_playlist_select()` 调用 `ncm_get_tracks()` 获取曲目，并发获取专辑发行时间
5. **排序** → `preview()` 调用 `sort_multi_level()` 或 `sort_by_custom_order()` 预览
6. **应用** → `apply_to_server()`
   - 小歌单（≤200首）：弹窗让用户选择「直接 reorder」或「新建歌单」
   - 大歌单（>200首）：直接用 `ncm_create_and_fill_playlist` 新建歌单分批添加歌曲
7. **多歌单歌手搜索** → `_show_search_artists_dialog()` → `SearchArtistsDialog`
   - 多选歌单 + 输入歌手名（每行一个，模糊匹配）
   - 遍历所有歌单的歌曲，匹配任一歌手就去重
   - 创建新歌单并分批添加歌曲

## ncm-cli 调用约定

ncm-cli 需全局安装（`npm install -g @music163/ncm-cli`）。调用通过 `run_ncm` / `run_ncm_global`：

- `ncm_login()` → `run_ncm_global(["login", "--background"])`
- `ncm_login_check()` → `run_ncm_global(["login", "--check", "--output", "json"])`
- `ncm_logout()` → `run_ncm_global(["logout"])`
- `ncm_get_tracks(enc_id)` → `run_ncm_global(["playlist", "tracks", "--playlistId", enc_id, "--limit", "500", "--offset", "0", "--output", "json"])`
- `ncm_reorder(enc_id, track_ids)` → 小歌单用 ncm-cli，大歌单用 `ncm_create_and_fill_playlist`
- `ncm_create_and_fill_playlist(name, track_ids)` → `playlist create` + `playlist add` 分批添加歌曲
- `ncm_get_playlists()` → `run_ncm_global(["playlist", "created", "--limit", "500", "--offset", "0", "--output", "json"])`
- `ncm_search_artists_in_playlists(playlist_enc_ids, artist_names, progress_callback)` → 遍历多个歌单匹配歌手，返回 (enc_ids列表, tracks列表)

## 关键发现（实践经验）

### 1. ncm-cli --trackIds 参数格式

`--trackIds` 接受的是**逗号分隔格式**，不是 JSON 数组格式：
```bash
# ✅ 正确（逗号分隔）
ncm-cli playlist reorder --playlistId <id> --trackIds 'id1,id2,id3'

# ❌ 错误（JSON 数组会增加额外字符 []" ，更容易触发长度限制）
ncm-cli playlist reorder --playlistId <id> --trackIds '["id1","id2","id3"]'
```

### 2. ncm-cli 命令行长度限制

实际阈值约 **235 个逗号分隔的 ID**（字符数约 7742），超过会报"网络好像有点问题"。  
JSON 数组格式因为更长的字符数，阈值更低（约 200）。

### 3. ncm-cli playlist add 的双重反转行为

`playlist add` 在内部对歌曲顺序做了**两层反转**：
1. **批次内部反转**：传入 `[A,B,C,D]`，实际添加到歌单的是 `[D,C,B,A]`
2. **批次顺序反转**：batch 0 先 add，最终会在歌单**最后面**；batch 1 后 add，最终会在歌单**最前面**

因此 `ncm_create_and_fill_playlist` 使用了双重修正：
- 倒序处理批次（batch 3 → batch 2 → batch 1 → batch 0）
- 每批内部也先反转再传入

### 4. 直接 API 方案失败原因

`POST /api/v3/playlist/track/update` 需要 MUSIC_U 和 __csrf cookie，但：
- `credentials.enc.json` 使用 Windows DPAPI 加密
- 打包后的 exe 调用 DPAPI 失败（Error code 13），无法解密获取 cookie
- 因此无法使用直接 API 方案作为备选

### 5. QMessageBox 在后台线程会冻结 UI

`apply_to_server` 在后台线程执行网络请求后，直接调用 `QMessageBox.warning/information` 会导致 UI 无响应。  
解决：用 `QTimer.singleShot(0, lambda: ...)` 将弹窗回调放回主线程。

## WeAPI 加密（未使用）

大歌单直接 API 调用原本计划使用 WeAPI 加密（见 `core/ncm_client.py` 的 `_ncm_reorder_direct`），但 DPAPI 解密失败，无法获取 cookie，现已改用新建歌单方案。

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
# 1. 用 pkg 将 ncm-cli 打包成独立 exe
cd "C:/Users/spenc/AppData/Roaming/npm/node_modules/@music163/ncm-cli"
npx pkg . -t node18-win-x64 -o e:/jsjzy/pyqt_app/dist/ncm-cli-bundle.exe

# 2. 删除旧目录并重新打包（onedir 模式）
rm -rf "e:/jsjzy/pyqt_app/dist/网易云歌单排序器2" "e:/jsjzy/pyqt_app/dist/网易云歌单排序器2.exe" "e:/jsjzy/pyqt_app/build"
cd e:/jsjzy/pyqt_app && pyinstaller 网易云歌单排序器2.spec

# 3. 手动复制 ncm-cli.exe 到输出目录
cp "e:/jsjzy/pyqt_app/dist/ncm-cli-bundle.exe" "e:/jsjzy/pyqt_app/dist/网易云歌单排序器2/ncm-cli.exe"
```

输出目录：`dist/网易云歌单排序器2/`

包含：网易云歌单排序器2.exe + ncm-cli.exe + _internal/

其他人下载后直接运行，无需安装 Node.js。

## 测试文件说明

根目录下的 `test_*.py` 和 `*.py`（非上述 7 个模块）均为临时调试脚本，切勿在生产代码中使用。生产逻辑全部在上述 7 个模块中。