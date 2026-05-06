"""日志工具"""
import time


def _log(msg):
    """写调试日志到固定路径"""
    try:
        with open(r"C:\Users\spenc\AppData\Local\Temp\ncm_sorter.log", "a", encoding="utf-8", errors="replace") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass
