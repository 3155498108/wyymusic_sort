# Agent 手册：网易云歌单排序器

## 项目概述

网易云歌单排序器是一款基于 PyQt6 的桌面工具，用于对网易云音乐歌单进行多级排序。支持扫码登录、多级排序规则、批量获取歌曲信息、以及直接应用到服务器或复制到剪贴板导出。

## 架构

```
main.py                 # 入口（~16行），QApplication 启动 + 初始化跨线程调度器
├── constants.py        # 路径、锁等常量
├── logger.py           # 日志工具，写入 TEMP/ncm_sorter.log
├── ui/
│   ├── main_window.py  # MainWindow，主窗口逻辑
│   ├── login_dialog.py # LoginDialog，扫码登录弹窗
│   ├── config_dialog.py # ConfigDialog，AppID/PrivateKey + AI 配置弹窗
│   ├── search_dialog.py # SearchDialog，多歌单筛选 / 全网搜专辑 → 新建歌单
│   ├── ai_sort_dialog.py # AISortDialog，AI 智能排序弹窗
│   └── ui_thread.py    # post()：把后台线程回调安全送回 GUI 线程
├── core/
│   ├── ncm_client.py   # ncm-cli 封装（login/tracks/reorder/playlists/album 搜索）
│   └── ai_sorter.py    # AI 排序核心（OpenAI / Claude / Ollama）
└── utils/
    ├── sort.py         # 排序算法（自定义顺序 + 多级排序）
    ├── match.py        # 关键词归一化与歌手/专辑/歌名模糊匹配
    └── excel.py        # Excel 导入导出
```

### 模块职责

| 模块 | 职责 | 外部依赖 |
|------|------|---------|
| `main.py` | 入口，QApplication 创建，`ui_thread.init()`，MainWindow 展示 | PyQt6 |
| `constants.py` | APP_DIR, BASE_DIR, CONFIG_FILE, album_lock, NODE, NCM_CLI | 无 |
| `ui/config_dialog.py` | AppID/PrivateKey + AI 配置弹窗，首次启动时检测配置，未配置则弹出对话框 | PyQt6, constants |
| `ui/ai_sort_dialog.py` | AI 智能排序弹窗，用户输入排序要求，调用 AI 自动排序 | PyQt6, ai_sorter |
| `ui/search_dialog.py` | 统一搜索弹窗：① 跨歌单按歌手/专辑/歌名筛选 ② 全网搜专辑收整张；先预览勾选再建歌单 | PyQt6, ncm_client, match |
| `ui/ui_thread.py` | `post(func, *args)` 通过信号把回调排队到 GUI 线程（工作线程里 QTimer 不可用） | PyQt6 |
| `logger.py` | `_log(msg)` 写日志到 TEMP | 无 |
| `ui/main_window.py` | 主窗口逻辑、track 加载/排序/应用、按需加载发行时间、AI 排序入口 | PyQt6, ncm_client, sort, excel |
| `ui/login_dialog.py` | 扫码登录弹窗，3秒轮询登录状态 | PyQt6, ncm_client |
| `core/ncm_client.py` | 调用系统 npm 全局安装的 ncm-cli（优先使用打包内的 ncm-cli.exe，回退到系统 npm）。小歌单用 ncm-cli reorder；大歌单用 `ncm_create_and_fill_playlist` 新建歌单分批添加歌曲 | subprocess, json |
| `core/ai_sorter.py` | AI 排序核心，支持 OpenAI / Anthropic Claude / 本地 Ollama | openai, anthropic, requests |
| `utils/sort.py` | `sort_by_custom_order`, `sort_multi_level`（含艺人+入库时间特殊分组） | re, collections |
| `utils/match.py` | `normalize`, `parse_keywords`（支持 - 排除）, `track_matches`, `group_by_album` | re, unicodedata |
| `utils/excel.py` | `export_table_to_excel`, `import_tracks_from_excel` | openpyxl |

## 已知问题与限制

1. **大歌单 reorder**：歌单超过200首时，ncm-cli `--trackIds` 命令行参数超限（~235 IDs 逗号分隔）。解决方案：大歌单用 `ncm_create_and_fill_playlist` 新建歌单分批添加歌曲，绕过命令行限制。
2. **凭据加密**：`credentials.enc.json` 使用机器相关密钥加密，无法直接读取。
3. **专辑发行时间**：ncm-cli 没有批量接口，只能逐张专辑 `album get`。大歌单（如 4000 首/3500 张专辑）首次加载需要十几分钟，所以默认**不在加载歌单时拉取**，改为排序用到「专辑发行时间」时按需加载，并落盘缓存（`TEMP/ncm_album_publish_cache.json`，发行时间不会变）。

## 工作流程

1. **启动** → MainWindow 初始化 → `_ensure_config()` 检查 AppID/PrivateKey 配置，未配置则弹出 ConfigDialog
2. **登录** → 未登录显示 LoginDialog（扫码 + 3秒轮询）
3. **加载歌单** → `load_playlists()` 调用 `ncm_get_playlists()`
4. **选择歌单** → `on_playlist_select()` 调用 `ncm_get_tracks()` 获取曲目；仅当勾选「加载发行时间」时才补 publishTime
5. **排序** → `preview()` 调用 `sort_multi_level()` 或 `sort_by_custom_order()` 预览
   - 若排序层级里有「专辑发行时间」且数据缺失 → `_ensure_publish_time()` 询问后按需加载，加载完自动重新预览
6. **应用** → `apply_to_server()`
   - 小歌单（≤200首）：弹窗让用户选择「直接 reorder」或「新建歌单」
   - 大歌单（>200首）：直接用 `ncm_create_and_fill_playlist` 新建歌单分批添加歌曲
7. **搜索歌曲 / 专辑** → `_show_search_dialog()` → `SearchDialog`，两种模式：
   - **从我的歌单中筛选**：多选歌单 + 关键词（每行一个，`-` 开头为排除）+ 匹配字段（歌手/专辑/歌曲名）
     → `ncm_search_tracks_in_playlists()` 每个歌单只抓一次 → 按专辑分组展示，可取消勾选某些专辑 → 建歌单
   - **全网搜索专辑**：关键词 → `ncm_search_albums()` → 专辑列表（可勾选）→ `ncm_collect_album_tracks()` 拉整张专辑歌曲 → 建歌单
8. **AI 智能排序** → `_show_ai_sort_dialog()` → `AISortDialog`
   - 用户描述排序要求（如"周杰伦的歌放前面，其余按入库时间排序"）
   - 调用 OpenAI / Claude / Ollama 自动生成排序
   - 排序结果直接应用到表格，支持「直接应用到服务器」

## AI 排序配置

`config.json` 中的 AI 配置：
```json
{
  "ai_provider": "openai|anthropic|local",
  "ai_api_key": "your-api-key",
  "ai_model": "gpt-4o-mini"
}
```

支持的 AI 提供商：
- **OpenAI**：使用 `openai` 包，需要 API Key
- **Anthropic Claude**：使用 `anthropic` 包，需要 API Key
- **本地模型 (Ollama)**：`ai_api_key` 填写 Ollama 地址（如 `http://localhost:11434`）

## ncm-cli 调用约定

ncm-cli 需全局安装（`npm install -g @music163/ncm-cli`）。调用通过 `run_ncm` / `run_ncm_global`：

- `ncm_login()` → `run_ncm_global(["login", "--background"])`
- `ncm_login_check()` → `run_ncm_global(["login", "--check", "--output", "json"])`
- `ncm_logout()` → `run_ncm_global(["logout"])`
- `ncm_get_tracks(enc_id)` → `run_ncm_global(["playlist", "tracks", "--playlistId", enc_id, "--limit", "500", "--offset", "0", "--output", "json"])`
- `ncm_reorder(enc_id, track_ids)` → 小歌单用 ncm-cli，大歌单用 `ncm_create_and_fill_playlist`
- `ncm_create_and_fill_playlist(name, track_ids)` → `playlist create` + `playlist add` 分批添加歌曲
- `ncm_get_playlists()` → `run_ncm_global(["playlist", "created", "--limit", "500", "--offset", "0", "--output", "json"])`
- `ncm_search_tracks_in_playlists(playlist_enc_ids, keywords, fields, exclude_keywords, progress_callback)` → 跨歌单按字段筛选，单次抓取，返回 (enc_ids, tracks)
- `ncm_fill_publish_time(tracks, progress_callback)` → 补齐专辑发行时间（走缓存，返回新请求的专辑数）
- `ncm_search_albums(keyword, limit)` → `run_ncm_global(["search", "album", "--keyword", kw, "--limit", str(limit), "--output", "json"])`，返回 `data.records`
- `ncm_get_album_tracks(album_enc_id)` → `run_ncm_global(["album", "tracks", "--albumId", id, "--output", "json"])`，返回整张专辑歌曲
- `ncm_collect_album_tracks(albums, progress_callback)` → 多专辑并发拉取 + 按专辑顺序去重合并
- `ncm_search_artists_in_playlists(...)` → 兼容旧接口，内部转调 `ncm_search_tracks_in_playlists(fields=("artist",))`

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

### 5. 后台线程更新 UI：必须用 `ui_thread.post`，不能用 `QTimer.singleShot`

工作线程里 `QTimer.singleShot(0, cb)` **不会触发**（该线程没有事件循环），旧代码用它"回主线程"会导致：
加载完成后表格一直空白、进度条不动、弹窗不出现。

正确做法：`from ui.ui_thread import post; post(self._show_tracks, tracks)`——内部用 `pyqtSignal` 排队到 GUI 线程。
调度器必须在 GUI 线程创建（`main.py` 里 `ui_thread.init()`，或首次 `post` 时自动 `moveToThread` 到主线程）。

### 6. 专辑发行时间要按需 + 缓存

- ncm-cli 没有批量专辑接口，只能逐张 `album get`；4000 首歌 ≈ 3500 张专辑，串行请求要十几分钟。
- 现在 `ncm_get_tracks(load_publish_time=False)` 是默认路径；排序用到「专辑发行时间」时才 `_ensure_publish_time()` 询问并按需加载。
- 结果写入 `TEMP/ncm_album_publish_cache.json`（专辑发行时间不会变），二次加载几乎零请求。

### 7. 关键词匹配的归一化

`utils/match.py` 先 NFKC（全角→半角）+ casefold + **去掉所有空白** 再做包含匹配，
所以「逆転裁判 4」≈「逆転裁判4」、「OST（限定）」≈「ost(限定)」，中日文混排也能匹配。
以 `-` / `!` 开头的行为排除关键词（例如 `逆転裁判` + `-オーケストラ`）。

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

根目录下的 `test_*.py` 和临时脚本均为调试用，切勿在生产代码中使用。生产逻辑全部在上述模块中（`main.py` + `ui/` + `core/` + `utils/`）。