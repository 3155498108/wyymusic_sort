# 网易云歌单排序器

基于 PyQt6 的网易云音乐歌单排序工具，支持多级排序、扫码登录、歌单管理、跨歌单搜索与 AI 排序。
界面模仿网易云音乐客户端的深色风格（主色 `#EC4141`）。

## 功能特性

- **扫码登录** - 二维码登录网易云音乐账号
- **多级排序** - 最多三层规则（艺人 / 专辑 / 歌曲名 / 入库时间 / 专辑发行时间 / 自定义顺序），每层可选升降序
- **跨歌单搜索** - 一次搜索多个歌单，按**歌手 / 专辑 / 歌曲名**模糊匹配，结果按专辑分组、可逐张勾选
- **全网搜专辑** - 按关键词搜索网易云专辑，收录整张专辑的歌曲到新歌单
- **AI 排序** - 用一句话描述排序要求（支持 OpenAI / Claude / 本地 Ollama），自动生成顺序
- **批量操作** - 并发获取歌曲信息，大歌单加载更快
- **本地 / 服务器** - 可复制排序结果，也可直接写回网易云歌单
- **Excel 导入导出** - 歌曲顺序导入导出为 xlsx
- **按需加载专辑发行时间** - 逐张专辑请求很慢，改成用到时才加载并落盘缓存

## 技术栈

- **GUI**: PyQt6
- **后端**: ncm-cli（网易云音乐 CLI 工具，打包时随包分发，无需 Node.js）
- **Excel**: openpyxl
- **AI**: openai / anthropic（可选）

## 项目结构

```
wyymusic_sort/
├── main.py                # 程序入口
├── constants.py           # 路径、常量
├── logger.py              # 日志工具
├── ui/
│   ├── main_window.py     # 主窗口（左侧栏 + 顶部搜索 + 曲目表）
│   ├── theme.py           # 网易云风格深色主题（配色 + QSS + 图标 + 深色标题栏）
│   ├── search_dialog.py   # 跨歌单搜索 / 全网搜专辑弹窗
│   ├── ai_sort_dialog.py  # AI 排序弹窗
│   ├── login_dialog.py    # 扫码登录弹窗
│   ├── config_dialog.py   # AppID/PrivateKey + AI 配置弹窗
│   └── ui_thread.py       # 后台线程回 GUI 线程的调度器
├── core/
│   ├── ncm_client.py      # ncm-cli 封装（登录/歌单/排序/专辑搜索）
│   └── ai_sorter.py       # AI 排序核心
└── utils/
    ├── sort.py            # 排序算法
    ├── match.py           # 关键词归一化与模糊匹配
    └── excel.py           # Excel 导入导出
```

## 首次使用

1. 运行程序
2. 首次启动会弹出配置窗口，填写 AppID 和 PrivateKey（也可点右上角「设置」随时修改）
3. 配置保存后，扫码登录网易云音乐账号

## 运行

```bash
pip install -r requirements.txt
python main.py
```

## 打包

```bash
pyinstaller 网易云歌单排序器2.spec
cp dist/ncm-cli-bundle.exe "dist/网易云歌单排序器2/ncm-cli.exe"
```

打包产物位于 `dist/网易云歌单排序器/`，包含 exe、ncm-cli.exe 与 _internal 运行时。
**下载后直接运行，无需安装 Node.js 或 Python。**

## 注意事项

- 歌单超过 200 首时 ncm-cli 命令行参数会超限，程序会自动改为「新建歌单 + 分批添加」
- 专辑发行时间只能逐张专辑请求，大歌单首次加载很慢，程序改为按需加载并缓存
- 大歌单建议只勾选需要的歌单，避免全量扫描
