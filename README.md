# 网易云歌单排序器

基于 PyQt6 的网易云音乐歌单排序工具，支持多级排序、扫码登录、歌单管理等功能。

## 功能特性

- **扫码登录** - 二维码登录网易云音乐账号
- **多级排序** - 支持自定义顺序和多级排序规则（艺人、入库时间等）
- **批量操作** - 支持并发获取歌曲信息，提高大数据量歌单处理速度
- **本地/服务器** - 可复制排序结果或直接应用到网易云音乐服务器
- **多歌单歌手搜索** - 跨多个歌单搜索特定艺人的歌曲
- **Excel 导入导出** - 支持 Excel 文件导入导出歌曲列表

## 技术栈

- **GUI**: PyQt6
- **后端**: ncm-cli (网易云音乐 CLI 工具)
- **加密**: pycryptodome
- **Excel**: openpyxl

## 项目结构

```
wyymusic_sort/
├── main.py              # 程序入口
├── constants.py         # 路径、锁等常量
├── logger.py            # 日志工具
├── ui/
│   ├── main_window.py  # 主窗口
│   ├── login_dialog.py # 扫码登录弹窗
│   └── config_dialog.py # AppID/PrivateKey 配置弹窗
├── core/
│   └── ncm_client.py   # ncm-cli 封装
├── utils/
│   ├── sort.py         # 排序算法
│   └── excel.py        # Excel 导入导出
├── ncm-cli/            # ncm-cli 子模块 (Node.js)
└── dist/               # 构建输出目录
```

## 首次使用

1. 运行程序
2. 首次启动会弹出配置窗口，填写 AppID 和 PrivateKey
3. 配置保存后，扫码登录网易云音乐账号

## 运行

```bash
python main.py
```

## 打包

使用 PyInstaller 打包为 Windows 可执行文件：

```bash
pyinstaller 网易云歌单排序器.spec
```

打包后的可执行文件位于 `dist/网易云歌单排序器/` 目录，包含：
- 网易云歌单排序器.exe
- ncm-cli.exe
- _internal/ (Python 运行时和依赖)

**下载后直接运行，无需安装 Node.js 或 Python。**

## 工作流程

1. 打开程序（如未配置 AppID/PrivateKey，先填写）
2. 扫码登录网易云音乐账号
3. 加载歌单
4. 选择要排序的歌单
5. 设置排序规则（自定义顺序或多级排序）
6. 预览排序结果
7. 应用到服务器或复制到剪贴板

## 大歌单处理

歌单超过 200 首时，ncm-cli 命令行参数会超限。解决方案：
- 自动新建歌单分批添加歌曲，绕过命令行限制
- 支持跨歌单歌手搜索，自动创建新歌单
