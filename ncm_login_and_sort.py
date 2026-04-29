"""
ncm-cli 登录 + 歌单排序
Python 调用 ncm-cli 做登录，从加密文件里读 cookie，
然后用 cookie 调网易云音乐 API 完成歌单读取和排序
"""
import subprocess
import json
import os
import sys
import time
import base64
import re

# ===== 路径配置 =====
NODE = r"C:\Program Files\nodejs\node.exe"
NCM = r"C:\Users\spenc\AppData\Roaming\npm\node_modules\@music163\ncm-cli\dist\index.js"
CONFIG_DIR = r"C:\Users\spenc\.config\ncm-cli"
CRED_FILE = os.path.join(CONFIG_DIR, "credentials.enc.json")
TOKEN_FILE = os.path.join(CONFIG_DIR, "tokens.enc.json")
BG_LOG = os.path.join(CONFIG_DIR, "bg-worker.log")


def run_ncm(args, timeout=15):
    env = {**os.environ, "USERPROFILE": "C:\\Users\\spenc", "HOME": "C:\\Users\\spenc"}
    r = subprocess.run([NODE, NCM] + args, capture_output=True, timeout=timeout, env=env)
    return r.returncode, r.stdout.decode("utf-8", errors="replace"), r.stderr.decode("utf-8", errors="replace")


def get_qr_url():
    """启动 ncm-cli login --background，返回二维码 URL"""
    rc, out, err = run_ncm(["login", "--background", "--output", "json"])
    if rc == 0 and out.strip():
        try:
            data = json.loads(out)
            if data.get("success"):
                return data.get("qrCodeUrl", "")
        except:
            pass
    return None


def check_bg_log():
    """读 bg-worker.log 最新行，检查是否登录成功"""
    if not os.path.exists(BG_LOG):
        return False
    try:
        with open(BG_LOG, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        if lines:
            last = lines[-1].strip()
            print(f"[LOG] {last}")
            return "登录成功" in last or "login successful" in last.lower()
    except:
        pass
    return False


def try_decrypt_creds():
    """
    尝试解密 credentials.enc.json
    ncm-cli 用 Node.js crypto (AES-256-CBC) 加密，key 来自机器信息
    先试试常见推导key，如果失败再想办法
    """
    if not os.path.exists(CRED_FILE):
        return None, "credentials.enc.json 不存在"

    try:
        with open(CRED_FILE, "r", encoding="utf-8") as f:
            cred_data = json.load(f)
    except Exception as e:
        return None, f"读文件失败: {e}"

    iv_b64 = cred_data.get("iv", "")
    data_b64 = cred_data.get("data", "")
    if not iv_b64 or not data_b64:
        return None, "iv 或 data 为空"

    try:
        iv = base64.b64decode(iv_b64)
        encrypted = base64.b64decode(data_b64)
    except Exception as e:
        return None, f"base64 解码失败: {e}"

    # 试试能不能用 pycryptodome 解密
    # ncm-cli 的加密key通常基于机器信息，我们先尝试几种常见组合
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad

        # 尝试用空密钥或默认密钥解密（不太可能成功，但试试）
        for pwd in [b"", b"ncm-cli", b"password", b"secret"]:
            try:
                key = pwd.ljust(32, b'\0')[:32]
                cipher = AES.new(key, AES.MODE_CBC, iv)
                decrypted = unpad(cipher.decrypt(encrypted), AES.block_size)
                result = decrypted.decode("utf-8", errors="replace")
                if "cookie" in result or "token" in result or "access" in result:
                    print(f"[解密成功] 密钥: {pwd}")
                    return json.loads(result), None
            except:
                continue
        return None, "所有已知密钥都解密失败，尝试其他方式"
    except ImportError:
        return None, "pycryptodome 未安装，请 pip install pycryptodome"


def get_login_status():
    """通过 ncm-cli login --check 检查登录状态"""
    rc, out, err = run_ncm(["login", "--check", "--output", "json"])
    if rc == 0 and out.strip():
        try:
            return json.loads(out)
        except:
            pass
    return {"success": False, "message": "检查失败"}


def get_playlists():
    """
    通过 ncm-cli config 获取 appId 和 privateKey，
    然后用这些凭证调开放平台 API 获取歌单
    """
    rc, out, err = run_ncm(["config", "list", "--output", "json"])
    if rc == 0 and out.strip():
        try:
            config = json.loads(out)
            app_id = config.get("appId", "b3010d0000000000877a84a1e79acb4b")
            return app_id, None
        except:
            pass
    return None, "获取配置失败"


def call_music_api_cookieless(app_id, playlist_id):
    """
    不带登录cookie调用歌单API（试探哪些接口可匿名访问）
    用于验证哪些接口真的不需要签名和登录
    """
    import requests

    # 这些是已知的网易云音乐 web API，部分可能不需要登录
    test_urls = [
        f"https://music.163.com/api/v3/playlist/detail?id={playlist_id}&n=1000000",
        f"https://music.163.com/api/playlist/detail?id={playlist_id}",
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://music.163.com/",
    }

    results = []
    for url in test_urls:
        try:
            r = requests.get(url, headers=headers, timeout=10)
            results.append({"url": url, "code": r.status_code, "body": r.text[:200]})
        except Exception as e:
            results.append({"url": url, "error": str(e)})

    return results


def main():
    print("=== 1. 检查 ncm-cli 登录状态 ===")
    status = get_login_status()
    print(f"登录状态: {status}")

    # 先尝试解密 credentials
    print("\n=== 2. 尝试解密 credentials ===")
    creds, err = try_decrypt_creds()
    if creds:
        print(f"解密成功: {str(creds)[:200]}")
    else:
        print(f"解密失败: {err}")

    # 尝试直接调用歌单 API（不登录）
    print("\n=== 3. 试探匿名访问歌单 API ===")
    # Bang Dream 歌单 (id: 4943170241, 加密id: A7587AF9528A4B9F00436694359E35AA)
    results = call_music_api_cookieless("b3010d0000000000877a84a1e79acb4b", "A7587AF9528A4B9F00436694359E35AA")
    for r in results:
        print(r)


if __name__ == "__main__":
    main()