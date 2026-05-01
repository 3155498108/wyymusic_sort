# 网易云歌单排序器

基于 PyQt6 的网易云音乐歌单排序工具，支持多级排序、扫码登录、歌单管理等功能。

## 功能特性

- **扫码登录** - 二维码登录网易云音乐账号
- **多级排序** - 支持按多个维度综合排序歌单（评分、发布时间、专辑热度等）
- **批量操作** - 支持并发获取歌曲信息，提高大数据量歌单处理速度
- **本地/服务器** - 可复制排序结果或直接应用到网易云音乐服务器
- **跨平台打包** - 支持 PyInstaller 打包为 Windows 可执行文件

## 技术栈

- **GUI**: PyQt6
- **后端 API**: ncm-cli (网易云音乐 CLI 工具)
- **加密**: pycryptodome
- **HTTP**: requests

## 项目结构

```
pyqt_app/
├── main.py              # 主程序入口
├── ncm-cli/             # ncm-cli 子模块 (Node.js)
├── dist/                # 构建输出目录
├── build/               # PyInstaller 构建目录
└── *.spec              # PyInstaller 配置文件
```

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行

```bash
python main.py
```

## 打包

使用 PyInstaller 打包为 Windows 可执行文件：

```bash
pyinstaller 网易云歌单排序器.spec
```

打包后的可执行文件位于 `dist/网易云歌单排序器/` 目录。

## 工作流程

1. 打开程序
2. 扫码登录（如需要）
3. 加载歌单
4. 设置多级排序规则
5. 执行排序，复制结果或直接应用到服务器