"""常量定义"""
import os
import sys
import threading

# 全局锁（用于序列化 ncm-cli album get 调用，避免并发 token 冲突）
album_lock = threading.Lock()

# 路径（兼容 PyInstaller 打包）
APP_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))


def _base_dir():
    """返回 exe 所在目录"""
    return os.path.dirname(sys.executable)


BASE_DIR = _base_dir()
NODE = os.path.join(BASE_DIR, "node", "node.exe")
NCM_CLI = os.path.join(BASE_DIR, "ncm-cli", "dist", "index.js")
SYSTEM_NODE = r"C:\Program Files\nodejs\node.exe"
GLOBAL_NCM_CLI = os.path.join(
    os.path.expanduser("~"), "AppData", "Roaming", "npm",
    "node_modules", "@music163", "ncm-cli", "dist", "index.js"
)
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
LOCAL_NCM_CLI = os.path.join(BASE_DIR, "ncm-cli", "dist", "index.js")
